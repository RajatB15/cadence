"""Decode archived FIT files into chartable streams plus every other message, verbatim."""

from __future__ import annotations

import math
import zipfile
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from garmin_fit_sdk import Decoder, Stream

SEMICIRCLE_TO_DEG = 180 / 2**31
MAX_FIT_BYTES = 50 * 1024 * 1024
MAX_POINTS = 1200
MAX_ROUTE_POINTS = 1500
TRACK_FIELDS = ("lat", "lon", "t", "hr", "speed", "alt", "dist")
# High-volume messages are charted/summarized instead of returned row by row.
STREAMED = {"record_mesgs", "gps_metadata_mesgs"}
PREFERRED = {"speed": "enhanced_speed", "altitude": "enhanced_altitude", "respiration_rate": "enhanced_respiration_rate"}
STEP_FAMILIES = {"run", "walk"}


class FitError(Exception):
    pass


def read_fit_bytes(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if m.filename.lower().endswith(".fit")]
        if not members:
            raise FitError("Archive has no FIT file")
        member = max(members, key=lambda m: m.file_size)
        if member.file_size > MAX_FIT_BYTES:
            raise FitError("FIT file is unexpectedly large")
        return archive.read(member)


def _clean(value: Any, offset: timedelta, key: str = "") -> Any:
    if isinstance(value, datetime):
        return (value.replace(tzinfo=None) + offset).isoformat()
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else round(value, 5)
    if isinstance(value, int) and not isinstance(value, bool) and key.endswith(("position_lat", "position_long")):
        return round(value * SEMICIRCLE_TO_DEG, 6)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, (list, tuple)):
        return [_clean(v, offset, key) for v in value]
    if isinstance(value, dict):
        return {(k if isinstance(k, str) else f"field_{k}"): _clean(v, offset, str(k)) for k, v in value.items()}
    return value


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return None if isinstance(value, float) and (math.isnan(value) or math.isinf(value)) else float(value)


def _bucket(values: list[list[float | None]], size: int) -> list[list[float | None]]:
    n = len(values[0]) if values else 0
    if n <= size:
        return values
    step = n / size
    out: list[list[float | None]] = [[] for _ in values]
    for b in range(size):
        lo, hi = int(b * step), max(int((b + 1) * step), int(b * step) + 1)
        for i, series in enumerate(values):
            chunk = [v for v in series[lo:hi] if v is not None]
            out[i].append(round(sum(chunk) / len(chunk), 4) if chunk else None)
    return out


def _streams(records: list[dict], family: str) -> tuple[dict, dict, list, dict]:
    if not records:
        return {}, {}, [], {}
    start = next((r["timestamp"] for r in records if isinstance(r.get("timestamp"), datetime)), None)
    fields: set[str] = set()
    for r in records:
        fields.update(k for k, v in r.items() if isinstance(k, str) and _num(v) is not None)
    fields -= {"position_lat", "position_long", "timestamp"}
    for plain, enhanced in PREFERRED.items():
        if enhanced in fields:
            fields.discard(plain)
    columns: dict[str, list[float | None]] = {name: [] for name in sorted(fields)}
    times: list[float | None] = []
    route: list[list[float]] = []
    track: dict[str, list] = {k: [] for k in TRACK_FIELDS}
    for r in records:
        ts = r.get("timestamp")
        t = (ts - start).total_seconds() if isinstance(ts, datetime) and start else None
        times.append(t)
        for name in columns:
            columns[name].append(_num(r.get(name)))
        lat, lon = _num(r.get("position_lat")), _num(r.get("position_long"))
        if lat is not None and lon is not None:
            point = [round(lat * SEMICIRCLE_TO_DEG, 6), round(lon * SEMICIRCLE_TO_DEG, 6)]
            route.append(point)
            values = {
                "lat": point[0], "lon": point[1], "t": t, "hr": _num(r.get("heart_rate")),
                "speed": _num(r.get("enhanced_speed", r.get("speed"))),
                "alt": _num(r.get("enhanced_altitude", r.get("altitude"))), "dist": _num(r.get("distance")),
            }
            for k in TRACK_FIELDS:
                track[k].append(values[k])

    renamed = {PREFERRED_REVERSE.get(k, k): v for k, v in columns.items()}
    if family in STEP_FAMILIES and "cadence" in renamed:
        # FIT running cadence counts one foot; Garmin displays steps/min for both feet.
        frac = renamed.pop("fractional_cadence", None)
        renamed["cadence"] = [
            None if c is None else 2 * (c + ((frac[i] or 0) if frac else 0)) for i, c in enumerate(renamed["cadence"])
        ]
    stats = {}
    for name, series in renamed.items():
        present = [v for v in series if v is not None]
        if present:
            stats[name] = {
                "min": round(min(present), 4),
                "avg": round(sum(present) / len(present), 4),
                "max": round(max(present), 4),
                "count": len(present),
            }
    names = [n for n in renamed if n in stats]
    sampled = _bucket([times] + [renamed[n] for n in names], MAX_POINTS)
    streams = {"t": sampled[0], **dict(zip(names, sampled[1:]))}
    if len(route) > MAX_ROUTE_POINTS:
        stride = len(route) / MAX_ROUTE_POINTS
        keep = [int(i * stride) for i in range(MAX_ROUTE_POINTS)] + [len(route) - 1]
        route = [route[i] for i in keep]
        track = {k: [v[i] for i in keep] for k, v in track.items()}
    track = {k: v for k, v in track.items() if any(x is not None for x in v)} if route else {}
    return streams, stats, route, track


