import { motion, useReducedMotion } from "motion/react";
import { useRef } from "react";
import { goalRing, type GoalStatus } from "../lib/goalRing";
import { fitNumeral, holeRadius, labelWidthPx } from "../lib/ringFit";
import { useElementWidth } from "../lib/useElementWidth";
import { CountUp } from "./CountUp";

const R = 78;
const W = 18;
const MAX = 168;
const TONE: Record<GoalStatus, string> = { none: "var(--color-dim)", no_target: "var(--color-gold)", below: "var(--color-sky)", within: "var(--color-mint)", above: "var(--color-amber)" };

const point = (f: number) => {
  const a = f * Math.PI * 2;
  return { x: 100 + R * Math.cos(a), y: 100 + R * Math.sin(a) };
};

/**
 * One goal as one ring: the fill is what you have, the pale arc is the target band, and the number in the middle always
 * has the target written under it. Missing is an empty ring and a dash, never a zero.
 */
export function GoalRing({ label, value, band, unit, format = (n) => Math.round(n).toLocaleString(), note }: {
  label: string;
  value: number | null;
  band: [number, number] | null;
  unit: string;
  format?: (n: number) => string;
  /** Replaces the status line under the ring (for wording the caller owns). */
  note?: string | null;
}) {
  const reduce = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const width = useElementWidth(box, MAX);
  const m = goalRing(value, band);
  const tone = TONE[m.status];
  const target = band ? `of ${format(band[0])}–${format(band[1])}` : unit;
  const text = value == null ? "—" : format(value);
  const font = fitNumeral({ radius: holeRadius(width, R, W), text, label: { width: labelWidthPx(target, 11), height: 13 }, gap: 3, pad: 5, min: 18, max: 32 });
  const status =
    note ??
    (m.status === "none" ? "Nothing logged yet" :
     m.status === "below" ? `${format(m.gap)} ${unit} to the low end` :
     m.status === "above" ? `${format(m.gap)} ${unit} above` :
     m.status === "within" ? "In range" : "No target yet");
  const end = point(m.fill);
  return (
    <div className="flex flex-col items-center text-center" role="group" aria-label={`${label}: ${value == null ? "nothing logged" : `${text} ${unit}`}${band ? `, target ${format(band[0])} to ${format(band[1])} ${unit}` : ""}. ${status}`}>
      <p className="eyebrow mb-2">{label} · {unit}</p>
      <div ref={box} className="relative aspect-square w-full" style={{ maxWidth: MAX }} data-ring-fit="goal" data-inner={R - W / 2}>
        <svg viewBox="0 0 200 200" className="h-full w-full -rotate-90" aria-hidden>
          <circle cx="100" cy="100" r={R} fill="none" stroke="color-mix(in srgb, var(--color-paper) 9%, transparent)" strokeWidth={W} />
          {band && m.bandTo > m.bandFrom && (
            <g transform={`rotate(${m.bandFrom * 360} 100 100)`}>
              <circle cx="100" cy="100" r={R} fill="none" stroke="color-mix(in srgb, var(--color-paper) 30%, transparent)" strokeWidth={W} pathLength={1} strokeDasharray={`${m.bandTo - m.bandFrom} 1.0001`} />
            </g>
          )}
          {m.fill > 0 && (
            <motion.circle
              cx="100" cy="100" r={R} fill="none" stroke={tone} strokeWidth={W - 6} strokeLinecap="round" pathLength={1}
              initial={{ strokeDasharray: reduce ? `${Math.max(m.fill, 0.002)} 1.01` : "0.002 1.01" }}
              animate={{ strokeDasharray: `${Math.max(m.fill, 0.002)} 1.01` }}
              transition={{ duration: reduce ? 0 : 1.1, ease: [0.16, 1, 0.3, 1] }}
            />
          )}
          {m.fill > 0.03 && <circle cx={end.x} cy={end.y} r={2.4} fill="#fff" fillOpacity={0.85} />}
        </svg>
        <div className="pointer-events-none absolute inset-0 grid place-items-center">
          <div>
            <p className="numeral whitespace-nowrap text-cream" style={{ fontSize: font }}>
              {value == null ? text : <CountUp value={value} format={format} immediate />}
            </p>
            <p className="mt-[3px] whitespace-nowrap text-[11px] leading-[13px] text-mute">{target}</p>
          </div>
        </div>
      </div>
      <p className="mt-2 text-xs font-semibold" style={{ color: m.status === "none" || m.status === "no_target" ? "var(--color-mute)" : tone }}>{status}</p>
    </div>
  );
}
