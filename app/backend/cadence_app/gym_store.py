"""Saved gym sessions and the gym settings (which equipment you have at home). Validation and structure live in analytics/gym.py."""

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cadence_app import planner_store
from cadence_app.analytics import gym as G
from cadence_app.models import AppSetting, GymSession, GymWorkout, PlannedSession

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


def planned_copies(session: Session, gid: int) -> list[dict]:
    """Where this session is on the plan (newest first): [{plan_id, day, start_hour, logged}]. The plan holds copies, so this is how you find them."""
    rows = session.scalars(select(PlannedSession).where(PlannedSession.option_key == f"gym:{gid}").order_by(PlannedSession.day.desc(), PlannedSession.id.desc()).limit(12)).all()
    logged = logged_plan_ids(session, [r.id for r in rows])
    return [{"plan_id": r.id, "day": r.day, "start_hour": r.start_hour, "logged": r.id in logged} for r in rows]


def listing(session: Session) -> list[dict]:
    return [{**as_dict(r), "planned": planned_copies(session, r.id)} for r in session.scalars(select(GymSession).order_by(GymSession.updated_at.desc(), GymSession.id.desc()))]


def get(session: Session, gid: int) -> dict | None:
    row = session.get(GymSession, gid)
    return {**as_dict(row), "planned": planned_copies(session, gid)} if row else None


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
    snapshot = {"name": row.name, "setting": row.setting, "format": row.format, "steps": steps, "notes": row.notes}
    return planner_store.create(session, day, option, {**predicted, "gym_session_id": row.id, "setting": row.setting, "gym": snapshot}, now, G.to_text(row.name, steps))


def refresh_plan(session: Session, plan_id: int, now: datetime) -> dict | None:
    """Brings a planned copy up to date with the saved session it came from (steps, title, time). The predicted load is kept as it was. None when the
    plan isn't a gym copy or its saved session is gone."""
    p = session.get(PlannedSession, plan_id)
    if p is None or p.sport != "strength":
        return None
    predicted = json.loads(p.predicted)
    live = session.get(GymSession, predicted.get("gym_session_id") or 0)
    if live is None:
        return None
    steps = json.loads(live.steps)
    predicted["gym"] = {"name": live.name, "setting": live.setting, "format": live.format, "steps": steps, "notes": live.notes}
    predicted["setting"] = live.setting
    p.title, p.detail, p.minutes = live.name[:120], G.outline(steps), G.estimate_minutes(steps)
    p.strength_text, p.predicted = G.to_text(live.name, steps), json.dumps(predicted, default=str)
    session.commit()
    return plan_detail(session, plan_id)


def plan_detail(session: Session, plan_id: int) -> dict | None:
    """The plan to follow: the steps as they were when planned; for plans made before copies were kept, the saved session; else just the outline."""
    p = session.get(PlannedSession, plan_id)
    if p is None or p.sport != "strength":
        return None
    predicted = json.loads(p.predicted)
    snap = predicted.get("gym")
    source = "plan"
    if snap is None and predicted.get("gym_session_id"):
        live = session.get(GymSession, predicted["gym_session_id"])
        if live is not None:
            snap, source = {"name": live.name, "setting": live.setting, "format": live.format, "steps": json.loads(live.steps), "notes": live.notes}, "saved"
    base = {"id": p.id, "session_id": predicted.get("gym_session_id"), "day": p.day, "title": p.title, "minutes": p.minutes, "start_hour": p.start_hour, "predicted_load": predicted.get("load"), "detail": p.detail}
    if snap is None:
        return {**base, "steps": None, "setting": predicted.get("setting", "gym"), "format": "custom", "notes": None, "source": "text", "workout": workout_for_plan(session, plan_id)}
    steps = G.normalize(snap["steps"])
    return {**base, "steps": steps, "setting": snap.get("setting", "gym"), "format": snap.get("format", "custom"), "notes": snap.get("notes"), "source": source,
            "minutes": G.estimate_minutes(steps), "workout": workout_for_plan(session, plan_id)}


# --------------------------------------------------------------------- workouts you did
MAX_ENTRIES, MAX_SETS = 60, 40
SET_NUM = {"reps": (0, 500), "seconds": (0, 7200), "distance_m": (0, 100_000), "calories": (0, 500), "target_reps": (1, 500), "took_s": (0, 86400)}


