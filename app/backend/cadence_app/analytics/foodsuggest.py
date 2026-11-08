"""What to eat now: rank things you have eaten before against what is left of the day. Deterministic, no model.

Pure: `suggest` takes plain numbers and candidate dicts and returns the ranked picks with the facts behind each score.
Loading is in `food_quick.py`; the sentences come from `notes.food_suggestion_reasons` (never from here).

Method (docs/food-logging-design.md section 2f). A candidate is one of your usual combinations for this meal, a saved
meal, or a single dish you have logged before. It is scored on four terms, each 0..1:

    fit_kcal  = 1 - clamp(|candidate kcal - kcal for this slot| / kcal for this slot)       slot = what is left / slots left
    fit_prot  = clamp(candidate protein / protein still to reach for this slot)               unknown protein scores 0 and is flagged
    fit_micro = mean over the (up to 2) biggest reference shortfalls of clamp(amount / (0.25 x reference))   known amounts only
    habit     = frecency of its dishes (analytics/foodrank.py), 0..1

    score = 0.35 fit_kcal + 0.30 fit_prot + 0.15 fit_micro + 0.20 habit

A term whose input is missing (no target yet, protein goal reached, no micronutrient figures) is dropped and the others
are re-weighted to sum to 1, so missing data never counts as a bad or good fit. Micronutrient gaps use the reference
amounts in `nutrients.py` (WHO / FDA Daily Values, context only) and show only after 3 logged days. Minimum data: 10
logged foods in the history; below that the answer is "insufficient". Suggestions are about fit with your own log, not
about whether a food is good or bad, and nothing here is medical advice.
"""

from __future__ import annotations

W_KCAL, W_PROT, W_MICRO, W_HABIT = 0.35, 0.30, 0.15, 0.20
MIN_HISTORY_ENTRIES = 10
MIN_LOGGED_DAYS_FOR_GAPS = 3
MICRO_SHARE = 0.25
MAX_GAPS = 2
MAX_SUGGESTIONS = 3


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def micro_gaps(rows: list[dict], logged_days: int) -> list[dict]:
    """The biggest shortfalls against a reference to reach. `rows` = nutrients.summarise output for the day so far.
    Nutrients no food reported are left out (unknown, not zero); limits (sodium, saturated fat) are never 'gaps'."""
    if logged_days < MIN_LOGGED_DAYS_FOR_GAPS:
        return []
    short = [r for r in rows if r["kind"] == "target" and r["reference"] and r["amount"] is not None and r["amount"] < r["reference"]]
    short.sort(key=lambda r: (r["amount"] / r["reference"], r["key"]))
    return [{"key": r["key"], "label": r["label"], "unit": r["unit"], "reference": r["reference"], "have": r["amount"]} for r in short[:MAX_GAPS]]


def score(c: dict, *, budget: float | None, protein_slot: float | None, gaps: list[dict]) -> dict:
    parts: dict[str, float | None] = {"fit_kcal": None, "fit_prot": None, "fit_micro": None, "habit": clamp(c.get("habit") or 0.0)}
    if budget:
        parts["fit_kcal"] = 1 - clamp(abs(c["kcal"] - budget) / budget)
    protein_unknown = c.get("protein_g") is None
    if protein_slot:
        parts["fit_prot"] = 0.0 if protein_unknown else clamp(c["protein_g"] / protein_slot)
    known = [clamp(c["micros"][g["key"]] / (MICRO_SHARE * g["reference"])) for g in gaps if c.get("micros") and g["key"] in c["micros"]]
    if known:
        parts["fit_micro"] = sum(known) / len(known)
    weights = {"fit_kcal": W_KCAL, "fit_prot": W_PROT, "fit_micro": W_MICRO, "habit": W_HABIT}
    used = {k: w for k, w in weights.items() if parts[k] is not None}
    total_w = sum(used.values())
    value = sum(parts[k] * w for k, w in used.items()) / total_w
    return {"score": value, "parts": {k: None if v is None else round(v, 3) for k, v in parts.items()}, "protein_unknown": protein_unknown and bool(protein_slot)}


def suggest(*, candidates: list[dict], n_history: int, remaining_kcal: tuple[float, float] | None, protein_gap_g: float | None,
            gaps: list[dict], slots_left: int, day_logged: bool) -> dict:
    """Candidates: {label, source, items, kcal, kcal_low, kcal_high, protein_g|None, micros|None, habit 0..1, times}.
    Returns {status, needs, suggestions:[{...candidate, score, parts, facts}]}."""
    if n_history < MIN_HISTORY_ENTRIES:
        return {"status": "insufficient", "needs": [f"{MIN_HISTORY_ENTRIES - n_history} more logged foods"], "suggestions": []}
    if not candidates:
        return {"status": "insufficient", "needs": ["a few meals logged in this slot"], "suggestions": []}
    slots = max(slots_left, 1)
    remaining = (remaining_kcal[0] + remaining_kcal[1]) / 2 if remaining_kcal else None
    budget = remaining / slots if remaining and remaining > 0 else None
    protein_slot = protein_gap_g / slots if protein_gap_g and protein_gap_g > 0 else None
    scored = []
    for c in candidates:
        s = score(c, budget=budget, protein_slot=protein_slot, gaps=gaps)
        micro_hits = [{"label": g["label"], "unit": g["unit"], "amount": round(c["micros"][g["key"]], 1), "pct_of_reference": round(c["micros"][g["key"]] / g["reference"] * 100)}
                      for g in gaps if c.get("micros") and g["key"] in c["micros"] and c["micros"][g["key"]] > 0]
        facts = {"budget_kcal": None if budget is None else round(budget), "remaining_kcal": None if remaining is None else round(remaining),
                 "protein_gap_g": None if protein_gap_g is None or protein_gap_g <= 0 else round(protein_gap_g), "micro_hits": micro_hits,
                 "day_logged": day_logged, "protein_unknown": s["protein_unknown"], "times": c.get("times", 0)}
        scored.append({**c, "score": round(s["score"], 3), "parts": s["parts"], "facts": facts})
    scored.sort(key=lambda c: (-c["score"], c["label"]))
    return {"status": "ok", "needs": [], "suggestions": scored[:MAX_SUGGESTIONS]}
