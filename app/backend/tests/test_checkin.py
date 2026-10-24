from datetime import timedelta

import pytest

from cadence_app.analytics import plan as training_plan
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_planner import training_ctx


def test_a_check_in_round_trips_and_validates(env):  # noqa: F811
    client, clock = env
    today = str(clock.today())
    assert client.get("/api/wellbeing").json()["entry"] is None
    r = client.put(f"/api/wellbeing/{today}", json={"feel": 4, "soreness": 1, "pain_level": 2, "pain_area": "  left knee ", "life_stress": 2}, headers=MUTATE)
    assert r.status_code == 200 and r.json()["pain_area"] == "left knee" and r.json()["feel"] == 4
    again = client.put(f"/api/wellbeing/{today}", json={"illness": 1}, headers=MUTATE).json()
    assert again["illness"] == 1 and again["feel"] == 4 and again["pain_area"] == "left knee"  # fields you leave out stay
    cleared = client.put(f"/api/wellbeing/{today}", json={"pain_level": 0}, headers=MUTATE).json()
    assert cleared["pain_area"] is None  # an area without pain is dropped
    assert client.put(f"/api/wellbeing/{today}", json={"feel": 9}, headers=MUTATE).status_code == 422
    assert client.put(f"/api/wellbeing/{clock.today() + timedelta(days=1)}", json={"feel": 3}, headers=MUTATE).status_code == 400
    assert client.put(f"/api/wellbeing/{clock.today() - timedelta(days=40)}", json={"feel": 3}, headers=MUTATE).status_code == 400
    assert client.get("/api/wellbeing").json()["entry"]["illness"] == 1
    assert client.delete(f"/api/wellbeing/{today}", headers=MUTATE).status_code == 200
    assert client.delete(f"/api/wellbeing/{today}", headers=MUTATE).status_code == 404


