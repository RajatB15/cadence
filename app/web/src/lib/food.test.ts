import { describe, expect, it } from "vitest";
import { kcalRange, proteinPosition, servingsLabel, shiftDay } from "./food";

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
});
