from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta
from statistics import fmean
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cadence_app import backup, days, goal_store, journal, ocr, planner_store, profile as profile_store, push, strength, weather, weightlog
from cadence_app.analytics import accuracy as accuracy_analytics
from cadence_app.analytics import banister as banister_analytics
from cadence_app.analytics import channels as channels_analytics
from cadence_app.analytics import exercises
from cadence_app.analytics import goals as goal_analytics
from cadence_app.analytics import routes as route_analytics
from cadence_app.analytics import whatif as whatif_analytics
from cadence_app.analytics import body as body_analytics
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import planner as session_planner
from cadence_app.analytics import review as reviews
from cadence_app.activity_types import activity_family
from cadence_app.analytics import insights as insights_service
from cadence_app.analytics import notes as coach_notes
from cadence_app.analytics import score as cadence_score
from cadence_app.analytics import training_log
from cadence_app.analytics import weight as weight_analytics
from cadence_app.config import Settings, load_settings
from cadence_app.credentials import credential_status
from cadence_app.db import make_engine, make_session_factory, upgrade_database
from cadence_app.garmin import fit, vault
from cadence_app.garmin.client import GarminClient, GarminError
from cadence_app.garmin.datasets import BY_KEY, DATASETS
from cadence_app.garmin.engine import SyncManager
from cadence_app.models import (
    Activity,
    AppSetting,
    DailyMetric,
    DatasetState,
    ReminderDismissal,
    Source,
    SyncRun,
    WeightReading,
)
from cadence_app.models import RawResponse as vault_model
from cadence_app.secrets import read_env_file
from cadence_app.share import ShareServer
from cadence_app.sync import latest_runs, run_demo_sync, utcnow

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# higher_is_better: None means context-dependent.
METRICS: dict[str, dict] = {
    "hrv": {"label": "HRV", "unit": "ms", "higher_is_better": True},
    "hrv_weekly": {"label": "HRV 7-day", "unit": "ms", "higher_is_better": True},
    "resting_hr": {"label": "Resting HR", "unit": "bpm", "higher_is_better": False},
    "sleep_hours": {"label": "Sleep", "unit": "h", "higher_is_better": True},
    "sleep_score": {"label": "Sleep score", "unit": "", "higher_is_better": True},
    "deep_sleep_h": {"label": "Deep sleep", "unit": "h", "higher_is_better": True},
    "rem_sleep_h": {"label": "REM sleep", "unit": "h", "higher_is_better": True},
    "sleep_stress": {"label": "Sleep stress", "unit": "", "higher_is_better": False},
    "stress": {"label": "Stress", "unit": "", "higher_is_better": False},
    "body_battery": {"label": "Body Battery", "unit": "", "higher_is_better": True},
    "body_battery_low": {"label": "Body Battery low", "unit": "", "higher_is_better": True},
    "body_battery_now": {"label": "Body Battery now", "unit": "", "higher_is_better": True},
    "steps": {"label": "Steps", "unit": "", "higher_is_better": True},
    "floors": {"label": "Floors", "unit": "", "higher_is_better": True},
    "intensity_minutes": {"label": "Intensity", "unit": "min", "higher_is_better": True},
    "active_calories": {"label": "Active calories", "unit": "kcal", "higher_is_better": None},
    "total_calories": {"label": "Total calories", "unit": "kcal", "higher_is_better": None},
    "calories_consumed": {"label": "Calories eaten", "unit": "kcal", "higher_is_better": None},
    "respiration": {"label": "Respiration", "unit": "brpm", "higher_is_better": None},
    "spo2": {"label": "SpO₂", "unit": "%", "higher_is_better": True},
    "hydration_ml": {"label": "Hydration", "unit": "ml", "higher_is_better": True},
    "training_load": {"label": "Training load", "unit": "", "higher_is_better": None},
    "vo2max": {"label": "VO₂ max", "unit": "", "higher_is_better": True},
    "fitness_age": {"label": "Fitness age", "unit": "yrs", "higher_is_better": False},
}
OVERVIEW_METRICS = [
    "hrv", "resting_hr", "sleep_hours", "sleep_score", "body_battery", "stress",
    "steps", "intensity_minutes", "vo2max",
]


class Clock:
    def today(self) -> date:
        return date.today()

    def now(self) -> datetime:
        return utcnow()


class DismissRequest(BaseModel):
    key: str = Field(max_length=64)


class WeightGoalRequest(BaseModel):
    goal_kg: float | None = Field(default=None, ge=30, le=300)


RaceDate = date  # the request field is called `date`, which would shadow the type inside the model


class TrainingGoalRequest(BaseModel):
    distance: Literal["5k", "10k", "half", "marathon"] | None = None
    date: RaceDate | None = None
    target_s: int | None = Field(default=None, ge=600, le=8 * 3600)


class GoalRequest(BaseModel):
    kind: Literal["race", "performance", "distance", "weight"]
    sport: Literal["run", "ride", "swim"] | None = None
    title: str | None = Field(default=None, max_length=120)
    date: RaceDate | None = None
    distance_m: float | None = Field(default=None, gt=0)
    label: str | None = Field(default=None, max_length=40)
    target_s: int | None = Field(default=None, ge=60, le=72 * 3600)
    speed_kmh: float | None = Field(default=None, gt=0, le=100)
    target_kg: float | None = Field(default=None, ge=30, le=300)


class GoalPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    date: RaceDate | None = None
    distance_m: float | None = Field(default=None, gt=0)
    label: str | None = Field(default=None, max_length=40)
    target_s: int | None = Field(default=None, ge=60, le=72 * 3600)
    speed_kmh: float | None = Field(default=None, gt=0, le=100)
    target_kg: float | None = Field(default=None, ge=30, le=300)
    status: Literal["active", "achieved", "dropped"] | None = None


class JournalDayRequest(BaseModel):
    answers: dict[str, float] = Field(default_factory=dict, max_length=60)


