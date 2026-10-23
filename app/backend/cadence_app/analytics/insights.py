"""Turns stored data into athlete insights: loading, cached per-run analysis, coach findings, recommendations."""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import fmean, median, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cadence_app import journal as journal_store
from cadence_app import strength as strength_store
from cadence_app import weather as weather_store
from cadence_app.activity_types import activity_family
from cadence_app.analytics import athlete as A
from cadence_app.analytics import habits as H
from cadence_app.analytics import heat as W
from cadence_app.analytics import performance as P
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import recovery as R
from cadence_app.analytics import strain as S
from cadence_app.garmin import fit, vault
from cadence_app.models import Activity, ActivityAnalysis, AppSetting, DailyMetric, DayHeartHistogram, RawResponse, WeightReading
from cadence_app.sync import utcnow

log = logging.getLogger(__name__)
ANALYSIS_VERSION = 2
MIN_ANALYSIS_S = 10 * 60
SEVERITY_ORDER = {"alert": 0, "warn": 1, "info": 2, "good": 3}
GOAL_KEY = "training_goal"
SPIKE_RATIO = 1.10
DAY = timedelta(days=1)


def _family(type_key: str) -> str:
    return activity_family(type_key)


# ---- loading ---------------------------------------------------------------------


def load_series(session: Session, source_id: str) -> dict[str, A.Series]:
    out: dict[str, A.Series] = {}
    for metric, day, value in session.execute(
        select(DailyMetric.metric, DailyMetric.day, DailyMetric.value).where(DailyMetric.source_id == source_id)
    ):
        out.setdefault(metric, {})[day] = value
    return out


def _offset(label: str) -> timedelta:
    return timedelta(minutes=fit.offset_minutes(label))


def load_acts(session: Session, source_id: str) -> list[A.Act]:
    summaries = vault.activity_summaries(session) if source_id == "garmin" else {}
    acts = []
    for a in session.scalars(select(Activity).where(Activity.source_id == source_id).order_by(Activity.start_time_utc)):
        s = summaries.get(a.source_record_id, {})
        start = a.start_time_utc + _offset(a.timezone)
        moving = a.moving_duration_s or a.duration_s
        speed = s.get("avgGradeAdjustedSpeed") or a.avg_speed_mps or (
            a.distance_m / moving if a.distance_m and moving else None
        )
        zones = tuple(float(s.get(f"hrTimeInZone_{i}") or 0) for i in range(1, 6)) if s else ()
        ana = s.get("anaerobicTrainingEffect")
        acts.append(
            A.Act(
                id=a.id, day=a.local_date, start_local=start, end_local=start + timedelta(seconds=a.duration_s),
                family=_family(a.activity_type), type=a.activity_type, name=a.name, load=a.training_load or 0.0,
                distance_m=a.distance_m, moving_s=moving, avg_hr=a.avg_hr,
                speed_mps=float(speed) if isinstance(speed, (int, float)) and speed > 0 else None,
                zones_s=zones if any(zones) else (), vo2max=a.vo2max, aerobic_te=a.aerobic_te,
                anaerobic_te=float(ana) if isinstance(ana, (int, float)) else None, max_hr=a.max_hr,
            )
        )
    return acts


def load_goal(session: Session) -> dict | None:
    setting = session.get(AppSetting, GOAL_KEY)
    if not setting:
        return None
    try:
        raw = json.loads(setting.value)
        return {"distance": raw["distance"], "date": date.fromisoformat(raw["date"]), "target_s": raw.get("target_s")}
    except (ValueError, KeyError, TypeError):
        return None


def save_goal(session: Session, goal: dict | None) -> None:
    existing = session.get(AppSetting, GOAL_KEY)
    if goal is None:
        if existing:
            session.delete(existing)
    else:
        value = json.dumps({"distance": goal["distance"], "date": goal["date"].isoformat(), "target_s": goal.get("target_s")})
        if existing:
            existing.value = value
        else:
            session.add(AppSetting(key=GOAL_KEY, value=value))
    session.commit()


def load_weights(session: Session, source_id: str) -> list[tuple[date, float]]:
    rows: dict[date, list[float]] = defaultdict(list)
    for day, kg in session.execute(
        select(WeightReading.local_date, WeightReading.weight_kg).where(WeightReading.source_id == source_id)
    ):
        rows[day].append(kg)
    return sorted((d, fmean(v)) for d, v in rows.items())


# ---- cached per-run FIT analysis --------------------------------------------------


def pending_analyses(session: Session) -> list[tuple[int, str, str]]:
    done = select(ActivityAnalysis.activity_id).where(ActivityAnalysis.version == ANALYSIS_VERSION)
    rows = session.execute(
        select(Activity.id, Activity.source_record_id, Activity.timezone)
        .where(
            Activity.source_id == "garmin",
            Activity.duration_s >= MIN_ANALYSIS_S,
            Activity.activity_type.contains("run"),
            Activity.id.not_in(done),
        )
        .order_by(Activity.start_time_utc.desc())
    ).all()
    return [tuple(r) for r in rows]


def analyse_pending(factory: sessionmaker, archive_dir: Path, stop: threading.Event | None = None) -> int:
    done = 0
    with factory() as session:
        pending = pending_analyses(session)
    for activity_id, record_id, tz in pending:
        if stop is not None and stop.is_set():
            break
        with factory() as session:
            raw, _ = vault.load(session, f"activity_fit:{record_id}")
        if raw is None or not raw.file_path:
            continue  # FIT not archived yet; picked up on a later pass
        result: dict = {}
        path = (archive_dir / raw.file_path).resolve()
        if archive_dir.resolve() in path.parents and path.is_file():
            decoded = fit.decode(path, "run", fit.offset_minutes(tz))
            result = P.analyse_run(decoded.get("streams", {}))
        with factory() as session, session.begin():
            session.merge(
                ActivityAnalysis(
                    activity_id=activity_id, version=ANALYSIS_VERSION, computed_at=utcnow(), data=json.dumps(result)
                )
            )
        done += 1
    return done


class AnalysisWorker:
    def __init__(self, factory: sessionmaker, archive_dir: Path, weather_refresh=None):
        self.factory, self.archive_dir = factory, archive_dir
        self.weather_refresh = weather_refresh
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def kick(self) -> None:
        with self._lock:
            if self.busy:
                return
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        try:
            analyse_pending(self.factory, self.archive_dir, self._stop)
            cache_strain(self.factory, self._stop)
            if self.weather_refresh:
                self.weather_refresh()
        except Exception:  # pylint: disable=broad-exception-caught  # background job boundary
            log.exception("Activity analysis failed")

    def stop(self) -> None:
        self._stop.set()


# ---- cached all-day heart-rate histograms (strain) ------------------------------------

STRAIN_VERSION = 1
LIVE_DAYS = 3  # the vault keeps re-fetching the last days; compute those fresh instead of caching


def _windows(session: Session, day: date) -> list[tuple[int, int]]:
    rows = session.execute(
        select(Activity.start_time_utc, Activity.duration_s).where(
            Activity.source_id == "garmin", Activity.local_date >= day - DAY, Activity.local_date <= day + DAY
        )
    ).all()
    return [S.window(start, duration) for start, duration in rows]


def _histogram(session: Session, day: date) -> tuple[dict, dict, int] | None:
    raw, payload = vault.load(session, f"hr_intraday:{day.isoformat()}")
    if raw is None or raw.status_code != 200:
        return None
    points = S.samples(payload)
    outside, inside = S.histogram(points, _windows(session, day))
    return outside, inside, len(points)


def pending_strain_days(session: Session) -> list[date]:
    stored = set(session.scalars(
        select(RawResponse.window_start).where(
            RawResponse.source_id == "garmin", RawResponse.dataset == "hr_intraday", RawResponse.final.is_(True),
            RawResponse.status_code == 200,
        )
    ))
    done = set(session.scalars(
        select(DayHeartHistogram.day).where(DayHeartHistogram.source_id == "garmin", DayHeartHistogram.version == STRAIN_VERSION)
    ))
    return sorted((d for d in stored - done if d is not None), reverse=True)


