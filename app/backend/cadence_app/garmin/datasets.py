from __future__ import annotations

from dataclasses import dataclass, field

# kinds: range (date windows), singleton, daily (one call per day), activity (one call per activity)
# selector (daily kind): ("metric", name) days having that metric | ("monthly",) | ("weekly",)


@dataclass(frozen=True)
class Dataset:
    key: str
    label: str
    tier: str  # core | deep
    kind: str
    path: str
    params: dict = field(default_factory=dict)
    window_days: int = 0
    page_size: int = 0
    refresh_days: int = 7
    selector: tuple = ()
    probe: bool = False
    binary: bool = False


RANGE = "range"
SINGLETON = "singleton"
DAILY = "daily"
ACTIVITY = "activity"

DATASETS: tuple[Dataset, ...] = (
    Dataset("profile", "Profile settings", "core", SINGLETON, "/userprofile-service/userprofile/settings"),
    Dataset("hr_zones", "Heart-rate zones", "core", SINGLETON, "/biometric-service/heartRateZones/v2"),
    # Range datasets, in backfill priority order; activities and daily summaries establish history depth.
    # Garmin documents 1-year windows but returns HTTP 500 above ~120 days in practice (observed 2026-10-22).
    Dataset(
        "activities", "Activities", "core", RANGE, "/activitylist-service/activities/search/activities",
        {"startDate": "{start}", "endDate": "{end}", "start": "{offset}", "limit": "{limit}"},
        window_days=180, page_size=50,
    ),
    Dataset(
        "daily_summaries", "Daily summaries", "core", RANGE, "/usersummary-service/v2/dailysummaries",
        {"startDate": "{start}", "endDate": "{end}"}, window_days=120,
    ),
    Dataset(
        "sleep", "Sleep", "core", RANGE, "/sleep-service/sleep/dailySleepSummariesByDate",
        {"startDate": "{start}", "endDate": "{end}"}, window_days=31,
    ),
    Dataset("hrv", "HRV", "core", RANGE, "/hrv-service/hrv/daily/{start}/{end}", window_days=31),
    Dataset(
        "weight", "Weight & body composition", "core", RANGE,
        "/weight-service/weight/range/{start}/{end}", {"includeAll": "true"}, window_days=120,
    ),
    Dataset(
        "weight_goals", "Weight goals", "core", RANGE,
        "/goal-service/goal/user/effective/weightgoal/{start}/{end}", window_days=120,
    ),
    Dataset(
        "body_battery", "Body Battery timeline", "deep", RANGE,
        "/wellness-service/wellness/bodyBattery/reports/daily",
        {"startDate": "{start}", "endDate": "{end}"}, window_days=31,
    ),
    Dataset(
        "wellness_activities", "Auto-detected moves", "deep", RANGE,
        "/wellnessactivity-service/activity/summary/range/{start}/{end}", window_days=31,
    ),
    Dataset("activity_fit", "Activity FIT files", "deep", ACTIVITY, "/download-service/files/activity/{id}", binary=True),
    Dataset("activity_detail", "Activity details & splits", "deep", ACTIVITY, "/activity-service/activity/{id}"),
    Dataset("activity_workouts", "Activity workouts", "deep", ACTIVITY, "/activity-service/activity/{id}/workouts"),
    Dataset(
        "hrv_intraday", "Overnight HRV readings", "deep", DAILY, "/hrv-service/hrv/{day}",
        selector=("metric", "hrv"),
    ),
    Dataset(
        "spo2", "SpO₂ readings", "deep", DAILY, "/wellness-service/wellness/daily/spo2acclimation/{day}",
        selector=("metric", "spo2"),
    ),
    Dataset(
        "food_logs", "Food logs", "deep", DAILY, "/nutrition-service/food/logs/{day}",
        selector=("metric", "calories_consumed"),
    ),
    Dataset(
        "fitness_age", "Fitness age", "deep", DAILY, "/fitnessage-service/fitnessage/v2/{day}",
        selector=("monthly",),
    ),
    Dataset(
        "menstrual", "Cycle summaries", "deep", DAILY,
        "/periodichealth-service/menstrualcycle/summary/{day}", selector=("weekly",), probe=True,
    ),
    Dataset(
        "hr_intraday", "All-day heart rate", "deep", DAILY, "/wellness-service/wellness/dailyHeartRate",
        {"date": "{day}"}, selector=("metric", "resting_hr"),
    ),
)

BY_KEY = {d.key: d for d in DATASETS}


def render(dataset: Dataset, **values) -> tuple[str, dict]:
    path = dataset.path.format(**values)
    params = {k: v.format(**values) for k, v in dataset.params.items()}
    return path, params
