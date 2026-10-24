import type { FoodDaySummary } from "./types";

export const MEALS = [
  { value: "breakfast", label: "Breakfast" },
  { value: "lunch", label: "Lunch" },
  { value: "snack", label: "Snacks" },
  { value: "dinner", label: "Dinner" },
] as const;

/** Moves a YYYY-MM-DD day by whole days without touching time zones. */
export function shiftDay(day: string, delta: number): string {
  const [y, m, d] = day.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + delta));
  return dt.toISOString().slice(0, 10);
}

/** "1,850–2,450 kcal": a range, because home-cooked portions are never exact. */
export function kcalRange(s: Pick<FoodDaySummary, "kcal_low" | "kcal_high">): string | null {
  if (s.kcal_low == null || s.kcal_high == null) return null;
  const f = (n: number) => Math.round(n).toLocaleString("en-US");
  return `${f(s.kcal_low)}–${f(s.kcal_high)}`;
}

/** Where protein per kg sits against the cited reference range; wording stays descriptive, never advice. */
export function proteinPosition(perKg: number | null, ref: [number, number]): "below" | "within" | "above" | null {
  if (perKg == null) return null;
  if (perKg < ref[0]) return "below";
  return perKg > ref[1] ? "above" : "within";
}

/** Quantities in servings read better as "1½" than "1.5". */
export function servingsLabel(n: number): string {
  const whole = Math.floor(n);
  const frac = n - whole;
  const glyph = Math.abs(frac - 0.5) < 0.01 ? "½" : Math.abs(frac - 0.25) < 0.01 ? "¼" : Math.abs(frac - 0.75) < 0.01 ? "¾" : null;
  if (glyph) return whole === 0 ? glyph : `${whole}${glyph}`;
  return String(Math.round(n * 100) / 100);
}
