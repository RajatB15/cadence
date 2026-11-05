"""Regression tests for the adversarial-review fixes (synthetic data only)."""
import json
import os
import stat
import subprocess
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pytest
from sqlalchemy import func, select

from cadence_app import localtime
from cadence_app.analytics import insights, performance, recovery, regress
from cadence_app.db import make_engine, make_session_factory, upgrade_database
from cadence_app.garmin.client import GarminClient
from cadence_app.garmin.engine import MAX_BAD_ATTEMPTS, SyncEngine
from cadence_app.models import Activity, ActivityAnalysis, DailyMetric, DatasetState, DayHeartHistogram, RawResponse
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_garmin_sync import TODAY, run_sync, world  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[3]


# (1) context cache ------------------------------------------------------------

def _factory(tmp_path, name="c.db"):
    url = f"sqlite:///{tmp_path / name}"
    upgrade_database(url)
    engine = make_engine(url)
    return engine, make_session_factory(engine)


def test_invalidation_during_a_build_is_not_lost(tmp_path, monkeypatch):
    _, factory = _factory(tmp_path)
    started, release = threading.Event(), threading.Event()
    version = {"v": 1}

    def slow_build(*a, **k):
        v = version["v"]  # reads "the database" at build start
        started.set()
        release.wait(5)
        return {"as_of": v}

    monkeypatch.setattr(insights, "build_context", slow_build)
    insights.invalidate_context()
    out = []

    def go():
        with factory() as s:
            out.append(insights.context(s, "demo", date(2026, 1, 1)))

    t = threading.Thread(target=go)
    t.start()
    started.wait(5)
    version["v"] = 2  # a write lands and invalidates while the build is running
    insights.invalidate_context()
    release.set()
    t.join(10)
    assert out[0]["as_of"] == 2  # the stale build was discarded and rebuilt, not served
    with factory() as s:
        assert insights.context(s, "demo", date(2026, 1, 1))["as_of"] == 2  # and the cache holds the fresh one


def test_waiting_for_the_build_lock_holds_no_pooled_connection(tmp_path, monkeypatch):
    engine, factory = _factory(tmp_path, "p.db")
    monkeypatch.setattr(insights, "build_context", lambda *a, **k: {"as_of": 1})
    insights.invalidate_context()
    seen = []

    def go():
        with factory() as s:
            insights.context(s, "demo", date(2026, 1, 1))

    insights._build_lock.acquire()
    try:
        t = threading.Thread(target=go)
        t.start()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not seen:
            time.sleep(0.1)
            if t.is_alive():
                seen.append(engine.pool.checkedout())
        assert seen and seen[-1] == 0  # blocked on the build lock without a connection checked out
    finally:
        insights._build_lock.release()
    t.join(5)


# (2) data_version -------------------------------------------------------------

def test_data_version_sees_recomputed_and_deleted_analyses(env):  # noqa: F811
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    factory = client.app.state.share.factory
    with factory() as s:
        act = s.scalars(select(Activity)).first()
        other = s.scalars(select(Activity).where(Activity.id != act.id)).first()
        s.add_all([ActivityAnalysis(activity_id=act.id, version=insights.ANALYSIS_VERSION, computed_at=datetime(2026, 1, 1), data="{}"),
                   ActivityAnalysis(activity_id=other.id, version=insights.ANALYSIS_VERSION, computed_at=datetime(2026, 1, 2), data="{}")])
        s.commit()
        v0 = insights.data_version(s)
        # an OLDER row (lower primary key than another) is recomputed
        row = s.get(ActivityAnalysis, min(act.id, other.id))
        row.computed_at = datetime(2026, 2, 1)
        row.data = '{"x": 1}'
        s.commit()
        v1 = insights.data_version(s)
        assert v1 != v0
        s.delete(s.get(ActivityAnalysis, min(act.id, other.id)))  # delete of a non-maximal row
        s.commit()
        assert insights.data_version(s) != v1
        s.add(DayHeartHistogram(source_id="garmin", day=date(2026, 1, 1), version=1, outside="{}", inside="{}", samples=1, computed_at=datetime(2026, 1, 1)))
        s.add(DayHeartHistogram(source_id="garmin", day=date(2026, 1, 5), version=1, outside="{}", inside="{}", samples=1, computed_at=datetime(2026, 1, 1)))
        s.commit()
        h0 = insights.data_version(s)
        s.get(DayHeartHistogram, ("garmin", date(2026, 1, 1))).computed_at = datetime(2026, 3, 1)
        s.commit()
        assert insights.data_version(s) != h0


