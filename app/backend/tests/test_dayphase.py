"""Day-phase engine: time bands x states matrix, overrides, unfinished-session rules, step prompts, DST and timezones. Synthetic only."""

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from cadence_app.analytics import dayphase as DP
from cadence_app.analytics import insights
from cadence_app.analytics import notes

DAY = date(2026, 10, 22)
TIMES = [(5, 30), (8, 0), (12, 0), (16, 0), (19, 30), (20, 0), (22, 0), (23, 45), (0, 10)]
SHAME = re.compile(r"\bopen\b|\bfail|(?<!nothing is )\bmissed\b|should have|lazy|behind|guilt|cheat|\bsick\b", re.I)
CARD_IDS = {"vitals", "calories", "now", "readiness", "checkin", "week", "recent", "more"}


def at(h, m):
    return datetime.combine(DAY, datetime.min.time()) + timedelta(hours=h, minutes=m)


def make(state, h, m):
    now = at(h, m)
    new_day = h < 4
    done_end = None if new_day else max(now - timedelta(hours=5), at(0, 0))
    f = DP.Facts(now=now, readiness=75.0)
    if state == "no_plan":
        pass
    elif state == "planned_not_done":
        f.plan_kind, f.plan_status = "easy", "not_done"
    elif state == "planned_done":
        f.plan_status, f.sessions_today, f.last_session_end = ("none", 0, None) if new_day else ("done", 1, done_end)
    elif state == "hard_done_1h":
        f.plan_status, f.sessions_today, f.last_session_end = ("none", 0, None) if new_day else ("done", 1, now - timedelta(hours=1))
    elif state == "bonus":
        f.plan_kind = None if new_day else None
        f.plan_status, f.sessions_today, f.last_session_end = ("none", 0, None) if new_day else ("done", 1, done_end)
    elif state == "rest_day":
        f.plan_kind = "rest"
    elif state == "sick":
        f.illness = 2
    elif state == "travel":
        f.time_off = "travel"
    elif state == "race_week":
        f.race_days = 4
    elif state == "race_day":
        f.race_days = 0
    elif state == "low_readiness":
        f.plan_kind, f.plan_status, f.readiness = "key", "not_done", 40.0
    elif state == "pain_flag":
        f.plan_kind, f.plan_status, f.pain = "easy", "not_done", 2
    elif state == "no_garmin":
        f.garmin_today, f.sleep_synced, f.readiness = False, False, None
    return f


STATES = ["no_plan", "planned_not_done", "planned_done", "hard_done_1h", "bonus", "rest_day", "sick", "travel", "race_week", "race_day", "low_readiness", "pain_flag", "no_garmin"]
CASES = [(s, h, m) for s in STATES for h, m in TIMES]


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from strings(v)


def test_the_matrix_is_117_cases():
    assert len(CASES) == 117


@pytest.mark.parametrize("state,h,m", CASES, ids=[f"{s}-{h:02d}{m:02d}" for s, h, m in CASES])
def test_matrix(state, h, m):
    f = make(state, h, m)
    ph = DP.phase(f)
    copy = notes.phase_copy(ph)
    assert ph["phase"] in DP.PHASES and ph["band"] == DP.band(f.now)
    assert ph["cards"] and len(set(ph["cards"])) == len(ph["cards"]) and set(ph["cards"]) <= CARD_IDS
    assert sorted(ph["cards"] + ph["hidden"]) == sorted(CARD_IDS) and set(ph["dimmed"]) <= set(ph["cards"])
    assert ph["cards"] == DP.CARDS[ph["phase"]][0]
    for t in strings(copy):
        assert not SHAME.search(t), (state, h, m, t)  # never "open" as a word, never shaming
    late = h >= 21 or h < 4
    assert ph["hints"]["calories"] == ("day_total" if late else "left") and (copy["calories"] == "Day total so far") == late
    if state == "sick":
        assert ph["phase"] == "sick" and ph["session_state"] == "none" and copy["session"] is None and "Rest" in copy["headline"]
        assert "readiness" not in ph["cards"] and "week" not in ph["cards"] and ph["hints"]["steps"] == "tile"
    if state == "travel":
        assert ph["phase"] == "time_off" and ph["session_state"] == "none" and "nothing is missed" in copy["headline"]
    if state in ("race_week", "race_day"):
        assert ph["phase"] == state
    if state == "planned_not_done":
        if (h, m) >= (20, 0) and h >= 20:
            assert ph["session_state"] == "deferred"
        elif h < 4:
            assert ph["session_state"] == "upcoming"
        elif (h, m) >= (18, 0):
            assert ph["session_state"] == "window_closed"
        else:
            assert ph["session_state"] == "open"
    if state in ("low_readiness", "pain_flag") and h >= 4:
        assert ph["session_state"] == "deferred" and "deferred" == ph["hints"]["session"]
        assert ("low_readiness" if state == "low_readiness" else "pain") in ph["flags"]
    if h == 22 and state == "planned_not_done":
        assert ph["session_state"] == "deferred" and copy["session"]["title"] == "Not today"
    if state == "no_garmin":
        assert {"no_garmin_data", "sleep_not_synced"} <= set(ph["flags"]) and copy["sleep"] == "Sleep not synced yet"
        assert not any(re.search(r"\b0 ?h\b", t) for t in strings(copy))
    if h == 0:
        assert "new_day" in ph["flags"] and ph["hints"]["yesterday_recap"] and copy["recap"] and ph["phase"] in ("late", "sick", "time_off", "race_week", "race_day", "rest_day")
    if state == "hard_done_1h" and h >= 4:
        assert ph["phase"] == "post_workout"
    if state == "bonus" and h >= 4 and h < 21:
        assert ph["phase"] == "post_workout" and "bonus" in ph["flags"]
    if state == "rest_day" and h >= 4:
        assert ph["phase"] == "rest_day" and ph["session_state"] == "rest"


