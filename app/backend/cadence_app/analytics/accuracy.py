"""Does the planner's load prediction hold up? Scores it against what happened, and corrects a persistent bias.

- Realised plans: each session you planned and then did is compared with the load predicted when you chose it
  (`load_raw`, before any correction, so the check can't feed on itself).
- Backtest: walk-forward over your own history. Every past session is predicted from only the sessions before it,
  given its duration and time in zones, with the load model fitted before the test window starts.
- Error is a ratio (actual / predicted), summarised on the log scale so that 2× too high and 2× too low count equally.
  The 95 % interval for the typical ratio is a t-interval on the log ratios (Altman & Bland, 1983: ratio measures
  are analysed as logs); a bias is only called when that interval excludes 1 and n ≥ MIN_BIAS_N.
- Correction: the geometric-mean ratio shrunk towards 1 by n / (n + SHRINK_N) and capped, applied per sport once that
  sport has MIN_BIAS_N realised sessions (otherwise the all-sport factor). Predictions say when they were corrected.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import median

import numpy as np
from scipy import stats

from cadence_app.analytics import athlete as A
from cadence_app.analytics import planner as PL

MIN_N = 5           # below this nothing is summarised
MIN_BIAS_N = 10     # below this no bias is claimed and nothing is corrected
SHRINK_N = 10
FACTOR_RANGE = (0.7, 1.4)
BACKTEST_MAX = 60
BACKTEST_MIN_HISTORY = 20
POINTS = 60  # scatter points returned per source


def raw_load(predicted: dict) -> float | None:
    v = predicted.get("load_raw", predicted.get("load"))
    return float(v) if isinstance(v, (int, float)) and v > 0 else None


def summarise(pairs: list[dict]) -> dict:
    """pairs: {"predicted", "actual", optional "range": [lo, hi]} → error statistics (None until n ≥ MIN_N)."""
    pairs = [p for p in pairs if p["predicted"] > 0 and p["actual"] > 0]
    n = len(pairs)
    out: dict = {"n": n, "enough": n >= MIN_N}
    if n < MIN_N:
        return out
    ratios = np.array([p["actual"] / p["predicted"] for p in pairs])
    logs = np.log(ratios)
    mean, sd = float(logs.mean()), float(logs.std(ddof=1))
    half = float(stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n))
    errs = [abs(p["actual"] - p["predicted"]) / p["predicted"] * 100 for p in pairs]
    ranged = [p for p in pairs if p.get("range")]
    out.update(
        typical_error_pct=round(median(errs)),
        ratio=round(math.exp(mean), 3),
        ratio_ci=[round(math.exp(mean - half), 3), round(math.exp(mean + half), 3)],
        bias_pct=round((math.exp(mean) - 1) * 100),
        biased=bool(n >= MIN_BIAS_N and (mean - half > 0 or mean + half < 0)),
        within_10_pct=round(sum(e <= 10 for e in errs) / n * 100),
        within_25_pct=round(sum(e <= 25 for e in errs) / n * 100),
        range_coverage_pct=round(sum(p["range"][0] <= p["actual"] <= p["range"][1] for p in ranged) / len(ranged) * 100) if len(ranged) >= MIN_N else None,
        range_n=len(ranged),
    )
    return out


def score_plans(plans: list[dict]) -> dict:
    """Realised plans vs predictions. `plans` are reconciled (status/activity) planned sessions."""
    rows, missed, planned_past = [], 0, 0
    for p in plans:
        if p.get("status") == "missed":
            missed += 1
        if p.get("status") in ("done", "missed"):
            planned_past += 1
        if p.get("status") != "done" or not p.get("activity"):
            continue
        predicted, actual = raw_load(p["predicted"]), (p["activity"] or {}).get("load")
        if predicted is None or not actual or actual <= 0:
            continue
        rows.append({"id": p["id"], "day": p["day"], "sport": p["sport"], "kind": p["kind"], "title": p["title"],
                     "predicted": predicted, "actual": float(actual), "range": p["predicted"].get("load_range"),
                     "error_pct": round((actual - predicted) / predicted * 100), "basis": p["predicted"].get("basis")})
    rows.sort(key=lambda r: r["day"])
    by_sport = {s: summarise([r for r in rows if r["sport"] == s]) for s in sorted({r["sport"] for r in rows})}
    return {
        "overall": summarise(rows),
        "by_sport": {s: v for s, v in by_sport.items() if v["enough"]},
        "recent": [{k: r[k] for k in ("id", "day", "sport", "title", "predicted", "actual", "error_pct")} for r in rows[-8:]][::-1],
        "followed": {"done": len(rows), "missed": missed, "of": planned_past} if planned_past else None,
        "points": [{k: r[k] for k in ("day", "sport", "predicted", "actual")} for r in rows[-POINTS:]],
        "rows": rows,
    }


def calibration(scored: dict) -> dict:
    """{sport: {factor, n, source}} for sports where a bias is established, plus "all". Absent sports are uncorrected."""
    out: dict = {}
    overall = scored["overall"]
    if overall.get("biased"):
        out["all"] = _factor(overall)
    for sport, s in scored["by_sport"].items():
        if s.get("biased"):
            out[sport] = _factor(s)
    return out


def _factor(s: dict) -> dict:
    shrink = s["n"] / (s["n"] + SHRINK_N)
    f = s["ratio"] ** shrink
    return {"factor": round(min(FACTOR_RANGE[1], max(FACTOR_RANGE[0], f)), 3), "n": s["n"], "ratio": s["ratio"], "ratio_ci": s["ratio_ci"]}


def backtest(c: dict, limit: int = BACKTEST_MAX) -> dict:
    """Predict each of your last sessions from the sessions before it (given its duration and zone minutes)."""
    as_of = c["as_of"]
    pool = [a for a in c["acts"] if a.family in ("run", "ride", "swim") and a.load > 0 and (a.moving_s or 0) >= 600 and len(a.zones_s) >= 5
            and a.day > as_of - timedelta(days=365)]
    pool.sort(key=lambda a: (a.day, a.id))
    test = pool[-limit:]
    if len(test) < MIN_N:
        return {"n": len(test), "enough": False, "kind": "backtest"}
    model = PL.load_model(c["acts"], test[0].day - timedelta(days=1))
    pairs = []
    for a in test:
        before = [x for x in c["acts"] if x.day < a.day]
        if sum(1 for x in before if x.family == a.family and x.load > 0) < BACKTEST_MIN_HISTORY:
            continue
        kind = "threshold" if A.is_hard(a) else "long" if (a.moving_s or 0) >= A.LONG_MIN.get(a.family, 10**6) * 60 else "easy"
        minutes = a.moving_s / 60
        option = {"sport": a.family, "kind": kind, "minutes": minutes, "profile": [z / 60 for z in a.zones_s]}
        past = {"as_of": a.day - timedelta(days=1), "acts": before, "labels": {}}
        similar = PL._similar(past, a.family, kind)  # pylint: disable=protected-access
        hist = [s.load for s in similar]
        load, _ = PL.estimate_load(model, option, similar)
        pairs.append({"predicted": load, "actual": a.load, "range": [min(hist), max(hist)] if len(hist) >= 3 else None,
                      "sport": a.family, "day": a.day})
    out = summarise(pairs)
    out.update(kind="backtest", points=[{k: p[k] for k in ("day", "sport", "predicted", "actual")} for p in pairs[-POINTS:]], window=[test[0].day, test[-1].day] if pairs else None,
               by_sport={s: v for s in sorted({p["sport"] for p in pairs}) if (v := summarise([p for p in pairs if p["sport"] == s]))["enough"]})
    return out


def report(c: dict, plans: list[dict]) -> dict:
    scored = score_plans(plans)
    cal = calibration(scored)
    scored_view = {k: v for k, v in scored.items() if k != "rows"}
    return {"plans": scored_view, "backtest": backtest(c), "calibration": cal, "form": form_check(plans, c["pmc_by_day"]),
            "as_of": c["as_of"], "min_bias_n": MIN_BIAS_N}


def form_check(plans: list[dict], pmc_by_day: dict[date, dict]) -> dict | None:
    """Predicted vs actual form the morning after (actual form includes anything unplanned that day)."""
    pairs = []
    for p in plans:
        pred = p["predicted"].get("form_tomorrow")
        nxt = pmc_by_day.get(p["day"] + timedelta(days=1))
        if p.get("status") == "done" and isinstance(pred, (int, float)) and nxt:
            pairs.append(nxt["form"] - pred)
    if len(pairs) < MIN_N:
        return None
    return {"n": len(pairs), "median_error": round(median(pairs), 1), "typical_abs_error": round(median(abs(x) for x in pairs), 1)}
