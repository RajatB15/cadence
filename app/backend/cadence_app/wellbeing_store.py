"""Wellbeing check-ins: feel, soreness, pain, illness and life stress, one row per day, written only by you."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.models import Wellbeing

MAX_BACKFILL_DAYS = 14
FIELDS = {"feel": (1, 5), "soreness": (0, 3), "pain_level": (0, 3), "illness": (0, 2), "life_stress": (1, 3)}


class WellbeingError(ValueError):
    pass


def as_dict(w: Wellbeing) -> dict:
    return {"day": w.day, "feel": w.feel, "soreness": w.soreness, "pain_level": w.pain_level, "pain_area": w.pain_area,
            "illness": w.illness, "life_stress": w.life_stress, "note": w.note}


def entries(session: Session, since: date | None = None) -> dict[date, dict]:
    q = select(Wellbeing).order_by(Wellbeing.day)
    if since is not None:
        q = q.where(Wellbeing.day >= since)
    return {w.day: as_dict(w) for w in session.scalars(q)}


def save(session: Session, day: date, values: dict, today: date, now: datetime) -> dict:
    """Upserts a day. Fields you leave out stay as they were; a null clears one. Pain without an area is allowed, an area without pain is dropped."""
    if day > today or day < today - timedelta(days=MAX_BACKFILL_DAYS):
        raise WellbeingError(f"Check-ins cover today and the last {MAX_BACKFILL_DAYS} days")
    for key, (lo, hi) in FIELDS.items():
        v = values.get(key)
        if v is not None and not lo <= v <= hi:
            raise WellbeingError(f"{key} must be between {lo} and {hi}")
    row = session.get(Wellbeing, day) or Wellbeing(day=day, updated_at=now)
    for key in (*FIELDS, "note"):
        if key in values:
            setattr(row, key, (values[key].strip() or None) if key == "note" and values[key] else values[key])
    if "pain_area" in values:
        area = (values["pain_area"] or "").strip()[:40]
        row.pain_area = area or None
    if not row.pain_level:
        row.pain_area = None
    row.updated_at = now
    session.merge(row)
    session.commit()
    return as_dict(session.get(Wellbeing, day))


def delete(session: Session, day: date) -> bool:
    row = session.get(Wellbeing, day)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True
