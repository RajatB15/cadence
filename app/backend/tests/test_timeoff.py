from datetime import date, timedelta

import pytest

from cadence_app.analytics import athlete as A
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import status as status_analytics
from cadence_app.analytics import timeoff as T
from cadence_app.analytics import trends
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_recovery import steady_ctx

CFG = T.DEFAULTS


def entry(kind="sick", start=date(2026, 3, 2), end=date(2026, 3, 8), **kw):
    return {"id": 1, "kind": kind, "start": start, "end": end, "activity": None, "severity": None, "return_weeks": None,
            "return_start_pct": None, "note": None, **kw}


def with_time_off(c: dict, *periods: dict, **settings) -> dict:
    c["time_off"] = list(periods)
    c["plan_settings"] = T.clean_settings(settings)
    c["_phase"] = {}
    return c


def next_week(c: dict) -> date:
    return A.week_start(c["as_of"])


def test_a_week_of_travel_scales_targets_by_the_days_you_can_train():
    ws = date(2026, 3, 2)
    trip = entry("travel", ws + timedelta(days=2), ws + timedelta(days=4), activity="none")
    scale = T.week_scale([trip], CFG, ws, ws)
    assert scale["availability"] == pytest.approx(4 / 7, abs=0.01) and scale["ret"] == 1.0 and scale["days_off"] == 3
    light = T.week_scale([{**trip, "activity": "light"}], CFG, ws, ws)
    assert light["availability"] == pytest.approx((4 + 3 * T.LIGHT_SHARE) / 7, abs=0.01)
    assert T.week_scale([{**trip, "activity": "full"}], CFG, ws, ws)["scale"] == 1.0  # travelling but training as normal


def test_return_ramp_starts_at_your_share_and_climbs_back_linearly():
    sick = entry("sick", date(2026, 3, 2), date(2026, 3, 8), severity=2)  # moderate: 2 weeks from 50%
    ws1, ws2, ws3 = date(2026, 3, 9), date(2026, 3, 16), date(2026, 3, 23)
    today = date(2026, 3, 9)
    r1, r2, r3 = (T.week_scale([sick], CFG, today, w)["ret"] for w in (ws1, ws2, ws3))
    assert 0.5 <= r1 < r2 < 1.0 and r3 == 1.0
    mild = T.week_scale([{**sick, "severity": 1}], CFG, today, ws1)["ret"]
    severe = T.week_scale([{**sick, "severity": 3}], CFG, today, ws1)["ret"]
    assert severe < r1 < mild  # how it felt scales the defaults
    custom = T.week_scale([{**sick, "return_weeks": 1, "return_start_pct": 80}], CFG, today, ws1)["ret"]
    assert 0.8 <= custom < 0.9 and T.week_scale([{**sick, "return_weeks": 1}], CFG, today, ws2)["ret"] == 1.0  # per-entry settings win


def test_short_trips_do_not_trigger_an_easing_back_period_but_long_ones_do():
    today, ws = date(2026, 3, 16), date(2026, 3, 16)
    short = entry("vacation", date(2026, 3, 11), date(2026, 3, 14), activity="none")  # 4 days
    two_days = entry("vacation", date(2026, 3, 13), date(2026, 3, 14), activity="none")
    assert T.week_scale([short], CFG, today, ws)["ret"] < 1.0
    assert T.week_scale([two_days], CFG, today, ws)["ret"] == 1.0


def test_settings_are_clamped_and_unknown_values_fall_back():
    cfg = T.clean_settings({"ramp_pct": 50, "build_weeks": 9, "away_activity": "swim", "deload_pct": "x"})
    assert cfg["ramp_pct"] == 8.0 and cfg["build_weeks"] == 4 and cfg["away_activity"] == "light" and cfg["deload_pct"] == 65.0


