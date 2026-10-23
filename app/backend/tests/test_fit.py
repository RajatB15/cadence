from datetime import datetime, timedelta, timezone

from cadence_app.garmin import fit

DEG = 1 / fit.SEMICIRCLE_TO_DEG


def _records(n: int) -> list[dict]:
    t0 = datetime(2026, 10, 1, 6, tzinfo=timezone.utc)
    return [
        {
            "timestamp": t0 + timedelta(seconds=i),
            "position_lat": int((12.9 + i * 1e-5) * DEG),
            "position_long": int((77.6 + i * 1e-5) * DEG),
            "heart_rate": 120 + i % 40,
            "enhanced_speed": 3.0,
            "enhanced_altitude": 900 + i * 0.1,
            "distance": i * 3.0,
        }
        for i in range(n)
    ]


def test_track_points_carry_aligned_values():
    records = _records(4000)
    records[10].pop("position_lat")  # GPS gap: no track point, still a stream sample
    _, _, route, track = fit._streams(records, "run")
    assert len(route) == fit.MAX_ROUTE_POINTS + 1
    assert set(track) == set(fit.TRACK_FIELDS)
    assert all(len(v) == len(route) for v in track.values())
    assert [track["lat"][-1], track["lon"][-1]] == route[-1]
    assert track["t"][-1] == 3999
    # values belong to the same record as the coordinate
    i = 700
    assert track["dist"][i] == track["t"][i] * 3.0
    assert track["hr"][i] == 120 + int(track["t"][i]) % 40


def test_track_drops_missing_channels_and_empty_routes():
    records = _records(50)
    for r in records:
        r.pop("heart_rate")
    _, _, _, track = fit._streams(records, "run")
    assert "hr" not in track and "alt" in track
    no_gps = [{k: v for k, v in r.items() if not k.startswith("position")} for r in records]
    assert fit._streams(no_gps, "run")[3] == {}
