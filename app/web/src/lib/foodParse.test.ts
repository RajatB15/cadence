import { describe, expect, it } from "vitest";
import { buildIndex, editDistance, parseLine, rank } from "./foodIndex";
import { foldKey, parseRaw, translit } from "./foodParse";
import { cycleUnit, rowNutrition, setAmount, stepRow, toLogItem, totals, type RowDish } from "./foodRow";

// Synthetic fixtures only (hand-written, not from any catalogue).
const dish = (id: number, name: string, unit: string, grams: number | null, extra: Partial<RowDish> = {}): RowDish => ({
  id, name, unit, unit_g: grams, kcal: 100, protein_g: 4, spread_pct: 15, source: "library", basis: "library", grams_ok: grams != null,
  per_100g: grams ? { kcal: (100 / grams) * 100, protein_g: (4 / grams) * 100, carbs_g: null, fat_g: null } : null,
  portions: grams ? [{ unit, grams }] : [], aliases: [], ...extra,
});
const DISHES: RowDish[] = [
  dish(1, "Idli", "1 piece", 40, { portions: [{ unit: "piece", grams: 40 }] }),
  dish(2, "Sambar", "1 katori", 150, { portions: [{ unit: "katori", grams: 150 }] }),
  dish(3, "Roti", "1 piece", 35, { portions: [{ unit: "piece", grams: 35 }], aliases: ["chapati"] }),
  dish(4, "Rice cooked", "1 katori", 150, { portions: [{ unit: "katori", grams: 150 }], aliases: ["chawal"] }),
  dish(5, "Filter coffee", "1 cup", 150, { portions: [{ unit: "cup", grams: 150 }], aliases: ["coffee"] }),
  dish(6, "Dal", "1 katori", 150, { portions: [{ unit: "katori", grams: 150 }] }),
  dish(7, "Curd", "1 katori", 150, { portions: [{ unit: "katori", grams: 150 }] }),
  dish(8, "Almonds", "10 almonds", 12, { portions: [{ unit: "10 almonds", grams: 12 }] }),
  dish(9, "Paneer bhurji", "1 katori", 120, { portions: [{ unit: "katori", grams: 120 }] }),
  dish(10, "Curd rice", "1 katori", 180, { portions: [{ unit: "katori", grams: 180 }] }),
  dish(11, "Idli sambar", "1 plate", 300, { portions: [{ unit: "plate", grams: 300 }] }),
  dish(12, "Masala tea", "1 cup", 150, { portions: [{ unit: "cup", grams: 150 }], aliases: ["chai"] }),
];
const index = buildIndex(DISHES);
const rows = (s: string) => parseLine(s, index);
const brief = (s: string) => rows(s).map((r) => ({ id: r.dishId, kind: r.kind, servings: r.servings, grams: r.grams, qty: r.qty, flags: r.flags.sort() }));

describe("folding", () => {
  it("makes spelling variants agree", () => {
    expect(foldKey("sambhar")).toBe(foldKey("sambaar"));
    expect(foldKey("sambar")).toBe(foldKey("Sambhar"));
    expect(foldKey("idly")).toBe(foldKey("idli"));
    expect(foldKey("idlee")).toBe(foldKey("idli"));
    expect(foldKey("kaapi")).toBe(foldKey("coffee"));
    expect(foldKey("Café")).toBe(foldKey("cafe"));
  });
  it("transliterates Devanagari", () => {
    expect(foldKey("इडली")).toBe(foldKey("idli"));
    expect(foldKey("सांभर")).toBe(foldKey("sambar"));
    expect(foldKey("दाल")).toBe(foldKey("dal"));
    expect(translit("hello")).toBe("hello");
  });
  it("measures edits with swaps as one", () => {
    expect(editDistance("idli", "ildi")).toBe(1);
    expect(editDistance("abc", "abc")).toBe(0);
    expect(editDistance("abcdef", "uvwxyz", 2)).toBeGreaterThan(2);
  });
});

