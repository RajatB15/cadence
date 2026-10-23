import math
import random
from datetime import date, datetime, timedelta

import pytest

from cadence_app.analytics import athlete as A
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import recovery as R
from cadence_app.analytics import score
from cadence_app.analytics.insights import assemble

D0 = date(2026, 1, 5)  # a Monday
EASY = (600, 3000, 0, 0, 0)
HARD = (300, 900, 600, 1500, 300)
ZONES = {"method": "LT", "floors": [100, 120, 140, 160, 175], "max": 190, "threshold": 168}


def days(n: int) -> list[date]:
    return [D0 + timedelta(days=i) for i in range(n)]


def act(i: int, day: date, zones=EASY, family="run", load=80.0, **kw) -> A.Act:
    start = datetime.combine(day, datetime.min.time()).replace(hour=7)
    return A.Act(id=i, day=day, start_local=start, end_local=start + timedelta(hours=1), family=family, type=family, name=f"r{i}",
                 load=load, distance_m=kw.pop("distance_m", 10000), moving_s=kw.pop("moving_s", 3600), avg_hr=kw.pop("avg_hr", 150),
                 speed_mps=2.8, zones_s=zones, **kw)


def test_hrv_guided_flags_a_suppressed_week_and_clears_a_normal_one():
    rng = random.Random(1)
    ds = days(100)
    hrv = {d: 60 * math.exp(rng.gauss(0, 0.05)) for d in ds}
    normal = R.hrv_guided(hrv, ds[-1])
    assert normal["status"] == "normal" and normal["green_light"] and normal["range_ms"][0] < 60 < normal["range_ms"][1]
    low = {**hrv, **{d: 48.0 for d in ds[-7:]}}
    r = R.hrv_guided(low, ds[-1])
    assert r["status"] == "below" and not r["green_light"] and r["history"]
    assert R.hrv_guided({d: 50.0 for d in ds[:10]}, ds[9]) is None


def test_recovery_profile_learns_how_long_hard_days_take():
    ds = days(200)
    acts = [act(i, d, HARD) for i, d in enumerate(ds) if i % 7 == 0 and i >= 70]
    hrv = {d: 60.0 + (i % 3) for i, d in enumerate(ds)}
    for a in acts:  # HRV dips for two mornings after each hard session
        hrv[a.day + timedelta(days=1)] = 50.0
        hrv[a.day + timedelta(days=2)] = 54.0
    r = R.recovery_profile(hrv, acts, ds[-1])
    hard = r["kinds"]["hard"]
    assert hard["personal"] and hard["days"] == 3 and hard["dip_sd"] < -2
    assert r["hard_spacing_days"] == 3 and r["half_life_h"] == 24.0
    assert not R.recovery_profile({}, [], ds[-1])["kinds"]["hard"]["personal"]


def test_sleep_need_finds_the_plateau():
    rng = random.Random(3)
    ds = days(200)
    hours = {d: rng.uniform(5.5, 9.5) for d in ds}
    hrv = {d: 55 + 4 * min(h, 7.5) + rng.gauss(0, 1.5) for d, h in hours.items()}
    r = R.sleep_need(hours, hrv)
    assert r["personal"] and r["hours"] == pytest.approx(7.5, abs=0.25)
    assert R.sleep_need({}, {})["hours"] == R.DEFAULT_SLEEP_NEED
    assert R.sleep_ok(7.8, 8.0) and not R.sleep_ok(7.5, 8.0)


def test_sleep_regularity_index():
    ds = days(14)
    steady = R.sleep_regularity({d: -30.0 for d in ds}, {d: 420.0 for d in ds}, ds[0], ds[-1])
    assert steady["sri"] == 100 and steady["midpoint_sd_min"] == 0
    beds = {d: -30.0 if i % 2 else 90.0 for i, d in enumerate(ds)}
    wakes = {d: 420.0 if i % 2 else 600.0 for i, d in enumerate(ds)}
    shifted = R.sleep_regularity(beds, wakes, ds[0], ds[-1])
    assert shifted["sri"] < 70


def test_warning_signals_need_two_markers():
    ds = days(40)
    series = {"resting_hr": {d: 50.0 + (i % 2) for i, d in enumerate(ds)}, "hrv": {d: 60.0 + (i % 3) for i, d in enumerate(ds)},
              "respiration": {d: 14.0 + (i % 2) * 0.2 for i, d in enumerate(ds)}}
    d = ds[-1]
    series["hrv"][d] = 61.0  # a typical night
    assert R.warning_signals(series, d) is None
    one = {**series, "resting_hr": {**series["resting_hr"], d: 57.0}}
    assert R.warning_signals(one, d) is None
    two = {**one, "hrv": {**series["hrv"], d: 45.0}}
    assert R.warning_signals(two, d)["level"] == "warn"
    three = {**two, "respiration": {**series["respiration"], d: 16.0}}
    assert R.warning_signals(three, d)["level"] == "alert"


