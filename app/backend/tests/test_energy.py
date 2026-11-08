"""Energy balance: projection, target, settings, snapshots and wording. Synthetic data only."""

import re
from datetime import date, datetime, timedelta, timezone

import pytest

from cadence_app import energy_store
from cadence_app.analytics import energy as E
from cadence_app.analytics import notes
from cadence_app.models import DailyMetric, EnergySnapshot, Source
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)

TODAY = date(2026, 10, 22)
SHAME = re.compile(r"burn (it )?off|\bearn(ed|s)?\b|cheat|over budget|\bfail|\bmiss(ed)?\b|should have|lazy|behind|\bcaus(e|es|ed)\b|because of|diagnos|\bsick\b|guilt|deserve", re.I)


def finals(n, total=2400.0, active=600.0, jitter=0):
    return {TODAY - timedelta(days=i): (total + (i % 3 - 1) * jitter, active) for i in range(1, n + 1)}


def curve_snaps(fs, minute, share, wobble=0.02):
    """Every settled day has a snapshot at `minute` holding `share` of its final total (a planted curve)."""
    return {d: [(minute + (i % 3) * 5, t * (share + ((i % 5) - 2) * wobble / 2))] for i, (d, (t, _)) in enumerate(fs.items())}


def block(**kw):
    base = dict(today=TODAY, now_min=14 * 60, burn={"total": 1500.0, "active": 400.0, "as_of_min": 14 * 60}, finals=finals(20), snapshots={}, food={}, workouts=[], settings=None)
    base.update(kw)
    return E.assemble(**base)


# ---- projection --------------------------------------------------------------------------------------------------


def test_curve_recovers_a_planted_fraction_with_an_ordered_range_and_sample_size():
    fs = finals(14, jitter=40)
    snaps = curve_snaps(fs, 14 * 60, 0.62)
    p = E.project_burn(14 * 60, 14 * 60, 1500.0, 400.0, fs, snaps, TODAY)
    assert p["status"] == "ok" and p["method"] == "curve" and p["n"] == 14
    assert abs(p["value"] - 1500 / 0.62) / (1500 / 0.62) < 0.03
    assert p["lo"] <= p["value"] <= p["hi"] and p["lo"] >= 1500


def test_curve_needs_ten_days_near_this_time():
    fs = finals(14)
    snaps = {d: v for i, (d, v) in enumerate(curve_snaps(fs, 14 * 60, 0.6).items()) if i < 9}  # nine days: fall back
    p = E.project_burn(14 * 60, 14 * 60, 1500.0, 400.0, fs, snaps, TODAY)
    assert p["method"] == "fallback" and p["status"] == "partial"
    far = curve_snaps(fs, 9 * 60, 0.3)  # snapshots all from another time of day do not count
    assert E.project_burn(14 * 60, 14 * 60, 1500.0, 400.0, fs, far, TODAY)["method"] == "fallback"


def test_fallback_at_eight_days_is_labelled_rough_and_time_aware():
    fs = finals(8, jitter=30)
    noon = E.project_burn(12 * 60, 12 * 60, 1200.0, 300.0, fs, {}, TODAY)
    evening = E.project_burn(20 * 60, 20 * 60, 2100.0, 500.0, fs, {}, TODAY)
    assert noon["status"] == "partial" and noon["method"] == "fallback" and noon["n"] == 8
    assert noon["lo"] <= noon["value"] <= noon["hi"]
    assert noon["value"] > 1200 and evening["value"] < noon["value"] + 1500
    assert 2100 <= evening["value"] <= 2510  # little is left in the evening


def test_insufficient_below_a_week_and_missing_burn_is_not_zero():
    p = E.project_burn(14 * 60, 14 * 60, 1500.0, 400.0, finals(6), {}, TODAY)
    assert p["status"] == "insufficient" and p["value"] is None and p["n"] == 6
    assert E.project_burn(14 * 60, 14 * 60, 0, 0, finals(20), {}, TODAY)["status"] == "no_burn"
    assert E.project_burn(14 * 60, 14 * 60, None, None, finals(20), {}, TODAY)["status"] == "no_burn"


