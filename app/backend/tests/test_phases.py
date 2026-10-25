from datetime import date, timedelta

import pytest

from cadence_app import phases
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)

START, END = date(2026, 11, 1), date(2026, 11, 30)


def act(i: int, day: date, minutes: float = 30, km: float | None = 5, family: str = "run", load: float | None = 40, gain: float | None = None) -> dict:
    return {"id": i, "name": f"s{i}", "day": day, "family": family, "duration_s": minutes * 60, "distance_m": km * 1000 if km else None,
            "ascent_m": gain, "load": load, "vo2max": None}


def spec(*pillars: dict) -> dict:
    return {"name": "No Break November", "tagline": "", "emoji": "", "color": "#ffffff", "start_date": START, "end_date": END, "pillars": list(pillars)}


MOVE = {"id": "p1", "kind": "daily", "metric": "moved", "label": "", "family": None, "target": 20.0, "passes": 0}


def test_daily_streak_miss_and_pending_today():
    # moved on 1-4, skipped the 5th, moved 6-8; today (8th) is judged only if the bar is met
    acts = [act(i, START + timedelta(days=i)) for i in (0, 1, 2, 3, 5, 6)]
    out = phases.assemble(spec(MOVE), phases.Inputs(acts=acts, first_activity_day=START), date(2026, 11, 8))
    p = out["pillars"][0]
    assert (p["hits"], p["misses"], p["streak"], p["best_streak"]) == (6, 1, 2, 4)
    assert p["intact"] is False and p["status"] == "slipping"  # 6/7 judged
    assert [c["status"] for c in p["cells"]][4:8] == ["miss", "hit", "hit", "pending"]  # 8th: nothing yet, not a miss
    assert p["cells"][-1]["status"] == "future"


def test_rest_passes_keep_the_challenge_intact():
    pillar = {**MOVE, "passes": 2}
    acts = [act(i, START + timedelta(days=i)) for i in (0, 2, 3)]
    p = phases.assemble(spec(pillar), phases.Inputs(acts=acts, first_activity_day=START), date(2026, 11, 4))["pillars"][0]
    assert p["misses"] == 1 and p["intact"] and p["passes_left"] == 1 and p["status"] == "on"


def test_unknown_sleep_night_is_not_a_miss_and_does_not_break_the_streak():
    sleep = {"id": "p1", "kind": "daily", "metric": "sleep_h", "label": "", "family": None, "target": 7.0, "passes": 0}
    series = {START: 7.5, START + timedelta(days=2): 7.2}  # the 2nd has no record
    p = phases.assemble(spec(sleep), phases.Inputs(metrics={"sleep_hours": series}), date(2026, 11, 4))["pillars"][0]
    assert (p["hits"], p["misses"], p["unknown"], p["streak"]) == (2, 0, 1, 2)


def test_habit_no_counts_zero_answers_and_skips_unanswered_days():
    habit = {"id": "p1", "kind": "habit", "metric": "habit", "behaviour": "alcohol", "want": "no", "label": "", "family": None, "target": 1, "passes": 0}
    answers = {START: 0.0, START + timedelta(days=1): 0.0, START + timedelta(days=3): 2.0}
    p = phases.assemble(spec(habit), phases.Inputs(habits={"alcohol": answers}), date(2026, 11, 5))["pillars"][0]
    assert (p["hits"], p["misses"], p["unknown"], p["best_streak"], p["streak"]) == (2, 1, 1, 2, 0)


def test_total_pace_projection_and_family_filter():
    pillar = {"id": "p1", "kind": "total", "metric": "distance_km", "label": "", "family": "run", "target": 100.0}
    acts = [act(i, START + timedelta(days=i), km=5) for i in range(10)] + [act(99, START, km=40, family="ride")]
    out = phases.assemble(spec(pillar), phases.Inputs(acts=acts, first_activity_day=START), date(2026, 11, 10))
    p = out["pillars"][0]
    assert p["value"] == 50 and p["expected"] == pytest.approx(33.33, abs=0.01) and p["status"] == "ahead"
    assert p["projection"] is None  # 10 days is too early to project
    later = phases.assemble(spec(pillar), phases.Inputs(acts=acts, first_activity_day=START), date(2026, 11, 20))["pillars"][0]
    assert later["projection"] == pytest.approx(75.0, abs=0.1) and later["status"] == "behind"


