import { describe, expect, it } from "vitest";
import { dayLabel, eventDates, eventStats } from "./events";

describe("event figures", () => {
  it("shows a field nobody reported as missing, not zero", () => {
    const stats = eventStats({ count: 2, distance_m: 32000, moving_s: 36000, elapsed_s: 90000, calories: null });
    expect(stats.find((s) => s.label === "km")?.value).toBe("32.0");
    expect(stats.find((s) => s.label === "kcal")?.value).toBe("—");
    expect(stats.find((s) => s.label === "load")?.value).toBe("—");
  });
  it("labels days from one and handles an event whose activities are gone", () => {
    expect(dayLabel(3)).toBe("Day 3");
    expect(eventDates(null, null)).toMatch(/No activities/);
  });
});
