import { clsx } from "clsx";
import { Scale } from "lucide-react";
import { useCallback, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { Sparkline } from "../Sparkline";
import { CountUp } from "../CountUp";
import { deltaTone, formatMetric, formatShortDate } from "../../lib/format";
import { orderVitals, vitalView } from "../../lib/home";
import { METRIC_STYLES, fallbackStyle } from "../../lib/metrics";
import { C } from "../../lib/theme";
import type { MetricSummary, Overview } from "../../lib/types";

const TILE = "surface surface-hover group relative flex min-h-[112px] w-[132px] shrink-0 snap-start flex-col overflow-hidden p-3.5 sm:w-auto";

function Accent({ color }: { color: string }) {
  return (
    <>
      <span aria-hidden className="absolute inset-x-0 top-0 h-[3px]" style={{ background: color }} />
      <span aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.10]" style={{ background: `linear-gradient(160deg, ${color}, transparent 60%)` }} />
    </>
  );
}

export function VitalTile({ m, today, index = 0 }: { m: MetricSummary; today: string; index?: number }) {
  const style = METRIC_STYLES[m.metric] ?? fallbackStyle;
  const Icon = style.icon;
  const v = vitalView(m, today);
  const tone = deltaTone(m.delta_pct, m.higher_is_better);
  const fmt = useCallback((x: number) => formatMetric(x, m.metric), [m.metric]);
  return (
    <Link to={`/metrics/${m.metric}`} className={clsx(TILE, "rise-in")} style={{ "--i": index } as CSSProperties} aria-label={`${m.label}: ${formatMetric(m.latest, m.metric)} ${m.unit}${v.stale ? `, from ${formatShortDate(m.latest_day)}, not synced today` : ""}${v.chip ? `, ${v.chip}` : ""}`}>
      <Accent color={style.color} />
      <span className="eyebrow relative flex items-center gap-1.5 !text-[11px] !tracking-[0.14em]">
        <Icon size={13} style={{ color: style.color }} aria-hidden /> <span className="truncate" title={m.label}>{m.label}</span>
      </span>
      <span className={clsx("relative mt-2 leading-none", v.stale ? "text-mute" : "text-cream")}>
        <CountUp value={m.latest} format={fmt} className="num text-[28px]" immediate />
        <span className="ml-1 text-[11px] font-semibold text-mute">{m.unit}</span>
      </span>
      <span className={clsx("relative mt-1 min-h-[16px] text-[11px] font-semibold", v.stale ? "text-dim" : tone === "good" ? "text-lime" : tone === "bad" ? "text-amber" : "text-mute")}>
        {v.stale ? `not synced · ${formatShortDate(m.latest_day)}` : v.chip ?? ""}
      </span>
      <Sparkline values={v.spark} baseline={v.baseline} color={style.color} height={24} className="relative mt-auto pt-1.5" />
    </Link>
  );
}

function WeightTile({ w, index }: { w: Extract<Overview, { has_data: true }>["weight"]; index: number }) {
  if (w.latest_trend_kg == null) return null;
  return (
    <Link to="/weight" className={clsx(TILE, "rise-in")} style={{ "--i": index } as CSSProperties} aria-label={`Weight trend ${w.latest_trend_kg.toFixed(1)} kilograms`}>
      <Accent color={C.sky} />
      <span className="eyebrow relative flex items-center gap-1.5 !text-[11px] !tracking-[0.14em]"><Scale size={13} style={{ color: C.sky }} aria-hidden /> Weight</span>
      <span className="relative mt-2 leading-none text-cream"><span className="num text-[28px]">{(w.latest_reading?.weight_kg ?? w.latest_trend_kg).toFixed(1)}</span><span className="ml-1 text-[11px] font-semibold text-mute">kg</span></span>
      <span className="relative mt-1 min-h-[16px] text-[11px] font-semibold text-mute">trend {w.latest_trend_kg.toFixed(1)}</span>
      <Sparkline values={w.spark.slice(-7).map((s) => s.value)} color={C.sky} height={24} className="relative mt-auto pt-1.5" />
    </Link>
  );
}

/** Swipeable on phones (snap), a grid from tablet width. Missing metrics are simply absent, never shown as zero. */
export function VitalsRail({ metrics, weight, today, phase, order }: { metrics: MetricSummary[]; weight: Extract<Overview, { has_data: true }>["weight"]; today: string; phase: string | undefined; order?: readonly string[] | null }) {
  const tiles = orderVitals(metrics, phase, order);
  if (!tiles.length) {
    return (
      <section aria-label="Vitals" className="surface p-5">
        <p className="eyebrow mb-1">Vitals</p>
        <p className="text-sm text-mute">No vitals synced yet. They appear here after your next Garmin sync.</p>
      </section>
    );
  }
  return (
    <section aria-label="Vitals">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="eyebrow">Today vs your usual</p>
        <p className="eyebrow !text-dim">7-day line, dashed = usual</p>
      </div>
      <div className="-mx-5 flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-px-5 px-5 pb-2 [scrollbar-width:none] sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0 lg:grid-cols-7 [&::-webkit-scrollbar]:hidden">
        {tiles.map((m, i) => (
          <VitalTile key={m.metric} m={m} today={today} index={i} />
        ))}
        <WeightTile w={weight} index={tiles.length} />
      </div>
    </section>
  );
}
