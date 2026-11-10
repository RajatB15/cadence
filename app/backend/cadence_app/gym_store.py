"""Saved gym sessions and the gym settings (which equipment you have at home). Validation and structure live in analytics/gym.py."""

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cadence_app import planner_store
from cadence_app.analytics import gym as G
from cadence_app.models import AppSetting, GymSession

HOME_KEY, DEFAULT_KEY = "gym_home_equipment", "gym_default_setting"
FORMATS = ("straight", "circuit", "hybrid", "hyrox", "custom")
MAX_SESSIONS = 200


def _setting(session: Session, key: str) -> str | None:
    row = session.get(AppSetting, key)
    return row.value if row else None


def _put(session: Session, key: str, value: str | None) -> None:
    row = session.get(AppSetting, key)
    if value is None:
        if row:
            session.delete(row)
    elif row:
        row.value = value
    else:
        session.add(AppSetting(key=key, value=value))


def settings(session: Session) -> dict:
    try:
        home = json.loads(_setting(session, HOME_KEY) or "[]")
    except ValueError:
        home = []
    home = [e for e in home if e in G.equipment_names()] if isinstance(home, list) else []
    default = _setting(session, DEFAULT_KEY)
    return {"home_equipment": home, "default_setting": default if default in G.SETTINGS else "gym", "equipment": G.equipment_names()}


def set_settings(session: Session, home_equipment: list[str] | None, default_setting: str | None) -> dict:
    if home_equipment is not None:
        bad = [e for e in home_equipment if e not in G.equipment_names()]
        if bad:
            raise G.GymError("Unknown equipment: " + ", ".join(bad))
        _put(session, HOME_KEY, json.dumps(sorted(set(home_equipment))))
    if default_setting is not None:
        if default_setting not in G.SETTINGS:
            raise G.GymError("setting must be gym or home")
        _put(session, DEFAULT_KEY, default_setting)
    session.commit()
    return settings(session)


def owned(session: Session, setting: str) -> set[str]:
    return G.owned_set(setting, settings(session)["home_equipment"])


def as_dict(row: GymSession) -> dict:
    steps = json.loads(row.steps)
    ids = G.exercise_ids(steps)
    return {"id": row.id, "name": row.name, "setting": row.setting, "format": row.format, "steps": steps, "notes": row.notes, "exercises": len(ids),
            "minutes": G.estimate_minutes(steps), "patterns": sorted({G.exercise(i)["pattern"] for i in ids}), "outline": G.outline(steps),
            "created_at": row.created_at, "updated_at": row.updated_at}


def listing(session: Session) -> list[dict]:
    return [as_dict(r) for r in session.scalars(select(GymSession).order_by(GymSession.updated_at.desc(), GymSession.id.desc()))]


def get(session: Session, gid: int) -> dict | None:
    row = session.get(GymSession, gid)
    return as_dict(row) if row else None


def _clean(name: str, setting: str, fmt: str, steps: object, notes: str | None) -> tuple[str, str, str, list[dict], str | None]:
    name = (name or "").strip()[:80]
    if not name:
        raise G.GymError("Give the session a name")
    if setting not in G.SETTINGS:
        raise G.GymError("setting must be gym or home")
    if fmt not in FORMATS:
        raise G.GymError("Unknown format")
    return name, setting, fmt, G.normalize(steps), (notes.strip()[:2000] if notes and notes.strip() else None)


def create(session: Session, name: str, setting: str, fmt: str, steps: object, notes: str | None, now: datetime) -> dict:
    if session.scalar(select(func.count(GymSession.id))) >= MAX_SESSIONS:
        raise G.GymError(f"At most {MAX_SESSIONS} saved sessions; delete some first")
    name, setting, fmt, clean, notes = _clean(name, setting, fmt, steps, notes)
    row = GymSession(name=name, setting=setting, format=fmt, steps=json.dumps(clean), notes=notes, created_at=now, updated_at=now)
    session.add(row)
    session.commit()
    return as_dict(row)


def update(session: Session, gid: int, fields: dict, now: datetime) -> dict | None:
    row = session.get(GymSession, gid)
    if row is None:
        return None
    name, setting, fmt, steps, notes = _clean(fields.get("name", row.name), fields.get("setting", row.setting), fields.get("format", row.format),
                                              fields.get("steps", json.loads(row.steps)), fields["notes"] if "notes" in fields else row.notes)
    row.name, row.setting, row.format, row.steps, row.notes, row.updated_at = name, setting, fmt, json.dumps(steps), notes, now
    session.commit()
    return as_dict(row)


def delete(session: Session, gid: int) -> bool:
    row = session.get(GymSession, gid)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def plan(session: Session, gid: int, day: date, start_hour: int | None, predicted: dict, now: datetime) -> dict | None:
    """Puts a snapshot of the session on a day as an ordinary planned strength session (so the week, plan vs actual and the pattern notes work)."""
    row = session.get(GymSession, gid)
    if row is None:
        return None
    steps = json.loads(row.steps)
    minutes = G.estimate_minutes(steps)
    option = {"key": f"gym:{row.id}", "sport": "strength", "kind": "gym", "title": row.name, "detail": G.outline(steps), "minutes": minutes,
              "start_hour": start_hour, "steps": None}
    out = planner_store.create(session, day, option, {**predicted, "gym_session_id": row.id, "setting": row.setting}, now, G.to_text(row.name, steps))
    return out
