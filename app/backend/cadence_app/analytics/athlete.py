"""Athlete analytics on plain data: load model, readiness, intensity, efficiency, durability, sleep, lagged effects.

Methods follow published sports-science heuristics; every output carries enough evidence to be checked:
- Fitness/fatigue/form: Banister impulse-response with 42/7-day exponentially weighted load (as in PMC charts).
- Acute:chronic workload ratio: EWMA 7/28 (Williams et al. 2017); 0.8-1.3 is the commonly cited "sweet spot".
- Training monotony and strain: Foster (1998); monotony > 2 flags low day-to-day variation.
- Intensity distribution: Seiler's ~80/20 polarised model for endurance work.
- Aerobic decoupling (Pa:HR): Friel; < 5% drift over a steady long effort indicates good aerobic durability.
- Aerobic efficiency: speed per beat above resting HR. Running VO2 rises linearly with speed (ACSM) and %VO2 reserve
  tracks %HR reserve (Swain), so speed ∝ HR − resting HR; plain speed/HR would make pace-at-HR wrong away from the
  median heart rate.
- Day-group comparisons: regression with covariates (weekend, training load), standard errors inflated for lag-1
  autocorrelation, and Benjamini–Hochberg false-discovery control across every test run.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import fmean, median, pstdev

import numpy as np
from scipy import stats

from cadence_app.analytics import performance

CTL_DAYS, ATL_DAYS, ACWR_CHRONIC_DAYS = 42, 7, 28
BASELINE_DAYS, MIN_BASELINE = 60, 14
ENDURANCE = {"run", "ride", "swim", "walk"}  # sessions that get an intensity verdict
INTENSITY_FAMILIES = {"run", "ride", "swim"}  # training that counts toward the 80/20 split (walks would dilute it)
NOT_TRAINING = {"walk", "mind"}
LONG_MIN = {"run": 75, "ride": 150, "swim": 60, "walk": 150}
# Body Battery is itself derived from overnight HRV and sleep, so it only breaks ties.
READINESS_WEIGHTS = {"sleep": 0.25, "sleep_history": 0.10, "hrv": 0.25, "rhr": 0.15, "load": 0.20, "battery": 0.05}
DEFAULT_RHR = 60.0


@dataclass(frozen=True)
class Act:
    id: int
    day: date
    start_local: datetime | None
    end_local: datetime | None
    family: str
    type: str
    name: str
    load: float
    distance_m: float | None
    moving_s: float | None
    avg_hr: float | None
    speed_mps: float | None  # grade-adjusted when Garmin provides it
    zones_s: tuple[float, ...] = ()
    vo2max: float | None = None
    aerobic_te: float | None = None
    anaerobic_te: float | None = None
    max_hr: float | None = None


Series = dict[date, float]


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


# ---- session classification ------------------------------------------------------------


def is_training(a: Act) -> bool:
    """Walks and yoga count as recovery, unless a hike carries real training load."""
    return a.family not in NOT_TRAINING or a.load >= 50


def is_hard(a: Act) -> bool:
    """Hard: ≥ 20% of zone time in Z4–5, or a high anaerobic training effect (heart rate lags in sprints and 30/30s)."""
    total = sum(a.zones_s) if len(a.zones_s) >= 5 else 0
    by_hr = total >= 600 and (a.zones_s[3] + a.zones_s[4]) / total >= 0.2
    return by_hr or (a.anaerobic_te or 0) >= 3.0


def intensity(a: Act) -> dict | None:
    if a.family not in ENDURANCE or len(a.zones_s) < 5:
        return None
    z = a.zones_s
    total = sum(z)
    if total < 600:
        return None
    easy, mod, hard = (z[0] + z[1]) / total * 100, z[2] / total * 100, (z[3] + z[4]) / total * 100
    kind = "hard" if hard >= 20 or (a.anaerobic_te or 0) >= 3.0 else "easy" if easy >= 80 else "grey"
    return {"easy_pct": round(easy), "moderate_pct": round(mod), "hard_pct": round(hard), "kind": kind}


# ---- load model -------------------------------------------------------------


def daily_load(acts: list[Act]) -> Series:
    load: Series = defaultdict(float)
    for a in acts:
        load[a.day] += a.load
    return dict(load)


def pmc(load: Series, start: date, end: date) -> list[dict]:
    """Fitness (CTL), fatigue (ATL), form (TSB = yesterday's CTL - ATL) and EWMA ACWR per day."""
    ctl = atl = chronic = 0.0
    out = []
    for d in daterange(start, end):
        form = ctl - atl
        x = load.get(d, 0.0)
        ctl += (x - ctl) / CTL_DAYS
        atl += (x - atl) / ATL_DAYS
        chronic += (x - chronic) / ACWR_CHRONIC_DAYS
        out.append(
            {
                "day": d,
                "load": round(x, 1),
                "fitness": round(ctl, 1),
                "fatigue": round(atl, 1),
                "form": round(form, 1),
                "acwr": round(atl / chronic, 2) if chronic > 5 else None,
            }
        )
    return out


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly(acts: list[Act], load: Series, start: date, end: date) -> list[dict]:
    weeks: dict[date, dict] = {}
    for d in daterange(week_start(start), end):
        w = weeks.setdefault(
            week_start(d),
            {"days": [], "sessions": defaultdict(int), "training": 0, "hard": 0, "run_km": 0.0, "hours": 0.0, "long_run_km": 0.0,
             "long_run_min": 0.0, "easy_s": 0.0, "moderate_s": 0.0, "hard_s": 0.0},
        )
        w["days"].append(load.get(d, 0.0))
    for a in acts:
        w = weeks.get(week_start(a.day))
        if w is None:
            continue
        w["sessions"][a.family] += 1
        w["training"] += is_training(a)
        w["hard"] += is_hard(a)
        w["hours"] += (a.moving_s or 0) / 3600
        if a.family == "run" and a.distance_m:
            w["run_km"] += a.distance_m / 1000
            w["long_run_km"] = max(w["long_run_km"], a.distance_m / 1000)
            w["long_run_min"] = max(w["long_run_min"], (a.moving_s or 0) / 60)
        if a.family in INTENSITY_FAMILIES and len(a.zones_s) >= 5:
            z = a.zones_s
            w["easy_s"] += z[0] + z[1]
            w["moderate_s"] += z[2]
            w["hard_s"] += z[3] + z[4]
    out = []
    for ws, w in sorted(weeks.items()):
        days = w["days"]
        mean = fmean(days)
        sd = pstdev(days)
        monotony = mean / sd if sd > 0 else None
        zone_total = w["easy_s"] + w["moderate_s"] + w["hard_s"]
        out.append(
            {
                "week": ws,
                "load": round(sum(days), 1),
                "sessions": dict(w["sessions"]),
                "total_sessions": w["training"],
                "hard_sessions": w["hard"],
                "strength_sessions": w["sessions"].get("strength", 0),
                "rest_days": sum(1 for x in days if x == 0),
                "run_km": round(w["run_km"], 1),
                "long_run_km": round(w["long_run_km"], 1),
                "long_run_min": round(w["long_run_min"]),
                "hours": round(w["hours"], 1),
                "monotony": round(monotony, 2) if monotony else None,
                "strain": round(sum(days) * monotony) if monotony else None,
                "easy_pct": round(w["easy_s"] / zone_total * 100) if zone_total else None,
                "moderate_pct": round(w["moderate_s"] / zone_total * 100) if zone_total else None,
                "hard_pct": round(w["hard_s"] / zone_total * 100) if zone_total else None,
                "complete": len(days) == 7,
            }
        )
    return out


def intensity_split(acts: list[Act], since: date) -> dict | None:
    """Zone time on runs, rides and swims, overall and per sport, plus the share of sessions that were hard.

    By time, polarised athletes sit near 90/10; by sessions, near 80/20 (Seiler). Both are reported.
    """
    totals = [0.0] * 5
    sport: dict[str, list[float]] = defaultdict(lambda: [0.0] * 5)
    sessions = hard = 0
    for a in acts:
        if a.day >= since and a.family in INTENSITY_FAMILIES and len(a.zones_s) >= 5:
            for i in range(5):
                totals[i] += a.zones_s[i]
                sport[a.family][i] += a.zones_s[i]
            sessions += 1
            hard += is_hard(a)
    t = sum(totals)
    if t < 1800:
        return None

    def pct(z: list[float]) -> dict:
        s = sum(z) or 1
        return {"easy_pct": round((z[0] + z[1]) / s * 100), "moderate_pct": round(z[2] / s * 100), "hard_pct": round((z[3] + z[4]) / s * 100),
                "minutes": round(s / 60)}

    return {
        "zones_min": [round(z / 60) for z in totals],
        **pct(totals),
        "by_sport": {f: pct(z) for f, z in sport.items() if sum(z) >= 1800},
        "sessions": sessions,
        "hard_sessions_pct": round(hard / sessions * 100) if sessions else None,
    }


# ---- readiness --------------------------------------------------------------


def baseline_z(series: Series, d: date) -> tuple[float, float, float] | None:
    """(z-score, baseline mean, baseline sd) of the day's value against the prior 60 days."""
    if d not in series:
        return None
    prior = [series[x] for x in daterange(d - timedelta(days=BASELINE_DAYS), d - timedelta(days=1)) if x in series]
    if len(prior) < MIN_BASELINE:
        return None
    mean, sd = fmean(prior), pstdev(prior)
    return ((series[d] - mean) / sd if sd > 0 else 0.0), mean, sd


def readiness(day: date, series: dict[str, Series], pmc_by_day: dict[date, dict], sleep_need: float = 8.0) -> dict | None:
    """Morning readiness 0-100, modelled on Garmin's factors: a typical, well-recovered day scores ~80."""
    def g(metric: str) -> Series:
        return series.get(metric, {})

    parts: dict[str, dict] = {}

    sleep_score, sleep_hours = g("sleep_score"), g("sleep_hours")
    if day in sleep_score:
        parts["sleep"] = {"score": clamp(sleep_score[day]), "value": round(sleep_score[day]), "hours": sleep_hours.get(day)}
    elif day in sleep_hours:
        parts["sleep"] = {"score": clamp(100 - max(0, sleep_need - sleep_hours[day]) * 25), "value": None, "hours": sleep_hours[day]}

    nights = [sleep_hours[d] for d in daterange(day - timedelta(days=2), day) if d in sleep_hours]
    if len(nights) >= 2:
        avg = fmean(nights)
        parts["sleep_history"] = {"score": clamp(100 - max(0, sleep_need - avg) * 25), "value": round(avg, 1), "need": sleep_need}

    hrv, low, high = g("hrv"), g("hrv_balanced_low"), g("hrv_balanced_high")
    if day in hrv:
        v = hrv[day]
        yesterday = day - timedelta(days=1)
        lo, hi = low.get(day, low.get(yesterday)), high.get(day, high.get(yesterday))
        if lo and hi and hi > lo:
            # Inside Garmin's personal balanced range is normal; each 10% below its floor costs 25 points.
            score = 75 + 20 * (v - lo) / (hi - lo) if lo <= v <= hi else 85 if v > hi else 75 - (lo - v) / (0.1 * lo) * 25
            parts["hrv"] = {"score": clamp(score), "value": round(v), "baseline": None, "range": [round(lo), round(hi)]}
        elif (z := baseline_z(hrv, day)) is not None:
            parts["hrv"] = {"score": clamp(80 + (10 if z[0] >= 0 else 25) * z[0]), "value": round(v), "baseline": round(z[1])}

    rhr = g("resting_hr")
    if (z := baseline_z(rhr, day)) is not None:
        delta = rhr[day] - z[1]
        # Absolute bpm, not z: a very stable resting HR would otherwise turn 1 bpm into a big swing.
        parts["rhr"] = {"score": clamp(85 - 8 * delta if delta > 0 else 85 + 4 * -delta), "value": round(rhr[day]),
                        "baseline": round(z[1], 1), "delta": round(delta, 1)}

    p = pmc_by_day.get(day)
    if p and p["fitness"] > 5:
        acwr = p["acwr"] or 1.0
        acwr_score = 90 if acwr <= 1 else 90 - (acwr - 1) * 100 if acwr <= 1.3 else 60 - (acwr - 1.3) * 150
        ratio = p["form"] / p["fitness"]
        form_score = 90 if ratio >= 0 else 90 + 100 * ratio
        parts["load"] = {"score": clamp((acwr_score + form_score) / 2), "value": p["form"], "acwr": p["acwr"], "fitness": p["fitness"]}

    battery = g("body_battery")
    if day in battery:
        parts["battery"] = {"score": clamp(battery[day]), "value": round(battery[day])}

    if "hrv" not in parts and "rhr" not in parts and "sleep" not in parts:
        return None
    if len(parts) < 3:
        return None
    weight = sum(READINESS_WEIGHTS[k] for k in parts)
    score = sum(READINESS_WEIGHTS[k] * v["score"] for k, v in parts.items()) / weight
    for k, v in parts.items():
        v["score"] = round(v["score"])
        v["weight"] = round(READINESS_WEIGHTS[k] / weight, 2)
    return {"day": day, "score": round(score), "label": readiness_label(score), "components": parts}


STRAIN_HALF_LIFE_H = 7.0


def live_readiness(
    morning: dict, battery_now: float | None, sessions: list[Act], fitness: float, now: datetime, half_life_h: float = STRAIN_HALF_LIFE_H,
) -> dict:
    """Readiness through the day: the morning score adjusted for Body Battery drain and training strain that recovers over hours."""
    parts = {k: dict(v) for k, v in morning["components"].items()}
    changes = []
    if battery_now is not None and "battery" in parts:
        peak = parts["battery"]["value"]
        # Half-weight on the drain: some evening decline is normal, not lost readiness.
        new = clamp(peak - 0.5 * max(0.0, peak - battery_now))
        changes.append({"label": f"Body Battery {peak:.0f} → {battery_now:.0f}", "delta": round(parts["battery"]["weight"] * (new - parts["battery"]["score"]), 1)})
        parts["battery"].update(score=round(new), now=battery_now, peak=peak)
    if "load" in parts:
        total = 0.0
        for a in sessions:
            if a.end_local is None or a.end_local > now or a.load <= 0:
                continue
            hours = (now - a.end_local).total_seconds() / 3600
            cost = min(35.0, a.load / max(fitness, 20.0) * 15) * 0.5 ** (hours / half_life_h)
            total += cost
            changes.append({"label": f"{a.name} · {hours:.0f} h ago", "delta": round(-parts["load"]["weight"] * cost, 1)})
        if total:
            parts["load"].update(score=round(clamp(parts["load"]["score"] - total)), strain=round(total, 1))
    score = sum(v["weight"] * v["score"] for v in parts.values())
    return {**morning, "score": round(score), "label": readiness_label(score), "components": parts,
            "morning_score": morning["score"], "changes": [c for c in changes if abs(c["delta"]) >= 0.5], "live": True}


def readiness_label(score: float) -> str:
    if score >= 90:
        return "primed"
    if score >= 70:
        return "ready"
    if score >= 50:
        return "hold back"
    return "recover"


# ---- aerobic efficiency & durability -----------------------------------------


def resting_hr_on(rhr: Series, d: date, fallback: float) -> float:
    near = [rhr[x] for x in daterange(d - timedelta(days=7), d) if x in rhr]
    return median(near) if near else fallback


def efficiency(acts: list[Act], rhr: Series | None = None) -> list[dict]:
    """Efficiency (metres per minute per beat above resting HR) for runs that weren't hard sessions.

    Interval sessions are left out: their average HR mixes reps and recoveries, so speed/HR is not comparable.
    """
    rhr = rhr or {}
    fallback = median(rhr.values()) if rhr else DEFAULT_RHR
    out = []
    for a in acts:
        if a.family != "run" or not a.avg_hr or a.avg_hr < 100 or not a.speed_mps or is_hard(a):
            continue
        if (a.distance_m or 0) < 3000 or (a.moving_s or 0) < 15 * 60:
            continue
        rest = resting_hr_on(rhr, a.day, fallback)
        if a.avg_hr - rest < 20:
            continue
        ef = a.speed_mps * 60 / (a.avg_hr - rest)
        out.append({"id": a.id, "day": a.day, "ef": round(ef, 4), "hr": round(a.avg_hr), "rhr": round(rest, 1),
                    "speed": round(a.speed_mps, 3), "name": a.name})
    return out


def pace_at_hr(ef: float, hr: float, rhr: float) -> float | None:
    """Pace (s/km) at a heart rate for a given efficiency."""
    return 1000 / (ef * (hr - rhr)) * 60 if ef > 0 and hr > rhr else None


def efficiency_trend(points: list[dict], ref_hr: float, end: date) -> dict | None:
    if len(points) < 8:
        return None
    rhr = median(p["rhr"] for p in points[-30:])
    x = np.array([(p["day"] - end).days for p in points], dtype=float)
    y = np.array([p["ef"] for p in points])
    slope, intercept, lo, hi = stats.theilslopes(y, x)
    now = intercept
    before = intercept + slope * -90
    monthly: dict[str, list[float]] = defaultdict(list)
    for p in points:
        monthly[p["day"].strftime("%Y-%m")].append(p["ef"])

    def pace(ef: float) -> float:
        return pace_at_hr(ef, ref_hr, rhr) or 0.0

    return {
        "ref_hr": ref_hr,
        "rhr": round(rhr, 1),
        "change_pct_90d": round((now - before) / before * 100, 1) if before > 0 else None,
        "ci_pct_90d": [round(lo * 90 / before * 100, 1), round(hi * 90 / before * 100, 1)] if before > 0 else None,
        "significant": bool(lo > 0 or hi < 0),
        "pace_now_s": round(pace(now)),
        "pace_90d_ago_s": round(pace(before)) if before > 0 else None,
        "monthly": [{"month": m, "ef": round(median(v), 4), "n": len(v), "pace_s": round(pace(median(v)))} for m, v in sorted(monthly.items())],
        "n": len(points),
    }


decoupling = performance.decoupling
pacing = performance.pacing


# ---- sleep ----------------------------------------------------------------------


def sleep_pattern(bedtime: Series, wake: Series, hours: Series, since: date, need: float = 8.0) -> dict | None:
    beds = [v for d, v in bedtime.items() if d >= since]
    wakes = [v for d, v in wake.items() if d >= since]
    durs = [v for d, v in hours.items() if d >= since]
    if len(durs) < 7:
        return None
    return {
        "nights": len(durs),
        "avg_hours": round(fmean(durs), 2),
        "need_hours": need,
        "nights_short": sum(1 for h in durs if h < need - 0.25),
        "debt_hours": round(sum(max(0, need - h) for h in durs[-7:]), 1),
        "avg_bedtime_min": round(fmean(beds)) if beds else None,
        "bedtime_sd_min": round(pstdev(beds)) if len(beds) > 2 else None,
        "avg_wake_min": round(fmean(wakes)) if wakes else None,
        "wake_sd_min": round(pstdev(wakes)) if len(wakes) > 2 else None,
    }


# ---- lagged effects -------------------------------------------------------------


@dataclass
class Effect:
    id: str
    cause: str
    outcome: str
    exposed: str
    reference: str
    lag_days: int
    unit: str
    higher_is_better: bool
    exposed_mean: float = 0
    reference_mean: float = 0
    diff: float = 0
    pct: float = 0
    n_exposed: int = 0
    n_reference: int = 0
    p_value: float = 1
    effect_size: float = 0
    significant: bool = False
    q_value: float = 1
    adjusted_for: list[str] = field(default_factory=list)
    n_effective: float = 0
    extra: dict = field(default_factory=dict)


def compare(
    eid: str, cause: str, outcome: str, exposed_label: str, reference_label: str,
    exposed_days: set[date], reference_days: set[date], series: Series, lag: int, unit: str, higher_is_better: bool,
    covariates: dict[str, Series] | None = None,
) -> Effect | None:
    """Outcome difference between two day groups, adjusted for covariates measured on the exposure day.

    `diff` is the adjusted difference (regression coefficient); the group means are raw. Significance is decided
    across the whole family of tests by `control_fdr`.
    """
    covariates = covariates or {}
    rows = []
    for d in sorted(exposed_days | reference_days):
        y = series.get(d + timedelta(days=lag))
        if y is None or (d in exposed_days and d in reference_days):
            continue
        covs = [covariates[k].get(d, 0.0) for k in covariates]
        rows.append((d, 1.0 if d in exposed_days else 0.0, y, covs))
    a = [r[2] for r in rows if r[1] == 1.0]
    b = [r[2] for r in rows if r[1] == 0.0]
    if len(a) < 8 or len(b) < 8:
        return None
    y = np.array([r[2] for r in rows])
    X = np.array([[1.0, r[1], *r[3]] for r in rows])
    keep = [0, 1] + [i + 2 for i in range(len(covariates)) if np.ptp(X[:, i + 2]) > 0]
    X = X[:, keep]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    sigma2 = float(resid @ resid) / max(n - k, 1)
    cov = sigma2 * np.linalg.pinv(X.T @ X)
    se = math.sqrt(max(cov[1, 1], 1e-12))
    # Lag-1 autocorrelation of residuals on consecutive days shrinks the information in daily data.
    by_day = {r[0]: e for r, e in zip(rows, resid)}
    lagged = [(by_day[d], by_day[d + timedelta(days=1)]) for d in by_day if d + timedelta(days=1) in by_day]
    r1 = 0.0
    if len(lagged) >= 10 and np.std([p[0] for p in lagged]) > 0 and np.std([p[1] for p in lagged]) > 0:
        r1 = float(np.corrcoef([p[0] for p in lagged], [p[1] for p in lagged])[0, 1])
        r1 = 0.0 if math.isnan(r1) else max(0.0, min(0.8, r1))
    inflate = math.sqrt((1 + r1) / (1 - r1))
    n_eff = n * (1 - r1) / (1 + r1)
    t = float(beta[1]) / (se * inflate)
    p = float(2 * stats.t.sf(abs(t), max(n_eff - k, 3)))
    pooled = math.sqrt((np.var(a, ddof=1) + np.var(b, ddof=1)) / 2) or 1
    ma, mb = fmean(a), fmean(b)
    diff = float(beta[1])
    return Effect(
        eid, cause, outcome, exposed_label, reference_label, lag, unit, higher_is_better,
        round(ma, 2), round(mb, 2), round(diff, 2), round(diff / mb * 100, 1) if mb else 0,
        len(a), len(b), p, round(diff / pooled, 2), p < 0.05, p,
        [name for i, name in enumerate(covariates) if i + 2 in keep], round(n_eff, 1),
    )


def control_fdr(effects: list[Effect], q: float = 0.05) -> list[Effect]:
    """Benjamini–Hochberg: with a dozen tests, some p < 0.05 would appear by chance alone."""
    ranked = sorted(effects, key=lambda e: e.p_value)
    m = len(ranked)
    running = 1.0
    for i in range(m - 1, -1, -1):
        running = min(running, ranked[i].p_value * m / (i + 1))
        ranked[i].q_value = round(running, 4)
        ranked[i].significant = running < q
    return effects


def quantile(values: list[float], q: float) -> float:
    return float(np.quantile(values, q))
