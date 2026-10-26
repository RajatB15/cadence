import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowDownRight, ArrowRight, ArrowUpRight, HelpCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { formatShortDate } from "../lib/format";
import { STATUS_STYLE, deltaText } from "../lib/trends";
import type { EvidenceMarker, FitnessEvidence, SeriesTrend, TrainingStatusKey, TrainingTrend } from "../lib/types";
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
            <div className="flex items-center gap-2 text-sm">
              <head.Icon size={18} style={{ color: head.color }} className="shrink-0" />
              <span className="text-paper">{head.word}</span>
              {t.slope_per_week != null && t.direction !== "steady" && <span className="num text-mute">{t.slope_per_week > 0 ? "+" : ""}{t.slope_per_week}/wk</span>}
              {t.projection && <span className="num ml-auto text-mute">in 4 wks ≈ {t.projection.value} <span className="text-dim">({t.projection.range[0]}–{t.projection.range[1]})</span></span>}
            </div>
          )}
          {t.heading && (
            <details className="text-xs text-dim"><summary className="cursor-pointer">Details</summary><p className="mt-2 leading-relaxed">{t.heading.text}</p></details>
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

const MARKER_STYLE = { better: { color: "#c8f560", sign: "▲", word: "improving" }, worse: { color: "#ff6a55", sign: "▼", word: "worsening" },
  flat: { color: "#8d8a82", sign: "●", word: "unchanged" }, missing: { color: "#5c5a55", sign: "–", word: "not enough data" } } as const;
const VERDICT_COLOR = { adapting: "#c8f560", not_adapting: "#ff9f5a", fading: "#ff6a55", mixed: "#6cc7ff", unknown: "#5c5a55" } as const;

const SHORT: Record<string, string> = { efficiency: "Efficiency", critical_speed: "Crit. speed", vo2max: "VO₂max", resting_hr: "Resting HR", hrv: "HRV", drift: "HR drift" };

function markerValue(m: EvidenceMarker): string {
  if (m.change == null) return "no data";
  return `${m.change > 0 ? "+" : m.change < 0 ? "−" : ""}${Math.abs(m.change).toFixed(1)}${m.unit}`;
}

/** Six body markers as tiles: tap one for what it measures and how sure we are. Never blended into one score. */
export function EvidencePanel({ evidence }: { evidence: FitnessEvidence }) {
  const [open, setOpen] = useState<string | null>(null);
  const v = evidence.verdict;
  const color = VERDICT_COLOR[v.key];
  const life = evidence.life_strain;
  const picked = evidence.markers.find((m) => m.key === open);
  return (
    <section aria-label="Fitness evidence" className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="eyebrow">Is your body adapting?</p>
        <p className="font-display text-xl" style={{ color }}>{v.label}</p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {evidence.markers.map((m) => {
          const st = MARKER_STYLE[m.state];
          return (
            <button key={m.key} type="button" onClick={() => setOpen(open === m.key ? null : m.key)} aria-pressed={open === m.key}
              className={clsx("border p-2.5 text-left transition-colors", open === m.key ? "border-gold bg-gold/10" : "border-line hover:border-line-strong")}>
              <p className="text-[10px] tracking-wide text-mute uppercase">{SHORT[m.key] ?? m.label}</p>
              <p className="num mt-1 text-lg leading-none" style={{ color: st.color }}>{st.sign} <span className="text-sm">{markerValue(m)}</span></p>
            </button>
          );
        })}
      </div>
      {picked && (
        <div className="border-l-2 border-gold pl-3 text-xs leading-relaxed text-mute">
          <p className="text-paper">{picked.label}: {MARKER_STYLE[picked.state].word}</p>
          <p>{picked.note}</p>
          <p className="num text-dim">{picked.change != null && picked.ci ? `${picked.n} readings, last ${picked.window_days} days · 95% range ${picked.ci[0].toFixed(1)} to ${picked.ci[1].toFixed(1)}${picked.unit}` : picked.reason}</p>
        </div>
      )}
      <p className="num text-xs text-mute">
        {v.counts.better ?? 0} ▲ · {v.counts.worse ?? 0} ▼ · {v.counts.flat ?? 0} ● · {v.counts.missing ?? 0} no data
        {evidence.load ? ` · fitness ${evidence.load.change_pct > 0 ? "+" : ""}${evidence.load.change_pct}% in 6 wks` : ""}
        {life && life.state !== "missing" && life.state !== "usual" ? ` · everyday strain ${life.state === "heavy" ? "high" : "low"}` : ""}
      </p>
      <details className="text-xs text-dim">
        <summary className="cursor-pointer">How to read this</summary>
        <p className="mt-2 leading-relaxed">{v.text} A marker counts only when its 95% range excludes zero and the change beats everyday noise. Associations over weeks, not proof training caused them.</p>
      </details>
    </section>
  );
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
            <p className="mt-1 text-sm text-mute">{now.why}</p>
          </div>
          {t.evidence && <EvidencePanel evidence={t.evidence} />}
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
            <p className="num text-xs text-mute">Fitness {t.projection.from} → {t.projection.to[0]}–{t.projection.to[1]} in {t.projection.weeks} wks <span className="text-dim">if the pace continues</span></p>
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
          <details className="text-xs text-dim">
            <summary className="cursor-pointer">How weeks are judged</summary>
            <p className="mt-2 leading-relaxed">From fitness change, load against 7 × the fitness the week started with, and acute:chronic load (0.8–1.3 productive, Gabbett 2016). Rules of thumb for labelling, not medical advice or proof of cause.</p>
          </details>
        </div>
      )}
    </section>
  );
}
