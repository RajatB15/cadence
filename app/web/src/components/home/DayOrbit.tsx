import { motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";
import { orbitModel, orbitPath, orbitPoint, type OrbitInput, type OrbitKind } from "../../lib/orbit";
import { skyStage } from "../../lib/sky";

const R = 118; // the main ring
const CX = 150;
const CY = 150;
const ARC_COLOR: Record<OrbitKind, string> = { sleep: "var(--color-violet)", session: "var(--color-lime)", planned: "var(--color-gold)", eat: "var(--color-sky)" };
const RING_OF: Record<OrbitKind, number> = { sleep: R - 14, session: R - 14, planned: R - 14, eat: R + 14 };
const SKY_STOPS: { from: number; to: number; stage: "night" | "dawn" | "morning" | "day" | "golden" | "dusk" }[] = [
  { from: 0, to: 300, stage: "night" }, { from: 300, to: 420, stage: "dawn" }, { from: 420, to: 660, stage: "morning" }, { from: 660, to: 960, stage: "day" },
  { from: 960, to: 1110, stage: "golden" }, { from: 1110, to: 1230, stage: "dusk" }, { from: 1230, to: 1440, stage: "night" },
];
const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(Math.round(m % 60)).padStart(2, "0")}`;

/**
 * The day as a ring you can read at a glance: the sky's colours around the edge, last night's sleep, today's sessions and the usual
 * eating window as arcs, a sun (or moon) that is where you are in the day, and what comes next in the middle. Built only from what
 * is known: an arc without data is simply not drawn.
 */
export function DayOrbit({ input, children }: { input: OrbitInput; children?: React.ReactNode }) {
  const reduce = useReducedMotion();
  const m = useMemo(() => orbitModel(input), [input]);
  const night = skyStage(m.now) === "night";
  const sun = orbitPoint(CX, CY, R, m.now);
  const bed = m.bed != null ? orbitPoint(CX, CY, R, m.bed) : null;
  const summary = [`It is ${hhmm(m.now)}.`, ...m.arcs.filter((a) => a.kind !== "eat").map((a) => a.label), m.next ? `${m.next.label} ${hhmm(m.next.at)}.` : ""].filter(Boolean).join(" ");
  return (
    <div className="relative mx-auto w-full max-w-[340px]" role="img" aria-label={summary}>
      <svg viewBox="0 0 300 300" className="block h-auto w-full overflow-visible" aria-hidden>
        <defs>
          <radialGradient id="orbit-sun" cx="50%" cy="50%" r="50%"><stop offset="0" stopColor="#fff" stopOpacity="0.95" /><stop offset="0.35" stopColor={night ? "#c7d2fe" : "#ffd27a"} stopOpacity="0.9" /><stop offset="1" stopColor={night ? "#818cf8" : "#ff8a3d"} stopOpacity="0" /></radialGradient>
        </defs>
        {/* the sky around the day: each stretch of the 24 hours in its own colour */}
        {SKY_STOPS.map((s) => (
          <path key={`${s.stage}${s.from}`} d={orbitPath(CX, CY, R, s.from, s.to)} fill="none" strokeWidth="9" strokeLinecap="butt" style={{ stroke: `var(--orbit-${s.stage})` }} opacity="0.85" />
        ))}
        {/* hour ticks */}
        {[0, 6, 12, 18].map((h) => { const a = orbitPoint(CX, CY, R + 8, h * 60); const b = orbitPoint(CX, CY, R + 16, h * 60); return <line key={h} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--color-dim)" strokeWidth="1.5" />; })}
        {[["00", 0, 1], ["06", 6, 0], ["12", 12, -1], ["18", 18, 0]].map(([t, h]) => { const p = orbitPoint(CX, CY, R + 29, (h as number) * 60); return <text key={t as string} x={p.x} y={p.y + 4} textAnchor="middle" fontSize="10" fontWeight="700" fill="var(--color-dim)" style={{ letterSpacing: "0.1em" }}>{t}</text>; })}
        {/* what is known about the day */}
        {m.arcs.map((a, i) => (
          <motion.path
            key={`${a.kind}${a.from}${i}`}
            d={orbitPath(CX, CY, RING_OF[a.kind], a.from, a.to)}
            fill="none"
            stroke={ARC_COLOR[a.kind]}
            strokeWidth={a.kind === "eat" ? 4 : 11}
            strokeLinecap="round"
            strokeDasharray={a.dashed ? "2 9" : undefined}
            opacity={a.kind === "eat" ? 0.55 : 1}
            initial={reduce ? false : { pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: a.kind === "eat" ? 0.55 : 1 }}
            transition={{ duration: reduce ? 0 : 1.4, delay: reduce ? 0 : 0.15 * i, ease: [0.16, 1, 0.3, 1] }}
          >
            <title>{a.label}</title>
          </motion.path>
        ))}
        {bed && <circle cx={bed.x} cy={bed.y} r="5" fill="var(--color-violet)" stroke="var(--color-coal)" strokeWidth="2"><title>{`In bed by ${hhmm(m.bed!)}`}</title></circle>}
        {/* where you are in the day */}
        <g transform={`translate(${sun.x} ${sun.y})`}>
          <circle r="30" fill="url(#orbit-sun)" className="orbit-sun" />
          <circle r="7" fill={night ? "#e0e7ff" : "#fff7e0"} />
        </g>
      </svg>
      <div className="absolute inset-0 grid place-items-center px-14 text-center">
        <div>
          {children ?? (
            <>
              <p className="eyebrow !text-[11px]">{m.next ? m.next.label : "Now"}</p>
              <p className="poster mt-1 text-[clamp(44px,15vw,64px)]">{hhmm(m.next ? m.next.at : m.now)}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
