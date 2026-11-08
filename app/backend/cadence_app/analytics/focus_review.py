"""Improve, part 5: did the metric differ in the four weeks after a focus started? (pure)

Compares the 28 days from the focus start with the 28 days before, with OLS on a step at the start plus a linear
trend and Newey-West errors (lags = 7; `regress.ols`; Newey & West 1987). Needs the full 28 days to have passed and at
least 14 values (VO2max: 4) in each window. The change is a level shift in the metric's unit with its 95% range; the
verdict is only "higher", "lower" or "no_clear_change" (the range excludes 0 or not). Adherence is not measured, so
this cannot tell whether the focus was followed, and it is never evidence that it worked. Context numbers (load, time
off, run-down days) are reported next to it.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean

import numpy as np

from cadence_app.analytics import athlete as A
from cadence_app.analytics import regress

DAY = timedelta(days=1)
WINDOW = 28
MIN_N = {"hrv": 14, "resting_hr": 14, "vo2max": 4}
UNITS = {"hrv": "ms", "resting_hr": "bpm", "vo2max": "mL/kg/min"}


def review(metric: str, series: A.Series, start: date, as_of: date) -> dict | None:
    if start + WINDOW * DAY > as_of + DAY:
        return None
    b0, a1 = start - WINDOW * DAY, start + WINDOW * DAY
    pts = sorted((d, v) for d, v in series.items() if b0 <= d < a1 and v is not None)
    before = [(d, v) for d, v in pts if d < start]
    after = [(d, v) for d, v in pts if d >= start]
    out = {"window": {"n_before": len(before), "n_after": len(after)}, "change": None, "ci": None, "unit": UNITS[metric], "verdict": "no_clear_change", "enough": False}
    need = MIN_N[metric]
    if len(before) < need or len(after) < need:
        return out
    x = np.array([(d - b0).days / WINDOW for d, _ in pts])
    step = np.array([1.0 if d >= start else 0.0 for d, _ in pts])
    y = np.array([v for _, v in pts])
    fit = regress.ols(np.column_stack([np.ones_like(x), step, x]), y, lags=7)
    if fit is None:
        return out
    lo, hi = float(fit["ci"][1][0]), float(fit["ci"][1][1])
    out.update(change=round(float(fit["coef"][1]), 1), ci=[round(lo, 1), round(hi, 1)], enough=True,
               verdict="higher" if lo > 0 else "lower" if hi < 0 else "no_clear_change",
               before_mean=round(fmean(v for _, v in before), 1), after_mean=round(fmean(v for _, v in after), 1))
    return out


def context(load: A.Series, wellbeing: dict, time_off_days: int, start: date) -> dict:
    """Numbers shown beside the review: load change, logged run-down days, days inside logged time off."""
    b = sum(load.get(start - k * DAY, 0.0) for k in range(1, WINDOW + 1))
    a = sum(load.get(start + k * DAY, 0.0) for k in range(WINDOW))
    down = sum(1 for k in range(WINDOW) if (wellbeing.get(start + k * DAY) or {}).get("illness"))
    return {"load_change_pct": round((a / b - 1) * 100) if b > 0 else None, "run_down_days": down, "time_off_days": time_off_days}
