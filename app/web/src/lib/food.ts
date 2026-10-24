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

export const SOURCE_NOTE: Record<string, string> = {
  library: "the food library",
  mine: "Your own dish",
};

export const BASIS_NOTE: Record<string, string> = {
  library: "Calculated from a recipe, not lab-measured",
  estimate: "Your own estimate",
};

export const MAX_SEARCH_RESULTS = 60;
export const COMMON_COUNT = 40;

interface Searchable {
  id: number;
  name: string;
  source: string;
  aliases?: string[];
}

/** The short list before you type: recent dishes, your own, then the most basic-looking foods (shortest names). Search reaches everything. */
export function browseList<T extends Searchable>(all: T[], recentIds: number[]): T[] {
  const recent = recentIds.map((id) => all.find((d) => d.id === id)).filter((d): d is T => d != null);
  const used = new Set(recent.map((d) => d.id));
  const mine = all.filter((d) => d.source === "mine" && !used.has(d.id));
  mine.forEach((d) => used.add(d.id));
  const common = all
    .filter((d) => d.source !== "mine" && !used.has(d.id))
    .sort((a, b) => a.name.length - b.name.length || a.name.localeCompare(b.name))
    .slice(0, COMMON_COUNT);
  return [...recent, ...mine, ...common];
}

/** Search every dish by name or alias: names starting with the text first, then names containing it, then aliases. Capped for the phone. */
export function searchList<T extends Searchable>(all: T[], query: string): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const starts: T[] = [];
  const contains: T[] = [];
  const viaAlias: T[] = [];
  for (const d of all) {
    const n = d.name.toLowerCase();
    if (n.startsWith(q)) starts.push(d);
    else if (n.includes(q)) contains.push(d);
    else if (d.aliases?.some((a) => a.toLowerCase().includes(q))) viaAlias.push(d);
  }
  return [...starts, ...contains, ...viaAlias].slice(0, MAX_SEARCH_RESULTS);
}

export type PortionMode = "servings" | "grams";

interface PortionDish {
  kcal: number;
  protein_g: number;
  unit_g: number | null;
  per_100g: { kcal: number; protein_g: number } | null;
}

/** What a portion adds up to. Grams use the per-100 g values, servings the per-serving ones; both agree by construction. */
export function portionPreview(dish: PortionDish, mode: PortionMode, amount: number): { kcal: number; protein_g: number; grams: number | null } {
  if (mode === "grams" && dish.per_100g) {
    return { kcal: (dish.per_100g.kcal * amount) / 100, protein_g: (dish.per_100g.protein_g * amount) / 100, grams: amount };
  }
  return { kcal: dish.kcal * amount, protein_g: dish.protein_g * amount, grams: dish.unit_g ? dish.unit_g * amount : null };
}
