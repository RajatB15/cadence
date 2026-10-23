"""Habit insights: how journal behaviours move your recovery.

Each behaviour splits days into "did it" and "didn't" (two or more drinks vs none for alcohol, so one glass doesn't
blur the contrast). The next night's and morning's outcomes are compared with the same machinery as the other
day-group effects: regression adjusted for that day's training load and weekends, standard errors widened for
day-to-day carry-over, and Benjamini–Hochberg control across every habit × outcome test. A habit needs at least
8 days each way before it is tested.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean, median

from cadence_app.analytics import athlete as A

MIN_DAYS = 8
# key, label, unit, higher is better
OUTCOMES = (
    ("hrv", "Overnight HRV", "ms", True),
    ("resting_hr", "Resting HR", "bpm", False),
    ("sleep_score", "Sleep score", "", True),
    ("readiness", "Readiness", "", True),
    ("run_eff", "Next-day run efficiency", "%", True),
)
# Logged "yes" answers to these count as recovery contributors on the day page even before your data proves it.
PRESUMED_COSTLY = {"alcohol", "late_caffeine", "late_meal", "screens_bed", "stress", "travel", "ill"}


def exposure(b: dict, values: dict[date, float]) -> tuple[set[date], set[date], str, str]:
    """(yes days, no days, yes label, no label) for one behaviour."""
    if b["kind"] == "count":
        threshold = 2 if b["key"] == "alcohol" else 1
        unit = b["unit"] or b["label"].lower()
        yes = {d for d, v in values.items() if v >= threshold}
        no = {d for d, v in values.items() if v == 0}
        return yes, no, (f"{threshold}+ {unit}" if threshold > 1 else f"Any {unit}"), f"No {unit}"
    yes = {d for d, v in values.items() if v >= 1}
    no = {d for d, v in values.items() if v == 0}
    return yes, no, b["label"], f"No {b['label'][:1].lower() + b['label'][1:]}"


def run_efficiency_series(eff: list[dict]) -> A.Series:
    """Per day: run efficiency vs the median of your runs in the prior 60 days, in %."""
    out: dict[date, list[float]] = {}
    for p in eff:
        prior = [q["ef"] for q in eff if p["day"] - timedelta(days=60) <= q["day"] < p["day"]]
        if len(prior) >= 5:
            out.setdefault(p["day"], []).append((p["ef"] / median(prior) - 1) * 100)
    return {d: fmean(v) for d, v in out.items()}


def insights(behaviours: list[dict], answers: dict[str, dict[date, float]], outcomes: dict[str, A.Series],
             covariates: dict[str, A.Series]) -> dict:
    effects: list[A.Effect] = []
    progress = []
    for b in behaviours:
        values = answers.get(b["key"], {})
        if not values and not b["active"]:
            continue
        yes, no, yes_label, no_label = exposure(b, values)
        ready = len(yes) >= MIN_DAYS and len(no) >= MIN_DAYS
        progress.append({"key": b["key"], "label": b["label"], "yes": len(yes), "no": len(no), "needed": MIN_DAYS, "ready": ready,
                         "yes_label": yes_label, "no_label": no_label})
        if not ready:
            continue
        for okey, olabel, unit, better in OUTCOMES:
            e = A.compare(f"habit_{b['key']}_{okey}", b["label"], olabel, yes_label, no_label, yes, no, outcomes.get(okey, {}), 1, unit, better,
                          covariates)
            if e is not None:
                e.extra = {"behaviour": b["key"], "outcome": okey}
                effects.append(e)
    A.control_fdr(effects)
    effects.sort(key=lambda e: (not e.significant, -abs(e.effect_size)))
    return {"effects": effects, "progress": progress}


def worse(e: A.Effect) -> bool:
    return e.diff < 0 if e.higher_is_better else e.diff > 0


def strongest(effects: list[A.Effect]) -> dict[str, A.Effect]:
    """The clearest significant effect per behaviour."""
    out: dict[str, A.Effect] = {}
    for e in effects:
        key = e.extra["behaviour"]
        if e.significant and (key not in out or abs(e.effect_size) > abs(out[key].effect_size)):
            out[key] = e
    return out
