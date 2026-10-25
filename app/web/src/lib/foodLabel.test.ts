import { describe, expect, it } from "vitest";
import { amount, dishFromLabel, fieldsFrom, type LabelFields } from "./foodLabel";
import type { FoodLabelRead } from "./types";

const f = (o: Partial<LabelFields> = {}): LabelFields => ({ kcal: "389", protein_g: "13.5", carbs_g: "66", fat_g: "7", fibre_g: "10", sugars_g: "1.2", sat_fat_g: "", sodium_mg: "4", ...o });

describe("label review", () => {
  it("pre-fills a column and leaves what was not read blank", () => {
    const read = { text: "", columns: { per_100g: { kcal: 389, protein_g: 13.5 } }, order: ["per_100g"], serving_g: null, serving_unit: null, column_assumed: false, warnings: [], issues: {} } as FoodLabelRead;
    expect(fieldsFrom(read, "per_100g")).toMatchObject({ kcal: "389", protein_g: "13.5", carbs_g: "", fat_g: "" });
    expect(fieldsFrom(read, "per_serving").kcal).toBe("");
  });
  it("reads typed amounts, treating blank and nonsense as unknown", () => {
    expect([amount("12"), amount("3,5"), amount(""), amount("abc"), amount("-4")]).toEqual([12, 3.5, null, null, null]);
  });
  it("turns per-100 g numbers and a serving weight into a dish that can be logged by weight", () => {
    const d = dishFromLabel("Granola", "per_100g", f(), 40)!;
    expect(d).toMatchObject({ unit: "1 serving (≈40 g)", grams: 40, kcal: 155.6, protein_g: 5.4, carbs_g: 26.4, fat_g: 2.8, basis: "label" });
    expect(d.micros_per_100g).toEqual({ fibre_g: 10, sugars_g: 1.2, sodium_mg: 4 }); // saturated fat was left blank
  });
  it("without a serving weight a per-100 g label is a 100 g dish", () => {
    expect(dishFromLabel("Oats", "per_100g", f(), null)).toMatchObject({ unit: "100 g", grams: 100, kcal: 389 });
  });
  it("turns per-serve numbers into per-100 g micronutrients only when the serving weight is known", () => {
    const withWeight = dishFromLabel("Bar", "per_serving", f({ kcal: "117", protein_g: "4.1", fibre_g: "3", sodium_mg: "1.2", sugars_g: "", carbs_g: "19.8", fat_g: "2.1" }), 30)!;
    expect(withWeight).toMatchObject({ kcal: 117, grams: 30, unit: "1 serving (≈30 g)" });
    expect(withWeight.micros_per_100g).toEqual({ fibre_g: 10, sodium_mg: 4 });
    const without = dishFromLabel("Bar", "per_serving", f({ kcal: "117" }), null)!;
    expect(without.unit).toBe("1 serving");
    expect(without.grams).toBeUndefined();
    expect(without.micros_per_100g).toBeUndefined();
  });
  it("needs a name and calories, and keeps unknown macros unknown", () => {
    expect(dishFromLabel("", "per_100g", f(), null)).toBeNull();
    expect(dishFromLabel("X", "per_100g", f({ kcal: "" }), null)).toBeNull();
    expect(dishFromLabel("X", "per_100g", f({ protein_g: "", carbs_g: "", fat_g: "" }), 50)).toMatchObject({ protein_g: null, carbs_g: null, fat_g: null });
  });
});
