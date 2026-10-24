import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowLeft, ChevronLeft, ChevronRight, CloudDownload } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { calendarAverage } from "../lib/series";
import { Chart, chartBase, type ChartOption } from "../components/Chart";
import { NoteGrid, NoteLines, readyColor } from "../components/CoachNotes";
import { humanize } from "../components/DataViews";
import { MetricDayPanels } from "../components/DayPanels";
import { ErrorBlock, LoadingBlock, PageHeader, Segmented } from "../components/Shell";
import { READ_ONLY, api } from "../lib/api";
import { deltaTone, formatMetric, parseDay } from "../lib/format";
import { METRIC_STYLES, fallbackStyle } from "../lib/metrics";
import type { DayCoach as DayCoachData, DayMetric, MetricSeries } from "../lib/types";

const RANGES = [
  { value: 30, label: "30D" },
  { value: 90, label: "90D" },
  { value: 365, label: "1Y" },
  { value: 3650, label: "All" },
];
const longDate = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });

function isoDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

export function MetricPage() {
  const { metric = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [days, setDays] = useState(90);
  const query = useQuery({ queryKey: ["metric", metric, days], queryFn: () => api.metric(metric, days) });
  const style = METRIC_STYLES[metric] ?? fallbackStyle;
  const points = query.data?.points ?? [];
  const selected = params.get("day") ?? points[points.length - 1]?.day ?? null;
  const select = (day: string) => setParams({ day }, { replace: true });

  return (
    <>
      <Link to="/" className="eyebrow mb-6 inline-flex items-center gap-2 hover:text-paper">
        <ArrowLeft size={12} /> Overview
      </Link>
      <PageHeader
        eyebrow={style.blurb}
        title={<span style={{ color: style.color }}>{query.data?.label ?? "…"}</span>}
      >
        <Segmented label="Range" options={RANGES} value={days} onChange={setDays} />
      </PageHeader>
      {query.isPending ? (
        <LoadingBlock height={480} />
      ) : query.isError ? (
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      ) : points.length === 0 || !selected ? (
        <div className="surface p-12 text-center text-mute">No data for this metric yet.</div>
      ) : (
        <div className="space-y-6">
          <DayView metric={metric} day={selected} color={style.color} onSelect={select} />
          <Trend data={query.data} color={style.color} selected={selected} onSelect={select} />
          <DayDetails metric={metric} day={selected} />
        </div>
      )}
    </>
  );
}

function useDay(day: string) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["day", day], queryFn: () => api.day(day) });
  const fetchDay = useMutation({
    mutationFn: () => api.fetchDay(day),
    onSettled: () => client.invalidateQueries({ queryKey: ["day", day] }),
  });
  const tried = useRef<string | null>(null);
  const missing = query.data?.missing.length ?? 0;
  useEffect(() => {
    // Intraday detail not yet archived is fetched once per day, then served from the vault forever.
    if (!READ_ONLY && missing && tried.current !== day) {
      tried.current = day;
      fetchDay.mutate();
    }
  }, [missing, day, fetchDay]);
  return { query, fetchDay };
}

