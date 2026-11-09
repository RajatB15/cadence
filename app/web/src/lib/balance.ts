// Pure model for the Home "burned vs eaten" card, built for a cut. Both sides are estimates (Garmin burn and a food log), so the
// card shows them side by side on one scale and never calls a day good or bad. A day with nothing logged is unknown, not a zero
// intake: it is left out of the week instead of counting as a huge deficit.
import { dayShare, eatShare, moment } from "./moment";
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

// ---- what the card says at this time of day ----------------------------------------------------------------------------------

export type BalanceMode = "budget" | "pace" | "result";

export interface BalanceView {
  mode: BalanceMode;
  /** The burned bar is hidden in the morning: burn so far is only a few hours of the day and says nothing about balance. */
  showBurned: boolean;
  headline: { kind: "left" | "over" | "budget" | "deficit" | "surplus" | "eaten" | "burned"; label: string; value: number; sub: string | null };
  /** Where eaten would sit at an even pace through the eating window, 09:00 to 20:00 (midday and afternoon). */
  paceFrac: number | null;
  /** Deficit if nothing more is eaten, from the projected burn range (evening). */
  ifStopped: [number, number] | null;
  /** Yesterday's settled balance, shown in the morning when both sides are known. */
  yesterday: number | null;
}

/** Share of the day's burn already spent: from the projection when there is one, else the share of the waking day. */
export function burnShare(bars: TodayBars, min: number): number {
  const total = bars.projected ? (bars.projected.lo + bars.projected.hi) / 2 : null;
  return total && total > 0 ? Math.max(0, Math.min(1, bars.burned / total)) : dayShare(min);
}

/**
 * Burned minus eaten only means something once most of the day has been burned: at 08:00 it is nearly all "not eaten yet".
 * So the morning shows the budget and what is left, midday and afternoon add a pace marker, and once eating is done (20:00) the
 * evening shows the balance itself.
 */
export function balanceView(e: HomeEnergy, bars: TodayBars, min: number): BalanceView {
  const share = burnShare(bars, min);
  const m = moment(min);
  // The eating window closes at 20:00, so the balance is only the answer after that; until then it is a budget with a pace.
  const mode: BalanceMode = m === "morning" || share < 0.4 ? "budget" : m === "midday" || m === "afternoon" ? "pace" : "result";
  const y = e.yesterday;
  const yesterday = y && y.total != null && y.total > 0 && y.eaten != null && y.eaten > 0 ? Math.round(y.total - y.eaten) : null;
  const allowance = bars.allowance;
  let headline: BalanceView["headline"];
  if (mode === "result" && bars.gap != null) {
    headline = bars.gap >= 0
      ? { kind: "deficit", label: m === "night" ? "Deficit today" : "Deficit so far", value: bars.gap, sub: `${fmt(bars.burned)} burned − ${fmt(bars.eaten!)} eaten` }
      : { kind: "surplus", label: m === "night" ? "Surplus today" : "Eaten more than burned so far", value: -bars.gap, sub: `${fmt(bars.eaten!)} eaten − ${fmt(bars.burned)} burned` };
  } else if (allowance != null && bars.eaten != null) {
    const left = Math.round(allowance - bars.eaten);
    headline = left >= 0
      ? { kind: "left", label: "Left to eat", value: left, sub: `${fmt(bars.eaten)} of ${fmt(allowance)} so far` }
      : { kind: "over", label: "Over today's target by", value: -left, sub: `${fmt(bars.eaten)} of ${fmt(allowance)}` };
  } else if (allowance != null) {
    headline = { kind: "budget", label: "Your budget today", value: allowance, sub: "Nothing logged yet" };
  } else if (bars.eaten != null) {
    headline = { kind: "eaten", label: "Eaten so far", value: bars.eaten, sub: "No target set" };
  } else {
    headline = { kind: "burned", label: "Burned so far", value: bars.burned, sub: "Log what you eat to see the balance" };
  }
  if (mode === "pace" && bars.gap != null) headline = { ...headline, sub: `${headline.sub ? headline.sub + " · " : ""}deficit so far ${fmt(Math.max(0, bars.gap))} builds through the day` };
  return {
    mode,
    showBurned: mode !== "budget",
    headline,
    paceFrac: mode === "pace" && allowance ? Math.min(1, (allowance * eatShare(min)) / bars.scale) : null,
    ifStopped: mode === "result" && bars.projected && bars.eaten != null ? [Math.round(bars.projected.lo - bars.eaten), Math.round(bars.projected.hi - bars.eaten)] : null,
    yesterday,
  };
}

const fmt = (n: number) => Math.round(n).toLocaleString();