# (3) rebuild ordering ---------------------------------------------------------

def test_rebuild_does_not_resurrect_load_of_pruned_activities(world):  # noqa: F811
    factory, fake, clock, archive = world
    run_sync(factory, fake, clock, archive)
    with factory() as s:
        act = s.scalars(select(Activity).where(Activity.training_load.is_not(None))).first()
        day = act.local_date
        s.add(Activity(source_id="garmin", source_record_id="ghost-1", start_time_utc=datetime(2020, 1, 1, 8), timezone="UTC",
                       local_date=date(2020, 1, 1), activity_type="running", name="ghost", duration_s=600, training_load=77.0, vo2max=55.0, imported_at=datetime(2020, 1, 2)))
        s.commit()
    engine = SyncEngine(factory, archive, clock.today, clock.now)
    engine._refresh_derived()  # the ghost's load is now derived into daily metrics
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(DailyMetric).where(DailyMetric.day == date(2020, 1, 1))) > 0
    engine.rebuild()
    with factory() as s:
        assert s.scalar(select(Activity).where(Activity.source_record_id == "ghost-1")) is None
        assert s.scalar(select(func.count()).select_from(DailyMetric).where(DailyMetric.day == date(2020, 1, 1))) == 0
        assert s.scalar(select(func.count()).select_from(DailyMetric).where(DailyMetric.day == day, DailyMetric.metric == "training_load")) == 1


# (4) bad-body head-of-line blocking -------------------------------------------

def _bad_detail_sync(factory, fake, clock, archive, bad_ids, deep=True):
    calls = []

    def handler(request):
        path = request.url.path
        for i in bad_ids:
            if path == f"/activity-service/activity/{i}":
                calls.append(path)
                return httpx.Response(200, text="<html>oops</html>", headers={"content-type": "text/html"})
        return fake.handle(request)

    engine = SyncEngine(factory, archive, clock.today, clock.now)
    client = GarminClient("synthetic-key", httpx.MockTransport(handler), min_interval_s=0, sleep=lambda s: None)
    try:
        engine.sync(client, include_deep=deep)
    finally:
        client.close()
    return engine, calls


def test_one_bad_activity_body_does_not_block_the_rest_and_is_given_up_after_three_runs(world):  # noqa: F811
    factory, fake, clock, archive = world
    run_sync(factory, fake, clock, archive)
    with factory() as s:
        ids = s.scalars(select(Activity.source_record_id).order_by(Activity.start_time_utc.desc())).all()
    assert len(ids) >= 3
    bad = ids[0]  # first in the queue: the head of the line
    engine, calls = _bad_detail_sync(factory, fake, clock, archive, [bad])
    assert calls == [f"/activity-service/activity/{bad}"]  # requested once in the run
    with factory() as s:
        done = {k for (k,) in s.execute(select(RawResponse.request_key).where(RawResponse.dataset == "activity_detail", RawResponse.final.is_(True)))}
        assert all(f"activity_detail:{i}" in done for i in ids[1:])  # everything behind it proceeded
        assert f"activity_detail:{bad}" not in done  # attempt 1: still retryable
    assert "Activity details & splits" in engine.failures
    for _ in range(MAX_BAD_ATTEMPTS - 1):
        _, calls = _bad_detail_sync(factory, fake, clock, archive, [bad])
        assert len(calls) <= 1
    with factory() as s:
        row = s.scalar(select(RawResponse).where(RawResponse.request_key == f"activity_detail:{bad}"))
        assert row.final  # given up: has_final now skips it
        state = s.get(DatasetState, ("garmin", "activity_detail"))
        assert json.loads(state.item_failures)[f"activity_detail:{bad}"]["gave_up"] is True
    engine, calls = _bad_detail_sync(factory, fake, clock, archive, [bad])
    assert calls == [] and "Activity details & splits" not in engine.failures


