import { describe, expect, it } from "vitest";
import { deltaText, spanDays, usesText } from "./trends";
import type { TimeOffItem } from "./types";

const item = (over: Partial<TimeOffItem>): TimeOffItem => ({
  id: 1, kind: "sick", start: "2026-03-02", end: "2026-03-08", activity: null, severity: 2, return_weeks: null, return_start_pct: null, note: null,
  ongoing: false, days: 7, uses: { activity: "none", return_weeks: 2, return_start_pct: 50 }, ...over,
});

describe("deltaText", () => {
  it("says nothing without a comparison and calls small changes level", () => {
    expect(deltaText(null, 28)).toBeNull();
    expect(deltaText(0.3, 28)).toBe("level with the previous 4 weeks");
    expect(deltaText(-4.26, 7)).toBe("−4.3 vs the previous week");
    expect(deltaText(6, 84)).toBe("+6.0 vs the previous 12 weeks");
  });
});

describe("usesText", () => {
  it("describes the plan effect of each kind", () => {
    expect(usesText(item({}))).toBe("No training planned, then 2 weeks easing back from 50%");
    expect(usesText(item({ kind: "travel", uses: { activity: "light", return_weeks: 0, return_start_pct: 90 } }))).toBe("Light movement only, no easing-back period");
    expect(usesText(item({ kind: "vacation", uses: { activity: "full", return_weeks: 0, return_start_pct: 90 } }))).toBe("Training as normal");
  });
});

describe("spanDays", () => {
  it("counts inclusively and runs an open entry to today", () => {
    expect(spanDays("2026-03-02", "2026-03-08", "2026-04-01")).toBe(7);
    expect(spanDays("2026-03-02", null, "2026-03-04")).toBe(3);
    expect(spanDays("2026-03-10", null, "2026-03-04")).toBe(1);
  });
});
