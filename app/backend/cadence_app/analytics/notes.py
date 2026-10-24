"""Coach notes for every surface: today's brief, each session, each day's vitals and each weigh-in."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import fmean, median

from cadence_app.analytics import athlete as A
from cadence_app.analytics import habits as H
from cadence_app.analytics import heat as W
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import recovery as R
from cadence_app.analytics import strain as S
from cadence_app.analytics.insights import (
    SEVERITY_ORDER,
    coach,
    finding,
    fmt_clock,
    heavy_lower_days,
    readiness_now,
    readiness_on,
    recommend,
)

LONG_MIN = A.LONG_MIN
FAMILY_NOUN = {"run": "run", "ride": "ride", "swim": "swim", "walk": "walk", "strength": "strength session"}
TE_LABELS = ((1, "no aerobic benefit"), (2, "minor benefit"), (3, "maintaining"), (4, "improving"), (5, "highly improving"))
DAY = timedelta(days=1)


def note(fid, severity, category, title, detail, action=None, evidence=None, metrics=(), link=None) -> dict:
    return {**finding(fid, severity, category, title, detail, action, evidence, link), "metrics": list(metrics)}


def _by_severity(notes: list[dict]) -> list[dict]:
    return sorted(notes, key=lambda n: SEVERITY_ORDER[n["severity"]])


def fmt_pace(seconds: float) -> str:
    m, s = divmod(round(seconds), 60)
    return f"{m}:{s:02d}"


def fmt_day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _lc_first(text: str) -> str:
    return text if text[:2].isupper() else text[:1].lower() + text[1:]


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _effect(c: dict, eid: str) -> A.Effect | None:
    return next((e for e in c["effects"] if e.id == eid and e.significant), None)


def _window(series: A.Series, start: date, end: date) -> list[float]:
    return [series[d] for d in A.daterange(start, end) if d in series]


def easy_cap(c: dict) -> int | None:
    return c["zones"]["floors"][2] - 1 if c["zones"] else None


def need(c: dict) -> float:
    return (c.get("sleep_need") or {}).get("hours", R.DEFAULT_SLEEP_NEED)


def pace_at(c: dict, hr: float | None) -> float | None:
    """Current pace (s/km) at a heart rate, from the efficiency trend (speed ∝ HR above resting)."""
    t = c["eff_trend"]
    if not t or not hr or hr <= t["rhr"]:
        return None
    return t["pace_now_s"] * (t["ref_hr"] - t["rhr"]) / (hr - t["rhr"])


def te_label(te: float) -> str:
    return next((label for limit, label in TE_LABELS if te < limit), "overreaching")


# ---- session classification ---------------------------------------------------------


intensity = A.intensity
is_hard = A.is_hard


def hard_days(c: dict) -> set[date]:
    return {a.day for a in c["acts"] if is_hard(a)}


def recent_hard(days: set[date], d: date) -> int:
    """Hard days in the six days before `d`."""
    return sum(1 for x in days if d - 6 * DAY <= x < d)


def verdict(a: A.Act, hard: set[date] | None = None) -> dict | None:
    if a.family not in A.ENDURANCE:
        if not is_hard(a):
            return None
        if hard is not None and recent_hard(hard, a.day) >= 2:
            return {"label": "Hard again", "tone": "warn"}
        return {"label": "High intensity", "tone": "key"}
    i = intensity(a)
    if i is None:
        return None
    long_ = (a.moving_s or 0) >= LONG_MIN.get(a.family, 10**6) * 60
    if i["kind"] == "hard":
        if long_:
            return {"label": "Long & hard", "tone": "warn"}
        if hard is not None and recent_hard(hard, a.day) >= 2:
            return {"label": "Hard again", "tone": "warn"}
        return {"label": "Key session", "tone": "key"}
    if i["kind"] == "easy":
        return {"label": "Long & easy" if long_ else "Easy", "tone": "good"}
    return {"label": "Grey zone", "tone": "warn"}


def verdicts(c: dict | None) -> dict[int, dict]:
    if c is None:
        return {}
    hard = hard_days(c)
    return {a.id: v for a in c["acts"] if (v := verdict(a, hard)) is not None}


# ---- per session ---------------------------------------------------------------------


def session(c: dict, activity_id: int, streams: dict | None = None, summary: dict | None = None, named: bool = False) -> dict | None:  # noqa: C901
    a = c["act_by_id"].get(activity_id)
    if a is None:
        return None
    notes: list[dict] = []
    s = c["series"]
    noun = FAMILY_NOUN.get(a.family, "session")
    i = intensity(a)
    r = readiness_on(c, a.day)
    cap = easy_cap(c)
    hard = hard_days(c)
    prior_hard = recent_hard(hard, a.day)

    te_ev = []
    if a.aerobic_te:
        te_ev.append({"label": "Aerobic TE", "value": f"{a.aerobic_te:.1f} · {te_label(a.aerobic_te)}"})
    ana = summary.get("anaerobicTrainingEffect") if summary else None
    if isinstance(ana, (int, float)) and ana > 0:
        te_ev.append({"label": "Anaerobic TE", "value": f"{ana:.1f}"})

    if i:
        ev = [{"label": "Easy Z1–2", "value": f"{i['easy_pct']}%"}, {"label": "Z3", "value": f"{i['moderate_pct']}%"},
              {"label": "Z4–5", "value": f"{i['hard_pct']}%"}, *te_ev]
        if i["kind"] == "grey":
            p_cap = pace_at(c, cap) if a.family == "run" else None
            action = (
                f"Keep easy {noun}s under {cap} bpm" + (f" (about {fmt_pace(p_cap)}/km at your current fitness)" if p_cap else "")
                + "; save intensity for 1–2 dedicated sessions a week."
                if cap else "Either slow right down to truly easy or commit to a structured hard session."
            )
            notes.append(note("intensity", "warn", "Intensity", "Grey-zone session",
                              f"Only {i['easy_pct']}% easy and {i['moderate_pct']}% in Z3: too hard to recover from quickly, not hard enough to raise your ceiling.",
                              action, ev))
        elif i["kind"] == "easy":
            notes.append(note("intensity", "good", "Intensity", "Genuinely easy",
                              f"{i['easy_pct']}% of heart-rate time in Z1–2. This is the volume that builds your aerobic engine without taxing recovery.",
                              None, ev))
        elif r and r["score"] < 50:
            notes.append(note("intensity", "warn", "Intensity", "Went hard on a low-readiness day",
                              f"{i['hard_pct']}% in Z4–5 with readiness at {r['score']}. Quality suffers and recovery stretches out.",
                              "On low-readiness mornings, swap intensity for easy Z2 and move the key session.", ev))
        elif (a.moving_s or 0) >= LONG_MIN.get(a.family, 10**6) * 60:
            notes.append(note("intensity", "warn", "Intensity", f"Long {noun} at race effort",
                              f"{round((a.moving_s or 0) / 60)} min with {i['hard_pct']}% in Z4–5. Long sessions build durability when they're easy; "
                              "at this intensity it's a race-level effort that takes 2–3 days to absorb.",
                              f"Keep long {noun}s{f' under {cap} bpm' if cap else ' conversational'}; if you want intensity, add a short block at the end.", ev))
        elif prior_hard >= 2:
            notes.append(note("intensity", "warn", "Intensity", f"Hard day #{prior_hard + 1} in a week",
                              f"{i['hard_pct']}% in Z4–5, after {prior_hard} other hard days in the previous 6. Two quality days a week is the sweet spot; "
                              "beyond that, fatigue masks fitness and easy days can't do their job.",
                              f"Make the next session genuinely easy{f' (under {cap} bpm)' if cap else ''}.", ev))
        else:
            notes.append(note("intensity", "good", "Intensity", "Quality stimulus",
                              f"{i['hard_pct']}% of time in Z4–5: the work that raises your ceiling."
                              + (f" Readiness was {r['score']} ({r['label']})." if r else ""),
                              "Follow it with an easy day.", ev))
        if i["kind"] != "hard" and r and r["score"] >= 85 and a.family in ("run", "ride"):
            notes.append(note("primed", "info", "Readiness", "You were primed",
                              f"Readiness was {r['score']} that morning: a green light for a quality session you didn't use.",
                              "When readiness is 85+, schedule your intervals or tempo that day."))
    elif a.aerobic_te and a.family != "strength":
        notes.append(note("effect", "warn" if a.aerobic_te >= 5 else "info", "Training effect",
                          f"Aerobic training effect {a.aerobic_te:.1f}", f"Garmin rates this session as {te_label(a.aerobic_te)}.", None, te_ev))
    if i is None and is_hard(a) and prior_hard >= 2:
        notes.append(note("intensity", "warn", "Intensity", f"Hard day #{prior_hard + 1} in a week",
                          f"Heart rate spent 20%+ of this session in Z4–5, after {prior_hard} other hard days in the previous 6. "
                          "Two quality days a week is the sweet spot.", "Make the next session genuinely easy."))

    big = False
    if a.load > 0:
        peers = [x.load for x in c["acts"] if x.family == a.family and x.id != a.id and x.load > 0
                 and a.day - timedelta(days=180) <= x.day <= a.day]
        if len(peers) >= 8:
            share = sum(1 for v in peers if v < a.load) / len(peers)
            big = share >= 0.75
            if share >= 0.9:
                notes.append(note("load", "info", "Load", f"One of your biggest {noun}s",
                                  f"Training load {round(a.load)} beats {share:.0%} of your {noun}s in the last 6 months.",
                                  None, [{"label": "Your median", "value": round(median(peers))}]))
        p = c["pmc_by_day"].get(a.day)
        if p and p["acwr"] and p["acwr"] > 1.5:
            notes.append(note("spike", "alert", "Load", "This tipped you into a load spike",
                              f"Acute:chronic reached {p['acwr']:.2f} that day, the zone where injury risk climbs fastest.",
                              "Keep the next 2–3 days easy."))

    this = next((p for p in c["eff"] if p["id"] == a.id), None)
    if this:
        peers = [p for p in c["eff"] if p["id"] != a.id and a.day - timedelta(days=90) <= p["day"] < a.day and abs(p["hr"] - this["hr"]) <= 8]
        if len(peers) >= 4:
            med = median(p["ef"] for p in peers)
            delta = (this["ef"] - med) / med * 100
            ev = [{"label": f"This run @ {this['hr']} bpm", "value": f"{fmt_pace(1000 / this['speed'])}/km"},
                  {"label": "Your usual at that HR", "value": f"{fmt_pace(A.pace_at_hr(med, this['hr'], this['rhr']) or 0)}/km"},
                  {"label": "Runs compared", "value": len(peers)}]
            if delta >= 3:
                notes.append(note("efficiency", "good", "Aerobic", "More efficient than usual",
                                  f"{delta:.0f}% more grade-adjusted speed per beat above resting than your runs at a similar heart rate in the prior 90 days.", None, ev))
            elif delta <= -3:
                notes.append(note("efficiency", "warn", "Aerobic", "Less efficient than usual",
                                  f"{abs(delta):.0f}% less speed per heartbeat than your similar-HR runs. Heat, fatigue, short sleep or dehydration are the usual causes.",
                                  "Check that day's readiness and the night before.", ev))
            else:
                notes.append(note("efficiency", "info", "Aerobic", "Typical efficiency",
                                  "Speed per heartbeat matched your similar-HR runs from the prior 90 days.", None, ev))

    w = (c.get("weather_runs") or {}).get(a.id)
    if w and a.family in ("run", "ride", "walk") and w.get("temperature") is not None:
        cond = f"{w['temperature']:.0f} °C, dew point {w['dew_point']:.0f} °C" if w.get("dew_point") is not None else f"{w['temperature']:.0f} °C"
        personal = bool((c.get("heat") or {}).get("significant"))
        if w["hot"]:
            notes.append(note("weather", "info", "Conditions", f"Hot: {cond}",
                              f"Conditions like these cost about {w['cost_pct']:.0f}% of pace at the same effort"
                              + (" on your own runs." if personal else " (general heat table).")
                              + " Slower splits or a higher heart rate today are mostly the weather, not lost fitness.",
                              "On days like this, run early or set the effort, not the pace."))
        elif w["temperature"] <= 0:
            notes.append(note("weather", "info", "Conditions", f"Cold: {cond}", "Cold air raises effort early on; warm up longer before anything fast."))
        elif (w.get("wind") or 0) >= 30:
            notes.append(note("weather", "info", "Conditions", f"Windy: {w['wind']:.0f} km/h", "Headwind sections cost pace at the same effort: judge this one by heart rate."))

    dec = c["dec"].get(a.id)
    if dec is None and streams and a.family == "run" and (a.moving_s or 0) >= 45 * 60:
        dec = A.decoupling(streams)
    if dec and dec.get("steady") and "decoupling_pct" in dec:
        d = dec["decoupling_pct"]
        ev = [{"label": "HR drift", "value": f"{d:.1f}%"}, {"label": "Analysed", "value": f"{dec['minutes']} min"}]
        if d < 5:
            notes.append(note("drift", "good", "Durability", "Held steady to the end",
                              f"Heart rate drifted only {d:.1f}% relative to pace, under the 5% mark of a durable aerobic base.", None, ev))
        else:
            notes.append(note("drift", "warn", "Durability", f"Heart rate drifted {d:.1f}%",
                              "Efficiency fell between halves. Usually the opening pace was too ambitious for the duration; heat, hydration or fuelling also play in.",
                              "Start 10–15 s/km slower and aim for an even heart rate across both halves.", ev))

    if a.family == "run" and (is_hard(a) or (a.moving_s or 0) >= LONG_MIN["run"] * 60):
        if a.day - DAY in heavy_lower_days(c):
            notes.append(note("heavy_legs", "info", "Strength", "Legs were loaded yesterday",
                              "A heavy lower-body class the day before a quality or long run usually costs the run some pace and feel.",
                              "Next time, move heavy legs to after a hard run, or 2+ days before it."))

    if streams and a.family == "run" and (i is None or i["kind"] != "hard"):
        pc = A.pacing(streams)
        if pc and pc["split_pct"] >= 2:
            notes.append(note("pacing", "good", "Pacing", "Negative split",
                              f"Second half {pc['split_pct']:.0f}% faster than the first: controlled start, strong finish."))
        elif pc and pc["split_pct"] <= -5:
            notes.append(note("pacing", "info", "Pacing", "Faded in the second half",
                              f"Second half {abs(pc['split_pct']):.0f}% slower than the first.",
                              "Unless the route was hillier on the way back, start more conservatively."))

    nxt = a.day + DAY
    zh = A.baseline_z(s.get("hrv", {}), nxt)
    sleep_next = s.get("sleep_score", {}).get(nxt)
    ev = []
    if zh:
        ev.append({"label": "HRV next morning", "value": f"{s['hrv'][nxt]:.0f} ms (base {zh[1]:.0f})"})
    if sleep_next is not None:
        ev.append({"label": "Sleep score that night", "value": round(sleep_next)})
    if zh and zh[0] <= -1:
        notes.append(note("response", "warn", "Recovery", "Your body felt this one",
                          f"Next-morning HRV dropped to {s['hrv'][nxt]:.0f} ms, {abs(zh[0]):.1f} SD under your baseline.",
                          "Pair sessions like this with an easy day after.", ev))
    elif zh and (big or (i and i["kind"] == "hard")) and zh[0] > -0.5:
        notes.append(note("response", "good", "Recovery", "Absorbed well",
                          f"Next-morning HRV {s['hrv'][nxt]:.0f} ms, at your baseline despite the work.", None, ev))

    if a.end_local and a.end_local.hour >= 20 and a.load >= 20:
        e = _effect(c, "late_sleep")
        if e and e.diff < 0:
            notes.append(note("late", "info", "Sleep", "Late finish",
                              f"Ended at {a.end_local:%H:%M}. On your history, workouts ending after 20:00 are followed by sleep scores of "
                              f"{e.exposed_mean:.0f} vs {e.reference_mean:.0f} for daytime sessions.",
                              "When you can, finish hard sessions before 18:00.", ev))

    if a.family == "run" and a.distance_m:
        recent = [x.distance_m for x in c["acts"] if x.family == "run" and x.distance_m and a.day - timedelta(days=30) <= x.day < a.day]
        if len(recent) >= 3 and a.distance_m > 1.10 * max(recent):
            notes.append(note("distance_spike", "warn", "Injury risk", f"{(a.distance_m / max(recent) - 1) * 100:.0f}% longer than your recent longest",
                              f"{a.distance_m / 1000:.1f} km vs {max(recent) / 1000:.1f} km, your longest in the previous 30 days. Single runs more than "
                              "10% beyond the recent longest carried clearly higher overuse-injury risk in a large study of Garmin runners.",
                              "Make the next few days easy and short; grow the long run ≤ 10% at a time."))

    if a.family in ("run", "ride", "swim") and a.distance_m:
        prior = [x for x in c["acts"] if x.family == a.family and x.day < a.day and x.distance_m]
        if len(prior) >= 5:
            longer = [x for x in prior if x.distance_m >= a.distance_m]
            if not longer:
                notes.append(note("record_distance", "good", "Milestone", f"Longest {noun} on record",
                                  f"{a.distance_m / 1000:.1f} km, further than any of your {len(prior)} previous {noun}s."))
            elif (a.day - longer[-1].day).days >= 60:
                notes.append(note("record_distance", "good", "Milestone", f"Longest {noun} since {fmt_day(longer[-1].day)}",
                                  f"{a.distance_m / 1000:.1f} km."))
        if a.family == "run" and a.speed_mps and a.distance_m >= 5000:
            fast = [x for x in prior if x.speed_mps and x.distance_m >= 5000]
            quicker = [x for x in fast if x.speed_mps >= a.speed_mps]
            if len(fast) >= 5 and (not quicker or (a.day - quicker[-1].day).days >= 60):
                notes.append(note("record_pace", "good", "Milestone",
                                  "Fastest 5 km+ run on record" if not quicker else f"Fastest 5 km+ run since {fmt_day(quicker[-1].day)}",
                                  f"{fmt_pace(1000 / a.speed_mps)}/km grade-adjusted average."))

    if a.family == "strength" and summary and not named:  # `named`: the user saved this session's exercises in Cadence
        sets = summary.get("summarizedExerciseSets") or []
        if sets and all(x.get("category") in (None, "UNKNOWN", "WARM_UP") for x in sets):
            notes.append(note("strength_labels", "info", "Missing data", "Exercises aren't named",
                              "Garmin recorded the sets but not which exercises, so progressive overload and muscle balance can't be tracked.",
                              "Pick the exercise on the watch, or edit it in Garmin Connect after the session."))

    return {
        "verdict": verdict(a, hard),
        "intensity": i,
        "readiness": {"score": r["score"], "label": r["label"]} if r else None,
        "notes": _by_severity(notes),
    }


# ---- per day -------------------------------------------------------------------------


def contributors(c: dict, d: date) -> list[str]:
    """Things around the night before `d` that typically hurt recovery."""
    s, prev = c["series"], d - DAY
    out = []
    positive = [v for v in c["load"].values() if v > 0]
    load_prev = c["load"].get(prev, 0)
    if positive and load_prev >= A.quantile(positive, 0.75):
        out.append(f"hard training the day before (load {round(load_prev)})")
    late = [a for a in c["acts"] if a.day == prev and a.end_local and a.end_local.hour >= 20 and a.load >= 20]
    if late:
        out.append(f"a workout ending at {late[-1].end_local:%H:%M}")
    bed = s.get("bedtime", {}).get(d)
    if bed is not None and bed >= 30:
        out.append(f"falling asleep at {fmt_clock(bed)}")
    hours = s.get("sleep_hours", {}).get(d)
    if hours is not None and hours < need(c) - 1:
        out.append(f"only {hours:.1f} h of sleep")
    stress = s.get("stress", {})
    if prev in stress and len(stress) >= 30 and stress[prev] >= A.quantile(list(stress.values()), 0.75):
        out.append(f"a high-stress day (average {stress[prev]:.0f})")
    out += logged_habits(c, prev)
    return out


def logged_habits(c: dict, day: date) -> list[str]:
    """Journal answers for `day` that usually cost recovery, in words ("2 drinks", "late caffeine")."""
    j = c.get("journal") or {}
    proven = H.strongest((c.get("habits") or {}).get("effects", []))
    out = []
    for b in j.get("behaviours", []):
        value = j.get("answers", {}).get(b["key"], {}).get(day)
        if not value:
            continue
        costly = b["key"] in H.PRESUMED_COSTLY or (b["key"] in proven and H.worse(proven[b["key"]]))
        if costly:
            out.append(f"{value:.0f} {b['unit'] or 'x'} ({b['label'].lower()})" if b["kind"] == "count" else b["label"].lower())
    return out


def day(c: dict, d: date) -> dict:  # noqa: C901 - one block per metric family
    s = c["series"]

    def g(metric: str) -> A.Series:
        return s.get(metric, {})

    notes: list[dict] = []
    r = readiness_on(c, d)
    warn = R.warning_signals(s, d)
    guided = R.hrv_guided(g("hrv"), d, history_days=14)
    call = recommend(r, c["pmc_by_day"].get(d), c["load"].get(d - DAY, 0), warn, guided) if r else None
    target = need(c)
    for key, e in H.strongest((c.get("habits") or {}).get("effects", [])).items():
        value = (c.get("journal") or {}).get("answers", {}).get(key, {}).get(d - DAY)
        yes, *_ = H.exposure(next(b for b in c["journal"]["behaviours"] if b["key"] == key), {d - DAY: value} if value is not None else {})
        if yes and H.worse(e):
            notes.append(note(f"habit_{key}", "info", "Your habits", f"{e.exposed} yesterday",
                              f"On your history that's followed by {_lc_first(e.outcome)} of {e.exposed_mean:.0f} vs {e.reference_mean:.0f} on days without it.",
                              None, None, (e.extra["outcome"],) if e.extra["outcome"] in s else ()))
    if warn:
        notes.append(note("warning", warn["level"], "Recovery", "Several signals off together",
                          _join([x["label"] for x in warn["signals"]]) + ". Two or more moving together is a common early sign of illness or overreaching.",
                          "Skip intensity today; sleep early.", None, tuple(x["key"] for x in warn["signals"])))
    causes = contributors(c, d)
    because = f" Likely contributors: {_join(causes)}." if causes else ""
    sleep_tags = ("sleep_hours", "sleep_score", "deep_sleep_h", "rem_sleep_h", "sleep_stress")

    hours, bed, wake = g("sleep_hours").get(d), g("bedtime").get(d), g("wake_time").get(d)
    if hours is not None:
        ev = [{"label": "Asleep", "value": f"{hours:.1f} h"}]
        if bed is not None:
            ev.append({"label": "Lights out", "value": fmt_clock(bed)})
        if wake is not None:
            ev.append({"label": "Woke", "value": fmt_clock(wake)})
        week = _window(g("sleep_hours"), d - 6 * DAY, d)
        if len(week) >= 4:
            ev.append({"label": f"7-night debt vs {target:g} h", "value": f"{sum(max(0, target - v) for v in week):.1f} h"})
        if hours < target - 1:
            action = (f"With a {fmt_clock(wake)} wake-up, {target:g} h means asleep by {fmt_clock(wake - target * 60)}." if wake is not None
                      else "Move lights-out 30 minutes earlier tonight.")
            notes.append(note("sleep_duration", "warn", "Sleep", "Short night",
                              f"{hours:.1f} h asleep, {target - hours:.1f} h short of the {target:g} h your training needs.", action, ev, sleep_tags))
        elif R.sleep_ok(hours, target):
            notes.append(note("sleep_duration", "good", "Sleep", "Full night", f"{hours:.1f} h asleep.", None, ev, sleep_tags))
        else:
            notes.append(note("sleep_duration", "info", "Sleep", "Nearly there", f"{hours:.1f} h, just under your {target:g} h target.",
                              "Fifteen to thirty minutes earlier gets you there.", ev, sleep_tags))

    score = g("sleep_score").get(d)
    if score is not None:
        prior = _window(g("sleep_score"), d - 30 * DAY, d - DAY)
        avg = fmean(prior) if len(prior) >= 7 else None
        if score < 70 or (avg and score <= avg - 8):
            notes.append(note("sleep_score", "warn", "Sleep", "Poor sleep quality",
                              f"Sleep score {score:.0f}" + (f" vs your 30-day average of {avg:.0f}" if avg else "") + "." + because,
                              None, [], sleep_tags))
        elif score >= 85:
            notes.append(note("sleep_score", "good", "Sleep", "High-quality sleep", f"Sleep score {score:.0f}.", None, [], sleep_tags))

    if bed is not None and bed >= 30:
        e = _effect(c, "bed_score")
        notes.append(note("bedtime", "warn", "Sleep", "Late lights-out", f"Asleep at {fmt_clock(bed)}."
                          + (f" Your nights after 00:30 average a sleep score of {e.exposed_mean:.0f} vs {e.reference_mean:.0f} before 23:30"
                             f" ({e.n_exposed} vs {e.n_reference} nights)." if e and e.diff < 0 else ""),
                          "Aim for lights out by 23:30.", None, sleep_tags))

    for metric, label in (("deep_sleep_h", "deep"), ("rem_sleep_h", "REM")):
        v = g(metric).get(d)
        prior = _window(g(metric), d - 60 * DAY, d - DAY)
        if v is not None and len(prior) >= 20 and v <= A.quantile(prior, 0.1):
            notes.append(note(f"{metric}_low", "info", "Sleep", f"Little {label} sleep",
                              f"{v:.1f} h of {label} sleep, in your bottom 10% for the last 60 days."
                              + (" Alcohol, late meals, late hard training and short nights are common causes." if label == "deep" else ""),
                              None, None, (metric, "sleep_score")))

    hrv = g("hrv").get(d)
    zh = A.baseline_z(g("hrv"), d)
    if hrv is not None and zh:
        lo, hi = g("hrv_balanced_low").get(d), g("hrv_balanced_high").get(d)
        ev = [{"label": "HRV", "value": f"{hrv:.0f} ms"}, {"label": "60-day baseline", "value": f"{zh[1]:.0f} ms"}]
        if lo and hi:
            ev.append({"label": "Garmin balanced", "value": f"{lo:.0f}–{hi:.0f} ms"})
        tags = ("hrv", "hrv_weekly")
        if zh[0] <= -1 or (lo and hrv < lo):
            notes.append(note("hrv", "warn", "Recovery", "HRV below your normal",
                              f"{hrv:.0f} ms is {abs(zh[0]):.1f} SD under your baseline." + because,
                              "Keep today easy. If it stays low 3+ days, cut the week's load.", ev, tags))
        elif zh[0] >= 0.5:
            notes.append(note("hrv", "good", "Recovery", "HRV above baseline",
                              f"{hrv:.0f} ms, {zh[0]:+.1f} SD vs baseline: your nervous system has recovered.",
                              "A good day for quality if the plan calls for it.", ev, tags))
        else:
            notes.append(note("hrv", "info", "Recovery", "HRV in your normal range", f"{hrv:.0f} ms vs {zh[1]:.0f} ms baseline.", None, ev, tags))

    rhr = g("resting_hr").get(d)
    zr = A.baseline_z(g("resting_hr"), d)
    if rhr is not None and zr:
        diff = rhr - zr[1]
        ev = [{"label": "Resting HR", "value": f"{rhr:.0f} bpm"}, {"label": "Baseline", "value": f"{zr[1]:.0f} bpm"}]
        if diff >= 5 or zr[0] >= 2:
            notes.append(note("rhr", "warn", "Recovery", f"Resting heart rate up {diff:.0f} bpm",
                              "An elevated resting HR often precedes illness or signals incomplete recovery." + because,
                              "Skip intensity today and recheck tomorrow.", ev, ("resting_hr",)))
        elif diff <= -3:
            notes.append(note("rhr", "good", "Recovery", "Resting heart rate low",
                              f"{rhr:.0f} bpm, {abs(diff):.0f} under baseline: recovered and aerobically fit.", None, ev, ("resting_hr",)))
        else:
            notes.append(note("rhr", "info", "Recovery", "Resting heart rate normal", f"{rhr:.0f} bpm vs {zr[1]:.0f} baseline.", None, ev, ("resting_hr",)))

    stress = g("stress")
    if d in stress and len(stress) >= 30:
        v = stress[d]
        values = list(stress.values())
        e = _effect(c, "stress_sleep")
        if v >= A.quantile(values, 0.75):
            notes.append(note("stress", "warn", "Stress", "High-stress day", f"Average stress {v:.0f}, in your top quarter."
                              + (f" Days like this are followed by sleep scores of {e.exposed_mean:.0f} vs {e.reference_mean:.0f} on calm days." if e and e.diff < 0 else ""),
                              "Protect tonight: wind down early, screens off, lights out on time.", None, ("stress", "sleep_stress")))
        elif v <= A.quantile(values, 0.25):
            notes.append(note("stress", "good", "Stress", "Calm day", f"Average stress {v:.0f}, in your calmest quarter.", None, None, ("stress",)))

    bb_hi, bb_lo = g("body_battery").get(d), g("body_battery_low").get(d)
    bb_tags = ("body_battery", "body_battery_low")
    if bb_hi is not None and bb_hi < 50:
        notes.append(note("bb_charge", "warn", "Energy", "Body Battery barely recharged",
                          f"Peaked at {bb_hi:.0f}: the day started with little in the tank." + because, None, None, bb_tags))
    elif bb_hi is not None and bb_hi >= 90:
        notes.append(note("bb_charge", "good", "Energy", "Fully charged", f"Body Battery peaked at {bb_hi:.0f}.", None, None, bb_tags))
    if bb_lo is not None and bb_lo <= 10:
        notes.append(note("bb_drain", "info", "Energy", "Ran to empty",
                          f"Body Battery bottomed out at {bb_lo:.0f}. Long, demanding days need an earlier night.", None, None, bb_tags))

    steps = g("steps").get(d)
    prior = _window(g("steps"), d - 30 * DAY, d - DAY)
    if steps is not None and len(prior) >= 10:
        avg = fmean(prior)
        e = _effect(c, "steps_sleep")
        if steps < 0.5 * avg:
            notes.append(note("steps", "info", "Movement", "Low movement day",
                              f"{steps:,.0f} steps, under half your 30-day average of {avg:,.0f}.",
                              "Easy walking between sessions helps recovery.", None, ("steps", "floors")))
        elif steps >= 12000 and e and e.diff > 0:
            notes.append(note("steps", "good", "Movement", "Active day",
                              f"{steps:,.0f} steps. On your history, 12k+ days are followed by sleep scores of {e.exposed_mean:.0f} vs {e.reference_mean:.0f}.",
                              None, None, ("steps",)))

    spo2 = g("spo2").get(d)
    if spo2 is not None:
        prior = _window(g("spo2"), d - 60 * DAY, d - DAY)
        base = fmean(prior) if len(prior) >= 7 else None
        if spo2 < 94:
            notes.append(note("spo2", "info", "Oxygen", "Low average SpO₂",
                              f"Average {spo2:.0f}%. Readings under ~95% can come from altitude, a loose strap or breathing during sleep.",
                              "This isn't a diagnosis. If it stays low, talk to a doctor.", None, ("spo2",)))
        elif base and spo2 <= base - 2:
            notes.append(note("spo2", "info", "Oxygen", "SpO₂ below your norm",
                              f"{spo2:.0f}% vs your usual {base:.0f}%. Alone it means little; with a raised resting HR or breathing rate it can be an early illness sign.",
                              None, None, ("spo2",)))
        else:
            notes.append(note("spo2", "good", "Oxygen", "Oxygen saturation normal",
                              f"{spo2:.0f}% average" + (f", in line with your usual {base:.0f}%." if base else "."), None, None, ("spo2",)))

    resp = g("respiration").get(d)
    zb = A.baseline_z(g("respiration"), d)
    if resp is not None and zb:
        if resp - zb[1] >= 1.5:
            notes.append(note("respiration", "warn", "Recovery", "Breathing rate elevated",
                              f"{resp:.1f} brpm vs your usual {zb[1]:.1f}. With a higher resting HR or lower HRV it's an early sign of illness or overreaching.",
                              None, None, ("respiration",)))
        else:
            notes.append(note("respiration", "info", "Recovery", "Breathing rate normal",
                              f"{resp:.1f} brpm vs your usual {zb[1]:.1f}.", None, None, ("respiration",)))

    day_load = c["load"].get(d, 0)
    p = c["pmc_by_day"].get(d)
    sessions = [a for a in c["acts"] if a.day == d]
    load_tags = ("training_load", "intensity_minutes", "active_calories")
    ev = [{"label": "Fitness", "value": round(p["fitness"])}, {"label": "Fatigue", "value": round(p["fatigue"])},
          {"label": "Form", "value": f"{p['form']:+.0f}"}] if p else []
    if p and p["acwr"]:
        ev.append({"label": "Acute:chronic", "value": f"{p['acwr']:.2f}"})
    if p and p["acwr"] and p["acwr"] > 1.5:
        notes.append(note("load_day", "alert", "Load", "In a load spike",
                          f"Acute:chronic at {p['acwr']:.2f}: well above your recent norm.", "Hold the next few days easy.", ev, load_tags))
    elif sessions:
        labels = [v["label"] for a in sessions if (v := verdict(a, hard_days(c)))]
        notes.append(note("load_day", "info", "Load", f"Training load {round(day_load)}",
                          f"{len(sessions)} session{'s' if len(sessions) != 1 else ''}" + (f": {', '.join(labels)}." if labels else "."),
                          None, ev, load_tags))
    elif p:
        notes.append(note("load_day", "good", "Load", "Rest day", "No training logged. Adaptation happens on days like this.", None, ev, load_tags))

    im = g("intensity_minutes")
    if d in im:
        ws = A.week_start(d)
        total = sum(im.get(x, 0) for x in A.daterange(ws, d))
        if total >= 150:
            notes.append(note("intensity_week", "good", "Movement", "Weekly intensity goal met",
                              f"{total:.0f} intensity minutes so far this week (WHO guideline: 150+).", None, None, ("intensity_minutes",)))
        else:
            left = 6 - d.weekday()
            notes.append(note("intensity_week", "info", "Movement", f"{total:.0f} of 150 intensity minutes",
                              f"{150 - total:.0f} to go this week" + (f", {left} day{'s' if left != 1 else ''} left." if left else "."),
                              None, None, ("intensity_minutes",)))

    return {
        "readiness": {"score": r["score"], "label": r["label"], "components": r["components"]} if r else None,
        "call": call,
        "notes": _by_severity(notes),
    }


# ---- weigh-ins -----------------------------------------------------------------------


def weight(points: list, rate_kg_per_week: float | None, goal_kg: float | None, today: date) -> list[dict]:
    if not points:
        return []
    notes: list[dict] = []
    last = points[-1]
    gap = (today - last.day).days
    recent = [p for p in points if (today - p.day).days < 28]
    if gap > 21:
        notes.append(note("weigh_gap", "info", "Data", f"Last weigh-in was {gap} days ago",
                          "Without regular readings the trend line is guesswork.",
                          "Weigh once a week: same morning, after the bathroom, before eating."))
    elif len(recent) < 4:
        notes.append(note("weigh_freq", "info", "Data", "Weigh in more often",
                          f"{len(recent)} reading{'s' if len(recent) != 1 else ''} in 4 weeks. Weekly readings separate real change from water swings.",
                          "Weigh once a week: same morning, same routine."))

    if rate_kg_per_week is not None:
        pct = rate_kg_per_week / last.trend_kg * 100
        ev = [{"label": "Rate", "value": f"{rate_kg_per_week:+.2f} kg/wk"}, {"label": "Of body weight", "value": f"{pct:+.2f}%/wk"}]
        if goal_kg is not None and abs(goal_kg - last.trend_kg) >= 0.5:
            losing = goal_kg < last.trend_kg
            if losing and pct < -1:
                notes.append(note("rate", "warn", "Rate", "Losing too fast for training",
                                  f"{abs(pct):.1f}% of body weight a week. Beyond ~1%, muscle, power and session quality suffer.",
                                  "Add 200–300 kcal on training days; aim for 0.5–1% a week.", ev))
            elif losing and pct <= -0.25:
                notes.append(note("rate", "good", "Rate", "Healthy rate toward your goal",
                                  f"Losing {abs(pct):.2f}% of body weight a week: inside the 0.25–1% range that protects training.", None, ev))
            elif losing and rate_kg_per_week > 0.05:
                notes.append(note("rate", "warn", "Rate", "Trending away from your goal",
                                  f"Up {rate_kg_per_week:.2f} kg a week while the goal is {goal_kg:.1f} kg.",
                                  "A modest deficit on rest days moves this without hurting training.", ev))
            elif not losing and pct > 0.5:
                notes.append(note("rate", "warn", "Rate", "Gaining fast",
                                  f"{pct:.1f}% a week. Above ~0.5%, much of the gain is likely fat rather than muscle.", None, ev))
            elif not losing and rate_kg_per_week > 0.05:
                notes.append(note("rate", "good", "Rate", "Building toward your goal", f"Gaining {pct:.2f}% of body weight a week.", None, ev))
            else:
                notes.append(note("rate", "info", "Rate", "Weight is flat", f"Goal {goal_kg:.1f} kg; the trend isn't moving yet.", None, ev))
        elif abs(pct) > 1:
            notes.append(note("rate", "info", "Rate", "Weight is changing fast",
                              f"{pct:+.1f}% of body weight a week.", "Check that fuelling matches your training load.", ev))
        elif abs(pct) < 0.25:
            notes.append(note("rate", "good", "Rate", "Weight is stable",
                              "Stable weight while training means fuelling roughly matches load.", None, ev))

    dev = last.weight_kg - last.trend_kg
    if gap <= 7 and abs(dev) >= 1:
        notes.append(note("noise", "info", "Reading", "Latest reading is off trend",
                          f"{last.weight_kg:.1f} kg is {dev:+.1f} kg from the trend line. Daily swings are mostly water, glycogen and salt; the trend is what counts."))
    if goal_kg is not None and abs(goal_kg - last.trend_kg) >= 0.5:
        weeks = round(abs(goal_kg - last.trend_kg) / (0.005 * last.trend_kg))
        notes.append(note("goal_path", "info", "Goal", f"{abs(goal_kg - last.trend_kg):.1f} kg to {goal_kg:.1f} kg",
                          f"At a training-friendly 0.5% of body weight a week ({0.005 * last.trend_kg:.2f} kg), that's about {weeks} weeks: "
                          f"around {fmt_day(today + timedelta(weeks=weeks))}.",
                          "Fuel training days fully; take the deficit on rest days." if goal_kg < last.trend_kg else
                          "Pair a small surplus with progressive strength work."))
    return _by_severity(notes)


# ---- home brief -----------------------------------------------------------------------


def recent_sessions(c: dict) -> dict:
    """Today's sessions with their verdict and headline note; falls back to the last two days."""
    as_of = c["as_of"]
    day = as_of if any(a.day == as_of for a in c["acts"]) else max((a.day for a in c["acts"] if a.day < as_of), default=None)
    if day is None or (as_of - day).days > 2:
        return {"label": None, "day": None, "items": []}
    hard = hard_days(c)
    items = []
    for a in (x for x in c["acts"] if x.day == day):
        s = session(c, a.id)
        top = next((n for n in s["notes"] if n["severity"] in ("alert", "warn")), s["notes"][0] if s["notes"] else None)
        items.append({
            "id": a.id, "name": a.name, "family": a.family, "type": a.type,
            "start": a.start_local, "moving_s": a.moving_s, "distance_m": a.distance_m, "load": round(a.load),
            "avg_hr": a.avg_hr, "verdict": verdict(a, hard), "intensity": intensity(a), "notes": len(s["notes"]),
            "note": {k: top[k] for k in ("severity", "title", "detail")} if top else None,
        })
    label = "Today" if day == as_of else "Yesterday" if (as_of - day).days == 1 else day.strftime("%A")
    return {"label": label, "day": day, "items": items}


