"""Fitness evidence: do independent body markers agree with what training load says?

Fitness (the 42-day load average) records how much you trained. This module asks whether your body adapted, from
markers the load number never sees. It never blends them into one made-up score: each marker reports its own direction,
change, sample size and uncertainty, and the verdict only counts how many agree.
- Markers: aerobic efficiency (speed per beat above resting HR on easy runs), critical speed, VO₂max, resting heart rate,
  your HRV level and heart-rate drift on steady runs (Pa:HR decoupling). Methods and sources are in athlete.py and
  performance.py; direction here is a straight-line fit over the window (log scale for ratios) with Newey-West errors
  (Newey & West 1987), because neighbouring days are not independent.
- A marker is "better" or "worse" only when the 95% interval of its change excludes zero and the change is at least a
  practical floor (the noise you would see anyway); otherwise it is "flat". Too little data in the window is "missing",
  never zero.
- Load side: fitness now against 42 days ago (±3% counts as steady).
- Everyday strain (heart-rate load outside workouts, from strain.py) is shown as context, not as a marker: it costs
  recovery but does not itself build aerobic fitness.
Associations over weeks, not proof that training caused them; no medical claims.
"""

from __future__ import annotations

from datetime import date, timedelta
from math import exp, log
from statistics import fmean, median

import numpy as np

from cadence_app.analytics import regress

DAY = timedelta(days=1)
LOAD_STEADY_PCT = 3.0
STRAIN_HIGH, STRAIN_LOW = 1.25, 0.8

# key: (label, window days, minimum points, practical floor, relative?, higher is better, unit, what it measures)
MARKERS = {
    "efficiency": ("Aerobic efficiency", 180, 8, 1.5, True, True, "%", "Speed per heartbeat above resting HR on easy runs."),
    "critical_speed": ("Critical speed", 180, 4, 1.5, True, True, "%", "The pace you can hold for 3–20 minutes, from your best efforts."),
    "vo2max": ("VO₂max (Garmin)", 180, 4, 1.5, True, True, "%", "Garmin's estimate; it moves in steps and lags."),
    "resting_hr": ("Resting heart rate", 84, 40, 1.0, False, False, " bpm", "Overnight resting HR; lower is the fitter direction."),
    "hrv": ("HRV level", 84, 40, 3.0, True, True, "%", "Overnight HRV: the level over weeks, not any one night."),
    "drift": ("Heart-rate drift", 120, 6, 1.0, False, False, " pts", "Pa:HR decoupling on steady runs; lower means better aerobic durability."),
}


