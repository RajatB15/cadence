"""Goals and feasibility: races, target performances, single-session distances and weight, in run, ride and swim.

Each goal is assessed against what your own data say you can do now and how fast that has been changing. Nothing here
predicts the future or gives medical advice; it states what the numbers imply, with the uncertainty that went in.

- Run races / performances with a valid critical-speed fit (Monod & Scherrer; Jones et al. 2010): the target time maps to
  the critical speed it needs (`race_time`, Riegel exponent 1.06 beyond 5 km). The chance of reaching it by the goal date
  is a Monte Carlo over (a) the uncertainty of today's critical speed (sampled from the scatter of your own monthly
  history, or 4 % when there are fewer than 4 months, and flagged as assumed) and (b) your trend, a Theil–Sen slope of
  that history with its 90 % interval, halved (new gains come slower than old ones) and capped at +10 % in total.
  The result is shown as a band, never as a promise.
- Ride and swim performances, and runs without a critical-speed fit: only demonstrated performances exist in the vault
  (no power or per-second streams), so today's level is your best recent session at least 90 % of the target distance,
  scaled to the target distance with Riegel's exponent. The outlook is then a heuristic on the improvement still
  required per month (≤ 1 % steady, ≤ 2.5 % demanding, more unlikely) and is labelled as such.
- Single-session distance: a long-session ladder from your longest session in the last 90 days, +10 % a week with every
  fourth week at 75 % of the peak, an easier week and then the attempt once the ladder reaches 85 % of the target. The
  +10 % step is a conservative rule of thumb (see analytics/plan.py for the run-spike evidence), not a guarantee.
- Weight: the Kalman trend and its rate (analytics/weight.py) against the date. Loss faster than 1 % of body weight a
  week, or gain faster than 0.5 %, is flagged as faster than is usually compatible with training well (the same limits
  as the weigh-in notes; Garthe et al. 2011 found 0.7 %/wk preserved lean mass better than 1.4 %/wk in athletes).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from scipy import stats

from cadence_app.analytics import athlete as A
from cadence_app.analytics import performance as P
from cadence_app.analytics import plan as training_plan

KINDS = ("race", "performance", "distance", "weight")
SPORTS = ("run", "ride", "swim")
RIEGEL = P.RIEGEL
PROJECTION_SHRINK = 0.5
MAX_GAIN = 0.10
MC_N = 4000
ASSUMED_SIGMA = 0.04
DEMONSTRATED_FRACTION = 0.9
DEMONSTRATED_DAYS = 180
LONG_DAYS = 90
LADDER_STEP, RECOVERY_EVERY, RECOVERY_FACTOR, READY_FRACTION = 1.10, 4, 0.75, 0.85
SAFE_LOSS_PCT = (0.25, 1.0)
MAX_GAIN_PCT = 0.5
HORIZON_DEFAULT_WEEKS = 12
ROADMAP_WEEKS = 30
TAPER = {"run": ((15000, 1), (25000, 2)), "ride": ((60000, 1), (120000, 2)), "swim": ((2500, 1), (5000, 2))}
BANDS = ((0.7, "likely"), (0.4, "plausible"), (0.15, "a stretch"), (0.0, "unlikely"))
STANDARD_RUN = {5000.0: "5k", 10000.0: "10k", 21097.5: "half", 42195.0: "marathon"}


def run_key(distance_m: float) -> str | None:
    """The standard race key (which drives the weekly plan) when the distance is exactly one of them."""
    return STANDARD_RUN.get(round(float(distance_m), 1))


def taper_weeks(sport: str, distance_m: float) -> int:
    for limit, weeks in TAPER.get(sport, TAPER["run"]):
        if distance_m <= limit:
            return weeks
    return 3


def band(p: float) -> str:
    return next(label for floor, label in BANDS if p >= floor)


def cs_needed(distance_m: float, target_s: float, d_prime: float) -> float:
    if distance_m <= 5000:
        return (distance_m - d_prime) / target_s
    return (5000 - d_prime) * (distance_m / 5000) ** RIEGEL / target_s


# ---- run: critical-speed model ----------------------------------------------------------------


def cs_model(c: dict) -> dict | None:
    cs = (c.get("performance") or {}).get("critical_speed")
    if not cs or not cs.get("valid"):
        return None
    hist = [h for h in (c["performance"].get("history") or []) if h.get("cs_mps")]
    end = c["as_of"]
    out = {"cs": cs["cs_mps"], "d_prime": cs["d_prime_m"], "n_history": len(hist), "slope": 0.0, "slope_se": 0.0, "sigma": ASSUMED_SIGMA, "sigma_assumed": True}
    if len(hist) >= 4:
        x = np.array([(h["day"] - end).days for h in hist], dtype=float)
        y = np.array([h["cs_mps"] for h in hist])
        slope, intercept, lo, hi = stats.theilslopes(y, x, 0.90)
        resid = y - (intercept + slope * x)
        out.update(slope=float(slope), slope_se=float((hi - lo) / (2 * 1.645)), sigma=max(0.015, float(resid.std(ddof=1) / y.mean())), sigma_assumed=False)
    return out


def project_run(model: dict, distance_m: float, target_s: float | None, days: int) -> dict:
    """Monte Carlo over today's critical speed and its trend, `days` ahead."""
    rng = np.random.default_rng(42)
    cs0 = rng.normal(model["cs"], model["sigma"] * model["cs"], MC_N)
    slope = rng.normal(PROJECTION_SHRINK * model["slope"], PROJECTION_SHRINK * model["slope_se"], MC_N)
    cs_future = np.minimum(cs0 + slope * days, cs0 * (1 + MAX_GAIN))
    cs_future = np.maximum(cs_future, 0.5 * cs0)
    d = model["d_prime"]
    t5 = (5000 - d) / cs_future
    times = (distance_m - d) / cs_future if distance_m <= 5000 else t5 * (distance_m / 5000) ** RIEGEL
    out = {"p10_s": round(float(np.percentile(times, 10))), "p50_s": round(float(np.percentile(times, 50))), "p90_s": round(float(np.percentile(times, 90)))}
    if target_s:
        out["probability"] = round(float((times <= target_s).mean()) * 20) / 20
    return out


