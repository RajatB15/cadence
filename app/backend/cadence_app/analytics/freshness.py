"""Does starting fresh actually make you run better? Measured on your own sessions, not assumed.

The what-if replay can show that an easier day leaves you fresher, but fresher only matters if it improves the sessions
that follow. Two outcomes, each regressed on the form (fitness minus fatigue) on the morning of the session:
- hard-session quality: the best 5-minute grade-adjusted speed of each hard run as a share of your best 5-minute speed in the
  previous 90 days. Controlled for fitness (CTL) so that being fitter doesn't masquerade as being fresher;
- easy-run efficiency: speed per heartbeat above resting HR, controlled for a linear drift over time.
Ordinary least squares with Newey–West standard errors (analytics/regress.py). An effect is only stated when its 95 % interval
excludes zero and the sample is big enough; otherwise the result says it is unproven, which is a legitimate answer.
Observational: sessions after rest days may differ in other ways (weather, motivation), so this is evidence, not proof.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
from scipy import stats

from cadence_app.analytics import athlete as A
from cadence_app.analytics import regress as R

MIN_HARD = 12
MIN_EASY = 24
LOOKBACK_DAYS = 90
MIN_PRIOR = 3
DURATION = "300"


def hard_points(c: dict) -> list[dict]:
    analysed = [(a, c["dec"][a.id]["best"]) for a in c["acts"] if a.family == "run" and a.id in c.get("dec", {}) and c["dec"][a.id].get("best", {}).get(DURATION)]
    out = []
    for a, best in analysed:
        if not A.is_hard(a):
            continue
        prior = [b[DURATION] for x, b in analysed if a.day - timedelta(days=LOOKBACK_DAYS) <= x.day < a.day]
        p = c["pmc_by_day"].get(a.day)
        if len(prior) < MIN_PRIOR or not p or p["fitness"] <= 5:
            continue
        out.append({"id": a.id, "day": a.day, "y": best[DURATION] / max(prior), "form": p["form"], "ctl": p["fitness"]})
    return sorted(out, key=lambda r: r["day"])


def _split(rows: list[dict]) -> dict | None:
    forms = [r["form"] for r in rows]
    mid = float(np.median(forms))
    fresh = [r["y"] for r in rows if r["form"] > mid]
    tired = [r["y"] for r in rows if r["form"] <= mid]
    if len(fresh) < 4 or len(tired) < 4:
        return None
    diff = float(np.mean(fresh) - np.mean(tired))
    se = float(np.sqrt(np.var(fresh, ddof=1) / len(fresh) + np.var(tired, ddof=1) / len(tired)))
    crit = float(stats.t.ppf(0.975, min(len(fresh), len(tired)) - 1))
    return {"cut": round(mid, 1), "fresh_n": len(fresh), "tired_n": len(tired), "diff_pct": round(diff * 100, 1),
            "ci_pct": [round((diff - crit * se) * 100, 1), round((diff + crit * se) * 100, 1)]}


def hard(c: dict) -> dict:
    rows = hard_points(c)
    out: dict = {"n": len(rows), "enough": len(rows) >= MIN_HARD, "min": MIN_HARD}
    if not out["enough"]:
        return out
    x = np.column_stack([np.ones(len(rows)), [r["form"] for r in rows], [r["ctl"] for r in rows]])
    res = R.ols(x, np.array([r["y"] for r in rows]), lags=2)
    if res is None:
        return {**out, "enough": False, "why": "form and fitness moved together too closely to separate"}
    lo, hi = (float(v) * 100 for v in res["ci"][1])
    per_point = float(res["coef"][1]) * 100
    spread = float(np.std([r["form"] for r in rows]))
    out.update(
        per_point_pct=round(per_point, 3), ci_per_point_pct=[round(lo, 3), round(hi, 3)], per10_pct=round(per_point * 10, 1),
        ci_per10_pct=[round(lo * 10, 1), round(hi * 10, 1)], significant=bool(lo > 0 or hi < 0), helpful=bool(lo > 0),
        form_sd=round(spread, 1), r2=round(res["r2"], 3), split=_split(rows),
        points=[{"day": r["day"], "form": round(r["form"], 1), "quality_pct": round(r["y"] * 100, 1)} for r in rows],
    )
    return out


def easy(c: dict) -> dict:
    eff = [p for p in c["eff"] if c["pmc_by_day"].get(p["day"])]
    out: dict = {"n": len(eff), "enough": len(eff) >= MIN_EASY, "min": MIN_EASY}
    if not out["enough"]:
        return out
    t0 = eff[0]["day"]
    x = np.column_stack([np.ones(len(eff)), [c["pmc_by_day"][p["day"]]["form"] for p in eff], [(p["day"] - t0).days / 30 for p in eff]])
    y = np.array([p["ef"] for p in eff])
    res = R.ols(x, y, lags=4)
    if res is None:
        return {**out, "enough": False}
    mean = float(y.mean())
    lo, hi = (float(v) / mean * 100 for v in res["ci"][1])
    out.update(per10_pct=round(float(res["coef"][1]) / mean * 1000, 2), ci_per10_pct=[round(lo * 10, 2), round(hi * 10, 2)],
               significant=bool(lo > 0 or hi < 0), helpful=bool(lo > 0), r2=round(res["r2"], 3))
    return out


def fit(c: dict) -> dict:
    return {"hard": hard(c), "easy": easy(c)}


def payoff(result: dict, form_delta: float) -> dict | None:
    """What `form_delta` extra form points would be worth on a hard session, if freshness has been shown to help."""
    h = result.get("hard") or {}
    if not h.get("helpful") or form_delta < 0.5:
        return None
    lo, hi = h["ci_per_point_pct"]
    return {"gain_pct": round(h["per_point_pct"] * form_delta, 1), "ci_pct": [round(lo * form_delta, 1), round(hi * form_delta, 1)]}