def test_a_trip_this_week_scales_the_plan_and_a_week_away_plans_nothing():
    c = steady_ctx()
    ws = next_week(c)
    base = training_plan.weekly_plan(c)
    away = with_time_off(c, entry("travel", ws, ws + timedelta(days=6), activity="none"))
    paused = training_plan.weekly_plan(away)
    assert paused["phase"]["phase"] == "away" and paused["targets"]["load"] == [0, 0] and paused["targets"]["sessions"] == 0
    assert paused["targets"]["hard"] == 0 and paused["sessions"] == [] and paused["targets"]["long_min"] is None
    half = with_time_off(steady_ctx(), entry("travel", ws, ws + timedelta(days=2), activity="none"))
    plan = training_plan.weekly_plan(half)
    assert plan["targets"]["load"][1] < 0.65 * base["targets"]["load"][1] and plan["targets"]["sessions"] < base["targets"]["sessions"]
    assert plan["items"][0]["label"] == "Time off" and plan["time_off"]["days_off"] == 3


def test_after_illness_the_plan_eases_back_from_pre_illness_fitness():
    c = steady_ctx()
    ws = next_week(c)
    chronic = 7 * c["pmc_by_day"][ws - timedelta(days=11)]["fitness"]  # the day before the illness began
    c = with_time_off(c, entry("sick", ws - timedelta(days=10), ws - timedelta(days=1), severity=2))
    c["pmc_by_day"][ws - timedelta(days=1)] = {**c["pmc_by_day"][ws - timedelta(days=1)], "fitness": 0.6 * chronic / 7}  # the break has cost fitness
    plan = training_plan.weekly_plan(c)
    ret = plan["time_off"]["ret"]
    assert plan["phase"]["phase"] == "return" and 0.5 <= ret < 0.7 and plan["targets"]["hard"] in (0, 1)
    assert plan["targets"]["load"][1] == pytest.approx(1.07 * ret * chronic, rel=0.02)  # from the pre-break level, not the lower one
    assert plan["targets"]["long_min"] is None or plan["targets"]["long_min"] <= 90


def test_the_ramp_setting_changes_how_fast_load_builds():
    gentle = steady_ctx()
    gentle["_phase"] = {A.week_start(gentle["as_of"]): {"phase": "build", "week_in_block": 2, "weeks_to_race": None, "label": "Build", "blurb": ""}}
    gentle["plan_settings"] = T.clean_settings({"ramp_pct": 2})
    keen = steady_ctx()
    keen["_phase"] = dict(gentle["_phase"])
    keen["plan_settings"] = T.clean_settings({"ramp_pct": 8})
    assert training_plan.weekly_plan(keen)["targets"]["load"][1] > training_plan.weekly_plan(gentle)["targets"]["load"][1]


def test_a_week_lost_to_a_break_stands_in_for_the_recovery_week():
    c = steady_ctx()
    ws = next_week(c)
    c = with_time_off(c, entry("travel", ws - timedelta(days=7), ws - timedelta(days=1), activity="none"))
    assert training_plan.phase(c, ws)["phase"] in ("build", "base") and training_plan.phase(c, ws)["week_in_block"] == 1


def test_status_labels_a_steady_block_and_marks_time_off_and_returns():
    c = steady_ctx()
    rep = status_analytics.report(c, 8)
    assert rep["n"] >= 4 and rep["current"]["status"] in ("maintaining", "progressing", "deloading") and rep["slope_4w"] is not None
    ws = next_week(c)
    off = with_time_off(steady_ctx(), entry("sick", ws - timedelta(days=8), ws - timedelta(days=3)))
    statuses = [w["status"] for w in status_analytics.report(off, 8)["weeks"]]
    assert "off" in statuses
    assert status_analytics.classify({"availability": 1, "ret": 1, "fitness_start": 40, "ratio": 1.4, "acwr": 1.1, "fatigued": False,
                                      "change_pct": 3, "days_off": 0, "scale": 1}, False, False)[0] == "overloading"
    assert status_analytics.classify({"availability": 1, "ret": 1, "fitness_start": 40, "ratio": 1.0, "acwr": 1.0, "fatigued": False,
                                      "change_pct": 2.4, "days_off": 0, "scale": 1}, False, False)[0] == "progressing"
    assert status_analytics.classify({"availability": 1, "ret": 1, "fitness_start": 40, "ratio": 0.5, "acwr": 0.6, "fatigued": False,
                                      "change_pct": -4, "days_off": 0, "scale": 1}, False, True)[0] == "detraining"
    assert status_analytics.classify({"availability": 1, "ret": 1, "fitness_start": 3, "ratio": 1, "acwr": 1, "fatigued": False,
                                      "change_pct": 0, "days_off": 0, "scale": 1}, False, False)[0] == "unknown"


