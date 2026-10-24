from datetime import timedelta

import numpy as np
import pytest

from cadence_app.analytics import banister as B
from cadence_app.analytics import channels as CH
from tests.test_notes import D0, EASY, act, ctx

GREY = (300, 1200, 2100, 0, 0)
HARD = (300, 900, 600, 1500, 300)


def history(high_effect=0.04, aer_effect=0.01, days=420, seed=6, noise=0.1):
    """Runs every other day; hard days every 6th. Efficiency is built from the two exposures with known effects."""
    rng = np.random.default_rng(seed)
    acts = []
    for i in range(days):
        if i % 2:
            continue
        hard = (i // 2) % 3 == 0 and (i // 35) % 2 == 0  # hard work comes in blocks, independent of easy volume
        grey = (i // 2) % 5 == 1
        zones = HARD if hard else GREY if grey else EASY
        scale = rng.uniform(0.7, 1.3) * (1.0 if (i // 49) % 3 else 0.5)  # easy volume has its own, different cycle
        acts.append(act(i + 1, D0 + timedelta(days=i), tuple(z * scale for z in zones), moving_s=3600 * scale, load=60.0 * scale))
    aer, high = CH.daily_minutes(acts)
    end = D0 + timedelta(days=days - 1)
    ea, eh = CH._exposure(aer, D0, end), CH._exposure(high, D0, end)
    eff, i = [], 0
    for d in range(10, days, 7):
        i += 1
        eff.append({"id": 9000 + i, "day": D0 + timedelta(days=d), "ef": float(1.0 + aer_effect * ea[d] + high_effect * eh[d] + rng.normal(0, noise * 0.1)), "hr": 150, "rhr": 50.0})
    return ctx(acts, days=days) | {"eff": eff}


def test_zone_three_counts_as_aerobic_so_a_grey_run_kept_easy_moves_no_minutes():
    grey = act(1, D0, GREY)
    assert CH.act_minutes(grey) == (60.0, 0.0)
    assert CH.shifted(grey, "easy") == (60.0, 0.0)
    hard = act(2, D0, HARD)
    a, h = CH.act_minutes(hard)
    assert h == pytest.approx(30.0) and CH.shifted(hard, "easy") == (a + h, 0.0)
    assert CH.shifted(hard, "skip") == (0.0, 0.0) and CH.shifted(hard, "half") == (a / 2, h / 2)
    assert CH.act_minutes(act(3, D0, EASY, family="strength")) == (0.0, 0.0)
    assert CH.act_minutes(act(4, D0, (), moving_s=1800)) == (30.0, 0.0)


def test_it_finds_that_high_intensity_minutes_matter_more():
    r = CH.fit(history(seed=8))
    assert r["valid"] and r["adopted"], r.get("why_not")
    assert r["high"]["pct_per_hour"] > r["aerobic"]["pct_per_hour"] > 0 and r["high"]["ci"][0] > 0


def test_when_easy_and_hard_cannot_be_told_apart_nothing_is_adopted():
    r = CH.fit(history(seed=6))
    assert r["valid"] and not r["adopted"] and r["why_not"] and CH.effect(r, [], [], D0) is None


def test_only_the_high_channel_changes_when_a_hard_session_is_kept_easy():
    c = history(seed=8)
    r = CH.fit(c)
    hard = next(a for a in c["acts"] if A_hard(a) and a.day > c["as_of"] - timedelta(days=120) and a.day < c["as_of"] - timedelta(days=20))
    e = CH.effect(r, c["acts"], [{"activity_id": hard.id, "action": "easy"}], hard.day + timedelta(days=14))
    assert e["ef_pct"] < 0 and e["high_hours_per_week"] < 0 and e["ci"][0] <= e["ef_pct"] <= e["ci"][1]
    grey = next(a for a in c["acts"] if CH.act_minutes(a)[1] == 0 and a.zones_s[2] > 1000)
    assert CH.effect(r, c["acts"], [{"activity_id": grey.id, "action": "easy"}], grey.day + timedelta(days=14))["ef_pct"] == pytest.approx(0.0, abs=1e-6)


def A_hard(a):
    return len(a.zones_s) >= 5 and a.zones_s[3] + a.zones_s[4] > 1000


def test_minutes_moved_summarises_the_swap_in_plain_numbers():
    c = history()
    greys = [a for a in c["acts"] if a.zones_s[2] > 1000][:3]
    m = CH.minutes_moved(c["acts"], [{"activity_id": a.id, "action": "easy"} for a in greys])
    assert m["before"] == m["after"] and m["zone3_minutes"] > 0


def test_too_little_data_or_no_hard_work_explains_itself():
    assert "weeks of runs" in CH.fit(history(days=90, seed=8))["missing"]
    easy_only = ctx([act(i + 1, D0 + timedelta(days=2 * i), EASY) for i in range(150)], days=300)
    easy_only["eff"] = [{"id": i, "day": D0 + timedelta(days=7 * i), "ef": 1.0 + 0.001 * i, "hr": 150, "rhr": 50.0} for i in range(40)]
    assert "zone 4-5" in CH.fit(easy_only)["missing"]


def test_result_is_json_serialisable():
    import json

    from fastapi.encoders import jsonable_encoder

    r = CH.fit(history(seed=8))
    json.dumps(jsonable_encoder(CH.public(r)))
    assert B.weekly_series(history()["eff"])


def test_a_weekly_point_dated_after_the_last_day_is_ignored():
    c = history(seed=8)
    c["eff"] = c["eff"] + [{"id": 99999, "day": c["as_of"], "ef": 1.0, "hr": 150, "rhr": 50.0}]  # its week's midpoint is after as_of
    assert CH.fit(c)["valid"]
