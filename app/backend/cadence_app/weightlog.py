"""Manual weight entries: one reading per day, typed in by the user, blended with the Garmin weight history.

Keyed `manual:<date>` so entering a day again corrects it instead of adding a second row, and an offline
rebuild of the Garmin data never touches these (they live under their own source).
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cadence_app.importer import Batch, WeightRecord, ensure_source, write_batch
from cadence_app.models import WeightReading

SOURCE_ID = "manual"
SOURCE_NAME = "Manual entry"
MIN_KG, MAX_KG = 30.0, 300.0


def _record_id(day: date) -> str:
    return f"manual:{day.isoformat()}"


def add(session: Session, day: date, weight_kg: float, today: date, now_utc: datetime) -> dict:
    if not MIN_KG <= weight_kg <= MAX_KG:
        raise ValueError(f"weight must be between {MIN_KG:g} and {MAX_KG:g} kg")
    if day > today:
        raise ValueError("can't log a weight in the future")
    weight_kg = round(weight_kg, 2)
    measured = now_utc if day == today else datetime.combine(day, time(12, 0))
    ensure_source(session, SOURCE_ID, SOURCE_NAME, "manual")
    write_batch(
        session, SOURCE_ID,
        Batch(weights=[WeightRecord(_record_id(day), measured, "local", day, weight_kg, None)]),
        now_utc,
    )
    session.commit()
    return {"day": day, "weight_kg": weight_kg}


def remove(session: Session, day: date) -> bool:
    result = session.execute(
        delete(WeightReading).where(WeightReading.source_id == SOURCE_ID, WeightReading.source_record_id == _record_id(day))
    )
    session.commit()
    return result.rowcount > 0


def entries(session: Session, limit: int = 30) -> list[dict]:
    rows = session.execute(
        select(WeightReading.local_date, WeightReading.weight_kg)
        .where(WeightReading.source_id == SOURCE_ID)
        .order_by(WeightReading.local_date.desc())
        .limit(limit)
    ).all()
    return [{"day": d, "weight_kg": w} for d, w in rows]
