from __future__ import annotations

import json
import logging
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from cadence_app.garmin import vault
from cadence_app.garmin.client import AuthError, Fetched, GarminClient, GarminError, RateLimited, ServerError
from cadence_app.garmin.datasets import ACTIVITY, BY_KEY, DAILY, DATASETS, SINGLETON, Dataset, render
from cadence_app.garmin.normalize import has_normalizer, item_count, meaningful, normalize
from cadence_app.importer import Batch, MetricRecord, ensure_source, write_batch
from cadence_app.models import Activity, DailyMetric, DatasetState, RawResponse, Source, SyncRun, WeightReading

log = logging.getLogger(__name__)

SOURCE_ID = vault.SOURCE_ID
# Garmin keeps revising the last couple of days (late syncs, sleep scoring); older days are settled.
SETTLE_DAYS = 3
HISTORY_FLOOR = date(2005, 1, 1)
ANCHOR_EMPTY_STOP_DAYS = 700
EMPTY_STOP_DAYS = 400
ANCHOR_DATASETS = ("daily_summaries", "activities")
CORE_RANGE = ("daily_summaries", "activities", "sleep", "hrv", "weight", "weight_goals")
DEEP_RANGE = ("body_battery", "wellness_activities")
DEEP_ORDER = (
    "fitness_age", "menstrual", "activity_fit", "hrv_intraday", "spo2",
    "food_logs", "activity_detail", "activity_workouts", "hr_intraday",
)
ACTIVITY_ASSETS = ("activity_fit", "activity_detail", "activity_workouts")


class Cancelled(Exception):
    pass


class WindowRejected(Exception):
    def __init__(self, server: bool = False):
        super().__init__()
        # Server errors on big windows usually mean "too large"; at one day they mean "Garmin is struggling".
        self.server = server


class DatasetUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Got:
    raw: int = 0
    useful: int = 0
    earliest: date | None = None

    def __add__(self, other: Got) -> Got:
        dates = [d for d in (self.earliest, other.earliest) if d is not None]
        return Got(self.raw + other.raw, self.useful + other.useful, min(dates) if dates else None)


