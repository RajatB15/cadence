import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowLeft, Check, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Chart, chartBase } from "../components/Chart";
import { MoreMenu } from "../components/MoreMenu";
import { PhaseEditor } from "../components/PhaseEditor";
import { ErrorBlock, LoadingBlock, PageHeader } from "../components/Shell";
import { api } from "../lib/api";
import { formatDuration, formatKm, formatShortDate, parseDay } from "../lib/format";
import { ACTIVITY_FAMILIES } from "../lib/metrics";
import { MEASURES, STATUS, clock, dayLine, goalValue, describePillar, isoDay, onTrackLine, passesLine, pillarHeadline, totalPaceLine } from "../lib/phases";
import type { HabitOption, PhaseCell, PhaseDetail, PhaseFamilyTotals, PhaseSummary, PillarResult } from "../lib/types";

const CELL: Record<PhaseCell["status"], string> = {
  hit: "bg-[var(--phase)]",
  miss: "bg-coral/55",
  pending: "border border-[var(--phase)] animate-pulse",
  unknown: "border border-dashed border-dim",
  future: "bg-line/60",
};

function Pct({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 w-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)}>
      <div className="h-full transition-[width] duration-700" style={{ width: `${Math.min(100, value * 100)}%`, background: color }} />
    </div>
  );
}

// ---- list ----------------------------------------------------------------------------------

function PhaseCard({ p, habits }: { p: PhaseSummary; habits: HabitOption[] }) {
  return (
    <li>
      <Link to={`/phases/${p.id}`} className="surface surface-hover block space-y-4 p-5 sm:p-6" style={{ borderLeft: `3px solid ${p.color}` }}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">{formatShortDate(p.start)} – {formatShortDate(p.end)} · {dayLine(p)}</p>
            <h2 className="mt-2 font-display text-3xl text-cream"><span aria-hidden>{p.emoji} </span>{p.name}</h2>
            {p.tagline && <p className="mt-1 text-sm text-mute">{p.tagline}</p>}
          </div>
          <span className="chip shrink-0" style={{ color: p.color, borderColor: `${p.color}66` }}>{p.state === "done" ? "Finished" : p.state === "active" ? "Active" : "Upcoming"}</span>
        </div>
        <Pct value={p.pct} color={p.color} />
        <p className="text-sm text-mute">
          {onTrackLine(p)} · {p.totals.sessions} session{p.totals.sessions === 1 ? "" : "s"}
          {p.pillars.length > 0 && <span className="text-dim"> · {p.pillars.map((x) => describePillar(x, habits)).join(" · ")}</span>}
        </p>
      </Link>
    </li>
  );
}

export function PhasesPage() {
  const query = useQuery({ queryKey: ["phases"], queryFn: api.phases });
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const items = query.data?.items ?? [];
  const groups = [
    { title: "Now", rows: items.filter((p) => p.state === "active") },
    { title: "Coming up", rows: items.filter((p) => p.state === "upcoming") },
    { title: "Finished", rows: items.filter((p) => p.state === "done") },
  ].filter((g) => g.rows.length);
  return (
    <>
      <PageHeader eyebrow={query.data ? `${items.length} on record` : "Phases"} title={<>Phases<em className="text-gold">.</em></>}>
        <button type="button" className="pop" onClick={() => setCreating(true)}><Plus size={16} /> New phase</button>
      </PageHeader>
      {query.isPending ? (
        <LoadingBlock height={240} />
      ) : query.isError ? (
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <div className="surface p-12 text-center text-mute">
          No phases yet. A phase is a stretch of the calendar with its own commitments: a Winter Arc, No Break November, a dry month, an eight-week block.
        </div>
      ) : (
        <div className="space-y-10">
          {groups.map((g) => (
            <section key={g.title}>
              <h2 className="eyebrow mb-4">{g.title}</h2>
              <ul className="space-y-4">{g.rows.map((p) => <PhaseCard key={p.id} p={p} habits={query.data.habits} />)}</ul>
            </section>
          ))}
        </div>
      )}
      {creating && <PhaseEditor open onOpenChange={setCreating} habits={query.data?.habits ?? []} onSaved={(p) => navigate(`/phases/${p.id}`)} />}
    </>
  );
}

