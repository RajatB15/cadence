"""Run performance from FIT streams: grade-adjusted speed, best efforts, critical speed, race times, zones and form.

Methods, so every number can be checked:
- Grade adjustment: Minetti et al. (2002) energy cost of running on slopes relative to flat (3.6 J/kg/m). Downhill
  savings are halved because few runners can exploit Minetti's full downhill benefit outside a treadmill.
- Best efforts: highest average grade-adjusted speed over each duration (mean-maximal speed curve).
- Critical speed (CS) and D′: linear distance–time model (Hill 1993) fitted to the best 3–20 minute efforts. Only
  trusted when the efforts look maximal: >= 4 efforts (>= 2 of 10+ min), D′ in a physiological range, small speed-space
  residuals and a small standard error (Jones et al. 2010 stress that CS needs several maximal, well-spread efforts).
  Reports SE and a 95% interval (t, n - 2 df).
- Race times: CS model where it is valid (≤ ~30 min), Riegel (1981) extrapolation with exponent 1.06 beyond; the CS
  estimate blends toward Riegel from the longest fitted effort when it extrapolates past 1.5 × that effort's duration.
  Ranges come from the fit's covariance (delta method).
- Threshold heart rate: Friel's 20-minute test — average HR of a hard 20-minute effort × 0.95.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean, median, pstdev

import numpy as np
from scipy import stats

BEST_DURATIONS = (60, 180, 300, 420, 600, 720, 900, 1200, 1800)
CS_DURATIONS = (180, 300, 420, 600, 720, 900, 1200)
CS_WINDOW_DAYS = 90
MAX_GRADE = 0.25
GRADE_SPAN_M = 50.0
MOVING_MPS = 1.5
MAX_GAP_S = 30.0  # a longer hole in the record is a pause: it adds time but no distance
RIEGEL = 1.06
RACES = (("5k", "5 km", 5000.0), ("10k", "10 km", 10000.0), ("half", "Half marathon", 21097.5), ("marathon", "Marathon", 42195.0))
FORM_FIELDS = {"cadence": "cadence", "stance_time": "stance_ms", "vertical_ratio": "vertical_ratio",
               "vertical_oscillation": "vertical_osc_mm", "step_length": "step_mm"}


# ---- grade adjustment -------------------------------------------------------------


def grade_factor(grade: float) -> float:
    """Energy cost on a slope relative to flat running (Minetti 2002), with downhill savings halved."""
    g = max(-MAX_GRADE, min(MAX_GRADE, grade))
    cost = 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + 3.6
    factor = cost / 3.6
    return factor if g >= 0 else 1 - 0.5 * (1 - factor)


def _distance(t: list, speed: list) -> list[float | None]:
    out: list[float | None] = []
    total = 0.0
    prev = None
    for ti, vi in zip(t, speed):
        if ti is not None and prev is not None and vi is not None:
            dt = ti - prev
            if 0 < dt <= MAX_GAP_S:
                total += vi * dt
        out.append(total if ti is not None else None)
        prev = ti if ti is not None else prev
    return out


def grade_adjusted(streams: dict[str, list]) -> list[float | None]:
    """Grade-adjusted speed per sample; plain speed when there is no altitude."""
    t, v = streams.get("t") or [], streams.get("speed") or []
    alt = streams.get("altitude")
    if not v:
        return []
    if not alt or not any(a is not None for a in alt):
        return list(v)
    dist = streams.get("distance")
    if not dist or not any(x is not None for x in dist):
        dist = _distance(t, v)
    out: list[float | None] = []
    j = 0
    for i, vi in enumerate(v):
        if vi is None or dist[i] is None or alt[i] is None:
            out.append(vi)
            continue
        while j < i and (dist[j] is None or alt[j] is None or dist[i] - dist[j] > GRADE_SPAN_M):
            j += 1
        span = dist[i] - dist[j] if dist[j] is not None else 0
        # Too little distance behind this point (start of the run, or stopped): no grade evidence yet.
        grade = (alt[i] - alt[j]) / span if span >= GRADE_SPAN_M / 2 else 0.0
        out.append(vi * grade_factor(grade))
    return out


# ---- per-run analysis ---------------------------------------------------------------


def _rows(streams: dict[str, list], gap: list[float | None]) -> list[tuple[float, float, float | None]]:
    t, hr = streams.get("t") or [], streams.get("heart_rate") or [None] * len(gap)
    return [(ti, vi, hi) for ti, vi, hi in zip(t, gap, hr) if ti is not None and vi is not None]


def best_efforts(t: list[float], values: list[float], durations=BEST_DURATIONS) -> dict[str, float]:
    """Highest time-weighted mean of `values` over each duration (seconds), pauses counting as zero."""
    if len(t) < 2:
        return {}
    cum = [0.0]
    for i in range(1, len(t)):
        dt = t[i] - t[i - 1]
        cum.append(cum[-1] + (values[i] * dt if 0 < dt <= MAX_GAP_S else 0.0))
    out = {}
    for dur in durations:
        if t[-1] - t[0] < dur:
            break
        best, j = 0.0, 0
        for i in range(len(t)):
            while j + 1 < i and t[i] - t[j + 1] >= dur:
                j += 1
            span = t[i] - t[j]
            if span >= dur:
                best = max(best, (cum[i] - cum[j]) / span)
        if best > 0:
            out[str(dur)] = round(best, 3)
    return out


def decoupling(streams: dict[str, list]) -> dict | None:
    """Pa:HR decoupling between halves of the moving portion on grade-adjusted pace, skipping a 10-minute warm-up."""
    rows = [(ti, vi, hi) for ti, vi, hi in _rows(streams, grade_adjusted(streams)) if hi and vi > MOVING_MPS and ti >= 600]
    if len(rows) < 60 or rows[-1][0] - rows[0][0] < 30 * 60:
        return None
    mid = (rows[0][0] + rows[-1][0]) / 2
    first = [r for r in rows if r[0] < mid]
    second = [r for r in rows if r[0] >= mid]
    ef1 = fmean(r[1] for r in first) / fmean(r[2] for r in first)
    ef2 = fmean(r[1] for r in second) / fmean(r[2] for r in second)
    speeds = [r[1] for r in rows]
    cv = pstdev(speeds) / fmean(speeds)
    return {
        "decoupling_pct": round((ef1 - ef2) / ef1 * 100, 1),
        "speed_cv": round(cv, 3),
        "steady": cv < 0.15,
        "minutes": round((rows[-1][0] - rows[0][0]) / 60),
    }


def pacing(streams: dict[str, list]) -> dict | None:
    """Average grade-adjusted moving speed of the first vs second half of the session by elapsed time."""
    rows = [(ti, vi) for ti, vi, _ in _rows(streams, grade_adjusted(streams)) if vi > MOVING_MPS]
    if len(rows) < 60 or rows[-1][0] - rows[0][0] < 20 * 60:
        return None
    mid = (rows[0][0] + rows[-1][0]) / 2
    v1 = fmean(r[1] for r in rows if r[0] < mid)
    v2 = fmean(r[1] for r in rows if r[0] >= mid)
    return {"first_mps": round(v1, 3), "second_mps": round(v2, 3), "split_pct": round((v2 - v1) / v1 * 100, 1)}


def late_fade(streams: dict[str, list]) -> dict | None:
    """Durability: efficiency (grade-adjusted speed per beat) in the last 20 minutes vs minutes 10–30, runs ≥ 75 min."""
    rows = [(ti, vi, hi) for ti, vi, hi in _rows(streams, grade_adjusted(streams)) if hi and vi > MOVING_MPS]
    if len(rows) < 60 or rows[-1][0] - rows[0][0] < 75 * 60:
        return None
    end = rows[-1][0]
    early = [r for r in rows if 600 <= r[0] - rows[0][0] < 1800]
    late = [r for r in rows if r[0] > end - 1200]
    if len(early) < 20 or len(late) < 20:
        return None
    speeds = [r[1] for r in rows]
    if pstdev(speeds) / fmean(speeds) >= 0.2:
        return None  # intervals or stop-start running: efficiency halves aren't comparable
    ef_early = fmean(r[1] for r in early) / fmean(r[2] for r in early)
    ef_late = fmean(r[1] for r in late) / fmean(r[2] for r in late)
    return {"fade_pct": round((ef_early - ef_late) / ef_early * 100, 1), "minutes": round((end - rows[0][0]) / 60)}


def form(streams: dict[str, list]) -> dict | None:
    """Median running-dynamics values while moving: cadence (steps/min) and whatever else the watch records."""
    v = streams.get("speed") or []
    moving = [i for i, x in enumerate(v) if x is not None and x > MOVING_MPS]
    if len(moving) < 60:
        return None
    out: dict[str, float] = {"speed": round(median(v[i] for i in moving), 3)}
    for field, key in FORM_FIELDS.items():
        values = [streams[field][i] for i in moving if field in streams and streams[field][i]]
        if len(values) >= 60:
            out[key] = round(median(values), 1)
    return out if "cadence" in out else None


def analyse_run(streams: dict[str, list]) -> dict:
    """Everything worth caching from one run's streams."""
    out: dict = {}
    if dec := decoupling(streams):
        out.update(dec)
    rows = _rows(streams, grade_adjusted(streams))
    if rows:
        t = [r[0] for r in rows]
        out["best"] = best_efforts(t, [r[1] for r in rows])
        hr_rows = [r for r in rows if r[2]]
        if len(hr_rows) >= 60:
            hr20 = best_efforts([r[0] for r in hr_rows], [r[2] for r in hr_rows], (1200,))
            if hr20:
                out["hr20"] = round(hr20["1200"], 1)
            out["hr_max"] = round(max(r[2] for r in hr_rows))
    if fade := late_fade(streams):
        out["late_fade"] = fade
    if f := form(streams):
        out["form"] = f
    if p := pacing(streams):
        out["pacing"] = p
    return out


