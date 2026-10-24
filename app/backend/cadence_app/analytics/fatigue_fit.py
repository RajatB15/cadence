"""How fast do YOU shake off training? Fitted from your own overnight HRV and resting heart rate.

The standard fitness model assumes fatigue fades with a 7-day time constant. Your body shows its fatigue directly: overnight
HRV falls and resting HR rises after hard training (Plews et al. 2013; Buchheit 2014). So for each night we build a strain
signal, the mean of -z(HRV) and +z(resting HR) against your trailing 60-day baseline, and ask which fatigue time constant
(an exponentially weighted average of the load up to the previous day) explains it best.

Safeguards, as for the personal Banister fit (analytics/banister.py):
- the fitted constant is only adopted if it predicts held-out blocks of days at least 10 % better than both the standard
  7-day constant and the plain average;
- the plausible range comes from an F-test with the sample size shrunk for autocorrelation, so it is wide when the nights
  are strongly serially correlated (they are);
- the load effect must be positive (more recent load, more strain), otherwise nothing is adopted.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from scipy import stats
from scipy.signal import lfilter

from cadence_app.analytics import athlete as A

TAU_GRID = tuple(range(2, 22))
DEFAULT_TAU = A.ATL_DAYS
BASELINE_DAYS, MIN_BASELINE = 150, 30
MIN_NIGHTS = 60
MIN_SPAN_DAYS = 90
MIN_ACTIVE_DAYS = 30
CV_FOLDS = 5
CV_GAIN = 0.90  # stricter than the Banister fit: the 150-day baseline pulls slow constants a little low, so a small win is not trusted


def _z(series: A.Series, d: date) -> float | None:
    """z-score of the night against the prior BASELINE_DAYS (a long baseline: a short one would subtract slow fatigue away)."""
    if d not in series:
        return None
    prior = [series[x] for x in A.daterange(d - timedelta(days=BASELINE_DAYS), d - timedelta(days=1)) if x in series]
    if len(prior) < MIN_BASELINE:
        return None
    sd = float(np.std(prior))
    return (series[d] - float(np.mean(prior))) / sd if sd > 0 else 0.0


def strain_signal(hrv: A.Series, rhr: A.Series) -> dict[date, float]:
    """Per night: mean of -z(HRV) and +z(resting HR) against the prior 150 days; higher is more strained."""
    out = {}
    for d in sorted(set(hrv) | set(rhr)):
        parts = []
        if (z := _z(hrv, d)) is not None:
            parts.append(-z)
        if (z := _z(rhr, d)) is not None:
            parts.append(z)
        if parts:
            out[d] = sum(parts) / len(parts)
    return out


def _acute_before(w: np.ndarray, tau: float) -> np.ndarray:
    """Exponentially weighted average of load through the previous day, for each day."""
    a = 1 / tau
    after = lfilter([a], [1.0, -(1 - a)], w)
    return np.concatenate([[0.0], after[:-1]])


def _fit_one(acute: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """intercept, slope, SSE for y ~ a + c·acute."""
    x = acute - acute.mean()
    sxx = float(x @ x)
    c = float(x @ (y - y.mean())) / sxx if sxx > 0 else 0.0
    a = float(y.mean() - c * acute.mean())
    resid = y - (a + c * acute)
    return a, c, float(resid @ resid)


def fit(load: A.Series, hrv: A.Series, rhr: A.Series, as_of: date) -> dict:
    out: dict = {"valid": False, "adopted": False}
    signal = {d: v for d, v in strain_signal(hrv, rhr).items() if d <= as_of}
    active = sum(1 for v in load.values() if v > 0)
    days = sorted(signal)
    span = (days[-1] - days[0]).days if days else 0
    out["n"] = len(days)
    if len(days) < MIN_NIGHTS or span < MIN_SPAN_DAYS or active < MIN_ACTIVE_DAYS:
        out["missing"] = f"{MIN_NIGHTS}+ nights of HRV or resting heart rate over {MIN_SPAN_DAYS}+ days, with training load"
        return out
    start = min(min(load, default=days[0]), days[0])
    n_days = (as_of - start).days + 1
    w = np.zeros(n_days)
    for d, x in load.items():
        if start <= d <= as_of:
            w[(d - start).days] = x
    idx = np.array([(d - start).days for d in days])
    y = np.array([signal[d] for d in days])
    acute = {t: _acute_before(w, t)[idx] for t in set(TAU_GRID) | {DEFAULT_TAU}}
    fits = {t: _fit_one(acute[t], y) for t in TAU_GRID}
    usable = {t: f for t, f in fits.items() if f[1] > 0}
    if not usable:
        out.update(valid=True, why_not="Recent training load did not line up with higher strain in your nights")
        return out
    tau = min(usable, key=lambda t: usable[t][2])
    a, c, sse = usable[tau]
    resid = y - (a + c * acute[tau])
    rho = float(np.corrcoef(resid[:-1], resid[1:])[0, 1]) if len(resid) > 3 and sse > 0 else 0.0
    rho = 0.0 if math.isnan(rho) else max(0.0, min(0.97, rho))
    n_eff = max(6.0, len(y) * (1 - rho) / (1 + rho))
    df = max(n_eff - 3, 1.0)
    limit = sse * (1 + stats.f.ppf(0.95, 1, df) / df)
    region = sorted(t for t, f in usable.items() if f[2] <= limit)

    sq = {"personal": 0.0, "default": 0.0, "mean": 0.0}
    for test in np.array_split(np.arange(len(y)), CV_FOLDS):
        train = np.setdiff1d(np.arange(len(y)), test)
        best = min(((t, _fit_one(acute[t][train], y[train])) for t in TAU_GRID), key=lambda kv: kv[1][2] if kv[1][1] > 0 else math.inf)
        t_best, (ta, tc, _) = best
        sq["personal"] += float(np.sum((y[test] - (ta + tc * acute[t_best][test])) ** 2))
        da, dc, _ = _fit_one(acute[DEFAULT_TAU][train], y[train])
        sq["default"] += float(np.sum((y[test] - (da + dc * acute[DEFAULT_TAU][test])) ** 2))
        sq["mean"] += float(np.sum((y[test] - y[train].mean()) ** 2))
    cv = {k: math.sqrt(v / len(y)) for k, v in sq.items()}
    adopted = cv["personal"] <= CV_GAIN * cv["default"] and cv["personal"] <= CV_GAIN * cv["mean"]
    weekly: dict[date, list[tuple[float, float]]] = {}
    for d, yy, fx in zip(days, y, a + c * acute[tau]):
        weekly.setdefault(A.week_start(d), []).append((float(yy), float(fx)))
    out.update(
        valid=True, adopted=bool(adopted), tau=tau, half_life_days=round(tau * math.log(2), 1), default_tau=DEFAULT_TAU,
        region=[region[0], region[-1]], n_eff=round(n_eff, 1), span_days=span,
        bump_per_100_load=round(c * 100 / tau, 3),
        cv={"personal": round(cv["personal"], 4), "default": round(cv["default"], 4), "mean": round(cv["mean"], 4),
            "gain_vs_default_pct": round((1 - cv["personal"] / cv["default"]) * 100, 1) if cv["default"] > 0 else 0.0,
            "gain_vs_mean_pct": round((1 - cv["personal"] / cv["mean"]) * 100, 1) if cv["mean"] > 0 else 0.0},
        consistent_with_default=DEFAULT_TAU in region,
        series=[{"day": wk + timedelta(days=3), "observed": round(float(np.mean([p[0] for p in v])), 3), "fitted": round(float(np.mean([p[1] for p in v])), 3)}
                for wk, v in sorted(weekly.items())],
    )
    if not adopted:
        out["why_not"] = "it did not predict held-out stretches of nights at least 10 % better than the standard 7-day constant and the plain average"
    return out
