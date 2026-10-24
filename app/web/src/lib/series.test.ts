import { describe, expect, it } from "vitest";
import { calendarAverage } from "./series";

const pts = (rows: [string, number][]) => rows.map(([day, value]) => ({ day, value }));

describe("calendarAverage", () => {
  it("averages over calendar days and fills every day", () => {
    const out = calendarAverage(pts([["2026-03-01", 10], ["2026-03-02", 20], ["2026-03-03", 30], ["2026-03-04", 40]]), 7, 3);
    expect(out.map((o) => o[0])).toEqual(["2026-03-01", "2026-03-02", "2026-03-03", "2026-03-04"]);
    expect(out.map((o) => o[1])).toEqual([null, null, 20, 25]);
  });

  it("breaks over a gap instead of averaging readings that are weeks apart", () => {
    const out = calendarAverage(pts([["2026-03-01", 10], ["2026-03-02", 10], ["2026-03-03", 10], ["2026-03-20", 50], ["2026-03-21", 50], ["2026-03-22", 50]]), 7, 3);
    const byDay = Object.fromEntries(out);
    expect(byDay["2026-03-03"]).toBe(10);
    expect(byDay["2026-03-10"]).toBeNull();
    expect(byDay["2026-03-22"]).toBe(50);
    expect(out).toHaveLength(22);
  });

  it("handles no data and month ends", () => {
    expect(calendarAverage([])).toEqual([]);
    const out = calendarAverage(pts([["2026-02-27", 1], ["2026-02-28", 2], ["2026-03-01", 3]]), 7, 3);
    expect(out[2]).toEqual(["2026-03-01", 2]);
  });
});