# ---- demonstrated performance (ride, swim, and runs without a critical-speed fit) -------------------------


def demonstrated(c: dict, sport: str, distance_m: float) -> dict | None:
    """Best recent session of at least 90 % of the distance, scaled to `distance_m` (time_s), or None."""
    since = c["as_of"] - timedelta(days=DEMONSTRATED_DAYS)
    best = None
    for a in c["acts"]:
        if a.family != sport or a.day <= since or not a.distance_m or not a.moving_s or a.distance_m < DEMONSTRATED_FRACTION * distance_m:
            continue
        time_s = a.moving_s * (distance_m / a.distance_m) ** RIEGEL
        if best is None or time_s < best["time_s"]:
            best = {"time_s": round(time_s), "id": a.id, "day": a.day, "distance_m": a.distance_m, "name": a.name}
    return best


def heuristic_outlook(current_s: float, target_s: float, weeks_left: float | None) -> dict:
    gain = (current_s - target_s) / current_s
    if gain <= 0:
        return {"band": "likely", "heuristic": True, "required_gain_pct": round(gain * 100, 1), "per_month_pct": None}
    months = max(weeks_left, 1) / 4.345 if weeks_left is not None else HORIZON_DEFAULT_WEEKS / 4.345
    per_month = gain / months
    label = "plausible" if per_month <= 0.01 else "a stretch" if per_month <= 0.025 else "unlikely"
    return {"band": label, "heuristic": True, "required_gain_pct": round(gain * 100, 1), "per_month_pct": round(per_month * 100, 1)}


# ---- single-session distance ladder -----------------------------------------------------------------


def ladder(current_m: float, target_m: float) -> dict:
    """Weekly long-session distances from `current_m` to the attempt at `target_m`."""
    weeks, peak, i = [], current_m, 0
    ready = READY_FRACTION * target_m
    while peak < ready and i < 104:
        i += 1
        if i % RECOVERY_EVERY == 0:
            weeks.append({"week": i, "m": round(peak * RECOVERY_FACTOR), "kind": "recovery"})
            continue
        peak = min(peak * LADDER_STEP, max(ready, current_m))
        weeks.append({"week": i, "m": round(peak), "kind": "build"})
    weeks.append({"week": i + 1, "m": round(peak * 0.7), "kind": "easier"})
    weeks.append({"week": i + 2, "m": round(target_m), "kind": "attempt"})
    return {"weeks": weeks, "weeks_needed": i + 2}


# ---- assessment -------------------------------------------------------------------------------------


def longest(c: dict, sport: str, days: int | None = LONG_DAYS) -> dict | None:
    pool = [a for a in c["acts"] if a.family == sport and a.distance_m and (days is None or a.day > c["as_of"] - timedelta(days=days))]
    a = max(pool, key=lambda x: x.distance_m, default=None)
    return {"id": a.id, "day": a.day, "distance_m": a.distance_m, "name": a.name} if a else None


def roadmap(goal: dict, today: date) -> list[dict]:
    if not goal.get("date"):
        return []
    synthetic = {"date": goal["date"], "taper_weeks": taper_weeks(goal["sport"], goal["spec"].get("distance_m", 0))}
    out = []
    ws = A.week_start(today)
    for i in range(ROADMAP_WEEKS + 1):
        w = ws + timedelta(weeks=i)
        ph = training_plan._goal_phase(synthetic, w)  # pylint: disable=protected-access
        if ph is None:
            break
        label, blurb = training_plan.PHASES[ph["phase"]]
        out.append({"week": w, "weeks_to_go": ph["weeks_to_race"], "phase": ph["phase"], "label": label, "blurb": blurb})
    return out


