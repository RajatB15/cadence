import base64
import hashlib
import json
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from cadence_app.analytics import gym as G
from cadence_app.config import Settings
from cadence_app.connector import Connector, ConnectorAuth
from cadence_app.main import create_app
from tests.test_api import MUTATE, FixedClock

REDIRECT = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture
def env(tmp_path):
    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='x'\n")
    web = tmp_path / "dist"
    web.mkdir()
    (web / "index.html").write_text("<html><head></head></html>")
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets, web_dist=web), FixedClock(date(2026, 11, 10)))
    store: dict[str, str] = {}
    auth = ConnectorAuth(store.get, lambda k, v: store.pop(k, None) if v is None else store.__setitem__(k, v))
    auth.set_enabled(True)
    with TestClient(app, base_url="http://127.0.0.1") as mine:
        mine.post("/api/sync/demo", headers=MUTATE)
        c = TestClient(Connector(app, auth, lambda: "https://cadence.example.test", lambda: date(2026, 11, 10)), base_url="https://cadence.example.test", follow_redirects=False)
        cid = c.post("/oauth/register", json={"redirect_uris": [REDIRECT]}).json()["client_id"]
        verifier = "g" * 64
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        r = c.post("/oauth/authorize", data={"client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "code_challenge": challenge,
                                             "code_challenge_method": "S256", "approval": auth.approval_code()[0]})
        token = c.post("/oauth/token", data={"grant_type": "authorization_code", "code": re.search(r"code=([^&]+)", r.headers["location"]).group(1), "client_id": cid,
                                             "redirect_uri": REDIRECT, "code_verifier": verifier}).json()["access_token"]

        def call(name, args=None):
            res = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}, headers={"Authorization": f"Bearer {token}"}).json()["result"]
            text = res["content"][0]["text"]
            return res["isError"], (json.loads(text) if not res["isError"] and text.startswith(("{", "[")) else text)

        yield call, auth, mine


def test_reads_work_without_any_write_switch(env):
    call, _, _ = env
    err, lib = call("gym_exercises", {"q": "push up", "setting": "home"})
    assert not err and lib["exercises"][0]["id"] == "push-up" and lib["exercises"][0]["cues"]
    err, ex = call("gym_exercise", {"ex_id": "goblet-squat"})
    assert not err and ex["mistakes"] and ex["harder"]
    assert call("gym_exercise", {"ex_id": "../etc"})[0] and call("gym_exercise", {"ex_id": "nope-nope"})[0]
    err, t = call("gym_templates")
    assert not err and any(x["id"] == "hyrox" for x in t["templates"])
    assert not call("gym_sessions")[0] and not call("gym_settings")[0]
    err, msg = call("gym_build_session", {"template": "full_body"})
    assert err and "isn't switched on" in msg


