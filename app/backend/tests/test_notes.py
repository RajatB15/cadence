from datetime import date, datetime, timedelta

from cadence_app.analytics import athlete as A
from cadence_app.analytics import notes, score
from cadence_app.analytics.insights import assemble, weekly_plan
from cadence_app.analytics.weight import TrendPoint

D0 = date(2026, 3, 2)  # a Monday
EASY = (600, 3000, 0, 0, 0)
HARD = (300, 900, 600, 1500, 300)
GREY = (300, 1200, 2100, 0, 0)


def insights_weekly_plan(c: dict) -> dict | None:
    return weekly_plan(c, c["zones"])


def act(i: int, day: date, zones=EASY, family="run", load=80.0, **kw) -> A.Act:
    start = datetime.combine(day, datetime.min.time()).replace(hour=kw.pop("hour", 7))
    return A.Act(
        id=i, day=day, start_local=start, end_local=start + timedelta(hours=1), family=family, type=family, name="x",
        load=load, distance_m=kw.pop("distance_m", 10000), moving_s=kw.pop("moving_s", 3600), avg_hr=150,
        speed_mps=kw.pop("speed_mps", 2.8), zones_s=zones, **kw,
    )


ZONES = {"method": "LT", "floors": [100, 120, 140, 160, 175], "max": 190, "threshold": 165}


def ctx(acts: list[A.Act], series: dict | None = None, days: int = 120, **kw) -> dict:
    """The real context pipeline on synthetic data; an anchor metric pins the date span."""
    first, as_of = D0, D0 + timedelta(days=days - 1)
    series = {**(series or {}), "_anchor": {first: 0.0, as_of: 0.0}}
    return assemble("demo", series, acts, as_of, zones=kw.pop("zones", ZONES), **kw)


def test_intensity_and_verdicts_flag_grey_and_repeated_hard_days():
    acts = [act(1, D0, EASY), act(2, D0 + timedelta(days=1), GREY), act(3, D0 + timedelta(days=2), HARD),
            act(4, D0 + timedelta(days=3), HARD), act(5, D0 + timedelta(days=4), HARD)]
    v = notes.verdicts(ctx(acts))
    assert [v[i]["label"] for i in range(1, 6)] == ["Easy", "Grey zone", "Key session", "Key session", "Hard again"]
    assert notes.intensity(act(9, D0, family="strength")) is None
    assert notes.verdict(act(9, D0, EASY, family="strength")) is None
    assert notes.verdict(act(9, D0, HARD, family="strength"))["label"] == "High intensity"
    assert notes.verdict(act(9, D0, HARD, moving_s=5400))["label"] == "Long & hard"


def test_session_notes_explain_grey_zone_with_easy_cap():
    acts = [act(i, D0 + timedelta(days=i), EASY) for i in range(10)] + [act(99, D0 + timedelta(days=12), GREY)]
    out = notes.session(ctx(acts), 99)
    grey = next(n for n in out["notes"] if n["id"] == "intensity")
    assert out["verdict"]["label"] == "Grey zone" and grey["severity"] == "warn"
    assert "under 139 bpm" in grey["action"]
    assert notes.session(ctx(acts), 12345) is None


def test_session_notes_spot_records_and_drift():
    acts = [act(i, D0 + timedelta(days=i * 2), distance_m=8000) for i in range(8)]
    acts.append(act(50, D0 + timedelta(days=20), distance_m=21000, moving_s=7200))
    t = list(range(0, 5400, 5))
    streams = {"t": t, "speed": [3.0] * len(t), "heart_rate": [140 if s < 3000 else 156 for s in t]}
    out = notes.session(ctx(acts), 50, streams)
    ids = {n["id"]: n for n in out["notes"]}
    assert ids["record_distance"]["title"] == "Longest run on record"
    assert ids["drift"]["severity"] == "warn"


