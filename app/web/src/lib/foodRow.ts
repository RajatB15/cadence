/**
 * One row of a food draft: the matched dish (or a calories-only item), the amount in a natural unit, and everything derived
 * from it (grams, servings, kcal range). Pure. Estimates are ranges, never a bare number; unknown protein stays null.
 */
import { portionPreview } from "./food";
import { UNIT_GRAMS, foldWords } from "./foodParse";
import type { FoodDish } from "./types";

export const MAX_SERVINGS = 20;
export const MAX_GRAMS = 5000;
/** Extra spread, in percentage points, when a unit was converted by a fixed table. */
export const ROUGH_EXTRA_PCT = 10;
export const MIN_SPREAD_PCT = 10;
export const KCAL_ONLY_SPREAD_PCT = 25;
export const OUT_SPREAD_PCT = 35;

export type RowFlag = "rough" | "zero" | "check_amount" | "unit_assumed" | "ml_assumed" | "unit_unknown" | "no_grams";

/** The dish fields a row needs; a full FoodDish satisfies it. */
export type RowDish = Pick<FoodDish, "id" | "name" | "unit" | "unit_g" | "kcal" | "protein_g" | "spread_pct" | "source" | "basis" | "grams_ok" | "per_100g" | "portions" | "aliases"> & { pinned?: boolean; my_names?: FoodDish["my_names"]; display_name?: string };

export interface FoodRow {
  id: string;
  text: string;
  kind: "dish" | "kcal" | "none";
  dish: RowDish | null;
  dishId: number | null;
  candidates: { id: number; name: string; score: number; via?: { kind: "mine" | "alias"; text: string } }[];
  /** Why the top dish matched (your name or a library alias), when not its own name. */
  via?: { kind: "mine" | "alias"; text: string };
  /** What was typed. */
  qty: number | null;
  unit: string | null;
  /** Index into `portionOptions(dish)`; -1 grams; -2 plain servings (a dish with no weight). */
  portionIdx: number;
  /** Amount in the chosen unit (count of portions, or grams). */
  amount: number;
  grams: number | null;
  servings: number | null;
  flags: RowFlag[];
  /** Calories-only rows. */
  kcal?: number;
  out?: boolean;
}

/** Household portions a dish can be measured in; a dish with only a weight gets its own unit as the one portion. */
export const portionOptions = (d: Pick<RowDish, "portions" | "unit" | "unit_g">): { unit: string; grams: number }[] =>
  d.portions.length ? d.portions : d.unit_g ? [{ unit: d.unit, grams: d.unit_g }] : [];

/** "1 katori (150 g)" -> "katori": the unit word without the leading count or bracket. */
export const unitWord = (u: string): string => u.replace(/\(.*?\)/g, "").replace(/^[\d./½¼¾⅓⅔\s]+/, "").trim() || u;

const singular = (w: string) => (w.length > 3 && w.endsWith("s") ? w.slice(0, -1) : w);

/** Does a dish portion label name this canonical unit ("1 katori", "katori", "katoris")? */
export const portionMatches = (label: string, unit: string): boolean => foldWords(unitWord(label)).map(singular).includes(singular(foldWords(unit)[0] ?? unit));

let seq = 0;
export const newRowId = () => `r${Date.now().toString(36)}${(seq++).toString(36)}`;

const round = (n: number, p = 100) => Math.round(n * p) / p;

/** Fills grams, servings and flags from the dish, portion and amount. */
export function settle(row: FoodRow): FoodRow {
  const flags = new Set(row.flags);
  flags.delete("zero");
  flags.delete("check_amount");
  let grams: number | null = null;
  let servings: number | null = null;
  if (row.kind === "dish" && row.dish) {
    const opts = portionOptions(row.dish);
    const base = opts[0]?.grams ?? null;
    if (row.portionIdx >= 0 && opts[row.portionIdx]) grams = row.amount * opts[row.portionIdx].grams;
    else if (row.portionIdx === -1) grams = row.amount;
    servings = row.portionIdx === -2 || base == null ? row.amount : (grams ?? 0) / base;
    if (row.amount <= 0) flags.add("zero");
    if ((servings ?? 0) > MAX_SERVINGS || (grams ?? 0) > MAX_GRAMS) flags.add("check_amount");
  } else if (row.kind === "kcal") {
    if (!(row.kcal && row.kcal > 0)) flags.add("zero");
    else if (row.kcal > 5000) flags.add("check_amount");
  }
  return { ...row, flags: [...flags], grams: grams == null ? null : round(grams, 10), servings: servings == null ? null : round(servings) };
}

