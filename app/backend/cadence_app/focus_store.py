"""Focus plans you accepted from the Improve page (written only by you; never automatic)."""

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.models import FocusPlan


class FocusError(ValueError):
    pass


def as_dict(row: FocusPlan) -> dict:
    return {"id": row.id, "metric": row.metric, "start": row.start_date, "end": row.end_date, "priorities": json.loads(row.priorities or "[]"),
            "baseline": json.loads(row.baseline or "{}"), "status": row.status}


def rows(session: Session) -> list[dict]:
    return [as_dict(r) for r in session.scalars(select(FocusPlan).order_by(FocusPlan.start_date))]


def accept(session: Session, metric: str, start: date, end: date, priorities: list[dict], baseline: dict | None, now: datetime) -> dict:
    """Accepting replaces an active focus for the same metric (the earlier one is marked completed so its review stays)."""
    if not priorities:
        raise FocusError("There is no focus to accept")
    for old in session.scalars(select(FocusPlan).where(FocusPlan.metric == metric, FocusPlan.status == "active")):
        old.status = "completed"
    row = FocusPlan(metric=metric, start_date=start, end_date=end, priorities=json.dumps(priorities, default=str),
                    baseline=json.dumps(baseline or {}, default=str), status="active", created_at=now)
    session.add(row)
    session.commit()
    return as_dict(row)


def dismiss(session: Session, focus_id: int) -> dict | None:
    row = session.get(FocusPlan, focus_id)
    if row is None:
        return None
    row.status = "dismissed"
    session.commit()
    return as_dict(row)