def _clean_entries(entries: object) -> list[dict]:
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
        raise G.GymError(f"A workout needs 1 to {MAX_ENTRIES} exercises")
    out = []
    for e in entries:
        if not isinstance(e, dict):
            raise G.GymError("Each exercise entry must be an object")
        ex_id, name = e.get("exercise"), str(e.get("name") or "").strip()[:80]
        if ex_id is not None and G.exercise(str(ex_id)) is None:
            raise G.GymError(f"Unknown exercise: {ex_id}")
        if ex_id is None and not name:
            raise G.GymError("Each entry needs an exercise id or a name")
        sets = e.get("sets")
        if not isinstance(sets, list) or not 1 <= len(sets) <= MAX_SETS:
            raise G.GymError(f"Each exercise needs 1 to {MAX_SETS} sets")
        clean_sets = []
        for st in sets:
            if not isinstance(st, dict):
                raise G.GymError("Each set must be an object")
            one: dict = {"done": bool(st.get("done", True))}
            for key, (lo, hi) in SET_NUM.items():
                v = st.get(key)
                if v is None:
                    continue
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                    raise G.GymError(f"{key} must be a number from {lo} to {hi}")
                one[key] = int(v) if float(v).is_integer() else round(float(v), 1)
            load = st.get("load")
            if load is not None and str(load).strip():
                one["load"] = str(load).strip()[:40]
            clean_sets.append(one)
        entry: dict = {"sets": clean_sets}
        block = str(e.get("block") or "").strip()[:60]
        if block:
            entry["block"] = block
        entry["exercise" if ex_id is not None else "name"] = str(ex_id) if ex_id is not None else name
        out.append(entry)
    return out


def workout_dict(w: GymWorkout) -> dict:
    entries = json.loads(w.entries)
    sets = [st for e in entries for st in e["sets"]]
    return {"id": w.id, "day": w.day, "plan_id": w.plan_id, "session_id": w.session_id, "name": w.name, "setting": w.setting, "duration_s": w.duration_s, "rpe": w.rpe,
            "entries": [{**e, "label": G.exercise(e["exercise"])["name"] if "exercise" in e else e.get("name")} for e in entries], "notes": w.notes,
            "sets_done": sum(1 for st in sets if st.get("done")), "sets_total": len(sets)}


def log_workout(session: Session, day: date, name: str, setting: str, entries: object, plan_id: int | None, session_id: int | None, duration_s: int | None,
                notes: str | None, now: datetime, rpe: int | None = None) -> dict:
    name = (name or "").strip()[:80]
    if not name:
        raise G.GymError("Give the workout a name")
    if setting not in G.SETTINGS:
        raise G.GymError("setting must be gym or home")
    if rpe is not None and not 1 <= rpe <= 10:
        raise G.GymError("rpe must be from 1 to 10")
    row = GymWorkout(day=day, plan_id=plan_id, session_id=session_id, name=name, setting=setting, duration_s=duration_s, rpe=rpe,
                     entries=json.dumps(_clean_entries(entries)), notes=(notes.strip()[:2000] if notes and notes.strip() else None), created_at=now)
    session.add(row)
    session.commit()
    return workout_dict(row)


def workouts(session: Session, limit: int = 30) -> list[dict]:
    return [workout_dict(w) for w in session.scalars(select(GymWorkout).order_by(GymWorkout.day.desc(), GymWorkout.id.desc()).limit(limit))]


def workout_for_plan(session: Session, plan_id: int) -> dict | None:
    w = session.scalars(select(GymWorkout).where(GymWorkout.plan_id == plan_id).order_by(GymWorkout.id.desc())).first()
    return workout_dict(w) if w else None


def logged_plan_ids(session: Session, plan_ids: list[int]) -> set[int]:
    if not plan_ids:
        return set()
    return set(session.scalars(select(GymWorkout.plan_id).where(GymWorkout.plan_id.in_(plan_ids))))


def delete_workout(session: Session, wid: int) -> bool:
    w = session.get(GymWorkout, wid)
    if w is None:
        return False
    session.delete(w)
    session.commit()
    return True


def last_loads(session: Session, exercise_ids: list[str]) -> dict[str, dict]:
    """The most recent logged load (and reps) per exercise, from the last 80 workouts: used to prefill the next session. Nothing is invented."""
    want = {i for i in exercise_ids if G.exercise(i)}
    found: dict[str, dict] = {}
    for w in session.scalars(select(GymWorkout).order_by(GymWorkout.day.desc(), GymWorkout.id.desc()).limit(80)):
        for e in json.loads(w.entries):
            ex = e.get("exercise")
            if ex in want and ex not in found:
                done = [st for st in e["sets"] if st.get("done") and st.get("load")]
                if done:
                    best = done[-1]
                    found[ex] = {"load": best["load"], "reps": best.get("reps"), "seconds": best.get("seconds"), "day": w.day, "sets": len([st for st in e["sets"] if st.get("done")]),
                                 "hint": G.progression_hint(ex, e["sets"])}
        if len(found) == len(want):
            break
    return found