// ---- detail --------------------------------------------------------------------------------

function DailyStrip({ cells, label }: { cells: PhaseCell[]; label: string }) {
  return (
    <div role="img" aria-label={label} className="flex flex-wrap gap-[3px]">
      {cells.map((c) => (
        <span key={c.day} title={`${formatShortDate(c.day)}: ${c.status === "unknown" ? "no data" : c.status === "future" ? "to come" : c.status === "pending" ? "today, not yet" : c.status}`} className={clsx("h-3 w-3", CELL[c.status])} />
      ))}
    </div>
  );
}

function WeekBars({ p }: { p: PillarResult }) {
  const weeks = p.weeks ?? [];
  const top = Math.max(p.target ?? 1, ...weeks.map((w) => w.value)) * 1.1;
  return (
    <div className="relative flex h-24 items-end gap-1.5" role="img" aria-label="Each week against the weekly target">
      <span aria-hidden className="absolute inset-x-0 border-t border-dashed border-gold/60" style={{ bottom: `${((p.target ?? 0) / top) * 100}%` }} />
      {weeks.map((w) => (
        <span
          key={w.start}
          title={`Week of ${formatShortDate(w.start)}: ${Math.round(w.value * 10) / 10}${w.partial ? " (partial week)" : ""}`}
          className={clsx("min-h-[3px] flex-1", w.hit === true ? "bg-[var(--phase)]" : w.hit === false ? "bg-coral/55" : w.future ? "bg-line/60" : "bg-[var(--phase)]/35")}
          style={{ height: `${Math.max(2, (w.value / top) * 100)}%` }}
        />
      ))}
    </div>
  );
}

function TotalChart({ p, phase }: { p: PillarResult; phase: PhaseDetail }) {
  const option = useMemo(
    () => ({
      ...chartBase,
      grid: { ...chartBase.grid, top: 12 },
      yAxis: { ...chartBase.yAxis, scale: false, min: 0 },
      xAxis: { ...chartBase.xAxis, min: phase.start, max: phase.end },
      series: [
        { name: "You", type: "line", showSymbol: false, smooth: false, data: p.series ?? [], lineStyle: { color: phase.color, width: 2.5 }, areaStyle: { color: phase.color, opacity: 0.12 } },
        { name: "Even pace", type: "line", showSymbol: false, silent: true, data: [[phase.start, 0], [phase.end, p.target]], lineStyle: { color: "#8d8a82", width: 1.5, type: "dashed" } },
      ],
    }),
    [p, phase],
  );
  return <Chart option={option} height={150} label={`${describePillar(p)}: running total against an even pace`} />;
}

const SESSION_GOALS = new Set(["run_pace", "run_best_pace", "ride_speed", "swim_pace", "longest_km"]);

function GoalBody({ p, phase }: { p: PillarResult; phase: PhaseDetail }) {
  const m = p.metric ?? "";
  if (p.no_data)
    return (
      <p className="text-sm text-mute">
        Not enough yet to measure this: {m.endsWith("_pace") || m === "ride_speed" ? "paces and speeds need at least 3 sessions in the phase" : "this needs a few readings in the last week"}.
        {p.base != null && ` You start from ${goalValue(m, p.base)}.`}
      </p>
    );
  return (
    <>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="num text-5xl text-cream">{goalValue(m, p.current)}</span>
        <span className="text-sm text-mute">goal {goalValue(m, p.target)}</span>
      </div>
      {p.progress != null ? (
        <div className="relative">
          <Pct value={p.progress} color={phase.color} />
          {phase.state === "active" && <span aria-hidden title="Share of the phase elapsed" className="absolute -top-1 h-3.5 w-0.5 bg-paper" style={{ left: `${Math.min(100, phase.pct * 100)}%` }} />}
        </div>
      ) : (
        <p className="text-xs text-dim">No earlier reading to measure progress from, so only the current figure and the goal are shown.</p>
      )}
      <p className="text-sm text-mute">
        {p.base != null ? `Started at ${goalValue(m, p.base)}` : "No starting point"} · {p.progress != null ? `${Math.round(p.progress * 100)}% of the way, ${Math.round(phase.pct * 100)}% of the time` : "tracking"} · {p.better === "lower" ? "lower is better" : "higher is better"}
      </p>
      <p className="text-xs text-dim">Based on {p.n} {m === "weight_kg" ? "weigh-in" : m === "vo2max" ? "reading" : SESSION_GOALS.has(m) ? "session" : "day"}{p.n === 1 ? "" : "s"} in the phase. Small gaps are within day-to-day noise.</p>
    </>
  );
}

