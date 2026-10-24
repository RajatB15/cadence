from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from cadence_app import goal_store as store
from cadence_app.analytics import goals as G
from cadence_app.analytics import notes
from cadence_app.analytics import performance as P
from cadence_app.analytics import weight as W
from cadence_app.db import MIGRATIONS_DIR, make_engine, make_session_factory
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_notes import D0, EASY, act

TODAY = date(2026, 10, 24)


def run_ctx(cs=4.0, d_prime=200.0, slope_per_month=0.0, months=8, extra_acts=()):
    hist = [{"day": TODAY - timedelta(days=30 * m), "cs_mps": cs - slope_per_month * m + (0.01 if m % 2 else -0.01)} for m in range(months - 1, -1, -1)]
    hist = [{**h, "cs_mps": round(cs - slope_per_month * (TODAY - h["day"]).days / 30 + (0.012 if i % 2 else -0.012), 3)} for i, h in enumerate(hist)]
    return {"as_of": TODAY, "acts": list(extra_acts), "performance": {
        "critical_speed": {"valid": True, "cs_mps": cs, "d_prime_m": d_prime}, "history": hist}}


def goal(kind="performance", sport="run", date_=None, **spec):
    base = {"id": 1, "kind": kind, "sport": sport, "title": "g", "date": date_, "status": "active", "start_value": None, "spec": {"distance_m": 10000.0, "label": "10 km", **spec}}
    return base


def test_cs_needed_inverts_race_time():
    for d in (3000, 5000, 10000, 21097.5):
        t = P.race_time(d, 4.0, 200.0)
        assert G.cs_needed(d, t, 200.0) == pytest.approx(4.0, rel=1e-6)


def test_probability_rises_with_an_easier_target_and_a_rising_trend():
    flat, rising = G.cs_model(run_ctx()), G.cs_model(run_ctx(slope_per_month=0.04))
    now = P.race_time(10000, 4.0, 200.0)
    easy = G.project_run(flat, 10000, now * 1.05, 84)["probability"]
    even = G.project_run(flat, 10000, now, 84)["probability"]
    hard = G.project_run(flat, 10000, now * 0.93, 84)["probability"]
    assert easy > even > hard and easy >= 0.9 and hard <= 0.1
    assert G.project_run(rising, 10000, now * 0.97, 140)["probability"] > G.project_run(flat, 10000, now * 0.97, 140)["probability"]
    assert G.project_run(flat, 10000, now, 84) == G.project_run(flat, 10000, now, 84)  # seeded: stable between requests


def test_few_history_points_assume_the_uncertainty_and_say_so():
    c = run_ctx(months=3)
    a = G.assess(goal(target_s=2500, date_=TODAY + timedelta(weeks=10)), c, TODAY)
    assert a["state"] == "ok" and a["cs"]["sigma_assumed"] and any("assumed" in x for x in a["caveats"])
    assert a["outlook"]["band"] in ("likely", "plausible", "a stretch", "unlikely") and a["basis"] == "critical speed"
    full = G.assess(goal(target_s=2500, date_=TODAY + timedelta(weeks=10)), run_ctx(), TODAY)
    assert not full["cs"]["sigma_assumed"]


def test_race_without_a_target_still_predicts():
    a = G.assess(goal("race", target_s=None, date_=TODAY + timedelta(weeks=8)), run_ctx(), TODAY)
    assert a["projected"]["p10_s"] <= a["projected"]["p50_s"] <= a["projected"]["p90_s"] and "outlook" not in a and a["roadmap"]


def test_ride_uses_the_best_recent_session_and_a_labelled_heuristic():
    rides = [act(i, TODAY - timedelta(days=20 + i * 5), EASY, family="ride", distance_m=42000, moving_s=4800) for i in range(1, 5)]
    c = {"as_of": TODAY, "acts": rides, "performance": {}}
    g = goal("performance", "ride", TODAY + timedelta(weeks=12), distance_m=40000.0, label="40 km", target_s=4200)
    a = G.assess(g, c, TODAY)
    assert a["basis"] == "best recent session" and a["outlook"]["heuristic"] and a["demonstrated"]["id"] in {r.id for r in rides}
    assert a["outlook"]["band"] in ("plausible", "a stretch", "unlikely")
    already = G.assess({**g, "spec": {**g["spec"], "target_s": 5000}}, c, TODAY)
    assert already["outlook"]["band"] == "likely" and already["achieved_hint"]
    assert G.assess(goal("performance", "swim", None, target_s=900), c, TODAY)["state"] == "no_basis"


