"""Regression tests for the analytics review fixes (workstream D). All data synthetic."""

from datetime import date, timedelta

import pytest

from cadence_app.analytics import athlete as A
from cadence_app.analytics import banister as B
from cadence_app.analytics import goals as G
from cadence_app.analytics import performance as P
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import recovery as R
from cadence_app.analytics import score as S
from tests.test_performance import D0, runs_from_curve
from tests.test_recovery import days, steady_ctx


def _plan_ctx(loads: list[float], phase="build"):
    c = steady_ctx()
    ws = A.week_start(c["as_of"])
    done = [w for w in c["weeks"] if w["complete"]]
    for w, load in zip(done[-3:], loads):
        w["load"] = load
    c["_phase"] = {ws: {"phase": phase, "week_in_block": 1, "weeks_to_race": None, "label": "Build", "blurb": ""}}
    return c, [w["load"] for w in done[-3:]]


def test_weekly_target_is_capped_by_recent_actual_load():
    c, recent = _plan_ctx([200.0, 200.0, 200.0])  # chronic load (from fitness) is far above what was just done
    plan = training_plan.weekly_plan(c)
    top = plan["targets"]["load"][1]
    assert top <= training_plan.RECENT_CAP * max(recent[-1], sum(recent[-2:]) / 2) + 1
    assert top < 1.25 * 7 * c["pmc_by_day"][A.week_start(c["as_of"]) - timedelta(days=1)]["fitness"]


def test_band_top_never_exceeds_1_25_chronic_and_ramp_setting_binds():
    c, _ = _plan_ctx([10_000.0] * 3)  # recent huge: only chronic cap should bind
    ws = A.week_start(c["as_of"])
    chronic = 7 * c["pmc_by_day"][ws - timedelta(days=1)]["fitness"]
    assert training_plan.weekly_plan(c)["targets"]["load"][1] <= round(1.25 * chronic)
    c["plan_settings"] = {**training_plan.T.DEFAULTS, "ramp_pct": 0.0}
    flat = training_plan.weekly_plan(c)["targets"]["load"]
    assert flat[1] <= round(chronic * 1.07) + 1  # a 0% ramp holds chronic (old code forced a >= 2 point ramp)


def test_long_run_builds_from_the_recent_longest_not_a_60_minute_floor():
    c = {"as_of": date(2026, 6, 1), "weeks": [{"complete": True, "long_run_min": 30}] * 3, "acts": []}
    minutes, _, _ = training_plan._long_run(c, "build", None, None)
    assert minutes <= 40
    none = {"as_of": date(2026, 6, 1), "weeks": [{"complete": True, "long_run_min": 0}] * 3, "acts": []}
    assert training_plan._long_run(none, "build", None, None)[0] <= 30


def test_acwr_is_none_for_the_first_28_days():
    start = date(2026, 1, 1)
    load = {start + timedelta(days=i): 60.0 for i in range(60)}
    rows = A.pmc(load, start, start + timedelta(days=59))
    assert all(r["acwr"] is None for r in rows[:28]) and rows[40]["acwr"] is not None
    assert 0 <= A.load_score({**rows[5], "form": -2.0}) <= 100  # consumers cope with None


def test_intensity_minutes_need_five_days_of_data():
    c = steady_ctx()
    d = c["as_of"]
    c["series"]["intensity_minutes"] = {d - timedelta(days=i): 40 for i in range(3)}  # 3 recorded days of 7
    assert not any(f["key"] == "intensity_minutes" for f in S.factors(c, d))
    c["series"]["intensity_minutes"] = {d - timedelta(days=i): 30 for i in range(6)}  # 6 days: scaled to a week
    f = next(f for f in S.factors(c, d) if f["key"] == "intensity_minutes")
    assert "210" in f["value"]


