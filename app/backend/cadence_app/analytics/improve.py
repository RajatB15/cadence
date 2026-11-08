"""Improve: assembles the per-metric payload for HRV, resting HR and VO2max from the shared insights context (pure).

`build(c, metric, ...)` takes the context from `insights.context()`/`assemble()` plus stored focus rows and the profile
(loaded by the route), so tests build everything from synthetic data. Algorithms live in drivers, improve_rules,
improve_watch, focus, focus_review and norms; wording only in notes.py; citations only in improve_sources.py.
All output is association on your own history: no causal or medical claims. See docs/improve-design.md.
"""

from __future__ import annotations

from datetime import date, timedelta

from cadence_app.analytics import athlete as A
from cadence_app.analytics import drivers as D
from cadence_app.analytics import focus as F
from cadence_app.analytics import focus_review as FR
from cadence_app.analytics import improve_rules as RL
from cadence_app.analytics import improve_sources as SRC
from cadence_app.analytics import improve_watch as W
from cadence_app.analytics import norms
from cadence_app.analytics import notes
from cadence_app.analytics import timeoff as T

DAY = timedelta(days=1)
METRICS = ("hrv", "resting_hr", "vo2max")
METHODS = {"hrv": ["plews2013", "flatt2016", "neweywest1987", "benjamini1995"], "resting_hr": ["reimers2018", "neweywest1987", "benjamini1995"],
           "vo2max": ["firstbeat2014", "molinagarcia2022", "passler2019", "neweywest1987", "benjamini1995"]}
WATCH_METRIC = {"overreach_pattern": "hrv", "illness_signature": "hrv", "sleep_debt": "hrv", "detraining": "resting_hr"}


INTERNAL = {"domain", "planner_hint", "behaviour"}  # used for the focus; not part of the payload


