"""All-day strain: every heartbeat above rest counts, not just recorded workouts.

- Load: Banister TRIMP over Garmin's all-day heart rate (one sample every ~2 minutes), weighted by heart-rate reserve:
  minutes × HRr × 0.64·e^(1.92·HRr), HRr = (HR − resting) / (max − resting), counted from 35% of heart-rate reserve
  so sitting doesn't accumulate strain. Gaps over 5 minutes count as 5.
- Units: TRIMP is scaled to Garmin's training load with the median load/TRIMP ratio across your workouts, so a day's
  strain and a session's load are directly comparable. Strain outside workout windows is reported separately.
- Target: today's band scales your typical day by morning readiness and what the plan calls for today.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from statistics import median

MAX_GAP_MIN = 5.0
# Below 35% of heart-rate reserve (sitting, desk work, pottering) nothing accrues: everyday strain starts around brisk
# walking. Checked on real data: at 25% two-plus hours a day of light movement outweighed training; at 35% everyday
# movement is about a third of the total.
HRR_FLOOR = 0.35
MIN_CALIBRATION = 10
DEFAULT_SCALE = 1.0


def samples(payload: object) -> list[tuple[int, float]]:
    """(UTC epoch ms, bpm) pairs from a Garmin dailyHeartRate payload, using its value descriptors when present."""
    if not isinstance(payload, dict):
        return []
    ti, vi = 0, 1
    for d in payload.get("heartRateValueDescriptors") or []:
        if isinstance(d, dict):
            key, idx = str(d.get("key", "")).lower(), d.get("index")
            if isinstance(idx, int):
                if "timestamp" in key:
                    ti = idx
                elif "heartrate" in key or "value" in key:
                    vi = idx
    out = []
    for row in payload.get("heartRateValues") or []:
        if isinstance(row, list) and len(row) > max(ti, vi):
            t, v = row[ti], row[vi]
            if isinstance(t, (int, float)) and isinstance(v, (int, float)) and v > 0:
                out.append((int(t), float(v)))
    return sorted(out)


def trimp(points: list[tuple[int, float]], rest: float, hr_max: float, windows: list[tuple[int, int]] = ()) -> tuple[float, float]:
    """(total TRIMP, TRIMP inside the workout windows) for one day of samples. Windows are UTC epoch ms ranges."""
    if hr_max <= rest + 20:
        return 0.0, 0.0
    total = inside = 0.0
    for (t0, hr), (t1, _) in zip(points, points[1:] + [(points[-1][0] + 120_000, 0.0)] if points else []):
        minutes = min(MAX_GAP_MIN, max(0.0, (t1 - t0) / 60_000))
        r = (hr - rest) / (hr_max - rest)
        if r <= HRR_FLOOR:
            continue
        r = min(r, 1.0)
        x = minutes * r * 0.64 * math.exp(1.92 * r)
        total += x
        if any(a <= t0 < b for a, b in windows):
            inside += x
    return total, inside


def histogram(points: list[tuple[int, float]], windows: list[tuple[int, int]] = ()) -> tuple[dict[int, float], dict[int, float]]:
    """Minutes at each bpm, (outside workouts, inside workouts). Small and reusable: TRIMP for any resting/max HR
    can be recomputed from it without re-reading the day's samples."""
    outside: dict[int, float] = {}
    inside: dict[int, float] = {}
    for (t0, hr), (t1, _) in zip(points, points[1:] + [(points[-1][0] + 120_000, 0.0)] if points else []):
        minutes = min(MAX_GAP_MIN, max(0.0, (t1 - t0) / 60_000))
        target_ = inside if any(a <= t0 < b for a, b in windows) else outside
        target_[round(hr)] = target_.get(round(hr), 0.0) + minutes
    return outside, inside


def trimp_from_hist(hist: dict[int, float], rest: float, hr_max: float) -> float:
    if hr_max <= rest + 20:
        return 0.0
    total = 0.0
    for hr, minutes in hist.items():
        r = (float(hr) - rest) / (hr_max - rest)
        if r > HRR_FLOOR:
            r = min(r, 1.0)
            total += minutes * r * 0.64 * math.exp(1.92 * r)
    return total


def calibrate(pairs: list[tuple[float, float]]) -> tuple[float, int]:
    """Median Garmin-load / TRIMP across workouts with enough of both; (scale, workouts used)."""
    ratios = [load / t for load, t in pairs if load > 5 and t > 5]
    return (median(ratios), len(ratios)) if len(ratios) >= MIN_CALIBRATION else (DEFAULT_SCALE, len(ratios))


def window(start_utc: datetime, duration_s: float) -> tuple[int, int]:
    start = start_utc.replace(tzinfo=timezone.utc).timestamp() * 1000
    return int(start), int(start + duration_s * 1000)


READINESS_BANDS = ((85, 1.2, 1.5), (70, 0.9, 1.2), (50, 0.6, 0.9), (0, 0.3, 0.6))
KIND_SHIFT = {"key": 1.15, "long": 1.15, "easy": 0.95, "strength": 0.95, "rest": 0.6, "done": 1.0, "unknown": 1.0}


def target(history: dict[date, float], today: date, readiness: float | None, plan_kind: str | None) -> dict | None:
    """Today's strain band: your median day over 4 weeks × a readiness factor × what today's plan calls for."""
    days = [v for d, v in history.items() if today - timedelta(days=28) <= d < today and v > 0]
    if len(days) < 10 or readiness is None:
        return None
    typical = median(days)
    lo, hi = next((lo, hi) for floor, lo, hi in READINESS_BANDS if readiness >= floor)
    shift = KIND_SHIFT.get(plan_kind or "unknown", 1.0)
    return {"typical": round(typical), "low": round(typical * lo * shift), "high": round(typical * hi * shift)}


def status(value: float, band: dict | None) -> str | None:
    if band is None:
        return None
    return "below" if value < band["low"] else "above" if value > band["high"] else "in"
