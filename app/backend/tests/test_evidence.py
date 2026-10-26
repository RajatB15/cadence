from datetime import date, timedelta

import pytest

from cadence_app.analytics import evidence as EV
from cadence_app.analytics import status as status_analytics
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_recovery import steady_ctx

END = date(2026, 6, 30)


def pts(n, f, step=1):
    return [(END - timedelta(days=i * step), f(n - 1 - i)) for i in range(n - 1, -1, -1)]


def test_a_rising_marker_is_better_and_a_noisy_flat_one_is_flat():
    rising = EV.marker("efficiency", pts(30, lambda i: 1.0 + 0.004 * i + (0.003 if i % 2 else -0.003), step=4), END)
    assert rising["state"] == "better" and rising["change"] > 1.5 and rising["ci"][0] > 0 and rising["n"] == 30
    flat = EV.marker("efficiency", pts(30, lambda i: 1.0 + (0.02 if i % 2 else -0.02), step=4), END)
    assert flat["state"] == "flat"
    dropping_rhr = EV.marker("resting_hr", pts(80, lambda i: 60 - 0.05 * i + (0.4 if i % 2 else -0.4)), END)
    assert dropping_rhr["state"] == "better" and dropping_rhr["change"] < -1  # lower resting HR is the fitter direction
    rising_rhr = EV.marker("resting_hr", pts(80, lambda i: 50 + 0.06 * i + (0.4 if i % 2 else -0.4)), END)
    assert rising_rhr["state"] == "worse"


def test_too_little_or_too_narrow_data_is_missing_not_zero():
    few = EV.marker("efficiency", pts(5, lambda i: 1.0, step=4), END)
    assert few["state"] == "missing" and "5 of 8" in few["reason"] and few["change"] is None
    narrow = EV.marker("resting_hr", pts(45, lambda i: 55.0), END)  # 45 days of an 84-day window is enough span
    assert narrow["state"] != "missing"
    bunched = EV.marker("hrv", [(END - timedelta(days=i % 10), 50.0 + i % 3) for i in range(60)], END)
    assert bunched["state"] == "missing" and "cover only" in bunched["reason"]


def test_the_verdict_counts_agreement_and_never_blends():
    def m(state):
        return {"state": state}
    up, steady, down = {"state": "up"}, {"state": "steady"}, {"state": "down"}
    assert EV.verdict([m("better"), m("better"), m("flat"), m("missing")], steady)["key"] == "adapting"
    bad = EV.verdict([m("worse"), m("worse"), m("better"), m("flat")], up)
    assert bad["key"] == "not_adapting" and "1 improving · 2 worsening" in bad["summary"]
    assert EV.verdict([m("worse"), m("worse"), m("flat")], down)["key"] == "fading"
    assert EV.verdict([m("better"), m("worse"), m("flat")], steady)["key"] == "mixed"
    assert EV.verdict([m("better"), m("missing"), m("missing")], up)["key"] == "unknown"


def test_load_side_and_life_strain():
    pmc = {END: {"fitness": 50.0}, END - timedelta(days=42): {"fitness": 40.0}}
    assert EV.load_side(pmc, END)["state"] == "up" and EV.load_side({END: {"fitness": 50.0}}, END) is None
    days = {END - timedelta(days=i): {"everyday": 60.0 if i < 7 else 40.0} for i in range(70)}
    heavy = EV.life_strain({"days": days}, END)
    assert heavy["state"] == "heavy" and heavy["ratio"] == pytest.approx(1.5)
    assert EV.life_strain({"days": {END: {"everyday": 50.0}}}, END)["state"] == "missing"
    assert EV.life_strain(None, END) is None


def test_the_headline_says_not_adapting_when_load_is_fine_but_the_body_disagrees():
    c = steady_ctx()
    c["_memo"] = {"evidence": {"markers": [], "load": None, "life_strain": None,
                               "verdict": {"key": "not_adapting", "label": "Not adapting yet", "summary": "0 improving · 3 worsening", "text": "Load is holding but markers are down.", "counts": {}, "judged": 3}}}
    now = status_analytics.report(c, 12)["current"]
    plain = status_analytics.report({**steady_ctx()}, 12)["current"]
    if plain["status"] in ("progressing", "maintaining"):
        assert now["status"] == "not_adapting" and "load" in now["why"].lower() and now["evidence"]["key"] == "not_adapting"
    else:
        assert now["status"] == plain["status"]  # overloading and the rest are never softened or replaced


def test_training_trend_endpoint_carries_the_evidence(env):  # noqa: F811
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    t = client.get("/api/trends/training?weeks=12").json()
    ev = t["evidence"]
    assert {m["key"] for m in ev["markers"]} == set(EV.MARKERS) and ev["verdict"]["summary"] and "evidence" in t["current"]
    assert all(m["state"] in ("better", "worse", "flat", "missing") for m in ev["markers"])
