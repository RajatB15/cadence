// The living theme's pure rules: which part of the day the sky is in, whether the clock says light or dark, and the mood a day phase gives.
// The same rules are repeated in the inline script in index.html (so the first paint is right); keep the two in step.
// Only ambient tints change with the sky and the mood. Text and surface colours come from the light or dark tokens alone, so contrast never moves.
import type { Theme } from "./theme";

export type SkyStage = "night" | "dawn" | "morning" | "day" | "golden" | "dusk";
export type Mood = "none" | "afterglow" | "electric" | "calm" | "sage";

/** Minutes after local midnight to the stage of the sky: 05:00 dawn, 07:00 morning, 11:00 day, 16:00 golden hour, 18:30 dusk, 20:30 night. */
export function skyStage(min: number): SkyStage {
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  if (m < 5 * 60) return "night";
  if (m < 7 * 60) return "dawn";
  if (m < 11 * 60) return "morning";
  if (m < 16 * 60) return "day";
  if (m < 18 * 60 + 30) return "golden";
  if (m < 20 * 60 + 30) return "dusk";
  return "night";
}

/** The page is light in daylight and dark otherwise (06:30 to 18:30). */
export function autoTheme(min: number): Theme {
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  return m >= 6 * 60 + 30 && m < 18 * 60 + 30 ? "light" : "dark";
}

/** The backend names the day phase; some phases have a mood. Anything else (or an older server) is no mood. */
export function moodFor(phase: string | null | undefined): Mood {
  switch (phase) {
    case "post_workout": return "afterglow";
    case "race_week":
    case "race_day": return "electric";
    case "sick":
    case "time_off": return "calm";
    case "rest_day": return "sage";
    default: return "none";
  }
}

export const minutesOf = (d: Date = new Date()) => d.getHours() * 60 + d.getMinutes();

/** Seconds per heartbeat for the decorative pulse, from a resting heart rate; null when the rate is unknown or implausible. */
export function beatSeconds(bpm: number | null | undefined): number | null {
  if (bpm == null || !Number.isFinite(bpm) || bpm < 30 || bpm > 120) return null;
  return Math.round((60 / bpm) * 1000) / 1000;
}
