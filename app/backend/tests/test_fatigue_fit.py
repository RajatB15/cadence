from datetime import date, timedelta

import numpy as np

from cadence_app.analytics import fatigue_fit as F

D0 = date(2025, 3, 3)


def history(days=420, tau=12, c=0.1, seed=4, signal=True, noise=0.6):
    rng = np.random.default_rng(seed)
    load = {}
    for i in range(days):
        block = (i // 14) % 3
        base = (0, 70, 0, 90, 60, 110, 0)[i % 7] * (0.3 if block == 2 else 1.0 + 0.4 * block)
        if base:
            load[D0 + timedelta(days=i)] = float(base * rng.uniform(0.8, 1.2))
    w = np.zeros(days)
    for d, x in load.items():
        w[(d - D0).days] = x
    acute = F._acute_before(w, tau)
    hrv, rhr = {}, {}
    for i in range(days):
        s = c * acute[i] - c * acute.mean() if signal else 0.0
        d = D0 + timedelta(days=i)
        hrv[d] = float(60 - 4 * s + rng.normal(0, noise))
        rhr[d] = float(50 + 2 * s + rng.normal(0, noise / 2))
    return load, hrv, rhr, D0 + timedelta(days=days - 1)


def test_recovers_a_slower_fatigue_constant_than_the_standard():
    load, hrv, rhr, end = history(tau=14)
    r = F.fit(load, hrv, rhr, end)
    assert r["valid"] and r["adopted"], r.get("why_not")
    assert 9 <= r["tau"] <= 17 and r["region"][0] <= r["tau"] <= r["region"][1] and r["half_life_days"] > 6
    assert r["cv"]["gain_vs_default_pct"] > 0 and r["bump_per_100_load"] > 0 and r["series"]


def test_standard_seven_days_is_kept_when_it_fits_as_well():
    load, hrv, rhr, end = history(tau=7, seed=9, c=0.08, noise=1.0)
    r = F.fit(load, hrv, rhr, end)
    assert r["valid"] and not r["adopted"] and r["why_not"]


def test_nights_unrelated_to_load_adopt_nothing():
    load, hrv, rhr, end = history(signal=False, seed=2)
    r = F.fit(load, hrv, rhr, end)
    assert not r.get("adopted") and (r.get("why_not") or not r["valid"])


def test_too_few_nights_say_what_is_missing():
    load, hrv, rhr, end = history(days=40)
    r = F.fit(load, hrv, rhr, end)
    assert not r["valid"] and "nights" in r["missing"]


def test_result_is_json_serialisable():
    import json

    from fastapi.encoders import jsonable_encoder

    load, hrv, rhr, end = history(tau=14)
    json.dumps(jsonable_encoder(F.fit(load, hrv, rhr, end)))
