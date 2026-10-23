import { describe, expect, it } from "vitest";
import { formatValue, humanize } from "./DataViews";

describe("humanize", () => {
  it("handles camelCase, snake_case and unnamed FIT fields", () => {
    expect(humanize("averageRunningCadenceInStepsPerMinute")).toBe("Average Running Cadence In Steps Per Minute");
    expect(humanize("avg_heart_rate")).toBe("Avg heart rate");
    expect(humanize("field_253")).toBe("Field 253");
  });
});

describe("formatValue", () => {
  it("keeps identifiers verbatim", () => {
    expect(formatValue("activityId", 24692048005).text).toBe("24692048005");
  });

  it("formats durations, distances and speeds with the raw value preserved", () => {
    expect(formatValue("movingDuration", 5723).text).toBe("1:35:23");
    expect(formatValue("total_distance", 1000)).toEqual({ text: "1.00 km", raw: "1000 m" });
    expect(formatValue("avg_speed", 2.5).text).toBe("9.0 km/h");
  });

  it("does not treat timestamps as durations", () => {
    expect(formatValue("start_time", "2026-10-12T06:18:00").raw).toBe("2026-10-12T06:18:00");
  });

  it("marks missing values explicitly", () => {
    expect(formatValue("x", null).text).toBe("—");
    expect(formatValue("x", false).text).toBe("No");
  });
});
