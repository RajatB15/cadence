"""Phases: a named stretch of the calendar (Winter Arc, No Break November …) with the things you commit to inside it.

A phase stores only its name, dates and *pillars*; every number on the phase page is computed from the vault, so an offline
rebuild changes nothing. A pillar is one commitment, in one of four shapes:

* daily  — a day counts when it meets a bar (moved ≥ N minutes, steps, sleep hours, km). Gives hit/miss days, streaks and an
  optional number of rest passes, so "no break" is `passes = 0`.
* total  — a running total over the whole phase (km, hours, sessions, climbing, load) against a target, with a straight-line
  pace to compare with. A projection is only offered after two weeks of data.
* weekly — a bar for each Monday–Sunday week (sessions, km, hours, load). The partial weeks at either edge are never counted
  as misses.
* goal   — an outcome you want to reach by the end: weight, average or best pace, ride speed, longest session, resting HR,
  HRV, sleep, VO₂max. It is measured against where you started (the last reading before the phase, or the equal stretch before
  it for paces), shows progress along that line against the share of time elapsed, and says "no data" rather than guessing
  when there are too few sessions (paces need 3, recent-average vitals 4 readings).
* habit  — a journal behaviour answered "no" (alcohol, late caffeine …) or "yes" (mobility) on enough days. Days with no
  answer are *unknown*: they neither extend a streak nor break it, and are never counted as a miss.

Missing data is kept apart from zero throughout (a night with no sleep record is unknown, not a miss). Today is "pending"
until it meets the bar, never a miss. The vitals comparison (sleep, HRV, resting HR, weight: first weeks vs latest weeks) shows
sample sizes and states no cause. Pure algorithms are `assemble()` and the helpers above the storage section; `context()`
loads. Wording lives in the web app (`lib/phases.ts`).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.activity_types import ACTIVITY_FAMILIES, activity_family
from cadence_app.models import Activity, AppSetting, DailyMetric, JournalEntry, Phase, WeightReading

MAX_NAME, MAX_TAGLINE, MAX_PILLARS, MAX_DAYS = 80, 160, 6, 400
KINDS = ("daily", "total", "weekly", "habit", "goal")
DAILY_METRICS = {"moved": "min", "steps": "steps", "sleep_h": "h", "distance_km": "km"}
TOTAL_METRICS = {"distance_km": "km", "duration_h": "h", "sessions": "sessions", "ascent_m": "m", "load": "load"}
WEEKLY_METRICS = {"sessions": "sessions", "distance_km": "km", "duration_h": "h", "load": "load"}
# metric -> (unit, which way is better, lowest and highest target). Weight's direction comes from the target vs where you started.
GOAL_METRICS = {
    "weight_kg": ("kg", "auto", 30, 300), "run_pace": ("s/km", "lower", 150, 1200), "run_best_pace": ("s/km", "lower", 150, 1200),
    "ride_speed": ("km/h", "higher", 5, 60), "swim_pace": ("s/100m", "lower", 40, 400), "longest_km": ("km", "higher", 0.1, 1000),
    "resting_hr": ("bpm", "lower", 30, 100), "hrv": ("ms", "higher", 10, 250), "sleep_h": ("h", "higher", 4, 12),
    "vo2max": ("ml/kg/min", "higher", 20, 90),
}
GOAL_MIN_SESSIONS, GOAL_MIN_RECENT, GOAL_MIN_BASE, GOAL_MIN_DAYS, BEST_PACE_MIN_M = 3, 4, 5, 7, 3000
TARGET_LIMITS = {"min": (1, 1440), "steps": (500, 100_000), "h": (0.1, 24 * 400), "km": (0.1, 100_000), "sessions": (1, 2000),
                 "m": (10, 1_000_000), "load": (10, 1_000_000)}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
VITALS = {"sleep_hours": "sleep", "hrv": "hrv", "resting_hr": "resting_hr"}
VITAL_WINDOW, VITAL_MIN_N, VITAL_MIN_DAYS = 14, 5, 28
SEEDED_KEY = "phases_seeded"
GOAL_WEIGHT_LOOKBACK = 30


class PhaseError(ValueError):
    pass


# ---- validation --------------------------------------------------------------------------------


def clean_pillars(raw: list, known_habits: set[str]) -> list[dict]:
    if not isinstance(raw, list) or len(raw) > MAX_PILLARS:
        raise PhaseError(f"A phase can have up to {MAX_PILLARS} pillars")
    out = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict) or p.get("kind") not in KINDS:
            raise PhaseError("Each pillar needs a type")
        kind = p["kind"]
        label = str(p.get("label") or "").strip()[:60]
        family = p.get("family") or None
        if family is not None and family not in ACTIVITY_FAMILIES:
            raise PhaseError("Unknown activity type")
        item: dict = {"id": f"p{i + 1}", "kind": kind, "label": label, "family": family}
        if kind == "habit":
            key, want = p.get("behaviour"), p.get("want", "no")
            if key not in known_habits:
                raise PhaseError("Choose a habit from your journal")
            if want not in ("no", "yes"):
                raise PhaseError("A habit is either kept to “no” or to “yes”")
            item.update(metric="habit", behaviour=key, want=want, family=None, target=1)
        elif kind == "goal":
            metric, target = p.get("metric"), p.get("target")
            if metric not in GOAL_METRICS:
                raise PhaseError("Unknown goal")
            unit, _, lo, hi = GOAL_METRICS[metric]
            if not isinstance(target, (int, float)) or isinstance(target, bool) or not lo <= target <= hi:
                raise PhaseError(f"Target must be between {lo:g} and {hi:g} {unit}")
            item.update(metric=metric, target=float(target), family=family if metric == "longest_km" else None)
        else:
            metric = p.get("metric")
            table = {"daily": DAILY_METRICS, "total": TOTAL_METRICS, "weekly": WEEKLY_METRICS}[kind]
            if metric not in table:
                raise PhaseError("Unknown measure")
            target = p.get("target")
            lo, hi = TARGET_LIMITS[table[metric]]
            if not isinstance(target, (int, float)) or isinstance(target, bool) or not lo <= target <= hi:
                raise PhaseError(f"Target must be between {lo:g} and {hi:g} {table[metric]}")
            if metric in ("steps", "sleep_h"):
                item["family"] = None
            item.update(metric=metric, target=float(target))
        if kind in ("daily", "habit"):
            passes = p.get("passes", 0)
            if not isinstance(passes, int) or isinstance(passes, bool) or not 0 <= passes <= 60:
                raise PhaseError("Rest passes must be a whole number from 0 to 60")
            item["passes"] = passes
        out.append(item)
    return out


def clean(body: dict, known_habits: set[str]) -> dict:
    """Validated fields for a phase row from a request body; raises PhaseError."""
    name = str(body.get("name") or "").strip()
    if not name:
        raise PhaseError("Give the phase a name")
    start, end = body.get("start"), body.get("end")
    if not isinstance(start, date) or not isinstance(end, date):
        raise PhaseError("A phase needs a start and an end date")
    if end < start:
        raise PhaseError("The phase can’t end before it starts")
    if (end - start).days + 1 > MAX_DAYS:
        raise PhaseError(f"A phase can last at most {MAX_DAYS} days")
    color = body.get("color") or "#6cc7ff"
    if not HEX.match(color):
        raise PhaseError("Colour must be a #rrggbb value")
    return {
        "name": name[:MAX_NAME], "tagline": str(body.get("tagline") or "").strip()[:MAX_TAGLINE],
        "emoji": str(body.get("emoji") or "").strip()[:4], "color": color.lower(), "start_date": start, "end_date": end,
        "pillars": clean_pillars(body.get("pillars") or [], known_habits),
    }


# ---- pure assembly -----------------------------------------------------------------------------


@dataclass
class Inputs:
    """What assemble() needs, already loaded. `acts` covers the phase plus an equal stretch before it."""

    acts: list[dict] = field(default_factory=list)  # id, name, day, family, duration_s, distance_m, ascent_m, load
    metrics: dict[str, dict[date, float]] = field(default_factory=dict)  # steps, sleep_hours, hrv, resting_hr
    habits: dict[str, dict[date, float]] = field(default_factory=dict)  # behaviour key -> day -> answer
    weights: list[tuple[date, float]] = field(default_factory=list)
    first_activity_day: date | None = None  # earliest activity in the vault, to tell "no data" from "zero"


def days_between(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _matches(a: dict, family: str | None) -> bool:
    return family is None or a["family"] == family


def _act_value(a: dict, metric: str) -> float:
    return {
        "moved": a["duration_s"] / 60, "duration_h": a["duration_s"] / 3600, "sessions": 1.0,
        "distance_km": (a["distance_m"] or 0) / 1000, "ascent_m": a["ascent_m"] or 0, "load": a["load"] or 0,
    }[metric]


def _per_day(acts: list[dict], metric: str, family: str | None) -> dict[date, float]:
    out: dict[date, float] = defaultdict(float)
    for a in acts:
        if _matches(a, family):
            out[a["day"]] += _act_value(a, metric)
    return out


def _daily_value(p: dict, inp: Inputs, by_day: dict[date, float], d: date) -> float | None:
    m = p["metric"]
    if m in ("moved", "distance_km"):
        return by_day.get(d, 0.0)
    if m == "steps":
        return inp.metrics.get("steps", {}).get(d)
    if m == "sleep_h":
        return inp.metrics.get("sleep_hours", {}).get(d)
    return inp.habits.get(p["behaviour"], {}).get(d)  # habit


def _hit(p: dict, v: float) -> bool:
    if p["metric"] == "habit":
        return v == 0 if p["want"] == "no" else v > 0
    return v >= p["target"]


def _daily(p: dict, inp: Inputs, days: list[date], today: date) -> dict:
    by_day = _per_day(inp.acts, "moved" if p["metric"] == "moved" else "distance_km", p["family"]) if p["metric"] in ("moved", "distance_km") else {}
    cells, hits, misses, unknown, cur, best = [], 0, 0, 0, 0, 0
    for d in days:
        if d > today:
            cells.append({"day": d, "status": "future", "value": None})
            continue
        v = _daily_value(p, inp, by_day, d)
        if v is None:
            status = "pending" if d == today else "unknown"
            unknown += d != today
        elif _hit(p, v):
            status, hits, cur = "hit", hits + 1, cur + 1
            best = max(best, cur)
        elif d == today:
            status = "pending"
        else:
            status, misses, cur = "miss", misses + 1, 0
        cells.append({"day": d, "status": status, "value": round(v, 2) if v is not None else None})
    judged = hits + misses
    passes = p.get("passes", 0)
    rate = hits / judged if judged else None
    if not judged:
        status = "early"
    elif misses <= passes:
        status = "on"
    else:
        status = "slipping" if rate >= 0.8 else "behind"
    return {
        "hits": hits, "misses": misses, "unknown": unknown, "judged": judged, "rate": rate, "streak": cur, "best_streak": best,
        "passes": passes, "passes_left": max(0, passes - misses), "intact": misses <= passes, "status": status, "cells": cells,
    }


def _total(p: dict, inp: Inputs, start: date, end: date, days: list[date], today: date) -> dict:
    by_day = _per_day([a for a in inp.acts if start <= a["day"] <= end], p["metric"], p["family"])
    elapsed = max(0, (min(today, end) - start).days + 1)
    total_days = len(days)
    running, series = 0.0, []
    for d in days[:elapsed]:
        running += by_day.get(d, 0.0)
        series.append([d, round(running, 2)])
    target = p["target"]
    expected = target * elapsed / total_days
    ratio = running / expected if expected else None
    if running >= target:
        status = "complete"
    elif elapsed == 0:
        status = "upcoming"
    elif elapsed < 7 and total_days > 14:
        status = "early"
    else:
        status = "ahead" if ratio >= 1.05 else "on" if ratio >= 0.9 else "behind"
    missing = sum(1 for a in inp.acts if start <= a["day"] <= end and _matches(a, p["family"]) and p["metric"] == "load" and a["load"] is None)
    return {
        "value": round(running, 2), "pct": running / target, "expected": round(expected, 2), "status": status,
        "projection": round(running / elapsed * total_days, 1) if elapsed >= 14 and status != "complete" else None,
        "series": series, "missing": missing, "per_day_to_go": (target - running) / max(1, total_days - elapsed) if running < target and elapsed < total_days else None,
    }


def _weekly(p: dict, inp: Inputs, start: date, end: date, today: date) -> dict:
    by_day = _per_day([a for a in inp.acts if start <= a["day"] <= end], p["metric"], p["family"])
    weeks, hits, misses, best = [], 0, 0, 0.0
    w = monday(start)
    while w <= end:
        last = w + timedelta(days=6)
        value = sum(v for d, v in by_day.items() if w <= d <= last)
        partial = w < start or last > end
        current, future = w <= today <= last, w > today
        met = value >= p["target"]
        hit = True if met and not future else None if (partial or current or future) else False
        hits += hit is True
        misses += hit is False
        best = max(best, value)
        weeks.append({"start": w, "value": round(value, 2), "partial": partial, "current": current, "future": future, "hit": hit})
        w += timedelta(days=7)
    judged = hits + misses
    rate = hits / judged if judged else None
    status = "early" if not judged else "ahead" if rate == 1 and hits >= 3 else "on" if rate >= 0.75 else "behind"
    return {"weeks": weeks, "hits": hits, "misses": misses, "judged": judged, "rate": rate, "best": round(best, 2), "status": status}


def _mean(values: list[float], minimum: int) -> float | None:
    return fmean(values) if len(values) >= minimum else None


def _window(series: dict[date, float], lo: date, hi: date) -> list[float]:
    return [v for d, v in series.items() if lo <= d <= hi]


def _runs_value(metric: str, rows: list[dict]) -> float | None:
    """Pace or speed over some sessions; None when there are too few to say anything."""
    rows = [a for a in rows if a["distance_m"] and a["duration_s"] > 0]
    if metric == "run_best_pace":
        fast = [a["duration_s"] / a["distance_m"] * 1000 for a in rows if a["distance_m"] >= BEST_PACE_MIN_M]
        return min(fast) if fast else None
    if metric == "longest_km":
        return max(a["distance_m"] for a in rows) / 1000 if rows else None
    if len(rows) < GOAL_MIN_SESSIONS:
        return None
    dist, dur = sum(a["distance_m"] for a in rows), sum(a["duration_s"] for a in rows)
    return {"run_pace": dur / dist * 1000, "swim_pace": dur / dist * 100, "ride_speed": dist / dur * 3.6}[metric]


def _goal_values(p: dict, inp: Inputs, start: date, last: date) -> tuple[float | None, float | None, int]:
    """(where you started, where you are, how many sessions or readings that rests on)."""
    m = p["metric"]
    before = [a for a in inp.acts if a["day"] < start]
    inside = [a for a in inp.acts if start <= a["day"] <= last]
    fam = {"run_pace": "run", "run_best_pace": "run", "ride_speed": "ride", "swim_pace": "swim", "longest_km": p.get("family")}
    if m in fam:
        pick = lambda rows: [a for a in rows if _matches(a, fam[m])]  # noqa: E731
        return _runs_value(m, pick(before)), _runs_value(m, pick(inside)), len(pick(inside))
    if m == "weight_kg":
        pre = [w for d, w in inp.weights if d < start]
        now = [w for d, w in inp.weights if start <= d <= last]
        base = pre[-1] if pre else (now[0] if now else None)
        return base, (now[-1] if now else None), len(now)
    if m == "vo2max":
        pre = [a["vo2max"] for a in before if a["vo2max"]]
        now = [a["vo2max"] for a in inside if a["vo2max"]]
        return (pre[-1] if pre else None), (now[-1] if now else None), len(now)
    series = inp.metrics.get({"sleep_h": "sleep_hours"}.get(m, m), {})
    recent = _window(series, last - timedelta(days=6), last)
    base = _window(series, start - timedelta(days=14), start - timedelta(days=1))
    return _mean(base, GOAL_MIN_BASE), _mean(recent, GOAL_MIN_RECENT), len(recent)


def _goal(p: dict, inp: Inputs, start: date, end: date, today: date) -> dict:
    last = min(today, end)
    elapsed = max(0, (last - start).days + 1)
    base, cur, n = _goal_values(p, inp, start, last)
    target = p["target"]
    better = GOAL_METRICS[p["metric"]][1]
    if better == "auto":
        ref = base if base is not None else cur
        better = "lower" if ref is None or target < ref else "higher"
    progress = None
    if cur is not None and base is not None and target != base:
        progress = max(0.0, min(1.0, (cur - base) / (target - base)))
    met = cur is not None and (cur <= target if better == "lower" else cur >= target)
    frac = elapsed / ((end - start).days + 1)
    if cur is None:
        status = "early"
    elif met:
        status, progress = "complete", 1.0
    elif elapsed < GOAL_MIN_DAYS or progress is None:
        status = "early"
    else:
        status = "ahead" if progress >= frac + 0.1 else "on" if progress >= frac - 0.15 else "behind"
    return {"base": base, "current": cur, "better": better, "progress": progress, "n": n, "no_data": cur is None, "status": status}


def _pillar(p: dict, inp: Inputs, start: date, end: date, days: list[date], today: date) -> dict:
    base = {k: p.get(k) for k in ("id", "kind", "metric", "label", "family", "behaviour", "want", "target")}
    if p["kind"] in ("daily", "habit"):
        return {**base, **_daily(p, inp, days, today)}
    if p["kind"] == "total":
        return {**base, **_total(p, inp, start, end, days, today)}
    if p["kind"] == "goal":
        return {**base, **_goal(p, inp, start, end, today)}
    return {**base, **_weekly(p, inp, start, end, today)}


def _sums(acts: list[dict]) -> dict:
    fam: dict[str, dict] = defaultdict(lambda: {"sessions": 0, "duration_s": 0.0, "distance_m": 0.0})
    for a in acts:
        f = fam[a["family"]]
        f["sessions"] += 1
        f["duration_s"] += a["duration_s"]
        f["distance_m"] += a["distance_m"] or 0
    loads = [a["load"] for a in acts if a["load"] is not None]
    return {
        "sessions": len(acts), "duration_s": sum(a["duration_s"] for a in acts), "distance_m": sum(a["distance_m"] or 0 for a in acts),
        "ascent_m": sum(a["ascent_m"] or 0 for a in acts), "load": sum(loads) if loads else None,
        "active_days": len({a["day"] for a in acts}), "families": dict(fam),
    }


def _weekly_bars(acts: list[dict], start: date, end: date) -> list[dict]:
    out, w = [], monday(start)
    while w <= end:
        rows = [a for a in acts if w <= a["day"] <= w + timedelta(days=6)]
        loads = [a["load"] for a in rows if a["load"] is not None]
        out.append({"start": w, "sessions": len(rows), "minutes": round(sum(a["duration_s"] for a in rows) / 60),
                    "km": round(sum(a["distance_m"] or 0 for a in rows) / 1000, 1), "load": round(sum(loads)) if loads else None})
        w += timedelta(days=7)
    return out


def _brief(a: dict) -> dict:
    return {"id": a["id"], "name": a["name"], "day": a["day"], "family": a["family"], "duration_s": a["duration_s"],
            "distance_m": a["distance_m"], "ascent_m": a["ascent_m"]}


def _highlights(acts: list[dict], bars: list[dict]) -> dict:
    out: dict = {"longest": None, "biggest_climb": None, "biggest_week": None}
    if acts:
        out["longest"] = _brief(max(acts, key=lambda a: a["duration_s"]))
        climbs = [a for a in acts if a["ascent_m"]]
        out["biggest_climb"] = _brief(max(climbs, key=lambda a: a["ascent_m"])) if climbs else None
        week = max(bars, key=lambda b: b["minutes"])
        out["biggest_week"] = {k: week[k] for k in ("start", "sessions", "minutes", "km")} if week["minutes"] else None
    return out


def _vitals(inp: Inputs, start: date, last: date) -> dict:
    """First weeks vs latest weeks of the phase. Needs 4+ weeks elapsed and 5+ readings in each window; says nothing about cause."""
    out: dict = {}
    elapsed = (last - start).days + 1
    for metric, key in VITALS.items():
        series = inp.metrics.get(metric, {})
        first = [series[d] for d in days_between(start, start + timedelta(days=VITAL_WINDOW - 1)) if d in series and d <= last]
        recent = [series[d] for d in days_between(last - timedelta(days=VITAL_WINDOW - 1), last) if d in series and d >= start]
        ok = elapsed >= VITAL_MIN_DAYS and len(first) >= VITAL_MIN_N and len(recent) >= VITAL_MIN_N
        out[key] = {"first": fmean(first) if ok else None, "latest": fmean(recent) if ok else None, "n_first": len(first), "n_latest": len(recent)}
    inside = [(d, kg) for d, kg in inp.weights if start <= d <= last]
    out["weight"] = {"first": inside[0][1], "latest": inside[-1][1], "n": len(inside), "first_day": inside[0][0], "latest_day": inside[-1][0]} if len(inside) >= 2 else {"first": None, "latest": None, "n": len(inside)}
    return out


def _milestones(start: date, end: date, today: date, total_days: int, sums: dict, pillars: list[dict]) -> list[dict]:
    out = []
    for frac, label in ((0.25, "A quarter in"), (0.5, "Halfway"), (0.75, "Three quarters in")):
        day = start + timedelta(days=round(total_days * frac) - 1)
        out.append({"key": f"time{frac}", "label": label, "done": today >= day, "detail": None, "day": day})
    for n in (10, 25, 50, 100):
        out.append({"key": f"sessions{n}", "label": f"{n} sessions", "done": sums["sessions"] >= n, "detail": None, "day": None})
    for p in pillars:
        name = p["label"] or p["metric"]
        if p["kind"] in ("daily", "habit"):
            for n in (7, 14, 30, 60):
                if n < (end - start).days + 1:
                    out.append({"key": f"{p['id']}streak{n}", "label": f"{n}-day streak", "done": p["best_streak"] >= n, "detail": name, "day": None})
        elif p["kind"] == "goal":
            out.append({"key": f"{p['id']}half", "label": "Halfway to the goal", "done": (p["progress"] or 0) >= 0.5, "detail": name, "day": None})
            out.append({"key": f"{p['id']}goal", "label": "Goal reached", "done": p["status"] == "complete", "detail": name, "day": None})
        elif p["kind"] == "total":
            for pct in (50, 100):
                out.append({"key": f"{p['id']}pct{pct}", "label": f"{pct}% of target", "done": p["pct"] * 100 >= pct, "detail": name, "day": None})
    done = [m for m in out if m["done"]]
    # Everything reached, then only the next few not yet reached, so the list stays a story rather than a checklist wall.
    return done + [m for m in out if not m["done"]][:4]


def assemble(spec: dict, inp: Inputs, today: date) -> dict:
    start, end = spec["start_date"], spec["end_date"]
    days = days_between(start, end)
    total_days = len(days)
    state = "upcoming" if today < start else "done" if today > end else "active"
    last = min(today, end)
    elapsed = max(0, (last - start).days + 1)
    inside = [a for a in inp.acts if start <= a["day"] <= last]
    pillars = [_pillar(p, inp, start, end, days, today) for p in spec["pillars"]]
    sums = _sums(inside)
    bars = _weekly_bars(inside, start, last) if elapsed else []

    before_end = start - timedelta(days=1)
    before_start = start - timedelta(days=min(elapsed, total_days) or 1)
    available = inp.first_activity_day is not None and inp.first_activity_day <= before_start and elapsed > 0
    before_rows = [a for a in inp.acts if before_start <= a["day"] <= before_end]
    before = {"available": available, "start": before_start, "days": (before_end - before_start).days + 1, **_sums(before_rows)} if available else {"available": False}

    judged = [p for p in pillars if p["status"] not in ("upcoming", "early")]
    on_track = sum(p["status"] in ("ahead", "on", "complete") for p in judged)
    return {
        "name": spec["name"], "tagline": spec["tagline"], "emoji": spec["emoji"], "color": spec["color"], "start": start, "end": end,
        "state": state, "day_number": elapsed, "total_days": total_days, "days_left": max(0, (end - today).days) if state != "done" else 0,
        "starts_in": (start - today).days if state == "upcoming" else None, "pct": elapsed / total_days,
        "pillars": pillars, "on_track": on_track, "judged": len(judged),
        "totals": sums, "weeks": bars, "highlights": _highlights(inside, bars), "before": before,
        "days": [{"day": d, "minutes": round(m), "sessions": s} for d, m, s in _activity_days(inside, start, last)],
        "vitals": _vitals(inp, start, last) if elapsed else None,
        "milestones": _milestones(start, end, today, total_days, sums, pillars),
        "has_activity_data": inp.first_activity_day is not None,
    }


def _activity_days(acts: list[dict], start: date, last: date):
    mins, n = defaultdict(float), defaultdict(int)
    for a in acts:
        mins[a["day"]] += a["duration_s"] / 60
        n[a["day"]] += 1
    for d in days_between(start, last):
        yield d, mins.get(d, 0.0), n.get(d, 0)


# ---- storage and loading -----------------------------------------------------------------------


def _spec(row: Phase) -> dict:
    return {"name": row.name, "tagline": row.tagline, "emoji": row.emoji, "color": row.color, "start_date": row.start_date,
            "end_date": row.end_date, "pillars": json.loads(row.pillars)}


def context(session: Session, spec: dict, source_id: str, weight_sources: tuple[str, ...]) -> Inputs:
    """Everything a phase needs: activities from one phase-length before the start to its end, the daily series and habits."""
    start, end = spec["start_date"], spec["end_date"]
    reach = start - timedelta(days=(end - start).days + 1)
    acts = [
        {"id": a.id, "name": a.name, "day": a.local_date, "family": activity_family(a.activity_type), "duration_s": a.duration_s,
         "distance_m": a.distance_m, "ascent_m": a.elevation_gain_m, "load": a.training_load, "vo2max": a.vo2max}
        for a in session.scalars(select(Activity).where(Activity.source_id == source_id, Activity.local_date >= reach, Activity.local_date <= end).order_by(Activity.start_time_utc))
    ]
    metrics: dict[str, dict[date, float]] = defaultdict(dict)
    for day, metric, value in session.execute(
        select(DailyMetric.day, DailyMetric.metric, DailyMetric.value).where(
            DailyMetric.source_id == source_id, DailyMetric.metric.in_(("steps", *VITALS)), DailyMetric.day >= reach, DailyMetric.day <= end)
    ):
        metrics[metric][day] = value
    keys = {p["behaviour"] for p in spec["pillars"] if p["kind"] == "habit"}
    habits: dict[str, dict[date, float]] = defaultdict(dict)
    if keys:
        for day, key, value in session.execute(
            select(JournalEntry.day, JournalEntry.behaviour_key, JournalEntry.value).where(
                JournalEntry.behaviour_key.in_(keys), JournalEntry.day >= start, JournalEntry.day <= end)
        ):
            habits[key][day] = value
    weights = sorted(
        (d, float(w)) for d, w in session.execute(
            select(WeightReading.local_date, WeightReading.weight_kg).where(
                WeightReading.source_id.in_(weight_sources), WeightReading.local_date >= start - timedelta(days=GOAL_WEIGHT_LOOKBACK), WeightReading.local_date <= end)
        )
    )
    first = session.scalar(select(Activity.local_date).where(Activity.source_id == source_id).order_by(Activity.local_date).limit(1))
    return Inputs(acts, dict(metrics), dict(habits), weights, first)


def _row_dict(row: Phase) -> dict:
    return {"id": row.id, "created_at": row.created_at}


def get(session: Session, phase_id: int, today: date, source_id: str, weight_sources: tuple[str, ...]) -> dict | None:
    row = session.get(Phase, phase_id)
    if row is None:
        return None
    spec = _spec(row)
    return {**_row_dict(row), **assemble(spec, context(session, spec, source_id, weight_sources), today)}


def listing(session: Session, today: date, source_id: str, weight_sources: tuple[str, ...]) -> list[dict]:
    out = []
    for row in session.scalars(select(Phase).order_by(Phase.start_date.desc(), Phase.id.desc())):
        full = get(session, row.id, today, source_id, weight_sources)
        out.append({k: v for k, v in full.items() if k not in ("days", "weeks", "milestones", "vitals", "highlights", "before")})
    return out


def create(session: Session, fields: dict, now: datetime) -> int:
    row = Phase(created_at=now, **{**fields, "pillars": json.dumps(fields["pillars"])})
    session.add(row)
    session.commit()
    return row.id


def update(session: Session, phase_id: int, fields: dict) -> bool:
    row = session.get(Phase, phase_id)
    if row is None:
        return False
    for k, v in {**fields, "pillars": json.dumps(fields["pillars"])}.items():
        setattr(row, k, v)
    session.commit()
    return True


def delete(session: Session, phase_id: int) -> None:
    row = session.get(Phase, phase_id)
    if row is not None:
        session.delete(row)
        session.commit()


def ensure_default(session: Session, today: date, now: datetime) -> None:
    """Once, ever: the Winter Arc (1 Oct – 31 Dec) if it hasn't ended. Deleting it later doesn't bring it back."""
    if session.get(AppSetting, SEEDED_KEY) is not None:
        return
    session.add(AppSetting(key=SEEDED_KEY, value="1"))
    year = today.year
    if today <= date(year, 12, 31) and session.scalar(select(Phase.id).limit(1)) is None:
        create(session, {
            "name": "Winter Arc", "tagline": "Build quietly through the dark months.", "emoji": "❄️", "color": "#6cc7ff",
            "start_date": date(year, 10, 1), "end_date": date(year, 12, 31),
            "pillars": [
                {"id": "p1", "kind": "daily", "metric": "moved", "label": "", "family": None, "target": 20.0, "passes": 12},
                {"id": "p2", "kind": "weekly", "metric": "sessions", "label": "", "family": None, "target": 4.0},
                {"id": "p3", "kind": "daily", "metric": "sleep_h", "label": "", "family": None, "target": 7.0, "passes": 15},
            ],
        }, now)
    session.commit()