def test_load_total_counts_sessions_without_a_load_as_missing_not_zero():
    pillar = {"id": "p1", "kind": "total", "metric": "load", "label": "", "family": None, "target": 500.0}
    acts = [act(1, START, load=60), act(2, START + timedelta(days=1), load=None)]
    p = phases.assemble(spec(pillar), phases.Inputs(acts=acts, first_activity_day=START), date(2026, 11, 3))["pillars"][0]
    assert p["value"] == 60 and p["missing"] == 1


def test_weekly_pillar_never_misses_a_partial_edge_week():
    pillar = {"id": "p1", "kind": "weekly", "metric": "sessions", "label": "", "family": None, "target": 3.0}
    # 1 Nov 2026 is a Sunday: the first week holds a single phase day. Week of the 2nd: 3 sessions. Week of the 9th: 1.
    acts = [act(1, START)] + [act(i, date(2026, 11, 2) + timedelta(days=i)) for i in (2, 3, 4)] + [act(9, date(2026, 11, 10))]
    p = phases.assemble(spec(pillar), phases.Inputs(acts=acts, first_activity_day=START), date(2026, 11, 20))["pillars"][0]
    weeks = {w["start"]: w for w in p["weeks"]}
    assert weeks[date(2026, 10, 26)]["partial"] and weeks[date(2026, 10, 26)]["hit"] is None
    assert weeks[date(2026, 11, 2)]["hit"] is True and weeks[date(2026, 11, 9)]["hit"] is False
    assert (p["hits"], p["misses"]) == (1, 1)
    assert weeks[date(2026, 11, 16)]["current"] and weeks[date(2026, 11, 16)]["hit"] is None


def test_before_window_is_unavailable_without_history_and_vitals_need_enough_readings():
    acts = [act(1, START + timedelta(days=1))]
    out = phases.assemble(spec(), phases.Inputs(acts=acts, first_activity_day=START), date(2026, 11, 10))
    assert out["before"]["available"] is False  # history starts inside the phase
    assert out["vitals"]["hrv"]["first"] is None  # fewer than 4 weeks elapsed
    sleep = {START + timedelta(days=i): 7.0 + (i >= 20) for i in range(30)}
    late = phases.assemble(spec(), phases.Inputs(metrics={"sleep_hours": sleep}, first_activity_day=START), date(2026, 12, 1))
    assert late["vitals"]["sleep"]["first"] == 7.0 and late["vitals"]["sleep"]["latest"] == pytest.approx(7.8, abs=0.1)
    assert late["state"] == "done" and late["days_left"] == 0


def goal(metric: str, target: float, **kw) -> dict:
    return {"id": "p1", "kind": "goal", "metric": metric, "label": "", "family": None, "target": target, **kw}


def test_weight_goal_measures_from_the_last_reading_before_the_phase():
    weights = [(date(2026, 10, 25), 80.0), (START + timedelta(days=2), 79.0), (START + timedelta(days=12), 77.5)]
    p = phases.assemble(spec(goal("weight_kg", 75)), phases.Inputs(weights=weights), date(2026, 11, 15))["pillars"][0]
    assert (p["base"], p["current"], p["better"], p["n"]) == (80.0, 77.5, "lower", 2)
    assert p["progress"] == pytest.approx(0.5) and p["status"] == "on"  # half the way after half the days
    done = phases.assemble(spec(goal("weight_kg", 77.5)), phases.Inputs(weights=weights), date(2026, 11, 15))["pillars"][0]
    assert done["status"] == "complete" and done["progress"] == 1.0


def test_pace_goal_needs_three_runs_and_compares_with_the_stretch_before():
    before = [act(i, START - timedelta(days=3 + i), minutes=33, km=5) for i in range(3)]  # 6:36 /km
    now = [act(10 + i, START + timedelta(days=i), minutes=30, km=5) for i in range(3)]  # 6:00 /km
    inp = phases.Inputs(acts=before + now, first_activity_day=START - timedelta(days=5))
    p = phases.assemble(spec(goal("run_pace", 330)), inp, date(2026, 11, 10))["pillars"][0]
    assert p["base"] == pytest.approx(396) and p["current"] == pytest.approx(360) and p["better"] == "lower"
    assert p["progress"] == pytest.approx((396 - 360) / (396 - 330))
    two = phases.Inputs(acts=now[:2], first_activity_day=START)
    p2 = phases.assemble(spec(goal("run_pace", 330)), two, date(2026, 11, 10))["pillars"][0]
    assert p2["current"] is None and p2["no_data"] is True and p2["base"] is None  # too few runs: unknown, not zero


