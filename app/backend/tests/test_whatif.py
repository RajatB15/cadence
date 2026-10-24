from datetime import timedelta

import pytest

from cadence_app.analytics import whatif as WI
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_notes import D0, EASY, GREY, HARD, act, ctx


def history(grey_days=(70, 76, 90), days=100):
    acts, i = [], 0
    for w in range(days // 7):
        for dd, z, minutes in ((0, EASY, 60), (3, EASY, 45), (5, EASY, 90)):
            i += 1
            day = D0 + timedelta(days=7 * w + dd)
            if day < D0 + timedelta(days=days):
                acts.append(act(i, day, tuple(x * minutes / 60 for x in z), load=minutes * 1.0, moving_s=minutes * 60))
    for k, d in enumerate(grey_days):
        acts.append(act(500 + k, D0 + timedelta(days=d), GREY, load=110.0, moving_s=3600))
    return ctx(acts, days=days)


def test_skipping_a_session_lowers_fitness_and_raises_form_in_the_model():
    c = history()
    r = WI.compare(c, [{"activity_id": 500, "action": "skip"}])
    assert r["valid"] and r["end"]["fitness_delta"] < 0
    assert r["next_morning"]["form_delta"] > 0 and r["next_morning"]["fatigue_delta"] < 0
    assert r["trajectory"][0]["fitness"] == pytest.approx(next(p["fitness"] for p in c["pmc"] if p["day"] == r["trajectory"][0]["day"]))
    assert r["edits"][0]["load_after"] == 0


def test_easy_keeps_the_duration_at_your_own_easy_rate_and_never_raises_load():
    c = history()
    rates = WI.easy_rates(c["acts"], c["as_of"])
    assert rates["run"]["n"] >= 3 and rates["run"]["rate"] == pytest.approx(1.0, rel=0.05)
    r = WI.compare(c, [{"activity_id": 500, "action": "easy"}], rates)
    assert 55 <= r["edits"][0]["load_after"] <= 65 and not r["rough"]
    low = act(1, D0, GREY, load=20.0, moving_s=3600)
    assert WI.new_load(low, "easy", rates)[0] == 20.0


def test_without_easy_sessions_the_fallback_is_flagged_rough():
    c = ctx([act(1, D0 + timedelta(days=90), GREY, load=100.0)], days=100)
    r = WI.compare(c, [{"activity_id": 1, "action": "easy"}])
    assert r["valid"] and r["rough"] and r["edits"][0]["load_after"] == 50


def test_edits_outside_the_window_or_unknown_are_ignored():
    c = history()
    assert WI.compare(c, [{"activity_id": 1, "action": "skip"}, {"activity_id": 9999, "action": "skip"}, {"activity_id": 500, "action": "nope"}])["valid"] is False


def test_suggestions_find_grey_sessions_and_bundle_them():
    c = history()
    s = WI.suggestions(c)
    assert {i["id"] for i in s["items"]} == {500, 501, 502} and all(i["kind"] == "grey" for i in s["items"])
    b = s["bundles"]["grey"]
    assert b["n"] == 3 and b["end"]["fitness_delta"] < 0 and b["trajectory"]
    assert s["recent"] and "hard_again" not in s["bundles"]


def test_hard_days_back_to_back_are_flagged():
    acts = [act(1, D0 + timedelta(days=80), HARD, load=120.0), act(2, D0 + timedelta(days=81), HARD, load=120.0)]
    s = WI.suggestions(ctx(acts, days=100))
    assert [(i["id"], i["kind"]) for i in s["items"]] == [(2, "hard_again")]


def test_results_are_json_serialisable():
    import json

    from fastapi.encoders import jsonable_encoder

    c = history()
    json.dumps(jsonable_encoder(WI.suggestions(c)))
    json.dumps(jsonable_encoder(WI.compare(c, [{"activity_id": 500, "action": "easy"}])))


def test_a_period_replays_its_flagged_sessions_and_counts_the_easy_ones_kept_easy():
    from cadence_app.analytics import notes

    c = history()
    w = WI.for_period(c, D0 + timedelta(days=66), D0 + timedelta(days=99))
    assert w["flagged"] == 3 and w["replay"]["n"] == 3 and w["replay"]["fitness_delta"] < 0 and w["sessions"]
    card = notes.whatif_card(w, "week", c)
    assert card["title"] == "3 sessions could have been easier" and "fresher" in card["text"] and "fitness point" in card["text"]
    assert "Model" not in card["text"] and card["link"].startswith("/lab")
    quiet = WI.for_period(c, D0 + timedelta(days=10), D0 + timedelta(days=30))
    assert quiet is None  # outside the replay window of the last 8 weeks
    clean = WI.for_period(history(grey_days=()), D0 + timedelta(days=75), D0 + timedelta(days=99))
    assert clean["flagged"] == 0 and clean["easy_kept"] >= 3
    assert notes.whatif_card(clean, "home")["tone"] == "good"
    assert notes.whatif_card(WI.for_period(history(grey_days=()), D0 + timedelta(days=99), D0 + timedelta(days=99)), "week") is None


def test_one_flagged_session_gets_its_own_card_and_others_get_none():
    from cadence_app.analytics import notes

    c = history()
    w = WI.for_activity(c, 500)
    assert w["kind"] == "grey" and w["load_after"] < w["load"]
    card = notes.whatif_card(w, "session", c)
    assert card["link"] == "/lab?tab=whatif&session=500" and "grey-zone" in card["text"] and card["action"]
    assert WI.for_activity(c, 1) is None and WI.for_activity(c, 99999) is None


def test_a_review_period_can_end_before_today():
    c = history()
    r = WI.compare(c, [{"activity_id": 500, "action": "skip"}], since=D0 + timedelta(days=60), until=D0 + timedelta(days=75))
    assert r["valid"] and r["trajectory"][-1]["day"] == D0 + timedelta(days=75)


def test_what_ifs_reach_home_sessions_and_reviews(env):  # noqa: F811
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    assert "what_if" in client.get("/api/overview").json()["coach"]
    review = client.get("/api/reviews/week").json()
    assert "what_if" in review
    first = client.get("/api/activities?limit=1").json()["items"][0]
    detail = client.get(f"/api/activities/{first['id']}").json()
    assert "route" in detail and detail["route"] is None
    assert detail["coach"] is None or "what_if" in detail["coach"]


def hist_with_hard_after_grey():
    c = history()
    # a hard run two days after the grey one at day 70, so the freshness the replay buys lands on it
    hard = act(900, D0 + timedelta(days=72), HARD, load=120.0, moving_s=3600)
    c2 = ctx(list(c["acts"]) + [hard], days=100)
    return c2


FRESH_HELPS = {"hard": {"enough": True, "helpful": True, "n": 20, "min": 12, "per_point_pct": 0.3, "ci_per_point_pct": [0.1, 0.5], "per10_pct": 3.0, "ci_per10_pct": [1.0, 5.0]}}
FRESH_UNPROVEN = {"hard": {"enough": True, "helpful": False, "n": 20, "min": 12}}


def test_a_personal_model_changes_the_replay_and_says_which_parts_are_personal():
    c = history()
    mine = {"ctl_days": 30, "atl_days": 10, "alpha": 0.7, "personal": True, "sources": ["fitness builds over 30 days"]}
    a = WI.compare(c, [{"activity_id": 500, "action": "skip"}])
    b = WI.compare(c, [{"activity_id": 500, "action": "skip"}], lab={"model": mine})
    assert a["model"]["personal"] is False and (a["model"]["ctl_days"], a["model"]["atl_days"]) == (42, 7)
    assert b["model"]["personal"] and b["model"]["sources"] == ["fitness builds over 30 days"]
    assert b["end"]["fitness"][0] != a["end"]["fitness"][0] and b["end"]["fitness_delta"] != a["end"]["fitness_delta"]


def test_every_replay_carries_a_range_that_contains_its_own_estimate():
    c = history()
    r = WI.compare(c, [{"activity_id": 500, "action": "skip"}])
    lo, hi = r["ranges"]["fitness_delta"]
    assert lo <= r["end"]["fitness_delta"] <= hi and lo < hi and "textbook" in r["ranges"]["basis"] and r["ranges"]["n_pairs"] >= 9
    nm_lo, nm_hi = r["ranges"]["next_morning_form"]
    assert nm_lo <= r["next_morning"]["form_delta"] <= nm_hi
    fit = {"valid": True, "region_pairs": [(30, 6), (36, 8)]}
    r2 = WI.compare(c, [{"activity_id": 500, "action": "skip"}], lab={"banister": fit})
    assert "cannot rule out" in r2["ranges"]["basis"] and r2["ranges"]["n_pairs"] == 3  # the two plausible pairs and the model's own


def test_a_grey_run_kept_easy_moves_no_minutes_between_channels():
    c = history()
    z = WI.compare(c, [{"activity_id": 500, "action": "easy"}])["zones"]
    assert z["before"] == z["after"] and z["zone3_minutes"] > 0
    assert WI.compare(c, [{"activity_id": 500, "action": "skip"}])["zones"]["after"] == {"aerobic": 0, "high": 0}


def test_freshness_is_priced_only_when_your_own_data_show_it_helps():
    c = hist_with_hard_after_grey()
    helped = WI.compare(c, [{"activity_id": 500, "action": "easy"}], lab={"freshness": FRESH_HELPS})["payoff"]
    assert helped["status"] == "measured" and helped["items"] and helped["items"][0]["session_id"] == 900
    assert helped["items"][0]["form_delta"] > 0 and helped["items"][0]["payoff"]["gain_pct"] > 0 and helped["total_gain_pct"] > 0
    unproven = WI.compare(c, [{"activity_id": 500, "action": "easy"}], lab={"freshness": FRESH_UNPROVEN})["payoff"]
    assert unproven["status"] == "unproven" and unproven["total_gain_pct"] is None
    assert WI.compare(c, [{"activity_id": 500, "action": "easy"}])["payoff"] == {"status": "unmeasured", "items": []}
    nothing_after = WI.compare(history(), [{"activity_id": 500, "action": "easy"}], lab={"freshness": FRESH_HELPS})["payoff"]
    assert nothing_after["items"] == [] and nothing_after["total_gain_pct"] is None


def test_the_channel_model_adds_an_efficiency_effect_only_when_adopted():
    c = history()
    adopted = {"adopted": True, "mean_ef": 1.0, "_coef": {"aer": 0.02, "high": 0.06, "se_aer": 0.005, "se_high": 0.02}}
    r = WI.compare(c, [{"activity_id": 500, "action": "skip"}], lab={"channels": adopted})
    assert r["channels"]["ef_pct"] < 0 and r["channels"]["ci"][0] < r["channels"]["ef_pct"] < r["channels"]["ci"][1]
    assert WI.compare(c, [{"activity_id": 500, "action": "skip"}], lab={"channels": {"adopted": False}})["channels"] is None


def test_suggestions_and_bundles_carry_the_new_fields():
    s = WI.suggestions(history(), {"freshness": FRESH_HELPS})
    b = s["bundles"]["grey"]
    assert {"ranges", "zones", "payoff", "model", "channels"} <= set(b) and s["items"][0]["ranges"]


def test_the_lines_under_a_card_are_plain_and_skip_empty_effects():
    from cadence_app.analytics import notes

    c = hist_with_hard_after_grey()
    adopted = {"adopted": True, "mean_ef": 1.0, "_coef": {"aer": 0.02, "high": 0.06, "se_aer": 0.005, "se_high": 0.02}}
    mine = {"ctl_days": 30, "atl_days": 10, "alpha": 0.7, "personal": True, "sources": ["fitness builds over 30 days", "very big days count for proportionally less"]}
    r = WI.compare(c, [{"activity_id": 500, "action": "easy"}], lab={"freshness": FRESH_HELPS, "channels": adopted, "model": mine})
    lines = notes.whatif_lines(r)
    assert any("Zone 3 minutes count as aerobic" in x for x in lines)  # a grey run kept easy moves no minutes, so no channel line
    assert not any("aerobic efficiency at" in x for x in lines)
    assert any("closer to your best" in x for x in lines) and any(x.startswith("Using your personal settings: fitness builds over 30 days; very big") for x in lines)
    skip = notes.whatif_lines(WI.compare(c, [{"activity_id": 900, "action": "skip"}], lab={"channels": adopted}))
    assert any("aerobic efficiency at" in x for x in skip)
    unproven = notes.whatif_lines(WI.compare(c, [{"activity_id": 500, "action": "easy"}], lab={"freshness": FRESH_UNPROVEN}))
    assert any("has not been shown to improve" in x for x in unproven)
    unmeasured = notes.whatif_lines(WI.compare(c, [{"activity_id": 500, "action": "easy"}], lab={"freshness": {"hard": {"enough": False, "n": 4, "min": 12}}}))
    assert any("Only 4 of the 12 hard runs" in x for x in unmeasured)
    card = notes.whatif_card(WI.for_period(c, D0 + timedelta(days=66), D0 + timedelta(days=99), {"freshness": FRESH_HELPS}), "week", c)
    assert "That only pays off" not in card["text"] and card["lines"]
