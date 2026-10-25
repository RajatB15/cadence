import type { FoodDaySummary, FoodEntry, FoodMicro, Meal } from "./types";

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
  library: "Food library",
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
  const aliasStarts: T[] = [];
  const viaAlias: T[] = [];
  for (const d of all) {
    const n = d.name.toLowerCase();
    if (n.startsWith(q)) starts.push(d);
    else if (n.includes(q)) contains.push(d);
    else if (d.aliases?.some((a) => a.toLowerCase().startsWith(q))) aliasStarts.push(d);
    else if (d.aliases?.some((a) => a.toLowerCase().includes(q))) viaAlias.push(d);
  }
  return [...starts, ...contains, ...aliasStarts, ...viaAlias].slice(0, MAX_SEARCH_RESULTS);
}

/** The other name a search matched, when the dish's own name did not match: shown so "Rotli" visibly leads to "Roti". */
export function matchedAlias(d: Searchable, query: string): string | null {
  const q = query.trim().toLowerCase();
  if (!q || d.name.toLowerCase().includes(q)) return null;
  const hits = (d.aliases ?? []).filter((a) => a.toLowerCase().includes(q));
  return hits.find((a) => a.toLowerCase().startsWith(q)) ?? hits[0] ?? null;
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

export const PHASE_LABEL: Record<string, string> = { cut: "Cutting", gain: "Gaining", maintain: "Maintaining" };

/** Positions (0-100) of a target band and a logged range on one shared scale, so a bar can show them together. */
export function bandPositions(
  target: [number, number] | null,
  logged: [number, number] | null,
  point: number | null,
): { max: number; target: [number, number] | null; logged: [number, number] | null; point: number | null } {
  const top = Math.max(target?.[1] ?? 0, logged?.[1] ?? 0, point ?? 0);
  const max = Math.max(1, top * 1.15);
  const pct = (v: number) => Math.min(100, Math.max(0, (v / max) * 100));
  return {
    max,
    target: target ? [pct(target[0]), pct(target[1])] : null,
    logged: logged ? [pct(logged[0]), pct(logged[1])] : null,
    point: point == null ? null : pct(point),
  };
}

export type DayState = "not_logged" | "no_target" | "under" | "within" | "over";

/** Colour for a day against the target band; unknown stays neutral rather than looking like zero. */
export const STATE_COLOR: Record<DayState, string> = {
  within: "#c8f560",
  under: "#6cc7ff",
  over: "#ffbe55",
  no_target: "#d9b26a",
  not_logged: "#5c5a55",
};

/** The same ranged comparison the server uses, so each day in the week chart can be coloured on its own. */
export function stateFor(day: { logged: boolean; kcal_low: number | null; kcal_high: number | null }, target: [number, number] | null): DayState {
  if (!day.logged || day.kcal_low == null || day.kcal_high == null) return "not_logged";
  if (!target) return "no_target";
  return day.kcal_high < target[0] ? "under" : day.kcal_low > target[1] ? "over" : "within";
}

/** Share of the day's calories from protein, carbohydrate and fat (4/4/9 kcal per gram), or null unless all three are known. */
export function macroSplit(s: Pick<FoodDaySummary, "protein_g" | "carbs_g" | "fat_g" | "partial_macros">): { protein: number; carbs: number; fat: number } | null {
  if (s.protein_g == null || s.carbs_g == null || s.fat_g == null || s.partial_macros) return null;
  const p = s.protein_g * 4, c = s.carbs_g * 4, f = s.fat_g * 9;
  const total = p + c + f;
  if (total <= 0) return null;
  const pct = (v: number) => Math.round((v / total) * 100);
  const protein = pct(p), carbs = pct(c);
  return { protein, carbs, fat: Math.max(0, 100 - protein - carbs) };
}

export type MicroState = "unknown" | "partial" | "reached" | "building" | "under" | "over" | "no_reference";

/** How a nutrient reads against its reference: limits go "over", targets "reached"; foods missing the value make it partial, never zero. */
export function microState(m: FoodMicro): MicroState {
  if (m.amount == null) return "unknown";
  if (m.reference == null || m.pct == null) return m.foods_with < m.foods ? "partial" : "no_reference";
  if (m.kind === "limit") return m.pct > 100 ? "over" : m.foods_with < m.foods ? "partial" : "under";
  if (m.pct >= 100) return "reached";
  return m.foods_with < m.foods ? "partial" : m.pct >= 50 ? "building" : "under";
}

/** "5 of 6 foods reported it": coverage in words, so a low total is read as possibly incomplete. */
export function microCoverage(m: Pick<FoodMicro, "foods_with" | "foods">): string | null {
  return m.foods_with >= m.foods ? null : m.foods_with === 0 ? "no food reported it" : `${m.foods_with} of ${m.foods} foods reported it`;
}

export function formatMicro(m: Pick<FoodMicro, "amount" | "unit">): string {
  if (m.amount == null) return "—";
  const v = m.amount >= 100 ? Math.round(m.amount) : Math.round(m.amount * 10) / 10;
  return `${v.toLocaleString("en-US")} ${m.unit}`;
}

/** Entries of one meal with their calorie and protein subtotal (protein counts only entries that have it). */
export function mealSubtotal(entries: FoodEntry[], meal: Meal): { items: FoodEntry[]; kcal: number; protein_g: number | null } {
  const items = entries.filter((e) => e.meal === meal);
  const withProtein = items.filter((e) => e.protein_g != null);
  return {
    items,
    kcal: items.reduce((a, e) => a + e.kcal, 0),
    protein_g: withProtein.length ? Math.round(withProtein.reduce((a, e) => a + (e.protein_g ?? 0), 0)) : null,
  };
}

/** Next servings value for the stepper: halves under 2, whole numbers above; never below the smallest portion. */
export function stepServings(current: number, direction: 1 | -1): number {
  const step = direction === 1 ? (current < 2 ? 0.5 : 1) : current <= 2 ? 0.5 : 1;
  return Math.max(0.5, Math.min(20, Math.round((current + direction * step) * 100) / 100));
}
