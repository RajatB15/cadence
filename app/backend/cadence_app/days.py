"""Everything known about one calendar day: normalized metrics with personal context, plus raw vault rows."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date, timedelta
from statistics import fmean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.garmin import vault
from cadence_app.models import DailyMetric, RawResponse

# Range datasets: where each day's row lives inside a stored window response.
ROW_LOCATORS: dict[str, tuple[str | None, str]] = {
    "daily_summaries": ("data", "calendarDate"),
    "sleep": (None, "calendarDate"),
    "hrv": ("hrvSummaries", "calendarDate"),
    "body_battery": (None, "date"),
    "wellness_activities": (None, "calendarDate"),
    "weight": ("dailyWeightSummaries", "summaryDate"),
}
MULTI_ROW = {"wellness_activities"}
PER_DAY = ("hrv_intraday", "hr_intraday", "spo2", "food_logs", "fitness_age")
# Which per-day datasets are worth fetching on demand, keyed by the metric proving the day has data.
ON_DEMAND = {"hrv_intraday": "hrv", "hr_intraday": "resting_hr", "spo2": "spo2"}


def _rows(payload: Any, container: str | None) -> list:
    rows = payload.get(container) if container and isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def raw_rows(session: Session, day: date) -> dict[str, Any]:
    out: dict[str, Any] = {}
    key = day.isoformat()
    for dataset, (container, field) in ROW_LOCATORS.items():
        responses = session.scalars(
            select(RawResponse)
            .where(
                RawResponse.source_id == vault.SOURCE_ID,
                RawResponse.dataset == dataset,
                RawResponse.status_code == 200,
                RawResponse.window_start <= day,
                RawResponse.window_end >= day,
            )
            .order_by(RawResponse.fetched_at.desc())
        ).all()
        for raw in responses:
            matches = [
                r for r in _rows(vault.decode(raw.body), container)
                if isinstance(r, dict) and str(r.get(field, ""))[:10] == key
            ]
            if matches:
                out[dataset] = matches if dataset in MULTI_ROW else matches[0]
                break
    for dataset in PER_DAY:
        raw, payload = vault.load(session, f"{dataset}:{key}")
        if raw is not None and raw.status_code == 200 and payload not in (None, {}, []):
            out[dataset] = payload
    return out


def metric_context(session: Session, source_id: str, day: date) -> tuple[dict[str, float], dict[str, dict]]:
    rows = session.execute(
        select(DailyMetric.metric, DailyMetric.day, DailyMetric.value, DailyMetric.unit)
        .where(DailyMetric.source_id == source_id)
        .order_by(DailyMetric.metric, DailyMetric.day)
    ).all()
    series: dict[str, list[tuple[date, float]]] = {}
    units: dict[str, str] = {}
    for metric, d, v, unit in rows:
        series.setdefault(metric, []).append((d, v))
        units[metric] = unit

    today_values: dict[str, float] = {}
    context: dict[str, dict] = {}
    for metric, points in series.items():
        days = [d for d, _ in points]
        values = [v for _, v in points]
        i = bisect_left(days, day)
        if i >= len(days) or days[i] != day:
            continue
        value = values[i]
        today_values[metric] = value

        def window(lo_days: int, hi_days: int) -> list[float]:
            lo = bisect_left(days, day - timedelta(days=hi_days))
            hi = bisect_right(days, day - timedelta(days=lo_days))
            return values[lo:hi]

        prior7 = window(1, 7)
        last7 = window(0, 6)
        last30 = window(0, 29)
        base60 = window(7, 66)
        ordered = sorted(values)
        below = bisect_left(ordered, value)
        context[metric] = {
            "value": value,
            "unit": units[metric],
            "avg_7d": round(fmean(last7), 3) if last7 else None,
            "prev_7d": round(fmean(prior7), 3) if prior7 else None,
            "avg_30d": round(fmean(last30), 3) if last30 else None,
            "baseline_60d": round(fmean(base60), 3) if len(base60) >= 14 else None,
            "all_min": ordered[0],
            "all_max": ordered[-1],
            "all_avg": round(fmean(values), 3),
            "percentile": round(below / max(1, len(values) - 1) * 100) if len(values) > 1 else None,
            "rank_high": len(values) - bisect_right(ordered, value) + 1,
            "count": len(values),
            "first_day": days[0],
        }
    return today_values, context


def neighbours(session: Session, source_id: str, day: date) -> tuple[date | None, date | None]:
    prev_day = session.scalar(
        select(DailyMetric.day)
        .where(DailyMetric.source_id == source_id, DailyMetric.day < day)
        .order_by(DailyMetric.day.desc())
        .limit(1)
    )
    next_day = session.scalar(
        select(DailyMetric.day)
        .where(DailyMetric.source_id == source_id, DailyMetric.day > day)
        .order_by(DailyMetric.day)
        .limit(1)
    )
    return prev_day, next_day
