/**
 * Delete, restore, move and scale for logged entries, using the server's bulk and restore endpoints when it has them and
 * falling back to what every server supports (re-creating an entry, PATCH of servings). Nothing here is destructive without
 * a way back: callers show an Undo toast built on `restoreEntries`.
 */
import { api, ApiError, newIdempotencyKey } from "./api";
import type { FoodEntry, FoodEntryInput, Meal } from "./types";

const missingRoute = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.status === 405);

/** The request that would log this entry again (used for undo and for moving between meals on older servers). */
export function recreateInput(e: FoodEntry, meal: Meal = e.meal): FoodEntryInput {
  if (e.dish_id != null) return { day: e.day, meal, dish_id: e.dish_id, ...(e.grams != null ? { grams: e.grams } : { servings: e.servings }) };
  return { day: e.day, meal, name: e.name, kcal: Math.max(1, e.kcal), protein_g: e.protein_g, carbs_g: e.carbs_g, fat_g: e.fat_g, save_dish: false };
}

export async function removeEntries(entries: FoodEntry[]): Promise<void> {
  const ids = entries.map((e) => e.id);
  if (ids.length > 1) {
    try {
      await api.foodBulk({ ids, action: "delete" });
      return;
    } catch (e) {
      if (!missingRoute(e)) throw e;
    }
  }
  for (const id of ids) await api.deleteFoodEntry(id);
}

/** Undo a delete: restore when the server keeps deleted rows, otherwise log the same thing again. */
export async function restoreEntries(entries: FoodEntry[]): Promise<void> {
  if (entries.length > 1) {
    try {
      await api.foodBulk({ ids: entries.map((e) => e.id), action: "restore" });
      return;
    } catch (e) {
      if (!missingRoute(e) && !(e instanceof ApiError && e.status === 400)) throw e;
    }
  }
  for (const e of entries) {
    try {
      await api.foodRestore(e.id);
    } catch (err) {
      if (!missingRoute(err)) throw err;
      await api.addFoodEntry(recreateInput(e), newIdempotencyKey());
    }
  }
}

export async function moveEntries(entries: FoodEntry[], meal: Meal): Promise<void> {
  try {
    await api.foodBulk({ ids: entries.map((e) => e.id), action: "move", meal });
    return;
  } catch (e) {
    if (!missingRoute(e)) throw e;
  }
  for (const e of entries) {
    await api.addFoodEntry(recreateInput(e, meal), newIdempotencyKey());
    await api.deleteFoodEntry(e.id);
  }
}

/** Scale dish entries by a factor; calories-only entries have no amount to scale and are reported back untouched. */
export async function scaleEntries(entries: FoodEntry[], scale: number): Promise<{ skipped: number }> {
  const scalable = entries.filter((e) => e.dish_id != null);
  if (scalable.length) {
    try {
      await api.foodBulk({ ids: scalable.map((e) => e.id), action: "scale", scale });
      return { skipped: entries.length - scalable.length };
    } catch (e) {
      if (!missingRoute(e)) throw e;
    }
    for (const e of scalable) await api.setFoodEntryAmount(e.id, Math.min(20, Math.max(0.25, Math.round(e.servings * scale * 4) / 4)));
  }
  return { skipped: entries.length - scalable.length };
}

/** Low and high kcal of an entry from its spread, so the day view shows ranges and never a bare number. */
export function entryRange(e: Pick<FoodEntry, "kcal" | "spread_pct">): { low: number; high: number } {
  const s = Math.max(e.spread_pct || 0, 10) / 100;
  return { low: Math.round(e.kcal * (1 - s)), high: Math.round(e.kcal * (1 + s)) };
}

export function groupTotals(entries: FoodEntry[]): { low: number; high: number; protein_g: number | null } {
  let low = 0, high = 0, p = 0, known = 0;
  for (const e of entries) {
    const r = entryRange(e);
    low += r.low;
    high += r.high;
    if (e.protein_g != null) {
      p += e.protein_g;
      known++;
    }
  }
  return { low, high, protein_g: known ? Math.round(p) : null };
}
