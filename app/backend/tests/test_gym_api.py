from datetime import date

import pytest
from fastapi.testclient import TestClient

from cadence_app.analytics import gym as G
from cadence_app.config import Settings
from cadence_app.main import create_app
from tests.test_api import MUTATE, FixedClock

TODAY = date(2026, 11, 10)


@pytest.fixture
def client(tmp_path):
    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='x'\n")
    web = tmp_path / "dist"
    web.mkdir()
    (web / "index.html").write_text("<html><head></head></html>")
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets, web_dist=web), FixedClock(TODAY))
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.post("/api/sync/demo", headers=MUTATE)
        yield c


def test_library_guides_and_templates(client):
    lib = client.get("/api/gym/library", params={"q": "goblet"}).json()
    assert lib["exercises"][0]["id"] == "goblet-squat" and lib["total"] >= 120 and "squat" in lib["patterns"]
    home = client.get("/api/gym/library", params={"pattern": "push", "setting": "home", "limit": 200}).json()["exercises"]
    assert home and all(e["available"] for e in home) and "barbell-bench-press" not in {e["id"] for e in home}
    ex = client.get("/api/gym/exercises/push-up").json()
    assert ex["cues"] and ex["mistakes"] and ex["easier"] and ex["harder"] and ex["needs"] == "no equipment"
    assert client.get("/api/gym/exercises/nope").status_code == 404
    t = client.get("/api/gym/templates").json()
    assert {x["id"] for x in t["templates"]} >= {"full_body", "hyrox", "hyrox_practice", "run_lift"} and "advanced" in t["levels"]


def test_home_equipment_setting_round_trips_and_changes_what_is_offered(client):
    assert client.get("/api/settings/gym").json()["home_equipment"] == []
    assert client.put("/api/settings/gym", json={"home_equipment": ["kettlebell", "band"]}).status_code == 403  # needs the header
    s = client.put("/api/settings/gym", json={"home_equipment": ["kettlebell", "band", "kettlebell"]}, headers=MUTATE).json()
    assert s["home_equipment"] == ["band", "kettlebell"] and s["default_setting"] == "gym"
    assert client.put("/api/settings/gym", json={"home_equipment": ["trampoline"]}, headers=MUTATE).status_code == 400
    ids = {e["id"] for e in client.get("/api/gym/library", params={"setting": "home", "limit": 200}).json()["exercises"]}
    assert "goblet-squat" in ids and "kettlebell-swing" in ids and "back-squat" not in ids
    gen = client.post("/api/gym/generate", json={"template": "full_body", "setting": "home"}, headers=MUTATE).json()
    assert all(G.available(G.exercise(i), G.owned_set("home", ["band", "kettlebell"])) for i in G.exercise_ids(gen["steps"]))


def test_generate_save_edit_and_delete_a_session(client):
    gen = client.post("/api/gym/generate", json={"template": "full_body", "setting": "gym", "minutes": 50, "goal": "strength", "seed": 5}, headers=MUTATE).json()
    assert gen["steps"] and gen["minutes"] >= 20 and gen["outline"]
    saved = client.post("/api/gym/sessions", json={"name": gen["name"], "setting": "gym", "format": gen["format"], "steps": gen["steps"]}, headers=MUTATE)
    assert saved.status_code == 201
    sid = saved.json()["id"]
    assert saved.json()["exercises"] >= 6 and saved.json()["patterns"]
    assert [s["id"] for s in client.get("/api/gym/sessions").json()["sessions"]] == [sid]
    renamed = client.put(f"/api/gym/sessions/{sid}", json={"name": "Monday lift", "notes": "felt good"}, headers=MUTATE).json()
    assert renamed["name"] == "Monday lift" and renamed["notes"] == "felt good" and renamed["steps"] == saved.json()["steps"]
    assert client.put(f"/api/gym/sessions/{sid}", json={"steps": [{"exercise": "nope"}]}, headers=MUTATE).status_code == 400
    assert client.put("/api/gym/sessions/999", json={"name": "x"}, headers=MUTATE).status_code == 404
    built = client.post("/api/gym/sessions/build", json={"template": "hyrox", "setting": "gym"}, headers=MUTATE)
    assert built.status_code == 201 and len(built.json()["steps"]) == 8 and built.json()["format"] == "hyrox"
    assert client.post("/api/gym/generate", json={"template": "nope"}, headers=MUTATE).status_code == 400
    assert client.delete(f"/api/gym/sessions/{sid}", headers=MUTATE).json() == {"deleted": sid}
    assert client.get(f"/api/gym/sessions/{sid}").status_code == 404 and client.delete(f"/api/gym/sessions/{sid}", headers=MUTATE).status_code == 404