def test_best_pace_ignores_short_runs_and_longest_respects_the_sport():
    acts = [act(1, START, minutes=10, km=2), act(2, START + timedelta(days=1), minutes=25, km=5), act(3, START + timedelta(days=2), minutes=300, km=40, family="ride")]
    inp = phases.Inputs(acts=acts, first_activity_day=START)
    best = phases.assemble(spec(goal("run_best_pace", 300)), inp, date(2026, 11, 5))["pillars"][0]
    assert best["current"] == pytest.approx(300) and best["status"] == "complete"  # the 2 km run is too short to count
    longest = phases.assemble(spec(goal("longest_km", 10, family="run")), inp, date(2026, 11, 5))["pillars"][0]
    assert longest["current"] == 5 and longest["better"] == "higher"


def test_recent_average_goal_needs_enough_readings():
    series = {START - timedelta(days=d): 58.0 for d in range(1, 15)} | {START + timedelta(days=d): 54.0 for d in range(10)}
    p = phases.assemble(spec(goal("resting_hr", 52)), phases.Inputs(metrics={"resting_hr": series}), date(2026, 11, 10))["pillars"][0]
    assert p["base"] == 58.0 and p["current"] == 54.0 and p["better"] == "lower"
    sparse = phases.assemble(spec(goal("resting_hr", 52)), phases.Inputs(metrics={"resting_hr": {START: 54.0}}), date(2026, 11, 10))["pillars"][0]
    assert sparse["current"] is None and sparse["status"] == "early"


def test_state_and_countdown():
    assert phases.assemble(spec(), phases.Inputs(), date(2026, 10, 28))["starts_in"] == 4
    mid = phases.assemble(spec(), phases.Inputs(), date(2026, 11, 15))
    assert (mid["state"], mid["day_number"], mid["days_left"], mid["total_days"]) == ("active", 15, 15, 30)


@pytest.mark.parametrize("bad, message", [
    ({"kind": "daily", "metric": "moved", "target": 0}, "Target"),
    ({"kind": "daily", "metric": "nope", "target": 5}, "measure"),
    ({"kind": "habit", "behaviour": "ghost"}, "journal"),
    ({"kind": "total", "metric": "distance_km", "target": 10, "family": "flying"}, "activity"),
    ({"kind": "daily", "metric": "moved", "target": 20, "passes": -1}, "passes"),
    ({"kind": "goal", "metric": "weight_kg", "target": 5}, "Target"),
    ({"kind": "goal", "metric": "mood", "target": 5}, "goal"),
])
def test_validation(bad, message):
    with pytest.raises(phases.PhaseError, match=message):
        phases.clean_pillars([bad], {"alcohol"})


def test_clean_rejects_backwards_dates_and_bad_colour():
    base = {"name": "x", "start": END, "end": START, "pillars": []}
    with pytest.raises(phases.PhaseError, match="before"):
        phases.clean(base, set())
    with pytest.raises(phases.PhaseError, match="Colour"):
        phases.clean({**base, "start": START, "end": END, "color": "red"}, set())


def body(**kw):
    return {"name": "No Break November", "start": "2026-11-01", "end": "2026-11-30", "emoji": "🔥",
            "pillars": [{"kind": "daily", "metric": "moved", "target": 20, "passes": 0}], **kw}


def test_api_round_trip_and_default_winter_arc(env):  # noqa: F811
    client, _ = env
    first = client.get("/api/phases").json()["items"]
    assert [p["name"] for p in first] == ["Winter Arc"] or first == []  # seeded once, only while the year's Winter Arc hasn't ended
    made = client.post("/api/phases", json=body(), headers=MUTATE)
    assert made.status_code == 200 and made.json()["pillars"][0]["id"] == "p1"
    pid = made.json()["id"]
    assert client.get(f"/api/phases/{pid}").json()["name"] == "No Break November"
    edited = client.put(f"/api/phases/{pid}", json=body(name="Never Break"), headers=MUTATE)
    assert edited.json()["name"] == "Never Break"
    assert client.post("/api/phases", json=body(end="2026-10-01"), headers=MUTATE).status_code == 400
    assert client.post("/api/phases", json=body(pillars=[{"kind": "habit", "behaviour": "ghost"}]), headers=MUTATE).status_code == 400
    assert client.delete(f"/api/phases/{pid}", headers=MUTATE).json() == {"deleted": True}
    assert client.get(f"/api/phases/{pid}").status_code == 404
    # deleting the seeded phase does not bring it back
    for p in client.get("/api/phases").json()["items"]:
        client.delete(f"/api/phases/{p['id']}", headers=MUTATE)
    assert client.get("/api/phases").json()["items"] == []
