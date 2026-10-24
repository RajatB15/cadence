"""Repeated routes: which sessions covered the same ground, and how your effort on it has changed.

Matching uses only what Garmin's activity summary already holds (start and end coordinates, bounding box, distance,
elevation gain), so it is offline, makes no API calls and needs no FIT decode:
- same sport, start points within START_M, end points within END_M, distances within DISTANCE_TOL;
- when both summaries carry a bounding box, the boxes must overlap (intersection over union ≥ BOX_IOU);
- when both carry elevation gain, it must agree within max(ELEV_MIN_M, ELEV_TOL).
Clusters are anchored on their earliest session (no chaining, so a route can't drift into another one). Out-and-backs
walked in the other direction are a different route. This is a fingerprint, not a map match: two different loops that
share a start, bounding box, length and climb would be merged.

Comparison is effort-aware, not a race: pace on its own mixes fitness with how hard you went. For runs, aerobic
efficiency (speed per beat above resting HR, heat-adjusted when your heat cost is known) is compared; a Theil–Sen
slope with its confidence interval says whether efficiency on this route moved (n ≥ TREND_MIN). Weather is shown
beside each effort as context and is not used to adjust pace.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import date
from statistics import median

import numpy as np
from scipy import stats

START_M, END_M = 250.0, 350.0
DISTANCE_TOL = 0.07
BOX_IOU = 0.55
ELEV_MIN_M, ELEV_TOL = 40.0, 0.35
MIN_EFFORTS = 3
TREND_MIN = 5
FAMILIES = ("run", "ride")
GENERIC_NAMES = {"running", "run", "morning run", "afternoon run", "evening run", "lunch run", "night run", "cycling", "ride",
                 "morning ride", "afternoon ride", "evening ride", "lunch ride", "night ride", "outdoor run", "outdoor ride"}
MAX_EFFORTS = 40


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def signature(summary: dict | None) -> dict | None:
    """The geometry fingerprint of an activity summary, or None without GPS start coordinates."""
    if not summary:
        return None
    lat, lon = _num(summary.get("startLatitude")), _num(summary.get("startLongitude"))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    box = [_num(summary.get(k)) for k in ("minLatitude", "maxLatitude", "minLongitude", "maxLongitude")]
    return {
        "start": (lat, lon),
        "end": (e_lat, e_lon) if (e_lat := _num(summary.get("endLatitude"))) is not None and (e_lon := _num(summary.get("endLongitude"))) is not None else None,
        "box": tuple(box) if all(b is not None for b in box) and box[0] < box[1] and box[2] < box[3] else None,
        "elev": _num(summary.get("elevationGain")),
    }


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _box_iou(a: tuple, b: tuple) -> float:
    lat = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    lon = max(0.0, min(a[3], b[3]) - max(a[2], b[2]))
    inter = lat * lon
    union = (a[1] - a[0]) * (a[3] - a[2]) + (b[1] - b[0]) * (b[3] - b[2]) - inter
    return inter / union if union > 0 else 0.0


def same_route(a: dict, b: dict) -> bool:
    """a, b: signature plus "distance_m"."""
    if not a["distance_m"] or not b["distance_m"] or abs(a["distance_m"] - b["distance_m"]) / a["distance_m"] > DISTANCE_TOL:
        return False
    if haversine_m(a["start"], b["start"]) > START_M:
        return False
    if a["end"] and b["end"] and haversine_m(a["end"], b["end"]) > END_M:
        return False
    if a["box"] and b["box"] and _box_iou(a["box"], b["box"]) < BOX_IOU:
        return False
    if a["elev"] is not None and b["elev"] is not None and abs(a["elev"] - b["elev"]) > max(ELEV_MIN_M, ELEV_TOL * max(a["elev"], b["elev"])):
        return False
    return True


def cluster(items: list[dict]) -> list[list[dict]]:
    """items: {"id", "day", "family", "distance_m", **signature}; each is placed with the first matching earlier anchor."""
    groups: list[list[dict]] = []
    for item in sorted(items, key=lambda i: (i["day"], i["id"])):
        for g in groups:
            if g[0]["family"] == item["family"] and same_route(g[0], item):
                g.append(item)
                break
        else:
            groups.append([item])
    return groups


def _loop(sig: dict) -> bool | None:
    return haversine_m(sig["start"], sig["end"]) <= END_M if sig["end"] else None


def _name(members: list[dict], distance_km: float) -> str:
    names = Counter(m["name"] for m in members if m["name"] and m["name"].strip().lower() not in GENERIC_NAMES)
    if names and names.most_common(1)[0][1] >= 2:
        return names.most_common(1)[0][0]
    loop = _loop(members[0])
    shape = "loop" if loop else "point-to-point" if loop is False else "route"
    return f"{distance_km:.1f} km {shape}"


def _effort(m: dict, ef: dict | None, weather: dict | None) -> dict:
    moving = m["moving_s"]
    return {
        "id": m["id"], "day": m["day"], "time_s": round(moving), "pace_s": round(moving / m["distance_m"] * 1000),
        "distance_km": round(m["distance_m"] / 1000, 2), "avg_hr": m["avg_hr"], "load": round(m["load"]),
        "ef": ef["ef"] if ef else None, "ef_hr": ef["hr"] if ef else None,
        "temperature": weather.get("temperature") if weather else None, "dew_point": weather.get("dew_point") if weather else None,
        "wind": weather.get("wind") if weather else None, "hot": bool(weather.get("hot")) if weather else None,
        "hard": m["hard"],
    }


def efficiency_trend(efforts: list[dict], end: date) -> dict | None:
    pts = [e for e in efforts if e["ef"]]
    if len(pts) < TREND_MIN or (pts[-1]["day"] - pts[0]["day"]).days < 28:
        return None
    x = np.array([(e["day"] - end).days for e in pts], dtype=float)
    y = np.array([e["ef"] for e in pts])
    slope, intercept, lo, hi = stats.theilslopes(y, x)
    before = intercept + slope * x.min()
    if before <= 0:
        return None
    span = float(x.max() - x.min())
    return {"n": len(pts), "span_days": int(span), "change_pct": round(slope * span / before * 100, 1),
            "ci_pct": [round(lo * span / before * 100, 1), round(hi * span / before * 100, 1)], "significant": bool(lo > 0 or hi < 0)}


def build(acts: list, geo: dict[int, dict], eff: list[dict], weather: dict[int, dict], end: date) -> dict:
    """acts: Act objects; geo: activity id → summary (raw Garmin fields); eff: efficiency points; weather: id → conditions."""
    ef_by_id = {p["id"]: p for p in eff}
    items = []
    gps = 0
    for a in acts:
        if a.family not in FAMILIES or not a.distance_m or a.distance_m < 1500 or not a.moving_s or a.moving_s < 300:
            continue
        sig = signature(geo.get(a.id))
        if sig is None:
            continue
        gps += 1
        items.append({**sig, "id": a.id, "day": a.day, "family": a.family, "distance_m": a.distance_m, "moving_s": a.moving_s,
                      "avg_hr": round(a.avg_hr) if a.avg_hr else None, "load": a.load, "name": a.name,
                      "hard": bool(a.zones_s) and (sum(a.zones_s[3:5]) / max(sum(a.zones_s), 1) >= 0.2 or (a.anaerobic_te or 0) >= 3.0)})
    if not gps:
        return {"has_geo": False, "n_with_gps": 0, "routes": [], "reason": "No activity has GPS start coordinates in the vault yet."}
    routes = []
    for g in cluster(items):
        if len(g) < MIN_EFFORTS:
            continue
        distance_km = median(m["distance_m"] for m in g) / 1000
        efforts = [_effort(m, ef_by_id.get(m["id"]) if m["family"] == "run" else None, weather.get(m["id"])) for m in g]
        best = min(efforts, key=lambda e: e["time_s"])
        running_best = math.inf
        for e in efforts:
            e["pr"] = e["time_s"] < running_best
            running_best = min(running_best, e["time_s"])
        latest, prior = efforts[-1], efforts[:-1]
        prior_ef = [e["ef"] for e in prior if e["ef"]]
        temps = [e["temperature"] for e in prior if e["temperature"] is not None]
        routes.append({
            "id": g[0]["id"], "name": _name(g, distance_km), "sport": g[0]["family"], "n": len(g), "distance_km": round(distance_km, 1),
            "loop": _loop(g[0]), "first": g[0]["day"], "last": g[-1]["day"], "elevation_m": round(median([m["elev"] for m in g if m["elev"] is not None]))
            if any(m["elev"] is not None for m in g) else None,
            "best": {"id": best["id"], "day": best["day"], "time_s": best["time_s"]},
            "median_time_s": round(median(e["time_s"] for e in efforts)),
            "latest": {**latest, "vs_prior": {
                "time_s": latest["time_s"] - round(median(e["time_s"] for e in prior)),
                "avg_hr": round(latest["avg_hr"] - median(e["avg_hr"] for e in prior if e["avg_hr"]), 1)
                if latest["avg_hr"] and any(e["avg_hr"] for e in prior) else None,
                "ef_pct": round((latest["ef"] / median(prior_ef) - 1) * 100, 1) if latest["ef"] and len(prior_ef) >= 2 else None,
                "temperature": round(latest["temperature"] - median(temps), 1) if latest["temperature"] is not None and len(temps) >= 2 else None,
            }},
            "trend": efficiency_trend(efforts, end) if g[0]["family"] == "run" else None,
            "efforts": efforts[-MAX_EFFORTS:],
        })
    routes.sort(key=lambda r: (r["last"], r["n"]), reverse=True)
    return {"has_geo": True, "n_with_gps": gps, "routes": routes, "reason": None if routes else f"No route has been covered {MIN_EFFORTS}+ times yet."}
