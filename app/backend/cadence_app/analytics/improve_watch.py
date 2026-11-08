"""Improve, part 3: "worth a look" prompts from your overnight numbers (pure). Never a diagnosis, never a disease name.

Each flag needs a 14+ night baseline (HRV or resting HR over the 60 days ending a week ago, so the days being judged
do not move their own baseline) and is suppressed when logged time off covers the window (a break is not a miss).
Flags carry numbers, the window and citation KEYS; wording is in notes.py.
- overreach_pattern: the rolling 7-day HRV mean below your band (mean - 0.75 SD) on at least 5 of the last 7 days,
  resting HR 7-day mean at least 3 bpm above baseline, and load 7d above 1.2 x your 28-day weekly average or a feel
  score <= 2. The thresholds are Cadence's own; Plews 2013 supports tracking HRV against a personal baseline and Meeusen
  2013 says no single marker is diagnostic. Severity "act" when your own feel score is also low.
- illness_signature: resting HR >= 5 bpm over baseline and HRV >= 20% below for 2+ nights, or a logged run-down day
  (the 5 bpm and 20% cut-offs are Cadence's own heuristic; Mishra 2020 only reports that resting-HR deviations from a
  personal baseline flagged some cases before symptoms in a smartwatch cohort, and says nothing about HRV or these
  numbers; not an individual test). Severity "act".
- sleep_debt: 4+ consecutive nights more than 1 h under your sleep need (Cadence's own rule; no citation).
- detraining: 10+ days without run/ride/swim/walk while the resting HR 7-day mean is >= 2 bpm over baseline
  (Cadence's own thresholds; Mujika & Padilla 2000 only supports that adaptations fade over weeks of inactivity).
Not built: the low-variability "suppressed HRV" prompt from the design (low confidence).
"""

from __future__ import annotations

from datetime import timedelta
from statistics import fmean, stdev

from cadence_app.analytics import athlete as A
from cadence_app.analytics import improve_rules as RL

DAY = timedelta(days=1)
MIN_BASE = 14


def _base(series: A.Series, as_of) -> tuple[float, float, int] | None:
    vals = [v for d, v in series.items() if as_of - 67 * DAY < d <= as_of - 7 * DAY]
    if len(vals) < MIN_BASE:
        return None
    return fmean(vals), stdev(vals), len(vals)


def _mean(series: A.Series, end, days: int, min_n: int = 4) -> float | None:
    v = [x for d, x in series.items() if end - days * DAY < d <= end]
    return fmean(v) if len(v) >= min_n else None


def _flag(fid: str, severity: str, numbers: dict, cites: list[str]) -> dict:
    return {"id": fid, "severity": severity, "numbers": numbers, "citations": cites}


def overreach(c: dict) -> dict | None:
    hrv, rhr, as_of = c["series"].get("hrv", {}), c["series"].get("resting_hr", {}), c["as_of"]
    bh, br = _base(hrv, as_of), _base(rhr, as_of)
    if not bh or not br or RL.covered_by_time_off(c, as_of - 12 * DAY, as_of):
        return None
    low = bh[0] - 0.75 * bh[1]
    below = sum(1 for k in range(7) if (m := _mean(hrv, as_of - k * DAY, 7)) is not None and m < low)
    r7 = _mean(rhr, as_of, 7)
    if below < 5 or r7 is None or r7 - br[0] < 3:
        return None
    load = c["load"]
    l7 = sum(load.get(as_of - k * DAY, 0.0) for k in range(7))
    l28 = sum(load.get(as_of - k * DAY, 0.0) for k in range(28)) / 4
    feels = [e["feel"] for d, e in (c.get("wellbeing") or {}).items() if d > as_of - 4 * DAY and e.get("feel") is not None]
    low_feel = bool(feels) and min(feels) <= 2
    spike = l28 > 0 and l7 > 1.2 * l28
    if not (spike or low_feel):
        return None
    n = {"hrv_days_below_band": below, "hrv_band_low": round(low, 1), "rhr_7d": round(r7, 1), "rhr_baseline": round(br[0], 1), "rhr_delta": round(r7 - br[0], 1),
         "load_ratio": round(l7 / l28, 2) if l28 else None, "low_feel": low_feel, "nights": bh[2], "window_days": 7}
    return _flag("overreach_pattern", "act" if low_feel else "look", n, ["plews2013", "meeusen2013"])


def illness_signature(c: dict) -> dict | None:
    hrv, rhr, as_of = c["series"].get("hrv", {}), c["series"].get("resting_hr", {}), c["as_of"]
    bh, br = _base(hrv, as_of), _base(rhr, as_of)
    wb = c.get("wellbeing") or {}
    run_down = any((wb.get(as_of - k * DAY) or {}).get("illness") for k in range(2))
    if RL.covered_by_time_off(c, as_of - 2 * DAY, as_of):
        return None
    nights = 0
    if bh and br:
        for k in range(2):
            d = as_of - k * DAY
            if d in hrv and d in rhr and rhr[d] - br[0] >= 5 and hrv[d] <= bh[0] * 0.8:
                nights += 1
    if nights < 2 and not run_down:
        return None
    n = {"nights": nights, "run_down_logged": run_down, "rhr_delta": round(rhr[as_of] - br[0], 1) if br and as_of in rhr else None,
         "hrv_pct": round((hrv[as_of] / bh[0] - 1) * 100) if bh and as_of in hrv else None, "baseline_nights": bh[2] if bh else 0, "window_days": 2}
    return _flag("illness_signature", "act", n, ["mishra2020"])


def sleep_debt(c: dict) -> dict | None:
    hours, as_of = c["series"].get("sleep_hours", {}), c["as_of"]
    need = c["sleep_need"]["hours"]
    if sum(1 for d in hours if as_of - 14 * DAY < d <= as_of) < MIN_BASE - 4:
        return None
    run = 0
    while (v := hours.get(as_of - run * DAY)) is not None and v < need - 1.0:
        run += 1
    if run < 4 or RL.covered_by_time_off(c, as_of - (run - 1) * DAY, as_of):
        return None
    return _flag("sleep_debt", "look", {"nights": run, "need_hours": need, "avg_hours": round(fmean(hours[as_of - k * DAY] for k in range(run)), 1), "window_days": run},
                 [])


def detraining(c: dict) -> dict | None:
    as_of, rhr = c["as_of"], c["series"].get("resting_hr", {})
    done = [a.day for a in c["acts"] if a.family in A.ENDURANCE and a.day <= as_of]
    br = _base(rhr, as_of - 3 * DAY)
    r7 = _mean(rhr, as_of, 7)
    if not done or br is None or r7 is None:
        return None
    gap = (as_of - max(done)).days
    if gap < 10 or RL.covered_by_time_off(c, max(done) + DAY, as_of) or r7 - br[0] < 2:
        return None
    return _flag("detraining", "look", {"days_without_aerobic": gap, "rhr_7d": round(r7, 1), "rhr_baseline": round(br[0], 1), "rhr_delta": round(r7 - br[0], 1),
                                       "window_days": gap}, ["mujika2000"])


FLAGS = (overreach, illness_signature, sleep_debt, detraining)


def run(c: dict) -> list[dict]:
    out = [f for fn in FLAGS if (f := fn(c))]
    out.sort(key=lambda f: (f["severity"] != "act", f["id"]))
    return out
