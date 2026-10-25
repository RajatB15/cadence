import json
from datetime import datetime, timedelta, timezone

from cadence_app import food_crawl as C

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def build(tmp_path, parsed, failed=(), slugs=("a-1", "b-2", "c-3", "d-4", "e-5", "-nameless")):
    hm = tmp_path / "library"
    hm.mkdir()
    (hm / "sitemap-seo.xml").write_text("".join(f"<loc>https://x.test/web/nutrifacts/{s}</loc>" for s in slugs))
    (hm / "nutrifacts.jsonl").write_text("".join(json.dumps({"id": i, "fetched_at": t.isoformat()}) + "\n" for i, t in parsed))
    (hm / "failed.jsonl").write_text("".join(json.dumps({"id": i, "error": e}) + "\n" for i, e in failed))
    return tmp_path


def test_pages_are_parsed_failed_or_not_tried_and_a_retry_that_worked_is_not_failed(tmp_path):
    t = NOW - timedelta(minutes=5)
    fd = build(tmp_path, [("a-1", t), ("a-1", t), ("b-2", t)], failed=[("b-2", "http 503"), ("c-3", "http 503"), ("d-4", "timed out")])
    p = C.progress(fd, NOW)
    assert (p["total"], p["parsed"], p["failed"], p["untried"]) == (5, 2, 2, 1)  # the nameless page is not counted; the repeat line is one page
    assert {r["reason"]: r["pages"] for r in p["failed_reasons"]} == {"http 503": 1, "timed out": 1}
    assert p["rate_per_min"] is None and p["finish"] is None  # too little history to project from


def test_the_timeline_fills_quiet_periods_with_zero_and_counts_every_page_once(tmp_path):
    start = NOW - timedelta(hours=2)
    pages = [(f"p-{i}", start + timedelta(minutes=i)) for i in range(60)]
    p = C.progress(build(tmp_path, pages, slugs=[s for s, _ in pages] + ["left-1"]), NOW)
    tl = p["timeline"]
    assert sum(r["pages"] for r in tl) == 60 and tl[-1]["cumulative"] == 60
    assert any(r["pages"] == 0 for r in tl)  # the last hour had no fetches
    assert p["rate_per_min"] == 0.0 and p["finish"] is None  # no pace: no finish time


def test_a_steady_pace_gives_a_rough_finish_time(tmp_path):
    pages = [(f"p-{i}", NOW - timedelta(minutes=60 - i)) for i in range(60)]  # 1 page a minute for an hour
    p = C.progress(build(tmp_path, pages, slugs=[s for s, _ in pages] + [f"left-{i}" for i in range(30)]), NOW)
    assert p["rate_per_min"] == 1.0 and datetime.fromisoformat(p["finish"]) == NOW + timedelta(minutes=30)


def test_no_food_data_means_no_progress(tmp_path):
    assert C.progress(None, NOW) is None and C.progress(tmp_path, NOW) is None
