import type { GoalSport, GoalView } from "./types";

/** h:mm:ss, or m:ss under an hour. */
export function clockTime(seconds: number): string {
  const r = Math.round(seconds);
  const h = Math.floor(r / 3600);
  return `${h ? `${h}:` : ""}${String(Math.floor((r % 3600) / 60)).padStart(h ? 2 : 1, "0")}:${String(r % 60).padStart(2, "0")}`;
}

/**
 * Digits typed on a phone's number pad (no colon key) as a time, filled from the right like a timer:
 * "45" is 0:45, "345" is 3:45, "3450" is 34:50, "34500" is 3:45:00. Already-formatted text with colons (a pasted "3:45:00",
 * a hardware keyboard) is kept as typed. At most six digits (hh:mm:ss, up to 99 h).
 */
export function formatTimeDigits(raw: string): string {
  const d = raw.replace(/\D/g, "").replace(/^0+(?=\d)/, "").slice(-6);
  if (!d) return "";
  const p = d.padStart(d.length <= 2 ? 3 : d.length <= 4 ? 4 : 6, "0");
  const ss = p.slice(-2);
  const mm = p.slice(-4, -2);
  const hh = p.slice(0, -4);
  const text = hh ? `${Number(hh)}:${mm}:${ss}` : `${Number(mm)}:${ss}`;
  return text;
}

const FASTEST_M_PER_S: Record<string, number> = { run: 9, ride: 20, swim: 3 };

/**
 * "mm:ss", "h:mm:ss" or "h:mm" → seconds; null when it isn't a time. Two parts are ambiguous, so when the distance is known
 * "3:45" for a marathon is read as 3 h 45 min (as 3 min 45 s it would be faster than anyone can run), while "25:00" for a 5 km
 * stays 25 minutes. Without a distance two parts are mm:ss.
 */
export function parseTime(text: string, metres?: number, sport: string = "run"): number | null {
  const parts = text.trim().split(":").map(Number);
  if (!text.trim() || parts.some((n) => !Number.isFinite(n) || n < 0) || parts.length < 2 || parts.length > 3) return null;
  const minSec = parts.reduce((acc, n) => acc * 60 + n, 0);
  if (parts.length === 3 || !metres || !(minSec > 0)) return minSec;
  const fastest = FASTEST_M_PER_S[sport] ?? 9;
  return metres / minSec > fastest ? parts[0] * 3600 + parts[1] * 60 : minSec;
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
