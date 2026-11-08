import { describe, expect, it } from "vitest";
import { dayRings, dayRingSummary } from "./dayRing";
import type { MetricSummary } from "./types";

const m = (metric: string, latest: number, day = "2026-11-08"): MetricSummary => ({ metric, label: metric, unit: "", higher_is_better: true, latest, latest_day: day, recent_mean: null, baseline_mean: null, delta_pct: null, spark: [] });
const base = { today: "2026-11-08", readiness: 80, energy: null };

describe("dayRings", () => {
  it("returns four rings in a fixed order", () => {
    expect(dayRings({ ...base, metrics: [] }).map((r) => r.key)).toEqual(["recovery", "sleep", "move", "fuel"]);
  });
  it("treats absent data as missing, not zero", () => {
    const r = dayRings({ ...base, readiness: null, metrics: [] });
    expect(r.every((x) => x.missing && x.fraction === 0 && x.value === "—")).toBe(true);
    expect(r.some((x) => x.closed)).toBe(false);
  });
  it("closes a ring only with fresh data at or above the reference", () => {
    const r = dayRings({ ...base, metrics: [m("steps", 12000), m("sleep_hours", 7, "2026-11-07")] });
    expect(r.find((x) => x.key === "move")!.closed).toBe(true);
    const sleep = r.find((x) => x.key === "sleep")!;
    expect(sleep.stale).toBe(true);
    expect(sleep.closed).toBe(false);
  });
  it("uses the personal sleep need when given", () => {
    const r = dayRings({ ...base, sleepNeedH: 7.5, metrics: [m("sleep_hours", 7.5)] }).find((x) => x.key === "sleep")!;
    expect(r.fraction).toBe(1);
    expect(r.sub).toContain("your");
  });
  it("fuel prefers intake against target, else burn against projection", () => {
    const fed = dayRings({ ...base, metrics: [], energy: { eaten: { kcal: 1000, logged: true, entries: 2, protein_g: null }, target: { kcal: 2000, source: "formula" } } }).find((x) => x.key === "fuel")!;
    expect(fed.fraction).toBe(0.5);
    const burn = dayRings({ ...base, metrics: [], energy: { burned: { total: 900, active: null, resting: null, as_of: null }, projected: { value: 1800, lo: 1600, hi: 2000, n: 20, method: "curve" } } }).find((x) => x.key === "fuel")!;
    expect(burn.fraction).toBe(0.5);
    expect(burn.sub).toContain("burned");
  });
  it("summary names every ring", () => {
    expect(dayRingSummary(dayRings({ ...base, metrics: [] }))).toContain("Fuel: no data");
  });
});