def test_underfuelling_needs_all_three_signs():
    ds = days(90)
    hrv = {d: 60.0 + (i % 3) for i, d in enumerate(ds)} | {d: 52.0 for d in ds[-7:]}
    weights = [(ds[-28 + i * 4], 70 - i * 0.25) for i in range(7)]
    assert R.underfuelling(weights, hrv, {"change_pct_90d": -1.0}, ds[-1])["rate_pct_week"] < -0.5
    assert R.underfuelling(weights, hrv, {"change_pct_90d": 3.0}, ds[-1]) is None
    assert R.underfuelling([(d, 70.0) for d, _ in weights], hrv, None, ds[-1]) is None


def test_fdr_keeps_the_real_effect_and_drops_chance_findings():
    effects = [A.Effect(f"e{i}", "c", "o", "a", "b", 0, "", True, p_value=p) for i, p in enumerate([0.0001] + [0.04, 0.2, 0.5, 0.7, 0.9] * 2)]
    A.control_fdr(effects)
    assert [e.id for e in effects if e.significant] == ["e0"] and effects[1].q_value > 0.05


def test_compare_adjusts_for_a_confounder():
    rng = random.Random(7)
    ds = days(200)
    load = {d: rng.choice([0.0, 50.0, 150.0]) for d in ds}
    exposed = {d for d in ds if load[d] == 150.0 and rng.random() < 0.8} | {d for d in ds if load[d] == 0 and rng.random() < 0.1}
    reference = set(ds) - exposed
    outcome = {d + timedelta(days=1): 60 - 0.08 * load[d] + rng.gauss(0, 1) for d in ds}  # load does it, not the exposure
    raw = A.compare("x", "c", "o", "a", "b", exposed, reference, outcome, 1, "ms", True)
    adjusted = A.compare("x", "c", "o", "a", "b", exposed, reference, outcome, 1, "ms", True, {"training load": load})
    assert raw.diff < -5 and raw.p_value < 0.001
    assert abs(adjusted.diff) < 1 and adjusted.adjusted_for == ["training load"]


def steady_ctx(weeks: int = 16, goal: dict | None = None, extra: list | None = None) -> dict:
    acts, i = [], 0
    for w in range(weeks):
        for dd, z in ((0, EASY), (2, HARD), (4, EASY), (5, EASY), (6, EASY)):
            i += 1
            acts.append(act(i, D0 + timedelta(days=7 * w + dd), z, moving_s=4800 if dd == 6 else 3600,
                            distance_m=14000 if dd == 6 else 10000))
    acts += extra or []
    ds = days(weeks * 7)
    series = {"hrv": {d: 58.0 + (k % 4) for k, d in enumerate(ds)}, "resting_hr": {d: 50.0 + (k % 2) for k, d in enumerate(ds)},
              "sleep_hours": {d: 7.9 for d in ds}, "sleep_score": {d: 84.0 for d in ds}}
    return assemble("demo", series, acts, ds[-1], zones=ZONES, goal=goal)


def test_without_a_goal_three_building_weeks_earn_a_recovery_week():
    c = steady_ctx()
    phases = [training_plan.phase(c, A.week_start(c["as_of"]) - timedelta(weeks=k))["phase"] for k in range(4)]
    assert "recovery" in phases and set(phases) <= {"build", "recovery", "base"}


def test_goal_phases_count_back_from_race_day():
    c = steady_ctx()
    race = A.week_start(c["as_of"]) + timedelta(weeks=20, days=6)
    c["goal"] = {"distance": "half", "date": race, "target_s": None}
    c["_phase"] = {}
    names = [training_plan.phase(c, A.week_start(race) - timedelta(weeks=k))["phase"] for k in range(20)]
    assert names[0] == "race" and names[1:3] == ["taper", "taper"]
    assert names[3:6] == ["specific"] * 3 and names[6] == "recovery" and names[10] == "recovery"
    assert names[-1] == "base"


def test_weekly_plan_ramps_load_caps_the_long_run_and_rotates_sessions():
    c = steady_ctx()
    c["_phase"] = {A.week_start(c["as_of"]): {"phase": "build", "week_in_block": 2, "weeks_to_race": None, "label": "Build", "blurb": ""}}
    plan = training_plan.weekly_plan(c)
    chronic = 7 * c["pmc_by_day"][A.week_start(c["as_of"]) - timedelta(days=1)]["fitness"]
    lo, hi = plan["targets"]["load"]
    assert chronic * 0.93 <= lo and hi <= chronic * 1.25 * 1.07
    assert [s["kind"] for s in plan["sessions"]] == ["threshold", "vo2"] and "4 × 8 min" in plan["sessions"][0]["detail"]
    assert "160–168 bpm" in plan["sessions"][0]["detail"]
    assert plan["targets"]["long_km_cap"] == pytest.approx(15.4) and plan["targets"]["strength"] == 2
    assert plan["targets"]["sleep_h"] == 8.0