def test_ladder_builds_ten_percent_with_recovery_weeks_then_attempts():
    lad = G.ladder(10000, 30000)
    kinds = [w["kind"] for w in lad["weeks"]]
    assert kinds[-2:] == ["easier", "attempt"] and lad["weeks"][-1]["m"] == 30000
    builds = [w["m"] for w in lad["weeks"] if w["kind"] == "build"]
    assert builds == sorted(builds) and builds[0] == 11000 and max(builds) <= 0.85 * 30000 + 1
    assert [w["week"] for w in lad["weeks"] if w["kind"] == "recovery"][0] == 4
    ready = G.ladder(26000, 30000)
    assert [w["kind"] for w in ready["weeks"]] == ["easier", "attempt"]


def test_distance_goal_is_judged_against_the_weeks_available():
    runs = [act(i, TODAY - timedelta(days=7 * i), EASY, distance_m=12000 if i else 14000) for i in range(1, 9)]
    c = {"as_of": TODAY, "acts": runs, "performance": {}}
    soon = G.assess(goal("distance", date_=TODAY + timedelta(weeks=4), distance_m=30000.0), c, TODAY)
    later = G.assess(goal("distance", date_=TODAY + timedelta(weeks=30), distance_m=30000.0), c, TODAY)
    assert soon["outlook"]["band"] == "unlikely" and later["outlook"]["band"] == "likely"
    done = G.assess(goal("distance", distance_m=12000.0), c, TODAY)
    assert done["achieved_hint"] and not soon["achieved_hint"]


def weight_summary(start=84.0, weekly=-0.4, n=40):
    readings = [(TODAY - timedelta(days=n - i), start + weekly / 7 * i + (0.15 if i % 2 else -0.15)) for i in range(n)]
    return W.summarize(readings, TODAY, 78.0)


def test_weight_goal_flags_unrealistic_dates_and_wrong_direction():
    w = G.weight_inputs(weight_summary())
    g = {"id": 3, "kind": "weight", "sport": None, "title": "t", "status": "active", "start_value": 84.0, "spec": {"target_kg": 78.0}, "date": TODAY + timedelta(weeks=3)}
    a = G.assess(g, None, TODAY, w)
    assert a["required"]["too_fast"] and a["gap_kg"] < 0 and a["path"][0]["kg"] == pytest.approx(a["current_kg"], abs=0.06)
    assert notes.goal_headline(a)["tone"] == "warn" and "faster than" in notes.goal_headline(a)["text"]
    relaxed = G.assess({**g, "date": TODAY + timedelta(weeks=20)}, None, TODAY, w)
    assert not relaxed["required"]["too_fast"] and relaxed["earliest_safe"] and relaxed["steady"] > relaxed["earliest_safe"]
    up = G.assess({**g, "spec": {"target_kg": 90.0}, "start_value": 84.0, "date": TODAY + timedelta(weeks=20)}, None, TODAY, w)
    assert up["required"]["wrong_way"] is False and up["rate_flag"] == "wrong_way"
    assert G.assess({**g, "spec": {"target_kg": 90.0}, "start_value": 84.0}, None, TODAY, w)["gap_kg"] > 0
    assert G.assess(g, None, TODAY, None)["state"] == "no_data"


def test_reached_weight_goal_counts_as_achieved_in_either_direction():
    w = G.weight_inputs(weight_summary(start=77.0, weekly=0.0))
    g = {"id": 3, "kind": "weight", "sport": None, "title": "t", "status": "active", "start_value": 84.0, "spec": {"target_kg": 78.0}, "date": None}
    assert G.assess(g, None, TODAY, w)["achieved_hint"]
    assert notes.goal_headline(G.assess(g, None, TODAY, w))["tone"] == "good"


# ---- store ----------------------------------------------------------------------------------------