def test_late_evening_range_collapses_and_hides_after_23():
    fs = finals(14)
    snaps = curve_snaps(fs, 21 * 60 + 30, 0.97, wobble=0.04)
    late = E.project_burn(21 * 60 + 30, 21 * 60 + 30, 2350.0, 600.0, fs, snaps, TODAY)
    assert late["status"] == "ok" and late["hi"] - late["lo"] <= 0.11 * 2350 + 1
    assert E.project_burn(23 * 60 + 10, 23 * 60 + 10, 2380.0, 600.0, fs, snaps, TODAY)["status"] == "hidden"


def test_garmin_zero_days_are_missing_not_zero_in_history():
    fs = finals(10)
    fs[TODAY - timedelta(days=3)] = (0.0, 0.0)
    assert len(E.settled(fs, TODAY)) == 9


# ---- target --------------------------------------------------------------------------------------------------------


def test_target_from_history_trims_outlier_days():
    fs = finals(24)
    for i in (2, 9, 15):
        fs[TODAY - timedelta(days=i)] = (4500.0, 2700.0)  # a race or a long hike
    t = E.derive_target(E.settled(fs, TODAY), E.clean_settings(None))
    assert t["source"] == "history" and t["kcal"] == 2400 and t["n_days"] == 21


def test_target_needs_two_weeks_else_formula_else_none():
    rows = E.settled(finals(10), TODAY)
    assert E.derive_target(rows, E.clean_settings(None)) is None
    prof = {"sex": "male", "height_cm": 180.0, "age_years": 35.0}
    t = E.derive_target(rows, E.clean_settings(None), profile=prof, weight_kg=75.0)
    assert t["source"] == "formula" and 2200 < t["kcal"] < 2800 and t["n_days"] == 0


def test_pace_is_clamped_to_half_a_percent_of_body_weight_per_week():
    rows = E.settled(finals(24), TODAY)
    t = E.derive_target(rows, E.clean_settings(None), weight_kg=80.0, pace={"target_kg": 70.0, "days_left": 10})
    assert t["pace"]["state"] == "gentle" and abs(t["pace"]["kg_per_week"]) <= 0.4 + 1e-9 and t["adjustment_kcal"] < 0
    assert abs(t["adjustment_kcal"]) <= 0.15 * 2400 and t["pace"]["weeks_at_gentle_pace"] >= 20
    gain = E.derive_target(rows, E.clean_settings(None), weight_kg=60.0, pace={"target_kg": 62.0, "days_left": 70})
    assert gain["adjustment_kcal"] > 0 and gain["pace"]["state"] == "on_pace"
    reached = E.derive_target(rows, E.clean_settings(None), weight_kg=70.1, pace={"target_kg": 70.0, "days_left": 70})
    assert reached["adjustment_kcal"] == 0 and reached["pace"]["state"] == "at_goal"


def test_no_adjustment_while_held_or_pace_turned_off():
    rows = E.settled(finals(24), TODAY)
    for hold in ("time_off", "unwell", "hard_block"):
        t = E.derive_target(rows, E.clean_settings(None), weight_kg=80.0, pace={"target_kg": 70.0, "days_left": 100}, hold=hold)
        assert t["adjustment_kcal"] == 0 and t["hold"] == hold and t["kcal"] == 2400
    off = E.derive_target(rows, E.clean_settings({"pace": False}), weight_kg=80.0, pace={"target_kg": 70.0, "days_left": 100})
    assert off["adjustment_kcal"] == 0 and off["pace"] is None


def test_floor_applies_to_auto_and_only_warns_for_manual():
    rows = E.settled(finals(24, total=1700.0, active=100.0), TODAY)  # resting ~1600 -> floor 1760
    t = E.derive_target(rows, E.clean_settings(None), weight_kg=90.0, pace={"target_kg": 60.0, "days_left": 30})
    assert t["floor_applied"] and t["kcal"] == t["floor_kcal"] == 1760
    m = E.derive_target(rows, E.clean_settings({"mode": "manual", "manual_kcal": 1400}))
    assert m["kcal"] == 1400 and m["source"] == "manual" and m["below_floor"] and not m["floor_applied"]
    assert E.derive_target([], E.clean_settings({"mode": "manual", "manual_kcal": 2000}))["kcal"] == 2000


