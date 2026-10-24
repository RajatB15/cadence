import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowLeft, CloudDownload, Gauge, HeartPulse, Map as MapIcon, Route as RouteIcon, Rows3 } from "lucide-react";
import { motion } from "motion/react";
import { Suspense, lazy, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Chart, chartBase, type ChartOption } from "../components/Chart";
import { NoteGrid, VerdictChip, readyColor } from "../components/CoachNotes";
import { WhatIfCard } from "../components/WhatIfCard";
import { MoreMenu } from "../components/MoreMenu";
import { ShareCardButton } from "../components/ShareCard";
import { ClassContent } from "../components/StrengthClass";
import { JsonTree, RecordTable, humanize } from "../components/DataViews";
import { ErrorBlock, LoadingBlock, Segmented } from "../components/Shell";
import { READ_ONLY, api } from "../lib/api";
import { formatDate, formatDuration, formatPace } from "../lib/format";
import { clockTime, signed } from "../lib/goals";
import { activityStyle } from "../lib/metrics";
import { buildCardModel } from "../lib/shareCard";
import type { ActivityDetail, ActivityRoute, FitData, Json, SessionCoach as SessionCoachData } from "../lib/types";

const ZONE_COLORS = ["#5c5a55", "#6cc7ff", "#5be3b0", "#c8f560", "#ffbe55", "#ff6a55", "#ff3b6b"];
const STREAM_STYLE: Record<string, { label: string; color: string; unit: string; area?: boolean }> = {
  heart_rate: { label: "Heart rate", color: "#ff6a55", unit: "bpm" },
  pace: { label: "Pace", color: "#c8f560", unit: "min/km" },
  speed: { label: "Speed", color: "#c8f560", unit: "km/h" },
  altitude: { label: "Elevation", color: "#d9b26a", unit: "m", area: true },
  cadence: { label: "Cadence", color: "#6cc7ff", unit: "spm" },
  power: { label: "Power", color: "#9b8cff", unit: "W" },
  respiration_rate: { label: "Respiration", color: "#5be3b0", unit: "brpm" },
  temperature: { label: "Temperature", color: "#ffbe55", unit: "°C" },
};
const STREAM_ORDER = ["heart_rate", "pace", "speed", "altitude", "cadence", "power", "respiration_rate", "temperature"];
const RouteMap = lazy(() => import("../components/RouteMap"));

export function ActivityPage() {
  const id = Number(useParams().id);
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["activity", id], queryFn: () => api.activity(id), enabled: Number.isFinite(id) });
  const fetchNow = useMutation({
    mutationFn: () => api.fetchActivity(id),
    onSettled: () => client.invalidateQueries({ queryKey: ["activity", id] }),
  });
  const tried = useRef(false);
  const missing = query.data?.missing ?? [];
  useEffect(() => {
    // Assets not yet archived by the background sync are fetched once, on first open.
    if (!READ_ONLY && missing.length && query.data?.activity.source_id === "garmin" && !tried.current) {
      tried.current = true;
      fetchNow.mutate();
    }
  }, [missing.length, query.data, fetchNow]);

  if (query.isPending) return <LoadingBlock height={640} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const d = query.data;

  return (
    <div className="space-y-10">
      <Link to="/activities" className="eyebrow inline-flex items-center gap-2 hover:text-paper">
        <ArrowLeft size={12} /> All activities
      </Link>
      <Header d={d} />
      {d.activity.event && (
        <p className="text-sm text-mute">
          Part of <Link to={`/events/${d.activity.event.id}`} className="font-semibold text-gold hover:underline">{d.activity.event.name}</Link>
          {" "}— unlink it from the event page.
        </p>
      )}
      {missing.length > 0 && !READ_ONLY && (
        <div className="surface flex flex-wrap items-center gap-4 border-gold/40 px-6 py-4">
          <CloudDownload size={18} className={clsx("text-gold", fetchNow.isPending && "animate-pulse")} />
          <p className="flex-1 text-sm text-mute">
            {fetchNow.isPending
              ? "Downloading the full recording from Garmin (once — it's kept in the vault)…"
              : fetchNow.isError
                ? `Couldn't download: ${fetchNow.error.message}`
                : `Not archived yet: ${missing.map((m) => humanize(m.replace("activity_", ""))).join(", ")}.`}
          </p>
          {!fetchNow.isPending && (
            <button type="button" className="pop pop-lime" onClick={() => fetchNow.mutate()}>
              Fetch now
            </button>
          )}
        </div>
      )}
      <HeadlineStats d={d} />
      {d.coach && (d.coach.notes.length > 0 || d.coach.verdict) && <SessionCoach coach={d.coach} />}
      <WhatIfCard card={d.coach?.what_if} />
      {d.route && <RouteSection r={d.route} />}
      {d.planned && <PlannedVsActual d={d} />}
      <ClassContent d={d} />
      {d.fit?.error && <p className="text-sm text-coral">FIT file couldn't be decoded: {d.fit.error}</p>}
      <Zones d={d} />
      {d.fit && Object.keys(d.fit.streams).length > 1 && <Streams fit={d.fit} family={d.activity.family} />}
      {d.fit && d.fit.route.length > 1 && <Route fit={d.fit} family={d.activity.family} />}
      <Splits d={d} />
      <Strength d={d} />
    </div>
  );
}