def cache_strain(factory: sessionmaker, stop: threading.Event | None = None) -> int:
    with factory() as session:
        pending = pending_strain_days(session)
    done = 0
    for day in pending:
        if stop is not None and stop.is_set():
            break
        with factory() as session:
            h = _histogram(session, day)
        if h is None:
            continue
        with factory() as session, session.begin():
            session.merge(DayHeartHistogram(source_id="garmin", day=day, version=STRAIN_VERSION, outside=json.dumps(h[0]),
                                            inside=json.dumps(h[1]), samples=h[2], computed_at=utcnow()))
        done += 1
    return done


def load_hr_histograms(session: Session, today: date) -> dict[date, tuple[dict, dict]]:
    """Cached settled days plus the last few days computed live from the vault."""
    out: dict[date, tuple[dict, dict]] = {}
    for day, outside, inside in session.execute(
        select(DayHeartHistogram.day, DayHeartHistogram.outside, DayHeartHistogram.inside).where(
            DayHeartHistogram.source_id == "garmin", DayHeartHistogram.version == STRAIN_VERSION
        )
    ):
        out[day] = ({int(k): v for k, v in json.loads(outside).items()}, {int(k): v for k, v in json.loads(inside).items()})
    for day in (today - timedelta(days=i) for i in range(LIVE_DAYS)):
        if (h := _histogram(session, day)) is not None and h[2]:
            out[day] = (h[0], h[1])
    return out


def strain_days(c: dict, hists: dict[date, tuple[dict, dict]]) -> dict | None:
    """Per-day strain in Garmin-load units: total, inside workouts and everyday (outside workouts)."""
    if not hists:
        return None
    rhr = c["series"].get("resting_hr", {})
    fallback = median(rhr.values()) if rhr else A.DEFAULT_RHR
    zones = c.get("zones") or {}
    observed = ((c.get("performance") or {}).get("zone_check") or {}).get("observed_max")
    hr_max = float(zones.get("max") or observed or 190)
    raw = {}
    for day, (outside, inside) in hists.items():
        rest = A.resting_hr_on(rhr, day, fallback)
        raw[day] = (S.trimp_from_hist(outside, rest, hr_max), S.trimp_from_hist(inside, rest, hr_max))
    scale, n = S.calibrate([(c["load"].get(d, 0.0), t_in) for d, (_, t_in) in raw.items()])
    days = {d: {"total": round((o + i) * scale, 1), "workout": round(i * scale, 1), "everyday": round(o * scale, 1)} for d, (o, i) in raw.items()}
    return {"days": days, "scale": round(scale, 3), "calibrated_on": n, "hr_max": hr_max}


def load_analyses(session: Session) -> dict[int, dict]:
    out = {}
    for activity_id, data in session.execute(
        select(ActivityAnalysis.activity_id, ActivityAnalysis.data).where(ActivityAnalysis.version == ANALYSIS_VERSION)
    ):
        parsed = json.loads(data)
        if parsed:
            out[activity_id] = parsed
    return out


# ---- assembly ---------------------------------------------------------------------


def context(session: Session, source_id: str, today: date, now: datetime | None = None) -> dict | None:
    """Everything the coach rules need, computed once per request and shared by every page."""
    garmin = source_id == "garmin"
    weather_on = garmin and weather_store.enabled(session)
    return assemble(
        source_id, load_series(session, source_id), load_acts(session, source_id), today,
        analyses=load_analyses(session) if garmin else {},
        zones=hr_zones(session) if garmin else None,
        goal=load_goal(session),
        weights=load_weights(session, source_id),
        strength=strength_labelling(session, today) if garmin else None,
        journal={"behaviours": [journal_store.behaviour_dict(b) for b in journal_store.catalogue(session)],
                 "answers": journal_store.entries(session)},
        labels=strength_store.by_activity(session, source_id),
        hr_hists=load_hr_histograms(session, today) if garmin else None,
        weather=weather_store.by_activity(session, source_id) if weather_on else None,
        forecast=weather_store.forecast(session, now or utcnow()) if weather_on else None,
    )


def assemble(
    source_id: str, series: dict[str, A.Series], acts: list[A.Act], today: date, *,
    analyses: dict[int, dict] | None = None, zones: dict | None = None, goal: dict | None = None,
    weights: list[tuple[date, float]] | None = None, strength: dict | None = None, journal: dict | None = None,
    labels: dict[int, dict] | None = None, hr_hists: dict[date, tuple[dict, dict]] | None = None,
    weather: dict[int, dict] | None = None, forecast: list[dict] | None = None,
) -> dict | None:
    """Pure assembly of the shared context from loaded data (tests build contexts with this directly)."""
    if not series and not acts:
        return None
    analyses = analyses or {}
    weights = weights or []
    days_with_data = [d for s in series.values() for d in s] + [a.day for a in acts]
    first, as_of = min(days_with_data), min(max(days_with_data), today)
    load = A.daily_load(acts)
    pmc = A.pmc(load, first, as_of)
    hrv, sleep_hours = series.get("hrv", {}), series.get("sleep_hours", {})

    eff = A.efficiency(acts, series.get("resting_hr", {}))
    weather = weather or {}
    heat_model = W.model(eff, weather) if weather else None
    eff = W.adjust(eff, weather, heat_model)  # heat-adjusted once your personal heat cost is clear
    ref_hr = round(median(p["hr"] for p in eff) / 5) * 5 if eff else 150
    eff_trend = A.efficiency_trend(eff, ref_hr, as_of)
    act_by_id = {a.id: a for a in acts}
    durability = sorted(
        ({"id": aid, "day": act_by_id[aid].day, "name": act_by_id[aid].name, **{k: v[k] for k in ("decoupling_pct", "speed_cv", "steady", "minutes")}}
         for aid, v in analyses.items() if aid in act_by_id and "decoupling_pct" in v),
        key=lambda r: r["day"],
    )
    need = R.sleep_need(sleep_hours, hrv)

    analysed = sorted(((act_by_id[aid], v) for aid, v in analyses.items() if aid in act_by_id), key=lambda x: x[0].day)
    best_runs = [{"id": a.id, "day": a.day, "name": a.name, "best": v["best"]} for a, v in analysed if v.get("best")]
    cs = P.critical_speed(best_runs, as_of)
    max_hrs = [(a.day, a.max_hr) for a in acts if a.max_hr and a.family in ("run", "ride")]
    performance = {
        "critical_speed": cs,
        "history": P.cs_history(best_runs, as_of),
        "zone_check": P.zone_check(zones, max_hrs, [(a.day, v["hr20"]) for a, v in analysed if v.get("hr20")], as_of),
        "form": P.form_trend([{"day": a.day, **v["form"]} for a, v in analysed if v.get("form")], as_of),
        "durability": P.durability_trend([{"day": a.day, **v["late_fade"]} for a, v in analysed if v.get("late_fade")], as_of),
        "analysed_runs": len(analysed),
    }

    c = {
        "source_id": source_id, "first": first, "as_of": as_of, "acts": acts, "act_by_id": act_by_id,
        "series": series, "load": load, "pmc": pmc, "pmc_by_day": {p["day"]: p for p in pmc},
        "weeks": A.weekly(acts, load, as_of - timedelta(weeks=25), as_of),
        "split_28": A.intensity_split(acts, as_of - timedelta(days=27)),
        "eff": eff, "ref_hr": ref_hr, "eff_trend": eff_trend,
        "dec": analyses, "durability": durability,
        "sleep_need": need,
        "sleep_14": A.sleep_pattern(
            series.get("bedtime", {}), series.get("wake_time", {}), sleep_hours, as_of - timedelta(days=13), need["hours"]
        ),
        "sleep_regularity": R.sleep_regularity(series.get("bedtime", {}), series.get("wake_time", {}), as_of - timedelta(days=27), as_of),
        "vo2": sorted(series.get("vo2max", {}).items()),
        "effects": lagged_effects(series, acts, load, first, as_of, need["hours"]),
        "weights": weights,
        "weigh_ins_60d": sum(1 for d, _ in weights if d >= as_of - timedelta(days=60)),
        "strength_labelled": strength,
        "zones": zones,
        "goal": goal if goal and goal["date"] >= as_of - timedelta(days=1) else None,
        "performance": performance,
        "recovery": R.recovery_profile(hrv, acts, as_of),
        "hrv_guided": R.hrv_guided(hrv, as_of),
        "warnings": R.warning_signals(series, as_of),
        "run_load": run_load(acts, as_of),
        "spikes": distance_spikes(acts, as_of - timedelta(days=13), as_of),
    }
    c["underfuelling"] = R.underfuelling(weights, hrv, eff_trend, as_of)
    c["tonight"] = R.sleep_tonight(series, load, need["hours"], as_of)
    c["heat"] = heat_model
    c["weather_runs"] = {aid: {**w, "hot": W.hot(w), "cost_pct": W.cost_pct(heat_model, w)[0]} for aid, w in weather.items()}
    c["forecast"] = forecast or []
    c["utc_offset"] = datetime.now().astimezone().utcoffset() or timedelta(0)
    c["start_hour"] = W.usual_start_hour([a.start_local for a in acts if a.family == "run" and a.start_local and a.day > as_of - timedelta(days=90)])
    c["strain"] = strain_days(c, hr_hists or {})
    c["journal"] = journal or {"behaviours": [], "answers": {}}
    c["labels"] = labels or {}
    c["strength_content"] = strength_overview(c)
    c["habits"] = habit_insights(c)
    return c