class BehaviourCreate(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    question: str = Field(default="", max_length=150)
    kind: Literal["yes_no", "count"] = "yes_no"
    unit: str = Field(default="", max_length=16)


class BehaviourUpdate(BaseModel):
    active: bool | None = None
    label: str | None = Field(default=None, min_length=1, max_length=60)
    question: str | None = Field(default=None, min_length=1, max_length=150)


class PlanRequest(BaseModel):
    day: RaceDate
    sport: Literal["run", "ride", "swim", "strength"]
    option_key: str = Field(max_length=48)
    strength_text: str | None = Field(default=None, max_length=4000)


class WeatherSetting(BaseModel):
    enabled: bool


class WeightEntryRequest(BaseModel):
    day: date
    weight_kg: float = Field(ge=weightlog.MIN_KG, le=weightlog.MAX_KG)


class ProfileRequest(BaseModel):
    height_cm: float = Field(ge=profile_store.MIN_HEIGHT_CM, le=profile_store.MAX_HEIGHT_CM)
    birth_date: RaceDate
    sex: Literal["male", "female"]


class StrengthText(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    template: str | None = Field(default=None, max_length=80)


class GarminSyncRequest(BaseModel):
    mode: Literal["quick", "full"] = "full"


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=256)
    auth: str = Field(min_length=8, max_length=64)


class PushSubscribeRequest(BaseModel):
    endpoint: str = Field(max_length=1024)
    keys: PushKeys
    label: str = Field(default="", max_length=120)


class PushEndpointRequest(BaseModel):
    endpoint: str = Field(max_length=1024)


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    garmin_client_factory: Callable[[str], GarminClient] | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    clock = clock or Clock()
    settings.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    upgrade_database(settings.database_url)
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    make_client = garmin_client_factory or (
        lambda key: GarminClient(key, min_interval_s=settings.garmin_min_interval_s)
    )
    garmin_jobs = SyncManager(
        factory,
        settings.archive_dir,
        clock.today,
        clock.now,
        lambda: make_client(read_env_file(settings.secrets_file).get("GARMIN_API_KEY", "")),
    )
    garmin_jobs.recover_interrupted()
    analysis = insights_service.AnalysisWorker(
        factory, settings.archive_dir, (lambda: weather.refresh(factory, clock.today(), clock.now())) if settings.weather else None
    )

    def current_credential():
        return credential_status(read_env_file(settings.secrets_file), clock.today())

    def active_source() -> str:
        with factory() as session:
            return _active_source(session)

    sender = push.PushSender(factory, settings.data_dir / "push-vapid.pem", settings.push_contact, clock.now)
    notifier = push.Notifier(factory, sender, active_source, current_credential)
    scheduler = push.Scheduler(
        factory, notifier, garmin_jobs.start, lambda: garmin_jobs.busy,
        lambda: current_credential().configured, clock.now, settings.sync_every_h,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        share.resume()
        if settings.scheduler:
            scheduler.start()
        yield
        scheduler.stop()
        share.stop(remember=False)
        analysis.stop()
        garmin_jobs.close()
        engine.dispose()

    app = FastAPI(title="Cadence", lifespan=lifespan, docs_url=None, redoc_url=None)
    share = ShareServer(app, factory, settings.web_dist, settings.share_port)
    app.state.share = share
    app.state.notifier, app.state.scheduler = notifier, scheduler
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    @app.middleware("http")
    async def guard_mutations(request: Request, call_next: Callable):
        # Custom header forces a CORS preflight, which this API never approves cross-origin.
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if request.headers.get("x-cadence-request") != "1" or (
                origin is not None and origin not in settings.allowed_origins
            ):
                return JSONResponse({"detail": "Request rejected"}, status_code=403)
        return await call_next(request)

    def get_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/push")
    def push_status() -> dict:
        return {
            "public_key": sender.public_key,
            "devices": push.devices(factory),
            "prefs": push.get_prefs(factory),
            "labels": push.PREFS,
            "recent": notifier.recent(),
            "scheduler": settings.scheduler,
            "sync_every_h": settings.sync_every_h,
        }

    @app.post("/api/push/subscribe")
    def push_subscribe(body: PushSubscribeRequest) -> dict:
        if not push.allowed_endpoint(body.endpoint):
            raise HTTPException(400, "Unsupported push service")
        push.subscribe(factory, body.endpoint, body.keys.p256dh, body.keys.auth, body.label or "Device", clock.now())
        return {"devices": push.devices(factory)}

    @app.post("/api/push/unsubscribe")
    def push_unsubscribe(body: PushEndpointRequest) -> dict:
        push.unsubscribe(factory, body.endpoint)
        return {"devices": push.devices(factory)}

    @app.post("/api/push/test")
    def push_test() -> dict:
        delivered = sender.broadcast("Cadence is connected", "Notifications from your coach will arrive here.", "/settings", tag="test")
        return {"delivered": delivered, "devices": push.devices(factory)}

    @app.put("/api/push/prefs")
    def push_prefs(body: dict[str, bool]) -> dict:
        return {"prefs": push.set_prefs(factory, body)}

    @app.get("/api/share")
    def share_status() -> dict:
        return share.status()

    @app.post("/api/share/start")
    def share_start() -> dict:
        try:
            share.start()
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from None
        return share.status()

    @app.post("/api/share/stop")
    def share_stop() -> dict:
        share.stop()
        return share.status()

    @app.post("/api/share/reset")
    def share_reset() -> dict:
        share.reset()
        return share.status()

    @app.get("/api/credentials/status")
    def credentials(session: Session = Depends(get_session)) -> dict:
        status = current_credential()
        key = status.reminder_key
        dismissed = (
            key is not None
            and status.level != "expired"
            and session.get(ReminderDismissal, key) is not None
        )
        return {
            "configured": status.configured,
            "expires_on": status.expires_on,
            "days_remaining": status.days_remaining,
            "level": status.level,
            "active_threshold": status.active_threshold,
            "thresholds": list(status.thresholds),
            "reminder_dates": list(status.reminder_dates),
            "reminder_key": key,
            "dismissed": dismissed,
            "today": clock.today(),
        }

    @app.post("/api/credentials/reminders/dismiss")
    def dismiss(body: DismissRequest, session: Session = Depends(get_session)) -> dict:
        status = current_credential()
        if status.reminder_key is None or body.key != status.reminder_key:
            raise HTTPException(409, "Reminder is no longer current")
        if status.level == "expired":
            raise HTTPException(409, "Expired credentials cannot be dismissed")
        if session.get(ReminderDismissal, body.key) is None:
            session.add(ReminderDismissal(key=body.key, dismissed_at=clock.now()))
            session.commit()
        return {"dismissed": True}

    @app.get("/api/sources")
    def sources(session: Session = Depends(get_session)) -> list[dict]:
        demo = session.get(Source, "demo")
        demo_rows = session.scalar(
            select(func.count()).select_from(DailyMetric).where(DailyMetric.source_id == "demo")
        )
        cred = current_credential()
        garmin = session.get(Source, "garmin")
        return [
            {
                "id": "demo",
                "name": "Demo data",
                "status": "ready" if demo_rows else "empty",
                "last_synced_at": demo.last_synced_at if demo else None,
                "detail": "Synthetic, deterministic history for building and testing features.",
            },
            {
                "id": "garmin",
                "name": "Garmin Connect",
                "status": "ready" if garmin and garmin.last_synced_at else "not_synced" if cred.configured else "not_configured",
                "last_synced_at": garmin.last_synced_at if garmin else None,
                "detail": "Full-history sync into a local vault. Every response is stored, so history is fetched once.",
            },
        ]

    @app.post("/api/sync/demo")
    def sync_demo() -> dict:
        run = run_demo_sync(factory, clock.today(), clock.now())
        return _run_dict(run)

    @app.post("/api/garmin/sync", status_code=202)
    def garmin_sync(body: GarminSyncRequest) -> dict:
        if not current_credential().configured:
            raise HTTPException(400, "No Garmin credential is configured")
        try:
            run_id = garmin_jobs.start(body.mode)
        except RuntimeError:
            raise HTTPException(409, "A Garmin job is already running") from None
        return {"run_id": run_id}

    @app.post("/api/garmin/rebuild", status_code=202)
    def garmin_rebuild() -> dict:
        try:
            return {"run_id": garmin_jobs.start("rebuild")}
        except RuntimeError:
            raise HTTPException(409, "A Garmin job is already running") from None

    @app.post("/api/garmin/stop")
    def garmin_stop() -> dict:
        return {"stopping": garmin_jobs.stop()}

    @app.get("/api/garmin/status")
    def garmin_status(session: Session = Depends(get_session)) -> dict:
        states = {
            s.dataset: s
            for s in session.scalars(select(DatasetState).where(DatasetState.source_id == "garmin"))
        }
        counts = dict(
            session.execute(
                select(vault_model.dataset, func.count())
                .where(vault_model.source_id == "garmin")
                .group_by(vault_model.dataset)
            ).all()
        )
        stored = dict(
            session.execute(
                select(vault_model.dataset, func.coalesce(func.sum(vault_model.stored_bytes), 0))
                .where(vault_model.source_id == "garmin")
                .group_by(vault_model.dataset)
            ).all()
        )
        latest = session.scalar(
            select(SyncRun)
            .where(SyncRun.source_id == "garmin", SyncRun.mode.is_not(None))
            .order_by(SyncRun.id.desc())
            .limit(1)
        )
        totals = {
            "activities": session.scalar(
                select(func.count()).select_from(Activity).where(Activity.source_id == "garmin")
            ),
            "days": session.scalar(
                select(func.count(func.distinct(DailyMetric.day))).where(DailyMetric.source_id == "garmin")
            ),
            "metrics": session.scalar(
                select(func.count()).select_from(DailyMetric).where(DailyMetric.source_id == "garmin")
            ),
            "weigh_ins": session.scalar(
                select(func.count()).select_from(WeightReading).where(WeightReading.source_id == "garmin")
            ),
            "first_day": session.scalar(
                select(func.min(DailyMetric.day)).where(DailyMetric.source_id == "garmin")
            ),
            "api_calls": sum(s.calls for s in states.values()),
        }
        datasets = []
        for ds in DATASETS:
            s = states.get(ds.key)
            if s is None:
                status = "pending"
            elif s.unsupported:
                status = "unavailable"
            elif ds.kind == "range":
                status = "complete" if s.backfill_done else "backfilling"
            else:
                status = "synced" if s.calls else "pending"
            datasets.append(
                {
                    "key": ds.key,
                    "label": ds.label,
                    "tier": ds.tier,
                    "kind": ds.kind,
                    "status": status,
                    "oldest": (s.oldest_with_data if s else None),
                    "covered_from": (s.oldest_fetched if s else None),
                    "calls": s.calls if s else 0,
                    "responses": counts.get(ds.key, 0),
                    "stored_bytes": stored.get(ds.key, 0),
                    "last_fetched_at": s.last_fetched_at if s else None,
                    "error": s.last_error if s else None,
                }
            )
        return {
            "busy": garmin_jobs.busy,
            "run": _run_dict(latest) if latest else None,
            "vault": vault.stats(session),
            "totals": totals,
            "datasets": datasets,
        }

    @app.get("/api/sync/runs")
    def sync_runs(session: Session = Depends(get_session)) -> list[dict]:
        return [_run_dict(r) for r in latest_runs(session)]

    @app.delete("/api/sources/demo/data")
    def delete_demo(session: Session = Depends(get_session)) -> dict:
        for model in (DailyMetric, Activity, WeightReading, SyncRun):
            session.execute(delete(model).where(model.source_id == "demo"))
        session.execute(delete(Source).where(Source.id == "demo"))
        session.commit()
        return {"deleted": True}

    @app.get("/api/overview")
    def overview(session: Session = Depends(get_session)) -> dict:
        source_id = _active_source(session)
        latest_day = session.scalar(select(func.max(DailyMetric.day)).where(DailyMetric.source_id == source_id))
        if latest_day is None:
            return {"has_data": False}
        since = latest_day - timedelta(days=66)
        rows = session.execute(
            select(DailyMetric.metric, DailyMetric.day, DailyMetric.value)
            .where(DailyMetric.source_id == source_id, DailyMetric.day > since, DailyMetric.metric.in_(OVERVIEW_METRICS))
            .order_by(DailyMetric.day)
        ).all()
        series: dict[str, list[tuple[date, float]]] = {m: [] for m in OVERVIEW_METRICS}
        for metric, day, value in rows:
            series[metric].append((day, value))

        metrics = []
        for metric in OVERVIEW_METRICS:
            points = series[metric]
            if not points:
                continue
            recent = [v for d, v in points if (latest_day - d).days < 7]
            baseline = [v for d, v in points if 7 <= (latest_day - d).days < 67]
            recent_mean = fmean(recent) if recent else None
            baseline_mean = fmean(baseline) if len(baseline) >= 14 else None
            delta_pct = (
                (recent_mean - baseline_mean) / baseline_mean * 100
                if recent_mean is not None and baseline_mean
                else None
            )
            metrics.append(
                {
                    "metric": metric,
                    **METRICS[metric],
                    "latest": points[-1][1],
                    "latest_day": points[-1][0],
                    "recent_mean": recent_mean,
                    "baseline_mean": baseline_mean,
                    "delta_pct": delta_pct,
                    "spark": [{"day": d, "value": v} for d, v in points if (latest_day - d).days < 30],
                }
            )

        week_start = latest_day - timedelta(days=6)
        week = session.execute(
            select(
                func.count(Activity.id),
                func.coalesce(func.sum(Activity.duration_s), 0),
                func.coalesce(func.sum(Activity.distance_m), 0),
                func.coalesce(func.sum(Activity.training_load), 0),
            ).where(Activity.source_id == source_id, Activity.local_date >= week_start, Activity.local_date <= latest_day)
        ).one()
        recent_activities = session.scalars(
            select(Activity).where(Activity.source_id == source_id).order_by(Activity.start_time_utc.desc()).limit(5)
        ).all()
        ctx = insights_service.context(session, source_id, clock.today())
        verdicts = coach_notes.verdicts(ctx)
        if source_id == "garmin" and (insights_service.pending_strain_days(session) or (settings.weather and weather.pending(session, clock.now()))):
            analysis.kick()  # strain history and weather are cached in the background

        weight = _weight_summary(session, clock.today())
        journal.ensure_catalogue(session, clock.now())
        today_plans = planner_store.reconcile(session, source_id, planner_store.listing(session, clock.today(), clock.today()), clock.today(), clock.now())
        return {
            "has_data": True,
            "planned_today": today_plans,
            "journal": {**journal.checkin(session, clock.today()),
                        "behaviours": [journal.behaviour_dict(b) for b in journal.catalogue(session, include_inactive=False)]},
            "source_id": source_id,
            "as_of": latest_day,
            "coach": coach_notes.brief(ctx) if ctx else None,
            "score": cadence_score.summary(ctx) if ctx else None,
            "metrics": metrics,
            "week": {
                "start": week_start,
                "activities": week[0],
                "duration_s": week[1],
                "distance_m": week[2],
                "training_load": week[3],
            },
            "recent_activities": [_activity_dict(a, verdicts) for a in recent_activities],
            "weight": {
                "latest_trend_kg": weight.latest_trend_kg,
                "rate_kg_per_week": weight.rate_kg_per_week,
                "latest_reading": asdict(weight.points[-1]) if weight.points else None,
                "weighed_today": bool(weight.points and weight.points[-1].day == clock.today()),
                "goal_kg": _goal(session),
                "projection": asdict(weight.projection) if weight.projection else None,
                "spark": [
                    {"day": p.day, "value": p.trend_kg} for p in weight.points[-60:]
                ],
            },
        }

    @app.get("/api/metrics/{metric}")
    def metric_series(
        metric: str, days: int = Query(90, ge=7, le=3650), session: Session = Depends(get_session)
    ) -> dict:
        if metric not in METRICS:
            raise HTTPException(404, "Unknown metric")
        source_id = _active_source(session)
        latest_day = session.scalar(select(func.max(DailyMetric.day)).where(DailyMetric.source_id == source_id))
        if latest_day is None:
            return {"metric": metric, **METRICS[metric], "points": []}
        rows = session.execute(
            select(DailyMetric.day, DailyMetric.value)
            .where(DailyMetric.source_id == source_id, DailyMetric.metric == metric, DailyMetric.day > latest_day - timedelta(days=days))
            .order_by(DailyMetric.day)
        ).all()
        return {
            "metric": metric,
            **METRICS[metric],
            "points": [{"day": d, "value": v} for d, v in rows],
        }

    @app.get("/api/activities")
    def activities(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        family: str | None = Query(None, max_length=16),
        session: Session = Depends(get_session),
    ) -> dict:
        source_id = _active_source(session)
        rows = session.scalars(
            select(Activity)
            .where(Activity.source_id == source_id)
            .order_by(Activity.start_time_utc.desc())
        ).all()
        counts: dict[str, int] = {}
        for a in rows:
            fam = activity_family(a.activity_type)
            counts[fam] = counts.get(fam, 0) + 1
        if family:
            rows = [a for a in rows if activity_family(a.activity_type) == family]
        ctx = insights_service.context(session, source_id, clock.today())
        verdicts = coach_notes.verdicts(ctx)
        mix = {a.id: i for a in ctx["acts"] if (i := coach_notes.intensity(a))} if ctx else {}
        return {
            "total": len(rows),
            "families": counts,
            "items": [_activity_dict(a, verdicts, mix) for a in rows[offset : offset + limit]],
        }

    @app.get("/api/activities/summary")
    def activities_summary(
        family: str | None = Query(None, max_length=16), session: Session = Depends(get_session)
    ) -> dict:
        ctx = insights_service.context(session, _active_source(session), clock.today())
        return training_log.summary(ctx, family) if ctx else {"has_data": False}

    def _activity_for(session: Session, activity_id: int) -> Activity:
        a = session.get(Activity, activity_id)
        if a is None or a.source_id != _active_source(session):
            raise HTTPException(404, "Activity not found")
        return a

    @app.get("/api/activities/{activity_id}")
    def activity_detail(activity_id: int, session: Session = Depends(get_session)) -> dict:
        a = _activity_for(session, activity_id)
        out: dict = {
            "activity": _activity_dict(a),
            "garmin_summary": None,
            "detail": None,
            "workouts": None,
            "fit": None,
            "missing": [],
            "stored": {},
            "coach": None,
            "strength": None,
        }
        if a.source_id == "garmin":
            rid = a.source_record_id
            out["garmin_summary"] = vault.activity_summaries(session).get(rid)
            for key, field in (("activity_detail", "detail"), ("activity_workouts", "workouts"), ("activity_fit", None)):
                raw, payload = vault.load(session, f"{key}:{rid}")
                if raw is None:
                    out["missing"].append(key)
                    continue
                out["stored"][key] = {"fetched_at": raw.fetched_at, "status": raw.status_code, "bytes": raw.body_bytes}
                if field:
                    out[field] = payload
                elif raw.file_path:
                    archive = settings.archive_dir.resolve()
                    path = (archive / raw.file_path).resolve()
                    if archive in path.parents and path.is_file():
                        out["fit"] = fit.decode(
                            path, activity_family(a.activity_type), fit.offset_minutes(a.timezone)
                        )
        ctx = insights_service.context(session, a.source_id, clock.today())
        label = strength.get(session, a) if activity_family(a.activity_type) == "strength" else None
        out["route"] = None
        if ctx:
            streams = out["fit"].get("streams") if out["fit"] else None
            out["coach"] = coach_notes.session(ctx, a.id, streams, out["garmin_summary"], named=label is not None)
            if out["coach"] is not None:
                out["coach"]["what_if"] = coach_notes.whatif_card(whatif_analytics.for_activity(ctx, a.id, insights_service.lab_models(ctx)), "session", ctx)
            if a.source_id == "garmin" and ctx["geo"].get(a.id):
                found = route_analytics.build(ctx["acts"], ctx["geo"], ctx["eff"], ctx["weather_runs"], ctx["as_of"])
                out["route"] = route_analytics.for_activity(
                    {**found, "routes": [{**r, "notes": coach_notes.route_notes(r)} for r in found["routes"] if a.id in r["member_ids"]]}, a.id)
        day_plans = planner_store.reconcile(session, a.source_id, planner_store.listing(session, a.local_date, a.local_date), clock.today(), clock.now())
        out["planned"] = next((p for p in day_plans if (p.get("activity") or {}).get("id") == a.id), None)
        if activity_family(a.activity_type) == "strength":
            if label and out["fit"] and out["fit"].get("streams"):
                s = out["fit"]["streams"]
                label["segments"] = exercises.segment(s.get("t") or [], s.get("heart_rate") or [], label["blocks"], ctx["zones"] if ctx else None)
            out["strength"] = {"label": label, "templates": strength.templates(session)}
        return out

    @app.post("/api/strength/parse")
    def strength_parse(body: StrengthText) -> dict:
        blocks = exercises.parse(body.text)
        return strength.view(body.text, blocks)

    def _plan_history(session: Session, source_id: str) -> list[dict]:
        today = clock.today()
        return planner_store.reconcile(
            session, source_id, planner_store.listing(session, date(2000, 1, 1), today + timedelta(days=planner_store.HORIZON_DAYS)), today, clock.now()
        )

    def _plan_options(session: Session, ctx: dict, day: date, sport: str, strength_text: str | None = None) -> list[dict]:
        today = clock.today()
        source_id = _active_source(session)
        # A bias in your own realised plans corrects new predictions (see analytics/accuracy.py).
        ctx["calibration"] = accuracy_analytics.calibration(accuracy_analytics.score_plans(_plan_history(session, source_id)))
        start, end = planner_store.window(today)
        planned = planner_store.listing(session, start, end + timedelta(days=7))
        if sport == "run":
            opts = session_planner.run_options(ctx, training_plan.weekly_plan(ctx))
        elif sport == "ride":
            opts = session_planner.ride_options(ctx)
        elif sport == "swim":
            opts = session_planner.swim_options()
        else:
            blocks = exercises.parse(strength_text) if strength_text else []
            opts = [session_planner.strength_option(ctx, blocks, exercises.summary(blocks) if blocks else None)]
        model = session_planner.load_model(ctx["acts"], ctx["as_of"])
        for o in opts:
            o["predicted"] = session_planner.predict(ctx, model, day, o, planned)
        readiness = insights_service.readiness_on(ctx, ctx["as_of"]) if day == ctx["as_of"] else None
        return session_planner.rank(ctx, day, opts, planned, readiness)

    def _planning_day(day: date) -> None:
        today = clock.today()
        if not today <= day < today + timedelta(days=planner_store.HORIZON_DAYS):
            raise HTTPException(400, f"Plan today or up to {planner_store.HORIZON_DAYS - 1} days ahead")

    @app.get("/api/reviews/{kind}")
    def review(kind: Literal["week", "month"], start: date | None = None, session: Session = Depends(get_session)) -> dict:
        source_id = _active_source(session)
        today = clock.today()
        ctx = insights_service.context(session, source_id, today)
        if ctx is None:
            return {"has_data": False}
        if start is None:
            start = coach_week_start(today) - timedelta(days=7) if kind == "week" else (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        if start > today or start < ctx["first"] - timedelta(days=31):
            raise HTTPException(400, "No data for that period")
        planned = planner_store.reconcile(
            session, source_id, planner_store.listing(session, start - timedelta(days=62), start + timedelta(days=31)), today, clock.now()
        )
        built = reviews.build(ctx, kind, start, planned, insights_service.readiness_on)
        card = coach_notes.whatif_card(whatif_analytics.for_period(ctx, built["start"], built["end"], insights_service.lab_models(ctx)), kind, ctx)
        return {"has_data": True, "first": ctx["first"], "today": today, **built, "what_if": card}

    @app.get("/api/planner")
    def planner_week(session: Session = Depends(get_session)) -> dict:
        source_id = _active_source(session)
        today = clock.today()
        start, end = planner_store.window(today)
        plans = planner_store.reconcile(session, source_id, planner_store.listing(session, start, end), today, clock.now())
        ctx = insights_service.context(session, source_id, today)
        model = session_planner.load_model(ctx["acts"], ctx["as_of"]) if ctx else None
        return {
            "today": today,
            "days": [{"day": d, "plans": [p for p in plans if p["day"] == d]} for d in (start + timedelta(days=i) for i in range((end - start).days + 1))],
            "projection": session_planner.projection(ctx) if ctx else None,
            "model": {k: model[k] for k in ("n", "r2", "counts")} if model else None,
        }

    @app.get("/api/planner/options")
    def planner_options(
        day: date, sport: Literal["run", "ride", "swim", "strength"], strength_text: str | None = Query(None, max_length=4000),
        session: Session = Depends(get_session),
    ) -> dict:
        _planning_day(day)
        ctx = insights_service.context(session, _active_source(session), clock.today())
        if ctx is None:
            raise HTTPException(409, "Sync some training first")
        return {"day": day, "sport": sport, "options": _plan_options(session, ctx, day, sport, strength_text)}

    @app.post("/api/planner")
    def planner_create(body: PlanRequest, session: Session = Depends(get_session)) -> dict:
        _planning_day(body.day)
        ctx = insights_service.context(session, _active_source(session), clock.today())
        if ctx is None:
            raise HTTPException(409, "Sync some training first")
        option = next((o for o in _plan_options(session, ctx, body.day, body.sport, body.strength_text) if o["key"] == body.option_key), None)
        if option is None:
            raise HTTPException(400, "That option isn't available for this day")
        return planner_store.create(session, body.day, option, option["predicted"], clock.now(), body.strength_text if body.sport == "strength" else None)

    @app.delete("/api/planner/{plan_id}")
    def planner_delete(plan_id: int, session: Session = Depends(get_session)) -> dict:
        if not planner_store.delete(session, plan_id):
            raise HTTPException(404, "Not found")
        return {"deleted": True}

    @app.post("/api/strength/ocr")
    async def strength_ocr(request: Request) -> dict:
        """Reads a class screenshot on this machine (Apple Vision, or Tesseract off the Mac); returns the text and its parsed blocks, unsaved."""
        if not request.headers.get("content-type", "").startswith("image/"):
            raise HTTPException(415, "Send the screenshot as an image")
        data = await request.body()
        if not data or len(data) > ocr.MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image is empty or larger than 15 MB")
        if not ocr.available():
            raise HTTPException(501, "Text recognition isn't available on this computer")
        try:
            text = await run_in_threadpool(ocr.image_text, data)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return strength.view(text, exercises.parse(text))

    @app.put("/api/strength/{activity_id}")
    def strength_save(activity_id: int, body: StrengthText, session: Session = Depends(get_session)) -> dict:
        a = _activity_for(session, activity_id)
        if activity_family(a.activity_type) != "strength":
            raise HTTPException(400, "Only strength and HIIT sessions can be named")
        try:
            return strength.save(session, a, body.text, clock.now(), body.template)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.delete("/api/strength/{activity_id}")
    def strength_delete(activity_id: int, session: Session = Depends(get_session)) -> dict:
        strength.delete(session, _activity_for(session, activity_id))
        return {"deleted": True}

    @app.post("/api/activities/{activity_id}/fetch")
    def activity_fetch(activity_id: int, session: Session = Depends(get_session)) -> dict:
        a = _activity_for(session, activity_id)
        if a.source_id != "garmin":
            return {"fetched": []}
        try:
            return {"fetched": garmin_jobs.fetch_activity(a.source_record_id)}
        except IntegrityError:
            # The background sync stored the same asset concurrently.
            return {"fetched": []}
        except GarminError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.get("/api/days/{day}")
    def day_detail(day: date, session: Session = Depends(get_session)) -> dict:
        source_id = _active_source(session)
        values, context = days.metric_context(session, source_id, day)
        prev_day, next_day = days.neighbours(session, source_id, day)
        raw = days.raw_rows(session, day) if source_id == "garmin" else {}
        missing = [
            ds for ds, metric in days.ON_DEMAND.items()
            if source_id == "garmin" and metric in values and ds not in raw
        ]
        acts = session.scalars(
            select(Activity)
            .where(Activity.source_id == source_id, Activity.local_date == day)
            .order_by(Activity.start_time_utc)
        ).all()
        ctx = insights_service.context(session, source_id, clock.today())
        verdicts = coach_notes.verdicts(ctx)
        return {
            "day": day,
            "source_id": source_id,
            "metrics": {
                m: {**c, **METRICS.get(m, {"label": m, "higher_is_better": None})}
                for m, c in context.items()
            },
            "raw": raw,
            "missing": missing,
            "activities": [_activity_dict(a, verdicts) for a in acts],
            "coach": coach_notes.day(ctx, day) if ctx else None,
            "prev_day": prev_day,
            "next_day": next_day,
        }

    @app.post("/api/days/{day}/fetch")
    def day_fetch(day: date, session: Session = Depends(get_session)) -> dict:
        if _active_source(session) != "garmin" or day > clock.today():
            return {"fetched": []}
        values, _ = days.metric_context(session, "garmin", day)
        wanted = [ds for ds, metric in days.ON_DEMAND.items() if metric in values]
        try:
            return {"fetched": garmin_jobs.fetch_day(day, wanted)}
        except IntegrityError:
            return {"fetched": []}
        except GarminError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.get("/api/insights")
    def insights(session: Session = Depends(get_session)) -> dict:
        source_id = _active_source(session)
        result = insights_service.build(session, source_id, clock.today())
        if result.get("analysis_pending"):
            analysis.kick()
        result["analysis_running"] = analysis.busy
        return result

    @app.get("/api/score")
    def score_detail(days: int = Query(90, ge=7, le=365), session: Session = Depends(get_session)) -> dict:
        ctx = insights_service.context(session, _active_source(session), clock.today())
        r = cadence_score.report(ctx, days) if ctx else None
        return {"has_data": True, **r} if r else {"has_data": False}

    @app.get("/api/garmin/vault/{dataset}")
    def vault_list(
        dataset: str,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: Session = Depends(get_session),
    ) -> dict:
        if dataset not in BY_KEY:
            raise HTTPException(404, "Unknown dataset")
        where = (vault_model.source_id == "garmin", vault_model.dataset == dataset)
        rows = session.scalars(
            select(vault_model)
            .where(*where)
            .order_by(vault_model.window_start.desc().nulls_last(), vault_model.fetched_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return {
            "total": session.scalar(select(func.count()).select_from(vault_model).where(*where)),
            "items": [_raw_meta(r) for r in rows],
        }

    @app.get("/api/garmin/vault/item/{raw_id}")
    def vault_item(raw_id: int, session: Session = Depends(get_session)) -> dict:
        raw = session.get(vault_model, raw_id)
        if raw is None or raw.source_id != "garmin":
            raise HTTPException(404, "Not found")
        activity_id = None
        if raw.dataset.startswith("activity_"):
            activity_id = session.scalar(
                select(Activity.id).where(
                    Activity.source_id == "garmin",
                    Activity.source_record_id == raw.request_key.split(":", 1)[1],
                )
            )
        return {"meta": _raw_meta(raw), "payload": vault.decode(raw.body), "activity_id": activity_id}

    @app.get("/api/weight")
    def weight(
        days: int = Query(180, ge=14, le=3650), session: Session = Depends(get_session)
    ) -> dict:
        today = clock.today()
        summary = _weight_summary(session, today)
        cutoff = summary.points[-1].day - timedelta(days=days) if summary.points else None
        body_profile = profile_store.load(session)
        latest_fat = session.scalar(
            select(WeightReading.body_fat_pct)
            .where(WeightReading.source_id.in_((_active_source(session), weightlog.SOURCE_ID)), WeightReading.body_fat_pct.is_not(None))
            .order_by(WeightReading.measured_at_utc.desc())
            .limit(1)
        )
        return {
            "points": [{**asdict(p), "body": _body_dict(p.trend_kg, body_profile, today)}
                       for p in summary.points if cutoff is None or p.day > cutoff],
            "body_profile": body_profile,
            "latest_trend_kg": summary.latest_trend_kg,
            "rate_kg_per_week": summary.rate_kg_per_week,
            "rate_se_kg_per_week": summary.rate_se_kg_per_week,
            "goal_kg": _goal(session),
            "projection": asdict(summary.projection) if summary.projection else None,
            "latest_body_fat_pct": latest_fat,
            "coach": coach_notes.weight(summary.points, summary.rate_kg_per_week, _goal(session), clock.today()),
            "model": {
                "process_var_per_day": weight_analytics.PROCESS_VAR_PER_DAY,
                "measurement_var": weight_analytics.MEASUREMENT_VAR,
                "rate_window_days": weight_analytics.RATE_WINDOW_DAYS,
            },
        }

    @app.put("/api/settings/weight-goal")
    def set_weight_goal(body: WeightGoalRequest, session: Session = Depends(get_session)) -> dict:
        today = clock.today()
        goal_store.set_weight_target(session, body.goal_kg, _weight_summary(session, today).latest_trend_kg, today, clock.now())
        return {"goal_kg": body.goal_kg}

    @app.get("/api/journal")
    def journal_view(days: int = Query(14, ge=1, le=60), session: Session = Depends(get_session)) -> dict:
        journal.ensure_catalogue(session, clock.now())
        today = clock.today()
        return {
            "behaviours": [journal.behaviour_dict(b) for b in journal.catalogue(session)],
            "checkin": journal.checkin(session, today),
            "days": journal.days(session, today - timedelta(days=days)),
            "today": today,
        }

    @app.put("/api/journal/{day}")
    def journal_save(day: date, body: JournalDayRequest, session: Session = Depends(get_session)) -> dict:
        journal.ensure_catalogue(session, clock.now())
        try:
            answers = journal.save_day(session, day, body.answers, clock.today(), clock.now())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"day": day, "answers": answers, "checkin": journal.checkin(session, clock.today())}

    @app.post("/api/journal/behaviours")
    def journal_add(body: BehaviourCreate, session: Session = Depends(get_session)) -> dict:
        b = journal.add_behaviour(session, body.label, body.question, body.kind, body.unit, clock.now())
        return journal.behaviour_dict(b)

    @app.patch("/api/journal/behaviours/{key}")
    def journal_update(key: str, body: BehaviourUpdate, session: Session = Depends(get_session)) -> dict:
        b = journal.update_behaviour(session, key, active=body.active, label=body.label, question=body.question)
        if b is None:
            raise HTTPException(404, "Unknown habit")
        return journal.behaviour_dict(b)

    @app.get("/api/settings/profile")
    def get_profile(session: Session = Depends(get_session)) -> dict:
        return {"profile": profile_store.load(session)}

    @app.put("/api/settings/profile")
    def set_profile(body: ProfileRequest, session: Session = Depends(get_session)) -> dict:
        try:
            p = profile_store.save(session, body.height_cm, body.birth_date, body.sex)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"profile": p}

    @app.get("/api/backup/status")
    def backup_status() -> dict:
        return backup.load(settings.data_dir, clock.now())

    @app.get("/api/weight/entries")
    def weight_entries(session: Session = Depends(get_session)) -> dict:
        return {"entries": weightlog.entries(session), "today": clock.today()}

    @app.post("/api/weight/entries")
    def weight_entry_add(body: WeightEntryRequest, session: Session = Depends(get_session)) -> dict:
        try:
            return weightlog.add(session, body.day, body.weight_kg, clock.today(), clock.now())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.delete("/api/weight/entries/{day}")
    def weight_entry_delete(day: date, session: Session = Depends(get_session)) -> dict:
        if not weightlog.remove(session, day):
            raise HTTPException(404, "No manual entry for that day")
        return {"deleted": day}

    @app.get("/api/settings/weather")
    def weather_setting(session: Session = Depends(get_session)) -> dict:
        return {"enabled": weather.enabled(session), "available": settings.weather}

    @app.put("/api/settings/weather")
    def set_weather_setting(body: WeatherSetting, session: Session = Depends(get_session)) -> dict:
        weather.set_enabled(session, body.enabled)
        if body.enabled and settings.weather:
            analysis.kick()
        return {"enabled": body.enabled, "available": settings.weather}

    @app.put("/api/settings/goal")
    def set_training_goal(body: TrainingGoalRequest, session: Session = Depends(get_session)) -> dict:
        if body.distance is None or body.date is None:
            goal_store.set_primary_race(session, None, clock.today(), clock.now())
            return {"goal": None}
        if body.date < clock.today():
            raise HTTPException(400, "Goal date is in the past")
        goal = {"distance": body.distance, "date": body.date, "target_s": body.target_s}
        goal_store.set_primary_race(session, goal, clock.today(), clock.now())
        return {"goal": insights_service._goal_dict(goal)}  # pylint: disable=protected-access

    # ---- goals ----

    @app.get("/api/goals")
    def goals_list(session: Session = Depends(get_session)) -> dict:
        today = clock.today()
        source_id = _active_source(session)
        ctx = insights_service.context(session, source_id, today)
        readings = _weight_readings(session)
        items = []
        for g in goal_store.listing(session):
            if g["status"] != "active":
                closed = {**goal_analytics.fields(g, today), "state": "closed"}
                items.append({**closed, "headline": coach_notes.goal_headline(closed)})
                continue
            w = goal_analytics.weight_inputs(weight_analytics.summarize(readings, today, g["spec"].get("target_kg"))) if g["kind"] == "weight" else None
            a = goal_analytics.assess(g, ctx, today, w)
            items.append({**a, "headline": coach_notes.goal_headline(a)})
        plan_goal = goal_store.primary_run_goal(session, today)
        return {"today": today, "goals": items, "plan_goal_id": plan_goal["id"] if plan_goal else None,
                "summary": goal_analytics.summarise_set(items), "has_training": ctx is not None}

    @app.post("/api/goals", status_code=201)
    def goals_create(body: GoalRequest, session: Session = Depends(get_session)) -> dict:
        today = clock.today()
        start = _weight_summary(session, today).latest_trend_kg if body.kind == "weight" else None
        try:
            return goal_store.create(session, body.model_dump(), today, clock.now(), start)
        except goal_store.GoalError as err:
            raise HTTPException(400, str(err)) from err

    @app.patch("/api/goals/{goal_id}")
    def goals_update(goal_id: int, body: GoalPatch, session: Session = Depends(get_session)) -> dict:
        try:
            out = goal_store.update(session, goal_id, body.model_dump(exclude_unset=True), clock.today(), clock.now())
        except goal_store.GoalError as err:
            raise HTTPException(400, str(err)) from err
        if out is None:
            raise HTTPException(404, "Not found")
        return out

    @app.delete("/api/goals/{goal_id}")
    def goals_delete(goal_id: int, session: Session = Depends(get_session)) -> dict:
        if not goal_store.delete(session, goal_id):
            raise HTTPException(404, "Not found")
        return {"deleted": True}

    # ---- lab: how far to trust the models, and what-ifs ----

    @app.get("/api/lab/accuracy")
    def lab_accuracy(session: Session = Depends(get_session)) -> dict:
        ctx = insights_service.context(session, _active_source(session), clock.today())
        if ctx is None:
            return {"has_data": False}
        rep = accuracy_analytics.report(ctx, _plan_history(session, _active_source(session)))
        return {"has_data": True, **rep, "headline": coach_notes.accuracy_headline(rep), "explain": coach_notes.accuracy_explain(rep)}

    @app.get("/api/lab/model")
    def lab_model(session: Session = Depends(get_session)) -> dict:
        ctx = insights_service.context(session, _active_source(session), clock.today())
        if ctx is None:
            return {"has_data": False}
        lab = insights_service.lab_models(ctx)
        fit_ = lab["banister"]
        out = banister_analytics.public(fit_)
        if fit_["valid"]:
            first = fit_["series"][0]["day"]
            out["curve"] = banister_analytics.curve(fit_, banister_analytics.effective(ctx["load"], fit_["alpha"]), ctx["as_of"], step=3, since=first)
        extra = {
            "fatigue": {k: v for k, v in lab["fatigue"].items() if not k.startswith("_")},
            "saturation": lab["saturation"],
            "channels": channels_analytics.public(lab["channels"]),
            "model": lab["model"],
            "explain_fatigue": coach_notes.fatigue_explain(lab["fatigue"]),
            "explain_saturation": coach_notes.saturation_explain(lab["saturation"]),
            "explain_channels": coach_notes.channels_explain(lab["channels"]),
        }
        return {"has_data": True, **out, **extra, "performance_label": "Aerobic efficiency (weekly median)", "headline": coach_notes.banister_headline(fit_),
                "explain": coach_notes.model_explain(fit_)}

    @app.get("/api/lab/routes")
    def lab_routes(session: Session = Depends(get_session)) -> dict:
        ctx = insights_service.context(session, _active_source(session), clock.today())
        if ctx is None:
            return {"has_data": False}
        out = route_analytics.build(ctx["acts"], ctx["geo"], ctx["eff"], ctx["weather_runs"], ctx["as_of"])
        for r in out["routes"]:
            r["notes"] = coach_notes.route_notes(r)
        return {"has_data": True, **out, "routes": out["routes"][:12]}

    @app.get("/api/lab/whatif")
    def lab_whatif(session: Session = Depends(get_session)) -> dict:
        ctx = insights_service.context(session, _active_source(session), clock.today())
        if ctx is None:
            return {"has_data": False}
        lab = insights_service.lab_models(ctx)
        out = whatif_analytics.suggestions(ctx, lab)
        for b in out["bundles"].values():
            b["headline"] = coach_notes.whatif_headline({**b, "edits": range(b["n"]), "next_morning": None})
            b["lines"] = coach_notes.whatif_lines(b)
        for i in out["items"]:
            i["lines"] = coach_notes.whatif_lines(i)
        return {"has_data": True, **out, "actions": whatif_analytics.ACTIONS, "model": lab["model"], "freshness": lab["freshness"],
                "explain_freshness": coach_notes.freshness_explain(lab["freshness"])}

    @app.get("/api/lab/whatif/replay")
    def lab_whatif_replay(edit: list[str] = Query(..., max_length=40), session: Session = Depends(get_session)) -> dict:
        ctx = insights_service.context(session, _active_source(session), clock.today())
        if ctx is None:
            raise HTTPException(409, "Sync some training first")
        edits = []
        for item in edit[:20]:
            aid, _, action = item.partition(":")
            if not aid.isdigit() or action not in whatif_analytics.ACTIONS:
                raise HTTPException(400, "Use edit=<activity id>:<skip|easy|half>")
            edits.append({"activity_id": int(aid), "action": action})
        result = whatif_analytics.compare(ctx, edits, lab=insights_service.lab_models(ctx))
        if not result["valid"]:
            raise HTTPException(400, "None of those sessions can be replayed (only sessions from the last 8 weeks with a training load)")
        return {**result, "headline": coach_notes.whatif_headline(result), "lines": coach_notes.whatif_lines(result)}

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str) -> Response:
        """Serves the built site so the Mac needs no dev server."""
        root = settings.web_dist.resolve()
        if path.startswith("api/") or not (root / "index.html").is_file():
            raise HTTPException(404, "Not found")
        target = (root / path).resolve()
        if path and root in target.parents and target.is_file():
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        return FileResponse(root / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def coach_week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _body_dict(weight_kg: float, prof: dict | None, today: date) -> dict | None:
    if prof is None:
        return None
    e = body_analytics.estimate(weight_kg, prof, today)
    return asdict(e) if e else None


def _goal(session: Session) -> float | None:
    return goal_store.weight_target(session)


def _active_source(session: Session) -> str:
    garmin = session.get(Source, "garmin")
    return "garmin" if garmin and garmin.last_synced_at else "demo"


def _weight_readings(session: Session) -> list[tuple[date, float]]:
    rows = session.execute(
        select(WeightReading.local_date, func.avg(WeightReading.weight_kg))
        .where(WeightReading.source_id.in_((_active_source(session), weightlog.SOURCE_ID)))
        .group_by(WeightReading.local_date)
        .order_by(WeightReading.local_date)
    ).all()
    return [(d, w) for d, w in rows]


def _weight_summary(session: Session, today: date) -> weight_analytics.WeightSummary:
    return weight_analytics.summarize(_weight_readings(session), today, _goal(session))


def _raw_meta(raw: vault_model) -> dict:
    return {
        "id": raw.id,
        "dataset": raw.dataset,
        "request_key": raw.request_key,
        "window_start": raw.window_start,
        "window_end": raw.window_end,
        "fetched_at": raw.fetched_at,
        "status": raw.status_code,
        "final": raw.final,
        "item_count": raw.item_count,
        "body_bytes": raw.body_bytes,
        "stored_bytes": raw.stored_bytes,
        "is_file": raw.file_path is not None,
    }


def _run_dict(run: SyncRun) -> dict:
    return {
        "id": run.id,
        "source_id": run.source_id,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "records_written": run.records_written,
        "error": run.error,
        "mode": run.mode,
        "requests_made": run.requests_made,
        "message": run.message,
    }


def _activity_dict(a: Activity, verdicts: dict[int, dict] | None = None, mix: dict[int, dict] | None = None) -> dict:
    return {
        "id": a.id,
        "source_id": a.source_id,
        "start_time_utc": a.start_time_utc,
        "timezone": a.timezone,
        "local_date": a.local_date,
        "type": a.activity_type,
        "family": activity_family(a.activity_type),
        "name": a.name,
        "duration_s": a.duration_s,
        "distance_m": a.distance_m,
        "avg_hr": a.avg_hr,
        "max_hr": a.max_hr,
        "elevation_gain_m": a.elevation_gain_m,
        "calories": a.calories,
        "training_load": a.training_load,
        "moving_duration_s": a.moving_duration_s,
        "avg_speed_mps": a.avg_speed_mps,
        "vo2max": a.vo2max,
        "aerobic_te": a.aerobic_te,
        "verdict": (verdicts or {}).get(a.id),
        "intensity": (mix or {}).get(a.id),
    }


def app_factory() -> FastAPI:
    return create_app()
