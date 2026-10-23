import random
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from cadence_app import weather as WX
from cadence_app.analytics import heat as W
from cadence_app.analytics import notes
from cadence_app.analytics import planner as PL
from cadence_app.analytics.insights import coach
from cadence_app.db import make_engine, make_session_factory, upgrade_database
from cadence_app.models import Activity, ActivityWeather, Source, WeatherHour
from tests.test_notes import D0, EASY, act, ctx


def test_hadley_table_and_heat_measure():
    assert W.hadley_pct(10, 5) == 0 and W.hadley_pct(30, 22) > W.hadley_pct(25, 15) > 0
    assert W.heat(8) == 0 and W.heat(20) == 10
    assert W.hot({"temperature": 29, "dew_point": 12}) and not W.hot({"temperature": 20, "dew_point": 12})


def heat_world(n: int = 60):
    """Runs where every °C of dew point above 10 costs 1% efficiency."""
    rng = random.Random(2)
    acts, weather, days = [], {}, [D0 + timedelta(days=i * 2) for i in range(n)]
    for i, d in enumerate(days):
        dew = rng.choice([4, 8, 12, 16, 20, 22])
        speed = 2.8 * (1 - 0.01 * max(0, dew - 10)) * (1 + rng.gauss(0, 0.005))
        acts.append(act(i, d, EASY, speed_mps=speed))
        weather[i] = {"temperature": dew + 6, "dew_point": dew, "humidity": 70, "apparent": dew + 7, "wind": 10}
    return acts, weather, days


def test_personal_heat_cost_is_learned_and_removed_from_the_trend():
    acts, weather, days = heat_world()
    c = ctx(acts, {"resting_hr": {d: 50.0 for d in days}}, days=125, weather=weather)
    m = c["heat"]
    assert m["significant"] and m["slope_pct_per_c"] == pytest.approx(-1.0, abs=0.25)
    raw = [p["ef_raw"] for p in c["eff"] if "ef_raw" in p]
    assert raw and max(p["ef"] for p in c["eff"]) / min(p["ef"] for p in c["eff"]) < max(raw) / min(raw)  # spread shrinks
    hot_run = next(a for a in acts if weather[a.id]["dew_point"] == 22)
    n = next(x for x in notes.session(c, hot_run.id)["notes"] if x["id"] == "weather")
    assert n["title"].startswith("Hot") and "your own runs" in n["detail"]
    assert any(f["id"] == "heat_cost" for f in coach(c))
    assert c["weather_runs"][hot_run.id]["hot"]


def test_outlook_suggests_a_cooler_hour():
    day = date(2026, 7, 4)
    hours = [{"ts": datetime(2026, 7, 4, h), "temperature": 18 + h * 0.8, "dew_point": 14 + h * 0.4, "apparent": 20 + h, "wind": 5, "humidity": 60}
             for h in range(24)]
    o = W.outlook(hours, day, 17, timedelta(0), None)
    assert o["hour"] == 17 and o["cost_pct"] > 1 and o["basis"] == "general"
    assert o["better_hour"] is not None and o["better_hour"] < 10
    assert W.outlook(hours, date(2026, 7, 9), 7, timedelta(0), None) is None


def test_planner_shows_tomorrows_weather():
    acts, weather, days = heat_world()
    tomorrow = days[-1] + timedelta(days=1)
    forecast = [{"ts": datetime.combine(tomorrow, datetime.min.time()) + timedelta(hours=h), "temperature": 30.0, "dew_point": 22.0,
                 "apparent": 33.0, "wind": 5.0, "humidity": 60} for h in range(24)]
    c = ctx(acts, {"resting_hr": {d: 50.0 for d in days}}, days=(days[-1] - D0).days + 1, weather=weather, forecast=forecast)
    m = PL.load_model(c["acts"], c["as_of"])
    opt = PL.run_options(c, None)[1]
    w = PL.predict(c, m, tomorrow, opt, [])["weather"]
    assert w["hot"] and w["basis"] == "personal" and w["cost_pct"] == pytest.approx(12, abs=3)


def fake_open_meteo(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        q = {k: v[0] for k, v in parse_qs(urlparse(str(request.url)).query).items()}
        seen.append((request.url.host, q))
        if "archive" in request.url.host:
            start, end = date.fromisoformat(q["start_date"]), date.fromisoformat(q["end_date"])
            days = (end - start).days + 1
        else:
            start = date(2026, 10, 22) - timedelta(days=int(q.get("past_days", 0)))
            days = int(q.get("past_days", 0)) + int(q.get("forecast_days", 1))
        times = [(datetime.combine(start, datetime.min.time()) + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(24 * days)]
        n = len(times)
        return httpx.Response(200, json={"utc_offset_seconds": 0, "hourly": {
            "time": times, "temperature_2m": [20.0] * n, "relative_humidity_2m": [60.0] * n, "dew_point_2m": [12.0] * n,
            "apparent_temperature": [21.0] * n, "wind_speed_10m": [8.0] * n}})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_refresh_sends_only_rounded_coordinates_and_fetches_history_once(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'db.sqlite3'}"
    upgrade_database(url)
    factory = make_session_factory(make_engine(url))
    now = datetime(2026, 10, 22, 12)
    with factory() as s, s.begin():
        s.add(Source(id="garmin", name="Garmin", kind="garmin"))
        s.flush()
        for i, d in enumerate((date(2026, 5, 1), date(2026, 5, 3), date(2026, 10, 21))):
            s.add(Activity(source_id="garmin", source_record_id=str(i), start_time_utc=datetime.combine(d, datetime.min.time()).replace(hour=7),
                           timezone="UTC", local_date=d, activity_type="running", name="Run", duration_s=3600, imported_at=now))
    summaries = {str(i): {"startLatitude": 12.97194, "startLongitude": 77.59369} for i in range(3)}
    monkeypatch.setattr(WX.vault, "activity_summaries", lambda session: summaries)
    seen: list = []
    calls = WX.refresh(factory, date(2026, 10, 22), now, fake_open_meteo(seen))
    assert calls == 3  # one archive (May), one recent forecast for the 21 Oct run, one home forecast
    assert all(q["latitude"] == "13.0" and q["longitude"] == "77.6" for _, q in seen)
    assert {k for _, q in seen for k in q} <= {"latitude", "longitude", "start_date", "end_date", "past_days", "forecast_days", "hourly", "timezone"}
    with factory() as s:
        rows = {r.source_record_id: r for r in s.query(ActivityWeather)}
        assert rows["0"].final and rows["0"].temperature == 20.0 and not rows["2"].final
        assert s.query(WeatherHour).count() > 0
        assert WX.forecast(s, now) and not WX.pending(s, now)
    seen.clear()
    WX.refresh(factory, date(2026, 10, 22), now + timedelta(hours=1), fake_open_meteo(seen))
    assert [h for h, _ in seen] == ["api.open-meteo.com"]  # only the unsettled recent session; archive never again
    with factory() as s:
        WX.set_enabled(s, False)
    assert WX.refresh(factory, date(2026, 10, 22), now + timedelta(hours=5), fake_open_meteo(seen)) == 0
