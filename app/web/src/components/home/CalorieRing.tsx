import { motion, useReducedMotion } from "motion/react";
import { useCallback } from "react";
import { CountUp } from "../CountUp";
import { circumference, ringGeometry } from "../../lib/home";
import { C } from "../../lib/theme";

interface Props {
  burned: number;
  active: number | null;
  resting: number | null;
  eaten: number | null;
  target: number | null;
  projected: { lo: number; hi: number } | null;
  asOf: string | null;
  size?: number;
  /** One text sentence for screen readers, built by the caller from the same numbers. */
  summary: string;
}

const R_RANGE = 93;
const R_BURN = 76;
const R_EATEN = 58;

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
export function CalorieRing({ burned, active, resting, eaten, target, projected, asOf, size = 176, summary }: Props) {
  const reduce = useReducedMotion();
  const g = ringGeometry({ burned, active, resting, projected, eaten, target });
  const fmt = useCallback((v: number) => Math.round(v).toLocaleString(), []);
  return (
    <div className="relative mx-auto shrink-0" style={{ width: size, height: size }} role="img" aria-label={summary}>
      <span aria-hidden className="pointer-events-none absolute inset-[10%] rounded-full opacity-40 blur-2xl" style={{ background: `radial-gradient(circle, ${C.gold}, transparent 70%)` }} />
      <svg viewBox="0 0 200 200" className="relative h-full w-full -rotate-90" aria-hidden>
        <circle cx="100" cy="100" r={R_RANGE} fill="none" stroke={C.grid} strokeWidth="5" />
        <circle cx="100" cy="100" r={R_BURN} fill="none" stroke={C.grid} strokeWidth="15" />
        <circle cx="100" cy="100" r={R_EATEN} fill="none" stroke={C.grid} strokeWidth="9" />
        {g.range && <Arc r={R_RANGE} from={g.range[0]} to={g.range[1]} color={C.gold} width={5} cap="round" delay={0.9} opacity={0.55} />}
        <Arc r={R_BURN} from={g.resting[0]} to={g.resting[1]} color={C.amber} width={15} cap={g.active[1] > g.active[0] ? "butt" : "round"} />
        <Arc r={R_BURN} from={g.active[0]} to={g.active[1]} color={C.gold} width={15} cap="round" delay={0.25} />
        <Arc r={R_EATEN} from={0} to={g.eaten} color={C.sky} width={9} cap="round" delay={0.4} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <p className="eyebrow !text-[11px]">Burned so far</p>
          <p className="num leading-none text-cream" style={{ fontSize: size * 0.24 }}>
            <CountUp value={burned} format={fmt} immediate />
          </p>
          <p className="mt-1 flex items-center justify-center gap-1.5 text-[11px] text-mute">
            <span aria-hidden className={`inline-block h-1.5 w-1.5 rounded-full bg-gold ${reduce ? "" : "motion-safe:animate-pulse"}`} />
            kcal{asOf ? ` · ${asOf}` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}
