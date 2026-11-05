from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from cadence_app import localtime
from cadence_app.main import Clock, create_app
from tests.test_api import env  # noqa: F401


def test_today_in_zone_crosses_midnight():
    instant = datetime(2026, 10, 22, 23, 30, tzinfo=UTC)
    assert localtime.today_in("UTC", instant) == date(2026, 10, 22)
    assert localtime.today_in("Asia/Kolkata", instant) == date(2026, 10, 23)
    assert localtime.today_in("America/Los_Angeles", instant) == date(2026, 10, 22)
    # naive instants are UTC by convention
    assert localtime.today_in("Asia/Kolkata", instant.replace(tzinfo=None)) == date(2026, 10, 23)


def test_invalid_zone_rejected():
    for bad in ("Mars/Olympus", "../etc/passwd", "/UTC", "x" * 80):
        with pytest.raises(ValueError):
            localtime.validate(bad)


def test_clock_uses_configured_zone():
    clock = Clock()
    clock.tz_name = "Pacific/Kiritimati"
    assert clock.today() == datetime.now(localtime.zone("Pacific/Kiritimati")).date()
    assert clock.tz().key == "Pacific/Kiritimati"


def test_timezone_setting_roundtrip(env):  # noqa: F811
    client, clock = env
    assert client.put("/api/settings/timezone", json={"timezone": "Nowhere/Land"}, headers={"X-Cadence-Request": "1"}).status_code == 400
    r = client.put("/api/settings/timezone", json={"timezone": "Asia/Kolkata"}, headers={"X-Cadence-Request": "1"})
    assert r.status_code == 200 and r.json()["timezone"] == "Asia/Kolkata"
    assert clock.tz_name == "Asia/Kolkata"
    assert client.get("/api/settings/timezone").json()["timezone"] == "Asia/Kolkata"
    assert client.put("/api/settings/timezone", json={"timezone": None}, headers={"X-Cadence-Request": "1"}).json()["timezone"] is None