def heavy_lower_days(c: dict) -> set[date]:
    return {c["act_by_id"][aid].day for aid, v in c.get("labels", {}).items() if aid in c["act_by_id"] and v["summary"]["heavy_lower"]}


def strength_overview(c: dict) -> dict | None:
    """What your strength sessions trained over the last 4 weeks, from the classes you've named."""
    as_of = c["as_of"]
    month = [a for a in c["acts"] if a.family == "strength" and a.day > as_of - timedelta(days=28)]
    if not month:
        return None
    labels = c.get("labels", {})
    last: dict[str, date] = {}
    counts: dict[str, int] = {}
    for a in c["acts"]:
        v = labels.get(a.id)
        if not v:
            continue
        for p in v["summary"]["patterns"]:
            last[p] = max(last.get(p, a.day), a.day)
            if a.day > as_of - timedelta(days=28):
                counts[p] = counts.get(p, 0) + 1
    week = A.week_start(as_of)
    unlabelled = [a for a in sorted(month, key=lambda a: a.day, reverse=True) if a.id not in labels]
    return {
        "sessions_28d": len(month),
        "labelled_28d": len(month) - len(unlabelled),
        "patterns_28d": counts,
        "last_trained": last,
        "heavy_lower_this_week": sum(1 for d in heavy_lower_days(c) if d >= week),
        "unlabelled": [{"id": a.id, "day": a.day, "name": a.name} for a in unlabelled[:6]],
    }


def habit_insights(c: dict) -> dict:
    """Journal behaviours against next-morning recovery and next-day running, adjusted for load and weekends."""
    j = c["journal"]
    if not any(j["answers"].values()):
        return {"effects": [], "progress": []}
    logged = {d for values in j["answers"].values() for d in values}
    readiness = {d + DAY: r["score"] for d in logged if (r := readiness_on(c, d + DAY)) is not None}
    s = c["series"]
    outcomes = {"hrv": s.get("hrv", {}), "resting_hr": s.get("resting_hr", {}), "sleep_score": s.get("sleep_score", {}),
                "readiness": readiness, "run_eff": H.run_efficiency_series(c["eff"])}
    span = list(A.daterange(min(logged), max(logged)))
    covariates = {"weekend": {d: float(d.weekday() >= 5) for d in span}, "training load": {d: c["load"].get(d, 0.0) for d in span}}
    return H.insights(j["behaviours"], j["answers"], outcomes, covariates)


def run_load(acts: list[A.Act], as_of: date) -> dict | None:
    """Running km acute:chronic (7/28-day EWMA): mechanical load that cycling fitness doesn't prepare you for."""
    km: dict[date, float] = defaultdict(float)
    for a in acts:
        if a.family == "run" and a.distance_m:
            km[a.day] += a.distance_m / 1000
    if not km:
        return None
    acute = chronic = 0.0
    for d in A.daterange(min(km), as_of):
        acute += (km.get(d, 0) - acute) / A.ATL_DAYS
        chronic += (km.get(d, 0) - chronic) / A.ACWR_CHRONIC_DAYS
    week = sum(km.get(d, 0) for d in A.daterange(as_of - 6 * DAY, as_of))
    return {"acwr": round(acute / chronic, 2) if chronic > 1 else None, "km_7d": round(week, 1), "km_week_avg_28d": round(chronic * 7, 1)}


def distance_spikes(acts: list[A.Act], start: date, end: date) -> list[dict]:
    """Runs more than 10% longer than the longest run of the previous 30 days."""
    runs = [a for a in acts if a.family == "run" and a.distance_m]
    out = []
    for a in runs:
        if not start <= a.day <= end:
            continue
        prior = [x.distance_m for x in runs if a.day - timedelta(days=30) <= x.day < a.day]
        if len(prior) >= 3 and a.distance_m > SPIKE_RATIO * max(prior):
            out.append({"id": a.id, "day": a.day, "name": a.name, "km": round(a.distance_m / 1000, 1),
                        "longest_km": round(max(prior) / 1000, 1), "pct": round((a.distance_m / max(prior) - 1) * 100)})
    return out


def readiness_on(c: dict, day: date) -> dict | None:
    return A.readiness(day, c["series"], c["pmc_by_day"], (c.get("sleep_need") or {}).get("hours", R.DEFAULT_SLEEP_NEED))


def readiness_now(c: dict, now: datetime | None = None) -> dict | None:
    """Today's readiness as it stands right now; past days keep their morning value."""
    now = now or datetime.now()
    day = c["as_of"]
    morning = readiness_on(c, day)
    if morning is None or day != now.date():
        return morning
    p = c["pmc_by_day"].get(day)
    return A.live_readiness(
        morning, c["series"].get("body_battery_now", {}).get(day), [a for a in c["acts"] if a.day == day],
        p["fitness"] if p else 0.0, now, (c.get("recovery") or {}).get("half_life_h", A.STRAIN_HALF_LIFE_H),
    )


