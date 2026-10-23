"""Weather from Open-Meteo (free, no account): history for outdoor sessions and a 7-day forecast for planning.

Only coordinates rounded to 0.1° (~10 km) and dates leave the Mac; routes, times of day and health data never do.
Settled history (archive) is fetched once per location and period; the forecast is refreshed at most every 3 hours.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import fmean

import httpx
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from cadence_app.garmin import vault
from cadence_app.models import Activity, ActivityWeather, AppSetting, WeatherHour

log = logging.getLogger(__name__)
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,wind_speed_10m"
ARCHIVE_LAG_DAYS = 6  # the reanalysis archive trails real time by several days; newer days come from the forecast model
FORECAST_REFRESH = timedelta(hours=3)
ENABLED_KEY = "weather_enabled"
HOME_KEY = "weather_home"


def enabled(session: Session) -> bool:
    row = session.get(AppSetting, ENABLED_KEY)
    return row is None or row.value == "1"


def set_enabled(session: Session, on: bool) -> None:
    row = session.get(AppSetting, ENABLED_KEY)
    if row:
        row.value = "1" if on else "0"
    else:
        session.add(AppSetting(key=ENABLED_KEY, value="1" if on else "0"))
    session.commit()


def rounded(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, 1), round(lon, 1)


def _parse(payload: dict, source: str, lat: float, lon: float, now: datetime) -> list[dict]:
    h = payload.get("hourly") or {}
    times = h.get("time") or []
    cols = {k: h.get(k) or [None] * len(times) for k in HOURLY.split(",")}
    rows = []
    for i, t in enumerate(times):
        temp = cols["temperature_2m"][i]
        if temp is None:
            continue  # archive hours not yet available come back as nulls
        rows.append({"lat": lat, "lon": lon, "ts": datetime.fromisoformat(t), "temperature": temp, "humidity": cols["relative_humidity_2m"][i],
                     "dew_point": cols["dew_point_2m"][i], "apparent": cols["apparent_temperature"][i], "wind": cols["wind_speed_10m"][i],
                     "source": source, "fetched_at": now})
    return rows


def _store(session: Session, rows: list[dict]) -> None:
    if rows:
        session.execute(insert(WeatherHour).prefix_with("OR REPLACE"), rows)
        session.commit()


def _get(http: httpx.Client, url: str, params: dict) -> dict:
    r = http.get(url, params={**params, "hourly": HOURLY, "timezone": "GMT"})
    r.raise_for_status()
    return r.json()


def _archive_covered(session: Session, lat: float, lon: float, start: date, end: date) -> bool:
    n = session.scalar(select(func.count()).where(
        WeatherHour.lat == lat, WeatherHour.lon == lon, WeatherHour.source == "archive",
        WeatherHour.ts >= datetime.combine(start, datetime.min.time()), WeatherHour.ts < datetime.combine(end + timedelta(days=1), datetime.min.time()),
    ))
    return n >= 24 * ((end - start).days + 1) * 0.95


def _conditions(session: Session, lat: float, lon: float, start: datetime, seconds: float) -> dict | None:
    lo = start.replace(minute=0, second=0, microsecond=0)
    hi = start + timedelta(seconds=max(seconds, 1800))
    rows = session.scalars(select(WeatherHour).where(WeatherHour.lat == lat, WeatherHour.lon == lon, WeatherHour.ts >= lo, WeatherHour.ts <= hi)).all()
    if not rows:
        return None

    def avg(attr: str) -> float | None:
        values = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return round(fmean(values), 1) if values else None

    return {"temperature": avg("temperature"), "humidity": avg("humidity"), "dew_point": avg("dew_point"), "apparent": avg("apparent"),
            "wind": avg("wind"), "final": all(r.source == "archive" for r in rows)}


def refresh(factory: sessionmaker, today: date, now: datetime, http: httpx.Client | None = None) -> int:
    """Fetch what's missing and fill per-session conditions. Returns the number of HTTP requests made."""
    with factory() as session:
        if not enabled(session):
            return 0
        summaries = vault.activity_summaries(session)
        settled = set(session.scalars(select(ActivityWeather.source_record_id).where(ActivityWeather.final.is_(True))))
        acts = session.execute(select(Activity.source_record_id, Activity.start_time_utc, Activity.duration_s).where(Activity.source_id == "garmin")).all()
    todo: dict[tuple[float, float], list] = defaultdict(list)
    recent_locs: Counter = Counter()
    for rid, start, duration in acts:
        s = summaries.get(rid) or {}
        lat, lon = s.get("startLatitude"), s.get("startLongitude")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        loc = rounded(lat, lon)
        if start.date() > today - timedelta(days=90):
            recent_locs[loc] += 1
        if rid not in settled:
            todo[loc].append((rid, start, duration))
    own = http is None
    http = http or httpx.Client(timeout=20)
    calls = 0
    try:
        for (lat, lon), items in todo.items():
            days = sorted({start.date() for _, start, _ in items})
            old = [d for d in days if d <= today - timedelta(days=ARCHIVE_LAG_DAYS)]
            with factory() as session:
                # One archive request per location and year of sessions; settled ranges are never fetched twice.
                for year in sorted({d.year for d in old}):
                    span = [d for d in old if d.year == year]
                    if not _archive_covered(session, lat, lon, span[0], span[-1]):
                        payload = _get(http, ARCHIVE_URL, {"latitude": lat, "longitude": lon, "start_date": span[0].isoformat(), "end_date": span[-1].isoformat()})
                        calls += 1
                        _store(session, _parse(payload, "archive", lat, lon, now))
                if any(d > today - timedelta(days=ARCHIVE_LAG_DAYS) for d in days):
                    payload = _get(http, FORECAST_URL, {"latitude": lat, "longitude": lon, "past_days": 7, "forecast_days": 1})
                    calls += 1
                    _store(session, _parse(payload, "forecast", lat, lon, now))
                for rid, start, duration in items:
                    cond = _conditions(session, lat, lon, start, duration)
                    if cond:
                        session.merge(ActivityWeather(source_id="garmin", source_record_id=rid, computed_at=now, **cond))
                session.commit()
        if recent_locs:
            calls += _refresh_forecast(factory, recent_locs.most_common(1)[0][0], now, http)
    except httpx.HTTPError as exc:
        log.warning("Weather refresh failed: %s", exc)
    finally:
        if own:
            http.close()
    return calls


