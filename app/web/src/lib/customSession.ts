import type { Sport } from "./types";

export type CustomSport = Exclude<Sport, "strength">;
export type Effort = "easy" | "moderate" | "hard";
export interface CustomSpec { distance_m?: number; minutes?: number; speed_mps?: number; effort?: Effort }
export interface CustomFields { distance: string; pace: string; minutes: string; effort: Effort | "auto" }

/** Typed units per sport: distance in km (swim: m), pace as m:ss per km / per 100 m, ride as km/h. */
export const UNITS: Record<CustomSport, { distance: string; pace: string; paceHint: string; metresPerPace: number | null }> = {
  run: { distance: "km", pace: "Pace (min/km)", paceHint: "5:30", metresPerPace: 1000 },
  ride: { distance: "km", pace: "Speed (km/h)", paceHint: "28", metresPerPace: null },
  swim: { distance: "m", pace: "Pace (min/100 m)", paceHint: "2:00", metresPerPace: 100 },
};

function positive(text: string): number | null {
  const v = Number(text.replace(",", "."));
  return text.trim() !== "" && Number.isFinite(v) && v > 0 ? v : null;
}

/** "5:30" → 330 seconds; plain numbers are minutes. */
export function parsePace(text: string): number | null {
  const m = text.trim().match(/^(\d+):([0-5]\d)$/);
  if (m) return Number(m[1]) * 60 + Number(m[2]);
  const v = positive(text);
  return v == null ? null : v * 60;
}

/** The request for what's typed, or null until two of distance, time and pace are valid. */
export function toSpec(sport: CustomSport, f: CustomFields): CustomSpec | null {
  const d = positive(f.distance);
  const minutes = positive(f.minutes);
  let speed: number | null = null;
  if (sport === "ride") {
    const kmh = positive(f.pace);
    speed = kmh == null ? null : kmh / 3.6;
  } else {
    const sec = parsePace(f.pace);
    speed = sec == null ? null : (UNITS[sport].metresPerPace as number) / sec;
  }
  const distance_m = d == null ? null : sport === "swim" ? d : d * 1000;
  // With distance and time given, speed follows from them (the server does the same), so pace is dropped.
  const given = [distance_m, minutes, speed].filter((v) => v != null).length;
  if (given < 2) return null;
  const spec: CustomSpec = {};
  if (distance_m != null) spec.distance_m = distance_m;
  if (minutes != null) spec.minutes = minutes;
  if (speed != null && !(distance_m != null && minutes != null)) spec.speed_mps = speed;
  if (f.effort !== "auto") spec.effort = f.effort;
  return spec;
}

export const hourLabel = (h: number) => `${String(h).padStart(2, "0")}:00`;
