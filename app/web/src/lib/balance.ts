// Pure model for the Home "burned vs eaten" card, built for a cut. Both sides are estimates (Garmin burn and a food log), so the
// card shows them side by side on one scale and never calls a day good or bad. A day with nothing logged is unknown, not a zero
// intake: it is left out of the week instead of counting as a huge deficit.
import type { HomeEnergy } from "./types";

export const KCAL_PER_KG = 7700; // the usual rule of thumb for body fat; rough and only used for the week's "about"
export const MIN_WEEK_DAYS = 3; // settled days with both burn and a food log before a weekly total is shown
export const WEEK_DAYS = 7;

export interface TodayBars {
  burned: number;
  resting: number | null;
  active: number | null;
  eaten: number | null;
  /** Range of the food log (its own uncertainty), when sent. */
  eatenLow: number | null;
  eatenHigh: number | null;
  allowance: number | null;
  projected: { lo: number; hi: number } | null;
  /** Everything below is a 0..1 share of `scale`, the largest figure on screen. */
  scale: number;
  burnedFrac: number;
  restingFrac: number | null;
  eatenFrac: number | null;
  allowanceFrac: number | null;
  projLoFrac: number | null;
  projHiFrac: number | null;
  /** Burned so far minus eaten; positive is a deficit. Null with nothing logged. */
  gap: number | null;
}

const frac = (v: number | null | undefined, scale: number) => (v == null || !(v > 0) ? 0 : Math.min(1, v / scale));

export function todayBars(e: HomeEnergy, allowance: number | null, projected: { lo: number; hi: number } | null): TodayBars | null {
  const burned = e.burned?.total;
  if (burned == null || !(burned > 0)) return null;
  const eaten = e.eaten?.logged && e.eaten.kcal != null ? e.eaten.kcal : null;
  const scale = Math.max(burned, eaten ?? 0, allowance ?? 0, projected?.hi ?? 0, 1);
  const resting = e.burned?.resting ?? null;
  const active = e.burned?.active ?? null;
  const split = resting != null && active != null && resting >= 0 && active >= 0 && Math.abs(resting + active - burned) <= Math.max(5, burned * 0.02);
  return {
    burned, resting: split ? resting : null, active: split ? active : null, eaten,
    eatenLow: eaten != null ? e.eaten?.kcal_low ?? null : null, eatenHigh: eaten != null ? e.eaten?.kcal_high ?? null : null,
    allowance, projected, scale,
    burnedFrac: frac(burned, scale), restingFrac: split ? frac(resting, scale) : null, eatenFrac: eaten != null ? frac(eaten, scale) : null,
    allowanceFrac: allowance ? frac(allowance, scale) : null,
    projLoFrac: projected ? frac(projected.lo, scale) : null, projHiFrac: projected ? frac(projected.hi, scale) : null,
    gap: eaten != null ? Math.round(burned - eaten) : null,
  };
}

export interface WeekDay {
  day: string;
  /** Burned minus eaten for the day; positive is a deficit. Null when either side is unknown. */
  deficit: number | null;
  reason: "ok" | "no_burn" | "no_log";
}

export interface WeekBalance {
  days: WeekDay[];
  counted: number;
  /** Null until MIN_WEEK_DAYS days have both sides. */
  total: number | null;
  average: number | null;
  /** Rough fat-mass equivalent of `total`, in kg; null with `total`. */
  kg: number | null;
  /** Largest absolute daily gap, for scaling the bars. */
  maxAbs: number;
}

/** The last WEEK_DAYS settled days before `today` from the overview's spark series. Partial days (still being counted) are not used. */
export function weekBalance(spark: NonNullable<HomeEnergy["spark"]> | undefined, today: string): WeekBalance | null {
  const rows = (spark ?? []).filter((d) => d.day < today).sort((a, b) => a.day.localeCompare(b.day)).slice(-WEEK_DAYS);
  if (rows.length === 0) return null;
  const days: WeekDay[] = rows.map((d) => {
    if (d.total == null || d.partial || !(d.total > 0)) return { day: d.day, deficit: null, reason: "no_burn" };
    if (d.eaten == null || !(d.eaten > 0)) return { day: d.day, deficit: null, reason: "no_log" };
    return { day: d.day, deficit: Math.round(d.total - d.eaten), reason: "ok" };
  });
  const known = days.filter((d) => d.deficit != null) as (WeekDay & { deficit: number })[];
  const enough = known.length >= MIN_WEEK_DAYS;
  const total = enough ? known.reduce((s, d) => s + d.deficit, 0) : null;
  return {
    days, counted: known.length, total,
    average: total != null ? Math.round(total / known.length) : null,
    kg: total != null ? Math.round((total / KCAL_PER_KG) * 100) / 100 : null,
    maxAbs: Math.max(1, ...known.map((d) => Math.abs(d.deficit))),
  };
}