function PillarCard({ p, phase, habits }: { p: PillarResult; phase: PhaseDetail; habits: HabitOption[] }) {
  const st = STATUS[p.status];
  const title = describePillar(p, habits);
  return (
    <li className="surface space-y-4 p-5" style={{ ["--phase" as string]: phase.color }}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-lg text-paper">{title}</h3>
        <span className="chip shrink-0" style={{ color: st.color, borderColor: `${st.color}66` }}>{st.label}</span>
      </div>
      {(p.kind === "daily" || p.kind === "habit") && p.cells && (
        <>
          <div className="flex items-baseline gap-3">
            <span className="num text-5xl text-cream">{p.streak ?? 0}</span>
            <span className="text-sm text-mute">day streak · best {p.best_streak ?? 0}</span>
          </div>
          <DailyStrip cells={p.cells} label={`${title}: ${p.hits} days met, ${p.misses} missed, ${p.unknown} unknown`} />
          <p className="text-sm text-mute">
            {p.hits} met · {p.misses} missed{(p.unknown ?? 0) > 0 && ` · ${p.unknown} with no data`} · {passesLine(p)}
          </p>
        </>
      )}
      {p.kind === "total" && (
        <>
          <div className="flex items-baseline gap-2">
            <span className="num text-5xl text-cream">{Math.round((p.value ?? 0) * 10) / 10}</span>
            <span className="text-sm text-mute">of {(p.target ?? 0).toLocaleString()} {MEASURES.total[p.metric ?? ""]?.unit}</span>
          </div>
          <div className="relative">
            <Pct value={p.pct ?? 0} color={phase.color} />
            {phase.state === "active" && <span aria-hidden title="Even pace" className="absolute -top-1 h-3.5 w-0.5 bg-paper" style={{ left: `${Math.min(100, (phase.pct) * 100)}%` }} />}
          </div>
          <p className="text-sm text-mute">{totalPaceLine(p)}</p>
          {(p.series?.length ?? 0) > 1 && <TotalChart p={p} phase={phase} />}
          {(p.missing ?? 0) > 0 && <p className="text-xs text-dim">{p.missing} session{p.missing === 1 ? "" : "s"} had no training load recorded, so are missing here rather than zero.</p>}
        </>
      )}
      {p.kind === "goal" && <GoalBody p={p} phase={phase} />}
      {p.kind === "weekly" && (
        <>
          <p className="num text-3xl text-cream">{pillarHeadline(p)}</p>
          <WeekBars p={p} />
          <p className="text-sm text-mute">Best week {Math.round((p.best ?? 0) * 10) / 10} · dashed line is your bar · partial weeks at the edges aren’t judged</p>
        </>
      )}
    </li>
  );
}

const MONTH = new Intl.DateTimeFormat(undefined, { month: "short" });

