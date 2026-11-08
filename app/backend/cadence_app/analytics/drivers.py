"""Improve, part 1: a personal baseline, the recent trend and what is associated with moving the metric (pure).

Everything here is an association in one person's own history; nothing is causal. Methods:
- Baseline: mean and SD over the last 60 days (needs 14 nights) and the coefficient of variation of the last 7 values.
  A rolling 7-day mean against your own baseline and CV, not single nights (Plews 2013; Flatt & Esco 2016).
- Trend: OLS of the value on time over 84 days with Newey-West errors (`regress.ols`, Newey & West 1987); "steady" when
  the 95% range of the change includes 0.
- Daily drivers (HRV, resting HR): the day-group contrasts already computed by `athlete.compare` (covariate-adjusted,
  autocorrelation-widened, >= 8 days each way) are re-graded together with Benjamini-Hochberg across ALL tests for that
  target (Benjamini & Hochberg 1995): q < 0.05 is "clear", q < 0.2 a "hint". Their 95% range is recovered from the
  reported p-value and effective sample size, so it is approximate.
- VO2max (sparse, step-like): weekly aggregates over at least 12 weeks and 6 readings; Spearman correlation between
  the 4-week mean exposure before a reading week and that week's change, with a block permutation p-value (blocks of 3
  weeks, 2,000 shuffles) and a moving-block bootstrap range for the change per +1 SD.
Never shown: any test below the minimum data rules, and nothing about a day without a value (missing is not zero).
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta
from statistics import fmean, stdev

import numpy as np
from scipy import stats

from cadence_app.analytics import athlete as A
from cadence_app.analytics import regress

DAY = timedelta(days=1)
BASELINE_DAYS, BASELINE_MIN = 60, 14
TREND_DAYS, TREND_MIN = 84, 40
NEEDED = {"hrv": 40, "resting_hr": 40, "vo2max": 6}
UNITS = {"hrv": "ms", "resting_hr": "bpm", "vo2max": "mL/kg/min"}
HIGHER_BETTER = {"hrv": True, "resting_hr": False, "vo2max": True}
VO2_MIN_WEEKS, VO2_MIN_PAIRS, BLOCK, SHUFFLES, BOOT = 12, 8, 3, 2000, 1000
CLEAR_Q, HINT_Q, MAX_SHOWN = 0.05, 0.2, 5
# lagged_effects() ids per target; journal habits are matched on their outcome key
LAGGED = {"hrv": {"load_hrv", "sleep_hrv", "bed_hrv", "late_hrv"}, "resting_hr": {"load_rhr", "sleep_rhr"}}


def window_values(series: A.Series, end: date, days: int) -> list[tuple[date, float]]:
    return sorted((d, v) for d, v in series.items() if end - days * DAY < d <= end and v is not None)


def baseline(series: A.Series, as_of: date, metric: str) -> dict | None:
    """Mean, SD, band (mean +/- 0.75 SD) over the last 60 days and the CV of the last 7 values; None below 14 values."""
    vals = window_values(series, as_of, BASELINE_DAYS if metric != "vo2max" else 180)
    if len(vals) < (BASELINE_MIN if metric != "vo2max" else 3):
        return None
    xs = [v for _, v in vals]
    mean, sd = fmean(xs), stdev(xs) if len(xs) > 1 else 0.0
    last7 = [v for d, v in vals if d > as_of - 7 * DAY]
    cv = round(stdev(last7) / fmean(last7) * 100, 1) if len(last7) >= 4 and fmean(last7) else None
    nd = 1 if metric == "vo2max" else 1
    return {"mean": round(mean, nd), "sd": round(sd, 1), "cv_7d": cv if metric != "vo2max" else None,
            "band": [round(mean - 0.75 * sd, 1), round(mean + 0.75 * sd, 1)], "n": len(xs),
            "window_days": BASELINE_DAYS if metric != "vo2max" else 180, "unit": UNITS[metric],
            "mean_7d": round(fmean(last7), 1) if len(last7) >= 3 else None, "n_7d": len(last7)}


def trend(series: A.Series, as_of: date, metric: str) -> dict:
    vals = window_values(series, as_of, TREND_DAYS if metric != "vo2max" else 180)
    need = TREND_MIN if metric != "vo2max" else NEEDED["vo2max"]
    out = {"direction": "too_early", "change": None, "ci": None, "n": len(vals)}
    if len(vals) < need or (vals[-1][0] - vals[0][0]).days < (TREND_DAYS * 0.5 if metric != "vo2max" else 7 * VO2_MIN_WEEKS):
        return out
    x = np.array([(d - vals[0][0]).days for d, _ in vals], dtype=float)
    y = np.array([v for _, v in vals])
    fit = regress.ols(np.column_stack([np.ones_like(x), x]), y, lags=min(7, len(vals) // 4))
    if fit is None:
        return out
    span = float(x[-1] - x[0])
    lo, hi = float(fit["ci"][1][0]) * span, float(fit["ci"][1][1]) * span
    change = float(fit["coef"][1]) * span
    out.update(change=round(change, 1), ci=[round(lo, 1), round(hi, 1)],
               direction="up" if lo > 0 else "down" if hi < 0 else "steady")
    return out


# ---- daily drivers (HRV, resting HR) -------------------------------------------------------------------------------


def _interval(e: A.Effect) -> list[float] | None:
    """Approximate 95% range of an adjusted day-group difference from its p-value and effective sample size."""
    if e.diff == 0 or not 0 < e.p_value < 1:
        return None
    df = max(e.n_effective - 2, 3.0)
    t = float(stats.t.isf(max(e.p_value, 1e-300) / 2, df))
    if t <= 0:
        return None
    se = abs(e.diff) / t
    crit = float(stats.t.ppf(0.975, df))
    return [round(e.diff - crit * se, 2), round(e.diff + crit * se, 2)]


def candidate_effects(metric: str, lagged: list[A.Effect], habits: list[A.Effect]) -> list[A.Effect]:
    """The already computed contrasts for one target, copied so the shared context is never altered."""
    out = [replace(e) for e in lagged if e.id in LAGGED.get(metric, ())]
    out += [replace(e) for e in habits if e.extra.get("outcome") == metric]
    return out


def grade(effects: list[A.Effect]) -> list[dict]:
    """BH across every test for the target, then the clear ones (largest standardised effect first) before the hints."""
    A.control_fdr(effects)
    rows = []
    for e in effects:
        ci = _interval(e)
        if ci is None or e.q_value >= HINT_Q:
            continue
        key = e.extra.get("behaviour") or e.id.rsplit("_", 1)[0]
        rows.append({
            "id": f"{key}_{e.id.rsplit('_', 1)[-1]}" if e.extra.get("behaviour") is None else f"{key}_{e.extra['outcome']}",
            "exposure": e.exposed, "reference": e.reference, "lag_days": e.lag_days, "diff": e.diff, "unit": e.unit, "pct": e.pct, "ci": ci,
            "n_exposed": e.n_exposed, "n_reference": e.n_reference, "n_effective": e.n_effective, "q": round(e.q_value, 4),
            "grade": "clear" if e.q_value < CLEAR_Q else "hint", "adjusted_for": list(e.adjusted_for),
            "_size": abs(e.effect_size), "_cause": e.cause, "_outcome": e.outcome, "_higher_is_better": e.higher_is_better, "_behaviour": e.extra.get("behaviour"),
        })
    rows.sort(key=lambda r: (r["grade"] != "clear", -r["_size"], r["id"]))
    return rows[:MAX_SHOWN]


def progress(habit_progress: list[dict]) -> list[dict]:
    """Journal behaviours still short of the minimum days each way: {key, have (the smaller side), needed}."""
    return [{"key": p["key"], "label": p["label"], "have": min(p["yes"], p["no"]), "needed": p["needed"]} for p in habit_progress if not p["ready"]]


# ---- VO2max: weekly aggregates -------------------------------------------------------------------------------------


def _weekly_mean(points: list[tuple[date, float]]) -> dict[date, float]:
    by: dict[date, list[float]] = {}
    for d, v in points:
        by.setdefault(A.week_start(d), []).append(v)
    return {w: fmean(v) for w, v in by.items()}


def _block_perm_p(x: np.ndarray, y: np.ndarray, rho: float, rng: np.random.Generator) -> float:
    n = len(x)
    blocks = [x[i:i + BLOCK] for i in range(0, n, BLOCK)]
    hits = 0
    for _ in range(SHUFFLES):
        order = rng.permutation(len(blocks))
        xp = np.concatenate([blocks[i] for i in order])
        r = stats.spearmanr(xp, y)[0]
        hits += abs(r) >= abs(rho) - 1e-12
    return (hits + 1) / (SHUFFLES + 1)


def _block_boot(z: np.ndarray, d: np.ndarray, rng: np.random.Generator) -> list[float] | None:
    n = len(z)
    starts = np.arange(0, n - BLOCK + 1)
    slopes = []
    for _ in range(BOOT):
        idx = np.concatenate([np.arange(s, s + BLOCK) for s in rng.choice(starts, size=math.ceil(n / BLOCK))])[:n]
        if np.ptp(z[idx]) == 0:
            continue
        slopes.append(np.polyfit(z[idx], d[idx], 1)[0])
    if len(slopes) < BOOT * 0.8:
        return None
    return [round(float(np.percentile(slopes, 2.5)), 2), round(float(np.percentile(slopes, 97.5)), 2)]


def vo2_drivers(vo2: list[tuple[date, float]], exposures: dict[str, dict], as_of: date, seed: int = 7) -> dict:
    """`exposures`: key -> {label, unit_label, weekly: {week_start: value}, cause}. Returns {drivers, tested, reason}.

    Below 12 weeks / 6 readings / 8 usable pairs nothing is tested (reason says why)."""
    pts = [(d, v) for d, v in vo2 if d <= as_of and v is not None]
    if len(pts) < NEEDED["vo2max"] or (pts[-1][0] - pts[0][0]).days < 7 * VO2_MIN_WEEKS:
        return {"drivers": [], "tested": 0, "reason": f"{len(pts)} readings over {(pts[-1][0] - pts[0][0]).days // 7 if pts else 0} weeks"}
    y = _weekly_mean(pts)
    weeks = sorted(y)
    mean_y = fmean(y.values())
    effects: list[A.Effect] = []
    meta: dict[str, dict] = {}
    for key, ex in exposures.items():
        xs, ds = [], []
        for prev, w in zip(weeks, weeks[1:]):
            if (w - prev).days > 21:
                continue
            before = [ex["weekly"][w - k * 7 * DAY] for k in range(1, 5) if (w - k * 7 * DAY) in ex["weekly"]]
            if len(before) < 3:
                continue
            xs.append(fmean(before))
            ds.append(y[w] - y[prev])
        if len(xs) < VO2_MIN_PAIRS or np.ptp(xs) == 0:
            continue
        x, d = np.array(xs), np.array(ds)
        rho = float(stats.spearmanr(x, d)[0])
        if math.isnan(rho):
            continue
        rng = np.random.default_rng(seed)
        p = _block_perm_p(x, d, rho, rng)
        z = (x - x.mean()) / x.std()
        slope = float(np.polyfit(z, d, 1)[0])
        ci = _block_boot(z, d, rng)
        if ci is None:
            continue
        med = float(np.median(x))
        hi_n, lo_n = int((x > med).sum()), int((x <= med).sum())
        r1 = float(np.corrcoef(x[:-1], x[1:])[0, 1]) if len(x) > 3 and np.ptp(x[:-1]) and np.ptp(x[1:]) else 0.0
        r1 = 0.0 if math.isnan(r1) else max(0.0, min(0.8, r1))
        e = A.Effect(f"{key}_vo2max", ex["cause"], "VO2max (Garmin's estimate)", f"Higher {ex['label']} (+1 SD)", f"Typical {ex['label']}", 0, "mL/kg/min", True,
                     diff=round(slope, 2), pct=round(slope / mean_y * 100, 1) if mean_y else 0.0, n_exposed=hi_n, n_reference=lo_n, p_value=p,
                     effect_size=round(abs(rho), 2), n_effective=round(len(x) * (1 - r1) / (1 + r1), 1), adjusted_for=[], extra={"ci": ci, "pairs": len(x)})
        effects.append(e)
        meta[e.id] = ex
    A.control_fdr(effects)
    rows = []
    for e in effects:
        if e.q_value >= HINT_Q:
            continue
        rows.append({"id": e.id, "exposure": e.exposed, "reference": e.reference, "lag_days": 0, "diff": e.diff, "unit": e.unit, "pct": e.pct, "ci": e.extra["ci"],
                     "n_exposed": e.n_exposed, "n_reference": e.n_reference, "n_effective": e.n_effective, "q": round(e.q_value, 4),
                     "grade": "clear" if e.q_value < CLEAR_Q else "hint", "adjusted_for": [], "_size": e.effect_size, "_cause": e.cause, "_outcome": e.outcome,
                     "_higher_is_better": True, "_behaviour": None})
    rows.sort(key=lambda r: (r["grade"] != "clear", -r["_size"], r["id"]))
    return {"drivers": rows[:MAX_SHOWN], "tested": len(effects), "reason": None}
