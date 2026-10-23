from datetime import date, datetime, timedelta

import pytest

from cadence_app.analytics import athlete as A
from cadence_app.analytics.insights import coach, recommend

D0 = date(2026, 1, 1)


def act(day: date, load: float, family: str = "run", zones=(0, 3000, 0, 0, 0), **kw) -> A.Act:
    start = datetime.combine(day, datetime.min.time()).replace(hour=7)
    return A.Act(
        id=kw.pop("id", day.toordinal()), day=day, start_local=start, end_local=start + timedelta(hours=1),
        family=family, type=family, name="x", load=load, distance_m=kw.pop("distance_m", 10000),
        moving_s=kw.pop("moving_s", 3600), avg_hr=kw.pop("avg_hr", 150), speed_mps=kw.pop("speed_mps", 2.8),
        zones_s=zones, **kw,
    )


def test_pmc_converges_to_steady_load_and_flags_spikes():
    days = [D0 + timedelta(days=i) for i in range(240)]
    load = {d: 100.0 for d in days}
    p = A.pmc(load, days[0], days[-1])
    assert p[-1]["fitness"] == pytest.approx(100, abs=1)
    assert p[-1]["fatigue"] == pytest.approx(100, abs=0.1)
    assert abs(p[-1]["form"]) < 1 and p[-1]["acwr"] == pytest.approx(1.0, abs=0.01)

    for i in range(5):
        load[days[-1] + timedelta(days=i + 1)] = 350.0
    spiked = A.pmc(load, days[0], days[-1] + timedelta(days=5))
    assert spiked[-1]["acwr"] > 1.5 and spiked[-1]["form"] < 0


def test_weekly_monotony_and_rest_days():
    week = [D0 + timedelta(days=i) for i in range(7)]  # 2026-01-01 is a Thursday; use a full Mon-Sun week
    monday = A.week_start(D0) + timedelta(days=7)
    acts = [act(monday + timedelta(days=i), 100) for i in range(7)]
    load = A.daily_load(acts)
    w = A.weekly(acts, load, monday, monday + timedelta(days=6))[-1]
    assert w["rest_days"] == 0 and w["monotony"] is None  # identical days: SD 0, infinite monotony
    acts = [act(monday + timedelta(days=i), 100 if i % 2 else 0) for i in range(7)]
    w = A.weekly(acts, A.daily_load(acts), monday, monday + timedelta(days=6))[-1]
    assert w["rest_days"] == 4 and w["monotony"] == pytest.approx(0.87, abs=0.01)
    assert w["easy_pct"] == 100 and len(week) == 7


def test_intensity_split_counts_endurance_only():
    acts = [
        act(D0, 50, zones=(600, 1800, 1200, 600, 0)),
        act(D0, 50, family="strength", zones=(0, 0, 0, 9999, 0)),
    ]
    s = A.intensity_split(acts, D0)
    assert (s["easy_pct"], s["moderate_pct"], s["hard_pct"]) == (57, 29, 14)


def test_readiness_scores_a_normal_day_around_80_and_penalises_low_signals():
    days = [D0 + timedelta(days=i) for i in range(30)]
    series = {
        "hrv": {d: 50.0 + (i % 3) for i, d in enumerate(days)},
        "hrv_balanced_low": {d: 45.0 for d in days}, "hrv_balanced_high": {d: 58.0 for d in days},
        "resting_hr": {d: 50.0 + (i % 2) for i, d in enumerate(days)},
        "sleep_score": {d: 82.0 for d in days}, "sleep_hours": {d: 7.3 for d in days}, "body_battery": {d: 90.0 for d in days},
    }
    assert A.readiness(days[2], {"hrv": series["hrv"]}, {}) is None
    normal = A.readiness(days[-1], series, {})
    assert 75 <= normal["score"] <= 90 and normal["label"] == "ready"
    # 1 bpm above a very stable baseline must not tank the score.
    assert normal["components"]["rhr"]["score"] >= 70
    bad = {**series, "hrv": {**series["hrv"], days[-1]: 34.0}, "resting_hr": {**series["resting_hr"], days[-1]: 58.0},
           "sleep_score": {**series["sleep_score"], days[-1]: 45.0}, "body_battery": {**series["body_battery"], days[-1]: 40.0}}
    low = A.readiness(days[-1], bad, {})
    assert low["score"] < 50 and low["label"] == "recover"
    assert set(normal["components"]) == {"sleep", "sleep_history", "hrv", "rhr", "battery"}


