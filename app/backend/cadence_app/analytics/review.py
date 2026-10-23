"""Weekly and monthly reviews: what happened, how it compares with the period before, and one thing to change.

Every number is recomputed from stored data for the period, so past reviews never drift; the verdict and focus are
simple, visible rules rather than a black box.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from statistics import fmean, median

from cadence_app.analytics import athlete as A
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import recovery as R

DAY = timedelta(days=1)


def month_bounds(month: date) -> tuple[date, date]:
    start = month.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt - DAY


def _avg(values: list[float]) -> float | None:
    return round(fmean(values), 1) if values else None


def _window(series: A.Series, start: date, end: date) -> list[float]:
    return [series[d] for d in A.daterange(start, end) if d in series]


def summarise(c: dict, start: date, end: date, planned: list[dict], readiness_fn) -> dict:
    """Every section for one period; `end` is clipped to the data's last day."""
    end = min(end, c["as_of"])
    s = c["series"]
    acts = [a for a in c["acts"] if start <= a.day <= end]
    training = [a for a in acts if A.is_training(a)]
    runs = [a for a in training if a.family == "run"]
    load = sum(c["load"].get(d, 0.0) for d in A.daterange(start, end))
    split = A.intensity_split(acts, start)
    p0 = c["pmc_by_day"].get(start - DAY)
    p1 = c["pmc_by_day"].get(end)
    strain = (c.get("strain") or {}).get("days", {})
    need = (c.get("sleep_need") or {}).get("hours", R.DEFAULT_SLEEP_NEED)
    hours = _window(s.get("sleep_hours", {}), start, end)
    beds = _window(s.get("bedtime", {}), start, end)
    ready = [r["score"] for d in A.daterange(start, end) if (r := readiness_fn(c, d))]
    base_start = start - timedelta(days=60)
    hrv, rhr = _window(s.get("hrv", {}), start, end), _window(s.get("resting_hr", {}), start, end)
    hrv_base, rhr_base = _window(s.get("hrv", {}), base_start, start - DAY), _window(s.get("resting_hr", {}), base_start, start - DAY)
    warnings = sum(1 for d in A.daterange(start, end) if R.warning_signals(s, d))

    j = c.get("journal") or {}
    habits = []
    for b in j.get("behaviours", []):
        values = [v for d, v in j.get("answers", {}).get(b["key"], {}).items() if start <= d <= end]
        if values and any(values):
            habits.append({"key": b["key"], "label": b["label"], "days": sum(1 for v in values if v), "logged": len(values),
                           "total": round(sum(values)) if b["kind"] == "count" else None, "unit": b["unit"]})
    logged_days = len({d for vals in j.get("answers", {}).values() for d in vals if start <= d <= end})

    patterns: Counter = Counter()
    heavy = 0
    for a in training:
        label = c.get("labels", {}).get(a.id)
        if label:
            patterns.update(label["summary"]["patterns"].keys())
            heavy += label["summary"]["heavy_lower"]

    mine = [p for p in planned if start <= p["day"] <= end]
    done = [p for p in mine if p.get("status") == "done"]

    biggest = max(training, key=lambda a: a.load, default=None)
    longest = max(training, key=lambda a: a.moving_s or 0, default=None)
    fast = [a for a in runs if a.speed_mps and (a.distance_m or 0) >= 5000]
    fastest = max(fast, key=lambda a: a.speed_mps or 0, default=None)

    def act(a: A.Act | None, value: str) -> dict | None:
        return {"id": a.id, "name": a.name, "day": a.day, "value": value} if a else None

    weather = c.get("weather_runs") or {}
    hot = [w for aid, w in weather.items() if aid in {a.id for a in acts} and w.get("hot")]
    return {
        "start": start, "end": end, "days": (end - start).days + 1,
        "training": {
            "sessions": len(training), "by_sport": dict(Counter(a.family for a in training)), "hours": round(sum((a.moving_s or 0) for a in training) / 3600, 1),
            "run_km": round(sum((a.distance_m or 0) for a in runs) / 1000, 1),
            "ride_km": round(sum((a.distance_m or 0) for a in training if a.family == "ride") / 1000, 1),
            "load": round(load), "quality": sum(1 for a in training if A.is_hard(a)),
            "long_run_min": round(max(((a.moving_s or 0) / 60 for a in runs), default=0)),
            "easy_pct": split["easy_pct"] if split else None, "hard_sessions_pct": split.get("hard_sessions_pct") if split else None,
            "strain": round(sum(v["total"] for d, v in strain.items() if start <= d <= end)) if strain else None,
            "everyday_strain": round(sum(v["everyday"] for d, v in strain.items() if start <= d <= end)) if strain else None,
            "rest_days": sum(1 for d in A.daterange(start, end) if c["load"].get(d, 0) == 0),
        },
        "plan": {"planned": len(mine), "done": len(done), "missed": sum(1 for p in mine if p.get("status") == "missed"),
                 "predicted_load": round(sum(p["predicted"]["load"] for p in done)) if done else None,
                 "actual_load": round(sum((p.get("activity") or {}).get("load") or 0 for p in done)) if done else None},
        "fitness": {"start": round(p0["fitness"], 1) if p0 else None, "end": round(p1["fitness"], 1) if p1 else None,
                    "form": round(p1["form"], 1) if p1 else None, "acwr": p1["acwr"] if p1 else None},
        "recovery": {"readiness": _avg(ready), "hrv": _avg(hrv), "hrv_base": _avg(hrv_base), "rhr": _avg(rhr), "rhr_base": _avg(rhr_base),
                     "warning_days": warnings},
        "sleep": {"avg_hours": _avg(hours), "need": need, "nights_at_need": sum(1 for h in hours if R.sleep_ok(h, need)), "nights": len(hours),
                  "avg_bedtime_min": round(fmean(beds)) if beds else None,
                  "regularity": (r["sri"] if (r := R.sleep_regularity(s.get("bedtime", {}), s.get("wake_time", {}), start, end)) else None)},
        "habits": {"logged_days": logged_days, "items": sorted(habits, key=lambda h: -h["days"])},
        "strength": {"sessions": sum(1 for a in training if a.family == "strength"), "heavy_lower": heavy, "patterns": dict(patterns)},
        "highlights": [h for h in (
            act(biggest, f"load {round(biggest.load)}") if biggest and biggest.load > 0 else None,
            act(longest, f"{round((longest.moving_s or 0) / 60)} min") if longest else None,
            act(fastest, f"{_pace(1000 / fastest.speed_mps)}/km over {fastest.distance_m / 1000:.1f} km") if fastest else None,
        ) if h],
        "hot_sessions": len(hot),
    }


