import { describe, expect, it } from "vitest";
import { MIN_WEEK_DAYS, todayBars, weekBalance } from "./balance";
import type { HomeEnergy } from "./types";

const energy = (over: Partial<HomeEnergy> = {}): HomeEnergy => ({
  burned: { total: 1600, active: 400, resting: 1200, as_of: "14:00" },
  eaten: { kcal: 900, logged: true, entries: 3, protein_g: 50 },
  ...over,
});

describe("todayBars", () => {
  it("puts burned and eaten on one scale and gives the gap", () => {
    const b = todayBars(energy(), 2000, { lo: 2200, hi: 2600 })!;
    expect(b.scale).toBe(2600);
    expect(b.burnedFrac).toBeCloseTo(1600 / 2600);
    expect(b.eatenFrac).toBeCloseTo(900 / 2600);
    expect(b.restingFrac).toBeCloseTo(1200 / 2600);
    expect(b.gap).toBe(700);
  });
  it("has no gap, and no eaten bar, when nothing is logged (not zero)", () => {
    const b = todayBars(energy({ eaten: { kcal: null, logged: false, entries: 0, protein_g: null } }), null, null)!;
    expect(b.gap).toBeNull();
    expect(b.eatenFrac).toBeNull();
  });
  it("is a surplus (negative gap) when more is eaten than burned", () => {
    expect(todayBars(energy({ eaten: { kcal: 2000, logged: true, entries: 4, protein_g: null } }), null, null)!.gap).toBe(-400);
  });
  it("drops an inconsistent resting/active split instead of drawing it", () => {
    const b = todayBars(energy({ burned: { total: 1600, active: 100, resting: 100, as_of: null } }), null, null)!;
    expect(b.restingFrac).toBeNull();
  });
  it("is null without a burn", () => {
    expect(todayBars(energy({ burned: { total: 0, active: null, resting: null, as_of: null } }), null, null)).toBeNull();
    expect(todayBars(energy({ burned: null }), null, null)).toBeNull();
  });
});

describe("weekBalance", () => {
  const day = (d: number, total: number | null, eaten: number | null, partial = false) => ({ day: `2026-11-0${d}`, total, eaten, partial });
  it("sums only days with both burn and a log, and never counts an unlogged day as a deficit", () => {
    const w = weekBalance([day(1, 2500, 2000), day(2, 2500, null), day(3, 2600, 2100), day(4, 2400, 2200)], "2026-11-09")!;
    expect(w.counted).toBe(3);
    expect(w.total).toBe(500 + 500 + 200);
    expect(w.days[1]).toMatchObject({ deficit: null, reason: "no_log" });
    expect(w.average).toBe(400);
    expect(w.kg).toBeCloseTo(1200 / 7700, 2);
  });
  it("shows no total below the minimum number of days", () => {
    const w = weekBalance([day(1, 2500, 2000), day(2, 2500, 2000)], "2026-11-09")!;
    expect(MIN_WEEK_DAYS).toBe(3);
    expect(w.total).toBeNull();
    expect(w.kg).toBeNull();
  });
  it("skips today and partially counted days, and uses at most seven days", () => {
    const rows = [1, 2, 3, 4, 5, 6, 7, 8].map((d) => day(d, 2500, 2000));
    rows.push({ day: "2026-11-09", total: 900, eaten: 100, partial: true });
    const w = weekBalance(rows, "2026-11-09")!;
    expect(w.days).toHaveLength(7);
    expect(w.days.at(-1)!.day).toBe("2026-11-08");
    const p = weekBalance([day(1, 2500, 2000), day(2, 2500, 2000, true), day(3, 2500, 2000), day(4, 2500, 2000)], "2026-11-09")!;
    expect(p.days[1].reason).toBe("no_burn");
  });
  it("is null with no history", () => {
    expect(weekBalance(undefined, "2026-11-09")).toBeNull();
    expect(weekBalance([], "2026-11-09")).toBeNull();
  });
});
