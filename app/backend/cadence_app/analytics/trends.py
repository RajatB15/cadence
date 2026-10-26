"""Trend of a daily 0-100 score (readiness, Cadence score) over a window: average, change, direction and where it is heading.

- The direction comes from a straight-line fit with Newey-West standard errors (daily scores are autocorrelated, so plain
  errors would call every wobble a trend; Newey & West 1987). It is called "up" or "down" only when the 95% interval of
  the slope excludes zero and at least MIN_DAYS days exist; otherwise "steady" or "too early to say".
- "Heading" is the same line carried forward 4 weeks with its 95% interval. It is an extrapolation of the recent past,
  not a forecast: it assumes nothing about sleep, training or illness changes.
- A window is compared with the equal window just before it; fewer than HALF of the days with data on either side gives no change.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean

import numpy as np

from cadence_app.analytics import regress

MIN_DAYS = 10
HALF = 0.5
HORIZON_DAYS = 28
DAY = timedelta(days=1)


def _fit(points: list[tuple[int, float]]) -> dict | None:
    if len(points) < MIN_DAYS:
        return None
    x = np.array([p[0] for p in points], dtype=float)
    y = np.array([p[1] for p in points], dtype=float)
    design = np.column_stack([np.ones_like(x), x])
    fit = regress.ols(design, y, lags=min(7, len(points) // 4))
    if fit is None:
        return None
    return {"slope": float(fit["coef"][1]), "ci": (float(fit["ci"][1][0]), float(fit["ci"][1][1])),
            "intercept": float(fit["coef"][0]), "se": float(fit["se"][1]), "x_last": float(x[-1]), "x_mean": float(x.mean()),
            "sxx": float(np.sum((x - x.mean()) ** 2)), "resid_sd": float(np.std(y - design @ fit["coef"], ddof=2)), "n": len(points)}


def summarise(history: list[dict], as_of: date, days: int, key: str = "score") -> dict:
    """`history`: [{day, <key>}], one per day with data. Returns the window's numbers, its weekly buckets and where it is heading."""
    start = as_of - (days - 1) * DAY
    prev_start = start - days * DAY
    now = [(h["day"], h[key]) for h in history if start <= h["day"] <= as_of]
    before = [h[key] for h in history if prev_start <= h["day"] < start]
    out: dict = {"days": days, "n": len(now), "avg": None, "min": None, "max": None, "prev_avg": None, "delta": None,
                 "direction": None, "slope_per_week": None, "slope_ci": None, "heading": None, "bands": None, "buckets": [], "values": []}
    out["values"] = [{"day": d, "value": v} for d, v in now]
    if not now:
        return out
    vals = [v for _, v in now]
    out.update(avg=round(fmean(vals), 1), min=min(vals), max=max(vals))
    out["bands"] = {"high": sum(v >= 70 for v in vals), "mid": sum(50 <= v < 70 for v in vals), "low": sum(v < 50 for v in vals)}
    if len(before) >= HALF * days and len(now) >= HALF * days:
        out["prev_avg"] = round(fmean(before), 1)
        out["delta"] = round(fmean(vals) - fmean(before), 1)
    # Weekly (or, for short windows, daily) averages: a week is only shown with 3+ days behind it.
    if days <= 14:
        out["buckets"] = [{"start": d, "avg": v, "n": 1} for d, v in now]
    else:
        by_week: dict[date, list[float]] = {}
        for d, v in now:
            by_week.setdefault(d - timedelta(days=d.weekday()), []).append(v)
        out["buckets"] = [{"start": w, "avg": round(fmean(v), 1), "n": len(v)} for w, v in sorted(by_week.items()) if len(v) >= 3]
    fit = _fit([((d - start).days, v) for d, v in now])
    if fit is None:
        out["heading"] = {"direction": "unknown", "text": f"Too early to say where this is heading: {len(now)} days of data in the window, {MIN_DAYS} needed."}
        return out
    lo, hi = fit["ci"]
    weekly = fit["slope"] * 7
    out["slope_per_week"] = round(weekly, 2)
    out["slope_ci"] = [round(lo * 7, 2), round(hi * 7, 2)]
    out["direction"] = "up" if lo > 0 else "down" if hi < 0 else "steady"
    x0 = fit["x_last"] + HORIZON_DAYS
    mid = fit["intercept"] + fit["slope"] * x0
    se_fit = fit["resid_sd"] * (1 / fit["n"] + (x0 - fit["x_mean"]) ** 2 / fit["sxx"]) ** 0.5 if fit["sxx"] > 0 else 0.0
    se = max(se_fit, fit["se"] * abs(x0 - fit["x_mean"]))  # the larger of the textbook and the autocorrelation-robust width
    clamp = lambda v: round(max(0.0, min(100.0, v)))  # noqa: E731
    out["projection"] = {"days": HORIZON_DAYS, "value": clamp(mid), "range": [clamp(mid - 1.96 * se), clamp(mid + 1.96 * se)]}
    text = {"up": f"Rising about {abs(weekly):.1f} points a week (95% range {lo * 7:+.1f} to {hi * 7:+.1f}).",
            "down": f"Falling about {abs(weekly):.1f} points a week (95% range {lo * 7:+.1f} to {hi * 7:+.1f}).",
            "steady": f"No clear direction: the trend is {weekly:+.1f} a week, within the day-to-day noise (95% range {lo * 7:+.1f} to {hi * 7:+.1f})."}[out["direction"]]
    out["heading"] = {"direction": out["direction"], "text": text + f" Carried forward {HORIZON_DAYS} days that is {out['projection']['value']} "
                      f"({out['projection']['range'][0]}–{out['projection']['range'][1]}), an extrapolation, not a forecast."}
    return out
