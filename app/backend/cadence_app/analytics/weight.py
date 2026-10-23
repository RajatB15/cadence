"""Weight trend: causal local-level Kalman filter with cautious goal projection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

# Day-to-day true-weight drift and scale/hydration noise, both in kg^2.
PROCESS_VAR_PER_DAY = 0.01
MEASUREMENT_VAR = 0.16
RATE_WINDOW_DAYS = 28
MIN_RATE_POINTS = 8
MAX_PROJECTION_DAYS = 730


@dataclass(frozen=True)
class TrendPoint:
    day: date
    weight_kg: float
    trend_kg: float
    band_kg: float


@dataclass(frozen=True)
class Projection:
    goal_kg: float
    status: str  # reached | on_track | off_track | flat | insufficient_data | too_far
    expected: date | None = None
    earliest: date | None = None
    latest: date | None = None


@dataclass(frozen=True)
class WeightSummary:
    points: list[TrendPoint]
    latest_trend_kg: float | None
    rate_kg_per_week: float | None
    rate_se_kg_per_week: float | None
    projection: Projection | None


def smooth(readings: list[tuple[date, float]]) -> list[TrendPoint]:
    """Readings must be sorted by day; one value per day (caller averages duplicates)."""
    points: list[TrendPoint] = []
    level: float | None = None
    variance = 0.0
    prev_day: date | None = None
    for day, weight in readings:
        if level is None:
            level, variance = weight, MEASUREMENT_VAR
        else:
            variance += PROCESS_VAR_PER_DAY * (day - prev_day).days
            gain = variance / (variance + MEASUREMENT_VAR)
            level += gain * (weight - level)
            variance *= 1 - gain
        prev_day = day
        points.append(TrendPoint(day, weight, round(level, 3), round(1.96 * math.sqrt(variance), 3)))
    return points


def rate_per_day(readings: list[tuple[date, float]], as_of: date) -> tuple[float, float] | None:
    """Least-squares slope and standard error of raw readings in the trailing window."""
    window = [(d, w) for d, w in readings if (as_of - d).days < RATE_WINDOW_DAYS]
    if len(window) < MIN_RATE_POINTS:
        return None
    xs = [(d - as_of).days for d, _ in window]
    ys = [w for _, w in window]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    residual = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(residual / (n - 2) / sxx)
    return slope, se


def project(current: float, goal: float, slope: float, se: float, today: date) -> Projection:
    gap = goal - current
    if abs(gap) < 0.1:
        return Projection(goal, "reached")
    # Treat statistically indistinguishable-from-zero trends as flat.
    if abs(slope) < 2 * se or abs(slope) < 0.002:
        return Projection(goal, "flat")
    if (gap > 0) != (slope > 0):
        return Projection(goal, "off_track")

    def at(rate: float) -> date | None:
        if (gap > 0) != (rate > 0) or rate == 0:
            return None
        days = gap / rate
        return today + timedelta(days=math.ceil(days)) if days <= MAX_PROJECTION_DAYS else None

    expected = at(slope)
    if expected is None:
        return Projection(goal, "too_far")
    fast = slope + math.copysign(se, slope)
    slow = slope - math.copysign(se, slope)
    return Projection(goal, "on_track", expected, at(fast), at(slow))


def summarize(readings: list[tuple[date, float]], today: date, goal: float | None) -> WeightSummary:
    points = smooth(readings)
    if not points:
        return WeightSummary([], None, None, None, None)
    latest = points[-1].trend_kg
    rate = rate_per_day(readings, readings[-1][0])
    projection = None
    if goal is not None:
        projection = (
            Projection(goal, "insufficient_data")
            if rate is None
            else project(latest, goal, rate[0], rate[1], today)
        )
    return WeightSummary(
        points,
        latest,
        round(rate[0] * 7, 3) if rate else None,
        round(rate[1] * 7, 3) if rate else None,
        projection,
    )
