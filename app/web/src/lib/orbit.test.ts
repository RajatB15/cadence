import { describe, expect, it } from "vitest";
import { minutesOfIso, orbitAngle, orbitModel, orbitPath, orbitPoint } from "./orbit";

describe("the ring's geometry", () => {
  it("puts midnight at the bottom, 06:00 on the left, noon at the top and 18:00 on the right", () => {
    const at = (h: number) => orbitPoint(100, 100, 50, h * 60);
    const near = (p: { x: number; y: number }, x: number, y: number) => { expect(p.x).toBeCloseTo(x, 5); expect(p.y).toBeCloseTo(y, 5); };
    near(at(0), 100, 150);
    near(at(6), 50, 100);
    near(at(12), 100, 50);
    near(at(18), 150, 100);
    expect(orbitAngle(12 * 60)).toBe(180);
    expect(orbitAngle(24 * 60 + 6 * 60)).toBe(orbitAngle(6 * 60)); // wraps
  });
  it("draws arcs the short way round, large-arc flag only past half a day, and nothing for an empty span", () => {
    expect(orbitPath(100, 100, 50, 6 * 60, 12 * 60)).toMatch(/ 0 0 1 /);
    expect(orbitPath(100, 100, 50, 6 * 60, 20 * 60)).toMatch(/ 0 1 1 /);
    expect(orbitPath(100, 100, 50, 600, 600)).toBe("");
    expect(orbitPath(100, 100, 50, 22 * 60, 6 * 60)).toMatch(/^M /); // across midnight
  });
});

describe("the day's arcs and what is next", () => {
  const base = { minutes: 16 * 60 + 48, sleepH: 7.4, wakeMin: 6 * 60 + 40, bedMin: 22 * 60 + 27 };
  it("places last night's sleep before the usual wake time, across midnight when needed", () => {
    const m = orbitModel(base);
    const sleep = m.arcs.find((a) => a.kind === "sleep")!;
    expect(sleep.to).toBe(400);
    expect(sleep.from).toBe(((400 - 444) + 1440) % 1440);
    expect(sleep.label).toContain("Slept 7 h 24 min");
  });
  it("leaves out sleep when either number is unknown, never a zero-hour arc", () => {
    expect(orbitModel({ ...base, sleepH: null }).arcs.some((a) => a.kind === "sleep")).toBe(false);
    expect(orbitModel({ ...base, wakeMin: undefined }).arcs.some((a) => a.kind === "sleep")).toBe(false);
    expect(orbitModel({ ...base, sleepH: 0 }).arcs.some((a) => a.kind === "sleep")).toBe(false);
  });
  it("always carries the usual eating window and marks planned sessions dashed", () => {
    const m = orbitModel({ ...base, planned: [{ startMin: 18 * 60, minutes: 45, label: "Full body" }], sessions: [{ startMin: 6 * 60 + 30, minutes: 50, label: "Run" }] });
    expect(m.arcs.find((a) => a.kind === "eat")).toMatchObject({ from: 540, to: 1200 });
    expect(m.arcs.find((a) => a.kind === "planned")).toMatchObject({ dashed: true, from: 1080, to: 1125 });
    expect(m.arcs.find((a) => a.kind === "session")).toMatchObject({ from: 390, to: 440 });
  });
  it("names what is next: a planned session still ahead, else bedtime, else nothing", () => {
    expect(orbitModel({ ...base, planned: [{ startMin: 18 * 60, minutes: 45, label: "Full body" }] }).next).toEqual({ label: "Full body", at: 1080 });
    expect(orbitModel(base).next).toEqual({ label: "In bed by", at: 22 * 60 + 27 });
    expect(orbitModel({ ...base, minutes: 23 * 60 }).next).toBeNull();
    expect(orbitModel({ ...base, planned: [{ startMin: 7 * 60, minutes: 45, label: "Past" }] }).next).toEqual({ label: "In bed by", at: 1347 }); // a session earlier today is not "next"
  });
});

describe("timestamps", () => {
  it("reads a time of day from an ISO string, with or without a zone", () => {
    expect(minutesOfIso("not a date")).toBeNull();
    expect(minutesOfIso(null)).toBeNull();
    expect(minutesOfIso("2026-11-15T06:15:00+00:00")).not.toBeNull();
  });
});
