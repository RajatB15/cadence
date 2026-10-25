import type { FoodDishInput, FoodLabelRead } from "./types";

export type LabelColumn = "per_100g" | "per_serving";

/** The fields of the review form, as text so a half-typed number is not forced into a value. */
export type LabelFields = { kcal: string; protein_g: string; carbs_g: string; fat_g: string; fibre_g: string; sugars_g: string; sat_fat_g: string; sodium_mg: string };

export const LABEL_FIELDS: { key: keyof LabelFields; label: string; unit: string }[] = [
  { key: "kcal", label: "Calories", unit: "kcal" },
  { key: "protein_g", label: "Protein", unit: "g" },
  { key: "carbs_g", label: "Carbohydrate", unit: "g" },
  { key: "fat_g", label: "Fat", unit: "g" },
  { key: "fibre_g", label: "Fibre", unit: "g" },
  { key: "sugars_g", label: "Sugars", unit: "g" },
  { key: "sat_fat_g", label: "Saturated fat", unit: "g" },
  { key: "sodium_mg", label: "Sodium", unit: "mg" },
];

const MICRO_KEYS = ["fibre_g", "sugars_g", "sat_fat_g", "sodium_mg"] as const;

/** Form text for one column of what the reader found; anything it did not find stays blank (unknown, not zero). */
export function fieldsFrom(read: FoodLabelRead, column: LabelColumn): LabelFields {
  const c = read.columns[column] ?? {};
  const text = (k: string) => (c[k] == null ? "" : String(c[k]));
  return { kcal: text("kcal"), protein_g: text("protein_g"), carbs_g: text("carbs_g"), fat_g: text("fat_g"), fibre_g: text("fibre_g"), sugars_g: text("sugars_g"), sat_fat_g: text("sat_fat_g"), sodium_mg: text("sodium_mg") };
}

/** A typed amount, or null when blank or not a number. */
export function amount(text: string): number | null {
  if (text.trim() === "") return null;
  const n = Number(text.replace(",", "."));
  return Number.isFinite(n) && n >= 0 ? n : null;
}

const r1 = (n: number) => Math.round(n * 10) / 10;

/**
 * The dish to save from reviewed label numbers. With a serving weight the dish can be logged by grams and its per-100 g
 * micronutrients are kept; without one it is a plain "1 serving" (or "100 g") dish and micronutrients are left out, since
 * they can't be scaled. Macros left blank stay unknown.
 */
export function dishFromLabel(name: string, basis: LabelColumn, f: LabelFields, servingG: number | null): FoodDishInput | null {
  const kcal = amount(f.kcal);
  if (!name.trim() || kcal == null || kcal > 5000) return null;
  const v = (k: keyof LabelFields) => amount(f[k]);
  const grams = servingG && servingG > 0 ? servingG : basis === "per_100g" ? 100 : null;
  const toServing = (n: number | null) => (n == null ? null : r1(basis === "per_100g" ? (n * (grams ?? 100)) / 100 : n));
  const per100 = (n: number | null) => (n == null || !grams ? null : r1(basis === "per_100g" ? n : (n * 100) / grams));
  const micros: Record<string, number> = {};
  for (const k of MICRO_KEYS) {
    const x = per100(v(k));
    if (x != null) micros[k] = x;
  }
  const unit = servingG ? `1 serving (≈${servingG} g)` : basis === "per_100g" ? "100 g" : "1 serving";
  return {
    name: name.trim(),
    unit,
    kcal: toServing(kcal) as number,
    protein_g: toServing(v("protein_g")),
    carbs_g: toServing(v("carbs_g")),
    fat_g: toServing(v("fat_g")),
    ...(grams ? { grams } : {}),
    ...(grams && Object.keys(micros).length ? { micros_per_100g: micros } : {}),
    basis: "label",
    note: "From a product label, read from a photo and checked by you.",
  };
}