function RouteSection({ r }: { r: ActivityRoute }) {
  const t = r.this;
  const v = t?.vs_prior;
  const sentences: string[] = [];
  if (t) {
    if (t.is_best) sentences.push(`Your fastest time on this route, out of ${t.of} efforts.`);
    else sentences.push(`${ordinal(t.rank)} fastest of ${t.of} efforts here (best ${clockTime(r.best.time_s)} on ${formatDate(r.best.day)}).`);
    if (v?.ef_pct != null && Math.abs(v.ef_pct) >= 2) {
      sentences.push(`Per heartbeat above resting, you ran ${Math.abs(v.ef_pct).toFixed(1)}% ${v.ef_pct > 0 ? "better" : "worse"} than your earlier efforts here, so ${v.ef_pct > 0 ? "fitness is showing" : "it was a harder day for the same speed"}.`);
    }
    if (v?.temperature != null && Math.abs(v.temperature) >= 5) {
      sentences.push(`It was ${Math.abs(v.temperature).toFixed(0)}°C ${v.temperature > 0 ? "warmer" : "cooler"} than usual, which is shown for context and not adjusted for.`);
    }
  }
  const trend = r.trend?.significant ? r.trend : null;
  return (
    <Section icon={<RouteIcon size={22} />} title="On this route" aside={<Link to="/lab?tab=routes" className="text-xs font-semibold tracking-widest text-mute uppercase hover:text-paper">All routes →</Link>}>
      <p className="mb-5 text-sm text-mute">{r.name} · {r.distance_km} km · covered {r.n} times</p>
      {t && (
        <div className="mb-5 grid grid-cols-2 gap-6 sm:grid-cols-4">
          <Fact label="This time" value={clockTime(t.time_s)} hint={t.is_best ? "fastest" : `${ordinal(t.rank)} of ${t.of}`} color={t.is_best ? "#c8f560" : undefined} />
          <Fact label="Against usual" value={v?.time_s != null ? `${v.time_s <= 0 ? "−" : "+"}${clockTime(Math.abs(v.time_s))}` : "—"} hint={t.earlier_efforts ? `vs median of ${t.earlier_efforts} earlier` : "first effort"} color={v?.time_s != null ? (v.time_s <= 0 ? "#c8f560" : "#ffbe55") : undefined} />
          <Fact label="Heart rate" value={t.avg_hr ?? "—"} hint={v?.avg_hr != null ? `${signed(v.avg_hr)} bpm vs usual` : undefined} color="#ff6a55" />
          <Fact label="Value per beat" value={v?.ef_pct != null ? `${signed(v.ef_pct)}%` : "—"} hint="speed per heartbeat above rest" color="#6cc7ff" />
        </div>
      )}
      <ul className="space-y-1.5 text-sm text-paper">{sentences.map((x) => <li key={x}>{x}</li>)}</ul>
      {trend && (
        <p className="mt-3 text-sm text-mute">
          Across {trend.n} efforts over {trend.span_days} days your value per heartbeat here has moved {signed(trend.change_pct)}% (range {signed(trend.ci_pct[0])} to {signed(trend.ci_pct[1])}%).
        </p>
      )}
    </Section>
  );
}

