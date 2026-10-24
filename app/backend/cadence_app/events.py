"""Events: several recorded activities grouped into one trek, expedition or multisport day.

Only the grouping is stored (`events`, `event_activities`, keyed by the source's activity id so an offline rebuild keeps it).
Activities stay untouched and keep counting on their own days in load and fitness, so grouping never double-counts.
Totals are plain sums over the linked activities; a field no activity reported stays None (missing, not zero).
Sleep and HRV come from the normal daily data, which Garmin keeps recording between stages when each day is its own activity.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cadence_app.activity_types import activity_family
from cadence_app.models import Activity, DailyMetric, Event, EventActivity

MAX_NAME = 120
RECOVERY_METRICS = {"sleep_hours": "sleep_h", "hrv": "hrv_ms", "resting_hr": "rhr"}


def _sum(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def totals(acts: list[Activity]) -> dict:
    """Totals over some activities. Average HR is weighted by duration; elapsed spans first start to last end."""
    if not acts:
        return {"count": 0}
    start = min(a.start_time_utc for a in acts)
    end = max(a.start_time_utc + timedelta(seconds=a.duration_s) for a in acts)
    hr = [(a.avg_hr, a.duration_s) for a in acts if a.avg_hr]
    maxes = [a.max_hr for a in acts if a.max_hr]
    return {
        "count": len(acts),
        "distance_m": _sum([a.distance_m for a in acts]),
        "duration_s": sum(a.duration_s for a in acts),
        "moving_s": sum(a.moving_duration_s or a.duration_s for a in acts),
        "elapsed_s": (end - start).total_seconds(),
        "elevation_gain_m": _sum([a.elevation_gain_m for a in acts]),
        "calories": _sum([a.calories for a in acts]),
        "training_load": _sum([a.training_load for a in acts]),
        "avg_hr": sum(h * d for h, d in hr) / sum(d for _, d in hr) if hr else None,
        "max_hr": max(maxes) if maxes else None,
    }


def _brief(a: Activity) -> dict:
    return {
        "id": a.id, "name": a.name, "type": a.activity_type, "family": activity_family(a.activity_type),
        "start_time_utc": a.start_time_utc, "timezone": a.timezone, "local_date": a.local_date,
        "duration_s": a.duration_s, "distance_m": a.distance_m, "elevation_gain_m": a.elevation_gain_m,
        "avg_hr": a.avg_hr, "training_load": a.training_load,
    }


def split(acts: list[Activity]) -> list[dict]:
    """Per calendar day (the activity's own local date), numbered from the first day; days without a recording are skipped
    but keep their number, so a rest day shows as a gap."""
    if not acts:
        return []
    by_day: dict[date, list[Activity]] = defaultdict(list)
    for a in sorted(acts, key=lambda a: a.start_time_utc):
        by_day[a.local_date].append(a)
    first = min(by_day)
    return [
        {"day": d, "number": (d - first).days + 1, "totals": totals(rows), "activities": [_brief(a) for a in rows]}
        for d, rows in sorted(by_day.items())
    ]


def assemble(name: str, acts: list[Activity], linked: int, recovery: dict[date, dict]) -> dict:
    days = split(acts)
    for d in days:
        d["recovery"] = recovery.get(d["day"])
    families = defaultdict(int)
    for a in acts:
        families[activity_family(a.activity_type)] += 1
    return {
        "name": name,
        "linked": linked,
        "missing": linked - len(acts),
        "start": days[0]["day"] if days else None,
        "end": days[-1]["day"] if days else None,
        "span_days": (days[-1]["day"] - days[0]["day"]).days + 1 if days else 0,
        "families": dict(families),
        "totals": totals(acts),
        "days": days,
    }


# ---- storage ---------------------------------------------------------------------------------


def _activities(session: Session, event_id: int) -> tuple[list[Activity], int]:
    keys = session.execute(
        select(EventActivity.source_id, EventActivity.source_record_id).where(EventActivity.event_id == event_id)
    ).all()
    acts = [
        a for sid, rid in keys
        if (a := session.scalar(select(Activity).where(Activity.source_id == sid, Activity.source_record_id == rid)))
    ]
    return acts, len(keys)


def _recovery(session: Session, source_ids: set[str], days: list[date]) -> dict[date, dict]:
    if not days or not source_ids:
        return {}
    out: dict[date, dict] = {d: {} for d in days}
    rows = session.execute(
        select(DailyMetric.day, DailyMetric.metric, DailyMetric.value).where(
            DailyMetric.source_id.in_(source_ids), DailyMetric.metric.in_(RECOVERY_METRICS), DailyMetric.day.in_(days)
        )
    )
    for day, metric, value in rows:
        out[day][RECOVERY_METRICS[metric]] = value
    return {d: v or None for d, v in out.items()}


def get(session: Session, event_id: int) -> dict | None:
    event = session.get(Event, event_id)
    if event is None:
        return None
    acts, linked = _activities(session, event_id)
    days = sorted({a.local_date for a in acts})
    out = assemble(event.name, acts, linked, _recovery(session, {a.source_id for a in acts}, days))
    return {"id": event.id, "created_at": event.created_at, **out}


def listing(session: Session) -> list[dict]:
    out = []
    for event in session.scalars(select(Event)):
        acts, linked = _activities(session, event.id)
        a = assemble(event.name, acts, linked, {})
        out.append({
            "id": event.id, "name": event.name, "start": a["start"], "end": a["end"], "span_days": a["span_days"],
            "families": a["families"], "totals": a["totals"], "linked": linked, "missing": a["missing"],
        })
    return sorted(out, key=lambda e: (e["start"] is None, e["start"]), reverse=True)


def membership(session: Session) -> dict[tuple[str, str], tuple[int, str]]:
    """(source, activity id) -> (event id, event name), for badges in the activity list."""
    return {
        (sid, rid): (eid, name)
        for sid, rid, eid, name in session.execute(
            select(EventActivity.source_id, EventActivity.source_record_id, Event.id, Event.name).join(
                Event, Event.id == EventActivity.event_id
            )
        )
    }


def _clean(name: str) -> str:
    name = " ".join(name.split())[:MAX_NAME]
    if not name:
        raise ValueError("Give the event a name")
    return name


def link(session: Session, event_id: int, acts: list[Activity]) -> None:
    """Add activities; one already in another event is refused rather than silently moved."""
    for a in acts:
        row = session.get(EventActivity, (a.source_id, a.source_record_id))
        if row is not None and row.event_id != event_id:
            other = session.get(Event, row.event_id)
            raise ValueError(f"“{a.name}” is already in “{other.name if other else 'another event'}”. Unlink it there first.")
        if row is None:
            session.add(EventActivity(source_id=a.source_id, source_record_id=a.source_record_id, event_id=event_id))


def create(session: Session, name: str, acts: list[Activity], now: datetime) -> int:
    if not acts:
        raise ValueError("Pick at least one activity")
    event = Event(name=_clean(name), created_at=now)
    session.add(event)
    session.flush()
    try:
        link(session, event.id, acts)
    except ValueError:
        session.rollback()
        raise
    session.commit()
    return event.id


def rename(session: Session, event_id: int, name: str) -> None:
    event = session.get(Event, event_id)
    if event is not None:
        event.name = _clean(name)
        session.commit()


def unlink(session: Session, event_id: int, a: Activity) -> None:
    """Remove one activity; an event left with no links is removed too."""
    session.execute(
        delete(EventActivity).where(
            EventActivity.event_id == event_id, EventActivity.source_id == a.source_id,
            EventActivity.source_record_id == a.source_record_id,
        )
    )
    left = session.scalar(select(func.count()).select_from(EventActivity).where(EventActivity.event_id == event_id))
    if not left:
        session.execute(delete(Event).where(Event.id == event_id))
    session.commit()


def delete_event(session: Session, event_id: int) -> None:
    """Dissolve an event; its activities are untouched."""
    session.execute(delete(EventActivity).where(EventActivity.event_id == event_id))
    session.execute(delete(Event).where(Event.id == event_id))
    session.commit()