def test_settings_are_clamped_on_read_and_strict_on_write():
    assert E.clean_settings({"mode": "manual"})["mode"] == "auto"  # manual without a number is unusable
    assert E.clean_settings({"manual_kcal": 50, "eat_back_pct": 500, "pace": "yes"}) == E.DEFAULT_SETTINGS
    for bad in ({"manual_kcal": 100}, {"manual_kcal": 9000}, {"eat_back_pct": 101}, {"mode": "other"}):
        with pytest.raises(ValueError):
            E.validate_settings(bad)


# ---- balance -----------------------------------------------------------------------------------------------------


def test_empty_food_log_is_not_zero_and_gives_no_left_or_balance():
    b = block()
    assert b["eaten"] == {"kcal": None, "kcal_low": None, "kcal_high": None, "logged": False, "entries": 0, "protein_g": None}
    assert b["left"] is None and b["above_by"] is None and b["balance"] is None
    assert notes.energy_copy(b, 14 * 60)["eaten"] == "Nothing logged yet" and notes.energy_copy(b, 14 * 60)["left"] is None


def test_left_is_never_negative_and_above_is_stated_flatly():
    food = {TODAY: {"logged": True, "entries": 4, "kcal": 1000, "kcal_low": 900, "kcal_high": 1100, "protein_g": 60.0}}
    b = block(food=food)
    assert b["left"] == 1400 and b["above_by"] is None and b["balance"] == {"so_far_kcal": -500}
    food[TODAY]["kcal"] = 2580
    over = block(food=food)
    assert over["left"] is None and over["above_by"] == 180
    text = notes.energy_copy(over, 20 * 60)["left"]
    assert "180" in text and "does not matter" in text and not SHAME.search(text)


def test_workout_burn_adds_a_share_to_the_target():
    food = {TODAY: {"logged": True, "entries": 3, "kcal": 1200, "kcal_low": 1, "kcal_high": 2, "protein_g": None}}
    b = block(food=food, workouts=[{"name": "Run", "kcal": 420.0}], settings={"eat_back_pct": 50})
    assert b["workout_active_kcal"] == 420 and b["eat_back_kcal"] == 210 and b["left"] == 2400 + 210 - 1200
    none = block(food=food, workouts=[{"name": "Run", "kcal": 420.0}], settings={"eat_back_pct": 0})
    assert none["eat_back_kcal"] == 0 and none["left"] == 1200
    assert block(workouts=[{"name": "x", "kcal": None}])["workout_active_kcal"] is None


def test_midnight_rollover_and_garmin_zero_are_not_a_burn():
    b = block(now_min=5, burn={"total": 2350.0, "active": 500.0, "as_of_min": 5})
    assert b["status"] == "just_started" and b["burned"] is None and b["projected"] is None and b["yesterday"]["total"] == 2400
    assert "just started" in notes.energy_copy(b, 5)["status"]
    z = block(burn={"total": 0.0, "active": 0.0, "as_of_min": 14 * 60})
    assert z["status"] == "no_garmin_kcal" and z["burned"] is None and z["balance"] is None
    assert block(burn=None)["status"] == "no_garmin_kcal"


def test_status_levels_and_payload_shape():
    fs = finals(14)
    ok = block(finals=fs, snapshots=curve_snaps(fs, 14 * 60, 0.62))
    assert ok["status"] == "ok" and ok["projected"]["method"] == "curve" and ok["projection_history_days"] == 14
    assert block(finals=finals(8))["status"] == "partial"
    assert block(finals=finals(5))["status"] == "insufficient"
    assert len(ok["spark"]) == 14 and ok["spark"][-1]["partial"] and ok["burned"]["resting"] == 1100
    assert set(ok) >= {"status", "day", "as_of_min", "as_of", "burned", "eaten", "projected", "target", "left", "workout_active_kcal", "eat_back_pct", "balance", "spark"}


# ---- wording -----------------------------------------------------------------------------------------------------