def _streak(flags: dict[date, bool], end: date) -> tuple[int, int]:
    """(current run ending at the latest day on or before `end`, best run ever) of consecutive True days."""
    best = run = 0
    prev = None
    for d in sorted(flags):
        if flags[d]:
            run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        else:
            run = 0
        best = max(best, run)
        prev = d
    current = 0
    d = max((x for x in flags if x <= end), default=None)
    if d is not None and (end - d).days <= 1:
        while flags.get(d):
            current += 1
            d -= DAY
    return current, best


def streaks(c: dict) -> list[dict]:
    s, as_of, out = c["series"], c["as_of"], []
    weeks = A.weekly(c["acts"], c["load"], c["first"], as_of)
    if len(weeks) >= 2:
        flags = {w["week"]: w["total_sessions"] >= 3 for w in weeks if w["complete"]}
        best = cur = 0
        for _, ok in sorted(flags.items()):
            cur = cur + 1 if ok else 0
            best = max(best, cur)
        live = weeks[-1]
        current = cur + (1 if not live["complete"] and live["total_sessions"] >= 3 else 0)
        out.append({"key": "weeks", "label": "Weeks with 3+ sessions", "current": current, "best": max(best, current), "unit": "wk"})
    hours = s.get("sleep_hours", {})
    if hours:
        target = need(c)
        cur, best = _streak({d: R.sleep_ok(v, target) for d, v in hours.items()}, as_of)
        out.append({"key": "sleep", "label": f"Nights at your {target:g} h need", "current": cur, "best": best, "unit": "nights"})
    bed = s.get("bedtime", {})
    if bed:
        cur, best = _streak({d: v <= -30 for d, v in bed.items()}, as_of)
        out.append({"key": "bed", "label": "Asleep by 23:30", "current": cur, "best": best, "unit": "nights"})
    return out


