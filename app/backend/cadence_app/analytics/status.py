"""Training status: is the last stretch progressing, maintaining, overloading, deloading, easing back or time off?

Each complete week is judged from three numbers, all from your own history:
- fitness change: the 42-day load average (CTL) at the end of the week against its start, in % (Banister-style load model);
- load ratio: the week's load against 7 × the fitness it started with (what "holding steady" would have asked);
- acute:chronic load at the week's end, with 0.8-1.3 as the productive range and above 1.5 as a spike (Gabbett 2016, BJSM).
Order of the rules: time off, easing back, overloading, deloading (or a planned recovery/taper week), detraining, progressing,
maintaining. The thresholds are rules of thumb for labelling, not medical or causal claims. The headline looks at the last
three complete weeks (the middle one decides ties) and is overridden only by time off now or an acute overload signal.
Fewer than MIN_WEEKS weeks of history, or fitness under MIN_FITNESS, gives "not enough data" rather than a guess.
"""

from __future__ import annotations

from datetime import date, timedelta

from cadence_app.analytics import athlete as A
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import timeoff as T

MIN_WEEKS = 4
MIN_FITNESS = 8.0
GAIN_PCT = 1.5  # fitness up by this much in a week counts as progressing
DROP_PCT = -3.0  # ...down by this much while training light counts as detraining
OVERLOAD_RATIO = 1.25
OVERLOAD_ACWR = 1.3
LIGHT_RATIO = 0.75
HOLD = (0.85, 1.15)

STATUSES = {
    "progressing": ("Progressing", "Fitness is rising on a load you can absorb."),
    "maintaining": ("Maintaining", "Fitness is holding steady on a steady load."),
    "overloading": ("Overloading", "Load or fatigue is running ahead of what you've built up."),
    "deloading": ("Deloading", "A lighter stretch so the work can turn into fitness."),
    "returning": ("Easing back", "Rebuilding after time off, on a ramp."),
    "off": ("Time off", "Travel, holiday, illness or injury took the week."),
    "detraining": ("Slipping", "Load has stayed low and fitness is falling."),
    "unknown": ("Not enough data", "Needs a few more weeks of training history."),
}


def _pct(a: float, b: float) -> float | None:
    return round((a / b - 1) * 100, 1) if b > 0 else None


def classify(row: dict, planned_deload: bool, prev_light: bool) -> tuple[str, str]:
    """Status and a one-line reason for one week's numbers (`row` from `week_row`)."""
    if row["availability"] < T.OFF_BELOW:
        return "off", f"{row['days_off']} of 7 days off, so no target was set."
    if row["ret"] < 0.95:
        return "returning", f"Easing back: the plan asked for about {round(row['scale'] * 100)}% of your usual load."
    if row["fitness_start"] is None or row["fitness_start"] < MIN_FITNESS:
        return "unknown", "Fitness is still too low to judge a trend."
    ratio, acwr = row["ratio"], row["acwr"]
    if (ratio is not None and ratio > OVERLOAD_RATIO) or (acwr is not None and acwr > OVERLOAD_ACWR) or row["fatigued"]:
        why = (f"Load was {round(ratio * 100)}% of your usual" if ratio and ratio > OVERLOAD_RATIO
               else f"Acute:chronic load ended at {acwr:.2f}" if acwr and acwr > OVERLOAD_ACWR else "Form ended deeply negative")
        return "overloading", f"{why}; more than the body usually absorbs in a week."
    ch = row["change_pct"]
    light = ratio is not None and ratio < LIGHT_RATIO
    if light and prev_light and ch is not None and ch <= DROP_PCT:
        return "detraining", f"Light for two weeks running ({round(ratio * 100)}% of usual) and fitness is down {abs(ch):.1f}%."
    if planned_deload or light:
        return "deloading", "A planned lighter week." if planned_deload else f"Load was {round(ratio * 100)}% of your usual."
    held = f" on {round(ratio * 100)}% of your usual load" if ratio else ""
    if ch is not None and ch >= GAIN_PCT:
        return "progressing", f"Fitness {ch:+.1f}%{held}."
    return "maintaining", f"Fitness {ch:+.1f}%{held}." if ch is not None else "A steady week."