function Fact({ label, value, hint, color }: { label: string; value: ReactNode; hint?: ReactNode; color?: string }) {
  return (
    <div>
      <p className="eyebrow mb-1">{label}</p>
      <p className="num text-2xl" style={{ color: color ?? "#f2e8cf" }}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-dim">{hint}</p>}
    </div>
  );
}

const ordinal = (n: number) => `${n}${["th", "st", "nd", "rd"][n % 100 > 10 && n % 100 < 14 ? 0 : Math.min(n % 10, 4) % 4] ?? "th"}`;

function PlannedVsActual({ d }: { d: ActivityDetail }) {
  const p = d.planned!;
  const actual = d.activity.training_load;
  const diff = actual != null && p.predicted.load ? (actual - p.predicted.load) / p.predicted.load : null;
  const verdict = diff == null ? null : diff > 0.25 ? "Harder than planned" : diff < -0.25 ? "Easier than planned" : "As planned";
  return (
    <section className="surface flex flex-wrap items-center gap-x-8 gap-y-3 p-5 sm:p-6" style={{ borderLeft: "3px solid #d9b26a" }}>
      <div className="min-w-0 flex-1">
        <p className="eyebrow mb-1">Planned</p>
        <p className="text-paper">{p.title}</p>
      </div>
      <div>
        <p className="eyebrow mb-1">Load</p>
        <p className="num text-xl text-cream">{actual != null ? Math.round(actual) : "—"} <span className="text-sm text-dim">vs {p.predicted.load} predicted</span></p>
      </div>
      {verdict && <span className={clsx("chip", verdict === "As planned" ? "text-lime" : "text-amber")}>{verdict}</span>}
    </section>
  );
}

function Header({ d }: { d: ActivityDetail }) {
  const a = d.activity;
  const navigate = useNavigate();
  const style = activityStyle(a.type, a.family);
  const Icon = style.icon;
  const local = (d.garmin_summary?.startTimeLocal as string | undefined) ?? a.start_time_utc;
  const when = new Date(local.replace(" ", "T"));
  const card = useMemo(() => buildCardModel(d, style.color, style.label), [d, style.color, style.label]);
  return (
    <header className="relative">
      <div
        className="pointer-events-none absolute -top-10 -left-10 h-56 w-56 rounded-full opacity-20 blur-3xl"
        style={{ background: style.color }}
      />
      <div className="eyebrow mb-4 flex flex-wrap items-center gap-3">
        <span className="chip" style={{ borderColor: `${style.color}66`, color: style.color }}>
          <Icon size={12} /> {style.label}
        </span>
        <span>
          {when.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })} ·{" "}
          {when.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
        </span>
        <span className="text-dim">{a.timezone}</span>
        <span className="ml-auto">
          <span className="flex items-center gap-2">
            <ShareCardButton model={card} />
            {!READ_ONLY && !a.event && (
              <MoreMenu
                items={[{ label: "Group with other activities", hint: "Multi-day trek or multisport event", onSelect: () => navigate(`/activities?group=${a.id}`) }]}
              />
            )}
          </span>
        </span>
      </div>
      <h1 className="font-display text-5xl leading-[0.95] text-cream sm:text-7xl">{a.name}</h1>
      {typeof d.garmin_summary?.description === "string" && d.garmin_summary.description && (
        <p className="mt-4 max-w-2xl text-mute">{d.garmin_summary.description as string}</p>
      )}
    </header>
  );
}