def week_progress(c: dict, plan: dict | None) -> dict:
    s, as_of = c["series"], c["as_of"]
    ws = A.week_start(as_of)
    acts = [a for a in c["acts"] if ws <= a.day <= as_of and A.is_training(a)]
    kinds = [k for a in acts if a.family in A.INTENSITY_FAMILIES and (k := intensity(a))]
    hard = sum(1 for a in acts if is_hard(a))
    strength = sum(1 for a in acts if a.family == "strength")
    easy = [k for k in kinds if k["kind"] != "hard"]
    t = plan["targets"] if plan else None
    items = []
    if t:
        load = sum(c["load"].get(d, 0) for d in A.daterange(ws, as_of))
        items.append({"key": "load", "label": "Training load", "done": round(load), "target": t["load"][1], "low": t["load"][0]})
        items.append({"key": "sessions", "label": "Sessions", "done": len(acts), "target": t["sessions"]})
        items.append({"key": "hard", "label": "Quality sessions", "done": hard, "target": t["hard"]})
        if t["long_min"]:
            done = any(a.family == "run" and (a.moving_s or 0) >= t["long_min"] * 60 * 0.9 for a in acts)
            items.append({"key": "long", "label": f"Long run · {t['long_min']} min", "done": int(done), "target": 1})
        if t.get("strength"):
            items.append({"key": "strength", "label": "Strength", "done": strength, "target": t["strength"]})
            sc = c.get("strength_content")
            if sc and sc["labelled_28d"]:
                items.append({"key": "heavy_lower", "label": "Heavy lower body", "done": sc["heavy_lower_this_week"], "target": 1})
    if easy:
        items.append({"key": "easy", "label": "Easy sessions kept easy", "done": sum(1 for k in easy if k["kind"] == "easy"), "target": len(easy)})
    nights = _window(s.get("sleep_hours", {}), ws, as_of)
    if nights:
        target = need(c)
        items.append({"key": "sleep", "label": f"Nights at {target:g} h", "done": sum(1 for h in nights if R.sleep_ok(h, target)), "target": len(nights)})
    beds = _window(s.get("bedtime", {}), ws, as_of)
    if beds:
        items.append({"key": "bed", "label": "Asleep by 23:30", "done": sum(1 for b in beds if b <= -30), "target": len(beds)})
    return {"start": ws, "days_left": 6 - as_of.weekday(), "items": items, "hard_done": hard, "sessions_done": len(acts), "strength_done": strength}