def test_post_workout_beats_the_rest_day_label_and_ends_by_evening():
    f = DP.Facts(now=at(10, 0), plan_kind="rest", sessions_today=1, last_session_end=at(9, 0), plan_status="done")
    assert DP.phase(f)["phase"] == "post_workout"
    f.now = at(22, 0)  # done long ago and it is late: the band takes over
    f.last_session_end = at(9, 0)
    assert DP.phase(f)["phase"] == "late"
    f.last_session_end = at(21, 0)  # finished an hour ago: still recovering
    assert DP.phase(f)["phase"] == "post_workout"


def test_override_priority_sick_then_time_off_then_race_then_workout():
    f = DP.Facts(now=at(10, 0), time_off="travel", race_days=0, sessions_today=1, last_session_end=at(9, 30), plan_kind="rest")
    assert DP.phase_of(f)[0] == "time_off"
    f.illness = 2
    assert DP.phase_of(f)[0] == "sick"
    f.illness, f.time_off = 0, None
    assert DP.phase_of(f)[0] == "race_day"
    f.race_days = 30
    assert DP.phase_of(f)[0] == "post_workout"
    f.sessions_today, f.last_session_end = 0, None
    assert DP.phase_of(f)[0] == "rest_day"
    f.plan_kind = None
    assert DP.phase_of(f)[0] == "morning"


@pytest.mark.parametrize("h,m,band", [(3, 59, "late"), (4, 0, "dawn"), (6, 59, "dawn"), (7, 0, "morning"), (11, 29, "morning"), (11, 30, "midday"), (14, 29, "midday"),
                                       (14, 30, "afternoon"), (17, 59, "afternoon"), (18, 0, "evening"), (20, 59, "evening"), (21, 0, "late"), (23, 59, "late"), (0, 0, "late")])
def test_time_bands(h, m, band):
    assert DP.band(at(h, m)) == band


def test_open_needs_a_two_hour_window_before_eight_pm_and_the_sessions_own_length():
    f = DP.Facts(now=at(17, 30), plan_kind="easy", plan_status="not_done")
    assert DP.session_state(f, "afternoon") == "open"
    f.now = at(18, 30)
    assert DP.session_state(f, "evening") == "window_closed"
    f.now, f.planned_minutes = at(16, 30), 240  # a long session needs more than the 2 h floor
    assert DP.session_state(f, "afternoon") == "window_closed"
    f.now, f.planned_minutes, f.strain_used = at(10, 0), None, True
    assert DP.session_state(f, "morning") == "deferred"
    f.strain_used, f.says_less = False, True
    assert DP.session_state(f, "morning") == "deferred"


def test_step_prompt_only_when_reachable_and_not_late_sick_or_time_off():
    f = DP.Facts(now=at(14, 0), steps=6000.0, step_goal=10000.0)
    assert DP.phase(f)["hints"]["steps"] == "prompt"  # 4000 in 7.5 h
    f.steps, f.step_goal = 500.0, 25000.0  # 24,500 in 7.5 h is more than 2,500 an hour
    assert DP.phase(f)["hints"]["steps"] == "tile"
    f.steps, f.now = 6000.0, at(20, 30)  # 4000 in 1 h
    assert DP.phase(f)["hints"]["steps"] == "tile"
    f.now, f.illness = at(14, 0), 2
    assert DP.phase(f)["hints"]["steps"] == "tile"
    assert DP.phase(DP.Facts(now=at(14, 0), steps=None, step_goal=10000.0))["hints"]["steps"] == "tile"  # unknown steps are not zero
    assert DP.phase(DP.Facts(now=at(14, 0), steps=12000.0, step_goal=10000.0))["hints"]["steps"] == "tile"  # already there
    assert DP.phase(DP.Facts(now=at(22, 0), steps=1000.0, step_goal=10000.0))["hints"]["steps"] == "tile"