def _pace(seconds: float) -> str:
    m, s = divmod(round(seconds), 60)
    return f"{m}:{s:02d}"


def _delta(now: float | None, before: float | None) -> float | None:
    return round(now - before, 1) if now is not None and before is not None else None


def compare(now: dict, before: dict) -> dict:
    t, tb = now["training"], before["training"]
    return {
        "load": _delta(t["load"], tb["load"]), "sessions": _delta(t["sessions"], tb["sessions"]), "hours": _delta(t["hours"], tb["hours"]),
        "run_km": _delta(t["run_km"], tb["run_km"]),
        "readiness": _delta(now["recovery"]["readiness"], before["recovery"]["readiness"]),
        "sleep": _delta(now["sleep"]["avg_hours"], before["sleep"]["avg_hours"]),
        "fitness_change": _delta(_delta(now["fitness"]["end"], now["fitness"]["start"]), _delta(before["fitness"]["end"], before["fitness"]["start"])),
    }


def verdict(c: dict, r: dict, kind: str) -> str:
    t, f = r["training"], r["fitness"]
    if r["recovery"]["warning_days"] >= 2:
        return "Your body pushed back this " + ("week" if kind == "week" else "month")
    if kind == "month":
        if f["start"] and f["end"]:
            change = (f["end"] - f["start"]) / f["start"] * 100
            return f"Fitness up {change:.0f}%" if change >= 3 else f"Fitness down {abs(change):.0f}%" if change <= -3 else "Fitness held steady"
        return "A month of data"
    chronic = 7 * f["start"] if f["start"] else None
    ratio = t["load"] / chronic if chronic else None
    recovery_week = training_plan.is_recovery_week(c, r["start"]) if c.get("weeks") else False
    if ratio is None:
        return "Training logged"
    if recovery_week and ratio < 0.9:
        return "Recovery week done right"
    if ratio > 1.3:
        return "A big week: watch recovery"
    if ratio < 0.6 and not recovery_week:
        return "A light week"
    return "A solid training week" if t["quality"] >= 1 else "Steady aerobic week"