def test_score_does_not_punish_a_planned_recovery_week():
    c = steady_ctx()
    d = c["as_of"]
    c["_phase"] = {A.week_start(d): {"phase": "recovery", "week_in_block": 4, "weeks_to_race": None, "label": "", "blurb": ""}}
    p = c["pmc_by_day"][d]
    c["pmc_by_day"][d] = {**p, "acwr": 0.6}
    factors = {f["key"]: f for f in score.factors(c, d)}
    assert factors["load_balance"]["score"] == 100 and "recovery week" in factors["load_balance"]["target"]
    c["_phase"] = {A.week_start(d): {"phase": "build", "week_in_block": 1, "weeks_to_race": None, "label": "", "blurb": ""}}
    assert {f["key"]: f for f in score.factors(c, d)}["load_balance"]["score"] < 100


def test_walks_no_longer_dilute_the_intensity_split():
    acts = [act(1, D0, GREY := (300, 1200, 2100, 0, 0)), act(2, D0, (0, 7200, 0, 0, 0), family="walk", load=10)]
    split = A.intensity_split(acts, D0)
    assert split["easy_pct"] == 42 and split["by_sport"]["run"]["moderate_pct"] == 58 and GREY
    assert not A.is_training(acts[1]) and A.is_training(act(3, D0, family="walk", load=60))


def test_anaerobic_effect_marks_sprint_sessions_hard():
    sprints = act(1, D0, EASY, anaerobic_te=3.4)
    assert A.is_hard(sprints) and A.intensity(sprints)["kind"] == "hard"
    assert not A.is_hard(act(2, D0, EASY, anaerobic_te=1.2))


def test_efficiency_uses_heart_rate_above_rest():
    runs = [act(i, D0 + timedelta(days=i), avg_hr=hr) for i, hr in enumerate([130, 150, 170] * 4)]
    # Speed proportional to HR above a 50 bpm rest: every run is equally efficient.
    runs = [A.Act(**{**r.__dict__, "speed_mps": (r.avg_hr - 50) * 0.035}) for r in runs]
    eff = A.efficiency(runs, {d: 50.0 for d in days(20)})
    assert len({p["ef"] for p in eff}) == 1
    pace_150 = A.pace_at_hr(eff[0]["ef"], 150, 50)
    assert pace_150 == pytest.approx(1000 / 3.5, abs=0.5)
    assert A.efficiency([act(9, D0, HARD)]) == []


def test_tonight_adds_training_and_debt_and_counts_back_from_wake():
    ds = days(40)
    day = ds[-1]  # 2026-02-13, a Friday: tomorrow is a weekend morning
    series = {"sleep_hours": {d: 8.0 for d in ds}, "wake_time": {d: (480.0 if d.weekday() >= 5 else 390.0) for d in ds}}
    load = {d: 100.0 for d in ds[:-1]}
    base = R.sleep_tonight(series, load | {day: 0.0}, 8.0, day)
    assert base["tonight_h"] == 8.0 and base["wake_min"] == 480 and base["bed_min"] == 480 - 480 - 15 and base["weekend"]
    hard = R.sleep_tonight(series, load | {day: 250.0}, 8.0, day)
    assert hard["extra_load_min"] == 30 and hard["tonight_h"] == 8.5
    short = {**series, "sleep_hours": series["sleep_hours"] | {d: 6.5 for d in ds[-4:]}}
    tired = R.sleep_tonight(short, load | {day: 0.0}, 8.0, day)
    assert tired["debt_h"] == 6.0 and tired["repay_min"] == 60 and tired["bed_min"] == base["bed_min"] - 60
    assert R.sleep_tonight({"sleep_hours": {}, "wake_time": {}}, load, 8.0, day) is None
    late = {**short, "bedtime": {d: 30.0 for d in ds}}  # usually asleep at 00:30
    shifted = R.sleep_tonight(late, load | {day: 0.0}, 8.0, day)
    assert shifted["capped"] and shifted["lights_out_min"] == -30 and shifted["ideal_h"] == 9.0 and shifted["tonight_h"] == 8.5


def test_bedtime_push_moves_with_tonight():
    from cadence_app.push import bedtime_due
    at = lambda h, m: datetime(2026, 2, 13, h, m)  # noqa: E731
    tonight = {"bed_min": -60}  # in bed by 23:00 → nudge at 22:15
    assert not bedtime_due(at(22, 0), tonight) and bedtime_due(at(22, 15), tonight)
    assert bedtime_due(at(23, 35), {"bed_min": 20}) and not bedtime_due(at(23, 30), {"bed_min": 20})  # 00:20 → 23:35
    assert bedtime_due(at(23, 30), {"bed_min": 60}) and not bedtime_due(at(23, 0), {"bed_min": 60})  # after 00:45 → 23:30
    assert not bedtime_due(at(18, 30), {"bed_min": -400}) and bedtime_due(at(19, 0), {"bed_min": -400})
    assert not bedtime_due(at(23, 0), None)


def test_sleep_target_check_compares_nights_at_target():
    rng = random.Random(5)
    ds = days(200)
    hours = {d: rng.choice([6.0, 7.0, 8.2, 8.5]) for d in ds}
    series = {"sleep_hours": hours, "wake_time": {d: 420.0 for d in ds}, "hrv": {d: 50 + 4 * (hours[d] - 6) + rng.gauss(0, 1.5) for d in ds}}
    e = R.sleep_target_check(series, {}, 8.0, ds[-1])
    assert e is not None and e.significant and e.diff > 3
