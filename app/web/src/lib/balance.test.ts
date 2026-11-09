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

import { balanceView } from "./balance";
const at = (h: number, m = 0) => h * 60 + m;
const withProjection = (e: HomeEnergy, burned: number, eaten: number | null, allow = 2000) => {
  const en = energy({ burned: { total: burned, active: null, resting: null, as_of: null }, eaten: eaten == null ? { kcal: null, logged: false, entries: 0, protein_g: null } : { kcal: eaten, logged: true, entries: 2, protein_g: null }, yesterday: { day: "2026-11-08", total: 2500, eaten: 2000 }, ...e });
  return { en, bars: todayBars(en, allow, { lo: 2300, hi: 2500 })! };
};

describe("balanceView: what the card says at this time", () => {
  it("shows the budget in the morning, with no deficit, and yesterday's balance", () => {
    const { en, bars } = withProjection({}, 700, 300);
    const v = balanceView(en, bars, at(8));
    expect(v).toMatchObject({ mode: "budget", showBurned: false, yesterday: 500 });
    expect(v.headline).toMatchObject({ kind: "left", value: 1700 });
    expect(v.paceFrac).toBeNull();
  });
  it("offers the whole budget, not a deficit, with nothing logged", () => {
    const { en, bars } = withProjection({}, 700, null);
    expect(balanceView(en, bars, at(9)).headline).toMatchObject({ kind: "budget", value: 2000, sub: "Nothing logged yet" });
  });
  it("adds a pace marker at midday and keeps 'left' as the headline", () => {
    const { en, bars } = withProjection({}, 1200, 800);
    const v = balanceView(en, bars, at(13));
    expect(v.mode).toBe("pace");
    expect(v.showBurned).toBe(true);
    expect(v.headline.kind).toBe("left");
    expect(v.paceFrac).toBeCloseTo((2000 * (1200 / 2400)) / bars.scale);
    expect(v.headline.sub).toContain("deficit so far 400");
  });
  it("makes the deficit the headline in the evening, with what the day ends at if nothing more is eaten", () => {
    const { en, bars } = withProjection({}, 2000, 1500);
    const v = balanceView(en, bars, at(19));
    expect(v.mode).toBe("result");
    expect(v.headline).toMatchObject({ kind: "deficit", value: 500 });
    expect(v.ifStopped).toEqual([800, 1000]);
  });
  it("calls it a surplus when more is eaten than burned late in the day", () => {
    const { en, bars } = withProjection({}, 2400, 2600);
    expect(balanceView(en, bars, at(22)).headline).toMatchObject({ kind: "surplus", value: 200 });
  });
  it("stays in budget mode late in the day if little has been burned yet (a late start or stale burn)", () => {
    const { en, bars } = withProjection({}, 700, 300);
    expect(balanceView(en, bars, at(18)).mode).toBe("budget");
  });
});
