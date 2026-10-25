#!/usr/bin/env python3
"""One pass of the food deploy loop. launchd runs this every 15 minutes (scripts/food-sync.sh install).

Each pass:
1. Keeps the the source site crawl alive: restarts any missing worker while pages are left to fetch, and runs one pass over
   the pages that failed at most every 6 hours (so dead pages don't cause a restart loop).
2. Rebuilds the catalogue from everything crawled so far (`cadence_app.food_import`), written atomically.
3. Makes it live: the running service reloads the catalogue when the file changes; one request here confirms it.
4. Backs the data up: commits and pushes the private `food-data` repo at most once an hour (or when the crawl is done),
   so a day of crawling doesn't bloat the repo with a commit per pass.

Nothing here touches the public repo or your health vault. Output goes to food-data/library/sync.log.
"""

from __future__ import annotations

import fcntl
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOOD = ROOT / "food-data"
HM = FOOD / "library"
PY = ROOT / "app" / "backend" / ".venv" / "bin" / "python"
SERVICE = "http://127.0.0.1:8765"
SHARDS = 4  # being measured: earlier, 5 workers were no faster than 2 because the site stalls requests under heavier load
COMMIT_EVERY_S = 3600
RETRY_FAILED_EVERY_S = 3600


def log(msg: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')} {msg}", flush=True)


def ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.add(json.loads(line)["id"])
        except (ValueError, KeyError):
            continue
    return out


def pending() -> dict:
    sys.path.insert(0, str(FOOD / "tools"))
    import crawl_library as crawler  # noqa: PLC0415 (only exists when the submodule is checked out)

    slugs = [crawler.slug(u) for u in crawler.sitemap_urls()]
    done, failed = ids(HM / "nutrifacts.jsonl"), ids(HM / "failed.jsonl")
    return {"total": len(slugs), "done": len(done & set(slugs)),
            "untried": sum(1 for s in slugs if s not in done and s not in failed),
            "retry": sum(1 for s in slugs if s in failed and s not in done)}


def crawler_running(*flags: str) -> bool:
    return subprocess.run(["/usr/bin/pgrep", "-f", "crawl_library.py " + " ".join(flags)], capture_output=True).returncode == 0


def start_crawler(*args: str) -> None:
    log_file = (HM / "crawl.log").open("a")
    subprocess.Popen(["/usr/bin/caffeinate", "-i", str(PY), "-I", str(FOOD / "tools" / "crawl_library.py"), *args],
                     stdout=log_file, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True, cwd=FOOD)


def ensure_crawlers(p: dict) -> None:
    state_file = HM / "supervisor.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    now = time.time()
    retry_due = p["retry"] > 0 and now - state.get("last_retry_pass", 0) > RETRY_FAILED_EVERY_S and not crawler_running("--retry")
    if p["untried"] == 0 and not retry_due:
        log(f"crawl: nothing to fetch ({p['done']}/{p['total']} done, {p['retry']} failed pages waiting for the next retry window)")
        return
    missing = [i for i in range(SHARDS) if p["untried"] > 0 and not crawler_running("--shard", f"{i}/{SHARDS}")]
    for i in missing:
        start_crawler("--shard", f"{i}/{SHARDS}")
    if retry_due:  # one pass over the failed pages, run beside the main workers
        start_crawler("--retry")
        state["last_retry_pass"] = now
        state_file.write_text(json.dumps(state))
    log(f"crawl: {p['done']}/{p['total']} done, {p['untried']} untried, {p['retry']} to retry; "
        + (f"restarted workers {missing}" if missing else f"{SHARDS} workers running")
        + ("; started a retry pass" if retry_due else ""))


def build_catalogue() -> int | None:
    if not (HM / "nutrifacts.jsonl").exists():
        log("catalogue: no crawled data yet")
        return None
    r = subprocess.run([str(PY), "-m", "cadence_app.food_import", str(FOOD)], cwd=ROOT / "app" / "backend", capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        log(f"catalogue: build FAILED: {r.stderr.strip()[-300:]}")
        return None
    report = json.loads(r.stdout)
    log(f"catalogue: {report['dishes']} dishes from {report['pages']} pages ({report['merged_alias_pages']} alias pages merged)")
    return report["dishes"]


def go_live(expected: int | None) -> None:
    """The service reloads the catalogue when the file changes; asking for the dish list confirms it."""
    try:
        with urllib.request.urlopen(f"{SERVICE}/api/food/dishes", timeout=60) as resp:
            n = len(json.loads(resp.read())["dishes"])
        log(f"live: the service lists {n} dishes")
    except Exception as e:  # noqa: BLE001 (the service may be restarting; the next pass will check again)
        log(f"live: could not reach the service ({e}); it will load the catalogue on its next start")


def git(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/git", "-C", str(FOOD), *args], capture_output=True, text=True, timeout=timeout)


def back_up(p: dict, dishes: int | None) -> None:
    if not (FOOD / ".git").exists():
        return
    git("add", "library", "tools", "README.md", ".gitignore")
    if not git("status", "--porcelain").stdout.strip():
        log("backup: nothing changed")
        return
    last = int(git("log", "-1", "--format=%ct").stdout.strip() or 0)
    finished = p["untried"] == 0 and p["retry"] == 0
    if time.time() - last < COMMIT_EVERY_S and not finished:
        log("backup: changes waiting; next commit within the hour")
        return
    msg = f"Food data update: {p['done']} of {p['total']} pages, {dishes if dishes is not None else '?'} dishes"
    c = git("commit", "-q", "-m", msg)
    if c.returncode != 0:
        log(f"backup: commit failed: {c.stderr.strip()[-200:]}")
        return
    push = git("push", "-q", "origin", "HEAD", timeout=600)
    log("backup: pushed to the private repo" if push.returncode == 0 else f"backup: push failed: {push.stderr.strip()[-200:]}")


def main() -> int:
    if not (FOOD / "tools" / "crawl_library.py").exists():
        log("food-data submodule is not checked out; nothing to do (git submodule update --init)")
        return 0
    lock = (HM / ".sync.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("another pass is still running; skipping")
        return 0
    p = pending()
    ensure_crawlers(p)
    dishes = build_catalogue()
    go_live(dishes)
    back_up(p, dishes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
