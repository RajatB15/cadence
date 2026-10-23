"""Training-log views: a year of daily load, period totals, weekly roll-ups, sport mix and personal records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from cadence_app.analytics import athlete as A
from cadence_app.analytics import notes


def _totals(acts: list[A.Act], start: date, end: date) -> dict:
    window = [a for a in acts if start <= a.day <= end]
    return {
        "sessions": len(window),
        "hours": round(sum((a.moving_s or 0) for a in window) / 3600, 1),
        "km": round(sum((a.distance_m or 0) for a in window) / 1000, 1),
        "load": round(sum(a.load for a in window)),
        "active_days": len({a.day for a in window}),
    }


def _record(key: str, label: str, a: A.Act | None, value: float | None, kind: str) -> dict | None:
    if a is None or not value:
        return None
    return {"key": key, "label": label, "value": value, "kind": kind, "id": a.id, "day": a.day, "name": a.name, "family": a.family}


def summary(c: dict, family: str | None = None) -> dict:
    as_of = c["as_of"]
    acts = [a for a in c["acts"] if family in (None, "", a.family)]
    start = A.week_start(as_of - timedelta(days=364))

    days: dict[date, dict] = defaultdict(lambda: {"load": 0.0, "sessions": 0, "minutes": 0.0, "families": Counter()})
    for a in acts:
        if a.day >= start:
            d = days[a.day]
            d["load"] += a.load
            d["sessions"] += 1
            d["minutes"] += (a.moving_s or 0) / 60
            d["families"][a.family] += a.load or 1
    calendar = [
        {"day": d, "load": round(days[d]["load"]), "sessions": days[d]["sessions"], "minutes": round(days[d]["minutes"]),
         "family": days[d]["families"].most_common(1)[0][0] if days[d]["families"] else None}
        if d in days else {"day": d, "load": 0, "sessions": 0, "minutes": 0, "family": None}
        for d in A.daterange(start, as_of)
    ]

    hard = notes.hard_days(c)
    weeks: dict[date, dict] = {}
    for a in acts:
        w = weeks.setdefault(A.week_start(a.day), {"sessions": 0, "load": 0.0, "hours": 0.0, "km": 0.0, "hard_days": set(), "families": Counter()})
        w["sessions"] += 1
        w["load"] += a.load
        w["hours"] += (a.moving_s or 0) / 3600
        w["km"] += (a.distance_m or 0) / 1000
        w["families"][a.family] += 1
        if a.day in hard:
            w["hard_days"].add(a.day)
    week_rows = {
        ws.isoformat(): {"sessions": w["sessions"], "load": round(w["load"]), "hours": round(w["hours"], 1), "km": round(w["km"], 1),
                         "hard_days": len(w["hard_days"]), "families": dict(w["families"])}
        for ws, w in weeks.items()
    }

    mix: dict[str, dict] = defaultdict(lambda: {"sessions": 0, "hours": 0.0})
    for a in acts:
        if a.day > as_of - timedelta(days=365):
            mix[a.family]["sessions"] += 1
            mix[a.family]["hours"] += (a.moving_s or 0) / 3600
    mix_rows = sorted(({"family": f, "sessions": v["sessions"], "hours": round(v["hours"], 1)} for f, v in mix.items()),
                      key=lambda r: -r["hours"])

    runs = [a for a in acts if a.family == "run"]
    rides = [a for a in acts if a.family == "ride"]
    fast = [a for a in runs if a.speed_mps and (a.distance_m or 0) >= 5000]
    best = {
        "long_run": max(runs, key=lambda a: a.distance_m or 0, default=None),
        "fast_run": max(fast, key=lambda a: a.speed_mps or 0, default=None),
        "long_ride": max(rides, key=lambda a: a.distance_m or 0, default=None),
        "big_load": max(acts, key=lambda a: a.load, default=None),
        "long_session": max(acts, key=lambda a: a.moving_s or 0, default=None),
    }
    records = [r for r in (
        _record("long_run", "Longest run", best["long_run"], best["long_run"] and best["long_run"].distance_m, "distance"),
        _record("fast_run", "Fastest 5 km+ run", best["fast_run"], best["fast_run"] and 1000 / best["fast_run"].speed_mps, "pace"),
        _record("long_ride", "Longest ride", best["long_ride"], best["long_ride"] and best["long_ride"].distance_m, "distance"),
        _record("big_load", "Biggest session", best["big_load"], best["big_load"] and round(best["big_load"].load), "load"),
        _record("long_session", "Longest session", best["long_session"], best["long_session"] and best["long_session"].moving_s, "duration"),
    ) if r]

    week_streak = next((s for s in notes.streaks(c) if s["key"] == "weeks"), None)
    return {
        "has_data": True,
        "as_of": as_of,
        "calendar": calendar,
        "year": _totals(acts, as_of - timedelta(days=364), as_of),
        "last_30": _totals(acts, as_of - timedelta(days=29), as_of),
        "prev_30": _totals(acts, as_of - timedelta(days=59), as_of - timedelta(days=30)),
        "weeks": week_rows,
        "mix": mix_rows,
        "records": records,
        "streak": week_streak,
    }
