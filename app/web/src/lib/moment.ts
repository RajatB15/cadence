// Time of day for the Home card. Pure; the caller passes minutes after local midnight (the server's clock for the user's timezone).
// Boundaries are plain defaults, not physiology: a day is "waking" from 06:00 to 22:00 for pacing, and the card changes its
// wording at 11:00, 17:00 and 21:30.
export type Moment = "morning" | "midday" | "evening" | "night";

export const WAKE_START_MIN = 6 * 60;
export const WAKE_END_MIN = 22 * 60;

export function moment(min: number): Moment {
  if (min < 11 * 60) return "morning";
  if (min < 17 * 60) return "midday";
  if (min < 21 * 60 + 30) return "evening";
  return "night";
}

/** Share of the waking day (06:00 to 22:00) that has passed, 0..1. */
export function dayShare(min: number): number {
  return Math.max(0, Math.min(1, (min - WAKE_START_MIN) / (WAKE_END_MIN - WAKE_START_MIN)));
}

/** Minutes after midnight from "HH:MM" (the server's `now_local`), else the fallback. */
export function localMinutes(nowLocal: string | null | undefined, fallback: number): number {
  const m = /^(\d{1,2}):(\d{2})/.exec(nowLocal ?? "");
  if (!m) return fallback;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  return h >= 0 && h <= 23 && mi >= 0 && mi <= 59 ? h * 60 + mi : fallback;
}
