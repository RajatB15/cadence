"""Strength-session content: exercise dictionary, class-text parsing and heart-rate block segmentation.

The watch records these classes as one long set at ~0.5 Hz heart rate, so exercises are never located in time.
What the heart rate can show is the class structure: warm-up, the blocks in order, cool-down. Segments are found by
optimal partitioning (dynamic programming over 15-second bins, least squares on mean heart rate and its
within-bin variability, minimum segment lengths), the standard offline changepoint approach.
"""

from __future__ import annotations

import re
from statistics import fmean, pstdev

import numpy as np

PATTERNS = ("squat", "hinge", "lunge", "push", "pull", "carry", "core", "plyometric")
MUSCLES = {
    "squat": ["quads", "glutes"], "hinge": ["hamstrings", "glutes", "lower back"], "lunge": ["quads", "glutes", "hips"],
    "push": ["chest", "shoulders", "triceps"], "pull": ["back", "biceps"], "carry": ["grip", "core"], "core": ["core"],
    "plyometric": ["legs", "power"],
}
LOWER = {"squat", "hinge", "lunge"}
# Ordered: the first matching rule wins, so specific phrases come before generic words.
RULES: tuple[tuple[str, str], ...] = (
    (r"reverse nordic", "squat"), (r"nordic", "hinge"), (r"split squat|bulgarian|step[- ]?up|lunge|single[- ]leg squat|pistol", "lunge"),
    (r"squat|wall sit|leg press|leg extension|thruster", "squat"),
    (r"dead ?lift|\brdl\b|romanian|good morning|hip thrust|glute bridge|bridge|swing|hamstring curl|hyperextension|back extension", "hinge"),
    (r"pull[- ]?up|chin[- ]?up|row|pull ?down|lat |face pull|curl", "pull"),
    (r"push[- ]?up|press|bench|dip|fly|flye|tricep|extension", "push"),
    (r"carry|farmer|suitcase|waiter", "carry"),
    (r"jump|burpee|sprawl|skater|bound|hop|high knees|mountain climber|battle rope|jack|sprint|sled|tuck", "plyometric"),
    (r"plank|crunch|sit[- ]?up|dead ?bug|hollow|beast|bear|v[- ]?up|russian twist|pallof|leg raise|ab |abs\b|toe touch|bird dog|drag|hold", "core"),
)
LOADED = r"barbell|dumbbell|\bdb\b|kettlebell|\bkb\b|goblet|wtd|weighted|loaded|trap bar|landmine|sandbag|cable|machine"
HEAVY_BLOCK = r"strong|strength|heavy|power|max"
CONDITIONING_BLOCK = r"hiit|interval|conditioning|endurance|metcon|amrap|emom|cardio|anaerobic|burn|tabata|finisher"
CORE_BLOCK = r"\bcore\b|\babs?\b|trunk"
NOISE = r"^(book now|what to bring|cancel|join|share|details|book|waitlist|\d{1,2}:\d{2}.*|\d+%?|[^a-z]*)$"


def classify(name: str) -> dict:
    n = name.lower()
    pattern = next((p for rx, p in RULES if re.search(rx, n)), None)
    return {"name": name.strip(), "pattern": pattern, "muscles": MUSCLES.get(pattern, []), "loaded": bool(re.search(LOADED, n))}


def _title_like(line: str) -> bool:
    # Taglines end in sentence punctuation or run long; titles are short labels.
    return len(line.split()) <= 5 and not re.search(r"[.!?,]$", line) and "," not in line


def _header_word(line: str) -> bool:
    """Lines like "Core" or "Finisher" between exercises are block titles, not unknown exercises."""
    return bool(re.search(f"{CORE_BLOCK}|{CONDITIONING_BLOCK}|{HEAVY_BLOCK}|warm|cool|block|round|circuit|part|section|superset",
                          line.lower()))


def parse(text: str) -> list[dict]:
    """Blocks from pasted class text (e.g. iPhone Live Text of a booking screenshot).

    Exercises are lines the dictionary recognises, plus unrecognised lines sandwiched between exercises. A block's
    name is the last title-like line before its first exercise. A line starting with "#" is always a block title.
    """
    lines = [re.sub(r"\s+", " ", ln).strip(" •-–—*\t") for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not re.match(NOISE, ln.lower())]
    known = [ln.startswith("#") is False and classify(ln)["pattern"] is not None for ln in lines]
    is_ex = list(known)
    for i in range(1, len(lines) - 1):
        if not lines[i].startswith("#") and known[i - 1] and known[i + 1] and _title_like(lines[i]) and not _header_word(lines[i]):
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
    if re.search(CONDITIONING_BLOCK, name) or (patterns and patterns.count("plyometric") / len(patterns) >= 0.5):
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