def build(session: Session, source_id: str, today: date) -> dict:
    ctx = context(session, source_id, today)
    if ctx is None:
        return {"has_data": False, "goal": _goal_dict(load_goal(session))}
    as_of, series, load = ctx["as_of"], ctx["series"], ctx["load"]
    pmc, pmc_by_day = ctx["pmc"], ctx["pmc_by_day"]
    ready_days = [r for d in A.daterange(as_of - timedelta(days=89), as_of) if (r := readiness_on(ctx, d)) is not None]
    today_ready = readiness_now(ctx) if ready_days and ready_days[-1]["day"] == as_of else None
    sleep_hours = series.get("sleep_hours", {})
    eff, eff_trend, durability, weeks = ctx["eff"], ctx["eff_trend"], ctx["durability"], ctx["weeks"]
    findings = sorted(coach(ctx), key=lambda f: SEVERITY_ORDER[f["severity"]])
    pending = (len(pending_analyses(session)) + len(pending_strain_days(session))) if source_id == "garmin" else 0
    ref_hr, rhr_ref = ctx["ref_hr"], eff_trend["rhr"] if eff_trend else None

    return {
        "has_data": True,
        "source_id": source_id,
        "as_of": as_of,
        "readiness": today_ready,
        "recommendation": recommend(today_ready, pmc_by_day.get(as_of), load.get(as_of - DAY, 0), ctx.get("warnings"), ctx.get("hrv_guided")),
        "readiness_history": [{"day": r["day"], "score": r["score"]} for r in ready_days],
        "readiness_validation": R.readiness_validation(ctx, readiness_on),
        "findings": findings,
        "pmc": pmc[-365:],
        "weeks": weeks,
        "intensity_28d": ctx["split_28"],
        "efficiency": {
            "runs": [{**p, "pace_s": round(A.pace_at_hr(p["ef"], ref_hr, rhr_ref) or 0)} for p in eff[-200:]] if rhr_ref is not None else [],
            "trend": eff_trend,
        },
        "durability": durability[-60:],
        "vo2max": [{"day": d, "value": v} for d, v in ctx["vo2"]],
        "sleep": {
            "pattern_14d": ctx["sleep_14"],
            "need": ctx["sleep_need"],
            "tonight": ctx["tonight"],
            "target_check": (e.__dict__ if (e := R.sleep_target_check(series, load, ctx["sleep_need"]["hours"], as_of)) else None),
            "regularity": ctx["sleep_regularity"],
            "nights": [
                {"day": d, "bedtime": series.get("bedtime", {}).get(d), "wake": series.get("wake_time", {}).get(d), "hours": sleep_hours.get(d)}
                for d in A.daterange(as_of - timedelta(days=59), as_of) if d in sleep_hours
            ],
        },
        "effects": [e.__dict__ for e in ctx["effects"]],
        "plan": training_plan.weekly_plan(ctx),
        "goal": _goal_dict(ctx["goal"] or load_goal(session)),
        "performance": ctx["performance"],
        "hrv_guided": ctx["hrv_guided"],
        "recovery": ctx["recovery"],
        "warnings": ctx["warnings"],
        "run_load": ctx["run_load"],
        "strength": ctx["strength_labelled"],
        "habits": {"effects": [e.__dict__ for e in ctx["habits"]["effects"]], "progress": ctx["habits"]["progress"]},
        "strength_content": ctx["strength_content"],
        "heat": ctx["heat"],
        "strain": ({"days": [{"day": d, **v} for d, v in sorted(ctx["strain"]["days"].items()) if d > as_of - timedelta(days=365)],
                    "scale": ctx["strain"]["scale"], "calibrated_on": ctx["strain"]["calibrated_on"], "hr_max": ctx["strain"]["hr_max"]}
                   if ctx["strain"] else None),
        "hr_zones": ctx["zones"],
        "analysis_pending": pending,
    }


def _goal_dict(goal: dict | None) -> dict | None:
    return training_plan._goal_view(goal)  # pylint: disable=protected-access


def hr_zones(session: Session) -> dict | None:
    _, payload = vault.load(session, "hr_zones")
    rows = payload if isinstance(payload, list) else []
    zone = next((z for z in rows if isinstance(z, dict) and z.get("sport") == "RUNNING"), None) or next(
        (z for z in rows if isinstance(z, dict) and z.get("sport") == "DEFAULT"), None
    )
    if not zone or not isinstance(zone.get("zone3Floor"), int):
        return None
    return {
        "method": zone.get("trainingMethod"),
        "floors": [zone.get(f"zone{i}Floor") for i in range(1, 6)],
        "max": zone.get("maxHeartRateUsed"),
        "threshold": zone.get("lactateThresholdHeartRateUsed"),
    }


def weekly_plan(c: dict, zones: dict | None = None) -> dict | None:
    """Kept for callers that pass zones explicitly; the context already carries them."""
    if zones is not None and c.get("zones") is None:
        c = {**c, "zones": zones}
    return training_plan.weekly_plan(c)


def strength_labelling(session: Session, today: date | None = None) -> dict:
    """How many strength sessions name their exercises, and sets/reps/volume per movement over the last 4 weeks."""
    total = labelled = 0
    since = (today - timedelta(days=27)).isoformat() if today else None
    by_cat: dict[str, dict] = defaultdict(lambda: {"sets": 0, "reps": 0, "volume_kg": 0.0, "sessions": 0})
    for item in vault.activity_summaries(session).values():
        sets = item.get("summarizedExerciseSets") or []
        if not sets:
            continue
        total += 1
        named = [s for s in sets if s.get("category") not in (None, "UNKNOWN", "WARM_UP")]
        if named:
            labelled += 1
        if since and str(item.get("startTimeLocal") or "")[:10] >= since:
            for s in named:
                row = by_cat[str(s["category"])]
                row["sets"] += int(s.get("sets") or 0)
                row["reps"] += int(s.get("reps") or 0)
                # Garmin reports volume in grams lifted.
                row["volume_kg"] += float(s.get("volume") or 0) / 1000
                row["sessions"] += 1
    return {
        "sessions": total, "labelled": labelled,
        "by_category": sorted(({"category": k.replace("_", " ").title(), **v, "volume_kg": round(v["volume_kg"])} for k, v in by_cat.items()),
                              key=lambda r: -r["sets"]),
    }


# ---- lagged effects -----------------------------------------------------------------


def lagged_effects(
    series: dict[str, A.Series], acts: list[A.Act], load: A.Series, first: date, last: date, sleep_need: float = R.DEFAULT_SLEEP_NEED,
) -> list[A.Effect]:
    out: list[A.Effect] = []
    hrv, rhr = series.get("hrv", {}), series.get("resting_hr", {})
    sleep_score, sleep_hours = series.get("sleep_score", {}), series.get("sleep_hours", {})
    stress, bedtime, steps = series.get("stress", {}), series.get("bedtime", {}), series.get("steps", {})
    covered = [d for d in A.daterange(first, last) if d in hrv or d in sleep_hours]
    weekend = {d: float(d.weekday() >= 5) for d in A.daterange(first, last)}
    load_cov = {d: load.get(d, 0.0) for d in A.daterange(first, last)}
    # Adjust non-load comparisons for that day's training and weekends: evening workouts, late nights and busy days
    # cluster with harder training and weekend routines.
    adjust = {"weekend": weekend, "training load": load_cov}

    def add(effect: A.Effect | None) -> None:
        if effect is not None:
            out.append(effect)

    positive = [v for v in load.values() if v > 0]
    if positive:
        high = A.quantile(positive, 0.75)
        hard = {d for d in covered if load.get(d, 0) >= high}
        rest = {d for d in covered if load.get(d, 0) == 0}
        label_hard = f"Hard days (load ≥ {round(high)})"
        only_weekend = {"weekend": weekend}
        add(A.compare("load_hrv", "Training load", "HRV next morning", label_hard, "Rest days", hard, rest, hrv, 1, "ms", True, only_weekend))
        add(A.compare("load_rhr", "Training load", "Resting HR next day", label_hard, "Rest days", hard, rest, rhr, 1, "bpm", False, only_weekend))
        add(A.compare("load_sleep", "Training load", "Sleep score that night", label_hard, "Rest days", hard, rest, sleep_score, 1, "", True, only_weekend))

    if sleep_hours:
        short_cut = sleep_need - 1.0
        short = {d for d, h in sleep_hours.items() if h < short_cut}
        long_ = {d for d, h in sleep_hours.items() if R.sleep_ok(h, sleep_need)}
        short_label, long_label = f"Nights < {short_cut:g} h", f"Nights ≥ {sleep_need - 0.25:g} h"
        add(A.compare("sleep_hrv", "Sleep duration", "HRV that night", short_label, long_label, short, long_, hrv, 0, "ms", True, adjust))
        add(A.compare("sleep_stress", "Sleep duration", "Stress the next day", short_label, long_label, short, long_, stress, 0, "", False, adjust))
        add(A.compare("sleep_rhr", "Sleep duration", "Resting HR that day", short_label, long_label, short, long_, rhr, 0, "bpm", False, adjust))

    if bedtime:
        late = {d for d, v in bedtime.items() if v >= 30}
        early = {d for d, v in bedtime.items() if v <= -30}
        add(A.compare("bed_score", "Bedtime", "Sleep score", "Asleep after 00:30", "Asleep before 23:30", late, early, sleep_score, 0, "", True, adjust))
        add(A.compare("bed_hrv", "Bedtime", "Overnight HRV", "Asleep after 00:30", "Asleep before 23:30", late, early, hrv, 0, "ms", True, adjust))

    evening, daytime = set(), set()
    for a in acts:
        if a.end_local is None or a.family == "other" or a.load < 20:
            continue
        (evening if a.end_local.hour >= 20 else daytime if a.end_local.hour < 18 else set()).add(a.day)
    daytime -= evening
    add(A.compare("late_sleep", "Workout timing", "Sleep score that night", "Workouts ending after 20:00", "Workouts done before 18:00", evening, daytime, sleep_score, 1, "", True, adjust))
    add(A.compare("late_hrv", "Workout timing", "HRV that night", "Workouts ending after 20:00", "Workouts done before 18:00", evening, daytime, hrv, 1, "ms", True, adjust))

    if stress:
        values = list(stress.values())
        hi, lo = A.quantile(values, 0.75), A.quantile(values, 0.25)
        add(A.compare("stress_sleep", "Daytime stress", "Sleep score that night", f"Stress ≥ {round(hi)}", f"Stress ≤ {round(lo)}",
                      {d for d, v in stress.items() if v >= hi}, {d for d, v in stress.items() if v <= lo}, sleep_score, 1, "", True, adjust))

    if steps:
        add(A.compare("steps_sleep", "Daily steps", "Sleep score that night", "≥ 12k steps", "< 6k steps",
                      {d for d, v in steps.items() if v >= 12000}, {d for d, v in steps.items() if v < 6000}, sleep_score, 1, "", True, adjust))

    A.control_fdr(out)
    out.sort(key=lambda e: (not e.significant, -abs(e.effect_size)))
    return out


