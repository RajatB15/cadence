from datetime import date

import pytest
from fastapi.testclient import TestClient

from cadence_app.config import Settings
from cadence_app.main import Clock, create_app

MUTATE = {"X-Cadence-Request": "1"}


class FixedClock(Clock):
    def __init__(self, today: date):
        self.current = today

    def today(self) -> date:
        return self.current


@pytest.fixture
def env(tmp_path):
    secrets = tmp_path / "garmin.env"
    secrets.write_text(
        "GARMIN_API_KEY='not-a-real-key'\nGARMIN_API_KEY_EXPIRES_ON=2027-10-22\nGARMIN_API_KEY_REMINDER_DAYS=30,7,1\n"
    )
    clock = FixedClock(date(2026, 10, 22))
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets), clock)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, clock


def test_rejects_unknown_host(env):
    client, _ = env
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_mutation_requires_custom_header_and_allowed_origin(env):
    client, _ = env
    assert client.post("/api/sync/demo").status_code == 403
    bad_origin = {**MUTATE, "Origin": "https://evil.example"}
    assert client.post("/api/sync/demo", headers=bad_origin).status_code == 403
    ok_origin = {**MUTATE, "Origin": "http://localhost:5173"}
    assert client.post("/api/sync/demo", headers=ok_origin).status_code == 200


def test_credential_status_never_exposes_key(env):
    client, _ = env
    response = client.get("/api/credentials/status")
    body = response.json()
    assert "not-a-real-key" not in response.text
    assert body["level"] == "ok" and body["days_remaining"] == 365
    assert body["reminder_dates"] == ["2027-09-22", "2027-10-15", "2027-10-21"]


def test_dismissal_does_not_hide_escalation(env):
    client, clock = env
    clock.current = date(2027, 9, 25)
    status = client.get("/api/credentials/status").json()
    assert status["level"] == "notice" and not status["dismissed"]
    assert client.post(
        "/api/credentials/reminders/dismiss", json={"key": status["reminder_key"]}, headers=MUTATE
    ).status_code == 200
    assert client.get("/api/credentials/status").json()["dismissed"]

    clock.current = date(2027, 10, 15)
    escalated = client.get("/api/credentials/status").json()
    assert escalated["level"] == "warning" and not escalated["dismissed"]

    clock.current = date(2027, 10, 22)
    expired = client.get("/api/credentials/status").json()
    assert expired["level"] == "expired"
    assert client.post(
        "/api/credentials/reminders/dismiss", json={"key": expired["reminder_key"]}, headers=MUTATE
    ).status_code == 409


def test_stale_dismissal_rejected(env):
    client, clock = env
    clock.current = date(2027, 10, 16)
    response = client.post(
        "/api/credentials/reminders/dismiss", json={"key": "2027-10-22:30"}, headers=MUTATE
    )
    assert response.status_code == 409


def test_demo_sync_is_idempotent(env):
    client, _ = env
    first = client.post("/api/sync/demo", headers=MUTATE).json()
    counts = client.get("/api/activities?limit=1").json()["total"]
    second = client.post("/api/sync/demo", headers=MUTATE).json()
    assert first["status"] == second["status"] == "succeeded"
    assert first["records_written"] == second["records_written"] > 0
    assert client.get("/api/activities?limit=1").json()["total"] == counts
    hrv = client.get("/api/metrics/hrv?days=3650").json()["points"]
    assert len(hrv) == 365
    assert len({p["day"] for p in hrv}) == len(hrv)
    assert hrv[-1]["day"] == "2026-10-21"


def test_empty_state_then_overview(env):
    client, _ = env
    assert client.get("/api/overview").json() == {"has_data": False}
    client.post("/api/sync/demo", headers=MUTATE)
    overview = client.get("/api/overview").json()
    assert overview["has_data"] and overview["as_of"] == "2026-10-21"
    assert {m["metric"] for m in overview["metrics"]} >= {"hrv", "resting_hr", "sleep_hours"}
    assert overview["weight"]["latest_trend_kg"] is not None
    coach = overview["coach"]
    assert coach["today"]["title"] and coach["week"]["items"] is not None and "recent" in coach
    assert overview["score"]["score"] is not None and overview["score"]["groups"]
    detail = client.get("/api/score").json()
    assert detail["has_data"] and detail["factors"] and detail["history"]
    assert {s["key"] for s in coach["streaks"]} >= {"weeks", "sleep"}
    first = client.get("/api/activities?limit=500").json()["items"]
    assert all("verdict" in a for a in first)
    log = client.get("/api/activities/summary").json()
    assert log["has_data"] and len(log["calendar"]) >= 365 and log["year"]["sessions"] > 0
    assert log["records"] and log["mix"] and log["weeks"]
    runs = client.get("/api/activities/summary?family=run").json()
    assert {m["family"] for m in runs["mix"]} <= {"run"}
    detail = client.get(f"/api/activities/{first[0]['id']}").json()
    assert detail["coach"]["notes"] is not None
    day = client.get(f"/api/days/{overview['as_of']}").json()
    assert any("hrv" in n["metrics"] for n in day["coach"]["notes"])
    assert isinstance(client.get("/api/weight").json()["coach"], list)


