"""Easy minutes and hard minutes are different currencies. Which one moves YOUR aerobic fitness?

Garmin's training load folds every session into one number, so "keep it easy" always looks like pure loss. Here the
training is split into two exposures, each an exponentially weighted weekly volume (28-day time constant):
- aerobic minutes: heart-rate zones 1-3 (everything you could sustain for a long time);
- high-intensity minutes: zones 4-5.
Weekly aerobic efficiency (speed per heartbeat above resting HR, analytics/athlete.py) is then regressed on both, with
Newey–West standard errors (analytics/regress.py). Polarised/threshold training research motivates the split
(Seiler 2010; Stöggl & Sperlich 2014), but how much each channel matters is individual, so it is measured, not assumed.

Safeguards: needs 16+ weekly points over 150+ days with at least 8 weeks that held real high-intensity work; the split is
only adopted if it predicts held-out weeks 5 % better than a single "total minutes" exposure and than the plain average.
Zone 3 counts as aerobic, so turning a grey-zone session into an easy one does not change either channel: that is the
point, and it is why such a swap can cost very little here even though Garmin load drops.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from scipy.signal import lfilter

from cadence_app.analytics import athlete as A
from cadence_app.analytics import banister as B
from cadence_app.analytics import regress as R

TAU = 28
MIN_WEEKS = 16
MIN_SPAN_DAYS = 150
MIN_HIGH_WEEKS = 8
HIGH_WEEK_HW = 0.15  # hours/week-equivalent of high-intensity work that counts as "a week with some"
CV_GAIN = 0.95
FAMILIES = A.INTENSITY_FAMILIES


def act_minutes(a: A.Act) -> tuple[float, float]:
    """(aerobic, high-intensity) minutes of one session; sessions without zones count as aerobic."""
    if a.family not in FAMILIES:
        return 0.0, 0.0
    if len(a.zones_s) >= 5 and sum(a.zones_s) > 0:
        z = a.zones_s
        return (z[0] + z[1] + z[2]) / 60, (z[3] + z[4]) / 60
    return ((a.moving_s or 0) / 60, 0.0)


def daily_minutes(acts: list[A.Act]) -> tuple[dict[date, float], dict[date, float]]:
    aer: dict[date, float] = {}
    high: dict[date, float] = {}
    for a in acts:
        m_a, m_h = act_minutes(a)
        if m_a:
            aer[a.day] = aer.get(a.day, 0.0) + m_a
        if m_h:
            high[a.day] = high.get(a.day, 0.0) + m_h
    return aer, high


def _exposure(series: dict[date, float], start: date, end: date) -> np.ndarray:
    """Hours-per-week equivalent on each day from `start`, from minutes up to the previous day."""
    w = np.zeros((end - start).days + 1)
    for d, v in series.items():
        if start <= d <= end:
            w[(d - start).days] = v
    r = math.exp(-1 / TAU)
    after = lfilter([1.0], [1.0, -r], w)
    before = np.concatenate([[0.0], after[:-1]])
    return before / TAU * 7 / 60


def fit(c: dict) -> dict:
    out: dict = {"valid": False, "adopted": False, "tau": TAU}
    obs = [(d, v) for d, v in B.weekly_series(c["eff"]) if d <= c["as_of"]]  # a week's midpoint can fall after the last day
    aer, high = daily_minutes(c["acts"])
    out["n"] = len(obs)
    span = (obs[-1][0] - obs[0][0]).days if obs else 0
    if len(obs) < MIN_WEEKS or span < MIN_SPAN_DAYS:
        out["missing"] = f"at least {MIN_WEEKS} weeks of runs with heart rate over {MIN_SPAN_DAYS}+ days (you have {len(obs)} weeks over {span} days)"
        return out
    start = min(min(aer, default=obs[0][0]), obs[0][0])
    end = c["as_of"]
    e_a, e_h = _exposure(aer, start, end), _exposure(high, start, end)
    idx = np.array([(d - start).days for d, _ in obs])
    y = np.array([v for _, v in obs])
    xa, xh = e_a[idx], e_h[idx]
    if int((xh > HIGH_WEEK_HW).sum()) < MIN_HIGH_WEEKS or float(np.std(xh)) == 0 or float(np.std(xa)) == 0:
        out.update(valid=False, missing="more weeks with some zone 4-5 work; the high-intensity channel is too empty to measure")
        return out
    mean_ef = float(y.mean())
    design = np.column_stack([np.ones(len(y)), xa, xh])
    res = R.ols(design, y, lags=4)
    if res is None:
        out.update(valid=False, missing="more varied training: easy and hard minutes move together too closely to tell apart")
        return out
    total = np.column_stack([np.ones(len(y)), xa + xh])
    cv = {
        "channels": R.blocked_cv_rmse(R.lstsq_predict, design, y),
        "total": R.blocked_cv_rmse(R.lstsq_predict, total, y),
        "mean": R.blocked_cv_rmse(R.lstsq_predict, np.ones((len(y), 1)), y),
    }
    adopted = cv["channels"] <= CV_GAIN * cv["total"] and cv["channels"] <= CV_GAIN * cv["mean"]
    pct = lambda v: round(float(v) / mean_ef * 100, 2)  # noqa: E731
    out.update(
        valid=True, adopted=bool(adopted), span_days=span, mean_ef=round(mean_ef, 4), r2=round(res["r2"], 3),
        high_weeks=int((xh > HIGH_WEEK_HW).sum()),
        aerobic={"pct_per_hour": pct(res["coef"][1]), "ci": [pct(res["ci"][1][0]), pct(res["ci"][1][1])], "se_pct": pct(res["se"][1])},
        high={"pct_per_hour": pct(res["coef"][2]), "ci": [pct(res["ci"][2][0]), pct(res["ci"][2][1])], "se_pct": pct(res["se"][2])},
        cv={k: round(v, 5) for k, v in cv.items()},
        gain_vs_total_pct=round((1 - cv["channels"] / cv["total"]) * 100, 1) if cv["total"] > 0 else 0.0,
        _coef={"aer": float(res["coef"][1]), "high": float(res["coef"][2]), "se_aer": float(res["se"][1]), "se_high": float(res["se"][2])},
    )
    if not adopted:
        out["why_not"] = "splitting easy from hard minutes did not predict held-out weeks at least 5 % better than total minutes and the plain average"
    return out


def public(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


# ---- what-if effects ---------------------------------------------------------------------------------


def shifted(a: A.Act, action: str) -> tuple[float, float]:
    """(aerobic, high) minutes of the session after the change."""
    m_a, m_h = act_minutes(a)
    if action == "skip":
        return 0.0, 0.0
    if action == "half":
        return m_a / 2, m_h / 2
    return m_a + m_h, 0.0  # kept easy: the same minutes, none of them in zones 4-5


def minutes_moved(acts: list[A.Act], edits: list[dict]) -> dict:
    """Totals by channel before and after the edits, for plain wording ("160 grey-zone minutes stay aerobic minutes")."""
    by_id = {a.id: a for a in acts}
    before = {"aerobic": 0.0, "high": 0.0}
    after = {"aerobic": 0.0, "high": 0.0}
    z3 = 0.0
    for e in edits:
        a = by_id.get(e["activity_id"])
        if a is None:
            continue
        m_a, m_h = act_minutes(a)
        n_a, n_h = shifted(a, e["action"])
        before["aerobic"] += m_a
        before["high"] += m_h
        after["aerobic"] += n_a
        after["high"] += n_h
        if len(a.zones_s) >= 5:
            z3 += a.zones_s[2] / 60
    return {"before": {k: round(v) for k, v in before.items()}, "after": {k: round(v) for k, v in after.items()}, "zone3_minutes": round(z3)}


def effect(result: dict, acts: list[A.Act], edits: list[dict], until: date) -> dict | None:
    """Predicted change in aerobic efficiency (% of your average) by `until`, with a 95 % interval; None unless the split was adopted."""
    if not result.get("adopted") or "_coef" not in result:
        return None
    by_id = {a.id: a for a in acts}
    d_a = d_h = 0.0
    for e in edits:
        a = by_id.get(e["activity_id"])
        if a is None or a.day > until:
            continue
        m_a, m_h = act_minutes(a)
        n_a, n_h = shifted(a, e["action"])
        decay = math.exp(-(until - a.day).days / TAU)
        d_a += (n_a - m_a) * decay
        d_h += (n_h - m_h) * decay
    k = 1 / TAU * 7 / 60
    d_a, d_h = d_a * k, d_h * k
    co = result["_coef"]
    delta = co["aer"] * d_a + co["high"] * d_h
    half = 1.96 * math.sqrt((co["se_aer"] * d_a) ** 2 + (co["se_high"] * d_h) ** 2)
    pct = lambda v: round(v / result["mean_ef"] * 100, 2)  # noqa: E731
    return {"ef_pct": pct(delta), "ci": [pct(delta - half), pct(delta + half)], "aerobic_hours_per_week": round(d_a, 2), "high_hours_per_week": round(d_h, 2)}