def today_session(c: dict, r: dict | None, week: dict, plan: dict | None, now_hour: int | None = None) -> dict:
    as_of = c["as_of"]
    done_today = [a for a in c["acts"] if a.day == as_of and A.is_training(a)]
    if not done_today:
        return _suggest(c, r, week, plan)

    t = plan["targets"] if plan else {}
    hard_today = any(is_hard(a) for a in done_today)
    long_today = bool(t.get("long_min")) and any(a.family == "run" and (a.moving_s or 0) >= t["long_min"] * 60 * 0.9 for a in done_today)
    cardio_today = any(a.family in A.ENDURANCE for a in done_today)
    before = {**week, "hard_done": week["hard_done"] - int(hard_today), "sessions_done": week["sessions_done"] - len(done_today)}
    planned = _suggest(c, r, before, plan, long_done_today=long_today) if r else None
    hard = hard_days(c)
    did = _join([f"{a.name} ({v['label'].lower()})" if (v := verdict(a, hard)) else a.name for a in done_today])
    load = sum(a.load for a in done_today)
    recent = [v for d, v in c["load"].items() if as_of - timedelta(days=28) <= d < as_of and v > 0]
    typical = median(recent) if recent else 0
    tomorrow = (as_of + DAY).strftime("%A")
    days_left = week["days_left"]
    out = {"kind": "done", "planned": planned["title"] if planned else None, "load": round(load),
           "sessions": [{"id": a.id, "name": a.name, "verdict": verdict(a, hard)} for a in done_today], "second": None}

    kind = planned["kind"] if planned else None
    if kind is None or (kind == "key" and hard_today) or (kind == "long" and long_today) or (kind == "easy" and cardio_today and not hard_today):
        status, title = "matched", "Today's work is done"
        detail = f"You did {did}." + (f" That covers what today called for ({planned['title'].lower()})." if planned else "")
        nxt = "Refuel, hydrate and get to bed on time; that's when the session turns into fitness."
    elif kind in ("key", "long"):
        status = "open"
        title = "Key session still open" if kind == "key" else "Long run still open"
        detail = f"You did {did}, which doesn't replace the {'quality session' if kind == 'key' else 'long run'} today called for."
        nxt = (f"Move it to {tomorrow} rather than stacking it on today's session." if days_left > 0
               else "Skip it this week rather than doubling up; next week's plan accounts for it.")
    elif kind == "easy" and hard_today:
        status, title = "over", "Harder than planned"
        detail = f"Today called for easy aerobic work; you did {did}."
        nxt = f"Make {tomorrow} genuinely easy so this doesn't turn into another hard-day streak."
    elif kind == "easy":
        status, title = "open", "Aerobic work still open"
        detail = f"You did {did}. Useful, but it doesn't build the aerobic base today called for ({planned['title'].lower()})."
        nxt = "Fit it in later today if you feel fresh, or make it tomorrow's session."
    else:
        status, title = "extra", "Bonus session on a recovery day"
        detail = f"Today was earmarked for rest; you did {did}."
        nxt = f"Keep {tomorrow} easy so the extra work doesn't cost the week."

    hour = now_hour if now_hour is not None else datetime.now().hour
    room = typical == 0 or load < 0.7 * typical
    if status == "open" and r and r["score"] >= 70 and hour < 19 and room and not hard_today:
        cap = t.get("easy_cap") or easy_cap(c)
        out["second"] = {"title": "Optional: easy 30–40 min this evening",
                         "detail": f"Conversational aerobic work{f' under {cap} bpm' if cap else ''}. Never a second hard session on the same day."}
    return {**out, "status": status, "title": title, "detail": detail, "next": nxt}