function num(obj: Json | null | undefined, key: string): number | null {
  const v = obj?.[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function HeadlineStats({ d }: { d: ActivityDetail }) {
  const a = d.activity;
  const s = d.garmin_summary;
  const moving = num(s, "movingDuration") ?? a.moving_duration_s ?? null;
  const stats: { label: string; value: string; unit?: string; accent?: string }[] = [];
  const push = (label: string, value: string | null, unit?: string, accent?: string) => {
    if (value !== null) stats.push({ label, value, unit, accent });
  };
  push("Distance", a.distance_m ? (a.distance_m / 1000).toFixed(2) : null, "km");
  push("Time", formatDuration(a.duration_s));
  push("Moving", moving ? formatDuration(moving) : null);
  if (a.family === "run" || a.family === "walk") push("Avg pace", formatPace(moving ?? a.duration_s, a.distance_m), "/km");
  else if (a.avg_speed_mps) push("Avg speed", (a.avg_speed_mps * 3.6).toFixed(1), "km/h");
  push("Avg HR", a.avg_hr ? String(Math.round(a.avg_hr)) : null, "bpm", "#ff6a55");
  push("Max HR", a.max_hr ? String(Math.round(a.max_hr)) : null, "bpm", "#ff6a55");
  push("Calories", a.calories ? String(Math.round(a.calories)) : null, "kcal");
  push("Elevation", a.elevation_gain_m ? String(Math.round(a.elevation_gain_m)) : null, "m");
  push("Training load", a.training_load ? String(Math.round(a.training_load)) : null, undefined, "#d9b26a");
  push("Aerobic TE", num(s, "aerobicTrainingEffect")?.toFixed(1) ?? null);
  push("Anaerobic TE", num(s, "anaerobicTrainingEffect")?.toFixed(1) ?? null);
  push("Avg cadence", num(s, "averageRunningCadenceInStepsPerMinute")?.toFixed(0) ?? null, "spm");
  push("Avg power", num(s, "avgPower")?.toFixed(0) ?? null, "W");
  push("VO₂ max", a.vo2max ? a.vo2max.toFixed(0) : null);
  push("Total sets", num(s, "totalSets")?.toFixed(0) ?? null);
  push("Total reps", num(s, "totalReps")?.toFixed(0) ?? null);
  push("Steps", num(s, "steps")?.toLocaleString() ?? null);
  push("Body Battery", num(s, "differenceBodyBattery")?.toFixed(0) ?? null);
  return (
    <section className="grid grid-cols-2 border-y border-line sm:grid-cols-3 lg:grid-cols-6">
      {stats.map((x, i) => (
        <motion.div
          key={x.label}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.03 }}
          className="border-b border-line/60 px-1 py-5 sm:px-4"
        >
          <p className="eyebrow mb-2">{x.label}</p>
          <p className="num text-3xl" style={{ color: x.accent ?? "#ecebe6" }}>
            {x.value}
            {x.unit && <span className="ml-1 text-sm text-mute">{x.unit}</span>}
          </p>
        </motion.div>
      ))}
    </section>
  );
}

function SessionCoach({ coach }: { coach: SessionCoachData }) {
  const i = coach.intensity;
  return (
    <Section
      icon={<Gauge size={22} />}
      title="Coach's take"
      aside={
        <div className="flex flex-wrap items-center gap-2">
          {coach.verdict && <VerdictChip v={coach.verdict} large />}
          {coach.readiness && (
            <span className="chip" style={{ color: readyColor(coach.readiness.score), borderColor: `${readyColor(coach.readiness.score)}55` }}>
              Readiness that morning {coach.readiness.score}
            </span>
          )}
        </div>
      }
    >
      {i && (
        <div className="mb-6">
          <div className="flex h-3 overflow-hidden">
            {[
              { pct: i.easy_pct, color: "#5be3b0" },
              { pct: i.moderate_pct, color: "#c8f560" },
              { pct: i.hard_pct, color: "#ff6a55" },
            ].map((s, k) => (
              <motion.div
                key={k}
                initial={{ width: 0 }}
                animate={{ width: `${s.pct}%` }}
                transition={{ duration: 0.9 }}
                style={{ background: s.color }}
              />
            ))}
          </div>
          <div className="mt-2 flex justify-between text-xs text-mute">
            <span>Easy Z1–2 <span className="num text-paper">{i.easy_pct}%</span></span>
            <span>Grey Z3 <span className="num text-paper">{i.moderate_pct}%</span></span>
            <span>Hard Z4–5 <span className="num text-paper">{i.hard_pct}%</span></span>
          </div>
        </div>
      )}
      {coach.notes.length > 0 ? (
        <NoteGrid notes={coach.notes} compact />
      ) : (
        <p className="text-mute">Not enough comparable history to judge this session yet.</p>
      )}
    </Section>
  );
}