# ---- critical speed & race times ------------------------------------------------------


CS_MIN_POINTS = 4
CS_MAX_RESID = 0.04  # worst relative speed residual allowed (4 %): maximal efforts sit on the hyperbola v = CS + D'/t
CS_MAX_RMSE = 0.025
CS_MAX_REL_SE = 0.04  # standard error of CS above 4 % of CS means the efforts don't pin it down


def critical_speed(runs: list[dict], end: date, days: int = CS_WINDOW_DAYS) -> dict:
    """CS and D′ from the best 3–20 min efforts of the trailing window.

    `runs` items: {"id", "day", "name", "best": {"180": m/s, ...}}. Always returns a dict; `valid` says whether the
    efforts were hard enough to trust, and `missing` names the efforts that would fix it.

    Validity needs >= 4 efforts (>= 2 of them 10 minutes or longer, >= 1 of 5 minutes or less) and speed-space residuals
    from v = CS + D′/t within CS_MAX_RESID (worst) and CS_MAX_RMSE (RMS), because a distance-time R² is near 1 for any
    set of points (distance is dominated by time). The standard errors come from the OLS covariance (n - 2 df); the fit
    is rejected when SE(CS) exceeds CS_MAX_REL_SE of CS.
    """
    window = [r for r in runs if end - timedelta(days=days) < r["day"] <= end and r.get("best")]
    points = []
    for dur in CS_DURATIONS:
        top = max(window, key=lambda r, k=str(dur): r["best"].get(k, 0), default=None)
        if top and top["best"].get(str(dur)):
            points.append({"seconds": dur, "speed": top["best"][str(dur)], "id": top["id"], "day": top["day"], "name": top["name"]})
    out: dict = {"valid": False, "points": points, "window_days": days}
    short = [p for p in points if p["seconds"] <= 300]
    long_ = [p for p in points if p["seconds"] >= 600]
    if len(points) < CS_MIN_POINTS or not short or len(long_) < 2:
        out["missing"] = "a hard 3-minute effort and two hard efforts of 10+ minutes"
        return out
    x = np.array([p["seconds"] for p in points], dtype=float)
    y = np.array([p["speed"] * p["seconds"] for p in points])
    cs, d_prime = np.polyfit(x, y, 1)
    pred = cs * x + d_prime
    sse = float(np.sum((y - pred) ** 2))
    r2 = 1 - sse / float(np.sum((y - y.mean()) ** 2))
    n = len(points)
    X = np.column_stack([x, np.ones(n)])
    xtx = X.T @ X
    if not np.all(np.isfinite(xtx)) or np.linalg.cond(xtx) > 1e12:
        out["missing"] = "a hard 3-minute effort and two hard efforts of 10+ minutes"  # degenerate (e.g. identical durations): no usable fit
        return out
    cov = sse / (n - 2) * np.linalg.inv(xtx)
    cs_se, d_se = float(np.sqrt(cov[0, 0])), float(np.sqrt(cov[1, 1]))
    tcrit = float(stats.t.ppf(0.975, n - 2))
    v = y / x
    rel = np.abs(v - pred / x) / v  # residuals in speed space
    out.update(cs_mps=round(float(cs), 3), d_prime_m=round(float(d_prime)), r2=round(r2, 4), n_points=n,
               cs_se=round(cs_se, 4), cs_ci=[round(float(cs) - tcrit * cs_se, 3), round(float(cs) + tcrit * cs_se, 3)],
               d_prime_se=round(d_se), resid_max_pct=round(float(rel.max()) * 100, 1), resid_rmse_pct=round(float(np.sqrt(np.mean(rel**2))) * 100, 1))
    # Steady easy runs give a flat curve (tiny D′); a real all-out curve has D′ of roughly 50–400 m.
    if not (1.5 < cs < 7.5) or not (40 <= d_prime <= 450) or rel.max() > CS_MAX_RESID or float(np.sqrt(np.mean(rel**2))) > CS_MAX_RMSE \
            or cs_se > CS_MAX_REL_SE * cs:
        out["missing"] = ("a hard 3-minute effort and two hard efforts of 10+ minutes" if d_prime < 40
                          else "cleaner maximal efforts (the current ones don't fit the model)")
        return out
    longest = max(points, key=lambda p: p["seconds"])
    anchor = {"seconds": longest["seconds"], "distance_m": longest["speed"] * longest["seconds"]}
    out["valid"] = True
    out["pace_s"] = round(1000 / cs)
    out["anchor"] = anchor
    out["predictions"] = predictions(float(cs), float(d_prime), anchor, cov, tcrit)
    out["paces"] = training_paces(float(cs))
    return out


