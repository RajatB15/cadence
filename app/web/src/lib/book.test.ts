import { describe, expect, it } from "vitest";
import { leftNote, percentRead, spanMinutes } from "./book";

const p = (parts_done: number, parts = 161, minutes_left = 660, finished = false) => ({ parts_done, parts, minutes_left, finished });

describe("book progress wording", () => {
  it("formats reading time", () => {
    expect(spanMinutes(0.2)).toBe("1 min");
    expect(spanMinutes(45)).toBe("45 min");
    expect(spanMinutes(60)).toBe("1 h");
    expect(spanMinutes(200)).toBe("3 h 20 min");
  });
  it("describes the start, the middle and the end without scolding", () => {
    expect(leftNote(p(0))).toContain("161 parts");
    expect(leftNote(p(10))).toContain("151 parts left");
    expect(leftNote(p(160))).toContain("1 part left");
    expect(leftNote(p(161, 161, 0, true))).toBe("You’ve finished the book.");
  });
  it("percent read", () => {
    expect(percentRead(p(0))).toBe(0);
    expect(percentRead(p(161, 161, 0, true))).toBe(100);
    expect(percentRead(p(0, 0))).toBe(0);
  });
});
