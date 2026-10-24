import { describe, expect, it } from "vitest";
import { clockTime, countdown, distanceLabel, pacePer, parseTime, signed } from "./goals";

describe("goal formatting", () => {
  it("formats and parses times both ways", () => {
    expect(clockTime(5100)).toBe("1:25:00");
    expect(clockTime(1500)).toBe("25:00");
    expect(parseTime("1:25:00")).toBe(5100);
    expect(parseTime("25:00")).toBe(1500);
    expect(parseTime("25")).toBeNull();
    expect(parseTime("")).toBeNull();
    expect(parseTime("a:b")).toBeNull();
    expect(parseTime("1:2:3:4")).toBeNull();
  });

  it("gives pace in the unit of each sport", () => {
    expect(pacePer("run", 10000, 3000)).toBe("5:00/km");
    expect(pacePer("swim", 1500, 1800)).toBe("2:00/100 m");
    expect(pacePer("ride", 40000, 4800)).toBe("30.0 km/h");
  });

  it("labels distances and signs numbers", () => {
    expect(distanceLabel(400)).toBe("400 m");
    expect(distanceLabel(21097.5)).toBe("21.1 km");
    expect(signed(2.345)).toBe("+2.3");
    expect(signed(-1, 0)).toBe("-1");
  });

  it("describes how far away a goal is", () => {
    expect(countdown({ days_left: null })).toBeNull();
    expect(countdown({ days_left: 0 })).toBe("today");
    expect(countdown({ days_left: 5 })).toBe("in 5 days");
    expect(countdown({ days_left: 70 })).toBe("in 10 weeks");
    expect(countdown({ days_left: -3 })).toBe("3 days ago");
  });
});