describe("grammar", () => {
  it("splits on separators and keeps leading and trailing numbers on the right item", () => {
    expect(parseRaw("idli 2, sambar, coffee")).toEqual([
      { name: "idli", qty: 2, unit: null }, { name: "sambar", qty: null, unit: null }, { name: "coffee", qty: null, unit: null },
    ]);
    expect(parseRaw("idli 2 sambar 1 katori coffee").map((i) => [i.name, i.qty, i.unit])).toEqual([["idli", 2, null], ["sambar", 1, "katori"], ["coffee", null, null]]);
    expect(parseRaw("2 idli 3 sambar").map((i) => [i.name, i.qty])).toEqual([["idli", 2], ["sambar", 3]]);
  });
  it("reads fractions, mixed numbers, glyphs and attached units", () => {
    expect(parseRaw("1 1/2 cup rice")[0]).toEqual({ name: "rice", qty: 1.5, unit: "cup" });
    expect(parseRaw("1½ katori dal")[0]).toEqual({ name: "dal", qty: 1.5, unit: "katori" });
    expect(parseRaw("rice 200g")[0]).toEqual({ name: "rice", qty: 200, unit: "g" });
    expect(parseRaw("two glasses of milk")[0]).toEqual({ name: "milk", qty: 2, unit: "glass" });
  });
});

describe("golden cases (docs/food-logging-design.md 2a)", () => {
  it("1: idli 2, sambar, coffee", () => {
    expect(brief("idli 2, sambar, coffee")).toEqual([
      { id: 1, kind: "dish", servings: 2, grams: 80, qty: 2, flags: [] },
      { id: 2, kind: "dish", servings: 1, grams: 150, qty: null, flags: [] },
      { id: 5, kind: "dish", servings: 1, grams: 150, qty: null, flags: [] },
    ]);
  });
  it("2: spelling variants and transliteration", () => {
    expect(rows("2 idly + sambhar + filter kaapi").map((r) => [r.dishId, r.servings])).toEqual([[1, 2], [2, 1], [5, 1]]);
    expect(rows("2 ildi, sambr").map((r) => r.dishId)).toEqual([1, 2]);
  });
  it("3: idli x3 / 3x idli / three idli", () => {
    for (const s of ["idli x3", "3x idli", "three idli", "idli 3x", "x3 idli"]) expect(rows(s).map((r) => [r.dishId, r.servings]), s).toEqual([[1, 3]]);
  });
  it("4: do roti, dal 1.5 katori", () => {
    expect(rows("do roti, dal 1.5 katori").map((r) => [r.dishId, r.servings, r.grams])).toEqual([[3, 2, 70], [6, 1.5, 225]]);
  });
  it("5: 1/2 cup rice and 1/2 katori chawal", () => {
    const [cup] = rows("1/2 cup rice");
    expect(cup.dishId).toBe(4);
    expect(cup.unit).toBe("cup");
    expect(cup.grams).toBe(120); // a cup the dish has no portion for: 240 g table value, flagged rough
    expect(cup.flags).toContain("rough");
    const [k] = rows("½ katori chawal");
    expect([k.dishId, k.servings, k.grams, k.flags]).toEqual([4, 0.5, 75, []]);
  });
  it("6: rice 200g / 200 g rice", () => {
    for (const s of ["rice 200g", "200 g rice"]) {
      const [r] = rows(s);
      expect([r.dishId, r.grams, r.servings]).toEqual([4, 200, 1.33]);
    }
  });
  it("7: curd 1 glass is converted and flagged rough", () => {
    const [r] = rows("curd 1 glass");
    expect([r.dishId, r.grams, r.servings]).toEqual([7, 250, 1.67]);
    expect(r.flags).toContain("rough");
  });
  it("8: a handful almonds", () => {
    const [r] = rows("a handful almonds");
    expect([r.dishId, r.grams]).toEqual([8, 30]);
    expect(r.flags).toContain("rough");
  });
  it("9: paneer bhurji with 2 roti", () => {
    expect(rows("paneer bhurji with 2 roti").map((r) => [r.dishId, r.servings])).toEqual([[9, 1], [3, 2]]);
  });
  it("10: no separators, number-after-name rule", () => {
    expect(rows("idli 2 sambar 1 katori coffee").map((r) => [r.dishId, r.servings])).toEqual([[1, 2], [2, 1], [5, 1]]);
  });
  it("11: unmatched keeps its row with the quantity", () => {
    const [r] = rows("xyzzy 2");
    expect([r.kind, r.dishId, r.qty, r.text]).toEqual(["none", null, 2, "xyzzy"]);
    expect(toLogItem(r)).toBeNull();
  });
  it("12: empty input gives no rows and no error", () => {
    expect(rows("")).toEqual([]);
    expect(rows(",,")).toEqual([]);
    expect(rows("  ;  + ")).toEqual([]);
  });
  it("13: Devanagari", () => {
    expect(rows("इडली 2, सांभर").map((r) => [r.dishId, r.servings])).toEqual([[1, 2], [2, 1]]);
  });
  it("14: a number alone is not an item", () => {
    expect(rows("2")).toEqual([]);
    expect(rows("2, 3")).toEqual([]);
  });
  it("15: zero is rejected and 100 needs a check", () => {
    const [zero] = rows("idly 0");
    expect(zero.flags).toContain("zero");
    expect(toLogItem(zero)).toBeNull();
    const [many] = rows("idli 100");
    expect(many.flags).toContain("check_amount");
    expect(toLogItem(many)).toBeNull();
  });
});

