"""Personal Banister impulse-response fit: how quickly YOUR fitness builds and fades, from your own training.

Model (Banister et al., 1975; Calvert et al., 1976; refit by constrained least squares as in Hellard et al., 2006):

    performance(t) = p0 + k1 · Σ w(s)·exp(-(t-s)/τ1)  −  k2 · Σ w(s)·exp(-(t-s)/τ2),   s < t

with w the daily training load. For any (τ1, τ2) the rest (p0, k1 ≥ 0, k2 ≥ 0) is a linear problem, so τ1 and τ2 are
found by an exhaustive grid search rather than a local optimiser (no bad starting points).

Few data points, strong autocorrelation and many free parameters make this fit fragile (Hellard et al. 2006; Hayes &
Quinn 2009), so nothing is trusted on in-sample fit alone:
- the personal τ pair is only adopted if, on blocked time-ordered cross-validation, it predicts held-out weeks at least
  5 % better than both the fixed 42/7-day constants and simply predicting the average;
- the 95 % region for (τ1, τ2) comes from an F-test on the sum of squares with the sample size shrunk for residual
  autocorrelation, so it is wide when the data are thin;
- the series is a weekly median of aerobic efficiency (heat-adjusted when possible), not a race or test result: it is
  a proxy for fitness, and a monthly critical-speed history gives too few points to fit anything.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from scipy import stats
from scipy.optimize import nnls
from scipy.signal import lfilter

from cadence_app.analytics import athlete as A

TAU1_GRID = tuple(range(20, 91, 2))
TAU2_GRID = tuple(range(3, 25))
DEFAULT_TAUS = (A.CTL_DAYS, A.ATL_DAYS)
MIN_OBS = 16
MIN_SPAN_DAYS = 150
MIN_ACTIVE_DAYS = 60
CV_FOLDS = 5
CV_GAIN = 0.95  # personal CV error must be ≤ 95 % of both baselines
HORIZON = 35


ALPHAS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5)


def effective(load: A.Series, alpha: float) -> A.Series:
    """Diminishing returns: each day's load raised to `alpha` (< 1 flattens big days), rescaled so typical days keep their size."""
    if alpha >= 1.0:
        return dict(load)
    positive = [v for v in load.values() if v > 0]
    if not positive:
        return dict(load)
    m = float(np.mean(positive))
    return {d: (v ** alpha) * (m ** (1 - alpha)) if v > 0 else 0.0 for d, v in load.items()}


def saturation(load: A.Series, obs: list[tuple[date, float]], as_of: date) -> dict:
    """Does a big day buy proportionally less fitness? Picks alpha by held-out error at the standard 42/7-day constants.

    alpha = 1 is "load counts linearly". A smaller alpha is only adopted if it predicts unseen weeks at least 5 % better
    than linear load, so a flat-looking history can't talk the model into a curve.
    """
    obs = sorted((d, v) for d, v in obs if d <= as_of)
    out: dict = {"valid": False, "adopted": False, "alpha": 1.0, "n": len(obs)}
    active = sum(1 for v in load.values() if v > 0)
    span = (obs[-1][0] - obs[0][0]).days if obs else 0
    if len(obs) < MIN_OBS or span < MIN_SPAN_DAYS or active < MIN_ACTIVE_DAYS:
        out["missing"] = f"at least {MIN_OBS} weeks of runs with heart rate over {MIN_SPAN_DAYS}+ days"
        return out
    start = min(min(load, default=obs[0][0]), obs[0][0])
    days = (as_of - start).days + 1
    idx = np.array([(d - start).days for d, _ in obs])
    y = np.array([v for _, v in obs])
    scores = {}
    for a in ALPHAS:
        eff = effective(load, a)
        w = np.zeros(days)
        for d, x in eff.items():
            if start <= d <= as_of:
                w[(d - start).days] = x
        e1, e2 = _impulse(w, DEFAULT_TAUS[0])[idx], _impulse(w, DEFAULT_TAUS[1])[idx]
        sq = 0.0
        for test in np.array_split(np.arange(len(y)), CV_FOLDS):
            train = np.setdiff1d(np.arange(len(y)), test)
            p0, k1, k2, _ = _linear(e1[train], e2[train], y[train])
            sq += float(np.sum((y[test] - (p0 + k1 * e1[test] - k2 * e2[test])) ** 2))
        scores[a] = math.sqrt(sq / len(y))
    best = min(scores, key=scores.get)
    gain = 1 - scores[best] / scores[1.0] if scores[1.0] > 0 else 0.0
    adopted = best < 1.0 and gain >= 1 - CV_GAIN
    out.update(valid=True, adopted=bool(adopted), alpha=best if adopted else 1.0, best_alpha=best, gain_pct=round(gain * 100, 1),
               cv={f"{a:g}": round(v, 5) for a, v in scores.items()})
    return out