def race_time(distance_m: float, cs: float, d_prime: float, anchor: dict | None = None):
    """CS-model race time; beyond 5 km Riegel from the 5 km time. Works on numpy arrays of cs/d_prime too.

    The CS hyperbola is only trusted near the fitted efforts (<= 20 min). When the predicted time runs beyond 1.5 × the
    longest fitted effort the estimate blends toward Riegel from that effort, fully Riegel at 4 ×.
    """
    def cs_time(dist):
        return (dist - d_prime) / cs

    def blend(dist, tcs):
        if not anchor:
            return tcs
        rieg = anchor["seconds"] * (dist / anchor["distance_m"]) ** RIEGEL
        w = np.clip((4.0 - tcs / anchor["seconds"]) / 2.5, 0.0, 1.0)  # 1 up to 1.5 ×, 0 at 4 ×
        return w * tcs + (1 - w) * rieg

    if distance_m <= 5000:
        return blend(distance_m, cs_time(distance_m))
    return blend(5000.0, cs_time(5000.0)) * (distance_m / 5000) ** RIEGEL


def predictions(cs: float, d_prime: float, anchor: dict | None = None, cov=None, tcrit: float = 0.0) -> list[dict]:
    out = []
    for key, label, dist in RACES:
        seconds = float(race_time(dist, cs, d_prime, anchor))
        row = {"key": key, "label": label, "distance_m": dist, "seconds": round(seconds), "pace_s": round(seconds / dist * 1000),
               "caveat": "Assumes long runs of 90+ minutes in training." if dist > 20000 else None}
        if cov is not None and tcrit:
            d5 = min(dist, 5000.0)
            scale = 1.0 if dist <= 5000 else (dist / 5000) ** RIEGEL
            # delta method for t = (d - D′)/CS, scaled by the Riegel factor beyond 5 km
            g = np.array([-(d5 - d_prime) / cs**2, -1.0 / cs]) * scale
            se_t = float(np.sqrt(max(g @ cov @ g, 0.0)))
            row.update(low_s=round(seconds - tcrit * se_t), high_s=round(seconds + tcrit * se_t))
        out.append(row)
    return out


