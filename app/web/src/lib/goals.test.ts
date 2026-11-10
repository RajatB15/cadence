import { describe, expect, it } from "vitest";
import { clockTime, countdown, distanceLabel, formatTimeDigits, pacePer, parseTime, signed } from "./goals";

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


describe("typing a time on a number pad", () => {
  it("fills from the right like a timer", () => {
    expect(formatTimeDigits("4")).toBe("0:04");
    expect(formatTimeDigits("45")).toBe("0:45");
    expect(formatTimeDigits("345")).toBe("3:45");
    expect(formatTimeDigits("3450")).toBe("34:50");
    expect(formatTimeDigits("34500")).toBe("3:45:00");
    expect(formatTimeDigits("134500")).toBe("13:45:00");
    expect(formatTimeDigits("1345000")).toBe("34:50:00"); // longer than hh:mm:ss: the oldest digit drops off
    expect(formatTimeDigits("")).toBe("");
  });
  it("keeps filling as you add digits to what is already shown, and a pasted time comes out the same", () => {
    let shown = "";
    const seen: string[] = [];
    for (const digit of "34500") {
      shown = formatTimeDigits(shown + digit); // the box holds the formatted text; each keystroke appends one digit
      seen.push(shown);
    }
    expect(seen).toEqual(["0:03", "0:34", "3:45", "34:50", "3:45:00"]);
    expect(formatTimeDigits("3:45:00")).toBe("3:45:00");
    expect(formatTimeDigits("3h45")).toBe("3:45");
    expect(formatTimeDigits("0:034")).toBe("0:34");
    expect(formatTimeDigits(formatTimeDigits("3:45:0"))).toBe("34:50"); // backspace shifts back, like a timer
  });
  it("what you type on the pad reads back as the time you meant, for the distance", () => {
    const typed = (digits: string, metres: number) => parseTime(formatTimeDigits(digits), metres);
    expect(typed("34500", 42195)).toBe(13500); // 3:45:00 marathon
    expect(typed("345", 42195)).toBe(13500); // 3:45 marathon
    expect(typed("2530", 5000)).toBe(1530); // 25:30 for 5 km
    expect(typed("14500", 21097.5)).toBe(6300); // 1:45:00 half
  });
});
