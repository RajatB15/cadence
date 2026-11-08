/**
 * Suggestion chips for the entry bar: the server's (usual for this meal, yesterday, last, saved, pinned) when /api/food/quick
 * answers, otherwise built here from this device's history, yesterday's entries, saved meals and pinned dishes. Pure.
 */
import { usualMeals, type LogRecord } from "./foodFrecency";
import { newRowId, portionOptions, settle, totals, type FoodRow, type RowDish } from "./foodRow";
import type { FoodQuick, KcalRangeValue, QuickItem } from "./foodTypes";
import type { FoodEntry, FoodSavedMeal, Meal } from "./types";

export interface ChipItem {
  dishId: number | null;
  name: string;
  servings: number;
  grams?: number | null;
  unit?: string | null;
  kcal?: number;
  protein_g?: number | null;
}

export interface Chip {
  key: string;
  kind: string;
  label: string;
  items: ChipItem[];
  kcal?: KcalRangeValue | null;
  nDays?: number;
}

export const MAX_CHIPS = 6;

const fromQuick = (i: QuickItem): ChipItem => ({ dishId: i.dish_id ?? null, name: i.name, servings: i.servings ?? 1, grams: i.grams ?? null, unit: i.unit ?? null, kcal: i.kcal, protein_g: i.protein_g });

export function chipsFromServer(q: FoodQuick | undefined | null): Chip[] | null {
  if (!q || !Array.isArray(q.chips)) return null;
  return q.chips
    .filter((c) => c && Array.isArray(c.items) && c.items.length > 0)
    .map((c, i) => ({ key: c.id ?? `${c.kind}:${i}`, kind: c.kind, label: c.label || c.kind, items: c.items.map(fromQuick), kcal: c.kcal ?? null, nDays: c.n_days }))
    .slice(0, MAX_CHIPS);
}

const MEAL_LABEL: Record<Meal, string> = { breakfast: "breakfast", lunch: "lunch", snack: "snack", dinner: "dinner" };

export interface LocalChipInput {
  meal: Meal;
  today: string;
  day: string;
  history: LogRecord[];
  dishById: Map<number, RowDish>;
  /** Entries logged the day before `day`. */
  yesterday: FoodEntry[];
  saved: FoodSavedMeal[];
  pinned: RowDish[];
}

export function localChips(i: LocalChipInput): Chip[] {
  const chips: Chip[] = [];
  const known = (id: number) => i.dishById.has(id);
  const usual = usualMeals(i.history.filter((l) => known(l.dishId)), i.day, i.meal)[0];
  if (usual) {
    chips.push({
      key: `usual:${i.meal}`, kind: "usual", label: `Usual ${MEAL_LABEL[i.meal]}`, nDays: usual.days,
      items: usual.items.map((x) => ({ dishId: x.dishId, name: i.dishById.get(x.dishId)!.name, servings: x.servings, unit: x.unit })),
    });
  }
  const y = i.yesterday.filter((e) => e.meal === i.meal);
  if (y.length) {
    chips.push({
      key: `yesterday:${i.meal}`, kind: "yesterday", label: `Yesterday's ${MEAL_LABEL[i.meal]}`,
      items: y.map((e) => ({ dishId: e.dish_id != null && known(e.dish_id) ? e.dish_id : null, name: e.name, servings: e.servings, grams: e.grams, kcal: e.kcal, protein_g: e.protein_g })),
    });
  }
  const last = i.history.filter((l) => known(l.dishId)).slice(-1)[0];
  if (last) {
    const items = i.history.filter((l) => l.day === last.day && l.meal === last.meal && known(l.dishId));
    if (items.length) chips.push({ key: "last", kind: "last", label: "Repeat last", items: items.map((l) => ({ dishId: l.dishId, name: i.dishById.get(l.dishId)!.name, servings: l.servings, unit: l.unit })) });
  }
  const savedSorted = [...i.saved].sort((a, b) => (b.last_used ?? "").localeCompare(a.last_used ?? ""));
  for (const m of savedSorted.slice(0, 3)) {
    chips.push({ key: `saved:${m.id}`, kind: "saved", label: m.name, items: m.items.map((x) => ({ dishId: x.dish_id, name: x.name, servings: x.servings, grams: x.grams, kcal: x.kcal, protein_g: x.protein_g })) });
  }
  for (const d of i.pinned.slice(0, 3)) chips.push({ key: `pinned:${d.id}`, kind: "pinned", label: d.name, items: [{ dishId: d.id, name: d.name, servings: 1 }] });
  return dedupe(chips).slice(0, MAX_CHIPS);
}

/** Drops chips that would log exactly the same dishes as an earlier one. */
function dedupe(chips: Chip[]): Chip[] {
  const seen = new Set<string>();
  return chips.filter((c) => {
    const sig = c.items.map((x) => `${x.dishId ?? x.name}:${x.servings}`).sort().join("|");
    if (seen.has(sig)) return false;
    seen.add(sig);
    return true;
  });
}

/** Draft rows for a chip. Dishes no longer in the list fall back to calories-only when the chip knows the calories, else are left out. */
export function rowsFromChip(chip: Chip, dishById: Map<number, RowDish>, out = false): FoodRow[] {
  const rows: FoodRow[] = [];
  for (const it of chip.items) {
    const dish = it.dishId != null ? dishById.get(it.dishId) : undefined;
    const base = { id: newRowId(), text: it.name, candidates: [], qty: it.servings, unit: null, grams: null, servings: null, out };
    if (dish) {
      const noWeight = portionOptions(dish).length === 0;
      rows.push(settle({ ...base, kind: "dish", dish, dishId: dish.id, portionIdx: noWeight ? -2 : 0, amount: it.servings > 0 ? it.servings : 1, flags: [] }));
    } else if (it.kcal != null && it.kcal > 0) {
      rows.push(settle({ ...base, kind: "kcal", dish: null, dishId: null, kcal: it.kcal, portionIdx: -2, amount: 1, flags: [] }));
    }
  }
  return rows;
}

/** "Usual breakfast · 3 items" and a kcal range from the rows when the server did not give one. */
export function chipSummary(chip: Chip, rows: FoodRow[]): { items: number; kcal: KcalRangeValue | null } {
  return { items: chip.items.length, kcal: chip.kcal ?? totals(rows).kcal };
}