function DayView({ metric, day, color, onSelect }: { metric: string; day: string; color: string; onSelect: (d: string) => void }) {
  const { query, fetchDay } = useDay(day);
  const d = query.data;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!d || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowLeft" && d.prev_day) onSelect(d.prev_day);
      if (e.key === "ArrowRight" && d.next_day) onSelect(d.next_day);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [d, onSelect]);

  const m = d?.metrics[metric];
  return (
    <section className="relative overflow-hidden border-y border-line py-8">
      <div className="pointer-events-none absolute -top-24 right-0 h-72 w-72 rounded-full opacity-15 blur-3xl" style={{ background: color }} />
      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          aria-label="Previous day"
          disabled={!d?.prev_day}
          onClick={() => d?.prev_day && onSelect(d.prev_day)}
          className="grid h-10 w-10 place-items-center border border-line-strong text-mute hover:text-paper disabled:opacity-30"
        >
          <ChevronLeft size={18} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Selected day<span className="pointer-coarse:hidden"> · ← → to move</span></p>
          <p className="font-display text-3xl text-cream sm:text-4xl">{longDate.format(parseDay(day))}</p>
        </div>
        <button
          type="button"
          aria-label="Next day"
          disabled={!d?.next_day}
          onClick={() => d?.next_day && onSelect(d.next_day)}
          className="grid h-10 w-10 place-items-center border border-line-strong text-mute hover:text-paper disabled:opacity-30"
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {query.isPending ? (
        <div className="mt-8 h-40 animate-pulse bg-coal" />
      ) : query.isError ? (
        <div className="mt-6"><ErrorBlock error={query.error} retry={() => query.refetch()} /></div>
      ) : !m ? (
        <p className="mt-8 text-mute">No {humanize(metric)} recorded on this day.</p>
      ) : (
        <motion.div key={day} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <div>
            <p className="num text-7xl leading-none sm:text-8xl" style={{ color }}>
              {formatMetric(m.value, metric)}
              <span className="ml-3 text-xl text-mute">{m.unit}</span>
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Compare label="vs 7-day avg" value={m.value} ref_={m.avg_7d} m={m} />
              <Compare label="vs 60-day baseline" value={m.value} ref_={m.baseline_60d} m={m} />
              <Compare label="vs prior week" value={m.value} ref_={m.prev_7d} m={m} />
            </div>
            {fetchDay.isPending && (
              <p className="mt-4 flex items-center gap-2 text-xs text-gold">
                <CloudDownload size={14} className="animate-pulse" /> Fetching this day's detail from Garmin (once)…
              </p>
            )}
          </div>
          <Context m={m} metric={metric} color={color} />
        </motion.div>
      )}
      {d?.coach && <DayCoach coach={d.coach} metric={metric} day={day} />}
    </section>
  );
}

function DayCoach({ coach, metric, day }: { coach: DayCoachData; metric: string; day: string }) {
  const mine = coach.notes.filter((n) => n.metrics.includes(metric));
  const rest = coach.notes.filter((n) => !n.metrics.includes(metric) && n.severity !== "info");
  const r = coach.readiness;
  if (!mine.length && !rest.length && !r) return null;
  return (
    <motion.div key={day} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-10 space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <p className="eyebrow">Coach on this day</p>
        {r && coach.call && (
          <span className="chip" style={{ color: readyColor(r.score), borderColor: `${readyColor(r.score)}55` }}>
            Readiness {r.score} · {coach.call.headline}
          </span>
        )}
      </div>
      {mine.length > 0 && <NoteGrid notes={mine} compact />}
      {rest.length > 0 && (
        <details className="group border border-line bg-ink/30 px-5">
          <summary className="eyebrow cursor-pointer py-3 hover:text-paper">
            Elsewhere that day · {rest.length}
          </summary>
          <NoteLines notes={rest} />
        </details>
      )}
    </motion.div>
  );
}

function Compare({ label, value, ref_, m }: { label: string; value: number; ref_: number | null; m: DayMetric }) {
  if (ref_ == null || ref_ === 0) return null;
  const pct = ((value - ref_) / Math.abs(ref_)) * 100;
  const tone = deltaTone(pct, m.higher_is_better);
  return (
    <span className={clsx("chip", tone === "good" && "!border-lime/40 !text-lime", tone === "bad" && "!border-amber/40 !text-amber")}>
      {Math.abs(pct) < 0.5 ? "≈" : pct > 0 ? "▲" : "▼"} {Math.abs(pct).toFixed(Math.abs(pct) < 10 ? 1 : 0)}% {label}
    </span>
  );
}