def marker(key: str, points: list[tuple[date, float]], end: date) -> dict:
    label, window, min_n, floor, relative, higher_better, unit, note = MARKERS[key]
    start = end - window * DAY
    pts = sorted((d, v) for d, v in points if start < d <= end and v is not None and (v > 0 or not relative))
    out = {"key": key, "label": label, "note": note, "window_days": window, "n": len(pts), "state": "missing", "change": None, "ci": None, "unit": unit,
           "now": None, "before": None, "reason": None}
    if len(pts) < min_n:
        out["reason"] = f"{len(pts)} of {min_n} readings in the last {window} days"
        return out
    span = (pts[-1][0] - pts[0][0]).days
    if span < window * 0.5:
        out["reason"] = f"readings cover only {span} of {window} days"
        return out
    x = np.array([(d - pts[0][0]).days for d, _ in pts], dtype=float)
    y = np.array([log(v) if relative else v for _, v in pts])
    fit = regress.ols(np.column_stack([np.ones_like(x), x]), y, lags=min(7, len(pts) // 4))
    if fit is None:
        out["reason"] = "too little variation to fit a line"
        return out
    over = float(window)  # change across the whole window, not just the span of the data
    lo, hi = float(fit["ci"][1][0]) * over, float(fit["ci"][1][1]) * over
    mid = float(fit["coef"][1]) * over
    conv = (lambda v: (exp(v) - 1) * 100) if relative else (lambda v: v)
    change, ci = conv(mid), [conv(lo), conv(hi)]
    half = window // 2
    recent = [v for d, v in pts if d > end - half * DAY]
    earlier = [v for d, v in pts if d <= end - half * DAY]
    clear = lo > 0 or hi < 0
    sign = (1 if change > 0 else -1) * (1 if higher_better else -1)
    out.update(change=round(change, 1), ci=[round(ci[0], 1), round(ci[1], 1)],
               now=round(fmean(recent), 3) if recent else None, before=round(fmean(earlier), 3) if earlier else None,
               state=("better" if sign > 0 else "worse") if clear and abs(change) >= floor else "flat")
    return out


def load_side(pmc_by_day: dict, end: date) -> dict | None:
    now, then = pmc_by_day.get(end), pmc_by_day.get(end - 42 * DAY)
    if not now or not then or then["fitness"] < 8:
        return None
    pct = (now["fitness"] / then["fitness"] - 1) * 100
    return {"change_pct": round(pct, 1), "state": "up" if pct >= LOAD_STEADY_PCT else "down" if pct <= -LOAD_STEADY_PCT else "steady",
            "now": round(now["fitness"], 1), "then": round(then["fitness"], 1)}


def life_strain(strain: dict | None, end: date) -> dict | None:
    """Everyday (outside-workout) heart-rate load this week against your usual weeks."""
    if not strain:
        return None
    days = {d: v["everyday"] for d, v in strain["days"].items()}
    week = [days[d] for d in (end - i * DAY for i in range(7)) if d in days]
    weeks = []
    for k in range(1, 9):
        w = [days[d] for d in (end - (7 * k + i) * DAY for i in range(7)) if d in days]
        if len(w) >= 5:
            weeks.append(fmean(w))
    if len(week) < 5 or len(weeks) < 4:
        return {"state": "missing", "reason": "needs 5 days this week and 4 earlier weeks of all-day heart rate"}
    usual = median(weeks)
    ratio = fmean(week) / usual if usual > 0 else None
    if ratio is None:
        return {"state": "missing", "reason": "no everyday load in the earlier weeks"}
    state = "heavy" if ratio >= STRAIN_HIGH else "light" if ratio <= STRAIN_LOW else "usual"
    return {"state": state, "ratio": round(ratio, 2), "week": round(fmean(week), 1), "usual": round(usual, 1), "weeks": len(weeks),
            "note": "Everyday load costs recovery but doesn't build fitness; it is not part of the markers."}


def verdict(markers: list[dict], load: dict | None) -> dict:
    count = {s: sum(m["state"] == s for m in markers) for s in ("better", "worse", "flat", "missing")}
    judged = count["better"] + count["worse"] + count["flat"]
    summary = f"{count['better']} improving · {count['worse']} worsening · {count['flat']} unchanged · {count['missing']} not enough data"
    base = {"counts": count, "summary": summary, "judged": judged}
    if judged < 2:
        return {**base, "key": "unknown", "label": "Not enough evidence",
                "text": f"Only {judged} marker{'s' if judged != 1 else ''} has enough data in its window to judge. {summary}."}
    steady_or_up = load is None or load["state"] != "down"
    if count["worse"] >= 2 and count["worse"] > count["better"]:
        return {**base, "key": "not_adapting" if steady_or_up else "fading",
                "label": "Not adapting yet" if steady_or_up else "Fading",
                "text": ("Load is holding or rising but most body markers are moving the wrong way: more hard work is unlikely to help until recovery catches up. "
                         if steady_or_up else "Load has fallen and most body markers are moving the wrong way. ") + summary + "."}
    if count["better"] >= 2 and count["better"] > count["worse"]:
        return {**base, "key": "adapting", "label": "Adapting", "text": "Several independent markers say your body is responding to the training. " + summary + "."}
    return {**base, "key": "mixed", "label": "Mixed", "text": "The markers don't agree, so there is no clear answer from the body yet. " + summary + "."}


def report(c: dict) -> dict:
    memo = c.setdefault("_memo", {})  # shared by the cached copies of one context
    if "evidence" in memo:
        return memo["evidence"]
    end, s = c["as_of"], c["series"]
    perf = c.get("performance") or {}
    series = {
        "efficiency": [(p["day"], p["ef"]) for p in c.get("eff", [])],
        "critical_speed": [(h["day"], h["cs_mps"]) for h in perf.get("history", [])],
        "vo2max": list(c.get("vo2", [])),
        "resting_hr": list(s.get("resting_hr", {}).items()),
        "hrv": list(s.get("hrv", {}).items()),
        "drift": [(r["day"], r["decoupling_pct"]) for r in c.get("durability", []) if r.get("steady") and r.get("decoupling_pct") is not None],
    }
    markers = [marker(k, series[k], end) for k in MARKERS]
    load = load_side(c["pmc_by_day"], end)
    out = {"markers": markers, "load": load, "life_strain": life_strain(c.get("strain"), end), "verdict": verdict(markers, load)}
    memo["evidence"] = out
    return out
