"""A planned run or ride as a Garmin Connect structured workout (pure; no network, no credentials).

Steps come from the planner (`analytics.planner`): warm-up, steady, work/recovery repeats, cool-down, each with a
heart-rate zone 1-5. Targets use Garmin's own zone numbers, so the watch applies the zones set in your Garmin
profile and Cadence never sends a made-up bpm. Cycling uses heart rate too: power zones need an FTP Cadence
doesn't know. Field names and ids follow Garmin Connect's workout-service JSON as written by the open-source
`garminconnect` library (workout.py); nothing here is documented by Garmin.
"""

from __future__ import annotations

SPORTS = {
    "run": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
    "ride": {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
}
STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "work": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "steady": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
}
REPEAT = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}
TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
DISTANCE = {"conditionTypeId": 3, "conditionTypeKey": "distance", "displayOrder": 3, "displayable": True}
ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}
HR_ZONE = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 4}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
NAME_LIMIT = 80  # Garmin Connect's workout name length
DEFAULT_ZONE = {"recovery": 1, "easy": 2, "long": 2, "tempo": 3, "threshold": 4, "vo2": 5}


class Unsupported(ValueError):
    pass


def fallback_steps(plan: dict) -> list[dict]:
    """Plans saved before steps existed: one steady block in the zone the session kind implies."""
    return [{"kind": "steady", "minutes": max(plan.get("minutes") or 0, 10), "zone": DEFAULT_ZONE.get(plan.get("kind"), 2)}]


def _executable(step: dict, order: int) -> dict:
    zone = step.get("zone")
    by_distance = bool(step.get("metres"))
    out = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": STEP_TYPES[step["kind"]],
        "endCondition": DISTANCE if by_distance else TIME,
        "endConditionValue": float(step["metres"]) if by_distance else round(step["minutes"] * 60.0),
        "targetType": HR_ZONE if zone else NO_TARGET,
    }
    if zone:
        out["zoneNumber"] = int(zone)
    return out


def _walk(steps: list[dict], order: int = 1) -> tuple[list[dict], int]:
    out: list[dict] = []
    for step in steps:
        if "repeat" in step:
            group_order = order
            children, order = _walk(step["steps"], order + 1)
            out.append({"type": "RepeatGroupDTO", "stepOrder": group_order, "stepType": REPEAT, "numberOfIterations": int(step["repeat"]),
                        "workoutSteps": children, "endCondition": ITERATIONS, "endConditionValue": float(step["repeat"]), "smartRepeat": False})
        else:
            out.append(_executable(step, order))
            order += 1
    return out, order


def _seconds(steps: list[dict], pace_s_per_m: float = 0.36) -> int:
    """Estimated duration; distance steps assume a 6:00/km pace when no better figure exists."""
    total = 0.0
    for step in steps:
        if "repeat" in step:
            total += step["repeat"] * _seconds(step["steps"], pace_s_per_m)
        elif step.get("metres"):
            total += step["metres"] * pace_s_per_m
        else:
            total += step["minutes"] * 60
    return round(total)


def build(plan: dict) -> dict:
    """The workout JSON for one planned session (`planner_store.as_dict` shape)."""
    sport = plan.get("sport")
    if sport not in SPORTS:
        raise Unsupported("Only runs and rides can be sent to Garmin")
    steps = plan.get("steps") or fallback_steps(plan)
    body, _ = _walk(steps)
    return {
        "workoutName": f"Cadence · {plan['title']}"[:NAME_LIMIT],
        "description": plan.get("detail"),
        "sportType": SPORTS[sport],
        "estimatedDurationInSecs": _seconds(steps),
        "workoutSegments": [{"segmentOrder": 1, "sportType": SPORTS[sport], "workoutSteps": body}],
    }
