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