def _texts(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _texts(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _texts(v)


def test_energy_wording_passes_the_forbidden_word_scan_in_every_state():
    fs = finals(24)
    food = {TODAY: {"logged": True, "entries": 1, "kcal": 3300, "kcal_low": 3000, "kcal_high": 3600, "protein_g": 80.0}}
    cases = [block(), block(food=food), block(finals=fs, snapshots=curve_snaps(fs, 14 * 60, 0.62)), block(finals=finals(8)), block(finals=finals(3)),
             block(burn=None), block(now_min=3), block(workouts=[{"name": "Run", "kcal": 600.0}], food=food),
             block(settings={"mode": "manual", "manual_kcal": 1200}, finals=finals(24, total=1700.0, active=100.0)),
             block(weight_kg=80.0, pace={"target_kg": 70.0, "days_left": 10}, hold="unwell"), block(weight_kg=80.0, pace={"target_kg": 70.0, "days_left": 10})]
    for b in cases:
        text = notes.energy_copy(b, 19 * 60)
        for t in _texts(text):
            assert not SHAME.search(t), t
    assert any("estimate" in t for t in _texts(notes.energy_copy(cases[0], 14 * 60)))
    assert "estimates" in notes.ENERGY_FOOTNOTE


# ---- snapshots, settings and the API ------------------------------------------------------------------------------


def test_record_snapshot_stamps_import_time_skips_stale_and_throttles(tmp_path):
    from cadence_app.db import make_engine, make_session_factory, upgrade_database

    url = f"sqlite:///{tmp_path / 'v.db'}"
    upgrade_database(url)
    with make_session_factory(make_engine(url))() as s:
        today = energy_store.localtime.today_in(None)
        s.add(Source(id="garmin", name="g", kind="garmin"))
        s.commit()
        at = datetime.now(timezone.utc).replace(tzinfo=None)
        s.add_all([DailyMetric(source_id="garmin", day=today, metric="total_calories", value=1500.0, unit="kcal", imported_at=at),
                   DailyMetric(source_id="garmin", day=today, metric="active_calories", value=300.0, unit="kcal", imported_at=at)])
        s.commit()
        local = energy_store._local(at, None)  # noqa: SLF001
        if local.date() != today:
            pytest.skip("clock rolled over during the test")
        assert energy_store.record_snapshot(s, "garmin", None) is True
        assert energy_store.record_snapshot(s, "garmin", None) is False  # unchanged / too soon
        row = s.query(EnergySnapshot).one()
        assert row.total_kcal == 1500.0 and row.active_kcal == 300.0 and row.taken_at_local_min == local.hour * 60 + local.minute
        s.query(EnergySnapshot).delete()
        for m in s.query(DailyMetric):
            m.imported_at = at - timedelta(days=2)  # fetched on another day: not a reading from today
        s.commit()
        assert energy_store.record_snapshot(s, "garmin", None) is False


def test_calorie_settings_api_validates_and_round_trips(env):  # noqa: F811
    client, _ = env
    g = client.get("/api/settings/calories").json()
    assert g["mode"] == "auto" and g["eat_back_pct"] == 50 and g["pace"] is True
    assert client.put("/api/settings/calories", json={"manual_kcal": 2300}).status_code == 403  # needs the header
    ok = client.put("/api/settings/calories", json={"mode": "manual", "manual_kcal": 2300, "eat_back_pct": 25}, headers=MUTATE)
    assert ok.status_code == 200 and ok.json()["manual_kcal"] == 2300 and ok.json()["mode"] == "manual"
    assert client.get("/api/settings/calories").json()["eat_back_pct"] == 25
    for bad in ({"manual_kcal": 100}, {"manual_kcal": 99999}, {"eat_back_pct": 150}, {"mode": "x"}):
        assert client.put("/api/settings/calories", json=bad, headers=MUTATE).status_code in (400, 422)
    assert client.put("/api/settings/calories", json={"mode": "auto", "manual_kcal": None}, headers=MUTATE).json()["mode"] == "auto"
    assert client.put("/api/settings/calories", json={"mode": "manual", "manual_kcal": None}, headers=MUTATE).status_code == 400


def test_overview_carries_energy_and_phase_blocks_and_keeps_old_fields(env):  # noqa: F811
    client, _ = env
    assert client.post("/api/sync/demo", headers=MUTATE).status_code == 200
    o = client.get("/api/overview").json()
    assert {"coach", "score", "metrics", "weight", "journal", "planned_today", "week", "recent_activities"} <= set(o)
    assert o["energy"]["status"] in {"ok", "partial", "insufficient", "no_garmin_kcal", "just_started"} and "eaten" in o["energy"]
    assert o["phase"]["phase"] in __import__("cadence_app.analytics.dayphase", fromlist=["PHASES"]).PHASES and o["phase"]["cards"] and o["phase"]["copy"]["headline"]
