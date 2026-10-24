from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(32))  # demo | garmin | scale | manual
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)


class DailyMetric(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = (UniqueConstraint("source_id", "day", "metric"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    metric: Mapped[str] = mapped_column(String(48), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    imported_at: Mapped[datetime] = mapped_column(DateTime)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    source_record_id: Mapped[str] = mapped_column(String(64))
    # Naive UTC instant; local_date and timezone keep the source's calendar semantics.
    start_time_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    timezone: Mapped[str] = mapped_column(String(64))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    activity_type: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(200))
    duration_s: Mapped[float] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    training_load: Mapped[float | None] = mapped_column(Float)
    moving_duration_s: Mapped[float | None] = mapped_column(Float)
    avg_speed_mps: Mapped[float | None] = mapped_column(Float)
    vo2max: Mapped[float | None] = mapped_column(Float)
    aerobic_te: Mapped[float | None] = mapped_column(Float)
    imported_at: Mapped[datetime] = mapped_column(DateTime)


class WeightReading(Base):
    __tablename__ = "weight_readings"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    source_record_id: Mapped[str] = mapped_column(String(64))
    measured_at_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    timezone: Mapped[str] = mapped_column(String(64))
    local_date: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    body_water_pct: Mapped[float | None] = mapped_column(Float)
    muscle_mass_kg: Mapped[float | None] = mapped_column(Float)
    bone_mass_kg: Mapped[float | None] = mapped_column(Float)
    visceral_fat: Mapped[float | None] = mapped_column(Float)
    metabolic_age: Mapped[float | None] = mapped_column(Float)
    imported_at: Mapped[datetime] = mapped_column(DateTime)


class Behaviour(Base):
    """Something worth tracking in the journal: built in (deactivate only) or your own."""

    __tablename__ = "behaviours"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    question: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(16))  # yes_no | count
    unit: Mapped[str] = mapped_column(String(16), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class StrengthLabel(Base):
    """What a strength/HIIT class contained, as you pasted it. Keyed by the source's activity id so an offline
    rebuild (which recreates activity rows) never loses it."""

    __tablename__ = "strength_labels"

    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    blocks: Mapped[str] = mapped_column(Text)  # JSON from analytics.exercises.parse
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class DayHeartHistogram(Base):
    """Cached minutes-per-bpm for one settled day of all-day heart rate (derived from the vault; safe to drop)."""

    __tablename__ = "day_hr_histograms"

    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    outside: Mapped[str] = mapped_column(Text)  # JSON {bpm: minutes}
    inside: Mapped[str] = mapped_column(Text)
    samples: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime)


class PlannedSession(Base):
    """A session planned for a day: the chosen option and what it was predicted to do."""

    __tablename__ = "planned_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    sport: Mapped[str] = mapped_column(String(16))  # run | ride | swim | strength
    kind: Mapped[str] = mapped_column(String(24))
    option_key: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(Text)
    minutes: Mapped[int] = mapped_column(Integer)
    predicted: Mapped[str] = mapped_column(Text)  # JSON from analytics.planner.predict
    strength_text: Mapped[str | None] = mapped_column(Text)
    start_hour: Mapped[int | None] = mapped_column(Integer)  # local hour you plan to start; None = your usual time
    created_at: Mapped[datetime] = mapped_column(DateTime)


class WeatherHour(Base):
    """Hourly conditions from Open-Meteo for a rounded location (0.1°, ~10 km); UTC hour."""

    __tablename__ = "weather_hours"

    lat: Mapped[float] = mapped_column(Float, primary_key=True)
    lon: Mapped[float] = mapped_column(Float, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    temperature: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    dew_point: Mapped[float | None] = mapped_column(Float)
    apparent: Mapped[float | None] = mapped_column(Float)
    wind: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))  # archive | forecast
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class ActivityWeather(Base):
    """Conditions during one outdoor session, averaged over its hours. Keyed by the source's activity id."""

    __tablename__ = "activity_weather"

    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    temperature: Mapped[float | None] = mapped_column(Float)
    humidity: Mapped[float | None] = mapped_column(Float)
    dew_point: Mapped[float | None] = mapped_column(Float)
    apparent: Mapped[float | None] = mapped_column(Float)
    wind: Mapped[float | None] = mapped_column(Float)
    final: Mapped[bool] = mapped_column(Boolean)  # archive (settled) vs forecast-model values
    computed_at: Mapped[datetime] = mapped_column(DateTime)


class Goal(Base):
    """A target: a race, a performance, a single-session distance or a weight. Spec is JSON (see goal_store)."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # race | performance | distance | weight
    sport: Mapped[str | None] = mapped_column(String(16))  # run | ride | swim; none for weight
    title: Mapped[str] = mapped_column(String(120))
    spec: Mapped[str] = mapped_column(Text)
    target_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(12), index=True)  # active | achieved | dropped
    start_value: Mapped[float | None] = mapped_column(Float)  # weight when the goal was set (progress)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Wellbeing(Base):
    """How you say you feel on a day: one row per day, entered by you, never derived from the watch."""

    __tablename__ = "wellbeing"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    feel: Mapped[int | None] = mapped_column(Integer)  # 1 awful .. 5 great
    soreness: Mapped[int | None] = mapped_column(Integer)  # 0 none, 1 mild, 2 moderate, 3 severe
    pain_level: Mapped[int | None] = mapped_column(Integer)  # 0 none, 1 niggle, 2 hurts, 3 stops me
    pain_area: Mapped[str | None] = mapped_column(String(40))
    illness: Mapped[int | None] = mapped_column(Integer)  # 0 well, 1 run down, 2 properly ill
    life_stress: Mapped[int | None] = mapped_column(Integer)  # 1 light, 2 normal, 3 heavy
    note: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class FoodDish(Base):
    """A dish in your own library: nutrition for one serving unit (a roti, a katori of dal, a plate of poha)."""

    __tablename__ = "food_dishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    unit: Mapped[str] = mapped_column(String(40))
    kcal: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    spread_pct: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    builtin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    source: Mapped[str] = mapped_column(String(16), default="mine", server_default="mine")  # healthify | mine (older: starter | INDB | IFCT)
    ref_code: Mapped[str | None] = mapped_column(String(24))
    # Grams are the standard unit: weight of one serving as eaten, and nutrition per 100 g. INDB dishes have only the
    # recipe's weight, so they're logged by serving. Per-serving kcal/protein/carbs/fat above always equal per-100 g x unit_g.
    unit_g: Mapped[float | None] = mapped_column(Float)
    kcal_100g: Mapped[float | None] = mapped_column(Float)
    protein_100g: Mapped[float | None] = mapped_column(Float)
    carbs_100g: Mapped[float | None] = mapped_column(Float)
    fat_100g: Mapped[float | None] = mapped_column(Float)
    basis: Mapped[str] = mapped_column(String(16), default="estimate", server_default="estimate")  # healthify | estimate (your own)
    note: Mapped[str | None] = mapped_column(String(240))
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    aliases: Mapped[str | None] = mapped_column(Text)  # other names, JSON list, searched alongside the name
    portions: Mapped[str | None] = mapped_column(Text)  # household portions, JSON list of {unit, grams}
    edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # you changed it; the catalogue won't overwrite
    created_at: Mapped[datetime] = mapped_column(DateTime)


class FoodEntry(Base):
    """One thing eaten. Nutrition is copied from the dish when logged, so editing a dish later never rewrites history."""

    __tablename__ = "food_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    meal: Mapped[str] = mapped_column(String(16))  # breakfast | lunch | snack | dinner
    dish_id: Mapped[int | None] = mapped_column(ForeignKey("food_dishes.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    servings: Mapped[float] = mapped_column(Float)
    kcal: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    spread_pct: Mapped[int] = mapped_column(Integer, default=25, server_default="25")
    grams: Mapped[float | None] = mapped_column(Float)  # amount eaten in grams, when the dish has a weight
    logged_at: Mapped[datetime] = mapped_column(DateTime)


class StrengthTemplate(Base):
    __tablename__ = "strength_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class JournalEntry(Base):
    """One answer for one behaviour on the day it happened. A "no" is stored too: it is data, not a gap."""

    __tablename__ = "journal_entries"
    __table_args__ = (UniqueConstraint("day", "behaviour_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    behaviour_key: Mapped[str] = mapped_column(ForeignKey("behaviours.key", ondelete="CASCADE"), index=True)
    value: Mapped[float] = mapped_column(Float)
    answered_at: Mapped[datetime] = mapped_column(DateTime)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16))  # running | succeeded | failed | stopped | paused
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(String(16))
    requests_made: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class RawResponse(Base):
    """Vault of every upstream response, so normalized data can be rebuilt with zero API calls."""

    __tablename__ = "raw_responses"
    __table_args__ = (UniqueConstraint("source_id", "request_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    dataset: Mapped[str] = mapped_column(String(48), index=True)
    request_key: Mapped[str] = mapped_column(String(160))
    path: Mapped[str] = mapped_column(String(300))
    params: Mapped[str] = mapped_column(Text)
    window_start: Mapped[date | None] = mapped_column(Date)
    window_end: Mapped[date | None] = mapped_column(Date)
    status_code: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(100))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # Final responses cover settled days and are never requested again.
    final: Mapped[bool] = mapped_column(Boolean, default=False)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    body: Mapped[bytes | None] = mapped_column(LargeBinary)  # zlib-compressed
    body_bytes: Mapped[int] = mapped_column(Integer, default=0)
    stored_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64))
    file_path: Mapped[str | None] = mapped_column(String(300))


class ActivityAnalysis(Base):
    """Expensive per-activity derivations (FIT stream analysis), computed once per calculation version."""

    __tablename__ = "activity_analyses"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime)
    data: Mapped[str] = mapped_column(Text)


class DatasetState(Base):
    __tablename__ = "dataset_states"

    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    dataset: Mapped[str] = mapped_column(String(48), primary_key=True)
    window_days: Mapped[int | None] = mapped_column(Integer)
    # Days <= final_until were fetched after they settled.
    final_until: Mapped[date | None] = mapped_column(Date)
    # Backfill has covered every day >= oldest_fetched.
    oldest_fetched: Mapped[date | None] = mapped_column(Date)
    oldest_with_data: Mapped[date | None] = mapped_column(Date)
    newest_with_data: Mapped[date | None] = mapped_column(Date)
    empty_days_streak: Mapped[int] = mapped_column(Integer, default=0)
    backfill_done: Mapped[bool] = mapped_column(Boolean, default=False)
    unsupported: Mapped[bool] = mapped_column(Boolean, default=False)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class ReminderDismissal(Base):
    __tablename__ = "reminder_dismissals"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(1024), unique=True)
    p256dh: Mapped[str] = mapped_column(String(256))
    auth: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    failures: Mapped[int] = mapped_column(Integer, default=0)


class NotificationLog(Base):
    """One row per notification decision so each one fires at most once."""

    __tablename__ = "notification_log"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    delivered: Mapped[int] = mapped_column(Integer, default=0)
