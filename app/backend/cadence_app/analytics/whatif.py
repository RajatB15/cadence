"""What-if replay: rerun your recent weeks with one session changed and compare the fitness model's trajectory.

Only the training-load inputs change; everything else (the other sessions, the 42/7-day fitness/fatigue model, the
EWMA acute:chronic ratio) is the same code that produces the numbers you see elsewhere, so a difference is purely what
the model says that session did. Limits worth keeping in mind:
- it is the model, not a measurement: load is Garmin's, the response curve is the standard 42/7-day one unless your own
  constants (fitness from `banister.fit`, fatigue from `fatigue_fit.fit`, diminishing returns from `banister.saturation`) beat
  it on held-out data, in which case those are used and named. Every number comes with a range over the plausible constants;
  `channels.py` prices easy and hard minutes separately, and `freshness.py` says whether your hard runs improve when you are fresher and no sleep, illness or life stress is in it;
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
from cadence_app.analytics import channels as CH
from cadence_app.analytics import freshness as FR

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


STANDARD = {"ctl_days": A.CTL_DAYS, "atl_days": A.ATL_DAYS, "alpha": 1.0, "personal": False, "sources": []}
TEXTBOOK_PAIRS = [(a, b) for a in (35, 42, 50) for b in (5, 7, 10)]
PAYOFF_DAYS = 4  # a hard session within this many days after the changed one is the one that feels the extra freshness


def _pmc(c: dict, load: A.Series, model: dict, pair: tuple[float, float] | None = None) -> list[dict]:
    ctl, atl = pair or (model["ctl_days"], model["atl_days"])
    return A.pmc(B.effective(load, model["alpha"]), c["first"], c["as_of"], ctl, atl)


def _base(c: dict, model: dict, pair: tuple[float, float] | None) -> list[dict]:
    cache = c.setdefault("_wi_base", {})
    key = (pair or (model["ctl_days"], model["atl_days"]), model["alpha"])
    if key not in cache:
        cache[key] = _pmc(c, c["load"], model, pair)
    return cache[key]


def _changed_load(c: dict, changes: dict[int, float]) -> A.Series:
    load = dict(c["load"])
    for aid, after in changes.items():
        a = c["act_by_id"][aid]
        load[a.day] = max(0.0, load.get(a.day, 0.0) - a.load + after)
    return load


def _summarise(base_all: list[dict], alt_all: list[dict], since: date, until: date, first_day: date) -> dict:
    base = [p for p in base_all if since < p["day"] <= until]
    alt = [p for p in alt_all if since < p["day"] <= until]
    nxt = next((p["day"] for p in base if p["day"] > first_day), None)
    base_by, alt_by = {p["day"]: p for p in base}, {p["day"]: p for p in alt}
    win_b, win_a = [p for p in base if p["day"] >= first_day], [p for p in alt if p["day"] >= first_day]
    return {"base": base, "alt": alt, "end_b": base[-1], "end_a": alt[-1], "next": nxt, "base_by": base_by, "alt_by": alt_by,
            "avg_form": sum(a["form"] - b["form"] for a, b in zip(win_a, win_b)) / len(win_b), "win_b": win_b, "win_a": win_a}


def _ranges(c: dict, changes: dict[int, float], model: dict, lab: dict, since: date, until: date, first_day: date) -> dict:
    fit = (lab or {}).get("banister") or {}
    pairs = [tuple(p) for p in fit.get("region_pairs", [])] if fit.get("valid") else []
    basis = "the time constants your data cannot rule out" if pairs else "textbook constants (35–50 and 5–10 days)"
    pairs = list({(model["ctl_days"], model["atl_days"]), *(pairs or TEXTBOOK_PAIRS)})
    alt_load = _changed_load(c, changes)
    fit_d, nm_d, form_d = [], [], []
    for pair in pairs:
        s = _summarise(_base(c, model, pair), _pmc(c, alt_load, model, pair), since, until, first_day)
        fit_d.append(s["end_a"]["fitness"] - s["end_b"]["fitness"])
        form_d.append(s["avg_form"])
        if s["next"]:
            nm_d.append(s["alt_by"][s["next"]]["form"] - s["base_by"][s["next"]]["form"])
    rng = lambda xs: [round(min(xs), 1), round(max(xs), 1)] if xs else None  # noqa: E731
    return {"fitness_delta": rng(fit_d), "next_morning_form": rng(nm_d), "avg_form_delta": rng(form_d), "n_pairs": len(pairs), "basis": basis}


def _payoff(c: dict, rows: list[dict], alt_by_day: dict, base_by_day: dict, lab: dict) -> dict:
    fresh = (lab or {}).get("freshness")
    if not fresh:
        return {"status": "unmeasured", "items": []}
    h = fresh["hard"]
    edited = {r["id"] for r in rows}
    items = []
    for r in rows:
        nxt = next((a for a in sorted(c["acts"], key=lambda x: x.day)
                    if A.is_hard(a) and r["day"] < a.day <= r["day"] + timedelta(days=PAYOFF_DAYS) and a.id not in edited and a.day in alt_by_day), None)
        if nxt is None:
            continue
        delta = alt_by_day[nxt.day]["form"] - base_by_day[nxt.day]["form"]
        pay = FR.payoff(fresh, delta)
        items.append({"after": r["id"], "session_id": nxt.id, "name": nxt.name, "day": nxt.day, "form_delta": round(delta, 1), "payoff": pay})
    if not h.get("enough"):
        status = "unmeasured"
    elif h.get("helpful"):
        status = "measured"
    else:
        status = "unproven"
    gains = [i["payoff"]["gain_pct"] for i in items if i["payoff"]]
    return {"status": status, "n_hard": h["n"], "needed": h["min"], "items": items,
            "per10_pct": h.get("per10_pct"), "ci_per10_pct": h.get("ci_per10_pct"), "total_gain_pct": round(sum(gains), 1) if gains else None}


def compare(c: dict, edits: list[dict], rates: dict[str, dict] | None = None, lab: dict | None = None,
            since: date | None = None, until: date | None = None) -> dict:
    """edits: [{"activity_id", "action"}] within (since, until], by default the last WINDOW_DAYS.

    `lab` carries the personal model and the Lab's analyses (see insights.lab_models); without it the standard 42/7-day model is used.
    """
    as_of = c["as_of"]
    until = min(until or as_of, as_of)
    since = since or as_of - timedelta(days=WINDOW_DAYS)
    lab = lab or {}
    model = lab.get("model") or STANDARD
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
    first_day = min(r["day"] for r in rows)
    alt_all = _pmc(c, _changed_load(c, changes), model)
    s = _summarise(_base(c, model, None), alt_all, since, until, first_day)
    end_b, end_a, nxt = s["end_b"], s["end_a"], s["next"]
    over = lambda ps: sum(1 for p in ps if p["acwr"] is not None and p["acwr"] > ACWR_FLAG)  # noqa: E731
    clean = [{"activity_id": r["id"], "action": r["action"]} for r in rows]
    out = {
        "valid": True, "edits": rows, "rough": rough, "window_days": (until - since).days, "n_days": len(s["win_b"]),
        "model": {k: model[k] for k in ("ctl_days", "atl_days", "alpha", "personal", "sources")},
        "end": {
            "fitness": [end_b["fitness"], end_a["fitness"]], "fatigue": [end_b["fatigue"], end_a["fatigue"]], "form": [end_b["form"], end_a["form"]],
            "fitness_delta": round(end_a["fitness"] - end_b["fitness"], 1),
            "fitness_delta_pct": round((end_a["fitness"] - end_b["fitness"]) / end_b["fitness"] * 100, 1) if end_b["fitness"] > 5 else None,
            "form_delta": round(end_a["form"] - end_b["form"], 1),
        },
        "next_morning": {"day": nxt, "form_delta": round(s["alt_by"][nxt]["form"] - s["base_by"][nxt]["form"], 1),
                         "fatigue_delta": round(s["alt_by"][nxt]["fatigue"] - s["base_by"][nxt]["fatigue"], 1)} if nxt else None,
        "avg_form_delta": round(s["avg_form"], 1),
        "acwr_days_over": [over(s["win_b"]), over(s["win_a"])],
        "ranges": _ranges(c, changes, model, lab, since, until, first_day),
        "zones": CH.minutes_moved(c["acts"], clean),
        "channels": CH.effect(lab["channels"], c["acts"], clean, until) if lab.get("channels") else None,
        "payoff": _payoff(c, rows, {p["day"]: p for p in alt_all}, {p["day"]: p for p in _base(c, model, None)}, lab),
        "trajectory": [{"day": b["day"], "fitness": b["fitness"], "fatigue": b["fatigue"], "form": b["form"], "acwr": b["acwr"],
                        "alt_fitness": a["fitness"], "alt_fatigue": a["fatigue"], "alt_form": a["form"], "alt_acwr": a["acwr"]}
                       for b, a in zip(s["base"], s["alt"])],
    }
    banister = lab.get("banister")
    if banister and banister.get("adopted") and "_model" in banister:
        alpha = banister.get("alpha", 1.0)
        b0 = B.curve(banister, B.effective(c["load"], alpha), until, step=1, since=until)[0]["value"]
        b1 = B.curve(banister, B.effective(_changed_load(c, changes), alpha), until, step=1, since=until)[0]["value"]
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


def suggestions(c: dict, lab: dict | None = None) -> dict:
    rates = easy_rates(c["acts"], c["as_of"])
    found = candidates(c)
    items = []
    for kind, a in sorted(found, key=lambda t: t[1].day, reverse=True):
        r = compare(c, [{"activity_id": a.id, "action": "easy"}], rates, lab)
        if not r["valid"]:
            continue
        items.append({"id": a.id, "day": a.day, "name": a.name, "family": a.family, "kind": kind, "load": round(a.load), "load_after": r["edits"][0]["load_after"],
                      "fitness_delta": r["end"]["fitness_delta"], "fitness_delta_pct": r["end"]["fitness_delta_pct"],
                      "next_morning_form": r["next_morning"]["form_delta"] if r["next_morning"] else None, "rough": r["rough"],
                      "ranges": r["ranges"], "channels": r["channels"], "payoff": r["payoff"], "zones": r["zones"]})
    bundle = {}
    for kind, label in CATEGORIES.items():
        edits = [{"activity_id": a.id, "action": "easy"} for k, a in found if k == kind]
        if len(edits) >= 2:
            r = compare(c, edits, rates, lab)
            if r["valid"]:
                bundle[kind] = {"label": label, "n": len(r["edits"]), **{k: r[k] for k in ("end", "avg_form_delta", "acwr_days_over", "rough", "trajectory", "n_days", "ranges", "zones", "channels", "payoff", "model", "next_morning")},
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
            "performance_pct": (r.get("performance") or {}).get("delta_pct"), "ranges": r["ranges"], "zones": r["zones"], "channels": r["channels"],
            "payoff": r["payoff"], "model": r["model"]}


def for_period(c: dict, start: date, end: date, lab: dict | None = None) -> dict | None:
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
        r = compare(c, edits, lab=lab, since=start - timedelta(days=1), until=end)
        if r["valid"]:
            out["replay"] = _brief(r)
            out["trajectory"] = r["trajectory"]
            out["sessions"] = [{"id": e["id"], "day": e["day"], "name": e["name"], "load": e["load"], "load_after": e["load_after"], "kind": k}
                               for e in r["edits"] for k, a in found if a.id == e["id"]]
    return out


def for_activity(c: dict, activity_id: int, lab: dict | None = None) -> dict | None:
    """The replay of one flagged session (grey zone, or a hard day right after another) kept easy; None when it isn't one."""
    match = next(((k, a) for k, a in candidates(c) if a.id == activity_id), None)
    if match is None:
        return None
    kind, a = match
    r = compare(c, [{"activity_id": a.id, "action": "easy"}], lab=lab)
    if not r["valid"]:
        return None
    return {"kind": kind, "activity_id": a.id, "load": r["edits"][0]["load"], "load_after": r["edits"][0]["load_after"], **_brief(r)}


def opportunity(c: dict, lab: dict | None = None) -> dict | None:
    """The biggest pattern in the last four weeks worth a nudge, for Home."""
    as_of = c["as_of"]
    return for_period(c, as_of - timedelta(days=27), as_of, lab)
