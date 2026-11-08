/**
 * Motion tokens and pure helpers, the one place the app's animation numbers live (docs/ui-system.md, "Motion").
 * CSS twins: --ease-snap / --ease-spring / --ease-out-expo, `.stagger`, `.fade-in`, `.press`, `.ring-halo` in index.css.
 * Rules: animate only transform and opacity; calm and short; never required to understand content; honour reduced motion.
 */

export const EASE = {
  snap: [0.2, 0.9, 0.1, 1] as [number, number, number, number],
  outExpo: [0.16, 1, 0.3, 1] as [number, number, number, number],
  spring: [0.34, 1.56, 0.64, 1] as [number, number, number, number],
};

/** Seconds. press 80 to 220ms, route 280ms, reveals 450 to 600ms, rings 1.1 to 1.4s. */
export const DUR = { press: 0.18, route: 0.28, reveal: 0.5, ring: 1.2, chart: 0.7 };

/** The shared spring for shared-layout morphs (tab pill, segmented thumb), so every selector moves the same way. */
export const MORPH_SPRING = { type: "spring" as const, stiffness: 520, damping: 38 };
export const SHEET_SPRING = { type: "spring" as const, stiffness: 340, damping: 34, mass: 0.9 };

/** Stagger delay in seconds for item `index`: `step` apart, capped so a long list never waits more than `cap * step`. */
export function staggerDelay(index: number, step = 0.045, cap = 8): number {
  return Math.min(Math.max(0, index), cap) * step;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// ---- route transitions ---------------------------------------------------------------------

/** Top-level destinations in tab order; moving along it slides left or right. Anything else counts as deeper (forward) or shallower (back). */
const TAB_ORDER = ["/", "/coach", "/plan", "/weight", "/activities", "/settings"];

function tabIndex(path: string): number {
  if (path === "/") return 0;
  return TAB_ORDER.findIndex((t, i) => i > 0 && (path === t || path.startsWith(`${t}/`)));
}

const segments = (path: string) => path.split("/").filter(Boolean).length;

/** +1 slide in from the right (forward / deeper), -1 from the left (back), 0 fade only (first load or the same page). */
export function routeDirection(from: string | null, to: string): -1 | 0 | 1 {
  if (from == null || from === to) return 0;
  const a = tabIndex(from);
  const b = tabIndex(to);
  if (a >= 0 && b >= 0 && a !== b) return b > a ? 1 : -1;
  if (a === b && a >= 0) return segments(to) >= segments(from) ? 1 : -1;
  return segments(to) >= segments(from) ? 1 : -1;
}

/** Short fade plus a small slide; with reduced motion only a fade-less instant swap (no offsets, zero duration). */
export function routeMotion(direction: -1 | 0 | 1, reduce: boolean) {
  if (reduce) return { initial: { opacity: 1, x: 0 }, animate: { opacity: 1, x: 0 }, transition: { duration: 0 } };
  const x = direction * 16;
  return {
    initial: { opacity: 0, x, y: direction === 0 ? 8 : 0 },
    animate: { opacity: 1, x: 0, y: 0 },
    transition: { duration: DUR.route, ease: EASE.outExpo },
  };
}

// ---- charts -------------------------------------------------------------------------------

/**
 * ECharts animation settings: a short eased draw-in the first time a chart is painted, and no animation on later updates
 * (refetches, resizes, range changes), which would replay the entrance and feel like flicker.
 */
export function chartAnimation(first: boolean, reduce: boolean, userAnimation?: boolean) {
  const on = first && !reduce && userAnimation !== false;
  return {
    animation: on,
    animationDuration: on ? Math.round(DUR.chart * 1000) : 0,
    animationDurationUpdate: 0,
    animationEasing: "cubicOut" as const,
  };
}

// ---- celebration --------------------------------------------------------------------------

/** True when `day` (YYYY-MM-DD) is within `days` days before `now`: a result worth a one-off halo, not an old one. */
export function isFreshDay(day: string | null | undefined, now: Date = new Date(), days = 7): boolean {
  if (!day) return false;
  const t = Date.parse(`${day}T12:00:00`);
  if (!Number.isFinite(t)) return false;
  const age = (now.getTime() - t) / 86_400_000;
  return age >= -1 && age <= days;
}
