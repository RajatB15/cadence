"""Stored strength-class content: pasted text, parsed blocks and reusable templates."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.analytics import exercises as X
from cadence_app.models import Activity, StrengthLabel, StrengthTemplate

MAX_TEXT = 4000


def view(text: str, blocks: list[dict]) -> dict:
    return {"text": text, "blocks": blocks, "summary": X.summary(blocks)}


def _blocks(text: str, stored: str) -> list[dict]:
    """Parsed afresh from the saved text so parser improvements reach sessions saved earlier; the stored blocks are the fallback."""
    return X.parse(text) or json.loads(stored)


def get(session: Session, a: Activity) -> dict | None:
    row = session.get(StrengthLabel, (a.source_id, a.source_record_id))
    return view(row.text, _blocks(row.text, row.blocks)) if row else None


def save(session: Session, a: Activity, text: str, now: datetime, template: str | None = None) -> dict:
    text = text.strip()[:MAX_TEXT]
    blocks = X.parse(text)
    if not blocks:
        raise ValueError("No exercises recognised. Put block titles on their own lines (or start them with #).")
    row = session.get(StrengthLabel, (a.source_id, a.source_record_id))
    if row is None:
        session.add(StrengthLabel(source_id=a.source_id, source_record_id=a.source_record_id, text=text, blocks=json.dumps(blocks), updated_at=now))
    else:
        row.text, row.blocks, row.updated_at = text, json.dumps(blocks), now
    if template:
        existing = session.scalar(select(StrengthTemplate).where(StrengthTemplate.name == template.strip()[:80]))
        if existing:
            existing.text = text
        else:
            session.add(StrengthTemplate(name=template.strip()[:80], text=text, created_at=now))
    session.commit()
    return view(text, blocks)


def delete(session: Session, a: Activity) -> None:
    row = session.get(StrengthLabel, (a.source_id, a.source_record_id))
    if row:
        session.delete(row)
        session.commit()


def templates(session: Session) -> list[dict]:
    return [{"id": t.id, "name": t.name, "text": t.text} for t in session.scalars(select(StrengthTemplate).order_by(StrengthTemplate.name))]


def by_activity(session: Session, source_id: str) -> dict[int, dict]:
    """activity id -> {"blocks", "summary"} for every labelled session of a source."""
    rows = session.execute(
        select(Activity.id, StrengthLabel.text, StrengthLabel.blocks)
        .join(StrengthLabel, (StrengthLabel.source_id == Activity.source_id) & (StrengthLabel.source_record_id == Activity.source_record_id))
        .where(Activity.source_id == source_id)
    ).all()
    out = {}
    for activity_id, text, blocks in rows:
        parsed = _blocks(text, blocks)
        out[activity_id] = {"blocks": parsed, "summary": X.summary(parsed)}
    return out