def test_custom_run_and_exercise_mix_is_stored_as_written(client):
    steps = [{"type": "group", "title": "Round", "rounds": 4, "rest_s": 60, "steps": [
        {"exercise": "run", "distance_m": 1000, "note": "easy"}, {"exercise": "wall-ball", "reps": 25, "load": "6 kg"}, {"exercise": "run", "distance_m": 400}, {"exercise": "burpee", "reps": 10}]},
        {"type": "rest", "seconds": 120}, {"exercise": "plank", "sets": 2, "seconds": 45}, {"name": "Odd machine", "sets": 3, "reps": 12}]
    r = client.post("/api/gym/sessions", json={"name": "Run and lift", "format": "hybrid", "steps": steps}, headers=MUTATE)
    assert r.status_code == 201
    got = client.get(f"/api/gym/sessions/{r.json()['id']}").json()
    assert got["steps"][0]["rounds"] == 4 and got["steps"][0]["steps"][1]["load"] == "6 kg" and got["steps"][3]["name"] == "Odd machine"
    assert got["outline"].splitlines()[0] == "Round x4" and got["minutes"] > 20


def test_swaps_alternatives_and_switching_to_home(client):
    steps = [{"type": "group", "title": "Main", "steps": [{"exercise": "back-squat", "sets": 4, "reps": 5, "load": "80 kg"}, {"exercise": "barbell-bench-press", "sets": 3, "reps": 8}]}]
    sid = client.post("/api/gym/sessions", json={"name": "Lift", "steps": steps}, headers=MUTATE).json()["id"]
    alt = client.post("/api/gym/alternatives", json={"exercise": "back-squat", "direction": "harder"}, headers=MUTATE).json()["alternatives"]
    assert alt[0]["id"] == "front-squat" and alt[0]["reason"]
    same = client.get(f"/api/gym/sessions/{sid}/alternatives", params={"path": "0.0", "direction": "easier"}).json()["alternatives"]
    assert same and all(G.exercise(a["id"])["level"] < 3 for a in same)
    hit = client.post(f"/api/gym/sessions/{sid}/swap", json={"path": [0, 0], "direction": "harder"}, headers=MUTATE).json()
    assert hit["swapped"] == {"from": "Back Squat", "to": "Front Squat"} and hit["steps"][0]["steps"][0]["load"] == "80 kg"
    by_id = client.post(f"/api/gym/sessions/{sid}/swap", json={"path": [0, 1], "exercise": "dumbbell-bench-press"}, headers=MUTATE).json()
    assert by_id["steps"][0]["steps"][1]["exercise"] == "dumbbell-bench-press"
    assert client.post(f"/api/gym/sessions/{sid}/swap", json={"path": [0, 1]}, headers=MUTATE).status_code == 400
    assert client.post(f"/api/gym/sessions/{sid}/swap", json={"path": [0, 1], "exercise": "x", "direction": "easier"}, headers=MUTATE).status_code == 400
    assert client.post(f"/api/gym/sessions/{sid}/swap", json={"path": [5, 0], "direction": "easier"}, headers=MUTATE).status_code == 400
    home = client.post(f"/api/gym/sessions/{sid}/setting", json={"setting": "home"}, headers=MUTATE).json()
    assert home["setting"] == "home" and home["changes"] and all(G.available(G.exercise(i), G.owned_set("home", [])) for i in G.exercise_ids(home["steps"]))
    refused = client.post(f"/api/gym/sessions/{sid}/swap", json={"path": [0, 0], "exercise": "back-squat"}, headers=MUTATE)
    assert refused.status_code == 400 and "equipment" in refused.json()["detail"]  # a home session can't take gym kit
    stateless = client.post("/api/gym/swap", json={"steps": steps, "path": [0, 0], "exercise": "goblet-squat", "setting": "gym"}, headers=MUTATE).json()
    assert stateless["steps"][0]["steps"][0]["exercise"] == "goblet-squat" and steps[0]["steps"][0]["exercise"] == "back-squat"
    conv = client.post("/api/gym/convert", json={"steps": steps, "setting": "home"}, headers=MUTATE).json()
    assert conv["changes"]


def test_planning_a_gym_session_makes_an_ordinary_strength_plan(client):
    gen = client.post("/api/gym/sessions/build", json={"template": "lower", "setting": "gym"}, headers=MUTATE).json()
    planned = client.post(f"/api/gym/sessions/{gen['id']}/plan", json={"day": "2026-11-12", "start_hour": 6}, headers=MUTATE)
    assert planned.status_code == 201
    p = planned.json()
    assert p["sport"] == "strength" and p["kind"] == "gym" and p["day"] == "2026-11-12" and p["start_hour"] == 6 and p["minutes"] > 10
    assert p["blocks"] and any(e["pattern"] == "squat" for b in p["blocks"] for e in b["exercises"])
    week = client.get("/api/planner").json()
    assert any(pl["id"] == p["id"] for d in week["days"] for pl in d["plans"])
    client.put(f"/api/gym/sessions/{gen['id']}", json={"name": "Changed later"}, headers=MUTATE)
    assert any(pl["title"] == gen["name"] for d in client.get("/api/planner").json()["days"] for pl in d["plans"])  # a snapshot, not a live link
    assert client.post(f"/api/gym/sessions/{gen['id']}/plan", json={"day": "2020-01-01"}, headers=MUTATE).status_code in (400, 422)
    assert client.post("/api/gym/sessions/999/plan", json={"day": "2026-11-12"}, headers=MUTATE).status_code == 404
    assert client.delete(f"/api/planner/{p['id']}", headers=MUTATE).status_code == 200


