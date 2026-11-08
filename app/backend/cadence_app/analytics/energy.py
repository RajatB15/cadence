"""Energy balance: burn so far, an end-of-day burn projection with a range, and a calorie target from your own history.

Pure functions on plain data. Loading is `energy_store.py`; wording is `notes.energy_copy`. Everything here is an estimate:
Garmin's burn and a food log both carry individual error of 10-20% or more, so nothing is presented as measured.

Methods and sources
- Garmin's `total_calories` for a day is resting plus active burn *so far*; it climbs all day. The projection uses the share
  of the final total that had already been burned at this time of day on your own past days (snapshots taken during the
  day). With at least `MIN_CURVE_N` past days that share is the median and the range is its 20th-80th percentile. With fewer,
  a rougher fallback adds the usual remaining resting burn (resting accrues about linearly through the day) and the part of
  a typical day's active burn that is still to come. With under `MIN_SETTLED` settled days there is no projection.
- Maintenance is the median total burn of your last 28 settled days (days with an active burn over twice the median, such as
  a race or a hike, are trimmed). With too little history, a formula guess: Mifflin-St Jeor resting rate x 1.4 (Mifflin et al.
  1990, Am J Clin Nutr 51:241), clearly labelled as a guess.
- A weight-goal adjustment uses 7,700 kcal per kg of body mass change (a common rule of thumb; real changes vary a lot between
  people), clamped to at most 0.5% of body weight per week (the gentle end of the pace commonly advised for athletes, ACSM/
  IOC consensus statements) and to 15% of maintenance, never applied on a day of illness, injury or time off.
- The target never goes below the larger of 1,500 kcal and 1.1 x your estimated resting burn; a lower value you type yourself
  is accepted with a neutral note.
- Protein: 1.4-2.0 g per kg of body weight a day for people who train (ISSN position stand, Jager et al. 2017).
No causal or medical claims: this says what the numbers are, not what to do about your body.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

MIN_CURVE_N = 10  # past days with a snapshot near this time of day before the curve is used
MIN_SETTLED = 7  # settled days of burn before any projection
MATCH_MIN = 45  # a snapshot counts for "this time of day" within this many minutes
HISTORY_DAYS = 28
TARGET_MIN_DAYS = 14
TRIM_ACTIVE_X = 2.0
LATE_MIN, HIDE_MIN = 21 * 60, 23 * 60  # the range collapses after 21:00; the projection hides after 23:00
JUST_STARTED_MIN = 60  # before 01:00 "today" is only just beginning and Garmin may still be carrying the old day
FLOOR_KCAL, FLOOR_RESTING_X = 1500.0, 1.1
MAX_PACE_PCT_WEEK = 0.5  # of body weight
KCAL_PER_KG = 7700.0
MAX_ADJUST_FRACTION = 0.15
MANUAL_RANGE = (800, 6000)
EAT_BACK_RANGE = (0, 100)
DEFAULT_SETTINGS = {"mode": "auto", "manual_kcal": None, "eat_back_pct": 50, "pace": True}
PROTEIN_G_PER_KG = (1.4, 2.0)
SPARK_DAYS = 14


def pos(x) -> float | None:
    """A usable kcal figure: a positive number, else missing. Garmin reports 0 for 'nothing yet', which is not a measurement."""
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def percentile(values: list[float], q: float) -> float:
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos_ = q * (len(xs) - 1)
    lo = int(pos_)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos_ - lo)


def clean_settings(raw: dict | None) -> dict:
    """Stored settings clamped to their range; anything missing or invalid falls back to the default."""
    out = dict(DEFAULT_SETTINGS)
    raw = raw or {}
    if raw.get("mode") in ("auto", "manual"):
        out["mode"] = raw["mode"]
    m = raw.get("manual_kcal")
    if isinstance(m, (int, float)) and not isinstance(m, bool) and MANUAL_RANGE[0] <= m <= MANUAL_RANGE[1]:
        out["manual_kcal"] = round(float(m))
    e = raw.get("eat_back_pct")
    if isinstance(e, (int, float)) and not isinstance(e, bool) and EAT_BACK_RANGE[0] <= e <= EAT_BACK_RANGE[1]:
        out["eat_back_pct"] = round(float(e))
    if isinstance(raw.get("pace"), bool):
        out["pace"] = raw["pace"]
    if out["mode"] == "manual" and out["manual_kcal"] is None:
        out["mode"] = "auto"  # manual without a number is not usable
    return out


def validate_settings(values: dict) -> None:
    """Strict checks for what a person submits (clean_settings is the lenient read)."""
    if "mode" in values and values["mode"] not in ("auto", "manual"):
        raise ValueError("mode must be auto or manual")
    m = values.get("manual_kcal")
    if m is not None and not MANUAL_RANGE[0] <= m <= MANUAL_RANGE[1]:
        raise ValueError(f"manual target must be between {MANUAL_RANGE[0]:,} and {MANUAL_RANGE[1]:,} kcal")
    e = values.get("eat_back_pct")
    if e is not None and not EAT_BACK_RANGE[0] <= e <= EAT_BACK_RANGE[1]:
        raise ValueError("workout share must be between 0 and 100 percent")


# ---- history --------------------------------------------------------------------------------------------------------


def settled(finals: dict[date, tuple[float | None, float | None]], today: date, days: int = HISTORY_DAYS) -> list[tuple[date, float, float | None]]:
    """(day, total, active|None) for settled days before today with a real total, oldest first."""
    out = []
    for d in sorted(finals):
        total, active = finals[d]
        if today - timedelta(days=days) <= d < today and (t := pos(total)) is not None:
            out.append((d, t, pos(active)))
    return out


def resting_estimate(rows: list[tuple[date, float, float | None]]) -> float | None:
    """Median of total minus active over settled days (needs a week)."""
    vals = [t - a for _, t, a in rows if a is not None and t - a > 0]
    return median(vals) if len(vals) >= MIN_SETTLED else None


# ---- projection -----------------------------------------------------------------------------------------------------


def project_burn(now_min: int, as_of_min: int, total: float | None, active: float | None,
                 finals: dict[date, tuple[float | None, float | None]], snapshots: dict[date, list[tuple[int, float]]], today: date) -> dict:
    """End-of-day burn with a range. Returns {status: ok|partial|insufficient|hidden|no_burn, value, lo, hi, n, method}."""
    base = {"value": None, "lo": None, "hi": None, "n": 0, "method": None}
    if pos(total) is None:
        return {**base, "status": "no_burn"}
    rows = settled(finals, today)
    if len(rows) < MIN_SETTLED:
        return {**base, "status": "insufficient", "n": len(rows)}
    if now_min >= HIDE_MIN:
        return {**base, "status": "hidden", "n": len(rows)}

    ratios = []
    for d, final, _ in rows:
        near = [(abs(m - as_of_min), t) for m, t in snapshots.get(d, []) if abs(m - as_of_min) <= MATCH_MIN]
        if near:
            ratio = min(near)[1] / final
            if 0.05 < ratio <= 1.02:
                ratios.append(ratio)
    if len(ratios) >= MIN_CURVE_N:
        mid, hi_r, lo_r = median(ratios), percentile(ratios, 0.8), percentile(ratios, 0.2)
        value, lo, hi = total / mid, total / hi_r, total / lo_r
        method, n = "curve", len(ratios)
    else:
        rest = resting_estimate(rows)
        actives = [a for _, _, a in rows if a is not None]
        if rest is None or len(actives) < MIN_SETTLED:
            return {**base, "status": "insufficient", "n": len(rows)}
        frac = as_of_min / 1440
        so_far_active = pos(active) if pos(active) is not None else max(total - rest * frac, 0.0)

        def remaining(typical: float) -> float:
            return min(max(typical - so_far_active, 0.0), typical * (1 - frac))

        resting_rem = rest * (1 - frac)
        value = total + resting_rem + remaining(median(actives))
        lo = total + resting_rem + remaining(percentile(actives, 0.25))
        hi = total + resting_rem + remaining(percentile(actives, 0.75))
        method, n = "fallback", len(actives)
    value = max(value, total)
    lo, hi = min(max(lo, total), value), max(hi, value)
    if now_min >= LATE_MIN:  # little burn is left: the range is about the estimate's own error
        lo, hi = max(total, value - 0.05 * total), value + 0.05 * total
    return {"status": "ok" if method == "curve" else "partial", "value": round(value), "lo": round(lo), "hi": round(hi), "n": n, "method": method}


# ---- target ---------------------------------------------------------------------------------------------------------


def mifflin_resting(sex: str, weight_kg: float, height_cm: float, age_years: float) -> float:
    return 10 * weight_kg + 6.25 * height_cm - 5 * age_years + (5 if sex == "male" else -161)


def maintenance(rows: list[tuple[date, float, float | None]], profile: dict | None, weight_kg: float | None) -> dict | None:
    """Maintenance kcal from history (median of settled totals, outlier days trimmed) or, failing that, a labelled formula guess."""
    if len(rows) >= TARGET_MIN_DAYS:
        actives = [a for _, _, a in rows if a is not None]
        keep = rows
        if len(actives) >= MIN_SETTLED:
            cutoff = TRIM_ACTIVE_X * median(actives)
            trimmed = [r for r in rows if r[2] is None or r[2] <= cutoff]
            if len(trimmed) >= 10:
                keep = trimmed
        return {"kcal": median(t for _, t, _ in keep), "source": "history", "n_days": len(keep)}
    if profile and weight_kg:
        resting = mifflin_resting(profile["sex"], weight_kg, profile["height_cm"], profile["age_years"])
        if resting > 0:
            return {"kcal": resting * 1.4, "source": "formula", "n_days": 0, "resting": resting}
    return None


def pace_adjustment(maint: float, current_kg: float, target_kg: float, days_left: int) -> dict:
    """Daily kcal change toward a weight goal at a cautious pace: at most 0.5% of body weight per week, at most 15% of maintenance."""
    diff = target_kg - current_kg
    if abs(diff) < 0.3:
        return {"kcal": 0, "state": "at_goal"}
    weeks = max(days_left / 7, 1.0)
    requested = diff / weeks
    cap = current_kg * MAX_PACE_PCT_WEEK / 100
    applied = max(-cap, min(cap, requested))
    kcal = applied * KCAL_PER_KG / 7
    limit = MAX_ADJUST_FRACTION * maint
    kcal = max(-limit, min(limit, kcal))
    clamped = abs(requested) > cap or abs(applied * KCAL_PER_KG / 7) > limit
    out = {"kcal": round(kcal), "state": "gentle" if clamped else "on_pace", "kg_per_week": round(kcal * 7 / KCAL_PER_KG, 2)}
    if clamped:
        out["weeks_at_gentle_pace"] = round(abs(diff) / max(abs(kcal * 7 / KCAL_PER_KG), 0.01))
    return out


def derive_target(rows: list[tuple[date, float, float | None]], settings: dict, *, profile: dict | None = None, weight_kg: float | None = None,
                  pace: dict | None = None, hold: str | None = None) -> dict | None:
    """The day's calorie target. `pace` = {target_kg, days_left}; `hold` names why no weight-goal adjustment applies today
    (illness, injury, time off, a hard training block). Manual mode ignores both."""
    maint = maintenance(rows, profile, weight_kg)
    resting = resting_estimate(rows)
    if resting is None and maint and maint.get("resting"):
        resting = maint["resting"]
    floor = max(FLOOR_KCAL, FLOOR_RESTING_X * resting) if resting else FLOOR_KCAL
    protein = ({"low_g": round(PROTEIN_G_PER_KG[0] * weight_kg), "high_g": round(PROTEIN_G_PER_KG[1] * weight_kg), "per_kg": list(PROTEIN_G_PER_KG)}
               if weight_kg else None)
    if settings["mode"] == "manual" and settings["manual_kcal"]:
        kcal = settings["manual_kcal"]
        return {"kcal": kcal, "source": "manual", "maintenance_kcal": round(maint["kcal"]) if maint else None, "adjustment_kcal": 0, "floor_kcal": round(floor),
                "floor_applied": False, "below_floor": kcal < floor, "n_days": maint["n_days"] if maint and maint["source"] == "history" else 0,
                "pace": None, "hold": None, "protein": protein}
    if maint is None:
        return None
    adjustment, pace_info, why = 0, None, None
    if settings["pace"] and pace and weight_kg:
        if hold:
            why = hold
        else:
            pace_info = pace_adjustment(maint["kcal"], weight_kg, pace["target_kg"], pace["days_left"])
            adjustment = pace_info["kcal"]
    kcal = maint["kcal"] + adjustment
    floor_applied = kcal < floor
    if floor_applied:
        kcal = floor
    return {"kcal": round(kcal), "source": maint["source"], "maintenance_kcal": round(maint["kcal"]), "adjustment_kcal": round(kcal - maint["kcal"]) if floor_applied else adjustment,
            "floor_kcal": round(floor), "floor_applied": floor_applied, "below_floor": False, "n_days": maint["n_days"], "pace": pace_info, "hold": why, "protein": protein}


# ---- assembly -------------------------------------------------------------------------------------------------------


def hhmm(minutes: int | None) -> str | None:
    return None if minutes is None else f"{minutes // 60:02d}:{minutes % 60:02d}"


def assemble(*, today: date, now_min: int, burn: dict | None, finals: dict[date, tuple[float | None, float | None]],
             snapshots: dict[date, list[tuple[int, float]]], food: dict[date, dict], workouts: list[dict], settings: dict | None,
             profile: dict | None = None, weight_kg: float | None = None, pace: dict | None = None, hold: str | None = None) -> dict:
    """The `energy` block of the overview. `burn` = {total, active, as_of_min} for today, or None when Garmin has not reported.
    `food` maps a day to `foodlog.day_summary` output; a day without entries is 'not logged', never zero."""
    cfg = clean_settings(settings)
    total = pos((burn or {}).get("total"))
    active = pos((burn or {}).get("active"))
    as_of = (burn or {}).get("as_of_min", now_min)
    just_started = now_min < JUST_STARTED_MIN
    if just_started:
        total = active = None  # at 00:05 Garmin may still carry yesterday; a new day starts with no burn to show
    rows = settled(finals, today)
    target = derive_target(rows, cfg, profile=profile, weight_kg=weight_kg, pace=pace, hold=hold)

    projected = project_burn(now_min, as_of, total, active, finals, snapshots, today)
    if total is None:
        status = "just_started" if just_started else "no_garmin_kcal"
    else:
        status = projected["status"] if projected["status"] in ("ok", "partial") else "insufficient"

    summary = food.get(today) or {}
    logged = bool(summary.get("logged"))
    eaten = {"kcal": summary.get("kcal") if logged else None, "kcal_low": summary.get("kcal_low") if logged else None,
             "kcal_high": summary.get("kcal_high") if logged else None, "logged": logged,
             "entries": summary.get("entries", 0) if logged else 0, "protein_g": summary.get("protein_g") if logged else None}

    workout_kcal = round(sum(w["kcal"] for w in workouts if pos(w.get("kcal")) is not None)) or None
    eat_back = round((workout_kcal or 0) * cfg["eat_back_pct"] / 100)
    left = above = None
    if target and logged:
        gap = target["kcal"] + eat_back - eaten["kcal"]
        left, above = (round(gap), None) if gap >= 0 else (None, round(-gap))

    resting = round(total - active) if total is not None and active is not None and total > active else None
    spark = []
    for i in range(SPARK_DAYS - 1, 0, -1):
        d = today - timedelta(days=i)
        s = food.get(d) or {}
        spark.append({"day": d, "total": pos(finals.get(d, (None, None))[0]), "eaten": s.get("kcal") if s.get("logged") else None})
    spark.append({"day": today, "total": total, "eaten": eaten["kcal"], "partial": True})
    yesterday = None
    if just_started:
        y = today - timedelta(days=1)
        ys = food.get(y) or {}
        yesterday = {"day": y, "total": pos(finals.get(y, (None, None))[0]), "eaten": ys.get("kcal") if ys.get("logged") else None}

    return {
        "status": status,
        "day": today,
        "as_of_min": as_of if total is not None else None,
        "as_of": hhmm(as_of) if total is not None else None,
        "burned": {"total": round(total), "active": round(active) if active is not None else None, "resting": resting, "as_of": hhmm(as_of)} if total is not None else None,
        "eaten": eaten,
        "projected": {k: projected[k] for k in ("value", "lo", "hi", "n", "method")} if projected["value"] is not None else None,
        "projection_state": projected["status"] if total is not None else None,
        "projection_history_days": projected["n"],
        "target": target,
        "left": left,
        "above_by": above,
        "workout_active_kcal": workout_kcal,
        "eat_back_pct": cfg["eat_back_pct"],
        "eat_back_kcal": eat_back,
        "balance": {"so_far_kcal": round(eaten["kcal"] - total)} if total is not None and logged else None,
        "spark": spark,
        "yesterday": yesterday,
        "settings": cfg,
    }
