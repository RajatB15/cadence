"""Energy balance loading: calorie-target settings, burn snapshots during the day, and the inputs `analytics/energy.py` needs.

Snapshots (`energy_snapshots`) are derived and droppable: one row per day and time of day holding Garmin's burn so far, so the
projection can learn what share of the final total is usually burned by this hour. They are written from rows already in the
vault (no API calls), stamped with the time the value was imported, so a snapshot says when Garmin's number was true.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cadence_app import foodlog, localtime, profile as profile_store
from cadence_app.analytics import energy
from cadence_app.models import Activity, AppSetting, DailyMetric, EnergySnapshot, FoodEntry, Goal

KEY = "energy_target"
SNAPSHOT_EVERY_MIN = 20
KEEP_DAYS = 60
LOOKBACK_DAYS = 35


def load_settings(session: Session) -> dict:
    row = session.get(AppSetting, KEY)
    try:
        raw = json.loads(row.value) if row else None
    except ValueError:
        raw = None
    return energy.clean_settings(raw if isinstance(raw, dict) else None)


def save_settings(session: Session, values: dict) -> dict:
    """Merges the submitted fields into the stored settings after strict validation. Raises ValueError for a bad value."""
    energy.validate_settings(values)
    merged = {**load_settings(session), **{k: v for k, v in values.items() if k in energy.DEFAULT_SETTINGS}}
    if merged["mode"] == "manual" and not merged.get("manual_kcal"):
        raise ValueError("a manual target needs a number of kcal")
    cleaned = energy.clean_settings(merged)
    value = json.dumps(cleaned)
    row = session.get(AppSetting, KEY)
    if row is None:
        session.add(AppSetting(key=KEY, value=value))
    else:
        row.value = value
    session.commit()
    return cleaned


def _local(instant: datetime, tz_name: str | None) -> datetime:
    return instant.replace(tzinfo=UTC).astimezone(localtime.zone(tz_name))


def local_minute(instant: datetime, tz_name: str | None) -> int:
    t = _local(instant, tz_name)
    return t.hour * 60 + t.minute


def record_snapshot(session: Session, source_id: str, tz_name: str | None = None) -> bool:
    """Stores today's burn so far from the daily rows already in the vault. Skips stale or unchanged values; returns whether a row was added."""
    today = localtime.today_in(tz_name)
    rows = {m: (v, at) for m, v, at in session.execute(
        select(DailyMetric.metric, DailyMetric.value, DailyMetric.imported_at)
        .where(DailyMetric.source_id == source_id, DailyMetric.day == today, DailyMetric.metric.in_(("total_calories", "active_calories", "steps"))))}
    if "total_calories" not in rows:
        return False
    total, at = rows["total_calories"]
    if energy.pos(total) is None or _local(at, tz_name).date() != today:
        return False  # the value was fetched on another day: it is not a reading from today
    minute = local_minute(at, tz_name)
    last = session.scalars(select(EnergySnapshot).where(EnergySnapshot.source_id == source_id, EnergySnapshot.day == today)
                           .order_by(EnergySnapshot.taken_at_local_min.desc())).first()
    if last is not None and (minute - last.taken_at_local_min < SNAPSHOT_EVERY_MIN or last.total_kcal == total):
        return False
    session.add(EnergySnapshot(source_id=source_id, day=today, taken_at_local_min=minute, total_kcal=total,
                               active_kcal=rows.get("active_calories", (None,))[0], steps=rows.get("steps", (None,))[0]))
    session.execute(delete(EnergySnapshot).where(EnergySnapshot.source_id == source_id, EnergySnapshot.day < today - timedelta(days=KEEP_DAYS)))
    session.commit()
    return True


def _food_by_day(session: Session, since: date, today: date, weight_kg: float | None) -> dict[date, dict]:
    by_day: dict[date, list[dict]] = {}
    for e in session.scalars(select(FoodEntry).where(FoodEntry.day >= since, FoodEntry.day <= today)):
        by_day.setdefault(e.day, []).append({**foodlog.entry_dict(e), "kcal": e.kcal})
    return {d: foodlog.day_summary(items, weight_kg) for d, items in by_day.items()}


def load(session: Session, source_id: str, today: date, tz_name: str | None, weight_kg: float | None, hold: str | None) -> dict:
    """Everything `energy.assemble` needs, as keyword arguments (minus now_min)."""
    since = today - timedelta(days=LOOKBACK_DAYS)
    metrics: dict[date, dict[str, float]] = {}
    imported: dict[str, datetime] = {}
    for d, m, v, at in session.execute(
            select(DailyMetric.day, DailyMetric.metric, DailyMetric.value, DailyMetric.imported_at)
            .where(DailyMetric.source_id == source_id, DailyMetric.day >= since, DailyMetric.day <= today,
                   DailyMetric.metric.in_(("total_calories", "active_calories")))):
        metrics.setdefault(d, {})[m] = v
        if d == today and m == "total_calories":
            imported["total"] = at
    finals = {d: (v.get("total_calories"), v.get("active_calories")) for d, v in metrics.items() if d < today}
    snaps: dict[date, list[tuple[int, float]]] = {}
    for s in session.scalars(select(EnergySnapshot).where(EnergySnapshot.source_id == source_id, EnergySnapshot.day >= since, EnergySnapshot.day < today)):
        snaps.setdefault(s.day, []).append((s.taken_at_local_min, s.total_kcal))
    burn = None
    cur = metrics.get(today, {})
    if energy.pos(cur.get("total_calories")) is not None and "total" in imported and _local(imported["total"], tz_name).date() == today:
        burn = {"total": cur["total_calories"], "active": cur.get("active_calories"), "as_of_min": local_minute(imported["total"], tz_name)}
    workouts = [{"name": a.name, "kcal": a.calories, "type": a.activity_type} for a in session.scalars(
        select(Activity).where(Activity.source_id == source_id, Activity.local_date == today, Activity.calories > 0).order_by(Activity.start_time_utc))]
    prof = profile_store.load(session)
    if prof:
        prof = {**prof, "age_years": profile_store.age_years(prof["birth_date"], today)}
    goal = session.scalars(select(Goal).where(Goal.kind == "weight", Goal.status == "active")
                           .order_by(Goal.id.desc())).first()
    pace = None
    if goal is not None and goal.target_date is not None:
        pace = {"target_kg": float(json.loads(goal.spec)["target_kg"]), "days_left": (goal.target_date - today).days}
    elif goal is not None:
        pace = {"target_kg": float(json.loads(goal.spec)["target_kg"]), "days_left": 12 * 7}  # no date: a deliberately slow default horizon
    return {"finals": finals, "snapshots": snaps, "burn": burn, "workouts": workouts, "food": _food_by_day(session, today - timedelta(days=energy.SPARK_DAYS), today, weight_kg),
            "settings": load_settings(session), "profile": prof, "weight_kg": weight_kg, "pace": pace, "hold": hold}


def snapshot_count(session: Session, source_id: str) -> int:
    return session.scalar(select(func.count()).select_from(EnergySnapshot).where(EnergySnapshot.source_id == source_id)) or 0