/** Weeks as columns, Monday at the top: the whole phase at a glance in a few lines. */
function Heatmap({ phase }: { phase: PhaseDetail }) {
  const byDay = new Map(phase.days.map((d) => [d.day, d]));
  const first = parseDay(phase.start);
  const lead = (first.getDay() + 6) % 7;
  const weeks = Math.ceil((lead + phase.total_days) / 7);
  const today = isoDay(new Date());
  const tone = (m: number) => (m <= 0 ? 0 : m < 20 ? 0.28 : m < 45 ? 0.5 : m < 90 ? 0.75 : 1);
  const shade = (t: number) => (t ? `color-mix(in srgb, var(--phase) ${t * 100}%, #1c1c1f)` : "#1c1c1f");
  const at = (w: number, r: number) => new Date(first.getFullYear(), first.getMonth(), first.getDate() + w * 7 + r - lead);
  const labels = Array.from({ length: weeks }, (_, w) => {
    const d = at(w, 0 < lead && w === 0 ? lead : 0);
    const prev = w ? at(w - 1, 0) : null;
    return !prev || prev.getMonth() !== d.getMonth() ? MONTH.format(d) : "";
  });
  return (
    <div className="space-y-3" style={{ ["--phase" as string]: phase.color }}>
      <div className="flex gap-2 overflow-x-auto pb-1">
        <div className="grid shrink-0 grid-rows-[16px_repeat(7,14px)] gap-[3px] pt-0 text-[10px] text-dim sm:grid-rows-[16px_repeat(7,16px)]" aria-hidden>
          <span />
          {["Mon", "", "Wed", "", "Fri", "", "Sun"].map((d, i) => <span key={i} className="leading-[14px] sm:leading-4">{d}</span>)}
        </div>
        <div role="img" aria-label="Every day of the phase, shaded by minutes of activity" className="grid grid-flow-col grid-rows-[16px_repeat(7,14px)] gap-[3px] sm:grid-rows-[16px_repeat(7,16px)]" style={{ gridTemplateColumns: `repeat(${weeks}, minmax(14px, 16px))` }}>
          {Array.from({ length: weeks }, (_, w) => [
            <span key={`m${w}`} className="overflow-visible text-[10px] leading-4 whitespace-nowrap text-dim">{labels[w]}</span>,
            ...Array.from({ length: 7 }, (_, r) => {
              const i = w * 7 + r - lead;
              if (i < 0 || i >= phase.total_days) return <span key={`${w}-${r}`} />;
              const key = isoDay(at(w, r));
              const m = byDay.get(key)?.minutes ?? 0;
              const n = byDay.get(key)?.sessions ?? 0;
              const future = key > today;
              return (
                <span
                  key={`${w}-${r}`}
                  title={future ? `${formatShortDate(key)}: to come` : `${formatShortDate(key)}: ${m ? `${m} min · ${n} session${n === 1 ? "" : "s"}` : "no activity"}`}
                  className={clsx("rounded-[2px]", future && "border border-line", key === today && "ring-1 ring-paper")}
                  style={future ? undefined : { background: shade(tone(m)) }}
                />
              );
            }),
          ])}
        </div>
      </div>
      <div className="flex items-center gap-2 text-[10px] text-dim">
        <span>Less</span>
        {[0, 0.28, 0.5, 0.75, 1].map((t) => <span key={t} className="h-3 w-3 rounded-[2px]" style={{ background: shade(t) }} />)}
        <span>More</span>
        <span className="ml-3">Minutes of activity a day</span>
      </div>
    </div>
  );
}

function WeekChart({ phase }: { phase: PhaseDetail }) {
  const perWeek = phase.before.available ? (phase.before.duration_s / 60) / (phase.before.days / 7) : null;
  const option = useMemo(
    () => ({
      ...chartBase,
      tooltip: { ...chartBase.tooltip, trigger: "axis", valueFormatter: (v: number) => `${v} min` },
      xAxis: { type: "category", data: phase.weeks.map((w) => formatShortDate(w.start)), axisLabel: { color: "#5c5a55", fontSize: 11, hideOverlap: true }, axisLine: { lineStyle: { color: "#262629" } }, axisTick: { show: false } },
      yAxis: { ...chartBase.yAxis, scale: false, min: 0, axisLabel: { color: "#5c5a55", fontSize: 11, formatter: (v: number) => `${v}m` } },
      series: [
        {
          name: "Minutes", type: "bar", data: phase.weeks.map((w) => w.minutes), itemStyle: { color: phase.color, borderRadius: 0 }, barMaxWidth: 28,
          markLine: perWeek != null ? { silent: true, symbol: "none", lineStyle: { color: "#8d8a82", type: "dashed" }, label: { color: "#8d8a82", formatter: "before" }, data: [{ yAxis: Math.round(perWeek) }] } : undefined,
        },
      ],
    }),
    [phase, perWeek],
  );
  return <Chart option={option} height={200} label="Minutes of activity per week in this phase" />;
}

const FIGURE = (label: string, value: string) => (
  <div key={label}>
    <dd className="num text-3xl text-paper">{value}</dd>
    <dt className="text-[10px] tracking-widest text-dim uppercase">{label}</dt>
  </div>
);