def _suggest(c: dict, r: dict | None, week: dict, plan: dict | None, long_done_today: bool = False) -> dict:  # noqa: C901
    as_of = c["as_of"]
    t = plan["targets"] if plan else {}
    cap = t.get("easy_cap") or easy_cap(c)
    cap_txt = f" under {cap} bpm" if cap else ""
    if r is None:
        return {"kind": "unknown", "title": "Train by feel", "detail": "Readiness needs this morning's HRV or resting heart rate."}

    easy_runs = [a.moving_s / 60 for a in c["acts"] if a.family == "run" and a.moving_s and a.day > as_of - timedelta(days=60)
                 and (k := intensity(a)) and k["kind"] == "easy"]
    easy_min = int(min(60, max(30, round(median(easy_runs) / 5) * 5))) if easy_runs else 40
    p = c["pmc_by_day"].get(as_of)
    hard = hard_days(c)
    spacing = t.get("hard_spacing", 2)
    last_hard = max((d for d in hard if d < as_of), default=None)
    rested = last_hard is None or (as_of - last_hard).days >= spacing
    hard_left = max(0, t.get("hard", 0) - week["hard_done"])
    if recent_hard(hard, as_of) >= 2:
        hard_left = 0
    sessions_left = max(0, t.get("sessions", 0) - week["sessions_done"])
    long_left = long_done_today or any(i["key"] == "long" and i["done"] < 1 for i in week["items"])
    strength_left = max(0, t.get("strength", 0) - week.get("strength_done", 0))
    left = f"{sessions_left} session{'s' if sessions_left != 1 else ''} and {hard_left} quality left this week." if t else ""
    warn = c.get("warnings") if as_of == c["as_of"] else None
    guided = c.get("hrv_guided") or {}

    if warn and warn["level"] == "alert" or r["score"] < 50:
        why = "Several body signals are off together." if warn else "Recovery markers are well below your normal."
        return {"kind": "rest", "title": "Rest", "detail": f"{why} Walk, stretch and sleep early; the work will land better tomorrow."}
    if warn or (p and p["acwr"] and p["acwr"] > 1.5) or r["score"] < 70 or guided.get("status") == "below":
        why = ("A couple of body signals are off" if warn else "Your 7-day HRV is below its normal range" if guided.get("status") == "below"
               else "Signals are below your normal")
        return {"kind": "easy", "title": f"Easy {easy_min} min",
                "detail": f"Conversational effort{cap_txt}, or mobility. {why}, so bank recovery today. {left}".strip()}
    if long_left and t.get("long_min") and as_of.weekday() >= 5 and as_of - DAY not in hard:
        km = f" (≤ {t['long_km_cap']:.1f} km)" if t.get("long_km_cap") else ""
        return {"kind": "long", "title": f"Long run · {t['long_min']} min",
                "detail": f"Conversational{cap_txt}{km}. Start slower than feels necessary and keep heart rate even to the end."}
    if hard_left and rested and not guided.get("today_low"):
        sessions = (plan or {}).get("sessions") or []
        nxt = sessions[min(week["hard_done"], len(sessions) - 1)] if sessions else None
        if nxt:
            return {"kind": "key", "title": ("Go hard: " if r["score"] >= 85 else "") + nxt["title"],
                    "detail": f"{nxt['detail']} {left}".strip(), "session": nxt}
        zones = c["zones"]
        work = (f"5 × 4 min at {zones['floors'][3]}–{zones['floors'][4] - 1} bpm" if zones else "5 × 4 min hard")
        return {"kind": "key", "title": "Go hard: key session" if r["score"] >= 85 else "Key session",
                "detail": f"Warm up 15 min, then {work} with 3 min easy between. Cool down 10 min. {left}".strip()}
    if sessions_left:
        extra = " Add a strength session after it if you have time." if strength_left else ""
        spaced = "" if rested or not hard_left else f" Your next quality session waits until {spacing} days after the last one."
        return {"kind": "easy", "title": f"Easy {easy_min} min",
                "detail": f"Aerobic volume{cap_txt}. Easy days make the hard days possible.{spaced}{extra} {left}".strip()}
    if strength_left:
        return {"kind": "strength", "title": "Strength 30–40 min", "detail": "Your sessions are covered; a strength session is the most useful addition."}
    return {"kind": "rest", "title": "Rest or walk", "detail": "This week's session targets are covered. A rest day banks the adaptation."}


