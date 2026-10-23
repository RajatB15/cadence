from datetime import date, timedelta

from cadence_app.analytics import review as RV
from cadence_app.analytics.insights import readiness_on
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_planner import training_ctx


def test_week_review_sections_and_comparison():
    c = training_ctx()
    start = c["as_of"] - timedelta(days=c["as_of"].weekday() + 7)  # last complete Monday
    planned = [{"day": start + timedelta(days=2), "status": "done", "predicted": {"load": 80}, "activity": {"load": 90}},
               {"day": start + timedelta(days=5), "status": "missed", "predicted": {"load": 50}, "activity": None}]
    r = RV.build(c, "week", start + timedelta(days=3), planned, readiness_on)
    assert r["start"] == start and r["end"] == start + timedelta(days=6) and r["complete"]
    t = r["training"]
    assert t["sessions"] == 4 and t["quality"] == 1 and t["long_run_min"] == 90 and t["by_sport"] == {"run": 4}
    assert r["plan"] == {"planned": 2, "done": 1, "missed": 1, "predicted_load": 80, "actual_load": 90}
    assert r["fitness"]["start"] and r["recovery"]["readiness"] and r["sleep"]["nights_at_need"] == 7
    assert r["vs_previous"]["sessions"] == 0 and r["verdict"] and r["focus"]["title"]
    assert [h["value"] for h in r["highlights"]][1] == "90 min"
    assert "Next:" in RV.headline(r)


def test_sleep_debt_becomes_the_focus():
    c = training_ctx()
    for d in list(c["series"]["sleep_hours"])[-14:]:
        c["series"]["sleep_hours"][d] = 6.5
    r = RV.build(c, "week", c["as_of"] - timedelta(days=7), [], readiness_on)
    assert r["focus"]["title"] == "Sleep"


def test_month_review_has_trends():
    c = training_ctx(days=84)
    r = RV.build(c, "month", c["as_of"] - timedelta(days=35), [], readiness_on)
    assert r["kind"] == "month" and r["start"].day == 1 and "trends" in r and r["verdict"].startswith("Fitness")


def test_review_api(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    w = client.get("/api/reviews/week").json()
    assert w["has_data"] and w["start"] == "2026-10-12" and w["end"] == "2026-10-18" and w["complete"]
    m = client.get("/api/reviews/month").json()
    assert m["start"] == "2026-09-01" and m["end"] == "2026-09-30"
    assert client.get("/api/reviews/week?start=2026-10-19").json()["complete"] is False  # this week so far
    assert client.get("/api/reviews/week?start=2030-01-01").status_code == 400
    assert date.fromisoformat(w["first"]) < date(2026, 1, 1)
