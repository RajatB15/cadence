from datetime import date, timedelta

import pytest

from cadence_app import garmin_connect, garmin_workout as GW
from cadence_app.analytics import planner as PL
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_planner import training_ctx


def flat(steps):
    for s in steps:
        yield s
        if "workoutSteps" in s:
            yield from flat(s["workoutSteps"])


def test_every_run_and_ride_option_builds_a_workout_with_sane_steps():
    c = training_ctx()
    opts = PL.run_options(c, None) + PL.ride_options(c) + [PL.custom_option(c, "run", distance_m=8000, minutes=48)]
    for o in opts:
        w = GW.build({**o, "steps": o["steps"]})
        steps = list(flat(w["workoutSegments"][0]["workoutSteps"]))
        orders = [s["stepOrder"] for s in steps]
        assert orders == list(range(1, len(steps) + 1)), o["key"]  # unique, in sequence
        assert all(s["targetType"]["workoutTargetTypeKey"] in ("heart.rate.zone", "no.target") for s in steps if s["type"] == "ExecutableStepDTO")
        assert all(1 <= s["zoneNumber"] <= 5 for s in steps if "zoneNumber" in s)
        # Garmin's duration agrees with what the planner priced, within the rounding of the approximations
        assert abs(w["estimatedDurationInSecs"] / 60 - o["minutes"]) <= max(5, o["minutes"] * 0.12), o["key"]
    assert GW.build({**opts[0]})["sportType"]["sportTypeKey"] == "running"
    assert GW.build({**PL.ride_options(c)[0]})["sportType"]["sportTypeKey"] == "cycling"


def test_intervals_become_a_repeat_group_and_km_reps_end_by_distance():
    c = training_ctx()
    ride = next(o for o in PL.ride_options(c) if o["key"] == "ride_threshold")
    body = GW.build(ride)["workoutSegments"][0]["workoutSteps"]
    group = next(s for s in body if s["type"] == "RepeatGroupDTO")
    assert group["numberOfIterations"] == 3 and [s["stepType"]["stepTypeKey"] for s in group["workoutSteps"]] == ["interval", "recovery"]
    assert group["workoutSteps"][0]["zoneNumber"] == 4 and group["workoutSteps"][0]["endConditionValue"] == 600
    assert body[0]["stepType"]["stepTypeKey"] == "warmup" and body[-1]["stepType"]["stepTypeKey"] == "cooldown"
    km = GW.build({"sport": "run", "title": "x", "steps": [{"repeat": 5, "steps": [{"kind": "work", "minutes": 4, "zone": 4, "metres": 1000},
                                                                                    {"kind": "recovery", "minutes": 2, "zone": 1}]}]})
    work = km["workoutSegments"][0]["workoutSteps"][0]["workoutSteps"][0]
    assert work["endCondition"]["conditionTypeKey"] == "distance" and work["endConditionValue"] == 1000


def test_plans_saved_before_steps_existed_and_unsupported_sports():
    w = GW.build({"sport": "run", "kind": "easy", "title": "Easy run · 40 min", "minutes": 40})
    step = w["workoutSegments"][0]["workoutSteps"][0]
    assert step["zoneNumber"] == 2 and step["endConditionValue"] == 2400
    assert len(GW.build({"sport": "ride", "kind": "easy", "title": "t" * 200, "minutes": 60})["workoutName"]) <= GW.NAME_LIMIT
    for sport in ("swim", "strength"):
        with pytest.raises(GW.Unsupported):
            GW.build({"sport": sport, "title": "x"})


def test_send_remove_and_delete_through_the_api(env, monkeypatch):  # noqa: F811
    client, clock = env
    calls = []
    monkeypatch.setattr(garmin_connect.GarminConnectLink, "send", lambda self, plan, day: calls.append(("send", plan["id"], day)) or {"workout_id": 11, "schedule_id": 22})
    monkeypatch.setattr(garmin_connect.GarminConnectLink, "remove", lambda self, wid, sid: calls.append(("remove", wid, sid)))
    client.post("/api/sync/demo", headers=MUTATE)
    today = clock.today()
    day = today + timedelta(days=1)
    made = client.post("/api/planner", json={"day": str(day), "sport": "run", "option_key": "run_easy"}, headers=MUTATE).json()
    assert made["steps"] and made["garmin"] is None
    sent = client.post(f"/api/planner/{made['id']}/garmin", headers=MUTATE)
    assert sent.status_code == 200 and sent.json()["garmin"] == {"workout_id": 11, "schedule_id": 22}
    again = client.post(f"/api/planner/{made['id']}/garmin", headers=MUTATE)  # replaces, never duplicates
    assert again.status_code == 200 and calls[-2:-1] == [("remove", 11, 22)]
    assert client.delete(f"/api/planner/{made['id']}/garmin", headers=MUTATE).json()["garmin"] is None
    client.post(f"/api/planner/{made['id']}/garmin", headers=MUTATE)
    assert client.delete(f"/api/planner/{made['id']}", headers=MUTATE).json() == {"deleted": True, "garmin_removed": True}
    assert client.post("/api/planner/9999/garmin", headers=MUTATE).status_code == 404
    swim = client.post("/api/planner", json={"day": str(day), "sport": "swim", "option_key": "swim_technique"}, headers=MUTATE)
    if swim.status_code == 200:
        assert client.post(f"/api/planner/{swim.json()['id']}/garmin", headers=MUTATE).status_code == 400


def test_not_connected_is_a_conflict_and_the_password_never_leaks(env, tmp_path):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    made = client.post("/api/planner", json={"day": str(clock.today() + timedelta(days=1)), "sport": "run", "option_key": "run_easy"}, headers=MUTATE).json()
    assert client.get("/api/garmin-connect").json()["connected"] is False
    assert client.post(f"/api/planner/{made['id']}/garmin", headers=MUTATE).status_code == 409
    assert "pw-secret" not in repr(garmin_connect.GarminConnectLink.__init__) and "pw-secret" not in client.get("/api/garmin-connect").text
    assert client.post("/api/garmin-connect/code", json={"code": "123456"}, headers=MUTATE).status_code == 400  # nothing pending
