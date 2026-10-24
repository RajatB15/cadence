from datetime import timedelta

from cadence_app.analytics import routes as RT
from tests.test_notes import D0, EASY, act

HOME = {"startLatitude": 40.0, "startLongitude": -100.0, "endLatitude": 40.0005, "endLongitude": -100.0003,
        "minLatitude": 39.99, "maxLatitude": 40.02, "minLongitude": -100.03, "maxLongitude": -100.0, "elevationGain": 80.0}
OTHER = {**HOME, "startLatitude": 40.05, "endLatitude": 40.0505, "minLatitude": 40.04, "maxLatitude": 40.07}


def runs(n, dist=10000, **kw):
    return [act(i + 1, D0 + timedelta(days=7 * i), EASY, distance_m=dist * (1 + 0.01 * (i % 3)), moving_s=3000 - 20 * i, **kw) for i in range(n)]


def test_signature_needs_gps_and_rejects_nonsense():
    assert RT.signature(None) is None and RT.signature({}) is None
    assert RT.signature({"startLatitude": 0, "startLongitude": 0}) is None
    assert RT.signature({"startLatitude": "x", "startLongitude": 1}) is None
    assert RT.signature(HOME)["box"] == (39.99, 40.02, -100.03, -100.0)


def test_same_loop_clusters_and_a_different_start_does_not():
    acts = runs(6)
    geo = {a.id: HOME for a in acts[:4]} | {acts[4].id: OTHER, acts[5].id: HOME}
    out = RT.build(acts, geo, [], {}, acts[-1].day)
    assert out["has_geo"] and len(out["routes"]) == 1
    r = out["routes"][0]
    assert r["n"] == 5 and r["loop"] is True and r["name"] == "x" and r["elevation_m"] == 80
    assert acts[4].id not in {e["id"] for e in r["efforts"]}


def test_distance_and_climb_must_agree():
    acts = runs(3) + [act(10, D0 + timedelta(days=40), EASY, distance_m=15000, moving_s=4500)]
    geo = {a.id: HOME for a in acts}
    assert RT.build(acts, geo, [], {}, D0 + timedelta(days=50))["routes"][0]["n"] == 3
    hilly = {**HOME, "elevationGain": 400.0}
    mixed = {acts[0].id: HOME, acts[1].id: HOME, acts[2].id: hilly}
    assert RT.build(acts[:3], mixed, [], {}, D0 + timedelta(days=50))["routes"] == []


def test_efforts_flag_personal_bests_and_compare_latest_with_prior():
    acts = runs(6)
    eff = [{"id": a.id, "day": a.day, "ef": 1.0 + 0.02 * i, "hr": 150, "rhr": 50.0} for i, a in enumerate(acts)]
    weather = {a.id: {"temperature": 10.0 + i, "dew_point": 5, "wind": 3, "hot": False} for i, a in enumerate(acts)}
    r = RT.build(acts, {a.id: HOME for a in acts}, eff, weather, acts[-1].day)["routes"][0]
    assert r["best"]["id"] == acts[-1].id and r["efforts"][-1]["pr"] and r["latest"]["vs_prior"]["time_s"] < 0
    assert r["latest"]["vs_prior"]["ef_pct"] > 0 and r["latest"]["vs_prior"]["temperature"] > 0
    assert r["trend"]["significant"] and r["trend"]["change_pct"] > 0


def test_no_gps_or_no_repeats_explain_themselves():
    acts = runs(4)
    assert RT.build(acts, {}, [], {}, D0)["has_geo"] is False
    out = RT.build(acts, {acts[0].id: HOME, acts[1].id: OTHER}, [], {}, D0)
    assert out["has_geo"] and out["routes"] == [] and "covered" in out["reason"]


def test_rides_are_matched_but_not_given_an_efficiency_trend():
    acts = [act(i + 1, D0 + timedelta(days=5 * i), EASY, family="ride", distance_m=30000, moving_s=4000) for i in range(6)]
    r = RT.build(acts, {a.id: HOME for a in acts}, [], {}, acts[-1].day)["routes"][0]
    assert r["sport"] == "ride" and r["trend"] is None


def test_results_are_json_serialisable():
    import json

    from fastapi.encoders import jsonable_encoder

    acts = runs(6)
    eff = [{"id": a.id, "day": a.day, "ef": 1.0 + 0.02 * i, "hr": 150, "rhr": 50.0} for i, a in enumerate(acts)]
    json.dumps(jsonable_encoder(RT.build(acts, {a.id: HOME for a in acts}, eff, {}, acts[-1].day)))


def test_an_activity_finds_its_place_on_its_route():
    acts = runs(6)
    eff = [{"id": a.id, "day": a.day, "ef": 1.0 + 0.02 * i, "hr": 150, "rhr": 50.0} for i, a in enumerate(acts)]
    report = RT.build(acts, {a.id: HOME for a in acts}, eff, {}, acts[-1].day)
    mid = RT.for_activity(report, acts[2].id)
    assert mid["n"] == 6 and mid["this"]["rank"] == 4 and mid["this"]["earlier_efforts"] == 2 and not mid["this"]["is_best"]
    assert mid["this"]["vs_prior"]["time_s"] < 0 and mid["this"]["vs_prior"]["ef_pct"] > 0
    last = RT.for_activity(report, acts[-1].id)
    assert last["this"]["is_best"] and last["this"]["rank"] == 1 and last["this"]["vs_prior"]["ef_pct"] > 0
    assert RT.for_activity(report, 99999) is None
