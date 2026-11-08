import { describe, expect, it } from "vitest";
import { buildIndex, parseLine, rank } from "./foodIndex";
import type { RowDish } from "./foodRow";

let n = 0;
const dish = (name: string, extra: Partial<RowDish> = {}): RowDish => ({
  id: ++n, name, unit: "1 katori", unit_g: 150, kcal: 150, protein_g: 5, spread_pct: 15, source: "library", basis: "library", grams_ok: true,
  per_100g: null, portions: [{ unit: "1 katori", grams: 150 }], aliases: [], ...extra,
});

const lib = {
  rice: dish("Steamed rice", { aliases: ["Chawal", "Bhaat"] }),
  dosa: dish("Dosa", { aliases: ["Dosai"] }),
  paneer: dish("Paneer butter masala"),
  curd: dish("Curd", { aliases: ["Dahi", "Yogurt"] }),
  sweetCurd: dish("Sweet curd", { aliases: ["Mishti doi"] }),
  potato: dish("Aloo sabzi", { aliases: ["Potato curry"] }),
  sambar: dish("Sambar"),
};
const index = () => buildIndex(Object.values(lib));
const top = (q: string, ix = index()) => rank(ix, q)[0]?.dish.name;

describe("spelling variants and scripts", () => {
  it("folds common spellings", () => {
    expect(top("chaval")).toBe("Steamed rice");
    expect(top("dosai")).toBe("Dosa");
    expect(top("panir butter masala")).toBe("Paneer butter masala");
    expect(top("alu sabji")).toBe("Aloo sabzi");
    expect(top("sambhar")).toBe("Sambar");
  });
  it("reads Devanagari, alone or mixed with Latin", () => {
    expect(top("चावल")).toBe("Steamed rice");
    expect(top("दही")).toBe("Curd");
    const d = dish("Sweet curd", { my_names: [{ id: 1, name: "मीठा दही" }] });
    const ix = buildIndex([d, dish("Curd")]);
    expect(rank(ix, "meetha dahi")[0].dish.id).toBe(d.id); // typed in Latin, saved in Devanagari
    expect(rank(ix, "meetha दही")[0].dish.id).toBe(d.id); // mixed
  });
});

describe("typos and word order", () => {
  it("tolerates a typo", () => {
    expect(top("sambr")).toBe("Sambar");
    expect(top("paner butter masla")).toBe("Paneer butter masala");
  });
  it("ignores the order of words", () => {
    expect(top("masala paneer butter")).toBe("Paneer butter masala");
    expect(top("curd sweet")).toBe("Sweet curd");
  });
  it("returns nothing for nothing", () => {
    expect(rank(index(), "   ")).toEqual([]);
    expect(rank(index(), "zzzzqq")).toEqual([]);
  });
});

describe("my names", () => {
  const mine = (name: string, preferred = false, id = 1) => ({ id, name, preferred });

  it("find the dish by a local name that no library alias has", () => {
    const d = dish("Sweet curd", { my_names: [mine("Meetha dahi")] });
    const ix = buildIndex([d, dish("Curd", { aliases: ["Dahi"] })]);
    const r = rank(ix, "meetha dahi");
    expect(r[0].dish.id).toBe(d.id);
    expect(r[0].via).toEqual({ kind: "mine", text: "Meetha dahi" });
  });

  it("outrank a library alias and even a library name of the same text", () => {
    const a = dish("Plain curd", { aliases: ["Thayir"] });
    const b = dish("Thayir sadam", { my_names: [mine("Thayir")] });
    const ix = buildIndex([a, b]);
    expect(rank(ix, "thayir")[0].dish.id).toBe(b.id);
    const c = dish("Curd rice");
    const d = dish("Something else", { my_names: [mine("Curd rice")] });
    expect(rank(buildIndex([c, d]), "curd rice")[0].dish.id).toBe(d.id);
  });

  it("match with a typo, reordered words and a prefix, and say so", () => {
    const d = dish("Sweet curd", { my_names: [mine("Meetha dahi")] });
    const ix = buildIndex([d, dish("Dahi vada")]);
    expect(rank(ix, "metha dahi")[0].dish.id).toBe(d.id);
    expect(rank(ix, "dahi meetha")[0].dish.id).toBe(d.id);
    expect(rank(ix, "meeth")[0].via?.kind).toBe("mine");
  });

  it("report a library alias as the reason when the name did not match", () => {
    const r = rank(index(), "mishti");
    expect(r[0].dish.name).toBe("Sweet curd");
    expect(r[0].via).toEqual({ kind: "alias", text: "Mishti doi" });
    expect(rank(index(), "sweet curd")[0].via).toBeUndefined();
  });

  it("survive missing or odd my_names", () => {
    const d = dish("Poha", { my_names: undefined });
    const e = dish("Upma", { my_names: [{ id: 1, name: "" }, { id: 2 } as never] });
    expect(() => buildIndex([d, e])).not.toThrow();
    expect(rank(buildIndex([d, e]), "poha")[0].dish.name).toBe("Poha");
  });

  it("frecency lifts one of two equal matches", () => {
    const a = dish("Roti large"), b = dish("Roti plain");
    const ix = buildIndex([a, b]);
    expect(rank(ix, "roti", new Map([[b.id, 1]]))[0].dish.id).toBe(b.id);
  });
});

describe("the entry bar", () => {
  it("resolves a typed line through your own names", () => {
    const d = dish("Sweet curd", { my_names: [{ id: 3, name: "Meetha dahi" }] });
    const rows = parseLine("meetha dahi 1 katori, sambar", buildIndex([d, dish("Sambar")]));
    expect(rows).toHaveLength(2);
    expect(rows[0].kind).toBe("dish");
    expect(rows[0].dishId).toBe(d.id);
    expect(rows[0].via).toEqual({ kind: "mine", text: "Meetha dahi" });
    expect(rows[1].dish?.name).toBe("Sambar");
  });
  it("keeps an unmatched name instead of dropping it", () => {
    expect(parseLine("zzqx", index())[0].kind).toBe("none");
  });
});
