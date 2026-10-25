"""Progress of the food library build, read from the private `food-data` folder: how many the source site pages are parsed,
failed or not tried yet, how fast, and what the pages became (dishes, merged aliases, dropped by checks).

Counts only: no page content leaves this module. Pure counting in `progress`; `workers` asks the OS which crawl
processes are alive. Rate and finish time are projections from the last hour of fetches and are shown as rough.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

BUCKET_MIN = 10
HISTORY_H = 24
RATE_WINDOW_MIN = 60
MIN_RATE_MIN = 30  # no finish estimate until the crawl has run this long inside the window


def _lines(path: Path):
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def sitemap_slugs(path: Path) -> list[str]:
    """Page names in the sitemap, minus the nameless entries the crawler skips (they always fail)."""
    if not path.is_file():
        return []
    seen: dict[str, None] = {}
    for loc in re.findall(r"<loc>([^<]*/web/nutrifacts/[^<]+)</loc>", path.read_text(encoding="utf-8")):
        slug = loc.rsplit("/", 1)[1]
        if not slug.startswith("-"):
            seen.setdefault(slug)
    return list(seen)


def workers() -> dict:
    """Crawl processes alive right now: sharded fetchers and the retry runner."""
    def alive(pattern: str) -> int:
        out = subprocess.run(["/usr/bin/pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
        return len(out)

    interpreter = r"^[^ ]*[Pp]ython[^ ]* .*crawl_library\.py"  # the interpreter itself, not the caffeinate wrapper around it
    return {"fetchers": alive(interpreter + r" --shard"), "retry": alive(interpreter + r" --retry") > 0}


def progress(food_data: Path | None, now: datetime, running: dict | None = None) -> dict | None:
    hm = food_data / "library" if food_data else None
    if hm is None or not (hm / "sitemap-seo.xml").is_file():
        return None
    slugs = sitemap_slugs(hm / "sitemap-seo.xml")
    wanted = set(slugs)
    first_seen: dict[str, datetime] = {}
    for r in _lines(hm / "nutrifacts.jsonl"):
        i = r.get("id")
        if i in wanted and i not in first_seen:
            try:
                first_seen[i] = datetime.fromisoformat(r["fetched_at"])
            except (KeyError, ValueError):
                first_seen[i] = now  # kept as parsed; just not placed on the timeline
    last_error: dict[str, str] = {}
    for r in _lines(hm / "failed.jsonl"):
        if r.get("id") in wanted:
            last_error[r["id"]] = str(r.get("error", "unknown"))
    failed = {i: e for i, e in last_error.items() if i not in first_seen}
    parsed, total = len(first_seen), len(slugs)
    out: dict = {
        "total": total, "parsed": parsed, "failed": len(failed), "untried": total - parsed - len(failed),
        "failed_reasons": [{"reason": k, "pages": v} for k, v in Counter(failed.values()).most_common(6)],
        "workers": running if running is not None else {"fetchers": 0, "retry": False},
        "now": now.isoformat(),
    }
    out["timeline"], out["rate_per_min"], out["finish"] = _timeline(first_seen, now, total - parsed - len(failed))
    out["library"] = _library(hm / "catalogue_report.json", parsed)
    return out


def _bucket(t: datetime) -> datetime:
    return t.replace(minute=t.minute - t.minute % BUCKET_MIN, second=0, microsecond=0)


def _timeline(first_seen: dict[str, datetime], now: datetime, untried: int):
    """Pages parsed per 10 minutes over the last day (zero when the crawler was quiet), the recent pace and a rough finish."""
    if not first_seen:
        return [], None, None
    now = now.astimezone(timezone.utc)
    start = _bucket(max(min(first_seen.values()), now - timedelta(hours=HISTORY_H)).astimezone(timezone.utc))
    counts = Counter(_bucket(t.astimezone(timezone.utc)) for t in first_seen.values())
    before = sum(1 for t in first_seen.values() if _bucket(t.astimezone(timezone.utc)) < start)
    rows, total, t = [], before, start
    while t <= now:
        n = counts.get(t, 0)
        total += n
        rows.append({"at": t.isoformat(), "pages": n, "cumulative": total})
        t += timedelta(minutes=BUCKET_MIN)
    window_start = now - timedelta(minutes=RATE_WINDOW_MIN)
    recent = [t for t in first_seen.values() if t.astimezone(timezone.utc) >= window_start]
    ran_min = min(RATE_WINDOW_MIN, (now - min(min(first_seen.values()).astimezone(timezone.utc), now)).total_seconds() / 60)
    rate = len(recent) / RATE_WINDOW_MIN if ran_min >= MIN_RATE_MIN else None
    finish = None
    if rate and rate > 0 and untried > 0:
        finish = (now + timedelta(minutes=untried / rate)).isoformat()
    return rows, (round(rate, 1) if rate is not None else None), finish


def _library(report_path: Path, parsed: int) -> dict | None:
    if not report_path.is_file():
        return None
    try:
        r = json.loads(report_path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    dropped = [{"reason": k, "pages": v} for k, v in sorted((r.get("dropped") or {}).items(), key=lambda kv: -kv[1])]
    return {"pages": r.get("pages"), "dishes": r.get("dishes"), "merged": r.get("merged_alias_pages"),
            "dropped": dropped, "no_latin_name": r.get("skipped_no_latin_name"),
            "with_portion": r.get("with_household_portion"), "unverified": r.get("unverified")}
