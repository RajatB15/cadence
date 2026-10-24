import { describe, expect, it } from "vitest";
import { parsePace, toSpec } from "./customSession";

const base = { distance: "", pace: "", minutes: "", effort: "auto" as const };

describe("custom session input", () => {
  it("parses pace as m:ss or minutes", () => {
    expect(parsePace("5:30")).toBe(330);
    expect(parsePace("2")).toBe(120);
    expect(parsePace("5:75")).toBeNull();
    expect(parsePace("")).toBeNull();
  });

  it("needs two of distance, time and pace", () => {
    expect(toSpec("run", { ...base, distance: "10" })).toBeNull();
    expect(toSpec("run", { ...base, distance: "10", pace: "5:00" })).toEqual({ distance_m: 10000, speed_mps: 1000 / 300 });
    expect(toSpec("run", { ...base, minutes: "45", pace: "abc" })).toBeNull();
  });

  it("converts units per sport and keeps the effort when chosen", () => {
    expect(toSpec("ride", { ...base, minutes: "90", pace: "36", effort: "hard" })).toEqual({ minutes: 90, speed_mps: 10, effort: "hard" });
    expect(toSpec("swim", { ...base, distance: "1500", pace: "2:00" })).toEqual({ distance_m: 1500, speed_mps: 100 / 120 });
  });

  it("lets distance and time win over a typed pace", () => {
    expect(toSpec("run", { ...base, distance: "5", minutes: "25", pace: "9:00" })).toEqual({ distance_m: 5000, minutes: 25 });
  });
});