function Section({ icon, title, aside, children }: { icon: ReactNode; title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="surface p-6 sm:p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-3 font-display text-3xl text-cream">
          <span className="text-gold">{icon}</span>
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function zoneName(zone: number): string {
  return zone === 0 ? "Below Z1" : zone > 5 ? "Above Z5" : `Zone ${zone}`;
}

function Zones({ d }: { d: ActivityDetail }) {
  let zones = d.fit?.zones?.filter((z) => z.seconds > 0 || (z.zone >= 1 && z.zone <= 5)) ?? null;
  if (!zones?.length && d.garmin_summary) {
    zones = [1, 2, 3, 4, 5]
      .map((z) => ({ zone: z, low: null, high: null, seconds: num(d.garmin_summary, `hrTimeInZone_${z}`) ?? 0 }))
      .filter((z) => z.seconds > 0);
  }
  if (!zones?.length) return null;
  const total = zones.reduce((s, z) => s + z.seconds, 0) || 1;
  const longest = Math.max(...zones.map((z) => z.seconds), 1);
  const hr = d.fit?.streams.heart_rate;
  const t = d.fit?.streams.t;
  return (
    <Section icon={<HeartPulse size={22} />} title="Heart-rate zones" aside={<p className="eyebrow">{formatDuration(total)} with HR</p>}>
      <div className="space-y-2.5">
        {[...zones].reverse().map((z) => (
          <div key={z.zone} className="grid grid-cols-[4.75rem_1fr] items-center gap-3 sm:grid-cols-[9rem_1fr_7rem]">
            <div>
              <p className="text-sm text-paper">{zoneName(z.zone)}</p>
              <p className="text-xs text-dim">
                {z.low != null && z.high != null ? `${z.low}–${z.high} bpm` : z.low == null && z.high != null ? `< ${z.high} bpm` : "\u00a0"}
              </p>
            </div>
            <div className="h-6 bg-slate">
              <motion.div
                className="h-full"
                initial={{ width: 0 }}
                animate={{ width: `${(z.seconds / longest) * 100}%` }}
                transition={{ duration: 0.9, ease: [0.2, 0.9, 0.1, 1] }}
                style={{ background: ZONE_COLORS[z.zone] ?? "#f2e8cf", minWidth: z.seconds > 0 ? 3 : 0 }}
              />
            </div>
            <p className="num col-span-2 -mt-1 text-right text-sm text-paper sm:col-span-1 sm:mt-0">
              {z.seconds > 0 ? formatDuration(z.seconds) : "—"} <span className="text-dim">{Math.round((z.seconds / total) * 100)}%</span>
            </p>
          </div>
        ))}
      </div>
      {hr && t && <ZoneTimeline hr={hr} t={t} zones={zones} />}
    </Section>
  );
}

/** Heart rate through the session, coloured by the zone it was in, so you see when the hard parts happened. */
function ZoneTimeline({ hr, t, zones }: { hr: (number | null)[]; t: (number | null)[]; zones: { zone: number; low: number | null }[] }) {
  const lows = useMemo(() => zones.filter((z) => z.low != null).sort((a, b) => a.low! - b.low!), [zones]);
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      grid: { left: 8, right: 16, top: 12, bottom: 8, containLabel: true },
      xAxis: {
        type: "value",
        min: "dataMin",
        max: "dataMax",
        axisLine: { lineStyle: { color: "#262629" } },
        axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => formatDuration(v) },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLabel: { color: "#5c5a55", fontSize: 10 },
        splitLine: { show: false },
      },
      visualMap: {
        show: false,
        dimension: 1,
        pieces: [
          { lt: lows[0].low!, color: ZONE_COLORS[0] },
          ...lows.map((z, i) => ({ gte: z.low!, ...(lows[i + 1] ? { lt: lows[i + 1].low! } : {}), color: ZONE_COLORS[z.zone] ?? "#f2e8cf" })),
        ],
      },
      tooltip: {
        ...chartBase.tooltip,
        formatter: (items: { value: [number, number] }[]) => {
          const p = items[0]?.value;
          return p && p[1] != null ? `<span style="color:#8d8a82">${formatDuration(p[0])}</span><br/><b>${Math.round(p[1])} bpm</b>` : "";
        },
      },
      series: [
        {
          type: "line",
          data: t.map((x, i) => [x, hr[i]]),
          symbol: "none",
          connectNulls: false,
          lineStyle: { width: 2 },
          markLine: {
            symbol: "none",
            silent: true,
            label: { show: true, position: "insideEndTop", color: "#5c5a55", fontSize: 10, formatter: (p: { name: string }) => p.name },
            lineStyle: { color: "#3a3a3f", type: "dashed" },
            data: lows.slice(1).map((z) => ({ yAxis: z.low!, name: `Z${z.zone}` })),
          },
        },
      ],
    }),
    [hr, t, lows],
  );
  if (!lows.length || !hr.some((v) => v != null)) return null;
  return (
    <div className="mt-6 border-t border-line/60 pt-4">
      <p className="eyebrow mb-2">Heart rate by zone through the session</p>
      <Chart option={option} height={170} label="Heart rate coloured by zone over the activity" />
    </div>
  );
}

