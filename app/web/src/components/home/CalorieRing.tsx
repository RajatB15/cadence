import { motion, useReducedMotion } from "motion/react";
import { useCallback, useRef } from "react";
import { CountUp } from "../CountUp";
import { circumference, ringGeometry } from "../../lib/home";
import { fitNumeral, holeRadius, labelWidthPx } from "../../lib/ringFit";
import { useElementWidth } from "../../lib/useElementWidth";
import { C } from "../../lib/theme";

interface Props {
  burned: number;
  active: number | null;
  resting: number | null;
  eaten: number | null;
  target: number | null;
  projected: { lo: number; hi: number } | null;
  asOf: string | null;
  /** Largest diameter in px; the ring shrinks to fit narrower columns (down to 320px screens). */
  size?: number;
  /** One text sentence for screen readers, built by the caller from the same numbers. */
  summary: string;
}

// Radii in a 200 box. Strokes never overlap: range 92.5..97.5, burn 76..88, eaten 62..70, leaving a hole of radius 62.
const R_RANGE = 95;
const R_BURN = 82;
const R_EATEN = 66;
const W_RANGE = 5;
const W_BURN = 12;
const W_EATEN = 8;
const KCAL_PX = 11;

function Arc({ r, from, to, color, width, cap = "butt", delay = 0, opacity = 1 }: { r: number; from: number; to: number; color: string; width: number; cap?: "butt" | "round"; delay?: number; opacity?: number }) {
  const reduce = useReducedMotion();
  if (to <= from) return null;
  const len = to - from;
  const c = circumference(r);
  const final = `${len} ${1 - len + 0.0001}`;
  return (
    <g transform={`rotate(${from * 360} 100 100)`}>
      <motion.circle
        cx="100" cy="100" r={r} fill="none" stroke={color} strokeWidth={width} strokeLinecap={cap} pathLength={1} opacity={opacity}
        initial={{ strokeDasharray: reduce ? final : `0 1.0001` }}
        animate={{ strokeDasharray: final }}
        transition={{ duration: reduce ? 0 : 1.1, ease: [0.2, 0.9, 0.1, 1], delay: reduce ? 0 : delay }}
        data-circumference={c.toFixed(0)}
      />
    </g>
  );
}

/** Calorie ring: burn so far (resting then active, centre number), projected range on the outer ring, intake on the inner ring. */
export function CalorieRing({ burned, active, resting, eaten, target, projected, asOf, size = 208, summary }: Props) {
  const reduce = useReducedMotion();
  const g = ringGeometry({ burned, active, resting, projected, eaten, target });
  const fmt = useCallback((v: number) => Math.round(v).toLocaleString(), []);
  const box = useRef<HTMLDivElement>(null);
  const width = useElementWidth(box, size);
  // The numeral is sized from the hole inside the innermost stroke, so the longest figure still clears the rings.
  const text = fmt(burned);
  const font = fitNumeral({ radius: holeRadius(width, R_EATEN, W_EATEN), text, label: { width: labelWidthPx("kcal", KCAL_PX), height: KCAL_PX + 2 }, pad: 5, min: 16, max: 44 });
  return (
    <figure className="m-0 w-full sm:w-[208px]">
      <div ref={box} data-ring-fit="calories" data-inner="62" className="relative mx-auto aspect-square w-full" style={{ maxWidth: size }} role="img" aria-label={summary}>
        <span aria-hidden className="pointer-events-none absolute inset-[14%] rounded-full opacity-25 blur-2xl" style={{ background: `radial-gradient(circle, ${C.gold}, transparent 70%)` }} />
        <svg viewBox="0 0 200 200" className="relative h-full w-full -rotate-90" aria-hidden>
          <circle cx="100" cy="100" r={R_RANGE} fill="none" stroke={C.grid} strokeWidth={W_RANGE} />
          <circle cx="100" cy="100" r={R_BURN} fill="none" stroke={C.grid} strokeWidth={W_BURN} />
          <circle cx="100" cy="100" r={R_EATEN} fill="none" stroke={C.grid} strokeWidth={W_EATEN} />
          {g.range && <Arc r={R_RANGE} from={g.range[0]} to={g.range[1]} color={C.gold} width={W_RANGE} cap="round" delay={0.9} opacity={0.55} />}
          <Arc r={R_BURN} from={g.resting[0]} to={g.resting[1]} color={C.amber} width={W_BURN} cap={g.active[1] > g.active[0] ? "butt" : "round"} />
          <Arc r={R_BURN} from={g.active[0]} to={g.active[1]} color={C.gold} width={W_BURN} cap="round" delay={0.25} />
          <Arc r={R_EATEN} from={0} to={g.eaten} color={C.sky} width={W_EATEN} cap="round" delay={0.4} />
        </svg>
        {/* Centre content sits in the hole only: the numeral (sized to fit) and a unit. Labels live outside the strokes. */}
        <div aria-hidden className="absolute inset-0 grid place-items-center text-center">
          <div className="flex flex-col items-center" style={{ gap: 3 }}>
            <p className="numeral whitespace-nowrap text-cream" style={{ fontSize: font }}>
              <CountUp value={burned} format={fmt} immediate />
            </p>
            <p className="whitespace-nowrap text-[11px] leading-[13px] text-mute">kcal</p>
          </div>
        </div>
      </div>
      <figcaption className="mt-3 flex flex-wrap items-center justify-center gap-x-1.5 gap-y-0.5 text-center text-[11px] leading-snug text-mute">
        <span aria-hidden className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-gold ${reduce ? "" : "motion-safe:animate-pulse"}`} />
        <span className="eyebrow !text-[11px] !tracking-[0.12em]">Burned so far</span>
        {asOf && <span>· {asOf}</span>}
      </figcaption>
    </figure>
  );
}