def test_trends_call_a_direction_only_when_the_data_support_it():
    end = date(2026, 6, 30)
    rising = [{"day": end - timedelta(days=i), "score": 50 + (27 - i) * 0.8 + (i % 3)} for i in range(55, -1, -1)]
    up = trends.summarise(rising, end, 28)
    assert up["direction"] == "up" and up["slope_per_week"] > 3 and up["delta"] > 10 and up["projection"]["range"][0] <= up["projection"]["value"]
    flat = [{"day": end - timedelta(days=i), "score": 70 + (3 if i % 2 else -3)} for i in range(55, -1, -1)]
    assert trends.summarise(flat, end, 28)["direction"] == "steady"
    few = trends.summarise(rising[-6:], end, 28)
    assert few["heading"]["direction"] == "unknown" and few["delta"] is None
    assert trends.summarise([], end, 7)["avg"] is None


def test_time_off_api_round_trip_and_phone_access(env):  # noqa: F811
    client, clock = env
    today = clock.today()
    body = {"kind": "travel", "start": str(today + timedelta(days=3)), "end": str(today + timedelta(days=8)), "activity": "light", "note": " Lisbon "}
    view = client.post("/api/time-off", json=body, headers=MUTATE).json()
    item = view["items"][0]
    assert item["note"] == "Lisbon" and item["uses"]["activity"] == "light" and item["days"] == 6 and view["settings"]["ramp_pct"] == 5.0
    assert client.post("/api/time-off", json={**body, "end": str(today)}, headers=MUTATE).status_code == 400
    assert client.post("/api/time-off", json={**body, "kind": "nap"}, headers=MUTATE).status_code == 422
    sick = client.post("/api/time-off", json={"kind": "sick", "start": str(today), "severity": 3}, headers=MUTATE).json()
    open_one = next(i for i in sick["items"] if i["kind"] == "sick")
    assert open_one["ongoing"] and open_one["uses"]["return_weeks"] == 3 and open_one["uses"]["return_start_pct"] == 35
    done = client.put(f"/api/time-off/{open_one['id']}", json={"kind": "sick", "start": str(today), "end": str(today), "severity": 1}, headers=MUTATE).json()
    assert next(i for i in done["items"] if i["id"] == open_one["id"])["ongoing"] is False
    saved = client.put("/api/settings/plan", json={"ramp_pct": 7, "away_activity": "none"}, headers=MUTATE).json()["settings"]
    assert saved["ramp_pct"] == 7 and saved["away_activity"] == "none" and saved["deload_pct"] == 65
    assert client.put("/api/settings/plan", json={"ramp_pct": 30}, headers=MUTATE).status_code == 400
    assert client.put("/api/settings/plan", json={"ramp_pct": None}, headers=MUTATE).json()["settings"]["ramp_pct"] == 5.0  # null resets
    assert client.delete(f"/api/time-off/{open_one['id']}", headers=MUTATE).status_code == 200
    assert client.delete(f"/api/time-off/{open_one['id']}", headers=MUTATE).status_code == 404


def test_trend_endpoints_and_home_status_on_demo_data(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    for kind in ("readiness", "score"):
        t = client.get(f"/api/trends/{kind}?days=28").json()
        assert t["has_data"] and t["n"] >= 10 and t["avg"] is not None and t["heading"]["text"] and len(t["buckets"]) >= 3
        assert sum(t["bands"].values()) == t["n"]
    status = client.get("/api/trends/training?weeks=12").json()
    assert status["has_data"] and status["current"]["status"] in status["statuses"] and status["n"] >= 4
    coach = client.get("/api/overview").json()["coach"]
    assert coach["status"]["label"] and "time_off" in coach["week"]
    client.post("/api/time-off", json={"kind": "sick", "start": str(clock.today() - timedelta(days=1))}, headers=MUTATE)
    paused = client.get("/api/overview").json()["coach"]
    assert paused["week"]["time_off"] is not None and paused["status"]["status"] in ("off", "returning", "maintaining", "progressing", "deloading", "overloading", "detraining")
