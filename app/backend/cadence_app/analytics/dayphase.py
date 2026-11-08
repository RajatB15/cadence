"""Day-phase engine: which part of the day it is for you, and what the Home should lead with.

Pure: facts about the day in, a phase, an ordered list of cards and wording *codes* out (`notes.phase_copy` turns the codes
into sentences). The clock is the user's wall clock; `insights.phase_facts` converts from UTC with the user's timezone, so
nothing here ever sees server local time.

Rules (design in docs/home-design.md, section C)
- Time bands: dawn 04:00-06:59, morning 07:00-11:29, midday 11:30-14:29, afternoon 14:30-17:59, evening 18:00-20:59,
  late 21:00-03:59.
- Overrides, strongest first: sick > time_off (travel, holiday, injury) > race_day / race_week > post_workout (a session
  ended under 3 h ago, or one was done today and it is before 21:00) > rest_day > the time band.
- A planned session that is not done is `open` only while a window remains (at least 2 h, and at least the session's own
  length, before 20:00) and nothing says to hold back; later it is `window_closed`, and from 20:00 (or when the day's strain
  budget is used, readiness is under 55, or a check-in says less) it is `deferred`. Nothing here ever calls a session
  "open" after 20:00, and a missed session is never presented as a failure.
- Step prompts appear only when the remaining steps are reachable at a normal pace (at most 2,500 an hour until 21:30)
  and the phase is not sick, time off or late.
This is scheduling of what to show, not health advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

BANDS = (("late", 0, 4 * 60), ("dawn", 4 * 60, 7 * 60), ("morning", 7 * 60, 11 * 60 + 30), ("midday", 11 * 60 + 30, 14 * 60 + 30),
         ("afternoon", 14 * 60 + 30, 18 * 60), ("evening", 18 * 60, 21 * 60), ("late", 21 * 60, 24 * 60))
DEFERRED_FROM_MIN = 20 * 60
MIN_WINDOW_MIN = 120
POST_WORKOUT_H = 3
LOW_READINESS = 55
STEP_PACE_MAX = 2500
STEP_DEADLINE_MIN = 21 * 60 + 30
PHASES = ("dawn", "morning", "midday", "afternoon", "evening", "late", "post_workout", "rest_day", "race_week", "race_day", "time_off", "sick")
OFF_KINDS = ("travel", "vacation", "injury")

DEFAULT_VITALS = ["steps", "sleep_hours", "hrv", "resting_hr", "body_battery", "stress"]
MORNING_VITALS = ["sleep_hours", "hrv", "resting_hr", "body_battery", "stress", "steps"]
EVENING_VITALS = ["steps", "stress", "body_battery", "sleep_hours", "hrv", "resting_hr"]

# (visible cards in order, dimmed cards). Hidden = everything not listed.
CARDS: dict[str, tuple[list[str], list[str]]] = {
    "dawn": (["vitals", "now", "readiness", "checkin", "calories", "week", "recent", "more"], []),
    "morning": (["vitals", "now", "readiness", "checkin", "calories", "week", "recent", "more"], []),
    "midday": (["vitals", "calories", "now", "readiness", "checkin", "week", "recent", "more"], []),
    "afternoon": (["vitals", "calories", "now", "readiness", "checkin", "week", "recent", "more"], []),
    "evening": (["vitals", "now", "calories", "checkin", "week", "recent", "readiness", "more"], []),
    "late": (["now", "vitals", "calories", "week", "readiness", "more"], ["readiness"]),
    "post_workout": (["vitals", "now", "calories", "readiness", "week", "recent", "checkin", "more"], []),
    "rest_day": (["vitals", "now", "readiness", "calories", "checkin", "week", "recent", "more"], []),
    "race_week": (["vitals", "now", "readiness", "calories", "checkin", "week", "recent", "more"], []),
    "race_day": (["now", "vitals", "readiness", "calories", "checkin", "more"], []),
    "time_off": (["now", "vitals", "calories", "checkin", "more"], []),
    "sick": (["now", "vitals", "checkin", "calories", "more"], []),
}


@dataclass
class Facts:
    now: datetime  # the user's wall-clock time; only its date, hour and minute are used
    last_session_end: datetime | None = None  # wall clock, same zone as `now`
    sessions_today: int = 0
    plan_kind: str | None = None  # key | long | easy | strength | rest, None when nothing is planned
    plan_status: str = "none"  # none | not_done | done
    planned_minutes: int | None = None
    readiness: float | None = None
    time_off: str | None = None  # travel | vacation | injury | sick, for today
    illness: int = 0  # check-in, 0-2
    pain: int = 0  # 0-3
    soreness: int = 0  # 0-3
    strain_used: bool = False
    says_less: bool = False  # a check-in asks for rest or easy
    race_days: int | None = None  # days until a race (0 = today)
    steps: float | None = None
    step_goal: float | None = None
    garmin_today: bool = True
    sleep_synced: bool = True
    food_logged: bool = False


def minute_of_day(now: datetime) -> int:
    return now.hour * 60 + now.minute


def band(now: datetime) -> str:
    m = minute_of_day(now)
    return next(name for name, lo, hi in BANDS if lo <= m < hi)


def session_state(f: Facts, phase: str) -> str:
    """none | rest | done | upcoming | open | window_closed | deferred | race."""
    if phase in ("sick", "time_off"):
        return "none"
    if phase == "race_day":
        return "race"
    if f.plan_status == "done" or (f.plan_status == "none" and f.sessions_today):
        return "done"
    if f.plan_kind == "rest":
        return "rest"
    if f.plan_status != "not_done":
        return "none"
    m = minute_of_day(f.now)
    says_less = f.says_less or f.illness >= 1 or f.pain >= 2 or f.soreness >= 3
    if m >= DEFERRED_FROM_MIN or f.strain_used or says_less or (f.readiness is not None and f.readiness < LOW_READINESS):
        if m < 4 * 60:
            return "upcoming"  # the new day has only just begun
        return "deferred"
    if m < 4 * 60:
        return "upcoming"
    left = DEFERRED_FROM_MIN - m
    return "open" if left >= max(MIN_WINDOW_MIN, f.planned_minutes or 0) else "window_closed"


def step_prompt(f: Facts, phase: str) -> bool:
    if phase in ("sick", "time_off", "late") or f.steps is None or not f.step_goal:
        return False
    m = minute_of_day(f.now)
    remaining = f.step_goal - f.steps
    hours = (STEP_DEADLINE_MIN - m) / 60
    return remaining > 0 and hours > 0 and remaining / hours <= STEP_PACE_MAX


def phase_of(f: Facts) -> tuple[str, str]:
    """(phase, time band)."""
    b = band(f.now)
    m = minute_of_day(f.now)
    if f.time_off == "sick" or f.illness >= 2:
        return "sick", b
    if f.time_off in OFF_KINDS:
        return "time_off", b
    if f.race_days == 0:
        return "race_day", b
    if f.race_days is not None and 0 < f.race_days <= 7:
        return "race_week", b
    recent = (f.last_session_end is not None and 0 <= (f.now - f.last_session_end).total_seconds() < POST_WORKOUT_H * 3600)
    if f.sessions_today and (recent or m < 21 * 60) and m >= 4 * 60:
        return "post_workout", b
    if f.plan_kind == "rest" and f.plan_status != "done":
        return "rest_day", b
    return b, b


def phase(f: Facts) -> dict:
    ph, b = phase_of(f)
    m = minute_of_day(f.now)
    flags = []
    if not f.garmin_today:
        flags.append("no_garmin_data")
    if not f.sleep_synced:
        flags.append("sleep_not_synced")
    if f.readiness is not None and f.readiness < LOW_READINESS:
        flags.append("low_readiness")
    if f.pain >= 1:
        flags.append("pain")
    if f.illness == 1:
        flags.append("feeling_off")
    if f.strain_used:
        flags.append("strain_used")
    if m < 4 * 60:
        flags.append("new_day")
    if f.sessions_today and f.plan_kind in (None, "rest"):
        flags.append("bonus")
    if f.food_logged:
        flags.append("food_logged")
    state = session_state(f, ph)
    visible, dimmed = CARDS[ph]
    cards = list(visible)
    vitals = MORNING_VITALS if b in ("dawn", "morning") else EVENING_VITALS if b in ("evening", "late") else DEFAULT_VITALS
    if ph == "time_off":
        vitals = ["steps", "sleep_hours"] + [v for v in DEFAULT_VITALS if v not in ("steps", "sleep_hours")]
    hints = {
        "phase": ph,
        "session": state,
        "sleep": "not_synced" if not f.sleep_synced else "recap" if b in ("dawn", "morning") and ph in ("dawn", "morning") else "tile",
        "calories": "day_total" if m >= 21 * 60 or m < 4 * 60 else "left",
        "steps": "prompt" if step_prompt(f, ph) else "tile",
        "protein_check": ph == "evening" and f.food_logged,
        "yesterday_recap": m < 4 * 60,
    }
    return {"phase": ph, "band": b, "flags": flags, "cards": cards, "dimmed": dimmed, "hidden": [c for c in
            ("vitals", "calories", "now", "readiness", "checkin", "week", "recent", "more") if c not in cards],
            "vitals_order": vitals, "session_state": state, "hints": hints}