@pytest.fixture
def session(tmp_path):
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    url = f"sqlite:///{tmp_path / 'g.db'}"
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    with make_session_factory(make_engine(url))() as s:
        yield s


NOW = datetime(2026, 10, 24, 9)


def test_goal_validation_and_titles(session):
    with pytest.raises(store.GoalError):
        store.create(session, {"kind": "race", "sport": "run", "distance_m": 10000}, TODAY, NOW)  # no date
    with pytest.raises(store.GoalError):
        store.create(session, {"kind": "performance", "sport": "ride", "distance_m": 40000}, TODAY, NOW)  # no target
    with pytest.raises(store.GoalError):
        store.create(session, {"kind": "race", "sport": "run", "distance_m": 10000, "date": TODAY - timedelta(days=1)}, TODAY, NOW)
    with pytest.raises(store.GoalError):
        store.create(session, {"kind": "distance", "sport": "swim", "distance_m": 10}, TODAY, NOW)
    g = store.create(session, {"kind": "performance", "sport": "ride", "distance_m": 40000, "speed_kmh": 30}, TODAY, NOW)
    assert g["spec"]["target_s"] == 4800 and g["title"] == "40 km in 1:20:00"
    r = store.create(session, {"kind": "race", "sport": "run", "distance_m": 21097.5, "date": TODAY + timedelta(weeks=9), "target_s": 6000}, TODAY, NOW)
    assert r["spec"]["key"] == "half" and r["title"] == "Half marathon race"


def test_one_weight_goal_at_a_time_and_primary_race_selection(session):
    a = store.create(session, {"kind": "weight", "target_kg": 78}, TODAY, NOW, 84.0)
    b = store.create(session, {"kind": "weight", "target_kg": 76}, TODAY, NOW, 83.0)
    assert store.weight_target(session) == 76.0 and [g["status"] for g in store.listing(session) if g["id"] == a["id"]] == ["dropped"]
    far = store.create(session, {"kind": "race", "sport": "run", "distance_m": 42195, "date": TODAY + timedelta(weeks=20)}, TODAY, NOW)
    near = store.create(session, {"kind": "race", "sport": "run", "distance_m": 10000, "date": TODAY + timedelta(weeks=6)}, TODAY, NOW)
    store.create(session, {"kind": "race", "sport": "ride", "distance_m": 100000, "date": TODAY + timedelta(weeks=2)}, TODAY, NOW)
    store.create(session, {"kind": "race", "sport": "run", "distance_m": 12000, "date": TODAY + timedelta(weeks=1)}, TODAY, NOW)  # not a standard distance
    assert store.primary_run_goal(session, TODAY)["id"] == near["id"] and b["id"] != far["id"]
    store.update(session, near["id"], {"status": "achieved"}, TODAY, NOW)
    assert store.primary_run_goal(session, TODAY)["id"] == far["id"]


def test_update_regenerates_the_title_and_keeps_custom_ones(session):
    g = store.create(session, {"kind": "performance", "sport": "run", "distance_m": 5000, "target_s": 1500}, TODAY, NOW)
    assert g["title"] == "5 km in 25:00"
    g2 = store.update(session, g["id"], {"target_s": 1440}, TODAY, NOW)
    assert g2["title"] == "5 km in 24:00" and g2["spec"]["target_s"] == 1440 and g2["spec"]["key"] == "5k"
    g3 = store.update(session, g["id"], {"title": "Parkrun PB"}, TODAY, NOW)
    assert g3["title"] == "Parkrun PB" and g3["spec"]["target_s"] == 1440
    assert store.update(session, 999, {"title": "x"}, TODAY, NOW) is None
    assert store.delete(session, g["id"]) and not store.delete(session, g["id"])


def test_migration_moves_the_old_single_goals_into_the_table(tmp_path):
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "0009")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO app_settings (key, value) VALUES ('training_goal', :v), ('weight_goal_kg', '77.5')"),
                     {"v": '{"distance": "half", "date": "2027-03-14", "target_s": 6300}'})
    command.upgrade(cfg, "head")
    with make_session_factory(engine)() as s:
        goals = store.listing(s)
        assert {g["kind"] for g in goals} == {"race", "weight"}
        race = next(g for g in goals if g["kind"] == "race")
        assert race["date"] == date(2027, 3, 14) and race["spec"]["key"] == "half" and race["spec"]["target_s"] == 6300
        assert store.weight_target(s) == 77.5
        assert s.execute(sa.text("SELECT count(*) FROM app_settings WHERE key IN ('training_goal','weight_goal_kg')")).scalar() == 0


