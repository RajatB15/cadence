from datetime import date

import pytest

from cadence_app.credentials import credential_status, parse_thresholds

EXPIRES = "2027-10-22"
BASE = {"GARMIN_API_KEY": "test-key", "GARMIN_API_KEY_EXPIRES_ON": EXPIRES}


@pytest.mark.parametrize(
    ("today", "level", "threshold", "days"),
    [
        (date(2026, 10, 22), "ok", None, 365),
        (date(2027, 9, 21), "ok", None, 31),
        (date(2027, 9, 22), "notice", 30, 30),
        (date(2027, 10, 14), "notice", 30, 8),
        (date(2027, 10, 15), "warning", 7, 7),
        (date(2027, 10, 20), "warning", 7, 2),
        (date(2027, 10, 21), "critical", 1, 1),
        (date(2027, 10, 22), "expired", None, 0),
        (date(2028, 1, 1), "expired", None, -71),
    ],
)
def test_threshold_boundaries(today, level, threshold, days):
    status = credential_status(BASE, today)
    assert (status.level, status.active_threshold, status.days_remaining) == (level, threshold, days)


def test_reminder_dates_match_plan():
    status = credential_status(BASE, date(2026, 10, 22))
    assert status.reminder_dates == (date(2027, 9, 22), date(2027, 10, 15), date(2027, 10, 21))


def test_reminder_key_changes_on_escalation_and_expiry():
    keys = [
        credential_status(BASE, d).reminder_key
        for d in (date(2026, 10, 22), date(2027, 9, 22), date(2027, 10, 15), date(2027, 10, 21), date(2027, 10, 22))
    ]
    assert keys == [None, f"{EXPIRES}:30", f"{EXPIRES}:7", f"{EXPIRES}:1", f"{EXPIRES}:expired"]


def test_leap_year_reminder():
    values = {**BASE, "GARMIN_API_KEY_EXPIRES_ON": "2028-03-01", "GARMIN_API_KEY_REMINDER_DAYS": "1"}
    status = credential_status(values, date(2028, 2, 29))
    assert status.reminder_dates == (date(2028, 2, 29),)
    assert status.level == "critical"


def test_missing_and_invalid_expiry_are_distinct():
    assert credential_status({}, date(2026, 10, 22)).level == "missing"
    assert credential_status({"GARMIN_API_KEY": " "}, date(2026, 10, 22)).level == "missing"
    invalid = credential_status({"GARMIN_API_KEY": "k", "GARMIN_API_KEY_EXPIRES_ON": "next year"}, date(2026, 10, 22))
    assert (invalid.configured, invalid.level, invalid.reminder_key) == (True, "invalid_expiry", None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, (30, 7, 1)), ("", (30, 7, 1)), ("7,30,1", (30, 7, 1)), ("x,7", (30, 7, 1)), ("14", (14,)), ("0,-3", (30, 7, 1))],
)
def test_parse_thresholds(raw, expected):
    assert parse_thresholds(raw) == expected