def test_build_edit_swap_and_schedule_through_the_connector(env):
    call, auth, mine = env
    auth.set_writes(True, "plan")
    err, home = call("gym_set_home_equipment", {"home_equipment": ["kettlebell", "band"], "default_setting": "home"})
    assert not err and home["home_equipment"] == ["band", "kettlebell"]
    assert call("gym_set_home_equipment", {"home_equipment": ["jetpack"]})[0] and call("gym_set_home_equipment")[0]
    err, built = call("gym_build_session", {"template": "full_body", "setting": "home", "level": "beginner", "minutes": 40})
    assert not err and built["setting"] == "home" and built["exercises"] >= 5
    assert all(G.available(G.exercise(i), G.owned_set("home", ["band", "kettlebell"])) for i in G.exercise_ids(built["steps"]))
    gid = built["id"]
    assert call("gym_build_session", {"template": "nope"})[0] and call("gym_build_session", {"template": "hyrox", "seed": 0})[0]
    _, listing = call("gym_sessions")
    assert [s["id"] for s in listing["sessions"]] == [gid]
    err, steps_resp = call("gym_session", {"gid": gid})
    first_ex = next(i for i, s in enumerate(steps_resp["steps"][-1]["steps"]) if s["type"] == "exercise")
    path = [len(steps_resp["steps"]) - 1, first_ex]
    err, alts = call("gym_alternatives", {"gid": gid, "path": ".".join(map(str, path)), "direction": "different"})
    assert not err and alts["alternatives"] and call("gym_alternatives", {"gid": gid, "path": "x", "direction": "easier"})[0]
    err, swapped = call("gym_swap_exercise", {"gid": gid, "path": path, "exercise": alts["alternatives"][0]["id"]})
    assert not err and swapped["swapped"]["to"] == G.exercise(alts["alternatives"][0]["id"])["name"]
    err, easier = call("gym_swap_exercise", {"gid": gid, "path": path, "direction": "easier"})
    assert not err or "Nothing easier" in easier
    assert call("gym_swap_exercise", {"gid": gid, "path": path})[0] and call("gym_swap_exercise", {"gid": gid, "path": [], "direction": "easier"})[0]
    err, gym = call("gym_set_session_setting", {"gid": gid, "setting": "gym"})
    assert not err and gym["setting"] == "gym"
    err, saved = call("gym_save_session", {"name": "Run and lift", "format": "hybrid", "steps": [
        {"type": "group", "title": "Round", "rounds": 4, "steps": [{"exercise": "run", "distance_m": 800}, {"exercise": "goblet-squat", "reps": 15, "load": "16 kg"}]}]})
    assert not err and saved["format"] == "hybrid" and saved["steps"][0]["rounds"] == 4
    assert call("gym_save_session", {"name": "Bad", "steps": [{"exercise": "nope"}]})[0] and call("gym_save_session", {"name": "Bad", "steps": "x"})[0]
    err, renamed = call("gym_update_session", {"gid": saved["id"], "name": "Hybrid day"})
    assert not err and renamed["name"] == "Hybrid day" and call("gym_update_session", {"gid": saved["id"]})[0]
    err, planned = call("gym_schedule_session", {"gid": saved["id"], "day": "2026-11-12", "start_hour": 6})
    assert not err and planned["sport"] == "strength" and planned["day"] == "2026-11-12"
    assert "2026-11-12" in json.dumps(mine.get("/api/planner").json())
    assert call("gym_schedule_session", {"gid": saved["id"], "day": "soon"})[0] and call("gym_schedule_session", {"gid": 9999, "day": "2026-11-12"})[0]
    assert not call("gym_delete_session", {"gid": saved["id"]})[0] and call("gym_delete_session", {"gid": saved["id"]})[0]
    assert [a["tool"] for a in auth.recent()][0] == "gym_delete_session"


def test_hyrox_at_home_through_the_connector_lists_what_was_swapped(env):
    call, auth, _ = env
    auth.set_writes(True, "plan")
    err, s = call("gym_build_session", {"template": "hyrox", "setting": "home"})
    assert not err and len(s["steps"]) == 8 and s["generator_notes"] and any("→" in n for n in s["generator_notes"])
    err, gym = call("gym_build_session", {"template": "hyrox", "setting": "gym", "name": "Race rehearsal"})
    assert not err and gym["name"] == "Race rehearsal" and [g["steps"][1]["exercise"] for g in gym["steps"]][0] == "skierg"


def test_plan_detail_workouts_and_loads_through_the_connector(env):
    call, auth, mine = env
    auth.set_writes(True, "plan")
    auth.set_writes(True, "log")
    _, built = call("gym_build_session", {"template": "lower", "setting": "gym"})
    err, planned = call("gym_schedule_session", {"gid": built["id"], "day": "2026-11-12"})
    assert not err
    err, detail = call("gym_plan_detail", {"plan_id": planned["id"]})
    assert not err and detail["steps"] == built["steps"] and detail["workout"] is None
    entries = [{"exercise": "goblet-squat", "sets": [{"reps": 8, "target_reps": 8, "load": "20 kg"}] * 3}]
    err, logged = call("gym_log_workout", {"name": "Lower", "entries": entries, "plan_id": planned["id"], "duration_s": 2400})
    assert not err and logged["sets_done"] == 3 and logged["day"] == "2026-11-10"
    assert call("gym_log_workout", {"name": "Bad", "entries": [{"exercise": "nope", "sets": [{"reps": 1}]}]})[0]
    assert call("gym_log_workout", {"name": "Bad", "entries": "x"})[0] and call("gym_log_workout", {"name": "Bad"})[0]
    err, hist = call("gym_workouts", {"limit": 5})
    assert not err and hist["workouts"][0]["id"] == logged["id"]
    err, loads = call("gym_last_loads", {"ids": "goblet-squat,plank"})
    assert not err and loads["loads"]["goblet-squat"]["hint"]["load"] == "21 kg"
    assert call("gym_last_loads", {"ids": "../x"})[0]
    assert call("gym_plan_detail", {"plan_id": 99999})[0]
    assert call("gym_plan_detail", {"plan_id": planned["id"]})[1]["workout"]["id"] == logged["id"]
    auth.set_writes(False, "log")
    assert call("gym_log_workout", {"name": "Nope", "entries": entries})[0]
