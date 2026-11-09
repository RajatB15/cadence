import { describe, expect, it } from "vitest";
import { dayRings, dayRingSummary } from "./dayRing";
import type { MetricSummary } from "./types";

const m = (metric: string, latest: number, day = "2026-11-08"): MetricSummary => ({ metric, label: metric, unit: "", higher_is_better: true, latest, latest_day: day, recent_mean: null, baseline_mean: null, delta_pct: null, spark: [] });
const base = { today: "2026-11-08", readiness: 80, energy: null };

describe("dayRings", () => {
  it("returns four meters in a fixed order without a clock", () => {
    expect(dayRings({ ...base, metrics: [] }).map((r) => r.key)).toEqual(["recovery", "sleep", "move", "protein"]);
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
  const eaten = (protein: number | null, logged = true) => ({ eaten: { kcal: 1000, logged, entries: 2, protein_g: protein }, target: { kcal: 2000, source: "formula", protein: { low_g: 100, high_g: 150, per_kg: [1.4, 2.0] as [number, number] } } });
  it("protein is a meter against the band, and missing is not zero", () => {
    const p = dayRings({ ...base, metrics: [], energy: eaten(60) }).find((x) => x.key === "protein")!;
    expect(p.fraction).toBeCloseTo(0.6);
    expect(p.sub).toContain("40 g to the low end");
    expect(dayRings({ ...base, metrics: [], energy: eaten(null) }).find((x) => x.key === "protein")!.missing).toBe(true);
    expect(dayRings({ ...base, metrics: [], energy: eaten(120) }).find((x) => x.key === "protein")!.sub).toContain("in your");
    expect(dayRings({ ...base, metrics: [], energy: eaten(120) }).find((x) => x.key === "protein")!.closed).toBe(true);
  });
  it("orders the meters for the time of day", () => {
    const keys = (min: number) => dayRings({ ...base, metrics: [], minutes: min }).map((r) => r.key);
    expect(keys(8 * 60)[0]).toBe("recovery");
    expect(keys(13 * 60)[0]).toBe("move");
    expect(keys(19 * 60)[0]).toBe("protein");
    expect(keys(22 * 60)[0]).toBe("sleep");
  });
  it("paces steps against the waking day, only for fresh data", () => {
    const at = (min: number, steps: number, day = "2026-11-08") => dayRings({ ...base, metrics: [m("steps", steps, day)], minutes: min }).find((x) => x.key === "move")!;
    const noon = at(14 * 60, 2000); // 8 of 16 waking hours: about 5,000 expected
    expect(noon.pace).toBeCloseTo(0.5);
    expect(noon.sub).toContain("behind");
    expect(at(14 * 60, 5100).sub).toContain("on pace");
    expect(at(14 * 60, 7000).sub).toContain("ahead");
    expect(at(14 * 60, 2000, "2026-11-07").pace).toBeNull();
    expect(at(5 * 60, 0).pace).toBeNull();
    expect(dayRings({ ...base, metrics: [m("steps", 2000)] }).find((x) => x.key === "move")!.pace).toBeNull();
  });
  it("says last night for sleep once the morning is over", () => {
    const s = dayRings({ ...base, metrics: [m("sleep_hours", 7)], minutes: 15 * 60 }).find((x) => x.key === "sleep")!;
    expect(s.sub.startsWith("last night")).toBe(true);
  });
  it("summary names every ring", () => {
    expect(dayRingSummary(dayRings({ ...base, metrics: [] }))).toContain("Protein: no data");
  });
});
