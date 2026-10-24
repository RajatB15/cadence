from datetime import timedelta

import pytest

from cadence_app.analytics import athlete as A
from cadence_app.analytics import planner as PL
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_notes import D0, EASY, HARD, act, ctx

THRESH = (300, 900, 300, 1800, 0)


def training_ctx(days: int = 84, **kw):
    """Four sessions a week: easy, hard, easy, long; Garmin load = 1·Z1 + 1·Z2 + 2·Z3 + 3·Z4 + 4·Z5 per minute."""
    acts, i = [], 0
    for w in range(days // 7):
        for dd, z, minutes in ((0, EASY, 60), (2, HARD, 60), (4, EASY, 45), (6, EASY, 90)):
            i += 1
            zones = tuple(x * minutes / 60 for x in z)
            load = sum(wt * s / 60 for wt, s in zip((1, 1, 2, 3, 4), zones))
            acts.append(act(i, D0 + timedelta(days=7 * w + dd), zones, load=load, moving_s=minutes * 60, distance_m=minutes * 170))
    ds = [D0 + timedelta(days=k) for k in range(days)]
    series = {"hrv": {d: 58.0 + (k % 4) for k, d in enumerate(ds)}, "resting_hr": {d: 50.0 + (k % 2) for k, d in enumerate(ds)},
              "sleep_hours": {d: 8.0 for d in ds}, "sleep_score": {d: 84.0 for d in ds}, "body_battery": {d: 85.0 for d in ds}}
    return ctx(acts, series, days=days, **kw)


def test_load_model_recovers_zone_weights():
    c = training_ctx()
    m = PL.load_model(c["acts"], c["as_of"])
    assert m["r2"] > 0.95 and m["counts"]["run"] == 48
    assert PL.predict_load(m, "run", [0, 60, 0, 0, 0]) == pytest.approx(60, rel=0.05)
    assert PL.predict_load(m, "run", [10, 10, 0, 30, 0]) == pytest.approx(110, rel=0.1)


def test_run_options_cover_the_week_and_parse_into_minutes():
    c = training_ctx()
    opts = PL.run_options(c, None)
    kinds = [o["kind"] for o in opts]
    assert {"recovery", "easy", "long", "threshold", "vo2", "hills"} <= set(kinds)
    thr = next(o for o in opts if o["kind"] == "threshold")
    assert sum(thr["profile"]) == pytest.approx(thr["minutes"], abs=1) and thr["profile"][3] >= 20
    assert all(o["detail"] for o in PL.ride_options(c) + PL.swim_options())


def test_predictions_move_fitness_and_recovery_the_right_way():
    c = training_ctx()
    m = PL.load_model(c["acts"], c["as_of"])
    day = c["as_of"] + timedelta(days=1)
    opts = {o["kind"]: o for o in PL.run_options(c, None)}
    hard = PL.predict(c, m, day, opts["vo2"], [])
    easy = PL.predict(c, m, day, opts["easy"], [])
    rest = PL.predict(c, m, day, opts["recovery"], [])
    assert hard["load"] > easy["load"] > rest["load"]
    assert hard["fitness"][1] > hard["fitness"][0] and hard["form_tomorrow"] < easy["form_tomorrow"]
    assert hard["readiness_load"][1] <= easy["readiness_load"][1]
    assert hard["similar_n"] >= 3 and hard["builds"] and hard["confidence"] == "personal"


def test_ranking_respects_spacing_and_readiness():
    c = training_ctx()
    day = c["as_of"] + timedelta(days=1)
    planned_hard = [{"id": 1, "day": day + timedelta(days=1), "sport": "run", "kind": "threshold", "predicted_load": 90, "heavy_lower": False}]
    ranked = PL.rank(c, day, PL.run_options(c, None), planned_hard, None)
    vo2 = next(o for o in ranked if o["kind"] == "vo2")
    assert vo2["caution"] and not vo2["recommended"] and ranked[0]["recommended"]
    tired = PL.rank(c, c["as_of"], PL.run_options(c, None), [], {"score": 40})
    assert tired[0]["kind"] == "recovery" and next(o for o in tired if o["kind"] == "threshold")["caution"]


def test_projection_follows_the_plan():
    p = PL.projection(training_ctx())
    assert p and p["fitness_4w"] > 0 and p["weekly_load"] > 0


def test_plan_a_week_and_match_it(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    today = clock.today()
    opts = client.get(f"/api/planner/options?day={today}&sport=run").json()["options"]
    assert opts and sum(o["recommended"] for o in opts) <= 1 and all("predicted" in o for o in opts)
    pick = opts[0]
    made = client.post("/api/planner", json={"day": str(today), "sport": "run", "option_key": pick["key"]}, headers=MUTATE)
    assert made.status_code == 200 and made.json()["predicted"]["load"] == pick["predicted"]["load"]
    text = "Get Stronger\nBarbell Front Squats\nGlute Bridges\nCore\nBeast Hold drag"
    tomorrow = today + timedelta(days=1)
    s = client.get("/api/planner/options", params={"day": str(tomorrow), "sport": "strength", "strength_text": text}).json()["options"][0]
    assert s["heavy_lower"] and s["predicted"]["load"] > 0
    assert client.post("/api/planner", json={"day": str(tomorrow), "sport": "strength", "option_key": s["key"], "strength_text": text}, headers=MUTATE).status_code == 200
    assert client.post("/api/planner", json={"day": str(today - timedelta(days=1)), "sport": "run", "option_key": "run_easy"}, headers=MUTATE).status_code == 400
    assert client.post("/api/planner", json={"day": str(today), "sport": "run", "option_key": "nope"}, headers=MUTATE).status_code == 400
    week = client.get("/api/planner").json()
    planned = [p for d in week["days"] for p in d["plans"]]
    assert {p["sport"] for p in planned} == {"run", "strength"} and week["projection"]["fitness_4w"] > 0
    today_plan = next(p for p in planned if p["sport"] == "run")
    assert today_plan["status"] in ("done", "planned")
    assert client.delete(f"/api/planner/{today_plan['id']}", headers=MUTATE).json() == {"deleted": True}
    assert A.Act  # athlete import used for type context


def test_a_second_hard_session_on_the_same_day_is_cautioned():
    c = training_ctx()
    day = c["as_of"] + timedelta(days=1)
    planned = [{"id": 1, "day": day, "sport": "run", "kind": "threshold", "predicted_load": 90, "heavy_lower": False}]
    swim = next(o for o in PL.rank(c, day, PL.swim_options(), planned, None) if o["kind"] == "threshold")
    assert "already a hard session" in swim["caution"] and not swim["recommended"]
    long_run = next(o for o in PL.rank(c, day, PL.run_options(c, None), planned, None) if o["kind"] == "long")
    assert long_run["caution"] and not long_run["recommended"]
    m = PL.load_model(c["acts"], c["as_of"])
    assert "critical speed" not in PL.predict(c, m, day, swim, [])["builds"]


def test_custom_session_derives_the_third_value_and_sets_effort():
    c = training_ctx()
    o = PL.custom_option(c, "run", distance_m=10_000, speed_mps=3.0)  # 55:33
    assert o["minutes"] == 56 and o["kind"] == "easy" and o["key"] == "custom"
    assert sum(o["profile"]) == pytest.approx(56)
    ride = PL.custom_option(c, "ride", minutes=180, speed_mps=7.0, effort="hard")
    assert ride["kind"] == "threshold" and "75.6 km" in ride["detail"]
    assert PL.custom_option(c, "swim", distance_m=1500, minutes=30)["detail"].startswith("1500 m at 2:00/100 m")
    assert PL.custom_option(c, "ride", minutes=160, speed_mps=7.0)["kind"] == "long"
    for bad in ({"distance_m": 5000}, {"distance_m": 5000, "minutes": 5}, {"distance_m": 5000, "speed_mps": 12.0}):
        with pytest.raises(ValueError):
            PL.custom_option(c, "run", **bad)


def test_custom_session_and_start_hour_through_the_api(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    today = clock.today()
    q = {"day": str(today), "sport": "run", "custom": "true", "distance_m": 8000, "speed_mps": 3.2, "start_hour": 6}
    got = client.get("/api/planner/options", params=q).json()
    assert got["start_hour"] == 6 and [o["key"] for o in got["options"]] == ["custom"] and not got["options"][0]["recommended"]
    assert client.get("/api/planner/options", params={**q, "sport": "strength"}).status_code == 400
    assert client.get("/api/planner/options", params={**q, "speed_mps": 12}).status_code == 400
    body = {"day": str(today), "sport": "run", "option_key": "custom", "start_hour": 6, "custom": {"distance_m": 8000, "speed_mps": 3.2}}
    made = client.post("/api/planner", json=body, headers=MUTATE)
    assert made.status_code == 200 and made.json()["start_hour"] == 6 and made.json()["minutes"] == 42
    suggested = client.get("/api/planner/options", params={"day": str(today), "sport": "ride", "start_hour": 18}).json()["options"]
    assert suggested and all(o["start_hour"] == 18 for o in suggested)