def test_live_readiness_dips_after_training_and_recovers():
    days = [D0 + timedelta(days=i) for i in range(30)]
    series = {
        "hrv": {d: 50.0 for d in days}, "hrv_balanced_low": {d: 45.0 for d in days}, "hrv_balanced_high": {d: 58.0 for d in days},
        "resting_hr": {d: 50.0 + (i % 2) for i, d in enumerate(days)}, "sleep_score": {d: 85.0 for d in days},
        "sleep_hours": {d: 7.8 for d in days}, "body_battery": {d: 92.0 for d in days},
    }
    pmc_day = {days[-1]: {"day": days[-1], "load": 0, "fitness": 60.0, "fatigue": 55.0, "form": 3.0, "acwr": 1.0}}
    morning = A.readiness(days[-1], series, pmc_day)
    session = act(days[-1], 150, id=7)  # ends 08:00
    at = lambda h: datetime.combine(days[-1], datetime.min.time()).replace(hour=h)  # noqa: E731
    before = A.live_readiness(morning, 92, [session], 60, at(7))
    right_after = A.live_readiness(morning, 70, [session], 60, at(9))
    evening = A.live_readiness(morning, 70, [session], 60, at(22))
    assert before["score"] == morning["score"] and before["changes"] == []
    assert right_after["score"] < morning["score"] - 5 and any("h ago" in c["label"] for c in right_after["changes"])
    assert right_after["score"] < evening["score"] <= morning["score"]
    assert right_after["morning_score"] == morning["score"] and right_after["live"]


def test_decoupling_detects_cardiac_drift():
    t = list(range(0, 3600, 5))
    speed = [3.0] * len(t)
    hr = [140 if s < 2100 else 154 for s in t]  # +10% HR in the second half at the same pace
    r = A.decoupling({"t": t, "speed": speed, "heart_rate": hr})
    assert r["steady"] and r["decoupling_pct"] == pytest.approx(9.0, abs=1.5)
    assert A.decoupling({"t": t[:200], "speed": speed[:200], "heart_rate": hr[:200]}) is None


def test_efficiency_trend_detects_improvement():
    runs = [act(D0 + timedelta(days=i * 4), 80, speed_mps=2.6 + i * 0.01, avg_hr=150) for i in range(30)]
    eff = A.efficiency(runs)
    t = A.efficiency_trend(eff, 150, runs[-1].day)
    assert t["significant"] and t["change_pct_90d"] > 5
    assert t["pace_now_s"] < t["pace_90d_ago_s"]


def test_compare_finds_real_effect_and_rejects_small_samples():
    days = [D0 + timedelta(days=i) for i in range(120)]
    hard = {d for i, d in enumerate(days) if i % 3 == 0}
    rest = set(days) - hard
    hrv = {d + timedelta(days=1): (45.0 if d in hard else 55.0) + (i % 4) for i, d in enumerate(days)}
    e = A.compare("x", "Load", "HRV", "hard", "rest", hard, rest, hrv, 1, "ms", True)
    assert e.significant and e.diff == pytest.approx(-10, abs=1)
    assert A.compare("x", "Load", "HRV", "hard", "rest", set(days[:3]), rest, hrv, 1, "ms", True) is None


def ctx(**over):
    base = {
        "as_of": D0 + timedelta(days=200), "acts": [], "series": {}, "pmc": [], "weeks": [], "split_28": None,
        "eff_trend": None, "durability": [], "sleep_14": None, "vo2": [], "load": {}, "weigh_ins_60d": 10,
        "strength_labelled": None,
    }
    base.update(over)
    return base


def test_coach_rules_fire_on_evidence():
    spike = [{"day": D0, "load": 300, "fitness": 60, "fatigue": 140, "form": -40, "acwr": 1.7}]
    ids = {f["id"]: f["severity"] for f in coach(ctx(pmc=spike, split_28={"easy_pct": 55, "moderate_pct": 30, "hard_pct": 15, "zones_min": [], "minutes": 600}))}
    # Acute:chronic alone is a weak injury predictor: a warning, escalated only when running volume spikes too.
    assert ids["acwr"] == "warn" and ids["intensity"] == "warn" and ids["form"] == "warn"
    run_spike = {"acwr": 1.8, "km_7d": 60, "km_week_avg_28d": 30}
    ids = {f["id"]: f["severity"] for f in coach(ctx(pmc=spike, run_load=run_spike))}
    assert ids["acwr"] == "alert" and ids["run_load"] == "warn"
    as_of = D0 + timedelta(days=200)
    every_day = {as_of - timedelta(days=i): 80.0 for i in range(14)}
    assert "rest" not in {f["id"] for f in coach(ctx())}
    assert {f["id"]: f["severity"] for f in coach(ctx(load=every_day))}["rest"] == "warn"

    sleep = {"nights": 14, "avg_hours": 6.2, "need_hours": 8.0, "nights_short": 11, "debt_hours": 12, "avg_bedtime_min": 45, "bedtime_sd_min": 80, "avg_wake_min": 420, "wake_sd_min": 30}
    ids = {f["id"] for f in coach(ctx(sleep_14=sleep, weigh_ins_60d=1, strength_labelled={"sessions": 20, "labelled": 0}))}
    assert {"sleep", "bedtime", "weight_data", "strength_data"} <= ids


def test_recommendation_respects_load_spike():
    r = {"score": 88, "components": {"hrv": {"score": 80}}}
    assert recommend(r, {"acwr": 1.2}, 0)["headline"] == "Go hard"
    assert recommend(r, {"acwr": 1.7}, 0)["headline"] == "Easy day"
    assert recommend({"score": 78, "components": {}}, None, 0)["headline"] == "Train as planned"
    assert recommend({"score": 40, "components": {}}, None, 0)["headline"] == "Recover"