describe("more parsing", () => {
  it("treats a bare number of 50 or more on an unknown name as calories, with a wide range", () => {
    for (const s of ["biryani 450", "450 biryani"]) {
      const [r] = rows(s);
      expect([r.kind, r.kcal]).toEqual(["kcal", 450]);
      const n = rowNutrition(r);
      expect(n.kcal).toEqual({ value: 450, low: 338, high: 563 });
      expect(n.protein_g).toBeNull();
      expect(toLogItem(r)).toMatchObject({ name: "biryani", kcal: 450, save_dish: false });
    }
  });
  it("keeps 'idli 100' a servings check, not calories, because idli matches", () => {
    expect(rows("idli 100")[0].kind).toBe("dish");
  });
  it("uses portion memory only when no amount is typed", () => {
    const ctx = { memory: { 1: { servings: 3 } } };
    expect(parseLine("idli", index, ctx)[0].servings).toBe(3);
    expect(parseLine("idli 2", index, ctx)[0].servings).toBe(2);
  });
  it("prefers an exact name over a longer one, and a more used dish on a tie", () => {
    expect(rows("curd")[0].dishId).toBe(7);
    expect(rows("idli")[0].dishId).toBe(1);
    const fr = new Map([[11, 1]]);
    expect(rank(index, "idli", fr, 2)[0].dish.id).toBe(1); // exact still wins over frecency
  });
  it("offers candidates for a near miss", () => {
    const r = parseLine("sambaaar", index)[0];
    expect(r.candidates[0]?.id).toBe(2);
  });
  it("matches an alias and says nothing else about the dish", () => {
    expect(rows("chapati 2")[0].dishId).toBe(3);
    expect(rows("chai")[0].dishId).toBe(12);
  });
  it("handles a hundred-thousand-character line without hanging", () => {
    const t = Date.now();
    parseLine("idli, ".repeat(2000), index);
    expect(Date.now() - t).toBeLessThan(5000);
  });
});

describe("rows", () => {
  it("steps in natural units and cycles units keeping the weight", () => {
    let r = rows("idli 2")[0];
    r = stepRow(r, 1);
    expect([r.amount, r.grams]).toEqual([3, 120]);
    r = cycleUnit(r);
    expect([r.portionIdx, r.amount, r.grams]).toEqual([-1, 120, 120]);
    expect(stepRow(r, 1).amount).toBe(125);
    const k = stepRow(rows("dal")[0], 1);
    expect(k.amount).toBe(1.5);
  });
  it("shows a range and sums totals without turning unknown protein into zero", () => {
    const a = rows("idli 2")[0];
    const n = rowNutrition(a);
    expect(n.kcal!.low).toBeLessThan(n.kcal!.value);
    expect(n.kcal!.high).toBeGreaterThan(n.kcal!.value);
    const noProtein = { ...rows("dal")[0], dish: { ...DISHES[5], protein_g: null, per_100g: null } };
    const t = totals([a, noProtein, ...rows("xyzzy")]);
    expect(t.count).toBe(2);
    expect(t.partial).toBe(true);
    expect(t.protein_g).toBe(n.protein_g === null ? null : Math.round(n.protein_g));
  });
  it("sends grams for weighable dishes and servings otherwise", () => {
    expect(toLogItem(rows("idli 2")[0])).toMatchObject({ dish_id: 1, grams: 80 });
    const noWeight = dish(20, "Mystery", "1 serving", null);
    const r = parseLine("mystery 2", buildIndex([noWeight]))[0];
    expect(toLogItem(r)).toEqual({ dish_id: 20, servings: 2 });
    expect(toLogItem(setAmount(r, 0))).toBeNull();
  });
});
