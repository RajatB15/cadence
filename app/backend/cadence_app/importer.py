from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from cadence_app.models import Activity, DailyMetric, Source, WeightReading


@dataclass(frozen=True)
class MetricRecord:
    day: date
    metric: str
    value: float
    unit: str


@dataclass(frozen=True)
class ActivityRecord:
    source_record_id: str
    start_time_utc: datetime
    timezone: str
    local_date: date
    activity_type: str
    name: str
    duration_s: float
    distance_m: float | None
    avg_hr: float | None
    max_hr: float | None
    elevation_gain_m: float | None
    calories: float | None
    training_load: float | None
    moving_duration_s: float | None = None
    avg_speed_mps: float | None = None
    vo2max: float | None = None
    aerobic_te: float | None = None


@dataclass(frozen=True)
class WeightRecord:
    source_record_id: str
    measured_at_utc: datetime
    timezone: str
    local_date: date
    weight_kg: float
    body_fat_pct: float | None
    bmi: float | None = None
    body_water_pct: float | None = None
    muscle_mass_kg: float | None = None
    bone_mass_kg: float | None = None
    visceral_fat: float | None = None
    metabolic_age: float | None = None


@dataclass
class Batch:
    metrics: list[MetricRecord] = field(default_factory=list)
    activities: list[ActivityRecord] = field(default_factory=list)
    weights: list[WeightRecord] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.metrics) + len(self.activities) + len(self.weights)


def ensure_source(session: Session, source_id: str, name: str, kind: str) -> Source:
    source = session.get(Source, source_id)
    if source is None:
        source = Source(id=source_id, name=name, kind=kind)
        session.add(source)
        session.flush()
    return source


def _upsert(session: Session, model, rows: list[dict], keys: list[str]) -> None:
    if not rows:
        return
    # SQLite caps bound parameters per statement; chunk to stay well under it.
    columns = len(rows[0])
    chunk = max(1, 30000 // columns)
    for i in range(0, len(rows), chunk):
        stmt = insert(model).values(rows[i : i + chunk])
        updates = {c: stmt.excluded[c] for c in rows[0] if c not in keys}
        session.execute(stmt.on_conflict_do_update(index_elements=keys, set_=updates))


def write_batch(session: Session, source_id: str, batch: Batch, now: datetime) -> int:
    """Idempotently upsert a batch keyed by each record's natural source identity."""
    _upsert(
        session,
        DailyMetric,
        [{**asdict(m), "source_id": source_id, "imported_at": now} for m in batch.metrics],
        ["source_id", "day", "metric"],
    )
    _upsert(
        session,
        Activity,
        [{**asdict(a), "source_id": source_id, "imported_at": now} for a in batch.activities],
        ["source_id", "source_record_id"],
    )
    _upsert(
        session,
        WeightReading,
        [{**asdict(w), "source_id": source_id, "imported_at": now} for w in batch.weights],
        ["source_id", "source_record_id"],
    )
    return len(batch)
