import type { GoalSport, GoalView } from "./types";

/** h:mm:ss, or m:ss under an hour. */
export function clockTime(seconds: number): string {
  const r = Math.round(seconds);
  const h = Math.floor(r / 3600);
  return `${h ? `${h}:` : ""}${String(Math.floor((r % 3600) / 60)).padStart(h ? 2 : 1, "0")}:${String(r % 60).padStart(2, "0")}`;
}

/** "mm:ss" or "h:mm:ss" → seconds; null when it isn't a time. */
export function parseTime(text: string): number | null {
  const parts = text.trim().split(":").map(Number);
  if (!text.trim() || parts.some((n) => !Number.isFinite(n) || n < 0) || parts.length < 2 || parts.length > 3) return null;
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

export function distanceLabel(metres: number): string {
  return metres < 1000 ? `${Math.round(metres)} m` : `${+(metres / 1000).toFixed(1)} km`;
}

/** Pace for the sport: km/h for rides, per 100 m for swims, per km for runs. */
export function pacePer(sport: GoalSport | null, metres: number, seconds: number): string {
  if (sport === "ride") return `${((metres / seconds) * 3.6).toFixed(1)} km/h`;
  const per = sport === "swim" ? 100 : 1000;
  const s = Math.round((seconds / metres) * per);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}/${sport === "swim" ? "100 m" : "km"}`;
}

export function signed(v: number, digits = 1): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}`;
}

export function countdown(g: Pick<GoalView, "days_left">): string | null {
  const d = g.days_left;
  if (d == null) return null;
  if (d < 0) return `${-d} days ago`;
  if (d === 0) return "today";
  return d < 14 ? `in ${d} days` : `in ${Math.round(d / 7)} weeks`;
}
