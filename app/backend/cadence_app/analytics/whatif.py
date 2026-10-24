"""What-if replay: rerun your recent weeks with one session changed and compare the fitness model's trajectory.

Only the training-load inputs change; everything else (the other sessions, the 42/7-day fitness/fatigue model, the
EWMA acute:chronic ratio) is the same code that produces the numbers you see elsewhere, so a difference is purely what
the model says that session did. Limits worth keeping in mind:
- it is the model, not a measurement: load is Garmin's, the response curve is generic (or your personal one when
  `banister.fit` was adopted) and no sleep, illness or life stress is in it;
- an "easy" replacement keeps the session's duration at your own typical easy load per minute for that sport (median of
  your easy sessions in the previous 90 days, ≥ MIN_EASY of them), and never raises the load;
- a change is only replayed forward, so effects on later choices (you might have trained harder the next day) are not
  modelled.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from cadence_app.analytics import athlete as A
from cadence_app.analytics import banister as B

WINDOW_DAYS = 56
MIN_EASY = 3
ACTIONS = {"skip": "Skip it", "easy": "Same time, kept easy", "half": "Cut it in half"}
ACWR_FLAG = 1.3
CATEGORIES = {
    "grey": "Grey-zone sessions kept easy",
    "hard_again": "Hard sessions the day after another hard one, kept easy",
}


def easy_rates(acts: list[A.Act], as_of: date) -> dict[str, dict]:
    """Load per minute of your easy sessions per sport over the previous 90 days."""
    out = {}
    for sport in ("run", "ride", "swim"):
        rates = [a.load / (a.moving_s / 60) for a in acts
                 if a.family == sport and a.load > 0 and (a.moving_s or 0) >= 15 * 60 and as_of - timedelta(days=90) < a.day <= as_of
                 and (k := A.intensity(a)) and k["kind"] == "easy"]
        out[sport] = {"rate": median(rates), "n": len(rates)} if len(rates) >= MIN_EASY else {"rate": None, "n": len(rates)}
    return out


def new_load(a: A.Act, action: str, rates: dict[str, dict]) -> tuple[float, bool]:
    """(replacement load, rough): `rough` when there was no personal easy rate and the load was simply halved."""
    if action == "skip":
        return 0.0, False
    if action == "half":
        return a.load / 2, False
    rate = (rates.get(a.family) or {}).get("rate")
    if rate and a.moving_s:
        return min(a.load, rate * a.moving_s / 60), False
    return a.load / 2, True


def _replay(c: dict, changes: dict[int, float], until: date) -> list[dict]:
    load = dict(c["load"])
    for aid, after in changes.items():
        a = c["act_by_id"][aid]
        load[a.day] = max(0.0, load.get(a.day, 0.0) - a.load + after)
    return A.pmc(load, c["first"], until)


def compare(c: dict, edits: list[dict], rates: dict[str, dict] | None = None, banister: dict | None = None,
            since: date | None = None, until: date | None = None) -> dict:
    """edits: [{"activity_id", "action"}] within (since, until], by default the last WINDOW_DAYS. Returns trajectories and headline differences."""
    as_of = c["as_of"]
    until = min(until or as_of, as_of)
    since = since or as_of - timedelta(days=WINDOW_DAYS)
    rates = rates if rates is not None else easy_rates(c["acts"], as_of)
    changes, rough, rows = {}, False, []
    for e in edits:
        a = c["act_by_id"].get(e["activity_id"])
        if a is None or e["action"] not in ACTIONS or a.day <= since or a.day > until or a.load <= 0:
            continue
        after, r = new_load(a, e["action"], rates)
        changes[a.id] = after
        rough = rough or r
        rows.append({"id": a.id, "day": a.day, "name": a.name, "family": a.family, "action": e["action"], "load": round(a.load), "load_after": round(after)})
    if not changes:
        return {"edits": [], "valid": False}
    base = [p for p in c["pmc"] if since < p["day"] <= until]
    alt = [p for p in _replay(c, changes, until) if p["day"] > since]
    first_day = min(r["day"] for r in rows)
    after_edit = {p["day"]: p for p in alt}
    base_by = {p["day"]: p for p in base}
    nxt = [d for d in sorted(base_by) if d > first_day][:1]
    end_b, end_a = base[-1], alt[-1]
    window_b = [p for p in base if p["day"] >= first_day]
    window_a = [p for p in alt if p["day"] >= first_day]
    over = lambda ps: sum(1 for p in ps if p["acwr"] is not None and p["acwr"] > ACWR_FLAG)  # noqa: E731
    out = {
        "valid": True, "edits": rows, "rough": rough, "window_days": (until - since).days, "n_days": len(window_b),
        "end": {
            "fitness": [end_b["fitness"], end_a["fitness"]], "fatigue": [end_b["fatigue"], end_a["fatigue"]], "form": [end_b["form"], end_a["form"]],
            "fitness_delta": round(end_a["fitness"] - end_b["fitness"], 1),
            "fitness_delta_pct": round((end_a["fitness"] - end_b["fitness"]) / end_b["fitness"] * 100, 1) if end_b["fitness"] > 5 else None,
            "form_delta": round(end_a["form"] - end_b["form"], 1),
        },
        "next_morning": {"day": nxt[0], "form_delta": round(after_edit[nxt[0]]["form"] - base_by[nxt[0]]["form"], 1),
                         "fatigue_delta": round(after_edit[nxt[0]]["fatigue"] - base_by[nxt[0]]["fatigue"], 1)} if nxt else None,
        "avg_form_delta": round(sum(a["form"] - b["form"] for a, b in zip(window_a, window_b)) / len(window_b), 1),
        "acwr_days_over": [over(window_b), over(window_a)],
        "trajectory": [{"day": b["day"], "fitness": b["fitness"], "fatigue": b["fatigue"], "form": b["form"], "acwr": b["acwr"],
                        "alt_fitness": a["fitness"], "alt_fatigue": a["fatigue"], "alt_form": a["form"], "alt_acwr": a["acwr"]}
                       for b, a in zip(base, alt)],
    }
    if banister and banister.get("adopted") and "_model" in banister:
        load = dict(c["load"])
        for aid, after in changes.items():
            a = c["act_by_id"][aid]
            load[a.day] = max(0.0, load.get(a.day, 0.0) - a.load + after)
        b0 = B.curve(banister, c["load"], until, step=1, since=until)[0]["value"]
        b1 = B.curve(banister, load, until, step=1, since=until)[0]["value"]
        out["performance"] = {"delta_pct": round((b1 - b0) / abs(b0) * 100, 2) if b0 else None, "taus": [banister["tau1"], banister["tau2"]]}
    return out


def candidates(c: dict) -> list[tuple[str, A.Act]]:
    """Sessions of the last WINDOW_DAYS that an easier day would most plausibly have improved, with why."""
    as_of = c["as_of"]
    since = as_of - timedelta(days=WINDOW_DAYS)
    spacing = (c.get("recovery") or {}).get("hard_spacing_days", 2)
    hard_days = sorted({a.day for a in c["acts"] if A.is_hard(a)})
    out = []
    for a in c["acts"]:
        if a.day <= since or a.load <= 0 or a.family not in A.INTENSITY_FAMILIES:
            continue
        k = A.intensity(a)
        if k and k["kind"] == "grey":
            out.append(("grey", a))
        elif A.is_hard(a) and any(0 < (a.day - d).days < spacing for d in hard_days):
            out.append(("hard_again", a))
    return out


def suggestions(c: dict, banister: dict | None = None) -> dict:
    rates = easy_rates(c["acts"], c["as_of"])
    found = candidates(c)
    items = []
    for kind, a in sorted(found, key=lambda t: t[1].day, reverse=True):
        r = compare(c, [{"activity_id": a.id, "action": "easy"}], rates, banister)
        if not r["valid"]:
            continue
        items.append({"id": a.id, "day": a.day, "name": a.name, "family": a.family, "kind": kind, "load": round(a.load), "load_after": r["edits"][0]["load_after"],
                      "fitness_delta": r["end"]["fitness_delta"], "fitness_delta_pct": r["end"]["fitness_delta_pct"],
                      "next_morning_form": r["next_morning"]["form_delta"] if r["next_morning"] else None, "rough": r["rough"]})
    bundle = {}
    for kind, label in CATEGORIES.items():
        edits = [{"activity_id": a.id, "action": "easy"} for k, a in found if k == kind]
        if len(edits) >= 2:
            r = compare(c, edits, rates, banister)
            if r["valid"]:
                bundle[kind] = {"label": label, "n": len(r["edits"]), **{k: r[k] for k in ("end", "avg_form_delta", "acwr_days_over", "rough", "trajectory", "n_days")},
                                **({"performance": r["performance"]} if "performance" in r else {})}
    return {"items": items, "bundles": bundle, "easy_rates": {k: v for k, v in rates.items()}, "window_days": WINDOW_DAYS,
            "recent": [{"id": a.id, "day": a.day, "name": a.name, "family": a.family, "load": round(a.load)}
                       for a in sorted(c["acts"], key=lambda x: (x.day, x.id), reverse=True)
                       if a.day > c["as_of"] - timedelta(days=WINDOW_DAYS) and a.load > 0][:30]}


def _flagged(c: dict, start: date, end: date) -> list[tuple[str, A.Act]]:
    return [(k, a) for k, a in candidates(c) if start <= a.day <= end]


def _brief(r: dict) -> dict:
    return {"n": len(r["edits"]), "rough": r["rough"], "fitness_delta": r["end"]["fitness_delta"], "fitness_delta_pct": r["end"]["fitness_delta_pct"],
            "form_delta": r["end"]["form_delta"], "avg_form_delta": r["avg_form_delta"], "acwr_days_over": r["acwr_days_over"],
            "next_morning_form": r["next_morning"]["form_delta"] if r["next_morning"] else None,
            "performance_pct": (r.get("performance") or {}).get("delta_pct")}


def for_period(c: dict, start: date, end: date, banister: dict | None = None) -> dict | None:
    """Sessions in [start, end] that an easier day would have improved, replayed together up to `end` (or today).

    Also counts the easy sessions you kept easy, so a clean period reads as the win it is. None outside the replay window.
    """
    as_of = c["as_of"]
    end = min(end, as_of)
    if end <= as_of - timedelta(days=WINDOW_DAYS) or start > end:
        return None
    start = max(start, as_of - timedelta(days=WINDOW_DAYS) + timedelta(days=1))
    found = _flagged(c, start, end)
    easy = sum(1 for a in c["acts"] if start <= a.day <= end and a.family in A.INTENSITY_FAMILIES and (k := A.intensity(a)) and k["kind"] == "easy")
    out: dict = {"start": start, "end": end, "flagged": len(found), "easy_kept": easy, "kinds": sorted({k for k, _ in found}), "replay": None, "sessions": []}
    if found:
        edits = [{"activity_id": a.id, "action": "easy"} for _, a in found]
        r = compare(c, edits, banister=banister, since=start - timedelta(days=1), until=end)
        if r["valid"]:
            out["replay"] = _brief(r)
            out["trajectory"] = r["trajectory"]
            out["sessions"] = [{"id": e["id"], "day": e["day"], "name": e["name"], "load": e["load"], "load_after": e["load_after"], "kind": k}
                               for e in r["edits"] for k, a in found if a.id == e["id"]]
    return out


def for_activity(c: dict, activity_id: int, banister: dict | None = None) -> dict | None:
    """The replay of one flagged session (grey zone, or a hard day right after another) kept easy; None when it isn't one."""
    match = next(((k, a) for k, a in candidates(c) if a.id == activity_id), None)
    if match is None:
        return None
    kind, a = match
    r = compare(c, [{"activity_id": a.id, "action": "easy"}], banister=banister)
    if not r["valid"]:
        return None
    return {"kind": kind, "activity_id": a.id, "load": r["edits"][0]["load"], "load_after": r["edits"][0]["load_after"], **_brief(r)}


def opportunity(c: dict, banister: dict | None = None) -> dict | None:
    """The biggest pattern in the last four weeks worth a nudge, for Home."""
    as_of = c["as_of"]
    return for_period(c, as_of - timedelta(days=27), as_of, banister)