function Context({ m, metric, color }: { m: DayMetric; metric: string; color: string }) {
  const fmt = (v: number | null) => (v == null ? "—" : formatMetric(v, metric));
  const span = m.all_max - m.all_min || 1;
  const pos = (v: number) => `${((v - m.all_min) / span) * 100}%`;
  const rankText =
    m.higher_is_better === false
      ? `#${m.count - m.rank_high + 1} lowest`
      : `#${m.rank_high} highest`;
  return (
    <div>
      <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
        {[
          ["7-day avg", m.avg_7d],
          ["30-day avg", m.avg_30d],
          ["60-day baseline", m.baseline_60d],
          ["All-time avg", m.all_avg],
        ].map(([label, v]) => (
          <div key={label as string}>
            <p className="eyebrow mb-1">{label}</p>
            <p className="num text-2xl text-paper">{fmt(v as number | null)}</p>
          </div>
        ))}
      </div>
      <div className="mt-8">
        <div className="flex flex-wrap justify-between gap-x-3 gap-y-1 text-xs text-dim">
          <span>Lowest {fmt(m.all_min)}</span>
          <span className="order-last w-full text-center sm:order-none sm:w-auto">
            {rankText} of {m.count.toLocaleString()} days
            {m.percentile != null && ` · ${m.percentile}th percentile`}
          </span>
          <span>Highest {fmt(m.all_max)}</span>
        </div>
        <div className="relative mt-3 h-8">
          <div className="absolute inset-x-0 top-3.5 h-1 bg-line-strong" />
          {m.avg_30d != null && (
            <div className="absolute top-1.5 h-5 w-px bg-mute" style={{ left: pos(m.avg_30d) }} title="30-day average" />
          )}
          <motion.div
            className="absolute top-1 h-6 w-6 -translate-x-1/2 rounded-full border-2 border-ink"
            style={{ background: color }}
            initial={{ left: "50%" }}
            animate={{ left: pos(m.value) }}
            transition={{ duration: 0.8, ease: [0.2, 0.9, 0.1, 1] }}
          />
        </div>
        <p className="mt-2 text-xs text-dim">
          Since {parseDay(m.first_day).toLocaleDateString(undefined, { month: "short", year: "numeric" })} · grey tick is your 30-day average
        </p>
      </div>
    </div>
  );
}

function Trend({
  data,
  color,
  selected,
  onSelect,
}: {
  data: MetricSeries;
  color: string;
  selected: string;
  onSelect: (day: string) => void;
}) {
  const avg7 = useMemo(() => calendarAverage(data.points, 7, 3), [data.points]);
  const days = useMemo(() => data.points.map((p) => p.day), [data]);

  const option = useMemo<ChartOption>(
    () => ({
      ...chartBase,
      series: [
        {
          name: "Daily",
          type: "bar",
          data: data.points.map((p) => ({
            value: [p.day, p.value],
            itemStyle: { color: p.day === selected ? color : `${color}40` },
          })),
          barMaxWidth: 8,
          markLine: {
            symbol: "none",
            silent: true,
            label: { show: false },
            lineStyle: { color: "#f2e8cf", type: "solid", width: 1 },
            data: [{ xAxis: selected }],
          },
        },
        {
          name: "7-day average",
          type: "line",
          data: avg7,
          symbol: "none",
          smooth: 0.2,
          connectNulls: false,
          lineStyle: { color, width: 2.5, shadowColor: color, shadowBlur: 10 },
        },
      ],
      yAxis: { ...chartBase.yAxis, scale: data.metric !== "steps" && data.metric !== "training_load" },
    }),
    [data, color, avg7, selected],
  );

  const pick = (x: number) => {
    const target = isoDay(x);
    let best = days[0];
    for (const d of days) if (Math.abs(parseDay(d).getTime() - parseDay(target).getTime()) < Math.abs(parseDay(best).getTime() - parseDay(target).getTime())) best = d;
    if (best) onSelect(best);
  };

  return (
    <section className="surface p-4 sm:p-6">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3 px-2">
        <p className="eyebrow">Trend · bars are days, line is the 7-day average</p>
        <p className="text-xs text-dim"><span className="pointer-coarse:hidden">Click</span><span className="hidden pointer-coarse:inline">Tap</span> any day to open it</p>
      </div>
      <Chart option={option} height={300} label={`${data.label} trend`} onPickX={pick} />
    </section>
  );
}

function DayDetails({ metric, day }: { metric: string; day: string }) {
  const { query } = useDay(day);
  if (!query.data) return null;
  return <MetricDayPanels metric={metric} d={query.data} />;
}