def test_day_notes_tag_metrics_and_explain_low_hrv():
    days = [D0 + timedelta(days=i) for i in range(60)]
    d = days[-1]
    hrv = {x: 60.0 + (i % 3) for i, x in enumerate(days)}
    hrv[d] = 40.0
    series = {
        "hrv": hrv, "sleep_hours": {x: 7.8 for x in days} | {d: 5.9}, "bedtime": {x: -40.0 for x in days} | {d: 55.0},
        "spo2": {d: 92.0}, "resting_hr": {x: 50.0 + (i % 2) for i, x in enumerate(days)},
    }
    out = notes.day(ctx([], series, days=60), d)
    by = {n["id"]: n for n in out["notes"]}
    assert by["hrv"]["severity"] == "warn" and "falling asleep at 00:55" in by["hrv"]["detail"]
    assert by["sleep_duration"]["title"] == "Short night" and "sleep_hours" in by["sleep_duration"]["metrics"]
    assert by["spo2"]["metrics"] == ["spo2"] and "diagnosis" in by["spo2"]["action"]
    assert out["readiness"] is not None


def test_weight_notes_guard_rate_and_frequency():
    today = date(2026, 6, 1)
    pts = [TrendPoint(today - timedelta(days=7 * i), 80.0, 80.0, 0.5) for i in range(3)][::-1]
    fast = notes.weight(pts, -1.2, 72.0, today)
    assert any(n["id"] == "rate" and n["severity"] == "warn" for n in fast)
    assert any(n["id"] == "weigh_freq" for n in fast)
    healthy = notes.weight(pts, -0.4, 72.0, today)
    assert any(n["id"] == "rate" and n["severity"] == "good" for n in healthy)
    assert notes.weight([], None, None, today) == []


def test_brief_scores_streaks_and_week_targets():
    acts, i = [], 0
    for w in range(16):
        for dd in (0, 2, 4, 5):
            i += 1
            acts.append(act(i, D0 + timedelta(days=7 * w + dd), HARD if dd == 2 else EASY))
    days = [D0 + timedelta(days=k) for k in range(112)]
    series = {
        "hrv": {x: 55.0 + (k % 4) for k, x in enumerate(days)}, "resting_hr": {x: 50.0 + (k % 2) for k, x in enumerate(days)},
        "sleep_hours": {x: 7.8 for x in days}, "sleep_score": {x: 82.0 for x in days}, "bedtime": {x: -45.0 for x in days},
    }
    b = notes.brief(ctx(acts, series, days=112))
    assert {s["key"]: s["current"] for s in b["streaks"]}["sleep"] == 112
    assert {it["key"] for it in b["week"]["items"]} >= {"load", "sessions", "hard", "sleep"}
    assert b["today"]["kind"] in {"key", "easy", "rest", "long", "done", "strength"}
    assert b["recent"]["label"] in {"Yesterday", "Saturday"} and b["recent"]["items"][0]["verdict"]["label"] == "Easy"

    c = ctx(acts, series, days=112)
    rep = score.report(c, days=30)
    groups = {g["key"]: g["score"] for g in rep["groups"]}
    assert {"train", "sleep"} <= set(groups) and 0 <= rep["score"] <= 100 and len(rep["history"]) == 30
    assert next(f for f in rep["factors"] if f["key"] == "consistency")["score"] == 100
    assert rep["gaps"] == sorted(rep["gaps"], key=lambda f: -f["points_lost"])
    assert next(f for f in rep["factors"] if f["key"] == "intensity")["score"] == 100  # 83% easy meets the 80% target
    assert all(f["tip"] and f["target"] for f in rep["factors"])


def test_after_a_session_today_explains_what_is_still_open():
    acts, i = [], 0
    for w in range(8):
        for dd in (0, 2, 4):
            i += 1
            acts.append(act(i, D0 + timedelta(days=7 * w + dd), HARD if dd == 2 else EASY))
    days = [D0 + timedelta(days=k) for k in range(60)]
    series = {"hrv": {x: 55.0 for x in days}, "resting_hr": {x: 50.0 for x in days}, "sleep_score": {x: 85.0 for x in days},
              "sleep_hours": {x: 7.8 for x in days}, "body_battery": {x: 92.0 for x in days}}
    today = D0 + timedelta(days=59)  # a Saturday; nothing hard yet this week
    gym = act(999, today, (3000, 600, 0, 0, 0), family="strength", load=60, distance_m=None)
    c = ctx(acts + [gym], series, days=60)
    plan = insights_weekly_plan(c)
    week = notes.week_progress(c, plan)
    r = notes.readiness_on(c, today)
    out = notes.today_session(c, r, week, plan, now_hour=10)
    assert out["kind"] == "done" and out["status"] in {"open", "matched"} and out["planned"]
    assert out["title"] != "Done for today" and out["next"]
    late = notes.today_session(c, r, week, plan, now_hour=21)
    assert late["second"] is None