def _clean(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_") and k not in INTERNAL}


def _weekly_exposures(c: dict) -> dict[str, dict]:
    weeks = [w for w in c["weeks"] if w["complete"]]
    sleep = c["series"].get("sleep_hours", {})
    by_sleep: dict[date, list[float]] = {}
    for d, v in sleep.items():
        by_sleep.setdefault(A.week_start(d), []).append(v)
    ex = {
        "hard_sessions": {"label": "hard sessions a week", "cause": "Hard sessions", "weekly": {w["week"]: float(w["hard_sessions"]) for w in weeks}},
        "load": {"label": "training load", "cause": "Training load", "weekly": {w["week"]: w["load"] for w in weeks}},
        "easy_share": {"label": "easy share of zone time", "cause": "Easy share", "weekly": {w["week"]: float(w["easy_pct"]) for w in weeks if w["easy_pct"] is not None}},
        "sleep": {"label": "sleep hours", "cause": "Sleep duration", "weekly": {w: sum(v) / len(v) for w, v in by_sleep.items() if len(v) >= 4}},
    }
    return ex


def _missing_signals(c: dict) -> list[str]:
    out = []
    for b in c["journal"]["behaviours"]:
        if b["active"] and not any(d > c["as_of"] - 28 * DAY for d in c["journal"]["answers"].get(b["key"], {})):
            out.append(f"{b['label'].lower()} (journal)")
    if not c["series"].get("hydration_ml"):
        out.append("hydration")
    return out


def _count(series: A.Series, as_of: date, metric: str) -> int:
    return len(D.window_values(series, as_of, 180 if metric == "vo2max" else D.TREND_DAYS))


def _time_off_days(c: dict, start: date, end: date) -> int:
    cfg, periods, today = c.get("plan_settings") or T.DEFAULTS, c.get("time_off") or [], c.get("today", c["as_of"])
    return sum(1 for d in A.daterange(start, end) if T.day_factors(periods, cfg, today, d)[0] < 1.0)


def _focus_view(row: dict) -> dict:
    return {"id": row["id"], "proposed": False, "start": row["start"], "check_on": row["end"], "priorities": row["priorities"], "blocked_by": row.get("blocked_by")}


def build(c: dict, metric: str, focus_rows: list[dict] | None = None, profile: dict | None = None, age: float | None = None) -> dict:
    series = c["series"].get(metric, {})
    as_of = c["as_of"]
    needed = D.NEEDED[metric]
    nights = _count(series, as_of, metric)
    out: dict = {
        "metric": metric, "as_of": as_of, "state": "ready", "message": None, "baseline": None, "trend": {"direction": "too_early", "change": None, "ci": None, "n": 0},
        "data": {"nights": nights, "needed": needed, "missing_signals": _missing_signals(c)}, "drivers": [], "progress": [], "start": [], "watch": [], "focus": None,
        "review": None, "benchmarks": {}, "context": [], "methods": METHODS[metric], "citations": {},
    }
    if not series:
        out.update(state="unsupported", message=notes.improve_message("unsupported", metric, 0, needed))
        out["citations"] = SRC.citation_map(out["methods"])
        return out
    out["baseline"] = D.baseline(series, as_of, metric)
    out["trend"] = D.trend(series, as_of, metric)
    bases = {m: D.baseline(c["series"].get(m, {}), as_of, m) for m in ("hrv", "resting_hr")}
    vo2 = sorted(c["series"].get("vo2max", {}).items())
    out["benchmarks"] = norms.benchmarks(bases, vo2[-1][1] if vo2 else None, profile, age)
    watch = W.run(c)
    out["watch"] = [{**f, **notes.improve_watch(f)} for f in watch]
    if nights < needed:
        out.update(state="collecting", message=notes.improve_message("collecting", metric, nights, needed))
        out["progress"] = [{"key": metric, "label": "readings" if metric == "vo2max" else "nights", "have": nights, "needed": needed}]
        out["citations"] = SRC.citation_map(out["methods"] + [k for f in watch for k in f["citations"]])
        return out

    if metric == "vo2max":
        dv = D.vo2_drivers(vo2, _weekly_exposures(c), as_of)
        rows = dv["drivers"]
    else:
        rows = D.grade(D.candidate_effects(metric, c["effects"], c["habits"]["effects"]))
        out["progress"] = D.progress(c["habits"]["progress"])
    out["drivers"] = [_clean({**r, **notes.improve_driver(r)}) for r in rows]
    d = {"metric": metric, "drivers": rows}
    recs = RL.run(c, d)
    out["start"] = [_clean({**r, **notes.improve_start(r, metric)}) for r in recs]
    out["context"] = [{**n_, "text": notes.improve_context(n_)} for n_ in RL.context_notes(c, metric)]

    mine = [r for r in (focus_rows or []) if r["metric"] == metric and r["status"] in ("active", "completed")]
    mine.sort(key=lambda r: r["start"])
    active = next((r for r in reversed(mine) if r["status"] == "active" and r["end"] >= as_of), None)
    if active:
        out["focus"] = _focus_view(active)
    elif (p := F.propose(recs, watch, c.get("today", as_of), metric)):
        p["priorities"] = [{**q, **notes.improve_priority(q, metric)} for q in p["priorities"]]
        out["focus"] = {**{k: v for k, v in p.items() if k != "metric"}}
        out["focus"]["priorities"] = [{k: v for k, v in q.items() if not k.startswith("_")} for q in p["priorities"]]
        out["focus"]["_internal"] = p["priorities"]
    past = [r for r in mine if r["start"] + FR.WINDOW * DAY <= as_of + DAY]
    if past:
        last = past[-1]
        rev = FR.review(metric, series, last["start"], as_of)
        if rev:
            ctx = FR.context(c["load"], c.get("wellbeing") or {}, _time_off_days(c, last["start"], last["start"] + 27 * DAY), last["start"])
            text = notes.improve_review(metric, rev, ctx)
            out["review"] = {"focus_id": last["id"], "window": rev["window"], "change": rev["change"], "ci": rev["ci"], "unit": rev["unit"], "verdict": rev["verdict"], **text}
    cites = out["methods"] + [k for r in out["start"] for k in r["citations"]] + [k for f in watch for k in f["citations"]]
    out["citations"] = SRC.citation_map(cites)
    return out


def public(payload: dict) -> dict:
    """The payload without internal fields (the route stores `_internal` priorities when a focus is accepted)."""
    out = {k: v for k, v in payload.items()}
    if out.get("focus"):
        out["focus"] = {k: v for k, v in out["focus"].items() if k != "_internal"}
    return out


def summary(c: dict, focus_rows: list[dict] | None = None) -> dict:
    parts = {m: build(c, m, focus_rows) for m in METRICS}
    states = {p["state"] for p in parts.values()}
    state = "ready" if "ready" in states else "collecting" if "collecting" in states else "unsupported"
    focus = None
    for m in METRICS:
        f = parts[m]["focus"]
        if f and f["priorities"]:
            q = f["priorities"][0]
            focus = {"check_on": f["check_on"], "metric": m, "priority": {"title": q["title"], "behaviour": q["behaviour"], "target_metrics": q["target_metrics"]}}
            break
    seen, watch = set(), []
    for m in METRICS:
        for f in parts[m]["watch"]:
            if f["id"] not in seen:
                seen.add(f["id"])
                watch.append({"metric": WATCH_METRIC.get(f["id"], m), "id": f["id"], "severity": f["severity"], "title": f["title"]})
    return {"as_of": c["as_of"], "state": state, "focus": focus, "watch": watch}