def fields(goal: dict, today: date) -> dict:
    days_left = (goal["date"] - today).days if goal.get("date") else None
    base = {k: goal.get(k) for k in ("id", "kind", "sport", "title", "date", "spec", "status", "start_value", "created_on", "closed_on")}
    base.update(days_left=days_left, weeks_left=round(days_left / 7, 1) if days_left is not None else None, overdue=bool(days_left is not None and days_left < 0))
    return base


def assess(goal: dict, c: dict | None, today: date, weight: dict | None = None) -> dict:
    """goal: {"id","kind","sport","title","date","spec","status","start_value"}. weight: summary of analytics.weight (see below)."""
    base = fields(goal, today)
    if goal["kind"] == "weight":
        return {**base, **assess_weight(goal, weight, today)}
    if c is None:
        return {**base, "state": "no_data", "reason": "Sync some training first."}
    if goal["kind"] == "distance":
        return {**base, **assess_distance(goal, c, today)}
    return {**base, **assess_performance(goal, c, today)}


def assess_performance(goal: dict, c: dict, today: date) -> dict:
    spec, sport = goal["spec"], goal["sport"]
    distance = float(spec["distance_m"])
    target = spec.get("target_s")
    days_left = (goal["date"] - today).days if goal.get("date") else None
    horizon_days = max(days_left, 0) if days_left is not None else HORIZON_DEFAULT_WEEKS * 7
    out: dict = {"state": "ok", "roadmap": roadmap(goal, today), "caveats": []}
    model = cs_model(c) if sport == "run" else None
    demo = demonstrated(c, sport, distance)
    out["demonstrated"] = demo
    if model:
        proj = project_run(model, distance, target, horizon_days)
        now_s = round(P.race_time(distance, model["cs"], model["d_prime"]))
        out.update(basis="critical speed", current_s=now_s, projected=proj, horizon_days=horizon_days,
                   cs={"cs_mps": model["cs"], "n_history": model["n_history"], "sigma_pct": round(model["sigma"] * 100, 1), "sigma_assumed": model["sigma_assumed"],
                       "slope_pct_per_month": round(model["slope"] * 30 / model["cs"] * 100, 2) if model["cs"] else None})
        if model["sigma_assumed"]:
            out["caveats"].append(f"Fewer than 4 monthly critical-speed estimates, so a {ASSUMED_SIGMA * 100:.0f}% uncertainty on today's level is assumed.")
        if distance > 20000:
            out["caveats"].append("Marathon-and-longer times assume long runs of 90+ minutes in training.")
        if target:
            need = cs_needed(distance, target, model["d_prime"])
            p = proj["probability"]
            out.update(required_s=target, cs_needed_mps=round(need, 3), cs_gain_pct=round((need / model["cs"] - 1) * 100, 1),
                       outlook={"band": band(p), "probability": p, "heuristic": False})
    elif demo:
        out.update(basis="best recent session", current_s=demo["time_s"], horizon_days=horizon_days)
        out["caveats"].append("Only past sessions are available for this sport, so today's level is the best you have shown, not a fitness estimate."
                              if sport != "run" else "No valid critical-speed fit yet (needs a hard 3-minute and a hard 12-minute effort), so today's level is your best recent run.")
        if target:
            out.update(required_s=target, outlook=heuristic_outlook(demo["time_s"], target, days_left / 7 if days_left is not None else None))
    else:
        out.update(state="no_basis", reason=f"No {sport} session of at least {round(DEMONSTRATED_FRACTION * distance / 1000, 1)} km in the last {DEMONSTRATED_DAYS} days to judge this from.")
    if out.get("current_s") and target:
        out["achieved_hint"] = bool(demo and demo["time_s"] <= target and demo["distance_m"] >= distance * 0.97)
    return out


def assess_distance(goal: dict, c: dict, today: date) -> dict:
    target = float(goal["spec"]["distance_m"])
    sport = goal["sport"]
    recent, ever = longest(c, sport), longest(c, sport, None)
    out: dict = {"state": "ok", "longest_recent": recent, "longest_ever": ever, "roadmap": roadmap(goal, today), "caveats": []}
    out["achieved_hint"] = bool(ever and ever["distance_m"] >= target)
    if out["achieved_hint"]:
        out["achieved_on"] = ever["day"]
    if not recent:
        out.update(state="no_basis", reason=f"No {sport} session in the last {LONG_DAYS} days to build from.")
        return out
    lad = ladder(recent["distance_m"], target)
    weeks_left = (goal["date"] - today).days / 7 if goal.get("date") else None
    out["ladder"] = lad
    out["earliest"] = A.week_start(today) + timedelta(weeks=lad["weeks_needed"] - 1)
    if weeks_left is not None:
        spare = weeks_left - lad["weeks_needed"]
        out["outlook"] = {"band": "likely" if spare >= 2 else "plausible" if spare >= 0 else "unlikely", "heuristic": True, "spare_weeks": round(spare, 1)}
    out["caveats"].append("The +10% weekly step is a conservative rule of thumb for the longest session, not a guarantee against injury.")
    return out


