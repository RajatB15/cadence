import { describe, expect, it } from "vitest";
import { browseList, portionPreview, kcalRange, MAX_SEARCH_RESULTS, proteinPosition, searchList, servingsLabel, shiftDay } from "./food";

describe("food helpers", () => {
  it("shifts days across month and year edges", () => {
    expect(shiftDay("2026-03-01", -1)).toBe("2026-02-28");
    expect(shiftDay("2026-12-31", 1)).toBe("2027-01-01");
  });
  it("shows a range, or nothing when the day isn't logged", () => {
    expect(kcalRange({ kcal_low: 1850, kcal_high: 2450 })).toBe("1,850–2,450");
    expect(kcalRange({ kcal_low: null, kcal_high: null })).toBeNull();
  });
  it("places protein against the reference without treating missing as zero", () => {
    expect(proteinPosition(null, [1.4, 2])).toBeNull();
    expect(proteinPosition(0.9, [1.4, 2])).toBe("below");
    expect(proteinPosition(1.6, [1.4, 2])).toBe("within");
    expect(proteinPosition(2.4, [1.4, 2])).toBe("above");
  });
  it("writes servings as fractions", () => {
    expect([0.5, 1, 1.5, 2.25, 0.75, 3.3].map(servingsLabel)).toEqual(["½", "1", "1½", "2¼", "¾", "3.3"]);
  });
  it("browses a short list but searches every dish, including other names", () => {
    const d = (id: number, name: string, source: string, aliases: string[] = []) => ({ id, name, source, aliases });
    const all = [d(1, "Dal tadka", "library"), d(2, "Dal makhani with cream", "library"), d(3, "Moong dal", "library"), d(4, "Mum's dal", "mine"), d(5, "Aam", "library", ["Mango"])];
    expect(browseList(all, [2]).map((x) => x.id)).toEqual([2, 4, 5, 1, 3]); // recent, mine, then shortest names (ties alphabetical)
    expect(searchList(all, "dal").map((x) => x.id)).toEqual([1, 2, 3, 4]); // names starting with the text first
    expect(searchList(all, "mango").map((x) => x.id)).toEqual([5]);
    expect(searchList(all, "  ")).toEqual([]);
    const many = Array.from({ length: 200 }, (_, i) => d(i, `Rice ${i}`, "library"));
    expect(searchList(many, "rice")).toHaveLength(MAX_SEARCH_RESULTS);
    expect(browseList(many, [])).toHaveLength(40);
  });
  it("previews a portion the same way by servings or by grams", () => {
    const paneer = { kcal: 152.7, protein_g: 9.4, unit_g: 50, per_100g: { kcal: 305.4, protein_g: 18.9 } };
    const byServings = portionPreview(paneer, "servings", 2);
    const byGrams = portionPreview(paneer, "grams", 100);
    expect(Math.round(byServings.kcal)).toBe(Math.round(byGrams.kcal));
    expect(byServings.grams).toBe(100);
    expect(portionPreview({ kcal: 200, protein_g: 5, unit_g: null, per_100g: null }, "servings", 1.5).grams).toBeNull();
  });
});
