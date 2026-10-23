from datetime import date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from tests.fake_garmin import FIRST, FIRST_HRV, HRV_MAX_DAYS, SUMMARY_MAX_DAYS, FakeGarmin
from cadence_app.db import make_engine, make_session_factory, upgrade_database
from cadence_app.garmin.client import GarminClient, GarminError, RateLimited
from cadence_app.garmin.engine import CORE_RANGE, SyncEngine, SyncManager
from cadence_app.models import Activity, DailyMetric, DatasetState, RawResponse, SyncRun, WeightReading

LIVE_HR_DAYS = 2  # today and yesterday, refreshed every sync for live strain

TODAY = date(2026, 10, 22)


class Clock:
    def __init__(self):
        self.day = TODAY

    def today(self) -> date:
        return self.day

    def now(self) -> datetime:
        return datetime.combine(self.day, datetime.min.time())


@pytest.fixture
def world(tmp_path):
    url = f"sqlite:///{tmp_path / 'db.sqlite3'}"
    upgrade_database(url)
    engine = make_engine(url)
    factory = make_session_factory(engine)
    fake = FakeGarmin(TODAY)
    clock = Clock()
    yield factory, fake, clock, tmp_path / "archive"
    engine.dispose()


def client_for(fake: FakeGarmin, sleeps: list | None = None) -> GarminClient:
    return GarminClient(
        "synthetic-key", fake.transport(), min_interval_s=0,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


def run_sync(factory, fake, clock, archive, deep=False):
    engine = SyncEngine(factory, archive, clock.today, clock.now)
    client = client_for(fake)
    try:
        engine.sync(client, include_deep=deep)
    finally:
        client.close()
    return engine


def counts(factory) -> tuple[int, int, int]:
    with factory() as s:
        return (
            s.scalar(select(func.count()).select_from(DailyMetric).where(DailyMetric.source_id == "garmin")),
            s.scalar(select(func.count()).select_from(Activity).where(Activity.source_id == "garmin")),
            s.scalar(select(func.count()).select_from(WeightReading).where(WeightReading.source_id == "garmin")),
        )


def test_full_history_backfill_reaches_first_day(world):
    factory, fake, clock, archive = world
    run_sync(factory, fake, clock, archive)

    with factory() as s:
        steps = s.scalars(
            select(DailyMetric.day).where(DailyMetric.metric == "steps").order_by(DailyMetric.day)
        ).all()
        assert steps[0] == FIRST and steps[-1] == TODAY
        assert len(steps) == (TODAY - FIRST).days + 1
        assert s.scalar(select(func.min(DailyMetric.day)).where(DailyMetric.metric == "hrv")) == FIRST_HRV
        assert s.scalar(select(func.min(Activity.local_date))) == FIRST
        assert s.scalar(select(func.min(WeightReading.muscle_mass_kg))) == 35.0
        for key in CORE_RANGE:
            assert s.get(DatasetState, ("garmin", key)).backfill_done, key
        assert s.get(DatasetState, ("garmin", "hrv")).window_days <= HRV_MAX_DAYS
        assert s.get(DatasetState, ("garmin", "daily_summaries")).window_days <= SUMMARY_MAX_DAYS
        assert s.get(DatasetState, ("garmin", "daily_summaries")).last_error is None
        activity = s.scalars(select(Activity)).first()
        assert activity.activity_type == "running" and activity.timezone == "UTC+05:30"


def test_second_sync_only_refreshes_recent_days(world):
    factory, fake, clock, archive = world
    run_sync(factory, fake, clock, archive)
    before = counts(factory)
    fake.calls.clear()

    run_sync(factory, fake, clock, archive)

    # One token + one provisional recent window per core dataset + today's and yesterday's all-day heart rate
    # (live strain); no history is re-fetched.
    assert fake.total <= 1 + len(CORE_RANGE) + LIVE_HR_DAYS
    assert counts(factory) == before
    with factory() as s:
        provisional = s.execute(
            select(RawResponse.dataset, RawResponse.window_start).where(RawResponse.final.is_(False))
        ).all()
    settled = TODAY - timedelta(days=3)
    assert all(ds == "profile" or ds == "hr_zones" or start > settled for ds, start in provisional)


def test_days_later_fetches_only_new_days(world):
    factory, fake, clock, archive = world
    run_sync(factory, fake, clock, archive)
    fake.calls.clear()
    clock.day = fake.today = TODAY + timedelta(days=5)

    run_sync(factory, fake, clock, archive)

    assert fake.total <= 1 + 2 * len(CORE_RANGE) + LIVE_HR_DAYS
    with factory() as s:
        assert s.scalar(select(func.max(DailyMetric.day)).where(DailyMetric.metric == "steps")) == clock.day


def test_rebuild_from_vault_makes_zero_api_calls(world):
    factory, fake, clock, archive = world
    run_sync(factory, fake, clock, archive)
    before = counts(factory)
    calls = fake.total

    engine = SyncEngine(factory, archive, clock.today, clock.now)
    replayed = engine.rebuild()

    assert replayed > 0
    assert fake.total == calls
    assert counts(factory) == before


def test_deep_sync_archives_fit_files_once(world):
    factory, fake, clock, archive = world
    run_sync(factory, fake, clock, archive, deep=True)
    fit_files = sorted((archive / "garmin" / "fit").glob("*.zip"))
    _, activities, _ = counts(factory)

    assert len(fit_files) == activities
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in fit_files)
    with factory() as s:
        assert s.get(DatasetState, ("garmin", "menstrual")).unsupported
        assert s.scalar(select(func.count()).select_from(DailyMetric).where(DailyMetric.metric == "fitness_age")) > 0

    fake.calls.clear()
    run_sync(factory, fake, clock, archive, deep=True)
    assert fake.calls["download-service:files"] == 0
    assert fake.calls["activity-service:activity"] == 0


