// Time of day for the Home card. Pure; the caller passes minutes after local midnight (the server's clock for the user's timezone).
// The boundaries follow this user's routine (stated by them, not inferred): up by 06:00, first meal after 09:00, last meal before
// 20:00, bed between 21:20 and 22:00, a morning session and sometimes a second one in the evening. They are constants, not settings.
export type Moment = "morning" | "midday" | "afternoon" | "evening" | "night";

export const WAKE_START_MIN = 6 * 60;
export const WAKE_END_MIN = 21 * 60 + 20; // earliest bedtime: the waking day ends here
export const EAT_START_MIN = 9 * 60;
export const EAT_END_MIN = 20 * 60;

/** Morning is before the first meal window is well under way; evening starts when eating is done; night when bedtime opens. */
export function moment(min: number): Moment {
  if (min < 11 * 60) return "morning";
  if (min < 15 * 60) return "midday";
  if (min < EAT_END_MIN) return "afternoon";
  if (min < WAKE_END_MIN) return "evening";
  return "night";
}

const share = (min: number, from: number, to: number) => Math.max(0, Math.min(1, (min - from) / (to - from)));

/** Share of the waking day (06:00 to 21:20) that has passed, 0..1. */
export const dayShare = (min: number): number => share(min, WAKE_START_MIN, WAKE_END_MIN);

/** Share of the eating window (09:00 to 20:00) that has passed, 0..1: where intake would be at an even pace. */
export const eatShare = (min: number): number => share(min, EAT_START_MIN, EAT_END_MIN);

/** Minutes after midnight from "HH:MM" (the server's `now_local`), else the fallback. */
export function localMinutes(nowLocal: string | null | undefined, fallback: number): number {
  const m = /^(\d{1,2}):(\d{2})/.exec(nowLocal ?? "");
  if (!m) return fallback;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  return h >= 0 && h <= 23 && mi >= 0 && mi <= 59 ? h * 60 + mi : fallback;
}
