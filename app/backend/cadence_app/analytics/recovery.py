"""Recovery analytics: HRV-guided training, personal recovery cost, sleep need and regularity, early warnings.

Methods:
- HRV-guided training (Plews et al. 2013; Kiviniemi et al. 2007): the 7-day rolling mean of ln RMSSD against a
  60-day normal range of ± 0.5 SD (the smallest worthwhile change). Inside or above it, hard training is supported;
  below it, keep it easy. A rising day-to-day variation (CV) alongside a falling mean signals poor coping.
- Recovery cost: how many days your HRV takes to return to baseline after isolated sessions, by session type.
- Sleep need: the duration beyond which more sleep stops lifting your overnight HRV (broken-stick regression).
- Sleep Regularity Index (Phillips et al. 2017), approximated from sleep onset and wake times: the chance of being
  in the same state (asleep/awake) at the same clock time on consecutive days, scaled -100…100.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import fmean, median, pstdev

import numpy as np
from scipy import stats

from cadence_app.analytics import athlete as A

DAY = timedelta(days=1)
DEFAULT_SLEEP_NEED = 8.0
DEFAULT_RECOVERY_DAYS = {"hard": 2, "long": 2, "easy": 1}
MIN_RECOVERY_SAMPLES = 5


def _window(series: A.Series, start: date, end: date) -> list[float]:
    return [series[d] for d in A.daterange(start, end) if d in series]


# ---- HRV-guided training ----------------------------------------------------------------


def hrv_guided(hrv: A.Series, as_of: date, history_days: int = 90) -> dict | None:
    ln = {d: math.log(v) for d, v in hrv.items() if v and v > 0}

    def state(d: date) -> dict | None:
        week = _window(ln, d - 6 * DAY, d)
        base = _window(ln, d - 67 * DAY, d - 8 * DAY)
        if len(week) < 5 or len(base) < 30:
            return None
        mb, sd = fmean(base), pstdev(base)
        m7 = fmean(week)
        swc = 0.5 * sd
        return {"day": d, "mean7": m7, "low": mb - swc, "high": mb + swc, "base": mb, "sd": sd,
                "cv7": pstdev(week) / m7 * 100 if m7 else 0.0}

    today = state(as_of)
    if today is None:
        return None
    history = [s for d in A.daterange(as_of - timedelta(days=history_days - 1), as_of) if (s := state(d))]
    cvs = [s["cv7"] for s in history[:-7]] or [today["cv7"]]
    cv_base = median(cvs)
    week_ago = next((s for s in history if s["day"] == as_of - 7 * DAY), None)
    status = "below" if today["mean7"] < today["low"] else "above" if today["mean7"] > today["high"] else "normal"
    today_ln = ln.get(as_of)
    today_low = today_ln is not None and today_ln < today["base"] - today["sd"]
    falling = week_ago is not None and today["mean7"] < week_ago["mean7"]
    cv_rising = today["cv7"] > cv_base * 1.25
    if status == "below" and cv_rising:
        coping = "struggling"
    elif status == "below" or (falling and cv_rising):
        coping = "strained"
    else:
        coping = "coping"
    return {
        "status": status,
        "coping": coping,
        "green_light": status != "below" and not today_low,
        "today_low": today_low,
        "mean7_ms": round(math.exp(today["mean7"]), 1),
        "range_ms": [round(math.exp(today["low"]), 1), round(math.exp(today["high"]), 1)],
        "today_ms": round(hrv[as_of], 1) if as_of in hrv else None,
        "cv7": round(today["cv7"], 2),
        "cv_base": round(cv_base, 2),
        "history": [{"day": s["day"], "mean7": round(math.exp(s["mean7"]), 1), "low": round(math.exp(s["low"]), 1),
                     "high": round(math.exp(s["high"]), 1)} for s in history],
    }


# ---- personal recovery cost ----------------------------------------------------------------


def _day_kind(acts: list[A.Act]) -> str | None:
    training = [a for a in acts if A.is_training(a)]
    if not training:
        return None
    if any(A.is_hard(a) for a in training):
        return "hard"
    if any((a.moving_s or 0) >= A.LONG_MIN.get(a.family, 10**6) * 60 for a in training):
        return "long"
    return "easy"


def recovery_profile(hrv: A.Series, acts: list[A.Act], as_of: date) -> dict:
    """Days for next-morning HRV to return to your pre-session level after isolated sessions of each kind."""
    by_day: dict[date, list[A.Act]] = defaultdict(list)
    for a in acts:
        by_day[a.day].append(a)
    kinds = {d: k for d, items in by_day.items() if (k := _day_kind(items))}
    samples: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for d, kind in kinds.items():
        if d < as_of - timedelta(days=365) or d > as_of - 5 * DAY:
            continue
        # Isolated: nothing hard or long in the next 3 days to muddy the response.
        if any(kinds.get(d + k * DAY) in ("hard", "long") for k in (1, 2, 3)):
            continue
        pre = _window(hrv, d - 7 * DAY, d - DAY)
        base = _window(hrv, d - 60 * DAY, d - DAY)
        if len(pre) < 4 or len(base) < A.MIN_BASELINE:
            continue
        sd = pstdev(base) or 1.0
        level = fmean(pre)
        zs = [(hrv[d + k * DAY] - level) / sd if d + k * DAY in hrv else None for k in range(1, 6)]
        if zs[0] is None:
            continue
        back = next((k + 1 for k, z in enumerate(zs) if z is not None and z >= -0.25), 6)
        samples[kind].append((back, zs[0]))
    out: dict = {"kinds": {}}
    for kind in ("hard", "long", "easy"):
        rows = samples.get(kind, [])
        personal = len(rows) >= MIN_RECOVERY_SAMPLES
        out["kinds"][kind] = {
            "days": round(median(r[0] for r in rows), 1) if personal else DEFAULT_RECOVERY_DAYS[kind],
            "dip_sd": round(fmean(r[1] for r in rows), 2) if personal else None,
            "n": len(rows),
            "personal": personal,
        }
    hard = out["kinds"]["hard"]
    # Hard-day spacing: at least one full day between hard sessions, more if your HRV needs it.
    out["hard_spacing_days"] = max(2, min(4, math.ceil(hard["days"])))
    # Live-readiness strain half-life: about three half-lives to be back to baseline, in hours.
    out["half_life_h"] = round(max(6.0, min(24.0, hard["days"] * 24 / 3)), 1) if hard["personal"] else A.STRAIN_HALF_LIFE_H
    return out


# ---- sleep need & regularity ------------------------------------------------------------------


def sleep_need(hours: A.Series, hrv: A.Series) -> dict:
    """Your sleep duration plateau: beyond it, more sleep no longer lifts overnight HRV. 8 h until the data says otherwise."""
    default = {"hours": DEFAULT_SLEEP_NEED, "personal": False, "n": 0,
               "detail": "8 h, the common recommendation for athletes, until your data shows your own plateau."}
    pairs = []
    for d, h in hours.items():
        z = A.baseline_z(hrv, d)
        if z is not None and 4 <= h <= 11:
            pairs.append((h, z[0]))
    default["n"] = len(pairs)
    if len(pairs) < 60:
        return default
    h = np.array([p[0] for p in pairs])
    z = np.array([p[1] for p in pairs])
    best = None
    for k in np.arange(7.0, 9.01, 0.25):
        if (h >= k).sum() < 10 or (h < k).sum() < 10:
            continue
        x = np.minimum(h, k)
        res = stats.linregress(x, z)
        sse = float(np.sum((z - (res.intercept + res.slope * x)) ** 2))
        if best is None or sse < best[1]:
            best = (float(k), sse, res)
    if best is None or best[2].slope <= 0 or best[2].pvalue >= 0.05:
        return default
    k, _, res = best
    return {"hours": k, "personal": True, "n": len(pairs),
            "detail": f"Your overnight HRV rises by {res.slope:.2f} SD per extra hour up to about {k:g} h, then levels off "
                      f"({len(pairs)} nights)."}


def sleep_ok(hours: float, need: float) -> bool:
    """A full night: within 15 minutes of your need."""
    return hours >= need - 0.25


def sleep_regularity(bedtime: A.Series, wake: A.Series, start: date, end: date) -> dict | None:
    """SRI from onset/wake times (noon-to-noon axis), plus sleep-midpoint variability."""
    spans = {}
    for d in A.daterange(start, end):
        if d in bedtime and d in wake:
            onset, off = bedtime[d] + 720, wake[d] + 720
            if 0 <= onset < off <= 1440:
                spans[d] = (onset, off)
    matches = []
    for d, (a0, a1) in spans.items():
        if (prev := spans.get(d - DAY)) is None:
            continue
        b0, b1 = prev
        overlap = max(0.0, min(a1, b1) - max(a0, b0))
        mismatch = (a1 - a0) + (b1 - b0) - 2 * overlap
        matches.append(1 - mismatch / 1440)
    if len(matches) < 7:
        return None
    mids = [(s0 + s1) / 2 - 720 for s0, s1 in spans.values()]
    return {"sri": round(200 * fmean(matches) - 100), "pairs": len(matches), "midpoint_min": round(fmean(mids)),
            "midpoint_sd_min": round(pstdev(mids))}


# ---- early warnings -----------------------------------------------------------------------------


def warning_signals(series: dict[str, A.Series], d: date) -> dict | None:
    """Illness / overreaching flag that needs two or more independent signals to agree (single ones are noisy)."""

    def signals_on(day: date) -> list[dict]:
        out = []
        rhr = series.get("resting_hr", {})
        if (z := A.baseline_z(rhr, day)) and (rhr[day] - z[1] >= 4 or z[0] >= 1.5):
            out.append({"key": "rhr", "label": f"Resting HR {rhr[day]:.0f} bpm (+{rhr[day] - z[1]:.0f})"})
        hrv = series.get("hrv", {})
        if (z := A.baseline_z(hrv, day)) and z[0] <= -1:
            out.append({"key": "hrv", "label": f"HRV {hrv[day]:.0f} ms ({z[0]:.1f} SD)"})
        resp = series.get("respiration", {})
        if (z := A.baseline_z(resp, day)) and resp[day] - z[1] >= 1.0:
            out.append({"key": "respiration", "label": f"Breathing {resp[day]:.1f} brpm (+{resp[day] - z[1]:.1f})"})
        spo2 = series.get("spo2", {})
        base = _window(spo2, day - 60 * DAY, day - DAY)
        if day in spo2 and len(base) >= 7 and spo2[day] <= fmean(base) - 2:
            out.append({"key": "spo2", "label": f"SpO₂ {spo2[day]:.0f}% (usual {fmean(base):.0f}%)"})
        return out

    today = signals_on(d)
    if len(today) < 2:
        return None
    yesterday = {s["key"] for s in signals_on(d - DAY)}
    persisting = len(yesterday & {s["key"] for s in today}) >= 2
    return {"day": d, "signals": today, "persisting": persisting,
            "level": "alert" if len(today) >= 3 or persisting else "warn"}


def underfuelling(weights: list[tuple[date, float]], hrv: A.Series, eff_trend: dict | None, as_of: date) -> dict | None:
    """Possible low energy availability (RED-S pattern): weight falling fast while HRV sags and efficiency stalls."""
    recent = [(d, w) for d, w in weights if (as_of - d).days < 28]
    if len(recent) < 4:
        return None
    x = np.array([(d - as_of).days for d, _ in recent], dtype=float)
    y = np.array([w for _, w in recent])
    if np.ptp(x) < 10:
        return None
    slope = float(np.polyfit(x, y, 1)[0]) * 7
    pct = slope / float(np.mean(y)) * 100
    week = _window(hrv, as_of - 6 * DAY, as_of)
    base = _window(hrv, as_of - 67 * DAY, as_of - 8 * DAY)
    if len(week) < 4 or len(base) < A.MIN_BASELINE:
        return None
    hrv_z = (fmean(week) - fmean(base)) / (pstdev(base) or 1)
    stalled = eff_trend is None or (eff_trend.get("change_pct_90d") or 0) <= 0
    if pct <= -0.5 and hrv_z <= -0.5 and stalled:
        return {"rate_pct_week": round(pct, 2), "rate_kg_week": round(slope, 2), "hrv_z": round(hrv_z, 2)}
    return None


# ---- does readiness predict anything? ---------------------------------------------------------------


def readiness_validation(c: dict, readiness_fn, days: int = 365) -> dict | None:
    """Spearman correlation between morning readiness and that day's run efficiency vs your recent norm.

    Efficiency is the cleanest same-day performance signal we have: if readiness can't predict it, its weights deserve
    a second look. Suggested weights are shown, never applied automatically.
    """
    as_of = c["as_of"]
    eff = [p for p in c["eff"] if p["day"] > as_of - timedelta(days=days)]
    rows = []
    for p in eff:
        prior = [q["ef"] for q in c["eff"] if p["day"] - timedelta(days=60) <= q["day"] < p["day"]]
        if len(prior) < 5:
            continue
        r = readiness_fn(c, p["day"])
        if r is None:
            continue
        rows.append((r["score"], p["ef"] / median(prior) - 1, {k: v["score"] for k, v in r["components"].items()}))
    if len(rows) < 20:
        return {"n": len(rows), "enough": False}
    rho, pval = stats.spearmanr([r[0] for r in rows], [r[1] for r in rows])
    components = {}
    for key in A.READINESS_WEIGHTS:
        pairs = [(r[2][key], r[1]) for r in rows if key in r[2]]
        if len(pairs) >= 20 and len({p[0] for p in pairs}) > 2:
            cr, cp = stats.spearmanr([p[0] for p in pairs], [p[1] for p in pairs])
            components[key] = {"rho": round(float(cr), 2), "p": round(float(cp), 3), "n": len(pairs)}
    suggested = None
    # Only components that clearly track performance earn weight; noise shouldn't reshape the score.
    useful = {k: v["rho"] for k, v in components.items() if v["rho"] > 0 and v["p"] < 0.05}
    if len(rows) >= 40 and useful:
        total = sum(useful.values())
        # Half evidence, half prior: a year of runs is still a small sample for six weights.
        suggested = {k: round(0.5 * A.READINESS_WEIGHTS[k] + 0.5 * useful.get(k, 0) / total, 2) for k in A.READINESS_WEIGHTS}
    return {"n": len(rows), "enough": True, "rho": round(float(rho), 2), "p": round(float(pval), 3),
            "predictive": bool(rho > 0.1 and pval < 0.05), "components": components, "suggested_weights": suggested}


# ---- tonight's sleep need and bedtime -------------------------------------------------------------

LATENCY_MIN = 15  # time to fall asleep; Garmin's sleep start is sleep onset, not lights out
MAX_LOAD_EXTRA_MIN = 45
MAX_REPAY_MIN = 60
MAX_SHIFT_MIN = 60  # body clocks move about an hour a night; a bigger jump just means lying awake


def sleep_tonight(series: dict[str, A.Series], load: A.Series, need: float, day: date) -> dict | None:
    """Tonight's sleep target and bedtime (the night after `day`, ending on the morning of `day` + 1).

    need tonight = your plateau + extra for a heavier-than-usual training day (20 min per multiple of your median
    day's load above 1×, ≤ 45 min) + half your 7-night debt (≤ 60 min). Bedtime counts back from your usual wake
    time on that kind of day (weekday vs weekend, last 4 weeks) and a 15-minute sleep latency.
    """
    hours = series.get("sleep_hours", {})
    wake = series.get("wake_time", {})
    tomorrow = day + DAY
    weekendish = tomorrow.weekday() >= 5
    recent = [wake[d] for d in A.daterange(day - timedelta(days=27), day) if d in wake]
    same_kind = [wake[d] for d in A.daterange(day - timedelta(days=27), day) if d in wake and (d.weekday() >= 5) == weekendish]
    wakes = same_kind if len(same_kind) >= 3 else recent
    if len(wakes) < 3:
        return None
    wake_min = median(wakes)
    positive = [v for d, v in load.items() if v > 0 and day - timedelta(days=90) <= d <= day]
    typical = median(positive) if len(positive) >= 10 else None
    today_load = load.get(day, 0.0)
    extra = max(0.0, min(MAX_LOAD_EXTRA_MIN, 20 * (today_load / typical - 1))) if typical and today_load > 0 else 0.0
    nights = [hours[d] for d in A.daterange(day - 6 * DAY, day) if d in hours]
    debt = sum(max(0.0, need - h) for h in nights)
    repay = min(MAX_REPAY_MIN, debt * 60 / 2)
    ideal = need + (extra + repay) / 60
    lights_out = wake_min - ideal * 60
    beds = [series.get("bedtime", {})[d] for d in A.daterange(day - 13 * DAY, day) if d in series.get("bedtime", {})]
    capped = len(beds) >= 5 and lights_out < fmean(beds) - MAX_SHIFT_MIN
    if capped:
        lights_out = fmean(beds) - MAX_SHIFT_MIN
    tonight = (wake_min - lights_out) / 60
    return {
        "day": day, "need_h": need, "tonight_h": round(tonight, 2), "ideal_h": round(ideal, 2), "capped": capped,
        "extra_load_min": round(extra), "repay_min": round(repay),
        "debt_h": round(debt, 1), "wake_min": round(wake_min), "lights_out_min": round(lights_out),
        "bed_min": round(lights_out - LATENCY_MIN), "weekend": weekendish,
    }


def sleep_target_check(series: dict[str, A.Series], load: A.Series, need: float, end: date, days: int = 180) -> A.Effect | None:
    """Do nights that reach the target precede better next-morning HRV? (Same adjusted comparison as other effects.)"""
    hours, hrv = series.get("sleep_hours", {}), series.get("hrv", {})
    met, missed = set(), set()
    for d in A.daterange(end - timedelta(days=days), end - DAY):
        t = sleep_tonight(series, load, need, d)
        h = hours.get(d + DAY)
        if t is None or h is None:
            continue
        (met if h >= t["tonight_h"] - 0.25 else missed).add(d)
    return A.compare("sleep_target", "Sleep target", "Overnight HRV", "Nights at target", "Nights short of it", met, missed, hrv, 1, "ms", True,
                     {"training load": load})