function Streams({ fit, family }: { fit: FitData; family: string }) {
  const [axis, setAxis] = useState<"time" | "distance">("time");
  const hasDistance = (fit.stream_stats.distance?.max ?? 0) > 100;
  const series = useMemo(() => {
    const out: { key: string; values: (number | null)[] }[] = [];
    const speed = fit.streams.speed;
    const paced = (family === "run" || family === "walk") && speed;
    const keys = Object.keys(fit.streams).filter((k) => k !== "t");
    const ordered = [...STREAM_ORDER.filter((k) => keys.includes(k) || (k === "pace" && paced)), ...keys.filter((k) => !STREAM_ORDER.includes(k)).sort()];
    for (const key of ordered) {
      if (key === "pace") {
        out.push({ key, values: speed.map((v) => (v && v > 0.8 ? 1000 / 60 / v : null)) });
      } else if (key === "speed") {
        if (!paced) out.push({ key, values: speed.map((v) => (v == null ? null : v * 3.6)) });
      } else {
        out.push({ key, values: fit.streams[key] });
      }
    }
    return out;
  }, [fit, family]);
  const x = axis === "distance" && hasDistance ? fit.streams.distance.map((v) => (v == null ? null : v / 1000)) : fit.streams.t;

  return (
    <Section
      icon={<Rows3 size={22} />}
      title="Every second, charted"
      aside={
        hasDistance ? (
          <Segmented
            label="X axis"
            options={[
              { value: "time", label: "Time" },
              { value: "distance", label: "Distance" },
            ]}
            value={axis}
            onChange={setAxis}
          />
        ) : null
      }
    >
      <p className="mb-6 text-sm text-mute">
        {series.length} recorded channels · {fit.streamed_counts.record_mesgs?.toLocaleString() ?? 0} samples. Hover any
        chart: they move together.
      </p>
      <div className="space-y-2">
        {series.map((s) => (
          <StreamChart key={`${s.key}-${axis}`} name={s.key} values={s.values} x={x} axis={axis} stats={fit.stream_stats[s.key === "pace" ? "speed" : s.key]} />
        ))}
      </div>
    </Section>
  );
}

