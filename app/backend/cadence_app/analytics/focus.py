"""Improve, part 4: a four-week focus and the planner hints it may pass on (pure).

A focus is a suggestion you accept; nothing is automatic. It takes the top three "start" rules with DISTINCT domains
(sleep, intensity, volume, recovery, alcohol, habit) ranked by impact x confidence x ease. A watch flag of severity "act"
overrides everything: the focus becomes "recover first" with one priority.

Planner hints can only keep or reduce load. `apply_hints` never raises the weekly load band, the session count or the
long-run cap that `plan.weekly_plan` produced (its ramp, 1.25 x chronic, 1.15 x recent-week, long-run +10%, time-off,
wellbeing and absorb rules all stay in force), so a hint such as `volume_bias: up` is clamped to "hold":
- intensity_bias easier: one quality session becomes easy (never removes the last quality session of a build week
  unless the plan itself has none).
- deload_week: load band x 0.65 and at most one quality session.
- volume_bias down: load band x 0.9; hold/up: unchanged.
- add_key_session: converts one easy session into a key session (no extra session, same load band) and only in base/
  build/specific/maintain weeks with at least 95% availability and below the plan's own cap on quality sessions (2 in
  build/specific weeks with 4+ sessions, otherwise 1).
Method sources: Seiler 2010; Meeusen 2013 (see improve_sources.py).
"""

from __future__ import annotations

import copy
from datetime import date, timedelta

MAX_PRIORITIES = 3
FOCUS_DAYS = 28
OK_PHASES = {"base", "build", "specific", "maintain"}
HINT_KEYS = {"intensity_bias": {"easier"}, "add_key_session": {"vo2", "threshold"}, "deload_week": {True}, "volume_bias": {"hold", "down", "up"}}


def propose(recs: list[dict], watch: list[dict], today: date, metric: str) -> dict | None:
    """The proposed focus for one metric (None when there is nothing to propose)."""
    act = [w for w in watch if w["severity"] == "act"]
    start = today + timedelta(days=1)
    base = {"id": None, "proposed": True, "start": start, "check_on": start + timedelta(days=FOCUS_DAYS), "metric": metric}
    if act:
        return {**base, "priorities": [{"rank": 1, "_rule": "recover_first", "_domain": "recovery", "target_metrics": [metric], "planner_hint": {"intensity_bias": "easier"}}],
                "blocked_by": act[0]["id"]}
    chosen, seen = [], set()
    for r in sorted(recs, key=lambda r: (-r["score"], r["id"])):
        if r["domain"] in seen:
            continue
        seen.add(r["domain"])
        chosen.append({"rank": len(chosen) + 1, "_rule": r["id"], "_domain": r["domain"], "_numbers": r["numbers"], "target_metrics": [metric],
                       "planner_hint": clean_hint(r.get("planner_hint"))})
        if len(chosen) == MAX_PRIORITIES:
            break
    if not chosen:
        return None
    return {**base, "priorities": chosen, "blocked_by": None}


def clean_hint(hint: dict | None) -> dict:
    return {k: v for k, v in (hint or {}).items() if k in HINT_KEYS and v in HINT_KEYS[k]}


def merge_hints(priorities: list[dict]) -> dict:
    out: dict = {}
    for p in priorities:
        for k, v in clean_hint(p.get("planner_hint")).items():
            out.setdefault(k, v)
    return out


def apply_hints(plan: dict | None, hints: dict | None) -> dict | None:
    """Plan with hints applied. Returns a copy with `focus_applied` listing what was applied or why not; never raises load."""
    if plan is None:
        return None
    hints = clean_hint(hints)
    out = copy.deepcopy(plan)
    t, notes = out["targets"], []
    lo, hi = t["load"]
    phase = out["phase"]["phase"]
    avail = (out.get("time_off") or {}).get("availability", 1.0)
    quality = [s for s in out["sessions"]]
    if hints.get("deload_week"):
        t["load"] = [round(lo * 0.65), round(hi * 0.65)]
        t["hard"] = min(t["hard"], 1)
        notes.append({"hint": "deload_week", "applied": True})
    if hints.get("volume_bias") == "down":
        t["load"] = [round(t["load"][0] * 0.9), round(t["load"][1] * 0.9)]
        notes.append({"hint": "volume_bias", "applied": True})
    elif "volume_bias" in hints:
        notes.append({"hint": "volume_bias", "applied": False, "reason": "load is already held to the plan's ramp caps"})
    if hints.get("intensity_bias") == "easier":
        if t["hard"] >= 2:
            t["hard"] -= 1
            if len(out["sessions"]) >= 2:
                out["sessions"] = out["sessions"][:-1]
            notes.append({"hint": "intensity_bias", "applied": True})
        else:
            notes.append({"hint": "intensity_bias", "applied": False, "reason": "the plan already has at most one quality session"})
    if "add_key_session" in hints:
        cap = 2 if phase in ("build", "specific") and t["sessions"] >= 4 else 1  # the plan's own quality-session cap
        if phase in OK_PHASES and avail >= 0.95 and t["hard"] < cap and len(quality) < cap and t["sessions"] > t["hard"]:
            t["hard"] += 1
            notes.append({"hint": "add_key_session", "applied": True, "kind": hints["add_key_session"]})
        else:
            notes.append({"hint": "add_key_session", "applied": False, "reason": "this week's phase, availability or quality-session cap does not allow it"})
    t["load"] = [min(t["load"][0], lo), min(t["load"][1], hi)]  # the clamp: never above what the plan allowed
    out["focus_applied"] = notes
    return out