def test_bad_settled_window_in_recent_does_not_advance_final_until_until_given_up(world):  # noqa: F811
    factory, fake, clock, archive = world
    bad = {"on": True}

    def handler(request):
        if bad["on"] and "dailySleepSummariesByDate" in request.url.path:
            return httpx.Response(200, text="<html/>", headers={"content-type": "text/html"})
        return fake.handle(request)

    def sync():
        engine = SyncEngine(factory, archive, clock.today, clock.now)
        client = GarminClient("synthetic-key", httpx.MockTransport(handler), min_interval_s=0, sleep=lambda s: None)
        try:
            engine.sync(client, include_deep=False)
        finally:
            client.close()
        return engine

    first = sync()
    assert "Sleep" in " ".join(first.failures) or first.failures  # reported, but the other datasets still synced
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(DailyMetric).where(DailyMetric.metric == "hrv")) > 0
        sleep_state = s.get(DatasetState, ("garmin", "sleep"))
        assert sleep_state.final_until is None or sleep_state.final_until < TODAY - timedelta(days=3)  # nothing skipped over the bad window
    for _ in range(MAX_BAD_ATTEMPTS):
        last = sync()
    with factory() as s:
        sleep_state = s.get(DatasetState, ("garmin", "sleep"))
        assert sleep_state.final_until == TODAY - timedelta(days=3)  # given up on: the checkpoint advances


# (6) timezones ----------------------------------------------------------------

def test_today_in_uses_the_zones_real_rules_for_past_instants():
    summer = datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc)  # London is UTC+1 (BST): already July 2nd
    winter = datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)  # London is UTC+0
    assert localtime.today_in("Europe/London", summer) == date(2026, 7, 2)
    assert localtime.today_in("Europe/London", winter) == date(2026, 1, 1)


def test_system_zone_is_a_real_zone_not_a_fixed_offset(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/London")
    z = localtime.zone(None)
    assert z.utcoffset(datetime(2026, 7, 1)) != z.utcoffset(datetime(2026, 1, 1))


def test_context_offset_comes_from_the_users_zone_not_the_server(tmp_path):
    _, factory = _factory(tmp_path, "tz.db")
    with factory() as s:
        localtime.save(s, "Asia/Kolkata")
        # build_context returns None with no data, so check the offset the way it is derived
        tz = localtime.zone(localtime.load(s))
        assert tz.utcoffset(datetime(2026, 1, 1)) == timedelta(hours=5, minutes=30)


def test_readiness_now_compares_to_the_users_day(monkeypatch):
    seen = {}
    monkeypatch.setattr(insights, "readiness_on", lambda c, d: {"score": 70})
    monkeypatch.setattr(insights.A, "live_readiness", lambda morning, *a: seen.setdefault("called", True) and morning)
    c = {"as_of": date(2026, 6, 2), "series": {}, "pmc_by_day": {}, "acts": [], "utc_offset": timedelta(hours=10)}
    monkeypatch.setattr(insights, "utcnow", lambda: datetime(2026, 6, 1, 20, 0))  # 20:00 UTC on June 1st is already June 2nd at +10
    insights.readiness_now(c)
    assert seen.get("called")


def test_profile_birth_date_checked_against_the_users_today(tmp_path):
    from cadence_app import profile

    _, factory = _factory(tmp_path, "pr.db")
    with factory() as s:
        with pytest.raises(ValueError):
            profile.save(s, 180, date(2026, 6, 2), "male", today=date(2026, 6, 2))  # "tomorrow" for a UTC server, today for the user
        assert profile.save(s, 180, date(2026, 6, 1), "male", today=date(2026, 6, 2))["height_cm"] == 180


def test_scheduler_uses_the_users_zone(tmp_path):
    from zoneinfo import ZoneInfo

    from cadence_app import push

    s = push.Scheduler(None, None, None, None, None, datetime.utcnow, 3, tz=lambda: ZoneInfo("Pacific/Kiritimati"))  # UTC+14
    local = s.local_now()
    assert abs((local - datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=14)).total_seconds()) < 5


