from datetime import date, timedelta

from cadence_app.analytics import wellbeing as WB
from tests.test_notes import D0, EASY, GREY, HARD, act

T = date(2026, 6, 10)


def e(**kw):
    return {"feel": None, "soreness": None, "pain_level": None, "pain_area": None, "illness": None, "life_stress": None, **kw}


def test_state_picks_the_strongest_reason_and_never_adds_training():
    assert WB.state(None) is None
    assert WB.state(e(feel=5, soreness=0, pain_level=0, illness=0, life_stress=1))["level"] is None
    assert WB.state(e(feel=5))["level"] is None
    assert WB.state(e(illness=2, feel=1))["level"] == "rest" and WB.state(e(illness=2, feel=1))["codes"][0] == "ill"
    assert WB.state(e(pain_level=3, pain_area="left knee"))["level"] == "rest" and WB.state(e(pain_level=3, pain_area="left knee"))["area"] == "left knee"
    assert WB.state(e(pain_level=2))["level"] == "easy" and WB.state(e(illness=1))["level"] == "easy"
    assert WB.state(e(soreness=3))["level"] == "easy" and WB.state(e(feel=2))["level"] == "easy"
    assert WB.state(e(pain_level=1))["level"] == "watch" and WB.state(e(life_stress=3))["level"] == "watch"
    both = WB.state(e(pain_level=1, feel=2))
    assert both["level"] == "easy" and both["codes"] == ["feel_low", "niggle"]


def test_feel_and_the_watch_can_disagree_in_both_directions():
    assert WB.disagrees(e(feel=2), 80) == "flat" and WB.disagrees(e(feel=5), 40) == "fresh"
    assert WB.disagrees(e(feel=3), 40) is None and WB.disagrees(e(feel=2), 60) is None
    assert WB.disagrees(e(), 80) is None and WB.disagrees(e(feel=2), None) is None and WB.disagrees(None, 80) is None


def test_the_plan_is_held_back_for_illness_pain_or_a_run_of_flat_days():
    assert WB.hold({}, T) is None
    assert WB.hold({T: e(illness=2)}, T) == "illness you reported"
    assert WB.hold({T - timedelta(days=1): e(pain_level=2)}, T) == "pain you reported"
    assert WB.hold({T - timedelta(days=2): e(illness=2)}, T) is None  # too long ago
    assert WB.hold({T: e(illness=1), T - timedelta(days=1): e(illness=1)}, T) == "feeling run down two days running"
    assert WB.hold({T: e(illness=1)}, T) is None
    flat = {T - timedelta(days=i): e(feel=2) for i in range(3)}
    assert WB.hold(flat, T) == "feeling flat for several days"
    assert WB.hold({T - timedelta(days=i): e(feel=2) for i in range(2)}, T) is None


def test_patterns_find_recurring_pain_disagreement_and_training_through_it():
    ent, ready = {}, {}
    for i in range(14):
        d = T - timedelta(days=i)
        ent[d] = e(feel=2 if i % 3 == 0 else 4, pain_level=2 if i in (1, 5, 9) else 0, pain_area="left knee" if i in (1, 5, 9) else None)
        ready[d] = 80.0
    acts = [act(1, T - timedelta(days=1), HARD), act(2, T - timedelta(days=5), EASY)]
    p = WB.patterns(ent, ready, acts, T)
    assert p["recurring_pain"] == {"area": "left knee", "days": 3, "worst": 2}
    assert p["disagreement"]["mostly"] == "flat" and p["disagreement"]["days"] >= 3 and p["disagreement"]["of"] == 14
    assert p["through_pain"] == {"days": 2, "hard": 1}
    assert "through_illness" not in p and "heavy_stress" not in p


def test_stress_and_a_dropping_feel_are_noticed_only_with_enough_data():
    ent = {T - timedelta(days=i): e(life_stress=3, feel=2) for i in range(5)}
    ent.update({T - timedelta(days=i): e(feel=4) for i in range(7, 20)})
    assert WB.stress_high(ent, T)
    p = WB.patterns(ent, {}, [], T)
    assert p["heavy_stress"]["days"] == 5 and p["feel_drop"]["now"] == 2.0 and p["feel_drop"]["before"] == 4.0
    assert WB.patterns({T: e(feel=1)}, {}, [], T) == {}


def test_illness_trained_through_is_called_out():
    p = WB.patterns({T: e(illness=2)}, {}, [act(1, T, EASY)], T)
    assert p["through_illness"] == {"days": 1}


def test_recovery_wins_count_what_was_done_right():
    acts = [act(1, T - timedelta(days=13), HARD), act(2, T - timedelta(days=12), EASY), act(3, T - timedelta(days=6), HARD), act(4, T - timedelta(days=5), HARD),
            act(5, T - timedelta(days=3), EASY), act(6, T - timedelta(days=1), GREY)]
    sleep = {T - timedelta(days=i): 8.2 if i % 2 else 6.5 for i in range(14)}
    c = {"as_of": T, "acts": acts, "series": {"sleep_hours": sleep}, "sleep_need": {"hours": 8.0},
         "wellbeing": {T - timedelta(days=2): e(feel=2), T - timedelta(days=4): e(pain_level=2), T - timedelta(days=6): e(illness=2)}}
    w = WB.recovery_wins(c)
    assert w["easy_kept"] == 2 and w["grey"] == 1 and w["sessions"] == 6
    assert w["eased_after_hard"] == 2 and w["hard_days"] == 3  # day 13 and day 5 were followed by an easier day; day 6 by another hard one
    assert w["nights"] == 14 and w["nights_at_need"] == 7 and w["listened"] == 2  # the day-6 illness fell on a hard day, so it doesn't count
    assert w["rest_days"] == 14 - 6