def focus(c: dict, r: dict) -> dict:
    """The single most useful change for next week, from a fixed priority list."""
    t, sl = r["training"], r["sleep"]
    runner = t["by_sport"].get("run", 0) >= 2
    if r["recovery"]["warning_days"] >= 2:
        return {"title": "Recover first", "detail": "Several days had illness/overreach signals. Keep next week easy until they're gone."}
    if sl["avg_hours"] is not None and sl["avg_hours"] < sl["need"] - 0.5:
        return {"title": "Sleep", "detail": f"You averaged {sl['avg_hours']:.1f} h against a {sl['need']:g} h need. Lights out 30 min earlier on weeknights."}
    if t["easy_pct"] is not None and t["easy_pct"] < 70:
        return {"title": "Slow the easy days", "detail": f"Only {t['easy_pct']}% of training time was easy. Keep easy sessions below your Zone 3 floor."}
    if t["sessions"] < 3:
        return {"title": "Consistency", "detail": "Fewer than three sessions. Protect three, even short ones."}
    if runner and t["long_run_min"] < 60:
        return {"title": "Long run", "detail": "No run over an hour. Add one easy long run, about 10 minutes longer than your recent longest."}
    if r["strength"]["sessions"] == 0 and runner:
        return {"title": "Strength", "detail": "No strength work. Two short sessions protect your running."}
    if t["quality"] == 0 and not training_plan.is_recovery_week(c, r["start"]):
        return {"title": "One quality session", "detail": "No hard session. Add one threshold workout from the Plan page."}
    return {"title": "Keep it rolling", "detail": "Repeat the pattern: it's working."}


def build(c: dict, kind: str, start: date, planned: list[dict], readiness_fn) -> dict:
    if kind == "week":
        start = A.week_start(start)
        end, prev = start + timedelta(days=6), start - timedelta(days=7)
        prev_end = start - DAY
    else:
        start, end = month_bounds(start)
        prev, prev_end = month_bounds(start - DAY)
    now = summarise(c, start, end, planned, readiness_fn)
    before = summarise(c, prev, prev_end, planned, readiness_fn)
    out = {"kind": kind, "complete": end <= c["as_of"], **now, "vs_previous": compare(now, before), "previous": {"start": prev, "end": prev_end},
           "verdict": verdict(c, now, kind), "focus": focus(c, now)}
    if kind == "month":
        out["trends"] = _month_trends(c, start, now["end"])
    return out


def _month_trends(c: dict, start: date, end: date) -> dict:
    hist = (c.get("performance") or {}).get("history") or []
    cs_now = next((h for h in reversed(hist) if h["day"] <= end), None)
    cs_before = next((h for h in reversed(hist) if h["day"] < start), None)
    eff_now = [p["ef"] for p in c["eff"] if start <= p["day"] <= end]
    eff_before = [p["ef"] for p in c["eff"] if start - timedelta(days=30) <= p["day"] < start]
    vo2 = [(d, v) for d, v in c["vo2"] if d <= end]
    vo2_before = [(d, v) for d, v in c["vo2"] if d < start]
    w = [kg for d, kg in c.get("weights", []) if start <= d <= end]
    w_before = [kg for d, kg in c.get("weights", []) if start - timedelta(days=30) <= d < start]
    return {
        "critical_speed_pace": [cs_before["pace_s"] if cs_before else None, cs_now["pace_s"] if cs_now else None],
        "efficiency_pct": round((median(eff_now) / median(eff_before) - 1) * 100, 1) if len(eff_now) >= 3 and len(eff_before) >= 3 else None,
        "vo2max": [vo2_before[-1][1] if vo2_before else None, vo2[-1][1] if vo2 else None],
        "weight": [round(fmean(w_before), 1) if w_before else None, round(fmean(w), 1) if w else None],
    }


def headline(r: dict) -> str:
    """One line for the push notification."""
    t = r["training"]
    parts = [f"{t['sessions']} sessions", f"{t['hours']:.1f} h"]
    if r["fitness"]["start"] and r["fitness"]["end"]:
        parts.append(f"fitness {r['fitness']['end'] - r['fitness']['start']:+.1f}")
    if r["sleep"]["avg_hours"]:
        parts.append(f"sleep {r['sleep']['avg_hours']:.1f} h")
    return " · ".join(parts) + f". Next: {r['focus']['title'].lower()}."
