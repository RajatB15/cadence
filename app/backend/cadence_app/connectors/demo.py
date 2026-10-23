"""Deterministic synthetic data so the UI and analytics can be built before Garmin access is verified."""

from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta

from cadence_app.importer import ActivityRecord, Batch, MetricRecord, WeightRecord

SOURCE_ID = "demo"
SOURCE_NAME = "Demo data"
TIMEZONE = "UTC"
# Simulation always starts here so any window yields identical values for the same day.
ANCHOR = date(2025, 1, 1)

# weekday -> (activity type, name, load range, intensity 0..1)
PLAN = {
    1: ("run", "Interval Session", (110, 150), 0.85),
    2: ("strength", "Strength", (40, 60), 0.5),
    3: ("run", "Easy Run", (60, 90), 0.55),
    5: ("run", "Long Run", (150, 220), 0.7),
    6: ("ride", "Weekend Ride", (90, 140), 0.6),
}


def _rng(day: date, salt: str) -> random.Random:
    return random.Random(f"cadence-demo:{salt}:{day.isoformat()}")


def generate(start: date, end: date) -> Batch:
    """Synthesize data for start..end inclusive."""
    batch = Batch()
    ctl = 45.0
    atl = 45.0
    prev_load = 0.0
    day = ANCHOR
    while day <= end:
        rng = _rng(day, "day")
        load = 0.0
        activities: list[ActivityRecord] = []
        planned = PLAN.get(day.weekday())
        if planned and rng.random() > 0.15:
            kind, name, (lo, hi), intensity = planned
            load = rng.uniform(lo, hi)
            activities.append(_activity(day, kind, name, load, intensity, rng))

        sleep = rng.gauss(7.2, 0.6) + (0.4 if day.weekday() >= 5 else 0.0)
        if day.weekday() == 4 and rng.random() < 0.35:
            sleep -= 1.1
        sleep = min(max(sleep, 4.2), 9.6)

        hrv = 52 + 0.12 * ctl - 0.06 * prev_load + 2.5 * (sleep - 7.2) + rng.gauss(0, 4)
        resting_hr = 55 - 0.06 * ctl + 0.025 * prev_load - 0.8 * (sleep - 7.2) + rng.gauss(0, 1.4)
        stress = 30 + 0.05 * prev_load - 4 * (sleep - 7.2) + (5 if day.weekday() < 5 else 0)
        stress += rng.gauss(0, 6)
        battery = 62 + 6 * (sleep - 7.2) + 0.35 * (hrv - 55) - 0.08 * prev_load + rng.gauss(0, 6)
        sleep_score = 62 + 9 * (sleep - 6.5) + rng.gauss(0, 5)
        steps = rng.gauss(8200, 2200) + sum((a.distance_m or 0) * 1.25 for a in activities if a.activity_type == "run")

        if day >= start:
            values = {
                "hrv": (hrv, "ms"),
                "resting_hr": (resting_hr, "bpm"),
                "sleep_hours": (sleep, "h"),
                "sleep_score": (min(max(sleep_score, 30), 98), "score"),
                "stress": (min(max(stress, 5), 95), "score"),
                "body_battery": (min(max(battery, 5), 100), "score"),
                "steps": (max(steps, 800), "steps"),
                "training_load": (load, "load"),
            }
            for metric, (value, unit) in values.items():
                batch.metrics.append(MetricRecord(day, metric, round(value, 2), unit))
            batch.activities.extend(activities)
            weight = _weight(day, prev_load)
            if weight:
                batch.weights.append(weight)

        atl += (load - atl) / 7
        ctl += (load - ctl) / 42
        prev_load = load
        day += timedelta(days=1)
    return batch


def _activity(
    day: date, kind: str, name: str, load: float, intensity: float, rng: random.Random
) -> ActivityRecord:
    start = datetime.combine(day, time(6, 15)) + timedelta(minutes=rng.randint(0, 70))
    if kind == "run":
        duration = load / (0.9 + intensity) * 60
        pace_s_per_km = 345 - 60 * (intensity - 0.5) + rng.gauss(0, 8)
        distance = duration / pace_s_per_km * 1000
        elevation = rng.uniform(20, 160)
    elif kind == "ride":
        duration = load / 1.4 * 60
        distance = duration * rng.uniform(7.0, 8.2)
        elevation = rng.uniform(150, 600)
    else:
        duration = rng.uniform(35, 55) * 60
        distance = None
        elevation = None
    avg_hr = 112 + 55 * intensity + rng.gauss(0, 4)
    return ActivityRecord(
        source_record_id=f"demo-{day.isoformat()}-{kind}",
        start_time_utc=start,
        timezone=TIMEZONE,
        local_date=day,
        activity_type=kind,
        name=name,
        duration_s=round(duration),
        distance_m=round(distance, 1) if distance else None,
        avg_hr=round(avg_hr),
        max_hr=round(avg_hr + rng.uniform(12, 24)),
        elevation_gain_m=round(elevation) if elevation else None,
        calories=round(duration / 60 * (6 + 7 * intensity)),
        training_load=round(load, 1),
    )


def _weight(day: date, prev_load: float) -> WeightRecord | None:
    rng = _rng(day, "weight")
    if rng.random() < 0.22:
        return None
    t = (day - ANCHOR).days
    true_weight = 81.5 - 0.008 * t + 1.1 * math.sin(2 * math.pi * t / 240)
    measured = true_weight + rng.gauss(0, 0.35) + (0.25 if prev_load > 140 else 0.0)
    body_fat = 22.5 - 0.006 * t + rng.gauss(0, 0.4)
    measured_at = datetime.combine(day, time(1, 30)) + timedelta(minutes=rng.randint(0, 90))
    return WeightRecord(
        source_record_id=f"demo-{day.isoformat()}-weight",
        measured_at_utc=measured_at,
        timezone=TIMEZONE,
        local_date=day,
        weight_kg=round(measured, 2),
        body_fat_pct=round(body_fat, 1),
    )
