import { describe, expect, it } from "vitest";
import { dayShare, eatShare, localMinutes, moment } from "./moment";

const at = (h: number, m = 0) => h * 60 + m;

describe("moment: this user's day", () => {
  it("changes at 11:00, 15:00, the end of the eating window (20:00) and bedtime (21:20)", () => {
    expect([at(5, 59), at(8), at(10, 59)].map(moment)).toEqual(["morning", "morning", "morning"]);
    expect([at(11), at(14, 59)].map(moment)).toEqual(["midday", "midday"]);
    expect([at(15), at(19, 59)].map(moment)).toEqual(["afternoon", "afternoon"]);
    expect([at(20), at(21, 19)].map(moment)).toEqual(["evening", "evening"]);
    expect([at(21, 20), at(23, 59), at(0, 30)].map(moment)).toEqual(["night", "night", "morning"]);
  });
  it("paces the waking day from 06:00 to 21:20 and the eating window from 09:00 to 20:00", () => {
    expect(dayShare(at(6))).toBe(0);
    expect(dayShare(at(21, 20))).toBe(1);
    expect(dayShare(at(5))).toBe(0);
    expect(eatShare(at(8))).toBe(0);
    expect(eatShare(at(9))).toBe(0);
    expect(eatShare(at(14, 30))).toBeCloseTo(0.5);
    expect(eatShare(at(20))).toBe(1);
    expect(eatShare(at(23))).toBe(1);
  });
  it("reads the server clock, else the fallback", () => {
    expect(localMinutes("13:05", 0)).toBe(785);
    expect(localMinutes("07:00:12", 0)).toBe(420);
    expect(localMinutes(null, 99)).toBe(99);
    expect(localMinutes("25:00", 99)).toBe(99);
  });
});