def test_critical_speed_rejects_noisy_or_thin_efforts():
    good = P.critical_speed(runs_from_curve(4.0, 200), D0 + timedelta(days=10))
    assert good["valid"] and good["n_points"] >= 4 and good["cs_ci"][0] <= good["cs_mps"] <= good["cs_ci"][1]
    noisy = runs_from_curve(4.0, 200)
    noisy[0]["best"]["420"] = round(noisy[0]["best"]["420"] * 1.10, 3)  # one effort 10% off the curve
    noisy[0]["best"]["900"] = round(noisy[0]["best"]["900"] * 0.92, 3)
    assert not P.critical_speed(noisy, D0 + timedelta(days=10))["valid"]
    thin = [{"id": 1, "day": D0, "name": "x", "best": {"180": 4.7, "720": 4.2, "1200": 4.17}}]
    assert not P.critical_speed(thin, D0 + timedelta(days=1))["valid"]  # 3 points, one 10+ min short of the 2 needed


def test_race_time_ranges_and_blend_toward_riegel_when_extrapolating():
    r = P.critical_speed(runs_from_curve(4.0, 200), D0 + timedelta(days=10))
    five = next(p for p in r["predictions"] if p["key"] == "5k")
    assert five["low_s"] <= five["seconds"] <= five["high_s"]
    anchor = {"seconds": 300.0, "distance_m": 300 * 4.9}
    cs_only = float(P.race_time(10000, 4.0, 200))
    blended = float(P.race_time(10000, 4.0, 200, anchor))
    assert blended != cs_only  # a 5-minute anchor cannot vouch for a 10 km hyperbola


def test_overlapping_cs_history_is_thinned_before_the_trend_fit():
    hist = [{"day": date(2026, 10, 24) - timedelta(days=30 * m), "cs_mps": 4.0 + 0.01 * (m % 2)} for m in range(12)]
    c = {"as_of": date(2026, 10, 24), "performance": {"critical_speed": {"valid": True, "cs_mps": 4.0, "d_prime_m": 200}, "history": hist}}
    m = G.cs_model(c)
    assert m["n_history"] <= 4 and m["sigma_assumed"] is False or m["n_history"] < 4


def test_banister_needs_30_weekly_points():
    assert B.MIN_OBS == 30
    load = {date(2025, 1, 1) + timedelta(days=i): 50.0 for i in range(400)}
    obs = [(date(2025, 1, 1) + timedelta(weeks=i), 1.0 + 0.001 * i) for i in range(20)]
    assert not B.fit(load, obs, date(2026, 1, 1))["valid"]


def test_efficiency_trend_needs_a_60_day_span():
    pts = [{"day": date(2026, 6, 1) + timedelta(days=i * 2), "ef": 1.0 + 0.001 * i, "rhr": 50.0} for i in range(20)]  # 38 days
    assert A.efficiency_trend(pts, 140.0, pts[-1]["day"]) is None


def test_sleep_debt_uses_the_last_seven_calendar_days():
    end = date(2026, 6, 30)
    hours = {end - timedelta(days=i): 6.0 for i in (0, 1, 20, 21, 22, 23, 24, 25)}  # only two nights in the last week
    p = A.sleep_pattern({}, {}, hours, end - timedelta(days=30))
    assert p["debt_hours"] == pytest.approx(4.0)  # 2 nights x 2 h, not 7 of the latest entries


def test_weekly_week_ending_today_is_not_complete():
    start = date(2026, 6, 1)  # Monday
    end = date(2026, 6, 7)  # Sunday
    load = {d: 10.0 for d in A.daterange(start, end)}
    assert A.weekly([], load, start, end)[0]["complete"]
    assert not A.weekly([], load, start, end, unsettled=end)[0]["complete"]


def test_hac_t_critical_value_is_wider_with_autocorrelation_lags():
    import numpy as np
    from cadence_app.analytics import regress
    x = np.column_stack([np.ones(40), np.arange(40.0)])
    y = np.sin(np.arange(40) / 5.0) + np.arange(40) * 0.01
    plain = regress.ols(x, y, lags=0)
    hac = regress.ols(x, y, lags=7)
    # same coefficient; the HAC interval uses fewer degrees of freedom than n - k
    assert hac["coef"][1] == pytest.approx(plain["coef"][1])
    width = lambda f: f["ci"][1][1] - f["ci"][1][0]  # noqa: E731
    assert width(hac) / hac["se"][1] > width(plain) / plain["se"][1]