const SPORTS: { family: string; noun: string }[] = [
  { family: "run", noun: "runs" },
  { family: "ride", noun: "rides" },
  { family: "swim", noun: "swims" },
];

function sportFigures(family: string, v: PhaseFamilyTotals): string | null {
  if (v.sessions < 3 || !v.distance_m) return null;
  if (family === "run") return `${clock(v.duration_s / v.distance_m * 1000)} /km`;
  if (family === "ride") return `${(v.distance_m / v.duration_s * 3.6).toFixed(1)} km/h`;
  return `${clock(v.duration_s / v.distance_m * 100)} /100 m`;
}

function Sports({ phase }: { phase: PhaseDetail }) {
  const zero: PhaseFamilyTotals = { sessions: 0, duration_s: 0, distance_m: 0 };
  const before = phase.before.available ? phase.before.families : null;
  return (
    <ul className="grid gap-3 sm:grid-cols-3">
      {SPORTS.map(({ family, noun }) => {
        const v = phase.totals.families[family] ?? zero;
        const style = ACTIVITY_FAMILIES[family];
        const Icon = style.icon;
        const pace = sportFigures(family, v);
        const was = before ? (before[family]?.sessions ?? 0) : null;
        return (
          <li key={family} className="surface space-y-3 p-5" style={{ borderTop: `2px solid ${style.color}` }}>
            <p className="eyebrow flex items-center gap-2"><Icon size={14} style={{ color: style.color }} /> {family === "ride" ? "Cycling" : style.label}</p>
            <p className="num text-5xl text-cream">{v.sessions}<span className="ml-2 text-base text-mute">{v.sessions === 1 ? noun.slice(0, -1) : noun}</span></p>
            <p className="num text-sm text-paper">{v.sessions ? `${formatKm(v.distance_m)} km · ${formatDuration(v.duration_s)}` : "None in this phase yet"}</p>
            <p className="text-xs text-dim">{[pace ? `Averaging ${pace}` : v.sessions ? "Pace shows from 3 sessions" : null, was != null && phase.before.available ? `${was} in the ${phase.before.days} days before` : null].filter(Boolean).join(" · ") || " "}</p>
          </li>
        );
      })}
    </ul>
  );
}