def test_saying_you_are_ill_overrules_the_watch_on_home(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    before = client.get("/api/overview").json()["coach"]
    assert before["wellbeing"]["needed"] is True and before["wellbeing"]["today"] is None
    client.put(f"/api/wellbeing/{clock.today()}", json={"illness": 2, "feel": 1}, headers=MUTATE)
    after = client.get("/api/overview").json()["coach"]
    assert after["call"]["headline"] == "Rest" and after["call"]["source"] == "check-in" and "clinician" in after["call"]["detail"]
    assert after["wellbeing"]["level"] == "rest" and after["wellbeing"]["needed"] is False


def test_a_good_check_in_never_adds_training(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    base = client.get("/api/overview").json()["coach"]
    client.put(f"/api/wellbeing/{clock.today()}", json={"feel": 5, "soreness": 0, "pain_level": 0, "illness": 0, "life_stress": 1}, headers=MUTATE)
    good = client.get("/api/overview").json()["coach"]
    assert good["call"] == base["call"] and good["today"]["kind"] == base["today"]["kind"] and good["wellbeing"]["level"] is None


def test_pain_yesterday_holds_the_week_back_and_heavy_stress_trims_it(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    before = client.get("/api/insights").json()["plan"]
    client.put(f"/api/wellbeing/{clock.today() - timedelta(days=1)}", json={"pain_level": 2, "pain_area": "calf"}, headers=MUTATE)
    held = client.get("/api/insights").json()["plan"]
    assert held["phase"]["phase"] == "absorb" and "pain you reported" in held["phase"]["blurb"] and held["targets"]["load"][1] < before["targets"]["load"][1]


def test_training_mode_is_saved_and_reported(env):  # noqa: F811
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    assert client.get("/api/insights").json()["training_mode"] == "auto"
    assert client.put("/api/settings/training-mode", json={"mode": "maintain"}, headers=MUTATE).json() == {"mode": "maintain"}
    body = client.get("/api/insights").json()
    assert body["training_mode"] == "maintain" and body["plan"]["phase"]["phase"] == "maintain"
    assert client.put("/api/settings/training-mode", json={"mode": "nope"}, headers=MUTATE).status_code == 422
    client.put("/api/settings/training-mode", json={"mode": "auto"}, headers=MUTATE)
    assert client.get("/api/insights").json()["training_mode"] == "auto"


def long_flat(**kw):
    return training_ctx(days=224, **kw)


def test_a_long_flat_stretch_with_no_goal_switches_to_maintain_by_itself():
    c = long_flat()
    ws = c["as_of"] - timedelta(days=c["as_of"].weekday())
    flat = training_plan.plateau(c, ws)
    assert flat and abs(flat["change_pct"]) <= 5
    ph = training_plan.phase(c, ws)
    assert ph["phase"] == "maintain" and "flat" in ph["blurb"]
    plan = training_plan.weekly_plan(c)
    assert plan["phase"]["phase"] == "maintain" and "no ramp" in " ".join(i["why"] for i in plan["items"] if i["label"] == "Weekly load")
    lo, hi = plan["targets"]["load"]
    assert abs((lo + hi) / 2 - 7 * c["pmc_by_day"][ws - timedelta(days=1)]["fitness"]) / (7 * c["pmc_by_day"][ws - timedelta(days=1)]["fitness"]) < 0.12


def test_a_goal_or_build_mode_stops_maintain():
    ws = lambda c: c["as_of"] - timedelta(days=c["as_of"].weekday())  # noqa: E731
    c = long_flat()
    c["goal"] = {"distance": "half", "date": c["as_of"] + timedelta(weeks=12), "target_s": None}
    assert training_plan.phase(c, ws(c))["phase"] != "maintain"
    c2 = long_flat()
    c2["training_mode"] = "build"
    assert training_plan.phase(c2, ws(c2))["phase"] in ("build", "base", "recovery")
    c3 = training_ctx(days=84)
    assert training_plan.plateau(c3, ws(c3)) is None  # still ramping up from nothing


def test_maintain_mode_can_be_chosen_before_there_is_a_plateau():
    c = training_ctx(days=84)
    c["training_mode"] = "maintain"
    assert training_plan.phase(c, c["as_of"] - timedelta(days=c["as_of"].weekday()))["phase"] == "maintain"


def test_heavy_stress_trims_the_week_by_a_tenth():
    c = long_flat()
    base = training_plan.weekly_plan(c)["targets"]["load"]
    c2 = long_flat()
    c2["wellbeing"] = {c2["as_of"] - timedelta(days=i): {"life_stress": 3} for i in range(5)}
    trimmed = training_plan.weekly_plan(c2)
    assert trimmed["targets"]["load"][1] == pytest.approx(base[1] * 0.9, abs=2) and "heavy life stress" in " ".join(i["why"] for i in trimmed["items"])


def test_the_suggested_session_follows_the_check_in():
    from cadence_app.analytics import notes

    c = training_ctx()
    c["today"] = c["as_of"]
    assert notes.wellbeing_suggestion(c) is None
    c["wellbeing"] = {c["as_of"]: {"pain_level": 3, "pain_area": "left knee"}}
    s = notes._suggest(c, {"score": 90, "components": {}}, {"hard_done": 0, "sessions_done": 0, "items": [], "days_left": 3}, None)
    assert s["kind"] == "rest" and "left knee" in s["detail"] and s["source"] == "check-in"
    c["wellbeing"] = {c["as_of"]: {"feel": 2}}
    e = notes._suggest(c, {"score": 90, "components": {}}, {"hard_done": 0, "sessions_done": 0, "items": [], "days_left": 3}, None)
    assert e["kind"] == "easy" and "The watch says you've recovered" in e["detail"] or "keep it easy" in e["detail"].lower()
    c["wellbeing"] = {c["as_of"]: {"pain_level": 1, "life_stress": 3}}  # watch-level only: a note, not an override
    assert notes.wellbeing_suggestion(c) is None and notes.wellbeing_call(c, None) is None


def test_wellbeing_findings_and_recovery_wins_reach_the_brief():
    from cadence_app.analytics import notes

    c = training_ctx()
    c["today"] = c["as_of"]
    c["wellbeing"] = {c["as_of"] - timedelta(days=i): {"pain_level": 2, "pain_area": "calf"} for i in (1, 5, 9)}
    block = notes.wellbeing_block(c, None)
    assert block["needed"] is True and any(n["id"] == "pain_recurring" for n in block["notes"])
    wins = notes.recovery_wins_card(c)
    assert wins is None or wins["items"]


def test_coach_page_and_home_agree_about_a_check_in(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    client.put(f"/api/wellbeing/{clock.today()}", json={"pain_level": 3, "pain_area": "left knee"}, headers=MUTATE)
    home = client.get("/api/overview").json()["coach"]["call"]
    coach = client.get("/api/insights").json()["recommendation"]
    assert home["headline"] == coach["headline"] == "Rest" and "left knee" in coach["detail"]


def sport_goal(sport="ride", days=84, metres=100000.0, taper=2):
    return {"id": 1, "sport": sport, "date": None, "distance_m": metres, "label": "100 km", "target_s": None, "kind": "race", "taper_weeks": taper}


def test_a_ride_goal_sets_the_phase_and_a_long_ride_target():
    c = training_ctx(days=84)
    rides = [a for a in c["acts"][-12:]]
    from tests.test_notes import act

    c["acts"] = list(c["acts"]) + [act(900 + i, c["as_of"] - timedelta(days=4 * i + 1), family="ride", distance_m=50000 + 2000 * (5 - i), moving_s=7200, load=90.0) for i in range(5)]
    g = sport_goal()
    g["date"] = c["as_of"] + timedelta(weeks=9)
    c["sport_goal"] = g
    ws = c["as_of"] - timedelta(days=c["as_of"].weekday())
    ph = training_plan.phase(c, ws)
    assert ph["weeks_to_race"] is not None and ph["phase"] in ("specific", "build", "recovery", "base", "taper")
    plan = training_plan.weekly_plan(c)
    item = next(i for i in plan["items"] if i["label"] == "Long ride")
    assert "km easy" in item["value"] and "100 km" in item["why"] and plan["targets"]["long_sport"]["sport"] == "ride"
    assert plan["goal"]["label"] == "100 km" and plan["goal"]["sport"] == "ride" and plan["goal"]["distance"] is None
    g["date"] = c["as_of"] + timedelta(weeks=1)
    c.pop("_phase", None)
    taper = training_plan.weekly_plan(c)
    assert taper["phase"]["phase"] in ("taper", "race") and rides is not None


def test_a_run_race_keeps_precedence_over_a_goal_in_another_sport():
    c = training_ctx(days=84)
    c["goal"] = {"distance": "half", "date": c["as_of"] + timedelta(weeks=12), "target_s": None}
    g = sport_goal()
    g["date"] = c["as_of"] + timedelta(weeks=4)
    c["sport_goal"] = g
    assert training_plan.active_goal(c) is c["goal"]
    assert training_plan.weekly_plan(c)["goal"]["distance"] == "half"
    assert not any(i["label"] == "Long ride" for i in training_plan.weekly_plan(c)["items"])
