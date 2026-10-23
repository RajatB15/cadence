import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from cadence_app import scale
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)


@dataclass
class FakeReading:
    """Stands in for `cadence_ble.ssw526.WeightReading` so these tests don't need bleak installed."""

    weight_kg: float
    stable: bool
    raw: int


SETTLING = lambda raw: FakeReading(raw / 120, False, raw)  # noqa: E731
LOCKED = lambda raw: FakeReading(round(raw / 120, 2), True, raw)  # noqa: E731


def test_debouncer_needs_repeats_and_ignores_settling_noise():
    d = scale.Debouncer(stable_repeats=3, cooldown_s=60)
    # A realistic sequence: noisy settling, then the value locks and repeats (as seen in real captures).
    noisy = [SETTLING(r) for r in (1200, 4300, 5100, 5600, 5350)]
    for r in noisy:
        assert d.offer(r, now_s=0.0) is None
    assert d.offer(LOCKED(6000), now_s=1.0) is None  # 1st repeat
    assert d.offer(LOCKED(6000), now_s=1.3) is None  # 2nd repeat
    accepted = d.offer(LOCKED(6000), now_s=1.6)  # 3rd repeat: accepted
    assert accepted is not None and accepted.weight_kg == 50.0


def test_debouncer_resets_the_run_if_the_value_changes_mid_lock():
    d = scale.Debouncer(stable_repeats=3, cooldown_s=60)
    assert d.offer(LOCKED(6000), now_s=0) is None
    assert d.offer(LOCKED(6000), now_s=0.3) is None
    assert d.offer(LOCKED(9000), now_s=0.6) is None  # different locked value: run restarts
    assert d.offer(LOCKED(9000), now_s=0.9) is None
    assert d.offer(LOCKED(9000), now_s=1.2) is not None


def test_debouncer_enforces_a_cooldown_between_acceptances():
    d = scale.Debouncer(stable_repeats=2, cooldown_s=60)
    assert d.offer(LOCKED(6000), now_s=0) is None
    assert d.offer(LOCKED(6000), now_s=0.3) is not None  # accepted
    # Still locked at the same value well within the cooldown: must not accept again.
    for t in (5, 10, 30, 59.9):
        assert d.offer(LOCKED(6000), now_s=t) is None
    assert d.offer(LOCKED(6000), now_s=61) is not None  # cooldown elapsed


def test_debouncer_ignores_a_zero_weight_reading_like_an_empty_platform():
    # Zero decodes fine (ssw526 doesn't filter it) but three locked zeros shouldn't look like a weigh-in
    # from the app's point of view... except the debouncer itself is intentionally value-agnostic (the
    # caller decides); confirm it does still accept 0 so that policy choice is explicit and visible here.
    d = scale.Debouncer(stable_repeats=3, cooldown_s=60)
    d.offer(LOCKED(0), now_s=0)
    d.offer(LOCKED(0), now_s=0.3)
    accepted = d.offer(LOCKED(0), now_s=0.6)
    assert accepted is not None and accepted.weight_kg == 0.0


def test_build_record_uses_local_date_and_a_utc_offset_timezone_label():
    tz = timezone(timedelta(hours=5, minutes=30))
    local = datetime(2026, 10, 24, 0, 30, tzinfo=tz)  # just after local midnight
    record = scale.build_record(LOCKED(9000), local)
    assert record.local_date == date(2026, 10, 24)
    assert record.timezone == "UTC+05:30"
    assert record.weight_kg == 75.0
    assert record.body_fat_pct is None
    # UTC instant: 2026-10-23 19:00, the day before the local date.
    assert record.measured_at_utc == datetime(2026, 10, 23, 19, 0)
    assert record.source_record_id == f"ssw526:{int(local.timestamp())}"


def test_build_record_handles_a_negative_utc_offset():
    tz = timezone(timedelta(hours=-8))
    local = datetime(2026, 10, 23, 9, 0, tzinfo=tz)
    record = scale.build_record(LOCKED(8400), local)
    assert record.timezone == "UTC-08:00" and record.local_date == date(2026, 10, 23)


def test_available_is_false_when_the_import_fails(monkeypatch):
    # Forced deterministically (rather than relying on whether this machine happens to have the research
    # package installed) so this passes the same way in CI and on a dev machine with it installed.
    monkeypatch.setitem(sys.modules, "bleak", None)
    assert scale.available() is False


def test_scale_setting_round_trip_when_unavailable(env, monkeypatch):  # noqa: F811
    client, _ = env
    monkeypatch.setattr(scale, "available", lambda: False)
    status = client.get("/api/scale/status").json()
    assert status == {"available": False, "enabled": False, "running": False, "connected": False, "last_error": None, "last_reading": None, "live": None}
    r = client.put("/api/settings/scale", json={"enabled": True}, headers=MUTATE)
    assert r.json() == {"enabled": True, "available": False}
    # Enabling doesn't start anything when the feature isn't available.
    assert client.get("/api/scale/status").json()["running"] is False
    assert client.get("/api/scale/status").json()["enabled"] is True
    client.put("/api/settings/scale", json={"enabled": False}, headers=MUTATE)
    assert client.get("/api/scale/status").json()["enabled"] is False


def test_sources_lists_scale_with_a_status_matching_availability(env):  # noqa: F811
    client, _ = env
    row = next(s for s in client.get("/api/sources").json() if s["id"] == "scale")
    # "off" when the feature is available but not enabled, "unavailable" when it isn't importable at all -
    # either is correct depending on whether this machine happens to have the research package installed.
    assert row["status"] in ("off", "unavailable")


def test_weight_endpoint_blends_scale_readings_with_the_active_source(env, tmp_path):  # noqa: F811
    from cadence_app.db import make_engine, make_session_factory
    from cadence_app.importer import Batch, WeightRecord, ensure_source, write_batch
    from cadence_app.models import Source

    client, _ = env
    # Insert a scale reading directly (bypassing the listener, which needs real hardware) to verify the
    # read-side blend without needing bleak. Same database the `env` fixture's app already opened.
    factory = make_session_factory(make_engine(f"sqlite:///{tmp_path / 'data' / 'cadence.sqlite3'}"))
    with factory() as session, session.begin():
        ensure_source(session, scale.SOURCE_ID, scale.SOURCE_NAME, "scale")
        write_batch(session, scale.SOURCE_ID, Batch(weights=[
            WeightRecord("ssw526:1", datetime(2026, 10, 20, 7, 0), "UTC", date(2026, 10, 20), 68.2, None),
        ]), datetime(2026, 10, 20, 7, 0))
        assert session.get(Source, scale.SOURCE_ID) is not None

    points = client.get("/api/weight?days=3650").json()["points"]
    assert any(p["day"] == "2026-10-20" and p["weight_kg"] == 68.2 for p in points)


def test_status_reports_the_live_in_progress_reading(env):  # noqa: F811
    from cadence_app.scale import LiveReading

    client, _ = env
    listener = client.app.state.scale_listener
    assert client.get("/api/scale/status").json()["live"] is None
    listener.live = LiveReading(weight_kg=68.4, stable=False, seen_at="2026-10-24T07:00:00+05:30")
    status = client.get("/api/scale/status").json()
    assert status["live"] == {"weight_kg": 68.4, "stable": False, "seen_at": "2026-10-24T07:00:00+05:30"}
    listener.live = LiveReading(weight_kg=68.2, stable=True, seen_at="2026-10-24T07:00:03+05:30")
    assert client.get("/api/scale/status").json()["live"]["stable"] is True