def weight_inputs(summary, goal_kg: float | None = None) -> dict | None:
    """Plain dict for `assess` from a WeightSummary (keeps this module free of the weight dataclasses)."""
    if summary is None or summary.latest_trend_kg is None:
        return None
    proj = summary.projection
    return {"trend_kg": summary.latest_trend_kg, "rate_kg_wk": summary.rate_kg_per_week, "rate_se": summary.rate_se_kg_per_week,
            "last_day": summary.points[-1].day, "n_points": len(summary.points),
            "projection": {"status": proj.status, "expected": proj.expected, "earliest": proj.earliest, "latest": proj.latest} if proj else None}


def assess_weight(goal: dict, w: dict | None, today: date) -> dict:
    target = float(goal["spec"]["target_kg"])
    if not w:
        return {"state": "no_data", "reason": "Log or sync some weigh-ins first.", "caveats": []}
    trend, rate = w["trend_kg"], w["rate_kg_wk"]
    start = goal.get("start_value")
    losing = target < start if start and abs(target - start) >= 0.5 else target < trend  # the goal's direction, even once it is reached
    out: dict = {"state": "ok", "current_kg": round(trend, 1), "target_kg": target, "gap_kg": round(target - trend, 1), "rate_kg_wk": rate,
                 "rate_se": w["rate_se"], "last_weigh_in": w["last_day"], "caveats": ["Scale weight swings with water, glycogen and salt; the trend line is what counts."]}
    if start and abs(target - start) >= 0.5:
        out["progress_pct"] = max(0, min(100, round((trend - start) / (target - start) * 100)))
    out["achieved_hint"] = bool(trend <= target + 0.1 if losing else trend >= target - 0.1)
    limit_pct = SAFE_LOSS_PCT[1] if losing else MAX_GAIN_PCT
    weeks_left = (goal["date"] - today).days / 7 if goal.get("date") else None
    if weeks_left is not None and weeks_left > 0:
        need = (target - trend) / weeks_left
        pct = need / trend * 100
        out["required"] = {"kg_wk": round(need, 2), "pct_wk": round(pct, 2),
                           "too_fast": bool((losing and pct < -SAFE_LOSS_PCT[1]) or (not losing and pct > MAX_GAIN_PCT)),
                           "wrong_way": bool((losing and need > 0) or (not losing and need < 0))}
        path = []
        for i in range(0, int(math.ceil(weeks_left)) + 1):
            wk = today + timedelta(weeks=i)
            path.append({"week": min(wk, goal["date"]), "kg": round(trend + need * min(i, weeks_left), 2)})
        out["path"] = path
    fastest = trend * limit_pct / 100
    out["earliest_safe"] = today + timedelta(days=math.ceil(abs(target - trend) / fastest * 7)) if fastest > 0 and abs(target - trend) >= 0.1 else None
    out["steady"] = today + timedelta(days=math.ceil(abs(target - trend) / (trend * 0.005) * 7)) if abs(target - trend) >= 0.1 else None
    proj = w["projection"]
    if proj:
        out["projection"] = proj
        if goal.get("date") and proj["status"] == "on_track" and proj["expected"]:
            out["outlook"] = {"band": "likely" if proj["latest"] and proj["latest"] <= goal["date"] else "plausible" if proj["expected"] <= goal["date"] else "a stretch",
                              "heuristic": False}
        elif goal.get("date") and proj["status"] in ("off_track", "flat", "too_far"):
            out["outlook"] = {"band": "unlikely", "heuristic": False}
    out["rate_flag"] = None
    if rate is not None and trend:
        pct = rate / trend * 100
        out["rate_pct_wk"] = round(pct, 2)
        out["rate_flag"] = "too_fast" if (pct < -SAFE_LOSS_PCT[1] and losing) or (pct > MAX_GAIN_PCT and not losing) else "wrong_way" if (losing and rate > 0.05) or (not losing and rate < -0.05) else None
    return out


def summarise_set(items: list[dict]) -> dict:
    """Counts for the goals header."""
    active = [g for g in items if g["status"] == "active"]
    nxt = min((g for g in active if g.get("date") and g["days_left"] is not None and g["days_left"] >= 0), key=lambda g: g["days_left"], default=None)
    return {"active": len(active), "achieved": sum(1 for g in items if g["status"] == "achieved"), "next": nxt["id"] if nxt else None}
