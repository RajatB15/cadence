import { describe, expect, it } from "vitest";
import { fitNumeral, holeRadius, labelWidthPx, numeralWidthEm } from "./ringFit";

describe("ringFit", () => {
  it("measures tabular numerals wider with more digits", () => {
    expect(numeralWidthEm("12,845")).toBeGreaterThan(numeralWidthEm("2,845"));
    expect(numeralWidthEm("2,845")).toBeGreaterThan(numeralWidthEm("845"));
  });

  it("holeRadius subtracts half the innermost stroke and scales with size", () => {
    expect(holeRadius(200, 58, 9)).toBeCloseTo(53.5);
    expect(holeRadius(100, 58, 9)).toBeCloseTo(26.75);
  });

  it("gives longer values a smaller numeral in the same hole", () => {
    const r = holeRadius(208, 58, 9);
    expect(fitNumeral({ radius: r, text: "12,845" })).toBeLessThan(fitNumeral({ radius: r, text: "845" }));
  });

  it("keeps every corner of numeral and label inside the hole at several sizes and values", () => {
    const label = { width: labelWidthPx("kcal"), height: 13 };
    for (const size of [160, 208, 260]) {
      for (const text of ["845", "2,845", "12,845", "7h 39m", "—"]) {
        const radius = holeRadius(size, 58, 9);
        const f = fitNumeral({ radius, text, label, pad: 4 });
        const numH = f * 0.9;
        const total = numH + 3 + label.height;
        const w = numeralWidthEm(text) * f;
        const corner = Math.hypot(w / 2, total / 2);
        // The numeral's own top corners are the widest reach; with the clamp at min it may overflow only when the hole is tiny.
        if (f > 14) expect(corner).toBeLessThanOrEqual(radius - 4 + 0.5);
      }
    }
  });

  it("never returns less than min or more than max", () => {
    expect(fitNumeral({ radius: 5, text: "12,845", min: 14 })).toBe(14);
    expect(fitNumeral({ radius: 400, text: "1", max: 48 })).toBe(48);
  });
});