def test_weight_goal_round_trip(env):
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    assert client.put("/api/settings/weight-goal", json={"goal_kg": 75}, headers=MUTATE).status_code == 200
    weight = client.get("/api/weight").json()
    assert weight["goal_kg"] == 75 and weight["projection"]["goal_kg"] == 75
    assert client.put("/api/settings/weight-goal", json={"goal_kg": 5}, headers=MUTATE).status_code == 422
    client.put("/api/settings/weight-goal", json={"goal_kg": None}, headers=MUTATE)
    assert client.get("/api/weight").json()["projection"] is None


def test_delete_demo_data(env):
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    assert client.delete("/api/sources/demo/data", headers=MUTATE).status_code == 200
    assert client.get("/api/overview").json() == {"has_data": False}
    assert client.get("/api/weight").json()["points"] == []


def test_unknown_metric(env):
    client, _ = env
    assert client.get("/api/metrics/nope").status_code == 404


def test_real_source_never_blends_demo_data(tmp_path):
    client, fake = garmin_app(tmp_path)
    with client:
        client.post("/api/sync/demo", headers=MUTATE)
        assert client.get("/api/overview").json()["source_id"] == "demo"
        assert client.post("/api/garmin/sync", json={"mode": "quick"}, headers=MUTATE).status_code == 202
        wait_idle(client)

        overview = client.get("/api/overview").json()
        assert overview["source_id"] == "garmin"
        assert all(a["source_id"] == "garmin" for a in overview["recent_activities"])
        activities = client.get("/api/activities?limit=500").json()["items"]
        assert activities and all(a["source_id"] == "garmin" for a in activities)
        status = client.get("/api/garmin/status").json()
        assert status["totals"]["first_day"] == "2025-09-01"
        assert status["vault"]["responses"] > 0
        assert "synthetic-key" not in str(status)


def test_garmin_job_conflict_and_rebuild(tmp_path):
    client, fake = garmin_app(tmp_path)
    with client:
        client.post("/api/garmin/sync", json={"mode": "quick"}, headers=MUTATE)
        wait_idle(client)
        calls = fake.total
        assert client.post("/api/garmin/rebuild", headers=MUTATE).status_code == 202
        status = wait_idle(client)
        assert status["run"]["mode"] == "rebuild" and status["run"]["status"] == "succeeded"
        assert fake.total == calls
        assert client.post("/api/garmin/sync", json={"mode": "bogus"}, headers=MUTATE).status_code == 422
        assert client.post("/api/garmin/sync", json={"mode": "quick"}).status_code == 403


def test_garmin_failure_is_persisted_without_switching_source(tmp_path):
    client, fake = garmin_app(tmp_path)
    fake.fail_with = 401
    with client:
        client.post("/api/sync/demo", headers=MUTATE)
        client.post("/api/garmin/sync", json={"mode": "quick"}, headers=MUTATE)
        status = wait_idle(client)
        assert client.get("/api/overview").json()["source_id"] == "demo"
        assert status["run"]["status"] == "failed"
        assert "401" in status["run"]["error"]


def test_activity_detail_shows_everything_and_fetches_once(tmp_path):
    client, fake = garmin_app(tmp_path)
    with client:
        client.post("/api/garmin/sync", json={"mode": "quick"}, headers=MUTATE)
        wait_idle(client)
        first = client.get("/api/activities?limit=1").json()["items"][0]

        detail = client.get(f"/api/activities/{first['id']}").json()
        assert detail["garmin_summary"]["activityName"] == "Morning Run"
        assert detail["garmin_summary"]["vO2MaxValue"] == 50.0
        assert set(detail["missing"]) == {"activity_fit", "activity_detail", "activity_workouts"}

        calls = fake.total
        assert client.post(f"/api/activities/{first['id']}/fetch", headers=MUTATE).json()["fetched"]
        assert fake.total == calls + 3 + 1  # three assets plus one token exchange
        detail = client.get(f"/api/activities/{first['id']}").json()
        assert detail["missing"] == [] and detail["detail"]["splitSummaries"] == []
        assert detail["fit"] is not None

        calls = fake.total
        assert client.post(f"/api/activities/{first['id']}/fetch", headers=MUTATE).json()["fetched"] == []
        assert fake.total == calls
        assert client.get("/api/activities/999999").status_code == 404


