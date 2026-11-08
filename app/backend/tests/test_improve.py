"""Improve: drivers, rules, watch flags, focus, review, norms, wording and the API. Synthetic data only."""

import json
import random
import re
from datetime import date, timedelta

import numpy as np
import pytest

from cadence_app.analytics import athlete as A
from cadence_app.analytics import drivers as D
from cadence_app.analytics import focus as F
from cadence_app.analytics import focus_review as FR
from cadence_app.analytics import habits as H
from cadence_app.analytics import improve as IMP
from cadence_app.analytics import improve_rules as RL
from cadence_app.analytics import improve_sources as SRC
from cadence_app.analytics import improve_watch as W
from cadence_app.analytics import norms
from cadence_app.analytics import notes
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics.insights import assemble
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_recovery import D0, EASY, HARD, ZONES, act, days, steady_ctx

FORBIDDEN = re.compile(r"\bcaus(e|es|ed|ing)\b|because of|\bproves?\b|diagnos|RED-S|you should take|\byou (have|are)\b|overtrain|\bsick|will improve", re.I)
GREY = (0, 600, 3000, 0, 0)
ALC = [{"key": "alcohol", "label": "Alcohol", "kind": "count", "unit": "drinks", "active": True}]
SEEDS = {"hrv": 60.0, "rhr": 50.0}


def noise(n, sd, seed, ar=0.0):
    rng, x, out = random.Random(seed), 0.0, []
    for _ in range(n):
        x = ar * x + rng.gauss(0, sd)
        out.append(x)
    return out


def series(n=120, hrv=60.0, rhr=50.0, sleep=7.9, seed=1, **kw):
    ds = days(n)
    e = noise(n, 2.5, seed)
    out = {"hrv": {d: hrv + e[i] for i, d in enumerate(ds)}, "resting_hr": {d: rhr + e[(i * 7) % n] / 2.5 for i, d in enumerate(ds)},
           "sleep_hours": {d: sleep + e[(i * 3) % n] / 20 for i, d in enumerate(ds)}, "sleep_score": {d: 80.0 for d in ds}}
    out.update(kw)
    return ds, out


def weekly_acts(weeks, pattern, start_week=0, zones=EASY, load=80.0, moving_s=3600):
    """pattern: list of (weekday, zones) per week."""
    acts, i = [], 1000 * (start_week + 1)
    for w in range(start_week, weeks):
        for dd, z in pattern:
            i += 1
            acts.append(act(i, D0 + timedelta(days=7 * w + dd), z, load=load, moving_s=moving_s))
    return acts


def ctx(n=120, acts=None, ser=None, **kw):
    ds, s = series(n)
    s.update(ser or {})
    return assemble("demo", s, acts or [], ds[-1], zones=ZONES, **kw)


def drinks_ctx(nights, n=120, effect=-8.0, seed=3, behaviours=ALC):
    ds, s = series(n, seed=seed)
    rng = random.Random(seed)
    drink = set(rng.sample(range(5, n - 2), nights))
    answers = {"alcohol": {d: (2.0 if i in drink else 0.0) for i, d in enumerate(ds[:-1])}}
    for i in drink:
        s["hrv"][ds[i + 1]] += effect
    return assemble("demo", s, [], ds[-1], zones=ZONES, journal={"behaviours": behaviours, "answers": answers})