def test_forbidden_dataset_is_marked_unavailable_and_others_continue(world):
    factory, fake, clock, archive = world
    fake.forbidden = {"/hrv-service/"}
    run_sync(factory, fake, clock, archive)
    with factory() as s:
        assert s.get(DatasetState, ("garmin", "hrv")).unsupported
        assert s.scalar(select(func.count()).select_from(DailyMetric).where(DailyMetric.metric == "steps")) > 0


def test_rate_limit_backs_off_then_pauses(world):
    factory, fake, clock, archive = world
    fake.fail_with = 429
    sleeps: list[float] = []
    client = client_for(fake, sleeps)
    with pytest.raises(RateLimited):
        client.fetch("/userprofile-service/userprofile/settings")
    assert sleeps and all(s >= 15 for s in sleeps)

    manager = SyncManager(factory, archive, clock.today, clock.now, lambda: client_for(fake))
    run_id = manager.start("quick", background=False)
    with factory() as s:
        run = s.get(SyncRun, run_id)
        assert run.status == "paused" and "rate" in run.error


def test_unauthorized_reauthenticates_once():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, text="a.b.c", headers={"content-type": "text/plain"})
        return httpx.Response(401 if seen.count(request.url.path) == 1 else 200, json={})

    client = GarminClient("k", httpx.MockTransport(handler), min_interval_s=0, sleep=lambda s: None)
    assert client.fetch("/x").status == 200
    assert sum(p.endswith("/token") for p in seen) == 2


def test_errors_never_leak_key():
    client = GarminClient(
        "synthetic-secret", httpx.MockTransport(lambda r: httpx.Response(500, text="synthetic-secret")),
        min_interval_s=0, max_retries=1, sleep=lambda s: None,
    )
    with pytest.raises(GarminError) as error:
        client.authenticate()
    assert "synthetic-secret" not in str(error.value)


def test_every_sync_refreshes_todays_all_day_heart_rate(world):
    factory, fake, clock, archive = world
    run_sync(factory, fake, clock, archive)
    with factory() as s:
        live = s.execute(
            select(RawResponse.window_start, RawResponse.final).where(RawResponse.dataset == "hr_intraday", RawResponse.window_start >= TODAY - timedelta(days=1))
        ).all()
    assert sorted(live) == [(TODAY - timedelta(days=1), False), (TODAY, False)]
