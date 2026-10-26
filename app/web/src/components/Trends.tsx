import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ArrowUpRight, HelpCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { formatShortDate } from "../lib/format";
import { STATUS_STYLE, deltaText } from "../lib/trends";
import type { SeriesTrend, TrainingStatusKey, TrainingTrend } from "../lib/types";
import { Chart, chartBase, type ChartOption } from "./Chart";
import { readyColor } from "./CoachNotes";
import { ErrorBlock, LoadingBlock, Segmented } from "./Shell";

const RANGES = [{ value: 7, label: "7D" }, { value: 28, label: "4W" }, { value: 84, label: "12W" }];
type Ready = Extract<SeriesTrend, { has_data: true }>;

const DIRECTION = {
  up: { Icon: ArrowUpRight, color: "#c8f560", word: "Heading up" },
  down: { Icon: ArrowDownRight, color: "#ff6a55", word: "Heading down" },
  steady: { Icon: ArrowRight, color: "#6cc7ff", word: "No clear direction" },
  unknown: { Icon: HelpCircle, color: "#5c5a55", word: "Too early to say" },
} as const;

function Stat({ label, value, sub, color }: { label: string; value: string; sub?: string | null; color?: string }) {
  return (
    <div>
      <p className="eyebrow mb-1">{label}</p>
      <p className="num text-2xl" style={{ color: color ?? "#ecebe6" }}>{value}</p>
      {sub && <p className="mt-0.5 text-[11px] leading-snug text-dim">{sub}</p>}
    </div>
  );
}

function seriesOption(t: Ready, name: string): ChartOption {
  const daily = t.days <= 14;
  const base = {
    ...chartBase,
    grid: { ...chartBase.grid, top: 12 },
    yAxis: { ...chartBase.yAxis, min: 0, max: 100, scale: false, interval: 25 },
    tooltip: { ...chartBase.tooltip, valueFormatter: (v: number) => String(Math.round(v)) },
  };
  if (daily) {
    return {
      ...base,
      xAxis: { ...chartBase.xAxis, type: "category", data: t.values.map((v) => formatShortDate(v.day)) },
      series: [{
        name, type: "bar", barMaxWidth: 26,
        data: t.values.map((v) => ({ value: v.value, itemStyle: { color: readyColor(v.value) } })),
        markLine: t.avg == null ? undefined : { silent: true, symbol: "none", lineStyle: { color: "#8d8a82", type: "dashed" }, label: { color: "#8d8a82", formatter: "avg {c}" }, data: [{ yAxis: t.avg }] },
      }],
    };
  }
  return {
    ...base,
    series: [
      { name: "Daily", type: "line", symbol: "none", data: t.values.map((v) => [v.day, v.value]), lineStyle: { color: "#5c5a55", width: 1 }, z: 1 },
      {
        name: "Weekly average", type: "line", symbol: "circle", symbolSize: 6, smooth: 0.25, z: 3,
        data: t.buckets.map((b) => {
          const mid = new Date(`${b.start}T12:00:00`);
          mid.setDate(mid.getDate() + 3);
          return [mid.getTime(), b.avg];
        }),
        lineStyle: { color: "#d9b26a", width: 2.5 }, itemStyle: { color: "#d9b26a" },
        markArea: { silent: true, data: [[{ yAxis: 70, itemStyle: { color: "rgba(200,245,96,0.05)" } }, { yAxis: 100 }], [{ yAxis: 0, itemStyle: { color: "rgba(255,106,85,0.05)" } }, { yAxis: 50 }]] },
      },
    ],
  };
}

