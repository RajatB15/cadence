from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_share import api, phone, web  # noqa: F401  (fixtures)


def test_manual_entry_round_trip_and_replace(env):  # noqa: F811
    client, _ = env  # fixed clock: 2026-10-22
    assert client.get("/api/weight/entries").json()["entries"] == []

    r = client.post("/api/weight/entries", json={"day": "2026-10-20", "weight_kg": 80.0}, headers=MUTATE)
    assert r.status_code == 200 and r.json()["weight_kg"] == 80.0
    client.post("/api/weight/entries", json={"day": "2026-10-22", "weight_kg": 79.4}, headers=MUTATE)
    client.post("/api/weight/entries", json={"day": "2026-10-20", "weight_kg": 80.5}, headers=MUTATE)  # corrects, not duplicates

    entries = client.get("/api/weight/entries").json()["entries"]
    assert [(e["day"], e["weight_kg"]) for e in entries] == [("2026-10-22", 79.4), ("2026-10-20", 80.5)]

    points = client.get("/api/weight?days=30").json()["points"]
    assert {p["day"]: p["weight_kg"] for p in points} == {"2026-10-20": 80.5, "2026-10-22": 79.4}

    assert client.delete("/api/weight/entries/2026-10-20", headers=MUTATE).status_code == 200
    assert client.delete("/api/weight/entries/2026-10-20", headers=MUTATE).status_code == 404
    assert len(client.get("/api/weight/entries").json()["entries"]) == 1


def test_manual_entry_validation(env):  # noqa: F811
    client, _ = env
    assert client.post("/api/weight/entries", json={"day": "2026-10-22", "weight_kg": 12}, headers=MUTATE).status_code == 422
    assert client.post("/api/weight/entries", json={"day": "2026-10-22", "weight_kg": 900}, headers=MUTATE).status_code == 422
    future = client.post("/api/weight/entries", json={"day": "2026-10-23", "weight_kg": 80}, headers=MUTATE)
    assert future.status_code == 400 and "future" in future.json()["detail"]
    assert client.post("/api/weight/entries", json={"day": "2026-10-22", "weight_kg": 80}).status_code == 403  # no CSRF header


def test_manual_entry_blends_with_the_demo_history(env):  # noqa: F811
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    before = client.get("/api/weight?days=30").json()["points"]
    client.post("/api/weight/entries", json={"day": "2026-10-21", "weight_kg": 100.0}, headers=MUTATE)
    after = {p["day"]: p for p in client.get("/api/weight?days=30").json()["points"]}
    assert after["2026-10-21"]["weight_kg"] != next((p["weight_kg"] for p in before if p["day"] == "2026-10-21"), None)


def test_paired_phone_can_log_and_remove_a_weight(api, web):  # noqa: F811
    c = phone(api, web)
    c.get("/pair?key=tok", follow_redirects=False)
    day = "2026-10-22"
    r = c.post("/api/weight/entries", json={"day": day, "weight_kg": 75.0}, headers=MUTATE)
    assert r.status_code == 200
    assert c.delete(f"/api/weight/entries/{day}", headers=MUTATE).status_code == 200