def training_paces(cs: float) -> list[dict]:
    """Pace bands (s/km, slow→fast) as fractions of critical speed."""
    bands = (("easy", "Easy & long", 0.70, 0.80), ("steady", "Steady", 0.80, 0.88), ("threshold", "Threshold", 0.92, 0.97),
             ("vo2", "VO₂max intervals", 1.03, 1.08))
    return [{"key": k, "label": label, "slow_s": round(1000 / (cs * lo)), "fast_s": round(1000 / (cs * hi))} for k, label, lo, hi in bands]


def cs_history(runs: list[dict], end: date, months: int = 12) -> list[dict]:
    out = []
    for m in range(months - 1, -1, -1):
        d = end - timedelta(days=30 * m)
        r = critical_speed(runs, d)
        if r["valid"]:
            out.append({"day": d, "cs_mps": r["cs_mps"], "pace_s": r["pace_s"], "d_prime_m": r["d_prime_m"]})
    return out


def pace_for(prediction_key: str, cs: dict | None, goal_time_s: float | None = None, goal_distance: float | None = None) -> float | None:
    """Race pace (s/km): from the goal time when given, else predicted."""
    if goal_time_s and goal_distance:
        return goal_time_s / goal_distance * 1000
    if not cs or not cs.get("valid"):
        return None
    return next((p["pace_s"] for p in cs["predictions"] if p["key"] == prediction_key), None)