/** Readiness or Cadence score over the last week, 4 weeks or 12 weeks: averages, change, days in band and where it is heading. */
export function TrendPanel({ kind, title, onRange }: { kind: "readiness" | "score"; title: string; onRange?: (days: number) => void }) {
  const [days, setDays] = useState(28);
  const q = useQuery({ queryKey: ["trends", kind, days], queryFn: () => api.seriesTrend(kind, days) });
  const t = q.data?.has_data ? q.data : null;
  const option = useMemo(() => (t ? seriesOption(t, title) : null), [t, title]);
  const head = t?.heading ? DIRECTION[t.heading.direction] : null;
  return (
    <section aria-label={`${title} history`}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="eyebrow">{title} over time</p>
        <Segmented label="Range" options={RANGES} value={days} onChange={(d) => { setDays(d); onRange?.(d); }} />
      </div>
      {q.isPending && <LoadingBlock height={260} />}
      {q.isError && <ErrorBlock error={q.error} retry={() => q.refetch()} />}
      {q.data && !q.data.has_data && <p className="text-sm text-mute">No history yet. Scores appear once the watch has synced a few days.</p>}
      {t && option && (
        <div className="space-y-5">
          {t.n < 3 ? (
            <p className="text-sm text-mute">Only {t.n} day{t.n === 1 ? "" : "s"} of data in this window, so there is no trend to draw yet.</p>
          ) : (
            <Chart option={option} height={210} label={`${title} over the last ${days} days`} />
          )}
          <div className="grid grid-cols-3 gap-4">
            <Stat label="Average" value={t.avg != null ? String(Math.round(t.avg)) : "—"} color={t.avg != null ? readyColor(t.avg) : undefined}
              sub={deltaText(t.delta, t.days) ?? (t.n ? "no earlier window to compare" : null)} />
            <Stat label="Range" value={t.min != null ? `${Math.round(t.min)}–${Math.round(t.max ?? 0)}` : "—"} sub={`${t.n} of ${t.days} days with data`} />
            <Stat label="Days 70+" value={t.bands ? `${t.bands.high}` : "—"} sub={t.bands ? `${t.bands.mid} at 50–69 · ${t.bands.low} under 50` : null} />
          </div>
          {head && t.heading && (
            <div className="flex gap-3 border-l-2 pl-3" style={{ borderColor: head.color }}>
              <head.Icon size={18} style={{ color: head.color }} className="mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-paper">{head.word}</p>
                <p className="mt-1 text-xs leading-relaxed text-mute">{t.heading.text}</p>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ---- training status ---------------------------------------------------------------------------

function statusOption(t: Extract<TrainingTrend, { has_data: true }>): ChartOption {
  return {
    ...chartBase,
    grid: { ...chartBase.grid, top: 12 },
    xAxis: { ...chartBase.xAxis, type: "category", data: t.weeks.map((w) => formatShortDate(w.week)) },
    yAxis: { ...chartBase.yAxis, scale: false, min: 0 },
    tooltip: { ...chartBase.tooltip, formatter: (p: { dataIndex: number }[]) => {
      const w = t.weeks[p[0].dataIndex];
      return `<b>${w.label}</b> · week of ${formatShortDate(w.week)}<br/>Load ${w.load}${w.expected ? ` (usual ${w.expected})` : ""}<br/>${w.sessions} sessions${w.change_pct != null ? ` · fitness ${w.change_pct > 0 ? "+" : ""}${w.change_pct}%` : ""}`;
    } },
    series: [
      { name: "Load", type: "bar", barMaxWidth: 28, data: t.weeks.map((w) => ({ value: w.load, itemStyle: { color: STATUS_STYLE[w.status].color } })) },
      { name: "Usual (7 × fitness)", type: "line", symbol: "none", step: "middle", data: t.weeks.map((w) => w.expected), lineStyle: { color: "#ecebe6", width: 1.2, type: "dashed" }, z: 3 },
    ],
  };
}

/** Week-by-week verdicts (progressing, maintaining, overloading, deloading, easing back, time off) from fitness change and load. */
export function StatusPanel() {
  const [weeks, setWeeks] = useState(12);
  const q = useQuery({ queryKey: ["trends", "training", weeks], queryFn: () => api.trainingTrend(weeks) });
  const t = q.data?.has_data ? q.data : null;
  const option = useMemo(() => (t ? statusOption(t) : null), [t]);
  const now = t?.current;
  const color = now ? STATUS_STYLE[now.status].color : "#5c5a55";
  return (
    <section aria-label="Training status history">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="eyebrow">Training status</p>
        <Segmented label="Range" options={[{ value: 4, label: "4W" }, { value: 12, label: "12W" }, { value: 26, label: "6M" }]} value={weeks} onChange={setWeeks} />
      </div>
      {q.isPending && <LoadingBlock height={260} />}
      {q.isError && <ErrorBlock error={q.error} retry={() => q.refetch()} />}
      {q.data && !q.data.has_data && <p className="text-sm text-mute">Training status needs a few weeks of synced activities.</p>}
      {t && now && option && (
        <div className="space-y-5">
          <div className="border-l-2 pl-3" style={{ borderColor: color }}>
            <p className="font-display text-3xl" style={{ color }}>{now.label}</p>
            <p className="mt-1 text-sm text-mute">{now.blurb}</p>
            <p className="mt-1 text-xs text-dim">{now.why}</p>
          </div>
          {t.n >= 2 && <Chart option={option} height={200} label="Weekly training load coloured by status" />}
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-mute">
            {(Object.keys(t.counts) as TrainingStatusKey[]).map((k) => (
              <span key={k} className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: STATUS_STYLE[k].color }} /> {t.statuses[k]?.label ?? k} · {t.counts[k]}
              </span>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Stat label="Fitness, last 4 weeks" value={t.slope_4w != null ? `${t.slope_4w > 0 ? "+" : ""}${t.slope_4w}%/wk` : "—"} sub={t.slope_4w == null ? "needs 4 weeks" : null} />
            <Stat label="Fitness, last 8 weeks" value={t.slope_8w != null ? `${t.slope_8w > 0 ? "+" : ""}${t.slope_8w}%/wk` : "—"} sub={t.slope_8w == null ? "needs 8 weeks" : null} />
          </div>
          {t.projection && (
            <p className="text-xs leading-relaxed text-mute">
              Fitness {t.projection.from} now, about {t.projection.to[0]}–{t.projection.to[1]} in {t.projection.weeks} weeks if the recent pace simply continues. {t.projection.note}
            </p>
          )}
          <details className="text-sm">
            <summary className="eyebrow cursor-pointer">Week by week</summary>
            <ul className="mt-3 space-y-2">
              {[...t.weeks].reverse().map((w) => (
                <li key={w.week} className="flex gap-3">
                  <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: STATUS_STYLE[w.status].color }} />
                  <span className="text-mute"><span className="text-paper">{formatShortDate(w.week)} · {w.label}</span> — {w.why}</span>
                </li>
              ))}
            </ul>
          </details>
          <p className="text-xs leading-relaxed text-dim">
            Each week is judged from fitness change, load against 7 × the fitness it started with, and acute:chronic load (0.8–1.3 productive, Gabbett 2016). Rules of thumb for labelling, not medical advice or proof of cause.
          </p>
        </div>
      )}
    </section>
  );
}