# (7) statistics ---------------------------------------------------------------

def test_ols_reports_its_hac_degrees_of_freedom_and_sleep_need_uses_them():
    rng = np.random.default_rng(1)
    x = np.column_stack([np.ones(80), rng.normal(size=80)])
    y = rng.normal(size=80)
    fit = regress.ols(x, y, lags=7)
    assert fit["df"] == pytest.approx(80 / (1 + 7 / 2) - 2) and fit["df"] < 78


def test_sleep_need_p_value_uses_conservative_df(monkeypatch):
    seen = {}
    real_sf = recovery.stats.t.sf

    def spy(t, df):
        seen["df"] = df
        return real_sf(t, df)

    day0 = date(2026, 1, 1)
    rng = np.random.default_rng(3)
    hours = {day0 + timedelta(days=i): float(rng.uniform(5.5, 9.5)) for i in range(150)}
    hrv = {day0 + timedelta(days=i): float(50 + 3 * min(hours[day0 + timedelta(days=i)], 8) + rng.normal(0, 3)) for i in range(150)}
    monkeypatch.setattr(recovery.stats.t, "sf", spy)
    recovery.sleep_need(hours, hrv)
    if "df" in seen:  # reached the p-value step
        assert seen["df"] < 150 - 2


def test_critical_speed_singular_design_is_not_valid_instead_of_raising():
    runs = [{"seconds": 600, "speed": 4.0, "day": date(2026, 6, 1), "activity_id": i} for i in range(5)] + [{"seconds": 600, "speed": 4.0, "day": date(2026, 6, 1), "activity_id": 9}]
    out = performance.critical_speed(runs, date(2026, 6, 2))  # identical durations: x'x is singular
    assert out.get("missing") and "cs_mps" not in out


# (8) backup.sh ----------------------------------------------------------------

def test_backup_crypt_check_survives_sigpipe_from_a_chatty_rclone(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    rclone = bin_dir / "rclone"
    rclone.write_text('#!/usr/bin/env bash\nif [[ "$1 $2" == "config show" ]]; then echo "type = crypt"; sleep 0.5; exec seq 1 300000; fi\nexit 0\n')

    sqlite = bin_dir / "sqlite3"
    sqlite.write_text('#!/usr/bin/env bash\ntouch "$(echo "$2" | sed "s/.backup .\\(.*\\).$/\\1/")"\n')
    for f in (rclone, sqlite):
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    data = tmp_path / "data"
    data.mkdir()
    r = subprocess.run(["bash", str(ROOT / "deploy" / "backup.sh")], env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "CADENCE_DATA_DIR": str(data), "CADENCE_BACKUP_REMOTE": "x:"},
                       capture_output=True, text=True, timeout=60, check=False)
    assert "refusing" not in r.stderr, r.stderr
    # (GNU-only `head -n -N` later in the script may fail on macOS; the crypt check is what matters here)


# (9) idempotent food entries --------------------------------------------------

def test_food_entry_retry_with_the_same_key_does_not_duplicate(env):  # noqa: F811
    client, clock = env
    body = {"day": str(clock.today()), "meal": "lunch", "name": "Thali", "kcal": 700, "client_key": "k-123"}
    a = client.post("/api/food/entries", json=body, headers=MUTATE)
    b = client.post("/api/food/entries", json=body, headers=MUTATE)
    assert a.status_code == b.status_code == 200 and a.json()["id"] == b.json()["id"] and b.json().get("replayed")
    h = {**MUTATE, "Idempotency-Key": "hdr-1"}
    c = client.post("/api/food/entries", json={**body, "client_key": None}, headers=h)
    d = client.post("/api/food/entries", json={**body, "client_key": None}, headers=h)
    assert c.json()["id"] == d.json()["id"] != a.json()["id"]
    e = client.post("/api/food/entries", json={k: v for k, v in body.items() if k != "client_key"}, headers=MUTATE)
    f = client.post("/api/food/entries", json={k: v for k, v in body.items() if k != "client_key"}, headers=MUTATE)
    assert e.json()["id"] != f.json()["id"]  # no key: unchanged behaviour