def test_vault_explorer_lists_and_opens_every_dataset(tmp_path):
    client, _ = garmin_app(tmp_path)
    with client:
        client.post("/api/garmin/sync", json={"mode": "quick"}, headers=MUTATE)
        wait_idle(client)
        listing = client.get("/api/garmin/vault/daily_summaries?limit=5").json()
        assert listing["total"] > 0 and len(listing["items"]) <= 5
        item = client.get(f"/api/garmin/vault/item/{listing['items'][0]['id']}").json()
        assert isinstance(item["payload"]["data"], list)
        assert client.get("/api/garmin/vault/not_a_dataset").status_code == 404
        assert client.get("/api/garmin/vault/item/999999").status_code == 404


def test_day_detail_has_context_raw_rows_and_fetches_intraday_once(tmp_path):
    client, fake = garmin_app(tmp_path)
    with client:
        client.post("/api/garmin/sync", json={"mode": "quick"}, headers=MUTATE)
        wait_idle(client)
        day = client.get("/api/days/2026-10-10").json()
        hrv = day["metrics"]["hrv"]
        assert hrv["value"] == 60 and hrv["avg_7d"] == 60 and hrv["label"] == "HRV"
        assert hrv["count"] > 200 and hrv["rank_high"] == 1
        assert day["raw"]["daily_summaries"]["calendarDate"] == "2026-10-10"
        assert day["raw"]["sleep"]["sleepTimeSeconds"] == 27000
        assert day["raw"]["hrv"]["lastNightAvg"] == 60
        assert set(day["missing"]) == {"hrv_intraday", "hr_intraday", "spo2"}
        assert day["prev_day"] == "2026-10-09" and day["next_day"] == "2026-10-11"

        calls = fake.total
        assert set(client.post("/api/days/2026-10-10/fetch", headers=MUTATE).json()["fetched"]) == {
            "hrv_intraday", "hr_intraday", "spo2",
        }
        assert fake.total == calls + 3 + 1
        day = client.get("/api/days/2026-10-10").json()
        assert day["missing"] == [] and day["raw"]["hrv_intraday"]["hrvReadings"]
        calls = fake.total
        assert client.post("/api/days/2026-10-10/fetch", headers=MUTATE).json()["fetched"] == []
        assert fake.total == calls
        assert client.get("/api/days/1999-01-01").json()["metrics"] == {}


def garmin_app(tmp_path):
    from tests.fake_garmin import FakeGarmin
    from cadence_app.garmin.client import GarminClient

    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='synthetic-key'\nGARMIN_API_KEY_EXPIRES_ON=2027-10-22\n")
    fake = FakeGarmin(date(2026, 10, 22))
    app = create_app(
        Settings(data_dir=tmp_path / "data", secrets_file=secrets),
        FixedClock(date(2026, 10, 22)),
        lambda key: GarminClient(key, fake.transport(), min_interval_s=0, sleep=lambda s: None),
    )
    return TestClient(app, base_url="http://127.0.0.1"), fake


def wait_idle(client, timeout=60.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get("/api/garmin/status").json()
        if not status["busy"]:
            return status
        time.sleep(0.05)
    raise AssertionError("Garmin job did not finish")


def test_training_goal_drives_the_plan(env):
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    assert client.put("/api/settings/goal", json={"distance": "half", "date": "2026-01-01"}, headers=MUTATE).status_code == 400
    r = client.put("/api/settings/goal", json={"distance": "half", "date": "2026-11-22", "target_s": 6300}, headers=MUTATE).json()
    assert r["goal"]["label"] == "Half marathon" and r["goal"]["target_pace_s"] == 299
    body = client.get("/api/insights").json()
    assert body["goal"]["distance"] == "half"
    assert body["plan"]["phase"]["weeks_to_race"] == 4 and body["plan"]["goal"]["date"] == "2026-11-22"
    for key in ("performance", "hrv_guided", "recovery", "readiness_validation"):
        assert key in body
    assert body["sleep"]["need"]["hours"] >= 7
    assert client.put("/api/settings/goal", json={}, headers=MUTATE).json() == {"goal": None}
    assert client.get("/api/insights").json()["goal"] is None