/** Resolves a typed quantity and unit against a dish into a row's amount and portion. */
export function resolveAmount(
  dish: RowDish,
  qty: number | null,
  unit: string | null,
  memory?: { servings: number; unit?: string | null } | null,
): Pick<FoodRow, "portionIdx" | "amount" | "flags"> {
  const opts = portionOptions(dish);
  const flags: RowFlag[] = [];
  const base = opts[0]?.grams ?? null;
  const noWeight = opts.length === 0;
  if (unit === "g" || unit === "ml") {
    if (unit === "ml") flags.push("ml_assumed");
    if (!dish.grams_ok || noWeight) return { portionIdx: -2, amount: qty ?? 1, flags: [...flags, "no_grams"] };
    return { portionIdx: -1, amount: qty ?? 100, flags };
  }
  if (unit) {
    const at = opts.findIndex((o) => portionMatches(o.unit, unit));
    if (at >= 0) return { portionIdx: at, amount: qty ?? 1, flags };
    const table = UNIT_GRAMS[unit];
    if (table && base != null && dish.grams_ok) return { portionIdx: -1, amount: round((qty ?? 1) * table, 10), flags: [...flags, "rough"] };
    // Counted units (piece, slice) with no matching portion: take the number as servings of the default portion.
    if (unit === "piece" || unit === "slice" || unit === "plate") return { portionIdx: noWeight ? -2 : 0, amount: qty ?? 1, flags: [...flags, "unit_assumed"] };
    return { portionIdx: noWeight ? -2 : 0, amount: qty ?? 1, flags: [...flags, "unit_unknown"] };
  }
  if (qty != null) return { portionIdx: noWeight ? -2 : 0, amount: qty, flags };
  if (memory && memory.servings > 0) return { portionIdx: noWeight ? -2 : 0, amount: memory.servings, flags };
  return { portionIdx: noWeight ? -2 : 0, amount: 1, flags };
}

/** The label of the unit a row is counted in: "piece", "katori", "g". */
export function rowUnitLabel(row: FoodRow): string {
  if (row.kind !== "dish" || !row.dish) return "";
  if (row.portionIdx === -1) return "g";
  const opts = portionOptions(row.dish);
  if (row.portionIdx >= 0 && opts[row.portionIdx]) return unitWord(opts[row.portionIdx].unit);
  return unitWord(row.dish.unit) || "serving";
}

const COARSE = /katori|bowl|plate|ladle|cup|scoop/i;

/** Step for the +/- stepper: 5 g for grams, halves for katori and bowls, whole numbers for countable units. */
export function stepFor(row: FoodRow): number {
  if (row.portionIdx === -1) return 5;
  return COARSE.test(rowUnitLabel(row)) ? 0.5 : 1;
}

export function stepRow(row: FoodRow, dir: 1 | -1): FoodRow {
  const step = stepFor(row);
  const min = row.portionIdx === -1 ? 5 : 0.5;
  const raw = row.amount + dir * step;
  const next = Math.min(row.portionIdx === -1 ? MAX_GRAMS : 99, Math.max(min, round(raw, 4)));
  return settle({ ...row, amount: next });
}

export function setAmount(row: FoodRow, amount: number): FoodRow {
  return settle({ ...row, amount: Number.isFinite(amount) ? amount : row.amount });
}

/** Units a row can cycle through: the dish's portions, then grams when the dish has a weight. */
export function unitChoices(row: FoodRow): number[] {
  if (row.kind !== "dish" || !row.dish) return [];
  const opts = portionOptions(row.dish);
  const idx = opts.map((_, i) => i);
  return row.dish.grams_ok && opts.length ? [...idx, -1] : idx;
}

