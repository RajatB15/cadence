"""Journal: a short daily check-in about yesterday's habits, stored per behaviour and day.

Answers are stored on the day the behaviour happened; the morning check-in asks about yesterday, and its effects show
up in that night's sleep and the next morning's HRV and readiness.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.models import Behaviour, JournalEntry

MAX_BACKFILL_DAYS = 60
MAX_COUNT = 30
KINDS = ("yes_no", "count")
# key, label, question (about yesterday), kind, unit
DEFAULTS = (
    ("alcohol", "Alcohol", "Alcoholic drinks yesterday?", "count", "drinks"),
    ("late_caffeine", "Late caffeine", "Caffeine after 14:00?", "yes_no", ""),
    ("late_meal", "Late meal", "A big meal within 2 hours of bed?", "yes_no", ""),
    ("screens_bed", "Screens in bed", "Phone or screens in bed?", "yes_no", ""),
    ("heat", "Sauna / hot bath", "Sauna, steam or a hot bath?", "yes_no", ""),
    ("stress", "Stressful day", "A stressful day?", "yes_no", ""),
    ("travel", "Travel", "Travel or a time-zone change?", "yes_no", ""),
    ("ill", "Felt ill", "Felt ill or run down?", "yes_no", ""),
    ("mobility", "Mobility", "Stretching or mobility work?", "yes_no", ""),
    ("nap", "Nap", "A daytime nap?", "yes_no", ""),
)


def ensure_catalogue(session: Session, now: datetime) -> None:
    """Adds any built-in behaviour that's missing; never re-activates one you switched off."""
    existing = set(session.scalars(select(Behaviour.key)))
    added = False
    for i, (key, label, question, kind, unit) in enumerate(DEFAULTS):
        if key not in existing:
            session.add(Behaviour(key=key, label=label, question=question, kind=kind, unit=unit, active=True,
                                  builtin=True, sort=i, created_at=now))
            added = True
    if added:
        session.commit()


def catalogue(session: Session, include_inactive: bool = True) -> list[Behaviour]:
    q = select(Behaviour).order_by(Behaviour.sort, Behaviour.label)
    if not include_inactive:
        q = q.where(Behaviour.active.is_(True))
    return list(session.scalars(q))


def behaviour_dict(b: Behaviour) -> dict:
    return {"key": b.key, "label": b.label, "question": b.question, "kind": b.kind, "unit": b.unit,
            "active": b.active, "builtin": b.builtin}


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40] or "habit"


def add_behaviour(session: Session, label: str, question: str, kind: str, unit: str, now: datetime) -> Behaviour:
    if kind not in KINDS:
        raise ValueError("Unknown kind")
    key = base = "my_" + slug(label)
    n = 2
    while session.get(Behaviour, key) is not None:
        key, n = f"{base}_{n}", n + 1
    b = Behaviour(key=key, label=label.strip(), question=question.strip() or f"{label.strip()}?", kind=kind, unit=unit.strip(),
                  active=True, builtin=False, sort=100, created_at=now)
    session.add(b)
    session.commit()
    return b


def update_behaviour(session: Session, key: str, *, active: bool | None = None, label: str | None = None,
                     question: str | None = None) -> Behaviour | None:
    b = session.get(Behaviour, key)
    if b is None:
        return None
    if active is not None:
        b.active = active
    if label is not None and not b.builtin:
        b.label = label.strip()
    if question is not None and not b.builtin:
        b.question = question.strip()
    session.commit()
    return b


def validate(b: Behaviour, value: float) -> float:
    if b.kind == "yes_no":
        if value not in (0, 1):
            raise ValueError(f"{b.label}: answer yes or no")
        return float(value)
    if not 0 <= value <= MAX_COUNT:
        raise ValueError(f"{b.label}: enter 0–{MAX_COUNT}")
    return float(round(value))


def save_day(session: Session, day: date, answers: dict[str, float], today: date, now: datetime) -> dict[str, float]:
    """Stores a day's answers. Active behaviours left out count as "no"/0: the check-in is all-or-nothing."""
    if day >= today:
        raise ValueError("Log a day once it's over")
    if day < today - timedelta(days=MAX_BACKFILL_DAYS):
        raise ValueError(f"Only the last {MAX_BACKFILL_DAYS} days can be logged")
    by_key = {b.key: b for b in catalogue(session)}
    unknown = set(answers) - set(by_key)
    if unknown:
        raise ValueError(f"Unknown habit: {sorted(unknown)[0]}")
    values = {k: validate(by_key[k], v) for k, v in answers.items()}
    for b in by_key.values():
        if b.active:
            values.setdefault(b.key, 0.0)
    existing = {e.behaviour_key: e for e in session.scalars(select(JournalEntry).where(JournalEntry.day == day))}
    for key, value in values.items():
        if key in existing:
            existing[key].value, existing[key].answered_at = value, now
        else:
            session.add(JournalEntry(day=day, behaviour_key=key, value=value, answered_at=now))
    session.commit()
    return values


def entries(session: Session, since: date | None = None) -> dict[str, dict[date, float]]:
    """behaviour key -> {day: value}."""
    q = select(JournalEntry.behaviour_key, JournalEntry.day, JournalEntry.value)
    if since:
        q = q.where(JournalEntry.day >= since)
    out: dict[str, dict[date, float]] = {}
    for key, day, value in session.execute(q):
        out.setdefault(key, {})[day] = value
    return out


def days(session: Session, since: date) -> list[dict]:
    rows: dict[date, dict[str, float]] = {}
    for key, day, value in session.execute(
        select(JournalEntry.behaviour_key, JournalEntry.day, JournalEntry.value).where(JournalEntry.day >= since)
    ):
        rows.setdefault(day, {})[key] = value
    return [{"day": d, "answers": rows[d]} for d in sorted(rows, reverse=True)]


def checkin(session: Session, today: date) -> dict:
    """Yesterday's check-in: done once any answer for it is stored."""
    day = today - timedelta(days=1)
    done = session.scalar(select(JournalEntry.id).where(JournalEntry.day == day).limit(1)) is not None
    return {"day": day, "done": done}
