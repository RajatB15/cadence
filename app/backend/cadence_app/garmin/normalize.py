"""Pure payload -> record mapping. Reads only vault payloads, so it is replayable offline."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from cadence_app.importer import ActivityRecord, Batch, MetricRecord, WeightRecord

_COMPACT_OFFSET = re.compile(r"(T.*[+-]\d{2})(\d{2})$")


def num(value: Any, *, positive: bool = False) -> float | None:
    # Garmin uses negative sentinels (e.g. -1, -2) for "not measured".
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or (positive and value == 0):
        return None
    return float(value)


def dig(obj: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def parse_day(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_instant(value: Any, *, wall_clock: bool = False) -> datetime | None:
    """Naive UTC datetime from epoch ms or ISO-like text; wall_clock keeps local time as written."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime(1970, 1, 1) + timedelta(milliseconds=value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = _COMPACT_OFFSET.sub(r"\1:\2", text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None) if wall_clock else parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def utc_offset_label(local: datetime | None, utc: datetime | None) -> str:
    if local is None or utc is None:
        return "unknown"
    minutes = round((local - utc).total_seconds() / 60 / 15) * 15
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def item_count(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("data", "hrvSummaries", "dailyWeightSummaries", "userGoals"):
            if isinstance(payload.get(key), list):
                return len(payload[key])
        return 1 if payload else 0
    return 1


def meaningful(value: Any) -> bool:
    """True if any leaf carries a real value, so all-null placeholder payloads count as empty."""
    if isinstance(value, dict):
        return any(meaningful(v) for k, v in value.items() if k not in _IDENTITY_KEYS)
    if isinstance(value, list):
        return any(meaningful(v) for v in value)
    return value not in (None, "", False)


_IDENTITY_KEYS = {"userProfilePk", "userProfilePK", "userProfileId", "calendarDate", "uuid", "displayName"}


def has_normalizer(dataset: str) -> bool:
    return dataset in _HANDLERS


def normalize(dataset: str, payload: Any, day: date | None = None) -> Batch:
    handler = _HANDLERS.get(dataset)
    return handler(payload, day) if handler else Batch()


def _daily_summaries(payload: Any, _day: date | None) -> Batch:
    batch = Batch()
    rows = payload.get("data") if isinstance(payload, dict) else None
    for row in rows or []:
        day = parse_day(dig(row, "calendarDate"))
        if day is None or row.get("includesWellnessData") is False:
            continue
        moderate = num(dig(row, "intensityMinutes", "moderate"))
        vigorous = num(dig(row, "intensityMinutes", "vigorous"))
        values = {
            "steps": (num(dig(row, "movement", "steps", "value")), "steps"),
            "floors": (num(dig(row, "movement", "floorsAscended", "value")), "floors"),
            "resting_hr": (num(dig(row, "heartRate", "restingValue"), positive=True), "bpm"),
            "stress": (num(dig(row, "stress", "avgLevel")), "score"),
            "body_battery": (num(dig(row, "bodyBattery", "maxValue"), positive=True), "score"),
            "body_battery_low": (num(dig(row, "bodyBattery", "minValue"), positive=True), "score"),
            # Today: the current level; settled days: where the day ended.
            "body_battery_now": (num(dig(row, "bodyBattery", "latestValue"), positive=True), "score"),
            "active_calories": (num(dig(row, "calories", "burnedActive")), "kcal"),
            "total_calories": (num(dig(row, "calories", "burnedTotal"), positive=True), "kcal"),
            "calories_consumed": (num(dig(row, "calories", "consumedValue"), positive=True), "kcal"),
            "intensity_minutes": (
                moderate + vigorous if moderate is not None and vigorous is not None else None,
                "min",
            ),
            "respiration": (num(dig(row, "respiration", "avgValue"), positive=True), "brpm"),
            "spo2": (num(dig(row, "pulseOx", "avgValue"), positive=True), "%"),
            "hydration_ml": (num(dig(row, "hydration", "consumedInFractionalMl"), positive=True), "ml"),
        }
        for metric, (value, unit) in values.items():
            if value is not None:
                batch.metrics.append(MetricRecord(day, metric, round(value, 2), unit))
    return batch


def _hrv(payload: Any, _day: date | None) -> Batch:
    batch = Batch()
    rows = payload.get("hrvSummaries") if isinstance(payload, dict) else None
    for row in rows or []:
        day = parse_day(dig(row, "calendarDate"))
        if day is None:
            continue
        for metric, field in (("hrv", "lastNightAvg"), ("hrv_weekly", "weeklyAvg")):
            value = num(row.get(field), positive=True)
            if value is not None:
                batch.metrics.append(MetricRecord(day, metric, value, "ms"))
        for metric, field in (("hrv_balanced_low", "balancedLow"), ("hrv_balanced_high", "balancedUpper")):
            value = num(dig(row, "baseline", field), positive=True)
            if value is not None:
                batch.metrics.append(MetricRecord(day, metric, value, "ms"))
    return batch


def _sleep(payload: Any, _day: date | None) -> Batch:
    batch = Batch()
    for row in payload if isinstance(payload, list) else []:
        day = parse_day(dig(row, "calendarDate"))
        seconds = num(dig(row, "sleepTimeSeconds"), positive=True)
        if day is None or seconds is None:
            continue
        batch.metrics.append(MetricRecord(day, "sleep_hours", round(seconds / 3600, 3), "h"))
        for metric, field in (("deep_sleep_h", "deepSleepSeconds"), ("rem_sleep_h", "remSleepSeconds")):
            value = num(row.get(field))
            if value is not None:
                batch.metrics.append(MetricRecord(day, metric, round(value / 3600, 3), "h"))
        score = num(dig(row, "sleepScores", "overall", "value"), positive=True)
        if score is not None:
            batch.metrics.append(MetricRecord(day, "sleep_score", score, "score"))
        stress = num(row.get("avgSleepStress"))
        if stress is not None:
            batch.metrics.append(MetricRecord(day, "sleep_stress", round(stress, 1), "score"))
        # Local timestamps are wall-clock encoded as epoch ms; minutes relative to midnight keep 23:30 -> -30.
        start = parse_instant(row.get("sleepStartTimestampLocal"))
        end = parse_instant(row.get("sleepEndTimestampLocal"))
        if start is not None:
            minutes = start.hour * 60 + start.minute
            batch.metrics.append(MetricRecord(day, "bedtime", minutes - 1440 if minutes >= 720 else minutes, "min"))
        if end is not None:
            batch.metrics.append(MetricRecord(day, "wake_time", end.hour * 60 + end.minute, "min"))
    return batch


def _kg(value: Any) -> float | None:
    # Body-composition masses arrive as integers; human-scale masses above 500 can only be grams.
    v = num(value, positive=True)
    if v is None:
        return None
    return round(v / 1000, 3) if v > 500 else v


def _weight(payload: Any, _day: date | None) -> Batch:
    batch = Batch()
    summaries = payload.get("dailyWeightSummaries") if isinstance(payload, dict) else None
    for summary in summaries or []:
        for entry in summary.get("allWeightMetrics") or []:
            weight = _kg(entry.get("weight"))
            utc = parse_instant(entry.get("timestampGMT"))
            local_day = parse_day(entry.get("calendarDate")) or parse_day(summary.get("summaryDate"))
            if weight is None or utc is None or local_day is None:
                continue
            batch.weights.append(
                WeightRecord(
                    source_record_id=f"{utc.isoformat()}",
                    measured_at_utc=utc,
                    timezone=utc_offset_label(parse_instant(entry.get("date"), wall_clock=True), utc),
                    local_date=local_day,
                    weight_kg=weight,
                    body_fat_pct=num(entry.get("bodyFat"), positive=True),
                    bmi=num(entry.get("bmi"), positive=True),
                    body_water_pct=num(entry.get("bodyWater"), positive=True),
                    muscle_mass_kg=_kg(entry.get("muscleMass")),
                    bone_mass_kg=_kg(entry.get("boneMass")),
                    visceral_fat=num(entry.get("visceralFat"), positive=True),
                    metabolic_age=num(entry.get("metabolicAge"), positive=True),
                )
            )
    return batch


def _activities(payload: Any, _day: date | None) -> Batch:
    batch = Batch()
    for row in payload if isinstance(payload, list) else []:
        activity_id = row.get("activityId")
        utc = parse_instant(row.get("startTimeGMT"))
        local = parse_instant(row.get("startTimeLocal"), wall_clock=True)
        duration = num(row.get("duration"), positive=True) or num(row.get("elapsedDuration"), positive=True)
        if not isinstance(activity_id, int) or utc is None or duration is None:
            continue
        type_key = dig(row, "activityType", "typeKey") or "other"
        batch.activities.append(
            ActivityRecord(
                source_record_id=str(activity_id),
                start_time_utc=utc,
                timezone=utc_offset_label(local, utc),
                local_date=(local or utc).date(),
                activity_type=str(type_key)[:48],
                name=str(row.get("activityName") or type_key.replace("_", " ").title())[:200],
                duration_s=duration,
                distance_m=num(row.get("distance"), positive=True),
                avg_hr=num(row.get("averageHR"), positive=True),
                max_hr=num(row.get("maxHR"), positive=True),
                elevation_gain_m=num(row.get("elevationGain")),
                calories=num(row.get("calories")),
                training_load=num(row.get("activityTrainingLoad")),
                moving_duration_s=num(row.get("movingDuration"), positive=True),
                avg_speed_mps=num(row.get("averageSpeed"), positive=True),
                vo2max=num(row.get("vO2MaxValue"), positive=True),
                aerobic_te=num(row.get("aerobicTrainingEffect")),
            )
        )
    return batch


def _fitness_age(payload: Any, day: date | None) -> Batch:
    batch = Batch()
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    for row in rows:
        value = num(dig(row, "fitnessAge"), positive=True)
        if value is not None and day is not None:
            batch.metrics.append(MetricRecord(day, "fitness_age", round(value, 1), "years"))
            break
    return batch


_HANDLERS = {
    "daily_summaries": _daily_summaries,
    "hrv": _hrv,
    "sleep": _sleep,
    "weight": _weight,
    "activities": _activities,
    "fitness_age": _fitness_age,
}