PREFERRED_REVERSE = {v: k for k, v in PREFERRED.items()}


def _zones(messages: dict, offset: timedelta) -> list[dict] | None:
    for msg in messages.get("time_in_zone_mesgs", []):
        if msg.get("reference_mesg") != "session":
            continue
        times = msg.get("time_in_hr_zone") or []
        bounds = msg.get("hr_zone_high_boundary") or []
        if not times:
            return None
        zones = []
        for i, seconds in enumerate(times):
            low = bounds[i - 1] if 0 < i <= len(bounds) else (0 if i == 0 else None)
            high = bounds[i] if i < len(bounds) else None
            zones.append({"zone": i, "low": low, "high": high, "seconds": _clean(seconds, offset)})
        return zones
    return None


@lru_cache(maxsize=24)
def _decode_cached(path: str, mtime: float, family: str, offset_min: int) -> dict:
    del mtime  # cache key only: a re-downloaded file invalidates the entry
    offset = timedelta(minutes=offset_min)
    try:
        data = read_fit_bytes(Path(path))
        messages, errors = Decoder(Stream.from_byte_array(bytearray(data))).read(
            convert_datetimes_to_dates=True, merge_heart_rates=True
        )
    except (FitError, zipfile.BadZipFile, OSError) as exc:
        return {"error": str(exc)}
    except Exception as exc:  # pylint: disable=broad-exception-caught  # third-party decoder boundary
        return {"error": f"FIT decode failed ({type(exc).__name__})"}

    streams, stats, route, track = _streams(messages.get("record_mesgs", []), family)
    named = {k: v for k, v in messages.items() if isinstance(k, str)}
    return {
        "streams": streams,
        "stream_stats": stats,
        "route": route,
        "track": track,
        "zones": _zones(named, offset),
        "messages": {k: _clean(v, offset) for k, v in named.items() if k not in STREAMED},
        "streamed_counts": {k: len(named[k]) for k in STREAMED if k in named},
        "unknown_messages": sorted(
            (
                {"id": k, "count": len(v), "sample": _clean(v[:3], offset)}
                for k, v in messages.items()
                if not isinstance(k, str)
            ),
            key=lambda m: -m["count"],
        ),
        "decode_errors": [str(e) for e in errors][:5],
    }


def decode(path: Path, family: str, offset_min: int) -> dict:
    return _decode_cached(str(path), path.stat().st_mtime, family, offset_min)


def offset_minutes(label: str) -> int:
    """'UTC+05:30' -> 330; unknown labels -> 0."""
    if not label.startswith("UTC") or len(label) != 9:
        return 0
    sign = -1 if label[3] == "-" else 1
    try:
        return sign * (int(label[4:6]) * 60 + int(label[7:9]))
    except ValueError:
        return 0