/** Switch to the next unit keeping the same weight, so "2 piece" becomes "80 g" and not "2 g". */
export function cycleUnit(row: FoodRow): FoodRow {
  const choices = unitChoices(row);
  if (choices.length < 2 || row.grams == null || !row.dish) return row;
  const opts = portionOptions(row.dish);
  const at = choices.indexOf(row.portionIdx);
  const next = choices[(at + 1) % choices.length];
  const amount = next === -1 ? Math.max(5, Math.round(row.grams / 5) * 5) : Math.max(0.5, Math.round((row.grams / opts[next].grams) * 2) / 2);
  return settle({ ...row, portionIdx: next, amount, flags: row.flags.filter((f) => f !== "rough") });
}

export interface RowNutrition {
  /** Always a range for a dish; `value` is the middle. */
  kcal: { value: number; low: number; high: number } | null;
  protein_g: number | null;
  grams: number | null;
}

export function spreadFor(row: FoodRow): number {
  const base = row.kind === "kcal" ? (row.out ? OUT_SPREAD_PCT : KCAL_ONLY_SPREAD_PCT) : Math.max(row.dish?.spread_pct ?? 0, MIN_SPREAD_PCT);
  return base + (row.flags.includes("rough") ? ROUGH_EXTRA_PCT : 0) + (row.out && row.kind === "dish" ? 10 : 0);
}

export function rowNutrition(row: FoodRow): RowNutrition {
  if (row.flags.includes("zero")) return { kcal: null, protein_g: null, grams: null };
  let value: number | null = null;
  let protein: number | null = null;
  if (row.kind === "kcal" && row.kcal != null) value = row.kcal;
  else if (row.kind === "dish" && row.dish) {
    const p = row.grams != null && row.dish.grams_ok && row.dish.per_100g ? portionPreview(row.dish, "grams", row.grams) : portionPreview(row.dish, "servings", row.servings ?? row.amount);
    value = p.kcal;
    protein = p.protein_g;
  }
  if (value == null) return { kcal: null, protein_g: null, grams: row.grams };
  const s = spreadFor(row) / 100;
  return { kcal: { value: Math.round(value), low: Math.round(value * (1 - s)), high: Math.round(value * (1 + s)) }, protein_g: protein == null ? null : Math.round(protein * 10) / 10, grams: row.grams };
}

export interface DraftTotals {
  kcal: { value: number; low: number; high: number } | null;
  /** Sum over rows that know their protein; `partial` when some do not (never counted as zero). */
  protein_g: number | null;
  partial: boolean;
  count: number;
}

export function totals(rows: FoodRow[]): DraftTotals {
  let v = 0, lo = 0, hi = 0, n = 0, protein = 0, known = 0, partial = false;
  for (const r of rows) {
    if (r.kind === "none") continue;
    const nut = rowNutrition(r);
    if (!nut.kcal) continue;
    n++;
    v += nut.kcal.value;
    lo += nut.kcal.low;
    hi += nut.kcal.high;
    if (nut.protein_g == null) partial = true;
    else {
      protein += nut.protein_g;
      known++;
    }
  }
  return { kcal: n ? { value: v, low: lo, high: hi } : null, protein_g: known ? Math.round(protein) : null, partial: partial && n > 0, count: n };
}

/** A row that can be logged: matched or calories-only, a positive amount, and within sane limits. */
export const loggable = (r: FoodRow): boolean => r.kind !== "none" && !r.flags.includes("zero") && !r.flags.includes("check_amount");

export interface LogItem {
  dish_id?: number;
  servings?: number;
  grams?: number;
  unit?: string;
  name?: string;
  kcal?: number;
  protein_g?: number | null;
  save_dish?: boolean;
}

export function toLogItem(r: FoodRow): LogItem | null {
  if (!loggable(r)) return null;
  if (r.kind === "kcal") return { name: r.text.slice(0, 80), kcal: r.kcal, protein_g: null, save_dish: false };
  if (r.dishId == null) return null;
  if (r.grams != null && r.dish?.grams_ok) return { dish_id: r.dishId, grams: Math.round(r.grams * 10) / 10, unit: rowUnitLabel(r) };
  return { dish_id: r.dishId, servings: r.servings ?? r.amount };
}

/** "320 to 410 kcal" (a range, always). */
export function rangeText(k: { low: number; high: number } | null | undefined, unit = "kcal"): string {
  if (!k) return "";
  return k.low === k.high ? `about ${k.low} ${unit}` : `${k.low} to ${k.high} ${unit}`;
}