function Totals({ phase }: { phase: PhaseDetail }) {
  const t = phase.totals;
  const fams = Object.entries(t.families).filter(([f]) => !SPORTS.some((x) => x.family === f)).sort((a, b) => b[1].duration_s - a[1].duration_s);
  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
        {FIGURE("sessions", String(t.sessions))}
        {FIGURE("training time", formatDuration(t.duration_s))}
        {FIGURE("km", formatKm(t.distance_m))}
        {FIGURE("m climbed", Math.round(t.ascent_m).toLocaleString())}
        {FIGURE("load", t.load != null ? Math.round(t.load).toLocaleString() : "—")}
        {FIGURE("active days", `${t.active_days}/${Math.max(1, phase.day_number)}`)}
      </dl>
      {fams.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {fams.map(([f, v]) => (
            <span key={f} className="chip" style={{ color: ACTIVITY_FAMILIES[f]?.color, borderColor: `${ACTIVITY_FAMILIES[f]?.color ?? "#888"}66` }}>
              {ACTIVITY_FAMILIES[f]?.label ?? f} · {v.sessions} · {formatDuration(v.duration_s)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const signed = (v: number, digits = 1) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(digits)}`;

function VsBefore({ phase }: { phase: PhaseDetail }) {
  const b = phase.before;
  if (!b.available) return <p className="text-sm text-mute">No earlier activity in the vault to compare against yet.</p>;
  const weeksNow = Math.max(1, phase.day_number) / 7;
  const weeksBefore = b.days / 7;
  const rows = [
    { label: "Sessions a week", now: phase.totals.sessions / weeksNow, then: b.sessions / weeksBefore, digits: 1 },
    { label: "Hours a week", now: phase.totals.duration_s / 3600 / weeksNow, then: b.duration_s / 3600 / weeksBefore, digits: 1 },
    { label: "Km a week", now: phase.totals.distance_m / 1000 / weeksNow, then: b.distance_m / 1000 / weeksBefore, digits: 0 },
  ];
  return (
    <div>
      <table className="w-full max-w-lg text-left text-sm">
        <thead className="text-[10px] tracking-widest text-dim uppercase">
          <tr><th className="py-2 font-normal" /><th className="py-2 font-normal">This phase</th><th className="py-2 font-normal">Before</th><th className="py-2 font-normal">Change</th></tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.label}>
              <td className="py-2.5 text-mute">{r.label}</td>
              <td className="num py-2.5 text-paper">{r.now.toFixed(r.digits)}</td>
              <td className="num py-2.5 text-mute">{r.then.toFixed(r.digits)}</td>
              <td className="num py-2.5 text-paper">{signed(r.now - r.then, r.digits)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-dim">Against the {b.days} days before the phase began ({weeksBefore.toFixed(1)} weeks). A change in what you did, not proof of why.</p>
    </div>
  );
}

function Vitals({ phase }: { phase: PhaseDetail }) {
  const v = phase.vitals;
  if (!v) return null;
  const rows = [
    { label: "Sleep", unit: "h", digits: 1, vit: v.sleep, good: 1 },
    { label: "HRV", unit: "ms", digits: 0, vit: v.hrv, good: 1 },
    { label: "Resting HR", unit: "bpm", digits: 0, vit: v.resting_hr, good: -1 },
  ];
  const ready = rows.filter((r) => r.vit.first != null && r.vit.latest != null);
  const w = v.weight;
  return (
    <div className="space-y-4">
      {ready.length > 0 || w.first != null ? (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
          {ready.map((r) => {
            const delta = r.vit.latest! - r.vit.first!;
            return (
              <div key={r.label}>
                <dd className="num text-2xl text-paper">{r.vit.first!.toFixed(r.digits)} → {r.vit.latest!.toFixed(r.digits)}<span className="ml-1 text-sm text-mute">{r.unit}</span></dd>
                <dt className="text-[10px] tracking-widest text-dim uppercase">{r.label} · {signed(delta, r.digits)} · {r.vit.n_first}/{r.vit.n_latest} days</dt>
              </div>
            );
          })}
          {w.first != null && w.latest != null && (
            <div>
              <dd className="num text-2xl text-paper">{w.first.toFixed(1)} → {w.latest.toFixed(1)}<span className="ml-1 text-sm text-mute">kg</span></dd>
              <dt className="text-[10px] tracking-widest text-dim uppercase">Weight · {signed(w.latest - w.first)} · {w.n} weigh-ins</dt>
            </div>
          )}
        </dl>
      ) : (
        <p className="text-sm text-mute">Needs four weeks into the phase and at least five readings in both the first and the latest two weeks before it says anything about sleep, HRV or resting heart rate.</p>
      )}
      <p className="text-xs text-dim">First two weeks of the phase against the latest two. Day-to-day noise is large; treat small changes as flat.</p>
    </div>
  );
}

function Highlights({ phase }: { phase: PhaseDetail }) {
  const h = phase.highlights;
  const items = [
    h.longest && { label: "Longest session", to: `/activities/${h.longest.id}`, title: h.longest.name, sub: `${formatDuration(h.longest.duration_s)} · ${formatShortDate(h.longest.day)}` },
    h.biggest_climb && { label: "Biggest climb", to: `/activities/${h.biggest_climb.id}`, title: h.biggest_climb.name, sub: `${Math.round(h.biggest_climb.ascent_m ?? 0)} m · ${formatShortDate(h.biggest_climb.day)}` },
    h.biggest_week && { label: "Biggest week", to: undefined, title: `Week of ${formatShortDate(h.biggest_week.start)}`, sub: `${h.biggest_week.sessions} sessions · ${formatDuration(h.biggest_week.minutes * 60)}` },
  ].filter(Boolean) as { label: string; to?: string; title: string; sub: string }[];
  if (!items.length) return null;
  return (
    <ul className="grid gap-3 sm:grid-cols-3">
      {items.map((i) => {
        const body = (
          <>
            <p className="eyebrow">{i.label}</p>
            <p className="mt-2 truncate text-lg text-paper">{i.title}</p>
            <p className="num text-sm text-mute">{i.sub}</p>
          </>
        );
        return <li key={i.label}>{i.to ? <Link to={i.to} className="surface surface-hover block p-4">{body}</Link> : <div className="surface p-4">{body}</div>}</li>;
      })}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <h2 className="eyebrow">{title}</h2>
      {children}
    </section>
  );
}

export function PhasePage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["phase", id], queryFn: () => api.phase(id), enabled: Number.isFinite(id), refetchInterval: 5 * 60_000 });
  const habits = useQuery({ queryKey: ["phases"], queryFn: api.phases, staleTime: 5 * 60_000 });
  const [editing, setEditing] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.deletePhase(id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["phases"] });
      client.invalidateQueries({ queryKey: ["phases-active"] });
      navigate("/phases");
    },
  });

  if (query.isPending) return <LoadingBlock height={520} />;
  if (query.isError) return <ErrorBlock error={query.error} retry={() => query.refetch()} />;
  const p = query.data;
  const opts = habits.data?.habits ?? [];
  const noData = !p.has_activity_data;

  return (
    <div className="space-y-12" style={{ ["--phase" as string]: p.color }}>
      <header>
        <div className="mb-4 flex items-center justify-between gap-4">
          <Link to="/phases" className="eyebrow inline-flex items-center gap-1 hover:text-paper"><ArrowLeft size={12} /> All phases</Link>
          <MoreMenu
            items={[
              { label: "Edit phase", onSelect: () => setEditing(true) },
              { label: <span className="text-coral">Delete phase</span>, hint: "Only the phase is removed, never your activities", onSelect: () => window.confirm(`Delete “${p.name}”? Your activities and data stay.`) && remove.mutate() },
            ]}
          />
        </div>
        <p className="eyebrow mb-3">{formatShortDate(p.start)} – {formatShortDate(p.end)} · {dayLine(p)}</p>
        <h1 className="font-display text-5xl leading-[0.95] tracking-tight text-cream sm:text-7xl"><span aria-hidden>{p.emoji} </span>{p.name}</h1>
        {p.tagline && <p className="mt-4 font-display text-2xl italic" style={{ color: p.color }}>{p.tagline}</p>}
        <div className="mt-8 max-w-2xl space-y-2">
          <Pct value={p.pct} color={p.color} />
          <p className="num text-sm text-mute">
            {p.state === "upcoming" ? `Starts in ${p.starts_in} days` : `${Math.round(p.pct * 100)}% of the way`} · {onTrackLine(p)}
          </p>
        </div>
      </header>

      {noData && <div className="surface p-6 text-mute">No activities have been synced yet, so nothing can be counted. Sync Garmin and this page fills in.</div>}

      {p.pillars.length > 0 && (
        <Section title="Your pillars">
          <ul className="grid gap-4 lg:grid-cols-2">{p.pillars.map((x) => <PillarCard key={x.id} p={x} phase={p} habits={opts} />)}</ul>
        </Section>
      )}

      {p.state !== "upcoming" && (
        <>
          <Section title="By sport"><Sports phase={p} /></Section>
          <Section title="Everything you’ve done in it"><Totals phase={p} /></Section>
          <Section title="Every day">
            <Heatmap phase={p} />
          </Section>
          {p.weeks.length > 0 && <Section title="Week by week"><WeekChart phase={p} /></Section>}
          <Highlights phase={p} />
          <Section title="Against the stretch before"><VsBefore phase={p} /></Section>
          <Section title="Body"><Vitals phase={p} /></Section>
        </>
      )}

      <Section title="Milestones">
        <ul className="flex flex-wrap gap-2">
          {p.milestones.map((m) => (
            <li key={m.key} className={clsx("chip", m.done ? "text-paper" : "text-dim")} style={m.done ? { borderColor: `${p.color}88` } : undefined}>
              {m.done && <Check size={12} style={{ color: p.color }} />} {m.label}{m.detail ? ` · ${m.detail}` : ""}
            </li>
          ))}
        </ul>
      </Section>

      {editing && <PhaseEditor open onOpenChange={setEditing} phase={p} habits={opts} onSaved={() => undefined} />}
    </div>
  );
}