# ---- coach ---------------------------------------------------------------------------


def finding(fid, severity, category, title, detail, action=None, evidence=None, link=None) -> dict:
    return {"id": fid, "severity": severity, "category": category, "title": title, "detail": detail,
            "action": action, "evidence": evidence or [], "link": link}


def fmt_clock(minutes: float) -> str:
    m = round(minutes) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _pace(s: float) -> str:
    m, sec = divmod(round(s), 60)
    return f"{m}:{sec:02d}"


EFFECT_ACTIONS = {
    "load": "Follow hard days with an easy day or rest.",
    "sleep": "Protect full nights, especially before key sessions.",
    "bed": "Be asleep before 23:30.",
    "late": "Finish hard sessions before 18:00 when you can.",
    "stress": "On high-stress days, wind down early and keep training easy.",
    "steps": "Get more easy walking in on low-movement days.",
}


def _lc(text: str) -> str:
    """Lower-case the first letter for use mid-sentence, leaving acronyms like HRV alone."""
    return text if text[:2].isupper() else text[:1].lower() + text[1:]


def _race_time(s: float) -> str:
    h, rem = divmod(round(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def coach(c: dict) -> list[dict]:  # noqa: C901 - a flat list of independent rules reads best
    out: list[dict] = []
    as_of: date = c["as_of"]
    pmc, acts, series = c["pmc"], c["acts"], c["series"]
    latest = pmc[-1] if pmc else None
    need = (c.get("sleep_need") or {}).get("hours", R.DEFAULT_SLEEP_NEED)
    run_load_ = c.get("run_load") or {}
    run_spiking = bool(run_load_.get("acwr") and run_load_["acwr"] > 1.5)

    # Early warning first: several body signals agreeing outrank any training rule.
    w = c.get("warnings")
    if w:
        out.append(finding("warning", w["level"], "Recovery", "Early warning: several signals are off",
                           f"{len(w['signals'])} independent markers moved together" + (" for two days running" if w["persisting"] else "")
                           + ". This pattern often comes before illness or follows overreaching.",
                           "Skip intensity, keep any training short and easy, and sleep early until they settle.",
                           [{"label": s["key"].upper() if s["key"] != "respiration" else "Breathing", "value": s["label"]} for s in w["signals"]]))

    # Load management. ACWR alone is a weak injury predictor (Impellizzeri 2020), so it only alerts when corroborated.
    if latest and latest["acwr"] is not None:
        r = latest["acwr"]
        ev = [{"label": "Acute:chronic", "value": f"{r:.2f}"}, {"label": "Fitness", "value": round(latest["fitness"])}, {"label": "Fatigue", "value": round(latest["fatigue"])}]
        recovering = training_plan.is_recovery_week(c, as_of) if c.get("weeks") else False
        if r > 1.5:
            corroborated = run_spiking or bool(w)
            out.append(finding("acwr", "alert" if corroborated else "warn", "Load", "Load spike",
                               f"Your last week's load is {r:.1f}× your 4-week norm" + (", and running volume spiked with it." if run_spiking else ".")
                               + " Big jumps are when fatigue outruns adaptation.",
                               "Hold the next few days easy until the ratio drifts back toward 1.0–1.3.", ev, "#load"))
        elif r > 1.3:
            out.append(finding("acwr", "warn", "Load", "Load climbing fast", f"Acute:chronic ratio is {r:.2f} — above the 0.8–1.3 range where fitness builds with the least risk.", "Keep this week's volume flat rather than adding more.", ev, "#load"))
        elif r < 0.8 and recovering:
            out.append(finding("acwr", "good", "Load", "Planned lighter week", f"Load is {r:.2f}× your recent norm, as a recovery or taper week should be.", None, ev, "#load"))
        elif r < 0.8:
            out.append(finding("acwr", "info", "Load", "Load is tapering off", f"You're training at {r:.2f}× your recent norm. Fine for a planned taper or rest week; sustained, fitness will fade.", "If this isn't intentional, rebuild gradually (~10% per week).", ev, "#load"))
        else:
            out.append(finding("acwr", "good", "Load", "Load in the productive zone", f"Acute:chronic ratio {r:.2f} sits inside 0.8–1.3: enough stimulus to improve without a spike.", None, ev, "#load"))
    if latest and latest["fitness"] > 5:
        ratio = latest["form"] / latest["fitness"]
        if ratio < -0.3:
            out.append(finding("form", "warn", "Recovery", "Carrying deep fatigue", f"Form is {latest['form']:.0f} ({ratio:.0%} of fitness). Hard sessions now tend to be lower quality.", "Insert 1–2 easy days before your next key workout.", link="#load"))
        elif ratio > 0.25:
            out.append(finding("form", "info", "Load", "You're fresh", f"Form is +{latest['form']:.0f}. A good window for a hard session, race or time trial.", link="#load"))

    # Running-specific mechanical load
    if run_spiking:
        out.append(finding("run_load", "warn", "Injury risk", "Running volume spiking",
                           f"{run_load_['km_7d']:.0f} km in the last 7 days vs a recent weekly norm of {run_load_['km_week_avg_28d']:.0f} km. "
                           "Tendons and bones adapt more slowly than your heart and lungs.",
                           "Keep running km flat for a week; get extra aerobic work on the bike if you want it.",
                           [{"label": "Run acute:chronic", "value": f"{run_load_['acwr']:.2f}"}], "#weeks"))
    for s in c.get("spikes", [])[-1:]:
        out.append(finding("distance_spike", "warn", "Injury risk", f"{s['name']} was a {s['pct']}% distance jump",
                           f"{s['km']:.1f} km on {s['day']:%d %b} vs your longest of {s['longest_km']:.1f} km in the 30 days before. "
                           "In a large study of Garmin runners, single runs more than 10% longer than the recent longest carried "
                           "a clearly higher overuse-injury risk.",
                           "Grow the long run by at most 10% at a time; the plan caps it for you.", link="#weeks"))

    full_weeks = [w for w in c["weeks"] if w["complete"]]
    if full_weeks and full_weeks[-1]["monotony"] and full_weeks[-1]["monotony"] > 2:
        wk = full_weeks[-1]
        out.append(finding("monotony", "warn", "Load", "Every day looks the same", f"Last week's training monotony was {wk['monotony']:.1f} (Foster flags > 2). Little contrast between hard and easy days blunts adaptation.", "Make hard days harder and easy days genuinely easy, with at least one full rest day.", [{"label": "Strain", "value": wk["strain"]}], "#weeks"))

    last14 = [as_of - timedelta(days=i) for i in range(14)]
    rest = sum(1 for d in last14 if c["load"].get(d, 0) == 0)
    if rest < 2:
        out.append(finding("rest", "warn", "Recovery", "No real rest in two weeks", f"Only {rest} zero-load day{'s' if rest != 1 else ''} in the last 14. Adaptation happens during recovery.", "Schedule at least one full rest day per week.", link="#weeks"))

    # Intensity distribution (runs, rides and swims only: walks would make it look easier than it is)
    split = c["split_28"]
    if split:
        ev = [{"label": "Easy (Z1–2)", "value": f"{split['easy_pct']}%"}, {"label": "Moderate (Z3)", "value": f"{split['moderate_pct']}%"}, {"label": "Hard (Z4–5)", "value": f"{split['hard_pct']}%"}]
        if split.get("hard_sessions_pct") is not None:
            ev.append({"label": "Hard sessions", "value": f"{split['hard_sessions_pct']}%"})
        run = (split.get("by_sport") or {}).get("run")
        if split["easy_pct"] < 70:
            out.append(finding("intensity", "warn", "Intensity", "Not enough easy training",
                               f"Only {split['easy_pct']}% of your run/ride/swim time in the last 4 weeks was easy. Well-trained endurance athletes spend ~80% of sessions and ~90% of time easy"
                               + (f"; {split['moderate_pct']}% of yours sits in the 'grey zone' (Z3)." if split["moderate_pct"] >= 20 else "."),
                               "Slow most sessions down to conversational (Z2) and keep intensity for 1–2 dedicated sessions a week.", ev, "#intensity"))
        elif run and run["easy_pct"] < 70 and split["easy_pct"] >= 70:
            out.append(finding("intensity", "warn", "Intensity", "Your runs are too hard",
                               f"Overall {split['easy_pct']}% easy, but only {run['easy_pct']}% of running time. Other sports are hiding it.",
                               "Keep easy runs below your Zone 3 floor.", ev, "#intensity"))
        elif split["easy_pct"] >= 75:
            out.append(finding("intensity", "good", "Intensity", "Intensity mix looks polarised", f"{split['easy_pct']}% easy over the last 4 weeks — close to the polarised pattern endurance athletes use.", None, ev, "#intensity"))

    # Long run
    runs_28 = [a for a in acts if a.family == "run" and a.day > as_of - timedelta(days=28)]
    longest_21 = max((a.moving_s or 0 for a in runs_28 if a.day > as_of - timedelta(days=21)), default=0)
    if len(runs_28) >= 4 and longest_21 < 75 * 60:
        out.append(finding("long_run", "info", "Aerobic", "No long run lately", f"You ran {len(runs_28)} times in 4 weeks but nothing over 75 minutes in the last 3. Long, easy runs drive aerobic durability.", "Add one weekly long run at easy effort, growing ~10 minutes per week.", [{"label": "Longest (21d)", "value": f"{round(longest_21 / 60)} min"}], "#aerobic"))

    # Aerobic engine
    t = c["eff_trend"]
    if t and t["change_pct_90d"] is not None:
        pace_now, pace_then = t["pace_now_s"], t["pace_90d_ago_s"]
        ev = [{"label": f"Pace @ {t['ref_hr']} bpm now", "value": f"{pace_now // 60}:{pace_now % 60:02d}/km"}, {"label": "90 days ago", "value": f"{pace_then // 60}:{pace_then % 60:02d}/km" if pace_then else "—"}, {"label": "Runs", "value": t["n"]}]
        if t["significant"] and t["change_pct_90d"] > 0:
            out.append(finding("efficiency", "good", "Aerobic", "Aerobic engine improving", f"At the same heart rate you're running {t['change_pct_90d']:.1f}% faster than 90 days ago.", None, ev, "#aerobic"))
        elif t["significant"] and t["change_pct_90d"] < 0:
            out.append(finding("efficiency", "warn", "Aerobic", "Aerobic efficiency slipping", f"Pace at a given heart rate is {abs(t['change_pct_90d']):.1f}% slower than 90 days ago. Common causes: accumulated fatigue, heat, or too little easy volume.", "Prioritise consistent Z2 running and check sleep/recovery trends.", ev, "#aerobic"))
        else:
            out.append(finding("efficiency", "info", "Aerobic", "Aerobic efficiency is flat", "Pace at the same heart rate hasn't changed meaningfully in 90 days.", "More easy volume is the most reliable way to move this number.", ev, "#aerobic"))

    recent_dur = [r for r in c["durability"] if r.get("steady") and r["day"] > as_of - timedelta(days=120) and r["minutes"] >= 35]
    if len(recent_dur) >= 3:
        med = median(r["decoupling_pct"] for r in recent_dur)
        ev = [{"label": "Median HR drift", "value": f"{med:.1f}%"}, {"label": "Steady runs", "value": len(recent_dur)}]
        if med > 5:
            out.append(finding("durability", "warn", "Aerobic", "Heart rate drifts on long runs", f"On steady runs over 45 min your grade-adjusted efficiency drops {med:.1f}% from first to second half (Friel's benchmark: under 5%). Your aerobic base isn't yet supporting that duration.", "Build longer Z2 runs until drift stays under 5%, then extend.", ev, "#aerobic"))
        else:
            out.append(finding("durability", "good", "Aerobic", "Solid aerobic durability", f"Median drift of {med:.1f}% on steady long runs — under the 5% benchmark.", None, ev, "#aerobic"))

    perf = c.get("performance") or {}
    late = perf.get("durability")
    if late and late["fade_before"] is not None and abs(late["fade_now"] - late["fade_before"]) >= 2:
        better = late["fade_now"] < late["fade_before"]
        out.append(finding("late_fade", "good" if better else "warn", "Aerobic", "Late-run fade " + ("shrinking" if better else "growing"),
                           f"In the last 20 minutes of runs over 75 min, efficiency now drops {late['fade_now']:.1f}% (was {late['fade_before']:.1f}% the 90 days before).",
                           None if better else "Fuel long runs (30–60 g carbs/hour after the first hour) and extend them gradually.", link="#performance"))

    vo2 = c["vo2"]
    if len(vo2) >= 2:
        cur_day, cur = vo2[-1]
        past = [v for d, v in vo2 if d <= cur_day - timedelta(days=90)]
        if past:
            delta = cur - past[-1]
            if abs(delta) >= 1:
                out.append(finding("vo2", "good" if delta > 0 else "warn", "Aerobic", f"VO₂ max {'up' if delta > 0 else 'down'} {abs(delta):.0f} in 90 days", f"Garmin's estimate moved from {past[-1]:.0f} to {cur:.0f}.", None, [{"label": "Current", "value": round(cur)}], "#aerobic"))

    # Performance: critical speed, zones, form
    cs = perf.get("critical_speed")
    runner = sum(1 for a in acts if a.family == "run" and a.day > as_of - timedelta(days=56)) >= 6
    if cs and cs["valid"]:
        five = next(p for p in cs["predictions"] if p["key"] == "5k")
        hist = perf.get("history") or []
        ev = [{"label": "Critical speed", "value": f"{_pace(cs['pace_s'])}/km"}, {"label": "D′", "value": f"{cs['d_prime_m']} m"},
              {"label": "5 km now", "value": _race_time(five["seconds"])}]
        change = (hist[-1]["cs_mps"] / hist[0]["cs_mps"] - 1) * 100 if len(hist) >= 3 else None
        out.append(finding("critical_speed", "good" if change is None or change >= 0 else "warn", "Performance",
                           f"Critical speed {_pace(cs['pace_s'])}/km" + (f", {'up' if change >= 0 else 'down'} {abs(change):.1f}% this year" if change is not None else ""),
                           "Your fastest sustainable pace for about 30 minutes, fitted from your best 3–20 minute efforts. It sets your threshold and interval paces in the plan.",
                           None, ev, "#performance"))
    elif cs and runner:
        out.append(finding("critical_speed", "info", "Missing data", "Add two hard efforts to unlock pace zones",
                           f"Your recent runs don't include {cs.get('missing', 'maximal efforts')}, so critical speed and race predictions can't be fitted.",
                           "After a good warm-up, run 3 minutes all-out, recover 30 minutes easy, then 12 minutes all-out. Or race a 5 km.",
                           link="#performance"))
    hm = c.get("heat")
    if hm and hm.get("significant"):
        out.append(finding("heat_cost", "info", "Performance", f"Heat costs you {abs(hm['slope_pct_per_c']):.1f}% per °C of dew point",
                           f"Across {hm['n']} runs ({hm['warm']} warm), each °C of dew point above 10 °C lowered your efficiency by about "
                           f"{abs(hm['slope_pct_per_c']):.1f}%. Your efficiency trend is now heat-adjusted, so summer won't look like lost fitness.",
                           "On hot days, run early or slow down by that much at the same effort.", link="#aerobic"))
    zc = perf.get("zone_check")
    if zc and zc["status"] == "stale":
        out.append(finding("zones", "warn", "Performance", "Your heart-rate zones look out of date",
                           " ".join(i["detail"] for i in zc["issues"]) + " Every easy cap, intensity split and verdict here depends on these zones.",
                           "Update max/threshold heart rate in Garmin Connect (or run the watch's lactate-threshold test); Cadence picks them up on the next sync.",
                           [{"label": i["label"], "value": f"{i['zones']} → {i['observed']} bpm"} for i in zc["issues"]], "#performance"))
    form = perf.get("form")
    if form and form.get("cadence_before") and abs(form["cadence_now"] - form["cadence_before"]) >= 3:
        up = form["cadence_now"] > form["cadence_before"]
        out.append(finding("cadence", "info", "Form", f"Cadence {'up' if up else 'down'} {abs(form['cadence_now'] - form['cadence_before'])} spm",
                           f"At {_pace(form['ref_pace_s'])}/km you now take {form['cadence_now']} steps/min (was {form['cadence_before']}). "
                           + ("Shorter, quicker steps usually lower impact loading." if up else "Often a sign of fatigue or longer, heavier strides."),
                           None, [{"label": "Runs", "value": form["n"]}], "#performance"))

    # Recovery signals
    hrv = series.get("hrv", {})
    g = c.get("hrv_guided")
    if g:
        ev = [{"label": "7-day HRV", "value": f"{g['mean7_ms']:.0f} ms"}, {"label": "Normal range", "value": f"{g['range_ms'][0]:.0f}–{g['range_ms'][1]:.0f} ms"},
              {"label": "Day-to-day variation", "value": f"{g['cv7']:.1f}% (usual {g['cv_base']:.1f}%)"}]
        if g["status"] == "below":
            out.append(finding("hrv", "warn", "Recovery", "HRV below your normal range",
                               f"Your 7-day HRV ({g['mean7_ms']:.0f} ms) sits under your normal range" + (" and is swinging more than usual: classic signs of not coping with the current load." if g["coping"] == "struggling" else ".")
                               + " HRV-guided training studies keep sessions easy until it returns.", "Easy sessions only until the 7-day average is back in range.", ev, "/metrics/hrv"))
        elif g["coping"] == "strained":
            out.append(finding("hrv", "info", "Recovery", "HRV wobbling", "Still in range, but trending down with bigger day-to-day swings than usual.", "Protect sleep this week; don't add load.", ev, "/metrics/hrv"))
        else:
            out.append(finding("hrv", "good", "Recovery", "HRV-guided: green light", f"Your 7-day HRV ({g['mean7_ms']:.0f} ms) is {'above' if g['status'] == 'above' else 'inside'} your normal range: hard training is supported.", None, ev, "/metrics/hrv"))

    rhr = series.get("resting_hr", {})
    r3 = [rhr[d] for d in last14[:3] if d in rhr]
    rb = [rhr[d] for d in A.daterange(as_of - timedelta(days=63), as_of - timedelta(days=4)) if d in rhr]
    if len(r3) == 3 and len(rb) >= A.MIN_BASELINE and not w:
        m3, mb, sd = fmean(r3), fmean(rb), pstdev(rb) or 1
        if m3 - mb >= 3 and (m3 - mb) / sd >= 1.5:
            out.append(finding("rhr", "warn", "Recovery", "Resting heart rate elevated", f"Last 3 days average {m3:.0f} bpm vs your usual {mb:.0f}. Often precedes illness or signals overreaching.", "Back off intensity and prioritise sleep for a few days.", [{"label": "3-day", "value": f"{m3:.0f} bpm"}, {"label": "Baseline", "value": f"{mb:.0f} bpm"}], "/metrics/resting_hr"))

    rec = c.get("recovery") or {}
    hard_rec = (rec.get("kinds") or {}).get("hard")
    if hard_rec and hard_rec["personal"] and hard_rec["days"] >= 3:
        out.append(finding("recovery_cost", "info", "Recovery", f"Hard sessions take you {hard_rec['days']:g} days to absorb",
                           f"Across {hard_rec['n']} isolated hard sessions, your HRV took a median {hard_rec['days']:g} days to return to its pre-session level. "
                           "The plan spaces quality sessions to match.", None, [{"label": "Spacing", "value": f"{rec['hard_spacing_days']} days"}], "#recovery"))

    f = c.get("underfuelling")
    if f:
        out.append(finding("underfuelling", "warn", "Fuelling", "Possible under-fuelling",
                           f"Weight is falling {abs(f['rate_pct_week']):.1f}% a week while HRV is down ({f['hrv_z']:+.1f} SD) and aerobic efficiency isn't improving. "
                           "Together these match low energy availability (RED-S), which erodes training adaptation, bone health and hormones.",
                           "Eat more on training days, especially carbohydrate around sessions. If it persists, talk to a sports dietitian or doctor.",
                           [{"label": "Weight trend", "value": f"{f['rate_kg_week']:+.2f} kg/wk"}], "/weight"))

    s = c["sleep_14"]
    if s:
        ev = [{"label": "Avg sleep", "value": f"{s['avg_hours']:.1f} h"}, {"label": f"Nights under {need:g} h", "value": f"{s['nights_short']}/{s['nights']}"}]
        if s["avg_hours"] < need - 0.75:
            out.append(finding("sleep", "warn", "Sleep", "Under-sleeping for training", f"You've averaged {s['avg_hours']:.1f} h over 2 weeks against your {need:g} h need; 7-day debt is {s['debt_hours']:.0f} h.", "Move bedtime earlier by 30 minutes before adding training.", ev, "#sleep"))
        sri = c.get("sleep_regularity")
        if sri and sri["sri"] < 70:
            out.append(finding("bedtime", "warn", "Sleep", "Irregular sleep timing", f"Your Sleep Regularity Index is {sri['sri']} (regular sleepers score 80+); your sleep midpoint moves by ±{sri['midpoint_sd_min']} min. Regular timing improves sleep quality and HRV.", "Fix your wake time first, then a lights-out window within 30 minutes.", [{"label": "SRI", "value": sri["sri"]}], "#sleep"))
        elif not sri and s["bedtime_sd_min"] and s["bedtime_sd_min"] > 60:
            out.append(finding("bedtime", "warn", "Sleep", "Irregular bedtime", f"Your bedtime varies by ±{s['bedtime_sd_min']} min (average {fmt_clock(s['avg_bedtime_min'])}). Regular timing improves sleep quality and HRV.", "Pick a fixed lights-out window within 30 minutes.", [{"label": "Avg bedtime", "value": fmt_clock(s["avg_bedtime_min"])}], "#sleep"))
        elif s["avg_hours"] >= need - 0.25 and (s["bedtime_sd_min"] or 0) <= 45:
            out.append(finding("sleep", "good", "Sleep", "Sleep is supporting your training", f"{s['avg_hours']:.1f} h on average with a consistent bedtime.", None, ev, "#sleep"))

    # Consistency
    recent_weeks = full_weeks[-12:]
    if len(recent_weeks) >= 6:
        avg = fmean(wk["total_sessions"] for wk in recent_weeks)
        zero = sum(1 for wk in recent_weeks if wk["total_sessions"] == 0)
        days = sorted({a.day for a in acts if a.day > as_of - timedelta(days=90) and A.is_training(a)})
        gap = max(((b - a).days for a, b in zip(days, days[1:])), default=0)
        if zero or gap >= 7:
            out.append(finding("consistency", "info", "Consistency", "Training has gaps", f"{zero} empty week{'s' if zero != 1 else ''} in the last 12; longest break {gap} days in 90.", "Consistency compounds: protect a minimum of 3 sessions in busy weeks.", [{"label": "Sessions/week", "value": f"{avg:.1f}"}], "#weeks"))
        else:
            out.append(finding("consistency", "good", "Consistency", "Remarkably consistent", f"{avg:.1f} training sessions per week for 12 weeks with no gap over {gap} days.", None, [{"label": "Sessions/week", "value": f"{avg:.1f}"}], "#weeks"))
        strength = fmean(wk.get("strength_sessions", 0) for wk in recent_weeks[-4:])
        if runner and strength < 1:
            out.append(finding("strength_freq", "info", "Strength", "Add strength twice a week",
                               f"{strength:.1f} strength sessions a week over the last month. Heavy strength work improves running economy and lowers injury risk.",
                               "Two 30–40 minute sessions: squats or deadlifts, single-leg work, calf raises, hip and core.", link="#weeks"))

    # Strength content from named classes
    heavy = heavy_lower_days(c)
    key_runs = {a.day for a in acts if a.family == "run" and (A.is_hard(a) or (a.moving_s or 0) >= A.LONG_MIN["run"] * 60)}
    clashes = sorted(d for d in heavy if d + DAY in key_runs and d > as_of - timedelta(days=28))
    if clashes:
        out.append(finding("heavy_legs", "warn", "Strength", "Heavy legs the day before key runs",
                           f"{len(clashes)} time{'s' if len(clashes) != 1 else ''} in 4 weeks a heavy lower-body class came the day before a quality "
                           f"or long run (last on {clashes[-1]:%d %b}). Leg fatigue blunts the run, and the run delays the strength recovery.",
                           "Put heavy leg work on a hard-run day (after the run) or 2+ days before the next one.", link="#strength"))
    sc = c.get("strength_content")
    if sc and runner and sc["labelled_28d"] >= 2:
        for pattern, label, why in (("hinge", "No hip-hinge work in 2 weeks", "Deadlifts, RDLs, bridges and swings build the hamstrings and glutes that protect a runner's hips and knees."),
                                    ("lunge", "No single-leg work in 3 weeks", "Lunges, split squats and step-ups train the one-leg stability running depends on.")):
            last_day = sc["last_trained"].get(pattern)
            limit = 14 if pattern == "hinge" else 21
            if last_day is None or (as_of - last_day).days > limit:
                out.append(finding(f"missing_{pattern}", "info", "Strength", label, why, "Ask for it in class or add one set after a session.", link="#strength"))
    if sc and sc["sessions_28d"] >= 3 and sc["labelled_28d"] == 0:
        out.append(finding("strength_names", "info", "Missing data", "Name your classes to unlock strength insights",
                           f"{sc['sessions_28d']} strength sessions in 4 weeks, none named. Paste the class list from its screenshot (iPhone: long-press → Copy text) on the session page.",
                           link="#strength"))

    # Data gaps that block insights
    if c["weigh_ins_60d"] is not None and c["weigh_ins_60d"] < 4:
        out.append(finding("weight_data", "info", "Missing data", "Too few weigh-ins to track body composition", f"{c['weigh_ins_60d']} weigh-in{'s' if c['weigh_ins_60d'] != 1 else ''} in 60 days. Power-to-weight and fuelling trends need a weekly reading.", "Weigh in once a week, same morning routine.", link="/weight"))
    sl = c["strength_labelled"]
    if sl and sl["sessions"] >= 5 and sl["labelled"] / sl["sessions"] < 0.2:
        out.append(finding("strength_data", "info", "Missing data", "Strength exercises aren't being recorded", f"{sl['sessions']} strength sessions have set data but none name the exercise, so muscle balance and progressive overload can't be tracked.", "Use a structured strength workout on the watch, or confirm exercise names in Garmin Connect after each session."))

    # Journal habits with a clear effect on your recovery
    for key, e in H.strongest((c.get("habits") or {}).get("effects", [])).items():
        bad = H.worse(e)
        diff = f"{abs(e.diff):.0f}{' ' + e.unit if e.unit and e.unit != '%' else e.unit} "
        out.append(finding(
            f"habit_{key}", "warn" if bad else "good", "Your habits",
            f"{e.exposed} {'costs' if bad else 'adds'} you {diff}{'of' if bad else 'to'} {_lc(e.outcome)}",
            f"After {_lc(e.exposed)} days your {_lc(e.outcome)} averages {e.exposed_mean:.0f} vs {e.reference_mean:.0f} after {_lc(e.reference)} days "
            f"({e.n_exposed} vs {e.n_reference}), still {abs(e.diff):.0f} after allowing for training load and weekends.",
            ("Cut it back before key sessions and long runs." if bad else "Keep it in your routine."),
            [{"label": "Effect size", "value": f"{abs(e.effect_size):.1f} SD"}, {"label": "Confidence", "value": f"q = {e.q_value:.3f}"}], "#habits",
        ))

    # Strongest personal patterns (FDR-controlled), translated into levers
    for e in [e for e in c.get("effects", []) if e.significant and abs(e.effect_size) >= 0.5][:2]:
        worse = e.diff < 0 if e.higher_is_better else e.diff > 0
        if not worse:
            continue
        out.append(finding(
            f"effect_{e.id}", "warn", "Your patterns", f"{e.exposed} cost you {abs(e.diff):.0f} {e.unit or 'points'} of {_lc(e.outcome)}",
            f"Across your history, {_lc(e.outcome)} averages {e.exposed_mean:.0f} after {_lc(e.exposed)} vs {e.reference_mean:.0f} after {_lc(e.reference)} ({e.n_exposed} vs {e.n_reference} days)"
            + (f", still {abs(e.diff):.0f} after allowing for {' and '.join(e.adjusted_for)}." if e.adjusted_for else "."),
            EFFECT_ACTIONS.get(e.id.split("_")[0], f"Aim for more {_lc(e.reference)}."), [{"label": "Effect size", "value": f"{abs(e.effect_size):.1f} SD"}], "#effects",
        ))
    return out


READINESS_FACTORS = {
    "sleep": "Sleep", "sleep_history": "Sleep history", "hrv": "HRV", "rhr": "Resting HR", "load": "Training load", "battery": "Body Battery",
}


def recommend(r: dict | None, p: dict | None, yesterday_load: float, warnings: dict | None = None, hrv: dict | None = None) -> dict | None:
    if r is None:
        return None
    score = r["score"]
    acwr = p["acwr"] if p else None
    reasons = []
    for key, label in READINESS_FACTORS.items():
        comp = r["components"].get(key)
        if comp:
            tone = "strong" if comp["score"] >= 85 else "low" if comp["score"] < 60 else "normal"
            reasons.append({"factor": label, "tone": tone, "score": comp["score"]})
    if warnings:
        return {"headline": "Recover" if warnings["level"] == "alert" else "Easy day",
                "detail": "Several body signals are off together, a common early sign of illness or overreaching. Rest or move gently today.",
                "reasons": reasons}
    if acwr and acwr > 1.5:
        return {"headline": "Easy day", "detail": "Recovery looks okay, but your load just spiked. Keep it aerobic and short.", "reasons": reasons}
    if hrv and hrv.get("status") == "below" and score >= 50:
        return {"headline": "Keep it easy", "detail": "Today looks fine, but your 7-day HRV is below its normal range. HRV-guided training keeps it easy until it recovers.",
                "reasons": reasons}
    if score >= 85:
        return {"headline": "Go hard", "detail": "Recovery signals are strong. A good day for intervals, a tempo or heavy lifting.", "reasons": reasons}
    if score >= 70:
        return {"headline": "Train as planned", "detail": "Normal readiness. Execute today's plan; keep hard efforts controlled.", "reasons": reasons}
    if score >= 50:
        detail = "Some signals are below your normal. Swap intensity for easy Z2, technique or mobility."
        if yesterday_load > 0:
            detail += " Yesterday's session may still be settling."
        return {"headline": "Keep it easy", "detail": detail, "reasons": reasons}
    return {"headline": "Recover", "detail": "Recovery markers are well below your normal. Rest, walk, sleep early.", "reasons": reasons}
