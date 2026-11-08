import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Check } from "lucide-react";
import { useCallback, useRef, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { CountUp } from "../CountUp";
import { dayRingSummary, type DayRingItem } from "../../lib/dayRing";
import { withAlpha } from "../../lib/color";
import { fitNumeral, holeRadius, labelWidthPx, numeralWidthEm } from "../../lib/ringFit";
import { useElementWidth } from "../../lib/useElementWidth";
import { C } from "../../lib/theme";

// Ring radii in a 200 box, outer to inner. 10px strokes with a 5px gap leave a hole of radius 45 for the centre text.
const RINGS = [92, 77, 62, 47];
const STROKE = 10;
const MAX_SIZE = 240;

/** Digits-only values count up; anything else ("7h 39m", "—") is shown as is. */
function numericOf(v: string): number | null {
  const n = Number(v.replace(/,/g, ""));
  return /^[\d,]+$/.test(v) && Number.isFinite(n) ? n : null;
}
const fmtInt = (n: number) => Math.round(n).toLocaleString();

function endPoint(r: number, f: number) {
  const a = f * Math.PI * 2;
  return { x: 100 + r * Math.cos(a), y: 100 + r * Math.sin(a) };
}

function Ringlet({ item, r, index }: { item: DayRingItem; r: number; index: number }) {
  const reduce = useReducedMotion();
  const color = C[item.accent];
  const f = Math.min(1, item.fraction);
  const end = endPoint(r, f);
  return (
    <g opacity={item.stale ? 0.55 : 1}>
      <circle cx="100" cy="100" r={r} fill="none" stroke={withAlpha(color, 0.14)} strokeWidth={STROKE} />
      {!item.missing && f > 0 && (
        <>
          <motion.circle
            cx="100" cy="100" r={r} fill="none" stroke={color} strokeWidth={STROKE} strokeLinecap="round" pathLength={1}
            initial={{ strokeDasharray: reduce ? `${Math.max(f, 0.001)} 1.01` : "0.001 1.01" }}
            animate={{ strokeDasharray: `${Math.max(f, 0.001)} 1.01` }}
            transition={{ duration: reduce ? 0 : 1.3, delay: reduce ? 0 : 0.15 + index * 0.12, ease: [0.16, 1, 0.3, 1] }}
          />
          {/* A bright cap on the leading edge gives the arc a lit, rounded end. */}
          <motion.circle
            cx={end.x} cy={end.y} r={2.2} fill="#fff" fillOpacity={0.85}
            initial={{ opacity: reduce ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ delay: reduce ? 0 : 1.2 + index * 0.1, duration: 0.4 }}
          />
        </>
      )}
      {item.closed && <circle className="ring-halo" cx="100" cy="100" r={r} fill="none" stroke={color} strokeWidth={STROKE + 4} style={{ transformOrigin: "100px 100px", opacity: 0 }} />}
    </g>
  );
}

function Value({ item }: { item: DayRingItem }) {
  const n = numericOf(item.value);
  return n == null ? <>{item.value}</> : <CountUp value={n} format={fmtInt} immediate />;
}

/** The hero: four concentric rings (recovery, sleep, move, fuel), each against a stated reference, never blended. */
export function DayRing({ rings, accent, asOf, demo }: { rings: DayRingItem[]; accent: string; asOf?: string | null; demo?: boolean }) {
  const [focus, setFocus] = useState(0);
  const cycle = useCallback(() => setFocus((f) => (f + 1) % rings.length), [rings.length]);
  const cur = rings[focus] ?? rings[0];
  const box = useRef<HTMLButtonElement>(null);
  const width = useElementWidth(box, MAX_SIZE);
  // Size the numeral from the hole inside the innermost ring, against the longest value and label that can show.
  const hole = holeRadius(width, RINGS[RINGS.length - 1], STROKE);
  const longest = rings.reduce((a, r) => (numeralWidthEm(r.value) > numeralWidthEm(a) ? r.value : a), "0");
  const longestLabel = rings.reduce((a, r) => (r.label.length > a.length ? r.label : a), "");
  const font = fitNumeral({ radius: hole, text: longest, label: { width: labelWidthPx(longestLabel, 11, { upper: true, trackingEm: 0.1 }), height: 13 }, gap: 3, pad: 4, min: 15, max: 32 });
  const closedCount = rings.filter((r) => r.closed).length;
  return (
    <section aria-label="Today's rings" className="surface relative overflow-hidden p-5 sm:p-7">
      <span aria-hidden className="pointer-events-none absolute -top-24 left-1/2 h-64 w-[130%] -translate-x-1/2 rounded-full opacity-[0.16] blur-3xl" style={{ background: accent }} />
      <div className="relative mb-4 flex items-baseline justify-between gap-3">
        <p className="eyebrow">Today · four rings</p>
        <p className="eyebrow !text-dim">
          {closedCount > 0 ? `${closedCount} of ${rings.length} closed` : demo ? "Demo data" : asOf ?? "vs a stated reference"}
        </p>
      </div>
      <div className="relative grid items-center gap-6 sm:grid-cols-[auto_1fr] sm:gap-10">
        <button
          type="button"
          ref={box}
          data-ring-fit="dayring" data-inner="45"
          onClick={cycle}
          aria-label={`Showing ${cur.label}. Tap to show the next ring.`}
          className="press relative mx-auto block aspect-square w-full rounded-full"
          style={{ maxWidth: MAX_SIZE, filter: `drop-shadow(0 0 18px ${withAlpha(accent, 0.2)})` } as CSSProperties}
        >
          <svg viewBox="0 0 200 200" className="h-full w-full -rotate-90" role="img" aria-label={dayRingSummary(rings)}>
            {rings.map((it, i) => (
              <Ringlet key={it.key} item={it} r={RINGS[i]} index={i} />
            ))}
          </svg>
          <div className="pointer-events-none absolute inset-0 grid place-items-center">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={cur.key}
                initial={{ opacity: 0, scale: 0.92, y: 4 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 1.04 }}
                transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                className="text-center"
              >
                <p className="numeral whitespace-nowrap" style={{ fontSize: font, color: cur.missing ? C.dim : C[cur.accent] }}>
                  <Value item={cur} />
                </p>
                <p className="eyebrow mt-[3px] whitespace-nowrap !text-[11px] !leading-[13px] !tracking-[0.1em]">{cur.label}</p>
              </motion.div>
            </AnimatePresence>
          </div>
        </button>

        <ul className="grid grid-cols-2 gap-2.5">
          {rings.map((it, i) => (
            <li key={it.key}>
              <Link
                to={it.to}
                onMouseEnter={() => setFocus(i)}
                onFocus={() => setFocus(i)}
                aria-label={`${it.label}: ${it.missing ? "no data" : `${it.value}, ${it.sub}`}`}
                className="press group relative block min-h-[76px] rounded-2xl border px-3.5 py-3 transition-colors"
                style={{ borderColor: i === focus ? withAlpha(C[it.accent], 0.55) : "var(--rim)", background: i === focus ? withAlpha(C[it.accent], 0.09) : "var(--pill)" }}
              >
                <span className="flex items-center gap-1.5 text-[11px] font-bold tracking-wide" style={{ color: C[it.accent] }}>
                  <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: C[it.accent], opacity: it.stale ? 0.5 : 1 }} />
                  {it.label}
                  {it.closed && <Check size={12} strokeWidth={3} aria-hidden className="ml-auto" />}
                </span>
                <span className={`num mt-1 block text-[22px] leading-none ${it.missing || it.stale ? "text-mute" : "text-cream"}`}>
                  <Value item={it} />
                </span>
                <span className="mt-1 block text-[11px] leading-snug text-mute">{it.stale ? `${it.sub} · earlier day` : it.sub}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