# ---- heart-rate zone check ---------------------------------------------------------------


def zone_check(zones: dict | None, max_hrs: list[tuple[date, float]], hr20: list[tuple[date, float]], end: date) -> dict | None:
    """Flags zones that recent efforts have outgrown. Only upward evidence counts: an easy month proves nothing."""
    if not zones:
        return None
    year = sorted((v for d, v in max_hrs if end - timedelta(days=365) < d <= end and 120 <= v <= 230), reverse=True)
    # Second-highest, so one optical-sensor spike can't move your zones.
    observed = year[1] if len(year) >= 2 else None
    recent = [(d, v) for d, v in hr20 if end - timedelta(days=120) < d <= end]
    best20 = max(recent, key=lambda x: x[1], default=None)
    lthr_est = round(best20[1] * 0.95) if best20 else None
    issues = []
    if observed and zones.get("max") and observed >= zones["max"] + 3:
        issues.append({"key": "max", "label": "Max heart rate", "zones": zones["max"], "observed": round(observed),
                       "detail": f"You've reached {observed:.0f} bpm this year; your zones assume a max of {zones['max']}."})
    if lthr_est and zones.get("threshold") and lthr_est >= zones["threshold"] + 3:
        issues.append({"key": "threshold", "label": "Threshold heart rate", "zones": zones["threshold"], "observed": lthr_est,
                       "detail": f"A 20-minute stretch averaging {best20[1]:.0f} bpm on {best20[0]:%d %b} implies a threshold of about "
                                 f"{lthr_est} bpm (Friel: × 0.95); your zones use {zones['threshold']}."})
    return {"status": "stale" if issues else "ok", "issues": issues, "observed_max": round(observed) if observed else None,
            "lthr_estimate": lthr_est, "zones_max": zones.get("max"), "zones_threshold": zones.get("threshold")}


# ---- running form & durability trends --------------------------------------------------------


def form_trend(points: list[dict], end: date) -> dict | None:
    """Cadence at a reference speed, last 90 days vs the 90 before (cadence rises with speed, so compare like with like).

    `points`: {"day", "speed", "cadence", ...form fields}.
    """
    now = [p for p in points if end - timedelta(days=90) < p["day"] <= end]
    then = [p for p in points if end - timedelta(days=180) < p["day"] <= end - timedelta(days=90)]
    if len(now) < 6:
        return None
    ref = median(p["speed"] for p in now)

    def at_ref(rows: list[dict]) -> float | None:
        if len(rows) < 6:
            return None
        x = np.array([p["speed"] for p in rows])
        y = np.array([p["cadence"] for p in rows])
        if np.ptp(x) < 0.2:
            return float(np.median(y))
        slope, intercept = np.polyfit(x, y, 1)
        return float(intercept + slope * ref)

    out: dict = {"ref_speed": round(ref, 2), "ref_pace_s": round(1000 / ref), "n": len(now), "cadence_now": round(at_ref(now) or 0)}
    before = at_ref(then)
    out["cadence_before"] = round(before) if before else None
    for key in ("stance_ms", "vertical_ratio", "vertical_osc_mm"):
        values = [p[key] for p in now if p.get(key)]
        prior = [p[key] for p in then if p.get(key)]
        if len(values) >= 6:
            out[key] = round(median(values), 1)
            out[f"{key}_before"] = round(median(prior), 1) if len(prior) >= 6 else None
    return out


def durability_trend(fades: list[dict], end: date) -> dict | None:
    """Median late-run efficiency fade, last 90 days vs the 90 before."""
    now = [f["fade_pct"] for f in fades if end - timedelta(days=90) < f["day"] <= end]
    then = [f["fade_pct"] for f in fades if end - timedelta(days=180) < f["day"] <= end - timedelta(days=90)]
    if len(now) < 3:
        return None
    return {"fade_now": round(median(now), 1), "fade_before": round(median(then), 1) if len(then) >= 3 else None, "n": len(now)}
