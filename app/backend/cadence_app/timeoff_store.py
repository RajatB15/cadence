"""Time off (travel, holiday, illness, injury) and the plan settings, written only by you."""

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.analytics import timeoff
from cadence_app.models import AppSetting, TimeOff

SETTINGS_KEY = "plan_settings"
MAX_DAYS = 120


class TimeOffError(ValueError):
    pass


def as_dict(row: TimeOff) -> dict:
    return {"id": row.id, "kind": row.kind, "start": row.start_date, "end": row.end_date, "activity": row.activity, "severity": row.severity,
            "return_weeks": row.return_weeks, "return_start_pct": row.return_start_pct, "note": row.note}


def entries(session: Session) -> list[dict]:
    return [as_dict(r) for r in session.scalars(select(TimeOff).order_by(TimeOff.start_date))]


def settings(session: Session) -> dict:
    row = session.get(AppSetting, SETTINGS_KEY)
    try:
        raw = json.loads(row.value) if row else None
    except ValueError:
        raw = None
    return timeoff.clean_settings(raw if isinstance(raw, dict) else None)


def save_settings(session: Session, values: dict) -> dict:
    """Merges the given fields into the stored settings; a null resets that field to its default."""
    row = session.get(AppSetting, SETTINGS_KEY)
    try:
        stored = json.loads(row.value) if row else {}
    except ValueError:
        stored = {}
    for key, v in values.items():
        if key not in timeoff.SETTINGS:
            continue
        if v is None:
            stored.pop(key, None)
            continue
        lo, hi = timeoff.SETTINGS[key][1:]
        if key == "away_activity":
            if v not in timeoff.ACTIVITIES:
                raise TimeOffError("away_activity must be none, light or full")
        elif not lo <= v <= hi:
            raise TimeOffError(f"{key} must be between {lo:g} and {hi:g}")
        stored[key] = v
    if row:
        row.value = json.dumps(stored)
    else:
        session.add(AppSetting(key=SETTINGS_KEY, value=json.dumps(stored)))
    session.commit()
    return timeoff.clean_settings(stored)


def _check(values: dict) -> None:
    if values["kind"] not in timeoff.KINDS:
        raise TimeOffError("kind must be travel, vacation, sick or injury")
    if values["end"] is not None and values["end"] < values["start"]:
        raise TimeOffError("The end date is before the start")
    if values["end"] is not None and (values["end"] - values["start"]).days >= MAX_DAYS:
        raise TimeOffError(f"Time off is capped at {MAX_DAYS} days")
    if values.get("activity") is not None and values["activity"] not in timeoff.ACTIVITIES:
        raise TimeOffError("activity must be none, light or full")
    if values.get("severity") is not None and values["severity"] not in (1, 2, 3):
        raise TimeOffError("severity must be 1, 2 or 3")
    if values.get("return_weeks") is not None and not 0 <= values["return_weeks"] <= 8:
        raise TimeOffError("return_weeks must be between 0 and 8")
    if values.get("return_start_pct") is not None and not 20 <= values["return_start_pct"] <= 100:
        raise TimeOffError("return_start_pct must be between 20 and 100")


def _apply(row: TimeOff, values: dict) -> None:
    row.kind, row.start_date, row.end_date = values["kind"], values["start"], values["end"]
    away = values["kind"] in ("travel", "vacation")
    # Settings only meaningful for the kind are kept; the rest are dropped so an edit never leaves stale numbers behind.
    row.activity = values.get("activity") if away else None
    row.severity = values.get("severity") if not away else None
    row.return_weeks = values.get("return_weeks")
    row.return_start_pct = values.get("return_start_pct")
    note = (values.get("note") or "").strip()[:200]
    row.note = note or None


def create(session: Session, values: dict, now: datetime) -> dict:
    _check(values)
    row = TimeOff(created_at=now)
    _apply(row, values)
    session.add(row)
    session.commit()
    return as_dict(row)


def update(session: Session, entry_id: int, values: dict) -> dict | None:
    row = session.get(TimeOff, entry_id)
    if row is None:
        return None
    merged = {**as_dict(row), **values}
    _check(merged)
    _apply(row, merged)
    session.commit()
    return as_dict(row)


def delete(session: Session, entry_id: int) -> bool:
    row = session.get(TimeOff, entry_id)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def view(session: Session, today: date) -> dict:
    cfg = settings(session)
    items = entries(session)
    return {"today": today, "settings": cfg, "defaults": timeoff.DEFAULTS,
            "ranges": {k: {"min": v[1], "max": v[2]} for k, v in timeoff.SETTINGS.items() if v[1] is not None},
            "items": [timeoff.describe(p, cfg, today) for p in items]}