class SyncEngine:
    def __init__(
        self,
        factory: sessionmaker,
        archive_dir: Path,
        today: Callable[[], date],
        now: Callable[[], datetime],
        cancel: threading.Event | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
    ):
        self.factory = factory
        self.archive_dir = archive_dir
        self.today = today
        self.now = now
        self.cancel = cancel or threading.Event()
        self.on_progress = on_progress or (lambda message, requests, records: None)
        self.client: GarminClient | None = None
        self.records = 0
        self.message = ""
        self.failures: list[str] = []
        self._stored_keys: list[str] = []

    # ---- public entry points -------------------------------------------------

    def sync(self, client: GarminClient, include_deep: bool) -> None:
        self.client = client
        with self.factory() as session, session.begin():
            ensure_source(session, SOURCE_ID, "Garmin Connect", "garmin")
        try:
            for ds in DATASETS:
                if ds.kind == SINGLETON:
                    self._singleton(ds)
            ranges = CORE_RANGE + (DEEP_RANGE if include_deep else ())
            for key in ranges:
                self._guard(self._recent, BY_KEY[key])
            for key in ranges:
                self._guard(self._backfill, BY_KEY[key])
            self._refresh_derived()
            # Core history is in: dashboards switch to Garmin while the long deep archive continues.
            self._mark_synced()
            if include_deep:
                for key in DEEP_ORDER:
                    ds = BY_KEY[key]
                    self._guard(self._per_activity if ds.kind == ACTIVITY else self._per_day, ds)
        finally:
            self._refresh_derived()
            self._mark_synced()

    def fetch_activity(self, client: GarminClient, activity_id: str) -> list[str]:
        """Fetch any per-activity assets not yet in the vault; each is requested at most once ever."""
        self.client = client
        fetched = []
        for key in ACTIVITY_ASSETS:
            request_key = f"{key}:{activity_id}"
            with self.factory() as session:
                if vault.has_final(session, request_key):
                    continue
            ds = BY_KEY[key]
            path, params = render(ds, id=activity_id)
            self._fetch(ds, request_key, path, params, final=True, file_id=activity_id)
            fetched.append(key)
        return fetched

    def fetch_day(self, client: GarminClient, day: date, datasets: list[str]) -> list[str]:
        """Fetch per-day datasets for one date; settled days are stored as final and never re-requested."""
        self.client = client
        final = day <= self.today() - timedelta(days=SETTLE_DAYS)
        fetched = []
        for key in datasets:
            request_key = f"{key}:{day.isoformat()}"
            with self.factory() as session:
                if vault.has_final(session, request_key):
                    continue
            ds = BY_KEY[key]
            path, params = render(ds, day=day.isoformat())
            self._fetch(ds, request_key, path, params, final=final, window=(day, day))
            fetched.append(key)
        return fetched

    def rebuild(self) -> int:
        """Re-derive every normalized Garmin row from the vault. Makes zero API calls."""
        with self.factory() as session, session.begin():
            ensure_source(session, SOURCE_ID, "Garmin Connect", "garmin")
            for model in (DailyMetric, Activity, WeightReading):
                session.execute(delete(model).where(model.source_id == SOURCE_ID))
        replayed = 0
        with self.factory() as reader:
            for stored in vault.iter_stored(reader, {d.key for d in DATASETS}):
                self._check()
                day = stored.window_start if BY_KEY[stored.dataset].kind == DAILY else None
                batch = normalize(stored.dataset, stored.payload, day)
                with self.factory() as session, session.begin():
                    self.records += write_batch(session, SOURCE_ID, batch, self.now())
                replayed += 1
                if replayed % 50 == 0:
                    self._progress(f"Rebuilding from vault · {replayed} responses replayed")
        self._refresh_derived()
        self._mark_synced()
        self._progress(f"Rebuilt from {replayed} stored responses with zero API calls")
        return replayed

    # ---- dataset strategies --------------------------------------------------

    def _singleton(self, ds: Dataset) -> None:
        state = self._state(ds.key)
        if state.unsupported:
            return
        if state.last_fetched_at and self.now() - state.last_fetched_at < timedelta(days=ds.refresh_days):
            return
        self._guard(lambda d: self._fetch(d, ds.key, *render(d), final=False), ds)

    def _recent(self, ds: Dataset) -> None:
        state = self._state(ds.key)
        if state.unsupported:
            return
        today = self.today()
        settled = today - timedelta(days=SETTLE_DAYS)
        size = state.window_days or ds.window_days
        start = state.final_until + timedelta(days=1) if state.final_until else today - timedelta(days=size - 1)
        segments = [(start, settled, True), (max(start, settled + timedelta(days=1)), today, False)]
        found: date | None = None
        self._stored_keys = []
        for seg_start, seg_end, final in segments:
            cursor = seg_start
            while cursor <= seg_end:
                end = min(cursor + timedelta(days=size - 1), seg_end)
                try:
                    got = self._range(ds, cursor, end, final=final)
                except WindowRejected as rejected:
                    if size == 1:
                        if rejected.server:
                            raise GarminError(f"{ds.label} is temporarily failing on Garmin's side") from None
                        raise DatasetUnavailable(f"{ds.label} rejected a single-day request") from None
                    size = max(1, size // 2)
                    self._update(ds.key, window_days=size)
                    continue
                if got.earliest is not None:
                    found = min(filter(None, (found, got.earliest)))
                cursor = end + timedelta(days=1)
        with self.factory() as session, session.begin():
            vault.prune_provisional(session, ds.key, keep=set(self._stored_keys))
        oldest = state.oldest_with_data
        if found is not None and (oldest is None or found < oldest):
            oldest = found
        self._update(
            ds.key,
            final_until=settled,
            oldest_fetched=state.oldest_fetched or start,
            oldest_with_data=oldest,
        )

    def _backfill(self, ds: Dataset) -> None:
        while True:
            state = self._state(ds.key)
            if state.unsupported or state.backfill_done or state.oldest_fetched is None:
                return
            end = state.oldest_fetched - timedelta(days=1)
            if end < HISTORY_FLOOR:
                self._update(ds.key, backfill_done=True)
                return
            size = state.window_days or ds.window_days
            start = max(end - timedelta(days=size - 1), HISTORY_FLOOR)
            self._progress(f"Backfilling {ds.label} · {start:%b %Y}")
            try:
                got = self._range(ds, start, end, final=True)
            except WindowRejected as rejected:
                if size == 1:
                    if rejected.server:
                        raise GarminError(f"{ds.label} is temporarily failing on Garmin's side") from None
                    # Garmin rejects dates before the account existed: that is the history edge.
                    self._update(ds.key, backfill_done=True)
                    return
                self._update(ds.key, window_days=max(1, size // 2))
                continue
            span = (end - start).days + 1
            streak = 0 if got.useful else state.empty_days_streak + span
            oldest = got.earliest or state.oldest_with_data
            self._update(ds.key, oldest_fetched=start, empty_days_streak=streak, oldest_with_data=oldest)
            if self._backfill_finished(ds, start, streak, oldest):
                self._update(ds.key, backfill_done=True)
                return

    def _backfill_finished(self, ds: Dataset, start: date, streak: int, oldest: date | None) -> bool:
        if start <= HISTORY_FLOOR:
            return True
        if ds.key == "daily_summaries":
            return streak >= ANCHOR_EMPTY_STOP_DAYS
        anchor = self._anchor(exclude=ds.key)
        if ds.key in ANCHOR_DATASETS:
            return streak >= EMPTY_STOP_DAYS and (anchor is None or start < anchor)
        if anchor is not None and start < anchor - timedelta(days=31):
            return True
        if oldest is None:
            return streak >= ANCHOR_EMPTY_STOP_DAYS
        return streak >= EMPTY_STOP_DAYS

    def _per_activity(self, ds: Dataset) -> None:
        state = self._state(ds.key)
        if state.unsupported:
            return
        with self.factory() as session:
            done = self._keys(session, ds.key)
            ids = session.scalars(
                select(Activity.source_record_id)
                .where(Activity.source_id == SOURCE_ID)
                .order_by(Activity.start_time_utc.desc())
            ).all()
        pending = [i for i in ids if f"{ds.key}:{i}" not in done]
        for n, activity_id in enumerate(pending, 1):
            self._progress(f"{ds.label} · {n}/{len(pending)}")
            path, params = render(ds, id=activity_id)
            self._fetch(ds, f"{ds.key}:{activity_id}", path, params, final=True, file_id=activity_id)

    def _per_day(self, ds: Dataset) -> None:
        state = self._state(ds.key)
        if state.unsupported:
            return
        days = self._days_for(ds)
        with self.factory() as session:
            done = self._keys(session, ds.key)
        pending = [d for d in days if f"{ds.key}:{d.isoformat()}" not in done]
        for n, day in enumerate(pending, 1):
            self._progress(f"{ds.label} · {day:%d %b %Y} · {n}/{len(pending)}")
            path, params = render(ds, day=day.isoformat())
            useful = self._fetch(
                ds, f"{ds.key}:{day.isoformat()}", path, params, final=True, window=(day, day)
            ).useful
            if ds.probe and n == 1 and not useful:
                self._update(ds.key, unsupported=True, last_error="No data on this account")
                return

    # ---- helpers -------------------------------------------------------------

    def _days_for(self, ds: Dataset) -> list[date]:
        settled = self.today() - timedelta(days=SETTLE_DAYS)
        if ds.selector and ds.selector[0] == "metric":
            with self.factory() as session:
                return list(
                    session.scalars(
                        select(DailyMetric.day)
                        .where(
                            DailyMetric.source_id == SOURCE_ID,
                            DailyMetric.metric == ds.selector[1],
                            DailyMetric.day <= settled,
                        )
                        .order_by(DailyMetric.day.desc())
                    ).all()
                )
        anchor = self._anchor()
        if anchor is None:
            return []
        step_monthly = ds.selector[0] == "monthly"
        days: list[date] = []
        cursor = settled
        while cursor >= anchor:
            days.append(cursor)
            if step_monthly:
                cursor = (cursor.replace(day=1) - timedelta(days=1)).replace(day=1)
            else:
                cursor -= timedelta(days=7)
        return days

    def _range(self, ds: Dataset, start: date, end: date, *, final: bool) -> Got:
        """Fetch one window. Raises WindowRejected on HTTP 400 so callers can shrink the window."""
        if ds.page_size:
            return self._paged(ds, start, end, final=final)
        path, params = render(ds, start=start.isoformat(), end=end.isoformat())
        return self._fetch(
            ds, f"{ds.key}:{start}:{end}", path, params, final=final, window=(start, end), strict=True
        )

    def _paged(self, ds: Dataset, start: date, end: date, *, final: bool) -> Got:
        total = Got()
        offset = 0
        while True:
            path, params = render(
                ds, start=start.isoformat(), end=end.isoformat(), offset=str(offset), limit=str(ds.page_size)
            )
            got = self._fetch(
                ds, f"{ds.key}:{start}:{end}:{offset}", path, params,
                final=final, window=(start, end) if offset == 0 else (None, None), strict=True,
            )
            total += got
            if got.raw < ds.page_size:
                return total
            offset += ds.page_size

    def _fetch(
        self,
        ds: Dataset,
        key: str,
        path: str,
        params: dict,
        *,
        final: bool,
        window: tuple[date | None, date | None] = (None, None),
        strict: bool = False,
        file_id: str | None = None,
    ) -> Got:
        self._check()
        try:
            fetched: Fetched = self.client.fetch(path, params)
        except ServerError:
            if strict:
                raise WindowRejected(server=True) from None
            raise
        if fetched.status == 400 and strict:
            raise WindowRejected()
        if fetched.status in (401, 403):
            raise DatasetUnavailable(f"{ds.label} is not available to this key (HTTP {fetched.status})")
        if fetched.status not in (200, 204, 400, 404):
            raise GarminError(f"{ds.label} returned HTTP {fetched.status}")

        payload = None
        file_path = None
        error = None
        if fetched.status == 200 and fetched.body:
            if ds.binary:
                if zipfile.is_zipfile(BytesIO(fetched.body)):
                    file_path = vault.write_file(
                        self.archive_dir, f"garmin/fit/{file_id}.zip", fetched.body
                    )
                else:
                    error = "Activity file was not a ZIP archive"
            else:
                try:
                    payload = json.loads(fetched.body)
                except ValueError:
                    error = "Response was not JSON"
        count = 1 if file_path else item_count(payload)
        batch = normalize(ds.key, payload, window[0] if ds.kind == DAILY else None)
        useful = len(batch) if has_normalizer(ds.key) else (count if meaningful(payload) or file_path else 0)
        dates = [m.day for m in batch.metrics] + [a.local_date for a in batch.activities] + [
            w.local_date for w in batch.weights
        ]
        earliest = min(dates) if dates else (window[0] if useful else None)
        now = self.now()
        with self.factory() as session, session.begin():
            vault.store(
                session, dataset=ds.key, request_key=key[:160], path=path, params=params,
                status=fetched.status, content_type=fetched.content_type, body=fetched.body,
                fetched_at=now, final=final, item_count=count, window=window, file_path=file_path,
            )
            self.records += write_batch(session, SOURCE_ID, batch, now)
            state = self._state_in(session, ds.key)
            state.calls += 1
            state.last_fetched_at = now
            state.last_error = error
            if useful and window[1] is not None:
                state.newest_with_data = max(filter(None, (state.newest_with_data, window[1])))
        self._stored_keys.append(key[:160])
        self._progress(self.message)
        return Got(count, useful, earliest)

    def _guard(self, step: Callable[[Dataset], object], ds: Dataset) -> None:
        try:
            step(ds)
        except DatasetUnavailable as exc:
            self._update(ds.key, unsupported=True, last_error=str(exc))
        except (Cancelled, RateLimited, AuthError):
            raise
        except GarminError as exc:
            # One failing dataset should not stall the rest; it resumes on the next run.
            self.failures.append(ds.label)
            self._update(ds.key, last_error=str(exc))

    def _refresh_derived(self) -> None:
        with self.factory() as session, session.begin():
            rows = session.execute(
                select(Activity.local_date, func.sum(Activity.training_load), func.max(Activity.vo2max))
                .where(Activity.source_id == SOURCE_ID)
                .group_by(Activity.local_date)
            ).all()
            batch = Batch()
            for day, load, vo2 in rows:
                if load is not None:
                    batch.metrics.append(MetricRecord(day, "training_load", round(load, 1), "load"))
                if vo2 is not None:
                    batch.metrics.append(MetricRecord(day, "vo2max", vo2, "ml/kg/min"))
            write_batch(session, SOURCE_ID, batch, self.now())

    def _mark_synced(self) -> None:
        with self.factory() as session, session.begin():
            has_data = session.scalar(
                select(func.count()).select_from(DailyMetric).where(DailyMetric.source_id == SOURCE_ID)
            ) or session.scalar(
                select(func.count()).select_from(Activity).where(Activity.source_id == SOURCE_ID)
            )
            source = session.get(Source, SOURCE_ID)
            if source is not None and has_data:
                source.last_synced_at = self.now()

    def _anchor(self, exclude: str | None = None) -> date | None:
        with self.factory() as session:
            values = [
                session.get(DatasetState, (SOURCE_ID, key))
                for key in ANCHOR_DATASETS
                if key != exclude
            ]
        dates = [s.oldest_with_data for s in values if s is not None and s.oldest_with_data]
        return min(dates) if dates else None

    def _keys(self, session: Session, dataset: str) -> set[str]:
        return set(
            session.scalars(
                select(RawResponse.request_key).where(
                    RawResponse.source_id == SOURCE_ID,
                    RawResponse.dataset == dataset,
                    RawResponse.final.is_(True),
                )
            ).all()
        )

    def _state(self, dataset: str) -> DatasetState:
        with self.factory() as session, session.begin():
            state = self._state_in(session, dataset)
            session.flush()
            session.expunge(state)
            return state

    def _state_in(self, session: Session, dataset: str) -> DatasetState:
        state = session.get(DatasetState, (SOURCE_ID, dataset))
        if state is None:
            state = DatasetState(
                source_id=SOURCE_ID, dataset=dataset, empty_days_streak=0,
                backfill_done=False, unsupported=False, calls=0,
            )
            session.add(state)
        return state

    def _update(self, dataset: str, **values) -> None:
        with self.factory() as session, session.begin():
            state = self._state_in(session, dataset)
            for key, value in values.items():
                setattr(state, key, value)

    def _check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def _progress(self, message: str) -> None:
        self.message = message
        requests = self.client.requests_made if self.client else 0
        self.on_progress(message, requests, self.records)


class SyncManager:
    """Runs at most one Garmin job at a time in a background thread."""

    def __init__(
        self,
        factory: sessionmaker,
        archive_dir: Path,
        today: Callable[[], date],
        now: Callable[[], datetime],
        client_factory: Callable[[], GarminClient],
    ):
        self.factory = factory
        self.archive_dir = archive_dir
        self.today = today
        self.now = now
        self.client_factory = client_factory
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._on_demand_lock = threading.Lock()
        self._on_demand: GarminClient | None = None

    def fetch_activity(self, activity_id: str) -> list[str]:
        with self._on_demand_lock:
            if self._on_demand is None:
                self._on_demand = self.client_factory()
            engine = SyncEngine(self.factory, self.archive_dir, self.today, self.now)
            return engine.fetch_activity(self._on_demand, activity_id)

    def fetch_day(self, day: date, datasets: list[str]) -> list[str]:
        with self._on_demand_lock:
            if self._on_demand is None:
                self._on_demand = self.client_factory()
            engine = SyncEngine(self.factory, self.archive_dir, self.today, self.now)
            return engine.fetch_day(self._on_demand, day, datasets)

    def close(self) -> None:
        self.stop()
        with self._on_demand_lock:
            if self._on_demand is not None:
                self._on_demand.close()
                self._on_demand = None

    def recover_interrupted(self) -> None:
        with self.factory() as session, session.begin():
            for run in session.scalars(
                select(SyncRun).where(SyncRun.source_id == SOURCE_ID, SyncRun.status == "running")
            ):
                run.status = "interrupted"
                run.finished_at = run.finished_at or self.now()

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, mode: str, background: bool = True) -> int:
        with self._lock:
            if self.busy:
                raise RuntimeError("A Garmin job is already running")
            with self.factory() as session, session.begin():
                ensure_source(session, SOURCE_ID, "Garmin Connect", "garmin")
                run = SyncRun(
                    source_id=SOURCE_ID, started_at=self.now(), status="running",
                    records_written=0, mode=mode, requests_made=0, cancel_requested=False,
                    message="Starting…",
                )
                session.add(run)
                session.flush()
                run_id = run.id
            self._cancel.clear()
            if background:
                self._thread = threading.Thread(target=self._execute, args=(run_id, mode), daemon=True)
                self._thread.start()
            else:
                self._execute(run_id, mode)
            return run_id

    def stop(self) -> bool:
        if not self.busy:
            return False
        self._cancel.set()
        with self.factory() as session, session.begin():
            for run in session.scalars(
                select(SyncRun).where(SyncRun.source_id == SOURCE_ID, SyncRun.status == "running")
            ):
                run.cancel_requested = True
        return True

    def _execute(self, run_id: int, mode: str) -> None:
        def progress(message: str, requests: int, records: int) -> None:
            with self.factory() as session, session.begin():
                run = session.get(SyncRun, run_id)
                run.message = message
                run.requests_made = requests
                run.records_written = records

        engine = SyncEngine(
            self.factory, self.archive_dir, self.today, self.now, self._cancel, progress
        )
        client = None
        status, error = "succeeded", None
        try:
            if mode == "rebuild":
                engine.rebuild()
            else:
                client = self.client_factory()
                engine.sync(client, include_deep=mode == "full")
                if engine.failures:
                    status = "partial"
                    error = "Retry later: " + ", ".join(dict.fromkeys(engine.failures))
        except Cancelled:
            status = "stopped"
        except RateLimited as exc:
            status, error = "paused", str(exc)
        except GarminError as exc:
            status, error = "failed", str(exc)
        except Exception as exc:  # pylint: disable=broad-exception-caught  # job boundary: report safely
            log.exception("Garmin job failed")
            status, error = "failed", f"Unexpected local error ({type(exc).__name__})"
        finally:
            if client is not None:
                client.close()
            with self.factory() as session, session.begin():
                run = session.get(SyncRun, run_id)
                run.status = status
                run.error = error
                run.finished_at = self.now()
                run.requests_made = client.requests_made if client else 0
                run.records_written = engine.records
                if status == "succeeded":
                    run.message = (
                        engine.message if mode == "rebuild" else "Up to date"
                    )