def weekly_series(points: list[dict], key: str = "ef") -> list[tuple[date, float]]:
    """Weekly median of per-run values, dated at the week's midpoint."""
    weeks: dict[date, list[float]] = {}
    for p in points:
        weeks.setdefault(A.week_start(p["day"]), []).append(p[key])
    return [(w + timedelta(days=3), float(np.median(v))) for w, v in sorted(weeks.items())]


def _impulse(w: np.ndarray, tau: float) -> np.ndarray:
    """e[t] = Σ_{s<t} w[s]·exp(-(t-s)/τ)."""
    r = math.exp(-1 / tau)
    return lfilter([0.0, r], [1.0, -r], w)


def _linear(e1: np.ndarray, e2: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float]:
    """Best p0, k1 ≥ 0, k2 ≥ 0 for fixed τs → (p0, k1, k2, SSE)."""
    m1, m2, my = e1.mean(), e2.mean(), y.mean()
    x = np.column_stack([e1 - m1, -(e2 - m2)])
    scale = np.maximum(np.linalg.norm(x, axis=0), 1e-12)
    coef, _ = nnls(x / scale, y - my)
    k1, k2 = coef / scale
    p0 = my - k1 * m1 + k2 * m2
    resid = y - (p0 + k1 * e1 - k2 * e2)
    return float(p0), float(k1), float(k2), float(resid @ resid)


class _Grid:
    def __init__(self, w: np.ndarray, idx: np.ndarray):
        self.e1 = {t: _impulse(w, t)[idx] for t in TAU1_GRID}
        self.e2 = {t: _impulse(w, t)[idx] for t in TAU2_GRID}

    def search(self, y: np.ndarray, rows: np.ndarray) -> list[tuple[float, int, int, float, float, float]]:
        out = []
        for t1 in TAU1_GRID:
            for t2 in TAU2_GRID:
                if t1 >= 2 * t2:
                    p0, k1, k2, sse = _linear(self.e1[t1][rows], self.e2[t2][rows], y[rows])
                    out.append((sse, t1, t2, p0, k1, k2))
        return out

    def predict(self, t1: int, t2: int, p0: float, k1: float, k2: float, rows: np.ndarray) -> np.ndarray:
        return p0 + k1 * self.e1[t1][rows] - k2 * self.e2[t2][rows]


def _cross_validate(g: _Grid, y: np.ndarray) -> dict:
    n = len(y)
    folds = np.array_split(np.arange(n), CV_FOLDS)
    sq = {"personal": 0.0, "default": 0.0, "mean": 0.0}
    for test in folds:
        train = np.setdiff1d(np.arange(n), test)
        sse, t1, t2, p0, k1, k2 = min(g.search(y, train))
        sq["personal"] += float(np.sum((y[test] - g.predict(t1, t2, p0, k1, k2, test)) ** 2))
        d0, dk1, dk2, _ = _linear(g.e1[DEFAULT_TAUS[0]][train], g.e2[DEFAULT_TAUS[1]][train], y[train])
        sq["default"] += float(np.sum((y[test] - g.predict(*DEFAULT_TAUS, d0, dk1, dk2, test)) ** 2))
        sq["mean"] += float(np.sum((y[test] - y[train].mean()) ** 2))
    return {k: math.sqrt(v / n) for k, v in sq.items()}


def _n_eff(resid: np.ndarray) -> float:
    n = len(resid)
    if n < 4 or float(resid @ resid) == 0:
        return float(n)
    rho = float(np.corrcoef(resid[:-1], resid[1:])[0, 1])
    rho = 0.0 if math.isnan(rho) else max(0.0, min(0.95, rho))
    return max(6.0, n * (1 - rho) / (1 + rho))