def texts(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("citations", "methods"):
                yield from texts(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from texts(v)


def clean(obj):
    bad = [t for t in texts(obj) if FORBIDDEN.search(t)]
    assert not bad, bad


# ---- citations ------------------------------------------------------------------------------------------------------


def test_sources_are_complete_and_verified_ones_have_a_link():
    for k, s in SRC.SOURCES.items():
        assert set(s) >= {"authors", "year", "title", "venue", "verified", "quality", "summary"} and isinstance(s["verified"], bool), k
        assert s["summary"] and s["quality"] != "", k
        if s["verified"] and k in cited_keys():
            assert s.get("doi") or s.get("url"), k  # a verified entry that rules cite must be checkable
    for k in ("seiler2006", "firstbeat2014", "liguori2021"):
        assert SRC.SOURCES[k]["verified"] is False and SRC.SOURCES[k]["summary"].startswith("Not verified")
    for old in ("manresa2021", "molina2022", "nes2011", "stein2012"):
        assert old not in SRC.SOURCES  # renamed or replaced after verification
    cm = SRC.citation_map(["seiler2010", "nope", "liguori2021"])
    assert list(cm) == ["seiler2010", "liguori2021"] and cm["seiler2010"]["short"] == "Seiler 2010" and cm["seiler2010"]["verified"] is True
    assert cm["seiler2010"]["doi"] and cm["seiler2010"]["summary"] and "doi" not in cm["liguori2021"] and cm["liguori2021"]["verified"] is False


def cited_keys() -> set[str]:
    import inspect

    src = inspect.getsource(RL) + inspect.getsource(W) + inspect.getsource(IMP) + inspect.getsource(norms)
    keys = set(re.findall(r'"([a-z]+(?:19|20)\d\d)"', src))
    return keys | {v for m in (IMP.METHODS.values()) for v in m} | set(norms.SOURCES.values())


def test_every_cited_key_exists():
    for key in cited_keys():
        assert key in SRC.SOURCES, key


def test_no_rule_or_flag_claims_hrv_guided_training_raises_vo2max_or_cites_removed_effects():
    import inspect

    from cadence_app.analytics import notes

    text = inspect.getsource(notes) + inspect.getsource(RL) + inspect.getsource(W)
    for k in ("kiviniemi2007", "vesterinen2016", "manresarocamora2021", "wisloff2007", "bacon2013", "midgley2006"):
        assert f'"{k}"' not in inspect.getsource(RL) + inspect.getsource(W), k
    for bad in ("+5 bpm", "5% VO2max", "within 5%", "Wisloff", "Bacon", "Midgley", "Kiviniemi", "Vesterinen", "Nes 2011", "Kaminsky 2015", "+1 mL/kg"):
        assert bad not in notes.improve_start.__code__.co_consts.__repr__() and bad not in inspect.getsource(notes.improve_start), bad
    assert "VO2max" in notes.IMPROVE_VO2 and "estimate" in notes.IMPROVE_VO2 and "wide individual error" in notes.IMPROVE_VO2
    assert text


# ---- drivers --------------------------------------------------------------------------------------------------------


def test_planted_alcohol_effect_is_recovered_with_a_range_that_holds_the_truth():
    c = drinks_ctx(14)
    rows = D.grade(D.candidate_effects("hrv", c["effects"], c["habits"]["effects"]))
    row = next(r for r in rows if r["id"] == "alcohol_hrv")
    assert row["grade"] == "clear" and row["q"] < 0.05 and row["lag_days"] == 1
    assert row["ci"][0] <= -8 <= row["ci"][1] and row["diff"] < -4
    assert row["n_exposed"] >= 8 and row["n_reference"] > 8 and "weekend" in row["adjusted_for"]


def test_null_data_rarely_yields_a_clear_driver_even_with_autocorrelated_noise():
    wrong = 0
    runs = 60
    for seed in range(runs):
        ds = days(100)
        e = noise(100, 3, seed, ar=0.5)
        hrv = {d: 60 + e[i] for i, d in enumerate(ds)}
        rng = random.Random(seed + 10_000)
        answers = {"alcohol": {d: float(rng.random() < 0.2) * 2 for d in ds}}
        cov = {"weekend": {d: float(d.weekday() >= 5) for d in ds}, "training load": {d: 0.0 for d in ds}}
        res = H.insights(ALC, answers, {"hrv": hrv}, cov)
        rows = D.grade(D.candidate_effects("hrv", [], res["effects"]))
        wrong += any(r["grade"] == "clear" for r in rows)
    assert wrong / runs <= 0.12


def test_missing_nights_are_skipped_not_zero_and_below_minimum_shows_progress():
    c = drinks_ctx(5)
    assert not [r for r in D.grade(D.candidate_effects("hrv", c["effects"], c["habits"]["effects"])) if r["id"] == "alcohol_hrv"]
    prog = D.progress(c["habits"]["progress"])
    assert prog == [{"key": "alcohol", "label": "Alcohol", "have": min(prog[0]["have"], 8), "needed": 8}] and prog[0]["have"] < 8
    ds = days(120)
    answers = {"alcohol": {d: (2.0 if i % 6 == 0 else 0.0) for i, d in enumerate(ds)}}
    hrv = {d: 60.0 + (i % 5) for i, d in enumerate(ds) if i % 3}  # a third of the nights have no value
    res = H.insights(ALC, answers, {"hrv": hrv}, {"weekend": {d: 0.0 for d in ds}})
    e = res["effects"][0]
    assert e.n_exposed + e.n_reference <= len(hrv)


def test_vo2max_weekly_drivers_need_twelve_weeks_and_six_readings():
    as_of = D0 + timedelta(days=200)
    few = [(D0 + timedelta(days=7 * i), 50.0) for i in range(4)]
    assert D.vo2_drivers(few, {}, as_of)["drivers"] == [] and D.vo2_drivers(few, {}, as_of)["tested"] == 0
    rng = random.Random(2)
    weeks = [D0 + timedelta(days=7 * i) for i in range(30)]
    hard = {w: float(rng.randint(0, 3)) for w in weeks}
    y, readings = 48.0, []
    for i, w in enumerate(weeks):
        if i:
            y += 0.4 * (hard[weeks[i - 1]] - 1.5) + rng.gauss(0, 0.1)
        readings.append((w + timedelta(days=2), y))
    ex = {"hard_sessions": {"label": "hard sessions", "cause": "Hard sessions", "weekly": hard}}
    res = D.vo2_drivers(readings, ex, weeks[-1] + timedelta(days=6))
    assert res["tested"] == 1
    if res["drivers"]:
        r = res["drivers"][0]
        assert r["unit"] == "mL/kg/min" and r["ci"][0] <= r["diff"] <= r["ci"][1] and r["grade"] in ("clear", "hint")


def test_baseline_and_trend_respect_minimums():
    ds = days(60)
    s = {d: 60.0 + (i % 5) for i, d in enumerate(ds)}
    b = D.baseline(s, ds[-1], "hrv")
    assert b["n"] == 60 and b["unit"] == "ms" and b["band"][0] < b["mean"] < b["band"][1] and b["n_7d"] == 7
    assert D.baseline({d: 60.0 for d in ds[:10]}, ds[9], "hrv") is None
    assert D.trend(s, ds[-1], "hrv")["direction"] == "steady"
    rising = {d: 50.0 + i * 0.3 + (i % 3) for i, d in enumerate(days(90))}
    t = D.trend(rising, days(90)[-1], "hrv")
    assert t["direction"] == "up" and t["ci"][0] > 0
    assert D.trend({d: 60.0 for d in ds[:20]}, ds[19], "hrv")["direction"] == "too_early"


# ---- rules: fires / below minimum / missing / wording ---------------------------------------------------------------


def rule_text(rule, c, metric="hrv"):
    d = {"metric": metric, "drivers": D.grade(D.candidate_effects(metric, c["effects"], c["habits"]["effects"]))}
    r = rule(c, d)
    return r, d


def check_rec(r, metric="hrv"):
    assert r["score"] == r["impact"] * r["confidence"] * r["ease"] and r["confidence"] in (1, 2, 3)
    assert all(k in SRC.SOURCES for k in r["citations"])
    clean(notes.improve_start(r, metric))


def test_easy_share_low():
    grey = weekly_acts(8, [(0, GREY), (2, GREY), (4, EASY), (6, GREY)])
    c = ctx(56, grey)
    r, _ = rule_text(RL.easy_share_low, c)
    assert r and r["numbers"]["easy_pct"] < 70 and r["numbers"]["sessions"] >= 6
    check_rec(r)
    assert RL.easy_share_low(ctx(56, weekly_acts(8, [(0, EASY), (2, EASY), (4, EASY), (6, EASY)])), {}) is None
    assert RL.easy_share_low(ctx(56, grey[-5:]), {}) is None  # fewer than 6 sessions in 28 days
    assert RL.easy_share_low(ctx(56, weekly_acts(8, [(0, ()), (2, ()), (4, ()), (6, ())])), {}) is None  # no zone data: unknown, not easy


def test_too_few_hard_and_too_many_hard():
    c = ctx(56, weekly_acts(8, [(0, EASY), (1, EASY), (3, EASY), (5, EASY)]))
    r, _ = rule_text(RL.too_few_hard, c, "vo2max")
    assert r and r["numbers"]["hard_sessions"] == 0 and r["planner_hint"] == {"add_key_session": "vo2"}
    check_rec(r, "vo2max")
    assert RL.too_few_hard(steady_ctx(8), {}) is None  # one hard session a week
    assert RL.too_few_hard(ctx(56, weekly_acts(8, [(0, EASY), (3, EASY)])), {}) is None  # fewer than 3 sessions a week
    ds, s = series(56)
    for d in ds[-7:]:
        s["hrv"][d] = 42.0
    hard = weekly_acts(8, [(0, HARD), (2, HARD), (4, HARD), (6, EASY)])
    c = assemble("demo", s, hard, ds[-1], zones=ZONES)
    r = RL.too_many_hard(c, {})
    assert r and r["numbers"]["hrv_7d"] < r["numbers"]["hrv_band_low"]
    check_rec(r)
    ds, s2 = series(56)
    assert RL.too_many_hard(assemble("demo", s2, hard, ds[-1], zones=ZONES), {}) is None  # HRV normal
    s3 = {k: v for k, v in s.items() if k != "hrv"}
    assert RL.too_many_hard(assemble("demo", s3, hard, ds[-1], zones=ZONES), {}) is None  # no HRV at all


def test_sleep_rule():
    ds, s = series(40, sleep=6.0)
    c = assemble("demo", s, [], ds[-1], zones=ZONES)
    r = RL.sleep_pattern_rule(c, {})
    assert r and r["numbers"]["short"]
    check_rec(r)
    _, ok = series(40, sleep=7.9)
    assert RL.sleep_pattern_rule(assemble("demo", ok, [], ds[-1], zones=ZONES), {}) is None
    few = {**s, "sleep_hours": {d: v for d, v in s["sleep_hours"].items() if d > ds[-1] - 5 * timedelta(days=1)}}
    assert RL.sleep_pattern_rule(assemble("demo", few, [], ds[-1], zones=ZONES), {}) is None
    erratic = {**ok, "bedtime": {d: float((i % 2) * 150 - 60) for i, d in enumerate(ds)}, "wake_time": {d: 420.0 for d in ds}}
    r = RL.sleep_pattern_rule(assemble("demo", erratic, [], ds[-1], zones=ZONES), {})
    assert r and r["numbers"]["erratic"]


def test_alcohol_rule():
    r, d = rule_text(RL.alcohol_nights, drinks_ctx(14))
    assert r and r["numbers"]["n_exposed"] >= 8 and r["numbers"]["diff"] < 0
    check_rec(r)
    assert RL.alcohol_nights(*[drinks_ctx(5), {"metric": "hrv", "drivers": []}]) is None
    c = ctx(80)  # no journal at all: missing is not "no drinks"
    assert RL.alcohol_nights(c, {"metric": "hrv", "drivers": []}) is None
    assert "alcohol (journal)" in IMP.build(ctx(80, journal={"behaviours": ALC, "answers": {}}), "hrv")["data"]["missing_signals"]  # said out loud, not read as zero


def test_habit_driver_rule_and_direction():
    row = {"_behaviour": "late_meal", "grade": "clear", "n_exposed": 10, "n_reference": 30, "diff": -5.0, "_higher_is_better": True, "_cause": "Late meal", "exposure": "Late meal",
           "reference": "No late meal", "unit": "ms", "ci": [-9.0, -1.0], "_outcome": "Overnight HRV"}
    r = RL.habit_driver({}, {"metric": "hrv", "drivers": [row]})
    assert r and r["id"] == "habit_late_meal"
    check_rec(r)
    assert RL.habit_driver({}, {"metric": "hrv", "drivers": [{**row, "diff": 5.0}]}) is None  # a favourable association is not a warning
    assert RL.habit_driver({}, {"metric": "hrv", "drivers": [{**row, "n_exposed": 7}]}) is None


def test_volume_fallen():
    pattern_hi, pattern_lo = [(0, EASY), (1, EASY), (3, EASY), (5, EASY), (6, EASY)], [(0, EASY)]
    acts = weekly_acts(4, pattern_hi) + weekly_acts(8, pattern_lo, start_week=4)
    c = ctx(56, acts)
    r = RL.volume_fallen(c, {})
    assert r and r["numbers"]["change_pct"] <= -20 and r["planner_hint"] == {"volume_bias": "up"}
    check_rec(r)
    assert RL.volume_fallen(steady_ctx(10), {}) is None
    assert RL.volume_fallen(ctx(40, weekly_acts(5, pattern_hi)), {}) is None  # under 8 complete weeks
    off = ctx(56, acts, time_off=[{"id": 1, "kind": "sick", "start": D0 + timedelta(days=30), "end": D0 + timedelta(days=36), "activity": None, "severity": 2,
                                   "return_weeks": None, "return_start_pct": None, "note": None}])
    assert RL.volume_fallen(off, {}) is None


def test_no_deload():
    rising = [(0, EASY), (2, EASY), (4, EASY), (6, EASY)]
    acts = []
    for w in range(9):
        for k, (dd, z) in enumerate(rising):
            acts.append(act(500 + w * 10 + k, D0 + timedelta(days=7 * w + dd), z, load=60 + 12 * w))
    c = ctx(63, acts)
    r = RL.no_deload(c, {})
    assert r and r["numbers"]["weeks_without_easier_week"] >= 5 and r["planner_hint"] == {"deload_week": True}
    check_rec(r)
    acts2 = [a if a.day < D0 + timedelta(days=7 * 5) or a.day >= D0 + timedelta(days=7 * 6) else act(a.id, a.day, EASY, load=20) for a in acts]
    r2 = RL.no_deload(ctx(63, acts2), {})
    assert r2 is None or r2["numbers"]["weeks_without_easier_week"] < 5
    assert RL.no_deload(ctx(30, acts[:8]), {}) is None


def test_long_gap_and_time_off_suppression():
    acts = weekly_acts(8, [(0, EASY), (2, EASY), (4, EASY)])
    last = max(a.day for a in acts)
    n = (last - D0).days + 11
    c = ctx(n, acts)
    r = RL.long_gap(c, {})
    assert r and r["numbers"]["days_without_training"] >= 7
    check_rec(r)
    assert RL.long_gap(ctx((last - D0).days + 5, acts), {}) is None
    assert RL.long_gap(ctx(n, []), {}) is None
    covered = ctx(n, acts, time_off=[{"id": 1, "kind": "travel", "start": last + timedelta(days=1), "end": last + timedelta(days=11), "activity": "none", "severity": None,
                                      "return_weeks": None, "return_start_pct": None, "note": None}])
    assert RL.long_gap(covered, {}) is None


def test_no_aerobic_base():
    short = (60, 120, 0, 0, 0)
    c = ctx(56, weekly_acts(8, [(0, short), (2, short), (4, short), (5, short)]))
    r = RL.no_aerobic_base(c, {})
    assert r and r["numbers"]["easy_minutes_per_week"] < 150 and r["tags"] == ["resting_hr"]
    check_rec(r, "resting_hr")
    assert RL.no_aerobic_base(steady_ctx(8), {}) is None
    assert RL.no_aerobic_base(ctx(56, weekly_acts(8, [(0, ()), (2, ()), (4, ()), (5, ())])), {}) is None  # unknown zones


def test_rules_run_filters_by_metric_and_orders_deterministically():
    c = ctx(56, weekly_acts(8, [(0, GREY), (2, GREY), (4, EASY), (6, GREY)]))
    d = {"metric": "hrv", "drivers": []}
    ids = [r["id"] for r in RL.run(c, d)]
    assert "easy_share_low" in ids and ids == [r["id"] for r in RL.run(c, d)]
    assert all("vo2max" in r["tags"] for r in RL.run(c, {"metric": "vo2max", "drivers": []}))


def test_vo2_context_notes():
    ds = days(100)
    weights = [(ds[-50 + i * 7], 80.0 - i * 0.6) for i in range(7)]
    c = ctx(100, [], weights=weights)
    notes_ = RL.context_notes(c, "vo2max")
    assert notes_ and notes_[0]["id"] == "vo2_weight"
    clean([notes.improve_context(n) for n in notes_])
    assert RL.context_notes(c, "hrv") == []
    assert RL.context_notes(ctx(100, [], weights=weights[:2]), "vo2max") == []


# ---- watch flags ----------------------------------------------------------------------------------------------------


def stress_series(n=70, hrv_drop=15.0, rhr_up=6.0, last=7):
    ds, s = series(n, seed=5)
    for d in ds[-last:]:
        s["hrv"][d] -= hrv_drop
        s["resting_hr"][d] += rhr_up
    return ds, s


def spike_acts(ds):
    return [act(900 + i, d, HARD, load=250.0) for i, d in enumerate(ds[-6:])] + [act(800 + i, d, EASY, load=40.0) for i, d in enumerate(ds[-34:-6:3])]


def test_overreach_pattern():
    ds, s = stress_series()
    c = assemble("demo", s, spike_acts(ds), ds[-1], zones=ZONES)
    f = W.overreach(c)
    assert f and f["severity"] == "look" and f["numbers"]["hrv_days_below_band"] >= 5 and f["numbers"]["rhr_delta"] >= 3
    clean(notes.improve_watch(f))
    c_feel = assemble("demo", s, spike_acts(ds), ds[-1], zones=ZONES, wellbeing={ds[-1]: {"feel": 1}})
    assert W.overreach(c_feel)["severity"] == "act"
    off = [{"id": 1, "kind": "travel", "start": ds[-5], "end": ds[-1], "activity": "none", "severity": None, "return_weeks": None, "return_start_pct": None, "note": None}]
    assert W.overreach(assemble("demo", s, spike_acts(ds), ds[-1], zones=ZONES, time_off=off)) is None
    no_rhr = {k: v for k, v in s.items() if k != "resting_hr"}
    assert W.overreach(assemble("demo", no_rhr, spike_acts(ds), ds[-1], zones=ZONES)) is None
    assert W.overreach(assemble("demo", s, [act(1, ds[-30], EASY)], ds[-1], zones=ZONES)) is None  # no load spike, no low feel
    ds2, s2 = stress_series(n=18)
    assert W.overreach(assemble("demo", s2, spike_acts(ds2), ds2[-1], zones=ZONES)) is None  # baseline under 14 nights


def test_illness_signature():
    ds, s = stress_series(hrv_drop=25.0, rhr_up=8.0, last=2)
    f = W.illness_signature(assemble("demo", s, [], ds[-1], zones=ZONES))
    assert f and f["severity"] == "act" and f["numbers"]["nights"] == 2
    text = notes.improve_watch(f)["suggestion"]
    assert "speak to a clinician" in text and "not medical advice" in text
    clean(notes.improve_watch(f))
    ds, s = stress_series(hrv_drop=25.0, rhr_up=8.0, last=1)
    assert W.illness_signature(assemble("demo", s, [], ds[-1], zones=ZONES)) is None  # one night is not enough
    f = W.illness_signature(assemble("demo", s, [], ds[-1], zones=ZONES, wellbeing={ds[-1]: {"illness": 1}}))
    assert f and f["numbers"]["run_down_logged"]
    clean(notes.improve_watch(f))


def test_sleep_debt_and_detraining():
    ds, s = series(40, seed=2)
    for d in ds[-4:]:
        s["sleep_hours"][d] = 5.5
    f = W.sleep_debt(assemble("demo", s, [], ds[-1], zones=ZONES))
    assert f and f["numbers"]["nights"] == 4
    clean(notes.improve_watch(f))
    del s["sleep_hours"][ds[-2]]  # a missing night breaks the run: unknown is not a short night
    assert W.sleep_debt(assemble("demo", s, [], ds[-1], zones=ZONES)) is None
    ds, s = series(60, seed=2)
    for d in ds[-7:]:
        s["resting_hr"][d] += 4
    acts = [act(i, d, EASY) for i, d in enumerate(ds[-40:-14:3])]
    f = W.detraining(assemble("demo", s, acts, ds[-1], zones=ZONES))
    assert f and f["numbers"]["days_without_aerobic"] >= 10
    clean(notes.improve_watch(f))
    _, flat = series(60, seed=2)
    assert W.detraining(assemble("demo", flat, acts, ds[-1], zones=ZONES)) is None


def test_every_template_passes_the_forbidden_word_scan():
    numbers = {
        "easy_share_low": dict(easy_pct=58, moderate_pct=30, target_pct=80, minutes=412, sessions=9, window_days=28),
        "too_few_hard": dict(hard_sessions=1, per_week=0.2, sessions=14, window_days=28),
        "too_many_hard": dict(hard_share_pct=40, hard_days_7d=3, sessions=10, hrv_7d=50, hrv_band_low=55, window_days=28),
        "sleep_pattern": dict(avg_hours=6.5, need_hours=8, nights=12, bedtime_sd_min=75, sri=60, short=True, erratic=True, window_days=14),
        "alcohol_nights": dict(diff=-7.4, unit="ms", ci=[-12.1, -2.7], n_exposed=9, n_reference=41, logged_days_28=10, outcome="Overnight HRV", window_days=28),
        "habit_late_meal": dict(cause="Late meal", exposure="Late meal", reference="No late meal", diff=-3.0, unit="ms", ci=[-6.0, -0.5], n_exposed=9, n_reference=30,
                                outcome="Overnight HRV", window_days=90),
        "volume_fallen": dict(minutes_per_week=120, previous_minutes_per_week=240, change_pct=-50, weeks=4, window_days=28),
        "no_deload": dict(weeks_without_easier_week=6, window_days=42),
        "long_gap": dict(days_without_training=9, window_days=9),
        "no_aerobic_base": dict(easy_minutes_per_week=90, sessions=8, window_days=28),
        "recover_first": {},
    }
    for rid, n in numbers.items():
        for metric in ("hrv", "resting_hr", "vo2max"):
            clean(notes.improve_start({"id": rid, "numbers": n, "timescale": "4-8 weeks"}, metric))
    for fid, n in {"overreach_pattern": dict(hrv_days_below_band=5, rhr_7d=56, rhr_delta=6, load_ratio=1.4, low_feel=True),
                   "illness_signature": dict(nights=2, rhr_delta=7, hrv_pct=-30, run_down_logged=True),
                   "sleep_debt": dict(nights=4, need_hours=8, avg_hours=5.5), "detraining": dict(days_without_aerobic=11, rhr_7d=55, rhr_delta=4)}.items():
        clean(notes.improve_watch({"id": fid, "numbers": n}))
    row = {"n_exposed": 9, "n_reference": 41, "exposure": "2+ drinks", "reference": "No drinks", "_outcome": "Overnight HRV", "diff": -7.4, "unit": "ms", "ci": [-12.1, -2.7]}
    clean(notes.improve_driver(row))
    for v in ("higher", "lower", "no_clear_change"):
        clean(notes.improve_review("hrv", {"enough": True, "verdict": v, "change": 4.1, "ci": [-1.0, 9.2], "unit": "ms", "window": {"n_before": 27, "n_after": 26}},
                                   {"load_change_pct": 12, "run_down_days": 2, "time_off_days": 3}))
    for st in ("unsupported", "collecting"):
        clean(notes.improve_message(st, "hrv", 3, 40))
    assert FORBIDDEN.search("this causes it") and FORBIDDEN.search("You are overtrained") and FORBIDDEN.search("risk of RED-S") and not FORBIDDEN.search("an association, not proof")


# ---- focus, planner hints, review, norms ----------------------------------------------------------------------------


def rec(rid, domain, score, hint=None):
    return {"id": rid, "domain": domain, "score": score, "numbers": {}, "planner_hint": hint or {}}


def test_focus_picks_top_three_distinct_domains_deterministically():
    recs = [rec("a", "sleep", 12), rec("b", "intensity", 18), rec("c", "intensity", 20), rec("d", "volume", 12), rec("e", "alcohol", 4), rec("f", "recovery", 8)]
    p = F.propose(recs, [], date(2026, 11, 8), "hrv")
    assert [q["_rule"] for q in p["priorities"]] == ["c", "a", "d"]  # a before d: equal score, id order
    assert p["start"] == date(2026, 11, 9) and p["check_on"] == date(2026, 12, 7) and p["proposed"] and p["blocked_by"] is None
    assert p == F.propose(list(reversed(recs)), [], date(2026, 11, 8), "hrv")
    assert F.propose([], [], date(2026, 11, 8), "hrv") is None


def test_act_watch_flag_overrides_to_recover_first():
    p = F.propose([rec("a", "sleep", 12), rec("b", "intensity", 9)], [{"id": "illness_signature", "severity": "act"}], date(2026, 11, 8), "hrv")
    assert len(p["priorities"]) == 1 and p["priorities"][0]["_rule"] == "recover_first" and p["blocked_by"] == "illness_signature"
    q = F.propose([rec("a", "sleep", 12)], [{"id": "sleep_debt", "severity": "look"}], date(2026, 11, 8), "hrv")
    assert q["priorities"][0]["_rule"] == "a"


@pytest.mark.parametrize("phase", ["build", "base", "recovery", "absorb", "maintain"])
@pytest.mark.parametrize("hints", [{"volume_bias": "up"}, {"add_key_session": "vo2"}, {"intensity_bias": "easier"}, {"deload_week": True},
                                   {"volume_bias": "up", "add_key_session": "vo2", "intensity_bias": "easier"}, {"volume_bias": "down", "deload_week": True}])
def test_planner_hints_never_raise_load_above_the_plan_caps(phase, hints):
    c = steady_ctx()
    ws = A.week_start(c["as_of"])
    c["_phase"] = {ws: {"phase": phase, "week_in_block": 2, "weeks_to_race": None, "label": phase.title(), "blurb": ""}}
    base = training_plan.weekly_plan(c)
    out = training_plan.weekly_plan(c, focus_hints=hints)
    assert out["targets"]["load"][0] <= base["targets"]["load"][0] and out["targets"]["load"][1] <= base["targets"]["load"][1]
    assert out["targets"]["sessions"] <= base["targets"]["sessions"] and out["targets"]["long_km_cap"] == base["targets"]["long_km_cap"]
    cap = 2 if phase == "build" and base["targets"]["sessions"] >= 4 else 1
    assert out["targets"]["hard"] <= max(base["targets"]["hard"], cap) and len(out["focus_applied"]) == len(hints)
    if phase in ("recovery", "absorb") and "add_key_session" in hints:
        assert next(n for n in out["focus_applied"] if n["hint"] == "add_key_session")["applied"] is False
    assert "focus_applied" not in base
    assert F.clean_hint({"add_key_session": "bogus", "deload_week": False, "x": 1}) == {}


def test_review_recovers_a_planted_step_and_reports_no_change_otherwise():
    start = date(2026, 6, 1)
    ds = [start + timedelta(days=i) for i in range(-28, 28)]
    e = noise(len(ds), 2.0, 4)
    step = {d: 60 + e[i] + (5.0 if d >= start else 0.0) for i, d in enumerate(ds)}
    r = FR.review("hrv", step, start, start + timedelta(days=28))
    assert r["verdict"] == "higher" and r["ci"][0] <= 5 <= r["ci"][1] and r["window"] == {"n_before": 28, "n_after": 28}
    null = {d: 60 + e[i] for i, d in enumerate(ds)}
    assert FR.review("hrv", null, start, start + timedelta(days=28))["verdict"] == "no_clear_change"
    assert FR.review("hrv", step, start, start + timedelta(days=10)) is None  # 28 days have not passed
    sparse = {d: v for i, (d, v) in enumerate(step.items()) if i % 4 == 0}
    s = FR.review("hrv", sparse, start, start + timedelta(days=28))
    assert s["enough"] is False and s["change"] is None
    assert FR.context({start + timedelta(days=1): 100.0, start - timedelta(days=1): 50.0}, {start + timedelta(days=2): {"illness": 1}}, 0, start)["run_down_days"] == 1


def test_norms_are_monotonic_and_missing_profile_hides_bands():
    table = {"vo2max": {"male": [(30, 39, [30.0, 37.0, 44.0], ["Poor", "Fair", "Good", "Excellent"])]}}
    assert norms.monotonic(table) and not norms.monotonic({"vo2max": {"male": [(30, 39, [40.0, 30.0], ["a", "b", "c"])]}})
    assert norms.band_for(table, "vo2max", "male", 35, 29.9) == "Poor" and norms.band_for(table, "vo2max", "male", 35, 36.9) == "Fair"
    assert norms.band_for(table, "vo2max", "male", 35, 37.0) == "Good"  # a cut point belongs to the band above it
    assert norms.band_for(table, "vo2max", "male", 35, 60) == "Excellent" and norms.band_for(table, "vo2max", "male", 50, 40) is None
    assert set(norms.TABLES) == {"resting_hr"} and norms.monotonic(norms.TABLES)  # VO2max/HRV not verifiable: absent, never invented
    b = norms.benchmarks({"hrv": {"mean": 60.0, "band": [55, 65]}, "resting_hr": None}, 47.0, None, None)
    assert b["profile_missing"] and b["vo2max"]["band"] is None and b["vo2max"]["estimate"] and "resting_hr" not in b and b["hrv"]["personal_band"] == [55, 65]
    ok = norms.benchmarks({}, 40.0, {"sex": "male"}, 35.0, table)
    assert ok["vo2max"]["band"] == "Good" and not ok["profile_missing"]


def test_resting_hr_norms_match_ostchega_2011():
    T = norms.TABLES
    # Table 2 (male 20-39): 10th 55, 25th 61, 75th 76, 90th 84; Table 3 (female 40-59): 10th 59, 25th 64, 75th 79, 90th 86
    assert norms.band_for(T, "resting_hr", "male", 30, 54) == "Below the 10th percentile"
    assert norms.band_for(T, "resting_hr", "male", 30, 55) == "10th to 25th percentile"
    assert norms.band_for(T, "resting_hr", "male", 30, 69) == "Middle half (25th to 75th)"
    assert norms.band_for(T, "resting_hr", "male", 39, 84) == "Above the 90th percentile"
    assert norms.band_for(T, "resting_hr", "female", 40, 78) == "Middle half (25th to 75th)"
    assert norms.band_for(T, "resting_hr", "female", 59, 79) == "75th to 90th percentile"
    assert norms.band_for(T, "resting_hr", "female", 95, 84) == "75th to 90th percentile" and norms.band_for(T, "resting_hr", "male", 19, 60) is None
    assert norms.band_for(T, "resting_hr", "other", 30, 60) is None and norms.band_for(T, "vo2max", "male", 30, 45) is None
    b = norms.benchmarks({"resting_hr": {"mean": 52.0, "band": [50, 54]}}, 45.0, {"sex": "male"}, 30.0)
    assert b["resting_hr"]["band"] == "Below the 10th percentile" and b["resting_hr"]["source"] == "ostchega2011" and "Context" in b["resting_hr"]["caveat"]
    assert b["vo2max"]["band"] is None and "estimate" in b["vo2max"]["caveat"] and b["vo2max"]["percentile"] is None
    for kw in ({"profile": None, "age": 30.0}, {"profile": {"sex": "male"}, "age": None}):
        m = norms.benchmarks({"resting_hr": {"mean": 52.0, "band": [50, 54]}}, 45.0, kw["profile"], kw["age"])
        assert m["profile_missing"] and m["resting_hr"]["band"] is None


# ---- payload --------------------------------------------------------------------------------------------------------

KEYS = {"metric", "as_of", "state", "message", "baseline", "trend", "data", "drivers", "progress", "start", "watch", "focus", "review", "benchmarks", "context", "methods", "citations"}


def test_payload_states_and_shape():
    c = drinks_ctx(14)
    p = IMP.public(IMP.build(c, "hrv"))
    assert set(p) == KEYS and p["state"] == "ready" and p["baseline"]["unit"] == "ms" and p["baseline"]["n"] >= 40
    assert {r["id"] for r in p["drivers"]} >= {"alcohol_hrv"} and all(r["grade"] in ("clear", "hint") for r in p["drivers"])
    assert p["focus"] is None or (p["focus"]["proposed"] and "_internal" not in p["focus"])
    assert all(k in p["citations"] for r in p["start"] for k in r["citations"]) and all(isinstance(v["verified"], bool) and v["summary"] for v in p["citations"].values())
    clean(p)
    json.dumps(p, default=str)
    collecting = IMP.build(ctx(20), "hrv")
    assert collecting["state"] == "collecting" and collecting["start"] == [] and collecting["drivers"] == [] and collecting["focus"] is None
    assert collecting["progress"][0]["have"] == 20 and collecting["progress"][0]["needed"] == 40
    unsupported = IMP.build(ctx(60), "vo2max")
    assert unsupported["state"] == "unsupported" and unsupported["baseline"] is None and unsupported["message"]
    clean(collecting)
    clean(unsupported)


def test_ready_payload_has_start_focus_and_a_review_of_the_last_focus():
    acts = weekly_acts(12, [(0, GREY), (2, GREY), (4, EASY), (6, GREY)])
    c = ctx(84, acts)
    p = IMP.build(c, "hrv")
    assert p["state"] == "ready" and any(r["id"] == "easy_share_low" for r in p["start"])
    top = p["start"][0]
    assert set(top) == {"id", "finding", "numbers", "why", "citations", "action", "timescale", "impact", "confidence", "ease", "score", "tags"}
    assert p["focus"]["proposed"] and p["focus"]["priorities"][0]["planner_hint"]
    assert set(p["focus"]["priorities"][0]) == {"rank", "title", "behaviour", "target_metrics", "planner_hint"}
    clean(p)
    start = c["as_of"] - timedelta(days=30)
    row = {"id": 3, "metric": "hrv", "start": start, "end": start + timedelta(days=28), "priorities": p["focus"]["priorities"], "baseline": {}, "status": "active"}
    q = IMP.build(c, "hrv", [row])
    assert q["review"]["focus_id"] == 3 and q["review"]["verdict"] in ("higher", "lower", "no_clear_change") and q["review"]["window"]["n_after"] >= 14
    assert q["focus"]["proposed"] is True  # past its check date, a new one is proposed
    row2 = {**row, "start": c["as_of"] - timedelta(days=5), "end": c["as_of"] + timedelta(days=23)}
    r2 = IMP.build(c, "hrv", [row2])
    assert r2["focus"]["id"] == 3 and r2["focus"]["proposed"] is False and r2["review"] is None
    clean(q)


def test_summary_shape():
    s = IMP.summary(ctx(84, weekly_acts(12, [(0, GREY), (2, GREY), (4, EASY), (6, GREY)])))
    assert set(s) == {"as_of", "state", "focus", "watch"} and s["state"] == "ready"
    assert set(s["focus"]) == {"check_on", "metric", "priority"} and set(s["focus"]["priority"]) == {"title", "behaviour", "target_metrics"}
    assert IMP.summary(ctx(10))["state"] == "collecting"


# ---- API ------------------------------------------------------------------------------------------------------------


def test_api_endpoints_states_accept_dismiss_and_read_only_phone(env):  # noqa: F811
    client, clock = env
    assert client.get("/api/improve/hrv").json()["state"] == "unsupported"
    assert client.get("/api/improve").json()["state"] == "unsupported"
    assert client.get("/api/improve/bogus").status_code == 422
    assert client.post("/api/sync/demo", headers=MUTATE).status_code == 200
    for m in ("hrv", "resting_hr", "vo2max"):
        p = client.get(f"/api/improve/{m}").json()
        assert p["metric"] == m and p["state"] in ("ready", "collecting", "unsupported") and set(p) >= KEYS - {"context"}
        clean(p)
    s = client.get("/api/improve").json()
    assert set(s) >= {"as_of", "state", "focus", "watch"}
    assert client.post("/api/focus", json={"metric": "hrv"}).status_code == 403  # needs the custom header
    r = client.post("/api/focus", json={"metric": "hrv"}, headers=MUTATE)
    assert r.status_code in (200, 409)
    if r.status_code == 200:
        fid = r.json()["id"]
        assert client.get("/api/improve/hrv").json()["focus"]["id"] == fid
        assert client.post(f"/api/focus/{fid}/dismiss", headers=MUTATE).json()["status"] == "dismissed"
    assert client.post("/api/focus/999/dismiss", headers=MUTATE).status_code == 404


def test_focus_store_round_trip_and_phone_is_read_only(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from cadence_app import focus_store
    from cadence_app.models import Base
    from cadence_app.share import phone_may_write

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as ses:
        now = __import__("datetime").datetime(2026, 11, 8, 9)
        a = focus_store.accept(ses, "hrv", date(2026, 11, 9), date(2026, 12, 7), [{"rank": 1, "title": "t", "behaviour": "b", "target_metrics": ["hrv"], "planner_hint": {}}], {"mean": 60}, now)
        b = focus_store.accept(ses, "hrv", date(2026, 11, 10), date(2026, 12, 8), [{"rank": 1}], None, now)
        rows = {r["id"]: r for r in focus_store.rows(ses)}
        assert rows[a["id"]]["status"] == "completed" and rows[b["id"]]["status"] == "active"
        with pytest.raises(focus_store.FocusError):
            focus_store.accept(ses, "hrv", date(2026, 11, 9), date(2026, 12, 7), [], None, now)
    assert not phone_may_write("POST", "/api/focus") and not phone_may_write("POST", "/api/focus/3/dismiss")
