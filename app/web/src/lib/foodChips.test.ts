import { describe, expect, it } from "vitest";
import { chipsFromServer, localChips, rowsFromChip } from "./foodChips";
import type { RowDish } from "./foodRow";
import type { FoodEntry, FoodSavedMeal } from "./types";

const dish = (id: number, name: string, grams = 40): RowDish => ({
  id, name, unit: "1 piece", unit_g: grams, kcal: 80, protein_g: 3, spread_pct: 15, source: "library", basis: "library", grams_ok: true,
  per_100g: { kcal: 200, protein_g: 7, carbs_g: null, fat_g: null }, portions: [{ unit: "piece", grams }], aliases: [],
});
const byId = new Map([1, 2, 3].map((i) => [i, dish(i, `Dish ${i}`)]));
const L = (day: string, meal: "breakfast", dishId: number, servings = 1) => ({ day, meal, dishId, servings });

describe("chips", () => {
  it("returns null when the server sent no chips so the page can use local ones", () => {
    expect(chipsFromServer(undefined)).toBeNull();
    expect(chipsFromServer({})).toBeNull();
    expect(chipsFromServer({ chips: [] })).toEqual([]);
  });
  it("reads server chips defensively and caps at six", () => {
    const chips = chipsFromServer({ chips: Array.from({ length: 9 }, (_, i) => ({ kind: "usual", label: `c${i}`, items: [{ dish_id: 1, name: "Idli" }] })) });
    expect(chips).toHaveLength(6);
    expect(chips![0].items[0]).toMatchObject({ dishId: 1, servings: 1 });
    expect(chipsFromServer({ chips: [{ kind: "x", label: "empty", items: [] }] })).toEqual([]);
  });
  it("builds local chips: usual, yesterday, last, saved, pinned, without duplicates", () => {
    const days = ["2026-11-07", "2026-11-06", "2026-11-05"];
    const history = days.flatMap((d) => [L(d, "breakfast", 1, 2), L(d, "breakfast", 2)]);
    const yesterday = [{ id: 9, day: "2026-11-07", meal: "breakfast", dish_id: 1, name: "Dish 1", servings: 2, grams: 80, kcal: 160, protein_g: 6, spread_pct: 15 }] as FoodEntry[];
    const saved = [{ id: 4, name: "Post run", items: [{ id: 1, dish_id: 3, name: "Dish 3", servings: 1, grams: 40, kcal: 80, protein_g: 3 }], last_used: null }] as unknown as FoodSavedMeal[];
    const chips = localChips({ meal: "breakfast", today: "2026-11-08", day: "2026-11-08", history, dishById: byId, yesterday, saved, pinned: [byId.get(2)!] });
    expect(chips.map((c) => c.kind)).toEqual(["usual", "yesterday", "saved", "pinned"].filter((k) => chips.some((c) => c.kind === k)));
    expect(chips[0].kind).toBe("usual");
    expect(chips[0].label).toBe("Usual breakfast");
    expect(chips.length).toBeLessThanOrEqual(6);
  });
  it("makes no chips from nothing", () => {
    expect(localChips({ meal: "lunch", today: "2026-11-08", day: "2026-11-08", history: [], dishById: byId, yesterday: [], saved: [], pinned: [] })).toEqual([]);
  });
  it("turns a chip into rows; unknown dishes need calories to be kept", () => {
    const rows = rowsFromChip({ key: "k", kind: "saved", label: "x", items: [{ dishId: 1, name: "Dish 1", servings: 2 }, { dishId: 99, name: "Gone", servings: 1 }, { dishId: null, name: "Thali", servings: 1, kcal: 600 }] }, byId);
    expect(rows.map((r) => [r.kind, r.servings ?? r.kcal])).toEqual([["dish", 2], ["kcal", 600]]);
  });
});