def _refresh_forecast(factory: sessionmaker, home: tuple[float, float], now: datetime, http: httpx.Client) -> int:
    lat, lon = home
    with factory() as session:
        row = session.get(AppSetting, HOME_KEY)
        saved = json.loads(row.value) if row else {}
        fresh = saved.get("lat") == lat and saved.get("lon") == lon and saved.get("fetched_at") and \
            now - datetime.fromisoformat(saved["fetched_at"]) < FORECAST_REFRESH
        if fresh:
            return 0
        payload = _get(http, FORECAST_URL, {"latitude": lat, "longitude": lon, "past_days": 1, "forecast_days": 8})
        _store(session, _parse(payload, "forecast", lat, lon, now))
        value = json.dumps({"lat": lat, "lon": lon, "fetched_at": now.isoformat(), "utc_offset_seconds": payload.get("utc_offset_seconds", 0)})
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=HOME_KEY, value=value))
        session.commit()
    return 1


def pending(session: Session, now: datetime) -> bool:
    """Whether a refresh is due (cheap check used to decide whether to kick the background worker)."""
    if not enabled(session):
        return False
    row = session.get(AppSetting, HOME_KEY)
    if row is None:
        return True
    saved = json.loads(row.value)
    return now - datetime.fromisoformat(saved["fetched_at"]) >= FORECAST_REFRESH


def by_activity(session: Session, source_id: str) -> dict[int, dict]:
    rows = session.execute(
        select(Activity.id, ActivityWeather).join(
            ActivityWeather, (ActivityWeather.source_id == Activity.source_id) & (ActivityWeather.source_record_id == Activity.source_record_id)
        ).where(Activity.source_id == source_id)
    ).all()
    return {aid: {"temperature": w.temperature, "humidity": w.humidity, "dew_point": w.dew_point, "apparent": w.apparent, "wind": w.wind}
            for aid, w in rows}


def forecast(session: Session, now: datetime) -> list[dict]:
    """Next 8 days of hourly forecast at your usual location (UTC hours)."""
    row = session.get(AppSetting, HOME_KEY)
    if row is None or not enabled(session):
        return []
    home = json.loads(row.value)
    rows = session.scalars(select(WeatherHour).where(
        WeatherHour.lat == home["lat"], WeatherHour.lon == home["lon"], WeatherHour.ts >= now - timedelta(hours=2), WeatherHour.ts <= now + timedelta(days=8)
    ).order_by(WeatherHour.ts)).all()
    return [{"ts": r.ts, "temperature": r.temperature, "dew_point": r.dew_point, "apparent": r.apparent, "humidity": r.humidity, "wind": r.wind} for r in rows]
