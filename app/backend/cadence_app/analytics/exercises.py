"""Strength-session content: exercise dictionary, class-text parsing and heart-rate block segmentation.

The dictionary lives in exercises.json (categories, exercises with aliases, fallback regex rules) so it can be edited
without touching code. Categories are movement patterns (squat, hinge, lunge, push, pull, carry, core, plyometric,
olympic, calves, hips) plus cardio, drill and mobility; the pattern taxonomy follows the usual strength-and-conditioning
split into knee-dominant, hip-dominant, single-leg, push, pull and carry work (e.g. NSCA, Essentials of Strength
Training and Conditioning). Which exercise belongs where is a judgement call, not a measurement.

The watch records these classes as one long set at ~0.5 Hz heart rate, so exercises are never located in time.
What the heart rate can show is the class structure: warm-up, the blocks in order, cool-down. Segments are found by
optimal partitioning (dynamic programming over 15-second bins, least squares on mean heart rate and its
within-bin variability, minimum segment lengths), the standard offline changepoint approach.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import fmean, pstdev

import numpy as np

DATA = json.loads((Path(__file__).with_name("exercises.json")).read_text(encoding="utf-8"))
CATEGORIES: dict[str, dict] = DATA["categories"]
PATTERNS = tuple(CATEGORIES)
MUSCLES = {k: v["muscles"] for k, v in CATEGORIES.items()}
LOWER = {k for k, v in CATEGORIES.items() if v["lower"]}
# Ordered: the first matching rule wins, so specific phrases come before generic words. Used for names not listed.
RULES: tuple[tuple[str, str], ...] = tuple((rx, cat) for rx, cat in DATA["rules"])
LOADED = DATA["loaded_pattern"]
# Words that change how an exercise is done, not what it is: tried again with these removed before the rules.
MODIFIERS = r"\b(barbell|dumbbells?|db|kettlebell|kb|wtd|weighted|single arm|one arm|alternating|banded|seated|standing|tempo|paused?|loaded)\b"


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", name.lower().replace("'", ""))).strip()


def _keys(name: str) -> list[str]:
    n = _norm(name)
    words = n.split()
    plural = " ".join(words[:-1] + [words[-1][:-1]]) if words and len(words[-1]) > 3 and words[-1].endswith("s") else n
    return [n, plural]


def _index() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in DATA["exercises"]:
        for alias in [e["name"], *e.get("aliases", [])]:
            for k in _keys(alias):
                out.setdefault(k, e)
    return out


INDEX = _index()
NOISE = r"^(book now|what to bring|cancel|join|share|details|book|waitlist|\d{1,2}:\d{2}.*|\d+%?|[^a-z]*)$"
HEAVY_BLOCK = r"strong|strength|heavy|power|max"
CONDITIONING_BLOCK = r"hiit|interval|conditioning|endurance|metcon|amrap|emom|cardio|anaerobic|burn|tabata|finisher"
CONDITIONING_PATTERNS = {"plyometric", "cardio"}
CORE_BLOCK = r"\bcore\b|\babs?\b|trunk"


def lookup(name: str) -> dict | None:
    """The dictionary entry for a name, ignoring case, punctuation, plurals, a leading count and equipment words."""
    n = re.sub(r"^\d+(\.\d+)?\s*(x\s*\d+\s*)?", "", _norm(name))
    for candidate in (n, re.sub(MODIFIERS, " ", n)):
        for k in _keys(candidate):
            if k.strip() in INDEX:
                return INDEX[k.strip()]
    return None


def classify(name: str) -> dict:
    n = name.lower()
    entry = lookup(name)
    pattern = entry["category"] if entry else next((p for rx, p in RULES if re.search(rx, n)), None)
    loaded = bool(re.search(LOADED, n)) or bool(entry and entry.get("loaded"))
    out = {"name": name.strip(), "pattern": pattern, "muscles": (entry or {}).get("muscles") or MUSCLES.get(pattern, []), "loaded": loaded}
    if entry and entry.get("modality"):
        out["modality"] = entry["modality"]
    return out


# "Endurance WOD: 50s ON, 15s OFF", "PACE Along: 40s ON, 20s OFF": a work/rest interval line heads a block.
INTERVAL_TITLE = r"\b\d+\s*(s|sec|secs|seconds|min|mins)\s*(on|work)\b.{0,12}\b\d+\s*(s|sec|secs|seconds|min|mins)\s*(off|rest)\b"


def _interval_title(line: str) -> bool:
    return len(line.split()) <= 9 and bool(re.search(INTERVAL_TITLE, line.lower()))


def _title_like(line: str) -> bool:
    # Taglines end in sentence punctuation or run long; titles are short labels.
    return _interval_title(line) or (len(line.split()) <= 5 and not re.search(r"[.!?,]$", line) and "," not in line)


def _header_word(line: str) -> bool:
    """Lines like "Core" or "Finisher" between exercises are block titles, not unknown exercises."""
    return bool(re.search(f"{CORE_BLOCK}|{CONDITIONING_BLOCK}|{HEAVY_BLOCK}|warm|cool|block|round|circuit|part|section|superset",
                          line.lower()))


def parse(text: str) -> list[dict]:
    """Blocks from pasted class text (e.g. iPhone Live Text of a booking screenshot).

    Exercises are lines the dictionary recognises, plus unrecognised lines sandwiched between exercises. A block's
    name is the last title-like line before its first exercise. A line starting with "#" is always a block title.
    """
    lines = [re.sub(r"^\d{1,2}[.)]\s+", "", re.sub(r"\s+", " ", ln).strip(" •-–—*\t")) for ln in text.splitlines()]  # "1. Air Squats"
    lines = [ln for ln in lines if ln and not re.match(NOISE, ln.lower())]
    known = [ln.startswith("#") is False and classify(ln)["pattern"] is not None for ln in lines]
    is_ex = list(known)
    for i in range(1, len(lines) - 1):
        if not lines[i].startswith("#") and known[i - 1] and known[i + 1] and _title_like(lines[i]) and not _header_word(lines[i]) and not _interval_title(lines[i]):
            is_ex[i] = True
    blocks: list[dict] = []
    title: str | None = None
    current: dict | None = None
    explicit = False  # after a "#" title, every line is an exercise until the next title
    for line, ex in zip(lines, is_ex):
        if line.startswith("#"):
            title, current, explicit = line.lstrip("# ").strip(), None, True
            continue
        if ex or explicit:
            if current is None:
                current = {"name": title or f"Block {len(blocks) + 1}", "exercises": []}
                blocks.append(current)
                title = None
            current["exercises"].append(classify(line))
        else:
            if _title_like(line):
                title = line
            current = None if title else current
    for b in blocks:
        b["kind"] = block_kind(b)
    return blocks


def block_kind(block: dict) -> str:
    name = block["name"].lower()
    patterns = [e["pattern"] for e in block["exercises"]]
    if re.search(CORE_BLOCK, name) or (patterns and patterns.count("core") / len(patterns) > 0.5):
        return "core"
    if re.search(CONDITIONING_BLOCK, name) or _interval_title(name) or (patterns and sum(p in CONDITIONING_PATTERNS for p in patterns) / len(patterns) >= 0.5):
        return "conditioning"
    if re.search(HEAVY_BLOCK, name) or any(e["loaded"] and e["pattern"] in LOWER | {"push", "pull"} for e in block["exercises"]):
        return "strength"
    return "mixed"


def summary(blocks: list[dict]) -> dict:
    """Movement patterns trained, and whether this counts as heavy lower-body work."""
    patterns: dict[str, int] = {}
    for b in blocks:
        for e in b["exercises"]:
            if e["pattern"]:
                patterns[e["pattern"]] = patterns.get(e["pattern"], 0) + 1
    heavy_lower = any(b["kind"] == "strength" and any(e["pattern"] in LOWER for e in b["exercises"]) for b in blocks)
    unknown = [e["name"] for b in blocks for e in b["exercises"] if e["pattern"] is None]
    return {"patterns": patterns, "heavy_lower": heavy_lower, "unknown": unknown,
            "exercises": sum(len(b["exercises"]) for b in blocks)}


# ---- heart-rate segmentation ------------------------------------------------------------------

BIN_S = 15
MIN_SEGMENT_S = {"warmup": 180, "block": 240, "cooldown": 120}


def _bins(t: list, hr: list) -> list[tuple[float, float, float, float]]:
    """(start s, end s, mean HR, HR spread) per 15-second bin."""
    buckets: dict[int, list[float]] = {}
    for ti, hi in zip(t, hr):
        if ti is not None and hi:
            buckets.setdefault(int(ti // BIN_S), []).append(hi)
    return [(k * BIN_S, (k + 1) * BIN_S, fmean(v), pstdev(v) if len(v) > 1 else 0.0) for k, v in sorted(buckets.items())]


def segment(t: list, hr: list, blocks: list[dict], zones: dict | None = None) -> dict | None:
    """Warm-up, each block in order, cool-down, fitted to the session's heart rate."""
    bins = _bins(t, hr)
    k = len(blocks) + 2
    mins = [MIN_SEGMENT_S["warmup"]] + [MIN_SEGMENT_S["block"]] * len(blocks) + [MIN_SEGMENT_S["cooldown"]]
    n = len(bins)
    if not blocks or n * BIN_S < sum(mins):
        return None
    mean_hr = [b[2] for b in bins]
    spread = [b[3] for b in bins]
    sd_m, sd_s = (pstdev(mean_hr) or 1.0), (pstdev(spread) or 1.0)
    x = np.column_stack([np.array(mean_hr) / sd_m, np.array(spread) / sd_s])
    # Prefix sums give every segment's within-segment squared deviation in O(1).
    p1 = np.vstack([np.zeros(2), np.cumsum(x, axis=0)])
    p2 = np.vstack([np.zeros(2), np.cumsum(x * x, axis=0)])

    def costs(i: np.ndarray, j: int) -> np.ndarray:
        m = (j - i)[:, None]
        return ((p2[j] - p2[i]) - (p1[j] - p1[i]) ** 2 / m).sum(axis=1)

    def cost(i: int, j: int) -> float:
        return float(costs(np.array([i]), j)[0])

    min_bins = [max(1, s // BIN_S) for s in mins]
    best = np.full((k + 1, n + 1), np.inf)
    back = np.zeros((k + 1, n + 1), dtype=int)
    best[0][0] = 0.0
    for seg in range(1, k + 1):
        first = sum(min_bins[: seg - 1])
        for j in range(sum(min_bins[:seg]), n + 1):
            i = np.arange(first, j - min_bins[seg - 1] + 1)
            if not len(i):
                continue
            c = best[seg - 1][i] + costs(i, j)
            pick = int(np.argmin(c))
            best[seg][j], back[seg][j] = c[pick], i[pick]
    if not np.isfinite(best[k][n]):
        return None
    cuts = [n]
    for seg in range(k, 0, -1):
        cuts.append(int(back[seg][cuts[-1]]))
    cuts.reverse()
    total = cost(0, n) or 1.0
    names = ["Warm-up"] + [b["name"] for b in blocks] + ["Cool-down"]
    kinds = ["warmup"] + [b["kind"] for b in blocks] + ["cooldown"]
    segments = []
    for idx in range(k):
        i, j = cuts[idx], cuts[idx + 1]
        hrs = mean_hr[i:j]
        seg = {"name": names[idx], "kind": kinds[idx], "start_s": bins[i][0], "end_s": bins[j - 1][1], "avg_hr": round(fmean(hrs)),
               "max_hr": round(max(hrs))}
        if zones:
            floors = zones["floors"]
            seg["hard_pct"] = round(sum(1 for h in hrs if h >= floors[3]) / len(hrs) * 100)
        segments.append(seg)
    return {"segments": segments, "fit": round(1 - best[k][n] / total, 2)}
