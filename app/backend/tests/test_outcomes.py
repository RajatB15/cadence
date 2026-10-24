from datetime import date, timedelta

from cadence_app.analytics import outcomes as O
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_notes import D0, EASY, HARD, act, ctx


def world(days=200, ef_gain=0.0, rhr_shift=0.0, with_checkins=False, vo2_gain=0.0):
    acts, i = [], 0
    for w in range(days // 7):
        for dd, z in ((0, EASY), (2, HARD), (4, EASY), (6, EASY)):
            i += 1
            acts.append(act(i, D0 + timedelta(days=7 * w + dd), z))
    ds = [D0 + timedelta(days=k) for k in range(days)]
    series = {"resting_hr": {d: 50.0 + (rhr_shift if k >= days - 84 else 0.0) for k, d in enumerate(ds)}, "hrv": {d: 60.0 for d in ds},
              "sleep_hours": {d: 7.5 for d in ds}, "vo2max": {d: 50.0 + (vo2_gain if k >= days - 84 else 0.0) for k, d in enumerate(ds)}}
    c = ctx(acts, series, days=days)
    c["eff"] = [{"id": 9000 + k, "day": D0 + timedelta(days=7 * k + 1), "ef": 1.0 + (ef_gain if 7 * k + 1 >= days - 84 else 0.0), "hr": 150, "rhr": 50.0} for k in range(days // 7)]
    if with_checkins:
        c["wellbeing"] = {D0 + timedelta(days=k): {"pain_level": 1 if k >= days - 84 and k % 4 == 0 else 0, "illness": 0, "feel": 3} for k in range(days)}
    return c


def test_it_needs_two_full_windows_of_history():
    out = O.summarise(world(days=120))
    assert not out["enough"] and "24 weeks" in out["reason"]


def test_better_efficiency_and_vo2_with_a_lower_resting_hr_reads_as_improving():
    out = O.summarise(world(ef_gain=0.05, rhr_shift=-2.0, vo2_gain=1.5))
    by = {m["key"]: m for m in out["markers"]}
    assert out["enough"] and by["efficiency"]["state"] == "better" and by["efficiency"]["change"] == 5.0
    assert by["vo2max"]["state"] == "better" and by["resting_hr"]["state"] == "better" and by["resting_hr"]["change"] == -2.0
    assert out["verdict"] == "improving" and out["better"] >= 2 and out["worse"] == 0


def test_changes_smaller_than_the_noise_are_flat_and_missing_data_is_not_zero():
    out = O.summarise(world(ef_gain=0.005))
    by = {m["key"]: m for m in out["markers"]}
    assert by["efficiency"]["state"] == "flat" and by["sleep"]["state"] == "flat"
    assert by["critical_speed"]["state"] == "missing" and by["critical_speed"]["change"] is None
    assert out["verdict"] in ("holding", "unclear", "edging_up", "edging_down")


def test_worse_efficiency_is_slipping_only_when_more_than_one_performance_marker_agrees():
    c = world(ef_gain=-0.06)
    out = O.summarise(c)
    assert out["verdict"] in ("edging_down", "slipping", "mixed", "unclear") and {m["key"]: m for m in out["markers"]}["efficiency"]["state"] == "worse"


def test_the_cost_side_counts_check_in_days_and_adherence():
    plans = [{"day": D0 + timedelta(days=150 + k), "status": "done" if k % 3 else "missed"} for k in range(20)]
    out = O.summarise(world(with_checkins=True), plans)
    assert out["now"]["pain_days"] >= 20 and out["before"]["pain_days"] == 0 and out["cost_up"] >= 20 and out["checkin_coverage"]
    assert out["now"]["adherence_pct"] == 65 and out["before"]["adherence_pct"] is None  # too few earlier plans to say
    assert 20 <= out["now"]["hard_share_pct"] <= 30


def test_the_verdict_is_plain_and_honest_about_cost():
    from cadence_app.analytics import notes

    good = notes.outcomes_text(O.summarise(world(ef_gain=0.05, rhr_shift=-2.0, vo2_gain=1.5, with_checkins=True)))
    assert good["headline"]["tone"] == "good" and "better than 12 weeks ago" in good["headline"]["text"] and "isn't free" in good["headline"]["text"]
    assert any(l.startswith("Training:") for l in good["lines"]) and any("Check-ins:" in l for l in good["lines"])
    short = notes.outcomes_text(O.summarise(world(days=100)))
    assert short["headline"]["tone"] == "info" and short["lines"] == []
    no_checkins = notes.outcomes_text(O.summarise(world()))
    assert any("Add daily check-ins" in l for l in no_checkins["lines"])


def test_the_outcomes_endpoint_answers_without_enough_history(env):  # noqa: F811
    client, _ = env
    assert client.get("/api/outcomes").json() == {"has_data": False}
    client.post("/api/sync/demo", headers=MUTATE)
    body = client.get("/api/outcomes").json()
    assert body["has_data"] and body["headline"]["text"] and "markers" in body or body["enough"] is False


def test_one_marker_moving_is_edging_not_a_trend():
    from cadence_app.analytics import notes

    up = O.summarise(world(vo2_gain=1.5))
    assert up["verdict"] == "edging_up" and "A little better" in notes.outcomes_text(up)["headline"]["text"]
    down = O.summarise(world(ef_gain=-0.05))
    assert down["verdict"] == "edging_down" and "A little worse" in notes.outcomes_text(down)["headline"]["text"]
