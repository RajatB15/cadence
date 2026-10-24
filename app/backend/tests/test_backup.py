import json
from datetime import UTC, datetime, timedelta

from cadence_app import backup
from tests.test_api import env  # noqa: F401  (fixture)

NOW = datetime(2026, 10, 25, 9, 0)


def write(tmp_path, payload):
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / backup.STATUS_FILE).write_text(payload if isinstance(payload, str) else json.dumps(payload))


def test_no_status_file_means_not_configured(tmp_path):
    assert backup.load(tmp_path, NOW) == {"configured": False}


def test_recent_success_is_not_stale(tmp_path):
    write(tmp_path, {"last_success_at": "2026-10-25T03:31:10", "snapshot": "20261025-0901", "last_attempt_at": "2026-10-25T03:31:10", "last_error": None})
    s = backup.load(tmp_path, NOW)
    assert s["configured"] and not s["stale"] and s["last_error"] is None
    assert s["last_success_at"] == datetime(2026, 10, 25, 3, 31, 10) and s["snapshot"] == "20261025-0901"


def test_a_missed_night_is_stale(tmp_path):
    write(tmp_path, {"last_success_at": "2026-10-23T08:00:00", "snapshot": "x", "last_attempt_at": "2026-10-24T22:00:00", "last_error": "Backup failed"})
    s = backup.load(tmp_path, NOW)
    assert s["stale"] and s["last_error"] == "Backup failed"


def test_failed_first_run_has_no_success_and_is_stale(tmp_path):
    write(tmp_path, {"last_success_at": None, "snapshot": None, "last_attempt_at": "2026-10-25T03:30:00", "last_error": "Backup failed"})
    s = backup.load(tmp_path, NOW)
    assert s["configured"] and s["last_success_at"] is None and s["stale"]


def test_a_corrupt_file_is_treated_as_not_configured(tmp_path):
    write(tmp_path, "{not json")
    assert backup.load(tmp_path, NOW) == {"configured": False}
    write(tmp_path, "[1, 2]")
    assert backup.load(tmp_path, NOW) == {"configured": False}


def test_status_endpoint_reads_the_data_directory(env, tmp_path):  # noqa: F811
    client, _ = env
    assert client.get("/api/backup/status").json() == {"configured": False}
    recent = (datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=3)).isoformat(timespec="seconds")
    write(tmp_path / "data", {"last_success_at": recent, "snapshot": "20261022-0330", "last_attempt_at": recent, "last_error": None})
    body = client.get("/api/backup/status").json()
    assert body["configured"] and body["snapshot"] == "20261022-0330" and body["stale"] is False