def week_row(c: dict, ws: date) -> dict | None:
    pmc = c["pmc_by_day"]
    start, end = pmc.get(ws - timedelta(days=1)), pmc.get(ws + timedelta(days=6))
    week = next((w for w in c["weeks"] if w["week"] == ws), None)
    if week is None:
        return None
    cfg, periods, today = c.get("plan_settings") or T.DEFAULTS, c.get("time_off") or [], c.get("today", c["as_of"])
    scale = T.week_scale(periods, cfg, today, ws)
    fit0 = start["fitness"] if start else None
    chronic = 7 * fit0 if fit0 else None
    return {
        "week": ws, "load": round(week["load"]), "expected": round(chronic) if chronic else None,
        "ratio": round(week["load"] / chronic, 2) if chronic and chronic > 0 else None,
        "fitness_start": round(fit0, 1) if fit0 is not None else None, "fitness_end": round(end["fitness"], 1) if end else None,
        "change_pct": _pct(end["fitness"], fit0) if end and fit0 else None, "acwr": end["acwr"] if end else None,
        "fatigued": bool(end and end["fitness"] > 5 and end["form"] / end["fitness"] < -0.3),
        "sessions": week["total_sessions"], "availability": scale["availability"], "ret": scale["ret"], "scale": scale["scale"],
        "days_off": scale["days_off"], "complete": week["complete"],
    }


def report(c: dict, weeks: int = 12) -> dict:
    """Weekly statuses over the last `weeks` complete weeks, the headline and fitness slopes."""
    as_of = c["as_of"]
    this_ws = A.week_start(as_of)
    rows = []
    prev_light = False
    for i in range(weeks + 1, 0, -1):
        ws = this_ws - timedelta(weeks=i)
        r = week_row(c, ws)
        if r is None or not r["complete"]:
            continue
        deload = training_plan.phase(c, ws)["phase"] in ("recovery", "taper", "race")
        status, why = classify(r, deload, prev_light)
        prev_light = r["ratio"] is not None and r["ratio"] < LIGHT_RATIO
        rows.append({**r, "status": status, "label": STATUSES[status][0], "why": why})
    rows = rows[-weeks:]
    out = {"weeks": rows, "n": len(rows), "counts": {}, "current": None, "slope_4w": None, "slope_8w": None, "projection": None}
    for r in rows:
        out["counts"][r["status"]] = out["counts"].get(r["status"], 0) + 1
    if len(rows) < MIN_WEEKS:
        out["current"] = {"status": "unknown", "label": STATUSES["unknown"][0], "why": f"{len(rows)} of {MIN_WEEKS} weeks of history needed.", "blurb": STATUSES["unknown"][1]}
        return out

    cfg, periods, today = c.get("plan_settings") or T.DEFAULTS, c.get("time_off") or [], c.get("today", as_of)
    now_scale = T.week_scale(periods, cfg, today, this_ws)
    latest = c["pmc"][-1] if c["pmc"] else None
    recent = [r["status"] for r in rows[-3:]]
    pick = max(set(recent), key=lambda s: (recent.count(s), s == recent[-1]))
    status, why = pick, rows[-1]["why"]
    if now_scale["availability"] < T.OFF_BELOW and (as_of - this_ws).days >= 1:
        status, why = "off", "This week is mostly time off."
    elif now_scale["ret"] < 0.95 and now_scale["availability"] >= T.OFF_BELOW:
        status, why = "returning", "You are easing back from time off; the plan is on a ramp."
    elif latest and latest["acwr"] and latest["acwr"] > 1.5 and latest["fitness"] >= MIN_FITNESS:
        status, why = "overloading", f"Acute:chronic load is {latest['acwr']:.2f}, past the 1.5 spike line."
    elif status != "overloading":
        why = f"Last {len(recent)} weeks: " + ", ".join(STATUSES[s][0].lower() for s in recent) + "."
    out["current"] = {"status": status, "label": STATUSES[status][0], "why": why, "blurb": STATUSES[status][1]}

    series = [(r["week"], r["fitness_end"]) for r in rows if r["fitness_end"] is not None]
    for key, n in (("slope_4w", 4), ("slope_8w", 8)):
        if len(series) >= n and series[-n][1] > 0:
            first = series[-n][1]
            out[key] = round(((series[-1][1] / first) ** (1 / (n - 1)) - 1) * 100, 1) if n > 1 else None
    if out["slope_4w"] is not None and latest:
        rates = [x for x in (out["slope_4w"], out["slope_8w"]) if x is not None]
        lo, hi = min(rates), max(rates)
        out["projection"] = {"weeks": 4, "from": round(latest["fitness"]), "to": [round(latest["fitness"] * (1 + lo / 100) ** 4), round(latest["fitness"] * (1 + hi / 100) ** 4)],
                             "note": "Fitness in 4 weeks if the last 4 and 8 weeks' pace of change simply continues; a range, not a forecast."}
    return out