function StreamChart({
  name,
  values,
  x,
  axis,
  stats,
}: {
  name: string;
  values: (number | null)[];
  x: (number | null)[];
  axis: string;
  stats?: { min: number; avg: number; max: number };
}) {
  const style = STREAM_STYLE[name] ?? { label: humanize(name), color: "#f2e8cf", unit: "" };
  const pace = name === "pace";
  const fmt = (v: number) =>
    pace ? `${Math.floor(v)}:${String(Math.round((v % 1) * 60)).padStart(2, "0")}` : Math.abs(v) >= 100 ? v.toFixed(0) : String(+v.toFixed(2));
  const present = values.filter((v): v is number => v != null);
  const avg = present.length ? present.reduce((a, b) => a + b, 0) / present.length : null;
  const range = useMemo(() => {
    if (!pace || present.length < 20) return {};
    // Stops produce extreme paces; keep the axis on how you actually moved.
    const sorted = [...present].sort((a, b) => a - b);
    return { min: sorted[Math.floor(sorted.length * 0.02)], max: sorted[Math.floor(sorted.length * 0.98)] * 1.04 };
  }, [pace, present]);
  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      grid: { left: 8, right: 16, top: 12, bottom: 8, containLabel: true },
      xAxis: {
        type: "value",
        min: "dataMin",
        max: "dataMax",
        axisLine: { lineStyle: { color: "#262629" } },
        axisLabel: {
          color: "#5c5a55",
          fontSize: 10,
          formatter: (v: number) => (axis === "distance" ? `${v.toFixed(1)} km` : formatDuration(v)),
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        inverse: pace,
        ...range,
        axisLabel: { color: "#5c5a55", fontSize: 10, formatter: (v: number) => fmt(v) },
        splitLine: { lineStyle: { color: "#1c1c1f" } },
      },
      tooltip: {
        ...chartBase.tooltip,
        formatter: (items: { value: [number, number] }[]) => {
          const p = items[0]?.value;
          if (!p || p[1] == null) return "";
          const where = axis === "distance" ? `${p[0].toFixed(2)} km` : formatDuration(p[0]);
          return `<span style="color:#8d8a82">${where}</span><br/><b style="color:${style.color}">${fmt(p[1])} ${style.unit}</b> ${style.label}`;
        },
      },
      series: [
        {
          type: "line",
          data: x.map((t, i) => [t, values[i]]),
          symbol: "none",
          connectNulls: false,
          lineStyle: { color: style.color, width: 1.5 },
          areaStyle: style.area
            ? { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `${style.color}55` }, { offset: 1, color: `${style.color}00` }] } }
            : undefined,
          markLine: avg != null ? { symbol: "none", silent: true, label: { show: false }, lineStyle: { color: `${style.color}88`, type: "dashed" }, data: [{ yAxis: avg }] } : undefined,
        },
      ],
    }),
    [values, x, axis, style.color, style.area, style.label, style.unit, pace, avg, range],
  );
  if (!present.length) return null;
  return (
    <div className="grid items-center gap-4 border-t border-line/60 pt-3 lg:grid-cols-[12rem_1fr]">
      <div>
        <p className="font-semibold" style={{ color: style.color }}>{style.label}</p>
        <p className="text-xs text-dim">{style.unit}</p>
        {avg != null && (
          <p className="num mt-2 text-sm text-mute">
            avg <span className="text-paper">{fmt(avg)}</span>
            {stats && !pace && (
              <>
                {" "}· {fmt(stats.min)}–{fmt(stats.max)}
              </>
            )}
          </p>
        )}
      </div>
      <Chart option={option} height={130} label={`${style.label} over the activity`} group="activity-streams" />
    </div>
  );
}

function Route({ fit, family }: { fit: FitData; family: string }) {
  return (
    <Section icon={<MapIcon size={22} />} title="Route" aside={<p className="eyebrow">{fit.route.length.toLocaleString()} GPS points</p>}>
      <Suspense fallback={<div className="h-[440px] animate-pulse border border-line bg-slate sm:h-[560px]" />}>
        <RouteMap fit={fit} family={family} fallback={<RouteShape route={fit.route} />} />
      </Suspense>
    </Section>
  );
}

/** Offline fallback: the route's shape alone, drawn locally without map tiles. */
function RouteShape({ route }: { route: [number, number][] }) {
  const { path, start, end, view } = useMemo(() => {
    const lats = route.map((p) => p[0]);
    const midLat = ((Math.min(...lats) + Math.max(...lats)) / 2) * (Math.PI / 180);
    const k = Math.cos(midLat);
    const pts = route.map(([lat, lon]) => [lon * k, -lat]);
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    const minX = Math.min(...xs), minY = Math.min(...ys);
    const w = Math.max(...xs) - minX || 1e-6, h = Math.max(...ys) - minY || 1e-6;
    const scale = 1000 / Math.max(w, h);
    const proj = pts.map(([px, py]) => [(px - minX) * scale, (py - minY) * scale]);
    return {
      path: proj.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" "),
      start: proj[0],
      end: proj[proj.length - 1],
      view: `-40 -40 ${w * scale + 80} ${h * scale + 80}`,
    };
  }, [route]);
  return (
    <div className="flex justify-center bg-ink/60 p-4">
        <svg viewBox={view} className="max-h-[460px] w-full" role="img" aria-label="Route shape">
          <defs>
            <filter id="route-glow">
              <feGaussianBlur stdDeviation="6" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <motion.path
            d={path}
            fill="none"
            stroke="#c8f560"
            strokeWidth={5}
            strokeLinejoin="round"
            strokeLinecap="round"
            filter="url(#route-glow)"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.8, ease: "easeInOut" }}
          />
          <circle cx={start[0]} cy={start[1]} r={14} fill="#0b0b0c" stroke="#c8f560" strokeWidth={5} />
          <circle cx={end[0]} cy={end[1]} r={14} fill="#ff6a55" />
        </svg>
    </div>
  );
}