def test_golden_card_order_per_phase():
    assert DP.CARDS["morning"][0] == ["vitals", "now", "readiness", "checkin", "calories", "week", "recent", "more"]
    assert DP.CARDS["afternoon"][0] == ["vitals", "calories", "now", "readiness", "checkin", "week", "recent", "more"]
    assert DP.CARDS["evening"][0] == ["vitals", "now", "calories", "checkin", "week", "recent", "readiness", "more"]
    assert DP.CARDS["late"] == (["now", "vitals", "calories", "week", "readiness", "more"], ["readiness"])
    assert DP.CARDS["post_workout"][0][:3] == ["vitals", "now", "calories"]
    assert DP.CARDS["sick"][0] == ["now", "vitals", "checkin", "calories", "more"]
    assert DP.CARDS["time_off"][0] == ["now", "vitals", "calories", "checkin", "more"]
    assert set(DP.CARDS) == set(DP.PHASES)
    assert DP.phase(DP.Facts(now=at(8, 0)))["vitals_order"][:3] == ["sleep_hours", "hrv", "resting_hr"]
    assert DP.phase(DP.Facts(now=at(19, 0)))["vitals_order"][:3] == ["steps", "stress", "body_battery"]
    assert DP.phase(DP.Facts(now=at(8, 0), time_off="travel"))["vitals_order"][:2] == ["steps", "sleep_hours"]


@pytest.mark.parametrize("name,day", [("Europe/London", date(2026, 3, 29)), ("Europe/London", date(2026, 10, 25)), ("America/New_York", date(2026, 3, 8)), ("America/New_York", date(2026, 11, 1))])
def test_dst_change_days_have_no_missing_or_duplicated_band(name, day):
    zone = ZoneInfo(name)
    start = datetime.combine(day, datetime.min.time(), tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    seq = []
    for k in range(0, 24 * 4 + 12):
        local = insights.to_local(start + timedelta(minutes=15 * k), name)
        if local.date() == day:
            b = DP.band(local)
            if not seq or seq[-1] != b:
                seq.append(b)
    assert seq == ["late", "dawn", "morning", "midday", "afternoon", "evening", "late"]


def test_the_users_timezone_decides_not_the_servers():
    instant = datetime(2026, 10, 22, 23, 0)  # naive UTC
    assert insights.to_local(instant, "Asia/Tokyo") == datetime(2026, 10, 23, 8, 0)
    assert insights.to_local(instant, "America/Los_Angeles") == datetime(2026, 10, 22, 16, 0)
    assert DP.band(insights.to_local(instant, "Asia/Tokyo")) == "morning" and DP.band(insights.to_local(instant, "America/Los_Angeles")) == "afternoon"


def test_phone_facts_from_a_brief_and_context():
    brief = {"today": {"kind": "key", "title": "Intervals"}, "readiness": {"score": 60, "morning_score": 72}, "strain": {"status": "in"}, "wellbeing": {"level": "easy"}}
    c = {"time_off": [], "wellbeing": {DAY: {"illness": 0, "pain_level": 2, "soreness": 1}}, "goal": {"date": DAY + timedelta(days=3)}}
    f = insights.phase_facts(c, brief, at(15, 0), session_ends=[at(9, 0)], steps=4000.0)
    assert (f.plan_kind, f.plan_status, f.readiness, f.strain_used, f.says_less, f.pain, f.race_days, f.sessions_today) == ("key", "not_done", 72, True, True, 2, 3, 1)
    done = insights.phase_facts(None, {"today": {"kind": "done", "status": "extra"}}, at(15, 0), session_ends=[at(9, 0)])
    assert done.plan_status == "done" and done.plan_kind is None
    off = insights.phase_facts({"time_off": [{"id": 1, "kind": "travel", "start": DAY, "end": DAY + timedelta(days=2), "activity": "none", "severity": None,
                                               "return_weeks": None, "return_start_pct": None}], "wellbeing": {}}, None, at(15, 0))
    assert off.time_off == "travel"
