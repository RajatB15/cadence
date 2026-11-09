import { motion, useReducedMotion } from "motion/react";
import { Check } from "lucide-react";
import { Link } from "react-router-dom";
import { CountUp } from "../CountUp";
import { dayRingSummary, type DayRingItem } from "../../lib/dayRing";

const fmtInt = (n: number) => Math.round(n).toLocaleString();
const numericOf = (v: string): number | null => {
  const n = Number(v.replace(/,/g, ""));
  return /^[\d,]+$/.test(v) && Number.isFinite(n) ? n : null;
};

function Value({ item }: { item: DayRingItem }) {
  const n = numericOf(item.value);
  return n == null ? <>{item.value}</> : <CountUp value={n} format={fmtInt} immediate />;
}

function Meter({ item, index }: { item: DayRingItem; index: number }) {
  const reduce = useReducedMotion();
  const color = `var(--color-${item.accent})`;
  const f = item.missing ? 0 : Math.min(1, item.fraction);
  return (
    <Link
      to={item.to}
      aria-label={`${item.label}: ${item.missing ? "no data" : `${item.value}, ${item.sub}${item.stale ? ", from an earlier day" : ""}`}`}
      className="press group block rounded-2xl border border-[var(--rim)] bg-[var(--pill)] px-4 py-3.5"
      style={{ opacity: item.stale ? 0.7 : 1 }}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-center gap-2 text-[13px] font-bold" style={{ color }}>
          <i aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
          {item.label}
          {item.closed && <Check size={13} strokeWidth={3} aria-hidden />}
        </span>
        <span className={`numeral text-[26px] leading-none ${item.missing ? "text-dim" : "text-cream"}`}><Value item={item} /></span>
      </div>
      <div className="relative mt-3 h-2.5 overflow-hidden rounded-full" style={{ background: "color-mix(in srgb, var(--color-paper) 10%, transparent)" }}>
        {!item.missing && (
          <motion.span
            aria-hidden
            className="absolute inset-y-0 left-0 rounded-full"
            style={{ background: color, boxShadow: `0 0 12px color-mix(in srgb, ${color} 35%, transparent)` }}
            initial={{ width: reduce ? `${f * 100}%` : 0 }}
            animate={{ width: `${f * 100}%` }}
            transition={{ duration: reduce ? 0 : 1, delay: reduce ? 0 : 0.1 + index * 0.1, ease: [0.16, 1, 0.3, 1] }}
          />
        )}
      </div>
      <p className="mt-1.5 text-[12px] leading-snug text-mute">{item.stale ? `${item.sub} · earlier day` : item.sub}</p>
    </Link>
  );
}

/** Today at a glance: four labelled meters, each against a stated reference, every value readable without a tap. Never blended into one score. */
export function DayBoard({ rings, asOf, demo }: { rings: DayRingItem[]; asOf?: string | null; demo?: boolean }) {
  const closed = rings.filter((r) => r.closed).length;
  return (
    <section aria-label="Today" className="surface relative p-5 sm:p-6">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="eyebrow">Today</p>
        <p className="eyebrow !text-dim">{closed > 0 ? `${closed} of ${rings.length} reached` : demo ? "Demo data" : asOf ?? "vs a stated reference"}</p>
      </div>
      <p className="sr-only">{dayRingSummary(rings)}</p>
      <div className="grid gap-2.5 sm:grid-cols-2">
        {rings.map((it, i) => <Meter key={it.key} item={it} index={i} />)}
      </div>
    </section>
  );
}
