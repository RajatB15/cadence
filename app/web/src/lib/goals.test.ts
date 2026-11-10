import { describe, expect, it } from "vitest";
import { clockTime, countdown, distanceLabel, pacePer, parseTime, signed } from "./goals";

describe("race times typed the way people say them", () => {
  it("reads 3:45 for a marathon as hours and minutes, but 25:00 for a 5 km as minutes", () => {
    expect(parseTime("3:45", 42195)).toBe(3 * 3600 + 45 * 60);
    expect(parseTime("4:00", 42195)).toBe(4 * 3600);
    expect(parseTime("1:45", 21097.5)).toBe(1 * 3600 + 45 * 60);
    expect(parseTime("25:00", 5000)).toBe(1500);
    expect(parseTime("45:30", 10000)).toBe(2730);
    expect(parseTime("3:45:00", 42195)).toBe(13500);
  });
  it("keeps two parts as mm:ss without a distance, and rides and swims use their own speeds", () => {
    expect(parseTime("3:45")).toBe(225);
    expect(parseTime("1:30", 40000, "ride")).toBe(5400);
    expect(parseTime("59:00", 40000, "ride")).toBe(3540);
    expect(parseTime("25:00", 1500, "swim")).toBe(1500);
  });
  it("still rejects things that are not times", () => {
    expect(parseTime("abc", 42195)).toBeNull();
    expect(parseTime("", 42195)).toBeNull();
    expect(parseTime("0:00", 42195)).toBe(0);
  });
});

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