def fit(load: A.Series, obs: list[tuple[date, float]], as_of: date) -> dict:
    """Fit τ1, τ2, k1, k2, p0 to the observed performance series. Always returns a dict; `valid` and `adopted` say how far to trust it."""
    out: dict = {"valid": False, "adopted": False, "n": len(obs), "min_obs": MIN_OBS}
    obs = sorted((d, v) for d, v in obs if d <= as_of)
    out["n"] = len(obs)
    active = sum(1 for v in load.values() if v > 0)
    span = (obs[-1][0] - obs[0][0]).days if obs else 0
    if len(obs) < MIN_OBS or span < MIN_SPAN_DAYS or active < MIN_ACTIVE_DAYS:
        out["missing"] = (f"at least {MIN_OBS} weeks of runs with heart rate over {MIN_SPAN_DAYS}+ days "
                          f"(you have {len(obs)} weeks over {span} days)" if active >= MIN_ACTIVE_DAYS else f"{MIN_ACTIVE_DAYS}+ days with training load")
        return out
    start = min(min(load, default=obs[0][0]), obs[0][0])
    days = (as_of - start).days + 1
    w = np.zeros(days)
    for d, x in load.items():
        if start <= d <= as_of:
            w[(d - start).days] = x
    idx = np.array([(d - start).days for d, _ in obs])
    y = np.array([v for _, v in obs])
    g = _Grid(w, idx)
    rows = np.arange(len(y))
    fits = g.search(y, rows)
    sse, t1, t2, p0, k1, k2 = min(fits)
    total = float(np.sum((y - y.mean()) ** 2))
    resid = y - g.predict(t1, t2, p0, k1, k2, rows)
    n_eff = _n_eff(resid)
    df = max(n_eff - 5, 1.0)
    limit = sse * (1 + 2 / df * stats.f.ppf(0.95, 2, df))
    region = [f for f in fits if f[0] <= limit]
    cv = _cross_validate(g, y)
    gain_default = 1 - cv["personal"] / cv["default"] if cv["default"] > 0 else 0.0
    gain_mean = 1 - cv["personal"] / cv["mean"] if cv["mean"] > 0 else 0.0
    nondegenerate = k1 > 0 and k2 > 0
    adopted = nondegenerate and cv["personal"] <= CV_GAIN * cv["default"] and cv["personal"] <= CV_GAIN * cv["mean"]
    out.update(
        valid=True, adopted=bool(adopted), tau1=t1, tau2=t2, k1=k1, k2=k2, p0=p0,
        r2=round(1 - sse / total, 3) if total > 0 else None,
        region={"tau1": [min(f[1] for f in region), max(f[1] for f in region)], "tau2": [min(f[2] for f in region), max(f[2] for f in region)],
                "n_eff": round(n_eff, 1), "points": len(region), "of": len(fits)},
        cv={"personal": round(cv["personal"], 5), "default": round(cv["default"], 5), "mean": round(cv["mean"], 5),
            "gain_vs_default_pct": round(gain_default * 100, 1), "gain_vs_mean_pct": round(gain_mean * 100, 1)},
        default_taus=list(DEFAULT_TAUS), span_days=span,
    )
    out["consistent_with_default"] = bool(any(f[1] == DEFAULT_TAUS[0] and f[2] == DEFAULT_TAUS[1] for f in region))
    if not adopted:
        out["why_not"] = ("fatigue or fitness did not come out as a positive effect" if not nondegenerate else
                          "it did not predict held-out weeks at least 5 % better than the standard 42/7-day constants and the plain average")
    step = max(1, len(region) // 25)
    out["region_pairs"] = [(f[1], f[2]) for f in region[::step]]
    out["series"] = [{"day": d, "observed": round(float(v), 4), "fitted": round(float(f), 4)} for (d, v), f in zip(obs, y - resid)]
    out["taper"] = taper(load, start, as_of, t1, t2, p0, k1, k2, region)
    out["_model"] = {"start": start, "taus": (t1, t2), "coef": (p0, k1, k2)}
    return out


def curve(model: dict, load: A.Series, end: date, step: int = 3, since: date | None = None) -> list[dict]:
    """Modelled performance on every `step`-th day for a (possibly altered) load history."""
    m = model["_model"]
    start = m["start"]
    days = (end - start).days + 1
    w = np.zeros(days)
    for d, x in load.items():
        if start <= d <= end:
            w[(d - start).days] = x
    t1, t2 = m["taus"]
    p0, k1, k2 = m["coef"]
    perf = p0 + k1 * _impulse(w, t1) - k2 * _impulse(w, t2)
    first = since or start
    return [{"day": start + timedelta(days=i), "value": float(perf[i])} for i in range((first - start).days, days) if (days - 1 - i) % step == 0]


def taper(load: A.Series, start: date, as_of: date, t1: int, t2: int, p0: float, k1: float, k2: float, region: list) -> dict | None:
    """If you stopped training after `as_of`: when does modelled performance peak? (a model statement, not a prescription)"""
    days = (as_of - start).days + 1
    w = np.zeros(days + HORIZON)
    for d, x in load.items():
        if start <= d <= as_of:
            w[(d - start).days] = x

    def peak(a: int, b: int, c0: float, c1: float, c2: float) -> tuple[int, float, float]:
        e1, e2 = _impulse(w, a), _impulse(w, b)
        perf = c0 + c1 * e1[days:] - c2 * e2[days:]
        now = float(c0 + c1 * e1[days - 1] - c2 * e2[days - 1])
        i = int(np.argmax(perf))
        return i + 1, float(perf[i]) - now, now

    day, gain, now = peak(t1, t2, p0, k1, k2)
    if gain <= 0:
        return {"peak_day": 0, "gain_pct": 0.0, "range": [0, 0]}
    # the same peak under the other (τ1, τ2) the data can't rule out (their own p0, k1, k2)
    others = [peak(f[1], f[2], f[3], f[4], f[5])[0] for f in region[:: max(1, len(region) // 25)] if f[4] > 0 and f[5] > 0]
    return {"peak_day": day, "gain_pct": round(gain / abs(now) * 100, 1) if now else None, "range": [min(others), max(others)] if others else [day, day]}


def public(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}
