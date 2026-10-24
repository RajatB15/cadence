"""Goals: races, target performances, single-session distances and weight targets (assessed in analytics/goals.py)."""

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.analytics import goals as G
from cadence_app.analytics import plan as training_plan
from cadence_app.models import Goal

DISTANCE_LIMITS_M = {"run": (400.0, 250_000.0), "ride": (1_000.0, 1_500_000.0), "swim": (50.0, 60_000.0)}
TARGET_LIMITS_S = (60, 72 * 3600)
SPORT_NOUN = {"run": "run", "ride": "ride", "swim": "swim"}


class GoalError(ValueError):
    pass


def distance_label(sport: str, metres: float) -> str:
    for g in training_plan.GOALS.values():
        if sport == "run" and abs(g["distance_m"] - metres) < 0.5:
            return g["label"]
    if metres < 1000:
        return f"{metres:g} m"
    return f"{metres / 1000:g} km"


def clock(seconds: float) -> str:
    h, rem = divmod(round(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def as_dict(g: Goal) -> dict:
    return {"id": g.id, "kind": g.kind, "sport": g.sport, "title": g.title, "spec": json.loads(g.spec), "date": g.target_date, "status": g.status,
            "start_value": g.start_value, "created_on": g.created_at.date(), "closed_on": g.closed_at.date() if g.closed_at else None}


def listing(session: Session) -> list[dict]:
    rows = session.scalars(select(Goal).order_by(Goal.status, Goal.target_date.is_(None), Goal.target_date, Goal.id))
    return [as_dict(g) for g in rows]


def build(body: dict, today: date) -> tuple[str, str | None, dict, str]:
    """(kind, sport, spec, title) from a request body; raises GoalError."""
    kind, sport = body.get("kind"), body.get("sport")
    day = body.get("date")
    if kind not in G.KINDS:
        raise GoalError("Unknown goal type")
    if day is not None and day < today:
        raise GoalError("The goal date is in the past")
    if kind == "weight":
        kg = body.get("target_kg")
        if kg is None or not 30 <= kg <= 300:
            raise GoalError("Enter a target weight between 30 and 300 kg")
        return kind, None, {"target_kg": round(float(kg), 1)}, body.get("title") or f"{kg:g} kg"
    if sport not in G.SPORTS:
        raise GoalError("Choose run, ride or swim")
    metres = body.get("distance_m")
    lo, hi = DISTANCE_LIMITS_M[sport]
    if metres is None or not lo <= metres <= hi:
        raise GoalError(f"Distance for a {sport} must be between {distance_label(sport, lo)} and {distance_label(sport, hi)}")
    metres = float(metres)
    label = body.get("label") or distance_label(sport, metres)
    spec: dict = {"distance_m": metres, "label": label}
    target = body.get("target_s")
    if target is None and body.get("speed_kmh"):
        target = metres / (body["speed_kmh"] / 3.6)
    if target is not None:
        if not TARGET_LIMITS_S[0] <= target <= TARGET_LIMITS_S[1]:
            raise GoalError("That target time is out of range")
        spec["target_s"] = round(float(target))
    if kind == "race" and day is None:
        raise GoalError("A race needs a date")
    if kind == "performance" and "target_s" not in spec:
        raise GoalError("Give a target time or speed")
    if sport == "run" and (key := G.run_key(metres)):
        spec["key"] = key
    if kind == "race":
        default = f"{label} {SPORT_NOUN[sport]} race" if sport != "run" else f"{label} race"
    elif kind == "performance":
        default = f"{label} in {clock(spec['target_s'])}" if sport != "ride" else f"{label} in {clock(spec['target_s'])}"
    else:
        default = f"{label} {SPORT_NOUN[sport]}"
    return kind, sport, spec, (body.get("title") or default)[:120]


def create(session: Session, body: dict, today: date, now: datetime, start_value: float | None = None) -> dict:
    kind, sport, spec, title = build(body, today)
    if kind == "weight":  # one weight target at a time
        for old in session.scalars(select(Goal).where(Goal.kind == "weight", Goal.status == "active")):
            old.status, old.closed_at = "dropped", now
    g = Goal(kind=kind, sport=sport, title=title, spec=json.dumps(spec), target_date=body.get("date"), status="active",
             start_value=start_value if kind == "weight" else None, created_at=now)
    session.add(g)
    session.commit()
    return as_dict(g)


def update(session: Session, goal_id: int, body: dict, today: date, now: datetime) -> dict | None:
    """Edit title, date, targets or status. Changing a target regenerates the title unless one is given."""
    g = session.get(Goal, goal_id)
    if g is None:
        return None
    status = body.get("status")
    if status is not None:
        if status not in ("active", "achieved", "dropped"):
            raise GoalError("Unknown status")
        if status == "active" and g.kind == "weight":
            for other in session.scalars(select(Goal).where(Goal.kind == "weight", Goal.status == "active", Goal.id != g.id)):
                other.status, other.closed_at = "dropped", now
        g.status, g.closed_at = status, (None if status == "active" else now)
    spec_fields = {"distance_m", "label", "target_s", "speed_kmh", "target_kg"}
    if body.get("title") and not (spec_fields & body.keys() or "date" in body):
        g.title = body["title"][:120]
    elif spec_fields & body.keys() or "date" in body:
        spec = json.loads(g.spec)
        merged = {"kind": g.kind, "sport": g.sport, "date": body["date"] if "date" in body else g.target_date, "title": body.get("title"), **spec}
        if "date" in body and body["date"] != g.target_date and body["date"] is not None and body["date"] < today:
            raise GoalError("The goal date is in the past")
        for key in spec_fields & body.keys():
            merged[key] = body[key]
        if "speed_kmh" in body or "distance_m" in body:
            merged.setdefault("target_s", None)
            if "speed_kmh" in body:
                merged["target_s"] = body.get("target_s")
        if "distance_m" in body and "label" not in body:
            merged.pop("label", None)
        merged.pop("key", None)
        day = merged["date"]
        _, _, new_spec, title = build(merged, today)
        g.spec, g.target_date = json.dumps(new_spec), day
        if body.get("title"):
            g.title = body["title"][:120]
        elif spec_fields & body.keys():
            g.title = title
    session.commit()
    return as_dict(g)


def delete(session: Session, goal_id: int) -> bool:
    g = session.get(Goal, goal_id)
    if g is None:
        return False
    session.delete(g)
    session.commit()
    return True


# ---- views other modules need -----------------------------------------------------------------------


def primary_run_goal(session: Session, today: date) -> dict | None:
    """The nearest upcoming active run race at a standard distance, in the shape the weekly plan expects."""
    rows = session.scalars(select(Goal).where(Goal.kind == "race", Goal.sport == "run", Goal.status == "active", Goal.target_date >= today)
                           .order_by(Goal.target_date, Goal.id))
    for g in rows:
        spec = json.loads(g.spec)
        if spec.get("key") in training_plan.GOALS:
            return {"id": g.id, "distance": spec["key"], "date": g.target_date, "target_s": spec.get("target_s")}
    return None


def weight_target(session: Session) -> float | None:
    g = session.scalars(select(Goal).where(Goal.kind == "weight", Goal.status == "active").order_by(Goal.id.desc())).first()
    return float(json.loads(g.spec)["target_kg"]) if g else None


def set_primary_race(session: Session, goal: dict | None, today: date, now: datetime) -> None:
    """The older single-race setting: edits (or creates, or removes) the primary standard-distance run race."""
    current = None
    for g in session.scalars(select(Goal).where(Goal.kind == "race", Goal.sport == "run", Goal.status == "active", Goal.target_date >= today).order_by(Goal.target_date, Goal.id)):
        if json.loads(g.spec).get("key") in training_plan.GOALS:
            current = g
            break
    if goal is None:
        if current is not None:
            session.delete(current)
        session.commit()
        return
    g = training_plan.GOALS[goal["distance"]]
    body = {"kind": "race", "sport": "run", "date": goal["date"], "distance_m": g["distance_m"], "target_s": goal.get("target_s")}
    if current is None:
        create(session, body, today, now)
        return
    _, _, spec, title = build(body, today)
    current.spec, current.title, current.target_date = json.dumps(spec), title, goal["date"]
    session.commit()


def set_weight_target(session: Session, kg: float | None, start_value: float | None, today: date, now: datetime) -> None:
    if kg is None:
        for g in session.scalars(select(Goal).where(Goal.kind == "weight", Goal.status == "active")):
            session.delete(g)
        session.commit()
        return
    current = session.scalars(select(Goal).where(Goal.kind == "weight", Goal.status == "active").order_by(Goal.id.desc())).first()
    if current is not None and json.loads(current.spec)["target_kg"] == kg:
        return
    if current is not None:
        session.delete(current)
    create(session, {"kind": "weight", "target_kg": kg}, today, now, start_value)


def primary_sport_goal(session: Session, today: date) -> dict | None:
    """The nearest upcoming dated goal in a sport the weekly plan can't prescribe in detail (rides, swims, non-standard run distances).

    It still sets the phase (base, build, specific, taper, race week) and a long-session target for that sport.
    """
    rows = session.scalars(select(Goal).where(Goal.kind.in_(("race", "performance", "distance")), Goal.status == "active", Goal.target_date >= today)
                           .order_by(Goal.target_date, Goal.id))
    for g in rows:
        spec = json.loads(g.spec)
        if g.sport == "run" and spec.get("key") in training_plan.GOALS:
            continue
        metres = float(spec["distance_m"])
        return {"id": g.id, "sport": g.sport, "date": g.target_date, "distance_m": metres, "label": spec.get("label") or distance_label(g.sport, metres),
                "target_s": spec.get("target_s"), "kind": g.kind, "taper_weeks": G.taper_weeks(g.sport, metres) if g.kind != "distance" else 1}
    return None