def test_preview_fills_defaults_and_times_unsaved_steps(client):
    r = client.post("/api/gym/preview", json={"steps": [{"exercise": "plank"}, {"type": "group", "rounds": 3, "steps": [{"exercise": "burpee", "reps": 10}]}]}, headers=MUTATE).json()
    assert r["steps"][0]["seconds"] == 30 and r["minutes"] >= 2 and r["outline"].splitlines()[1] == "Round x3" and r["patterns"] == ["core", "plyometric"]
    assert client.post("/api/gym/preview", json={"steps": [{"exercise": "nope"}]}, headers=MUTATE).status_code == 400


def _planned(client, template="full_body"):
    built = client.post("/api/gym/sessions/build", json={"template": template, "setting": "gym"}, headers=MUTATE).json()
    plan = client.post(f"/api/gym/sessions/{built['id']}/plan", json={"day": "2026-11-11", "start_hour": 6}, headers=MUTATE).json()
    return built, plan


def test_plan_detail_gives_the_steps_as_planned_and_survives_edits_and_deletes(client):
    built, plan = _planned(client)
    d = client.get(f"/api/gym/plans/{plan['id']}").json()
    assert d["steps"] == built["steps"] and d["source"] == "plan" and d["setting"] == "gym" and d["workout"] is None and d["day"] == "2026-11-11"
    client.put(f"/api/gym/sessions/{built['id']}", json={"steps": [{"exercise": "plank"}]}, headers=MUTATE)
    assert client.get(f"/api/gym/plans/{plan['id']}").json()["steps"] == built["steps"]  # a snapshot
    client.delete(f"/api/gym/sessions/{built['id']}", headers=MUTATE)
    assert client.get(f"/api/gym/plans/{plan['id']}").json()["steps"] == built["steps"]
    assert client.get("/api/gym/plans/9999").status_code == 404
    week = client.get("/api/planner").json()
    got = next(p for d in week["days"] for p in d["plans"] if p["id"] == plan["id"])
    assert got["gym"] is True and got["logged"] is False


def test_workouts_are_logged_listed_deleted_and_feed_last_loads(client):
    built, plan = _planned(client)
    entries = [{"exercise": "goblet-squat", "sets": [{"reps": 10, "target_reps": 10, "load": "24 kg"}] * 3},
               {"exercise": "plank", "sets": [{"seconds": 45, "done": True}]}, {"name": "Odd machine", "sets": [{"reps": 12, "load": "30 kg", "done": False}]}]
    r = client.post("/api/gym/workouts", json={"name": "Lower day", "plan_id": plan["id"], "session_id": built["id"], "duration_s": 3100, "entries": entries, "notes": "good"}, headers=MUTATE)
    assert r.status_code == 201
    w = r.json()
    assert w["sets_done"] == 4 and w["sets_total"] == 5 and w["entries"][0]["label"] == "Goblet Squat" and w["day"] == "2026-11-10"
    assert client.get("/api/gym/workouts").json()["workouts"][0]["id"] == w["id"]
    assert client.get(f"/api/gym/plans/{plan['id']}").json()["workout"]["id"] == w["id"]
    week = client.get("/api/planner").json()
    assert next(p for d in week["days"] for p in d["plans"] if p["id"] == plan["id"])["logged"] is True
    loads = client.get("/api/gym/last-loads", params={"ids": "goblet-squat,plank,back-squat"}).json()["loads"]
    assert loads["goblet-squat"]["load"] == "24 kg" and loads["goblet-squat"]["hint"]["kind"] == "increase_load" and "plank" not in loads and "back-squat" not in loads
    for bad in ([], [{"exercise": "nope", "sets": [{"reps": 1}]}], [{"exercise": "plank", "sets": []}], [{"exercise": "plank", "sets": [{"reps": -1}]}], [{"sets": [{"reps": 1}]}],
                [{"exercise": "plank", "sets": [{"reps": True}]}], ["x"]):
        assert client.post("/api/gym/workouts", json={"name": "x", "entries": bad}, headers=MUTATE).status_code in (400, 422), bad
    assert client.get("/api/gym/last-loads", params={"ids": "../x"}).status_code == 422
    assert client.delete(f"/api/gym/workouts/{w['id']}", headers=MUTATE).json() == {"deleted": w["id"]}
    assert client.delete(f"/api/gym/workouts/{w['id']}", headers=MUTATE).status_code == 404
    assert client.get("/api/gym/workouts").json()["workouts"] == []