# ---- API ------------------------------------------------------------------------------------------


def test_goals_api_round_trip(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    today = clock.today()
    assert client.post("/api/goals", json={"kind": "race", "sport": "run", "distance_m": 10000}, headers=MUTATE).status_code == 400
    assert client.post("/api/goals", json={"kind": "weight", "target_kg": 5}, headers=MUTATE).status_code == 422
    made = client.post("/api/goals", json={"kind": "race", "sport": "run", "distance_m": 21097.5, "date": str(today + timedelta(weeks=12)), "target_s": 6300}, headers=MUTATE)
    assert made.status_code == 201
    ride = client.post("/api/goals", json={"kind": "performance", "sport": "ride", "distance_m": 40000, "speed_kmh": 28, "date": str(today + timedelta(weeks=10))}, headers=MUTATE).json()
    swim = client.post("/api/goals", json={"kind": "distance", "sport": "swim", "distance_m": 1500}, headers=MUTATE).json()
    kg = client.post("/api/goals", json={"kind": "weight", "target_kg": 70}, headers=MUTATE).json()
    listing = client.get("/api/goals").json()
    by_id = {g["id"]: g for g in listing["goals"]}
    assert len(by_id) == 4 and listing["plan_goal_id"] == made.json()["id"] and listing["has_training"]
    assert all(g["headline"]["text"] for g in by_id.values())
    assert by_id[made.json()["id"]]["roadmap"] and by_id[kg["id"]]["kind"] == "weight"
    assert by_id[swim["id"]]["state"] in ("no_basis", "ok") and by_id[ride["id"]]["spec"]["target_s"] == 5143
    plan = client.get("/api/insights").json()["plan"]
    assert plan["goal"]["date"] == str(today + timedelta(weeks=12))
    assert client.patch(f"/api/goals/{made.json()['id']}", json={"status": "achieved"}, headers=MUTATE).json()["status"] == "achieved"
    assert client.get("/api/insights").json()["goal"] is None
    assert client.get("/api/goals").json()["goals"][-1]["state"] == "closed" or any(g["state"] == "closed" for g in client.get("/api/goals").json()["goals"])
    assert client.delete(f"/api/goals/{ride['id']}", headers=MUTATE).status_code == 200
    assert client.delete(f"/api/goals/{ride['id']}", headers=MUTATE).status_code == 404
    assert client.patch("/api/goals/999", json={"title": "x"}, headers=MUTATE).status_code == 404
    assert client.get("/api/weight").json()["goal_kg"] == 70


def test_goals_without_training_data_do_not_crash(env):  # noqa: F811
    client, clock = env
    client.post("/api/goals", json={"kind": "race", "sport": "run", "distance_m": 5000, "date": str(clock.today() + timedelta(weeks=8))}, headers=MUTATE)
    g = client.get("/api/goals").json()
    assert not g["has_training"] and g["goals"][0]["state"] == "no_data"


def test_a_ride_race_with_no_run_goal_drives_the_plan(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    made = client.post("/api/goals", json={"kind": "race", "sport": "ride", "distance_m": 100000, "date": str(clock.today() + timedelta(weeks=9))}, headers=MUTATE).json()
    plan = client.get("/api/insights").json()["plan"]
    assert plan["goal"]["sport"] == "ride" and plan["goal"]["label"] == "100 km" and plan["phase"]["weeks_to_race"] is not None
    assert client.get("/api/goals").json()["plan_goal_id"] == made["id"]
    assert client.put("/api/settings/goal", json={"distance": "10k", "date": str(clock.today() + timedelta(weeks=20))}, headers=MUTATE).status_code == 200
    assert client.get("/api/insights").json()["plan"]["goal"]["distance"] == "10k"  # a run race takes over
