"""Planned sessions: stored choices, matched to what you actually did that day."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app import strength as strength_store
from cadence_app.activity_types import activity_family
from cadence_app.analytics import exercises as X
from cadence_app.models import Activity, PlannedSession, StrengthLabel

HORIZON_DAYS = 7


def as_dict(p: PlannedSession) -> dict:
    predicted = json.loads(p.predicted)
    out = {"id": p.id, "day": p.day, "sport": p.sport, "kind": p.kind, "option_key": p.option_key, "title": p.title, "detail": p.detail,
           "minutes": p.minutes, "predicted": predicted, "predicted_load": predicted.get("load"), "heavy_lower": False, "blocks": []}
    if p.strength_text:
        blocks = X.parse(p.strength_text)
        out.update(blocks=blocks, heavy_lower=X.summary(blocks)["heavy_lower"])
    return out


def listing(session: Session, start: date, end: date) -> list[dict]:
    rows = session.scalars(select(PlannedSession).where(PlannedSession.day >= start, PlannedSession.day <= end).order_by(PlannedSession.day, PlannedSession.id))
    return [as_dict(p) for p in rows]


def create(session: Session, day: date, option: dict, predicted: dict, now: datetime, strength_text: str | None = None) -> dict:
    p = PlannedSession(day=day, sport=option["sport"], kind=option["kind"], option_key=option["key"], title=option["title"][:120],
                       detail=option["detail"], minutes=int(option.get("minutes") or 0), predicted=json.dumps(predicted, default=str),
                       strength_text=(strength_text or None), created_at=now)
    session.add(p)
    session.commit()
    return as_dict(p)


def delete(session: Session, plan_id: int) -> bool:
    p = session.get(PlannedSession, plan_id)
    if p is None:
        return False
    session.delete(p)
    session.commit()
    return True


def reconcile(session: Session, source_id: str, plans: list[dict], today: date, now: datetime) -> list[dict]:
    """Status per plan (planned / done / missed) and the matching activity; a planned class labels its session."""
    if not plans:
        return plans
    days = {p["day"] for p in plans}
    acts = session.scalars(
        select(Activity).where(Activity.source_id == source_id, Activity.local_date.in_(days)).order_by(Activity.start_time_utc)
    ).all()
    used: set[int] = set()
    for p in sorted(plans, key=lambda x: x["id"]):
        match = next((a for a in acts if a.local_date == p["day"] and a.id not in used and activity_family(a.activity_type) == p["sport"]), None)
        if match is None:
            p.update(status="missed" if p["day"] < today else "planned", activity=None)
            continue
        used.add(match.id)
        p.update(status="done", activity={"id": match.id, "name": match.name, "load": match.training_load, "minutes": round(match.duration_s / 60)})
        if p["sport"] == "strength" and p["blocks"]:
            text = session.get(PlannedSession, p["id"]).strength_text
            if text and session.get(StrengthLabel, (match.source_id, match.source_record_id)) is None:
                strength_store.save(session, match, text, now)
    return plans


def window(today: date) -> tuple[date, date]:
    return today - timedelta(days=7), today + timedelta(days=HORIZON_DAYS - 1)