function Splits({ d }: { d: ActivityDetail }) {
  const paced = d.activity.family === "run" || d.activity.family === "walk";
  const withPace = (rows: Json[], speedKeys: string[]) =>
    paced
      ? rows.map((r) => {
          const speed = speedKeys.map((k) => r[k]).find((v): v is number => typeof v === "number" && v > 0);
          return speed ? { pace: formatPace(1000 / speed, 1000), ...r } : r;
        })
      : rows;
  const laps = withPace(d.fit?.messages.lap_mesgs ?? [], ["enhanced_avg_speed", "avg_speed"]);
  const splits = withPace(d.fit?.messages.split_mesgs ?? [], ["avg_speed", "enhanced_avg_speed"]);
  const garminSplits = withPace((d.detail?.splitSummaries as Json[] | undefined) ?? [], ["averageSpeed"]);
  if (!laps.length && !splits.length && !garminSplits.length) return null;
  const tabs = [
    laps.length && { value: "laps", label: `Laps ${laps.length}` },
    splits.length && { value: "splits", label: `Splits ${splits.length}` },
    garminSplits.length && { value: "garmin", label: `Garmin splits ${garminSplits.length}` },
  ].filter(Boolean) as { value: string; label: string }[];
  return <SplitTabs tabs={tabs} rows={{ laps, splits, garmin: garminSplits }} />;
}

function SplitTabs({ tabs, rows }: { tabs: { value: string; label: string }[]; rows: Record<string, Json[]> }) {
  const [tab, setTab] = useState(tabs[0].value);
  return (
    <Section icon={<Rows3 size={22} />} title="Laps & splits" aside={<Segmented label="Split type" options={tabs} value={tab} onChange={setTab} />}>
      <RecordTable rows={rows[tab]} limit={60} priority={SPLIT_PRIORITY} />
    </Section>
  );
}

const SPLIT_PRIORITY = [
  "split_type", "splitType", "total_distance", "distance", "total_timer_time", "duration", "movingDuration", "pace",
  "avg_heart_rate", "averageHR", "max_heart_rate", "maxHR", "avg_running_cadence", "averageRunCadence", "avg_power",
  "averagePower", "total_ascent", "elevationGain", "total_descent", "elevationLoss", "total_calories", "calories",
];

function Strength({ d }: { d: ActivityDetail }) {
  const fitSets = (d.fit?.messages.set_mesgs ?? []).filter((s) => s.set_type !== "rest");
  // Garmin reports a summarized set's duration in milliseconds; the table formats durations as seconds.
  const summarySets: Json[] = ((d.garmin_summary?.summarizedExerciseSets as Json[] | undefined) ?? []).map((s) => ({
    ...s,
    ...(typeof s.duration === "number" ? { duration: s.duration / 1000 } : {}),
    ...(s.category === "UNKNOWN" ? { category: "Not named on the watch" } : {}),
  }));
  const watchUnnamed = summarySets.length > 0 && summarySets.every((s) => !s.category || s.category === "Not named on the watch");
  const named = (d.strength?.label?.blocks.length ?? 0) > 0;
  const sum = (key: string) => summarySets.reduce((t, s) => t + (typeof s[key] === "number" ? (s[key] as number) : 0), 0);
  const workouts = Array.isArray(d.workouts) ? d.workouts : [];
  if (!fitSets.length && !summarySets.length && !workouts.length) return null;
  return (
    <Section icon={<Rows3 size={22} />} title="Sets & exercises">
      <div className="space-y-8">
        {summarySets.length > 0 && named && watchUnnamed ? (
          <div>
            <p className="eyebrow mb-3">Counted by the watch</p>
            <p className="num text-paper">
              {sum("sets")} sets · {sum("reps")} reps{sum("duration") > 0 && ` · ${formatDuration(sum("duration"))} working`}
            </p>
            <p className="mt-1 text-sm text-dim">The watch didn't record which exercises these were; the exercises you named are listed with the class above.</p>
          </div>
        ) : (
          summarySets.length > 0 && (
            <div>
              <p className="eyebrow mb-3">By exercise (Garmin)</p>
              <RecordTable rows={summarySets} />
            </div>
          )
        )}
        {fitSets.length > 0 && (
          <div>
            <p className="eyebrow mb-3">Every set (from the watch)</p>
            <RecordTable rows={fitSets} limit={60} />
          </div>
        )}
        {workouts.length > 0 && <JsonTree name="Planned workout" value={workouts} />}
      </div>
    </Section>
  );
}