def weather_today(c: dict) -> dict | None:
    if not c.get("forecast"):
        return None
    return W.outlook(c["forecast"], c["as_of"], c.get("start_hour", 7), c["utc_offset"], c.get("heat"))


def strain_today(c: dict, morning: dict | None, today: dict) -> dict | None:
    st = c.get("strain")
    if not st:
        return None
    as_of = c["as_of"]
    v = st["days"].get(as_of, {"total": 0.0, "workout": 0.0, "everyday": 0.0})
    band = S.target({d: x["total"] for d, x in st["days"].items()}, as_of, morning["score"] if morning else None, today.get("kind"))
    state = S.status(v["total"], band)
    message = {
        "below": f"Room for about {band['low'] - v['total']:.0f} more today." if band else None,
        "in": "In today's target band: enough to progress, little enough to recover.",
        "above": "Past today's target: keep the rest of the day easy and protect tonight's sleep.",
    }.get(state or "", None)
    return {**v, "band": band, "status": state, "message": message, "calibrated": st["calibrated_on"] >= S.MIN_CALIBRATION}


def brief(c: dict) -> dict:
    as_of = c["as_of"]
    morning = readiness_on(c, as_of)
    r = readiness_now(c)
    plan = training_plan.weekly_plan(c)
    week = week_progress(c, plan)
    findings = sorted(coach(c), key=lambda f: SEVERITY_ORDER[f["severity"]])
    trend = [{"day": d, "score": x["score"]} for d in A.daterange(as_of - 13 * DAY, as_of) if (x := readiness_on(c, d))]
    today = today_session(c, morning, week, plan)
    return {
        "as_of": as_of,
        "readiness": {k: r[k] for k in ("score", "label", "components", "morning_score", "changes", "live") if k in r} if r else None,
        "readiness_trend": trend,
        "call": recommend(r, c["pmc_by_day"].get(as_of), c["load"].get(as_of - DAY, 0), c.get("warnings"), c.get("hrv_guided")),
        # The day's plan is set by the morning score, not by how today's training has since lowered it.
        "today": today,
        "strain": strain_today(c, morning, today),
        "weather": weather_today(c),
        "focus": plan["focus"] if plan else None,
        "phase": plan["phase"] if plan else None,
        "goal": plan["goal"] if plan else None,
        "recent": recent_sessions(c),
        "week": week,
        "streaks": streaks(c),
        "tonight": c.get("tonight"),
        "fix": [f for f in findings if f["severity"] in ("alert", "warn")][:3],
        "wins": [f for f in findings if f["severity"] == "good"][:2],
    }
