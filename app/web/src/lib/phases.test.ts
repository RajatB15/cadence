import { describe, expect, it } from "vitest";
import { clock, goalValue, bannerLine, describePillar, nextWindow, passesLine, pillarHeadline, pillarOf, draftOf, templates, totalPaceLine, validateBody } from "./phases";
import type { PhaseSummary, PillarResult } from "./types";

const pillar = (over: Partial<PillarResult>): PillarResult => ({ id: "p1", kind: "daily", metric: "moved", target: 20, status: "on", ...over });

describe("pillar wording", () => {
  it("describes each shape and prefers your own label", () => {
    expect(describePillar({ kind: "daily", metric: "moved", target: 20 })).toBe("Move 20+ min a day");
    expect(describePillar({ kind: "daily", metric: "sleep_h", target: 7.5 })).toBe("Sleep 7.5+ h a night");
    expect(describePillar({ kind: "weekly", metric: "sessions", target: 4 })).toBe("4 sessions a week");
    expect(describePillar({ kind: "total", metric: "distance_km", target: 100, family: "run" })).toBe("100 km · Run");
    expect(describePillar({ kind: "habit", behaviour: "alcohol", want: "no" }, [{ key: "alcohol", label: "Alcohol" }])).toBe("No alcohol");
    expect(describePillar({ kind: "daily", metric: "moved", target: 20, label: "Daily dose" })).toBe("Daily dose");
  });
  it("words streaks, totals and passes without inventing numbers", () => {
    expect(pillarHeadline(pillar({ streak: 23, judged: 30 }))).toBe("23-day streak");
    expect(pillarHeadline(pillar({ streak: 0, best_streak: 9, judged: 12 }))).toMatch(/best 9/);
    expect(pillarHeadline(pillar({ judged: 0, streak: 0 }))).toBe("Nothing to judge yet");
    expect(pillarHeadline(pillar({ kind: "total", metric: "distance_km", target: 100, value: 42.5 }))).toBe("42.5 of 100 km");
    expect(passesLine(pillar({ misses: 0, passes: 0, passes_left: 0, intact: true }))).toMatch(/every day counts/);
    expect(passesLine(pillar({ misses: 3, passes: 12, passes_left: 9, intact: true }))).toBe("9 of 12 rest passes left");
    expect(passesLine(pillar({ misses: 2, passes: 0, passes_left: 0, intact: false }))).toBe("No rest passes allowed");
  });
  it("only projects when the server did", () => {
    const base = pillar({ kind: "total", metric: "distance_km", target: 100, value: 50, expected: 40 });
    expect(totalPaceLine(base)).toBe("10 km ahead of an even pace");
    expect(totalPaceLine({ ...base, projection: 96.2 })).toMatch(/heading for about 96/);
  });
});

describe("banner line", () => {
  const phase = (over: Partial<PhaseSummary>): PhaseSummary => ({
    id: 1, name: "x", tagline: "tag", emoji: "", color: "#fff", start: "2026-11-01", end: "2026-11-30", state: "active", day_number: 5, total_days: 30,
    days_left: 25, starts_in: null, pct: 0.16, pillars: [], on_track: 0, judged: 0, has_activity_data: true,
    totals: { sessions: 3, duration_s: 0, distance_m: 0, ascent_m: 0, load: null, active_days: 3, families: {} }, ...over,
  });
  it("leads with the first pillar that has something to say", () => {
    const early = pillar({ status: "early" });
    const live = pillar({ id: "p2", status: "on", streak: 5, judged: 5 });
    expect(bannerLine(phase({ pillars: [early, live] }))).toBe("Move 20+ min a day · 5-day streak");
    expect(bannerLine(phase({ pillars: [] }))).toBe("tag");
    expect(bannerLine(phase({ state: "upcoming", starts_in: 3 }))).toBe("tag");
  });
});

describe("dates and templates", () => {
  it("picks the next window that hasn't ended, wrapping the year", () => {
    expect(nextWindow(new Date(2026, 9, 24), [10, 1], [12, 31])).toEqual(["2026-10-01", "2026-12-31"]);
    expect(nextWindow(new Date(2026, 11, 31), [10, 1], [12, 31])).toEqual(["2026-10-01", "2026-12-31"]);
    expect(nextWindow(new Date(2027, 0, 1), [10, 1], [12, 31])).toEqual(["2027-10-01", "2027-12-31"]);
    expect(nextWindow(new Date(2026, 11, 15), [1, 1], [1, 31])).toEqual(["2027-01-01", "2027-01-31"]);
  });
  it("offers No Break November with zero rest passes", () => {
    const t = templates(new Date(2026, 9, 24)).find((x) => x.key === "nobreak")!;
    expect(t.body.start).toBe("2026-11-01");
    expect(t.body.pillars[0]).toMatchObject({ kind: "daily", metric: "moved", passes: 0 });
  });
});

describe("editing", () => {
  it("turns a draft into a request pillar and rejects nonsense", () => {
    expect(pillarOf({ ...draftOf(), target: "30", passes: "2" })).toEqual({ pillar: { kind: "daily", metric: "moved", target: 30, passes: 2, family: null, label: "" } });
    expect(pillarOf({ ...draftOf(), target: "" })).toHaveProperty("error");
    expect(pillarOf({ ...draftOf(), kind: "habit", behaviour: "" })).toHaveProperty("error");
    expect(pillarOf({ ...draftOf(), kind: "habit", behaviour: "alcohol" })).toMatchObject({ pillar: { want: "no" } });
  });
  it("checks the dates", () => {
    const body = { name: "x", tagline: "", emoji: "", color: "#fff", start: "2026-11-30", end: "2026-11-01", pillars: [] };
    expect(validateBody(body)).toMatch(/before/);
    expect(validateBody({ ...body, name: " " })).toMatch(/name/);
    expect(validateBody({ ...body, end: "2026-12-01" })).toBeNull();
  });
});

describe("goals", () => {
  const goal = (over: Partial<PillarResult>): PillarResult => ({ id: "p1", kind: "goal", metric: "run_pace", target: 330, status: "on", ...over });
  it("formats paces as m:ss and other figures with units", () => {
    expect(clock(329.6)).toBe("5:30");
    expect(goalValue("run_pace", 330)).toBe("5:30 /km");
    expect(goalValue("weight_kg", 74.25)).toBe("74.3 kg");
    expect(goalValue("hrv", null)).toBe("—");
  });
  it("describes and heads a goal without inventing data", () => {
    expect(describePillar({ kind: "goal", metric: "weight_kg", target: 75 })).toBe("Weight: 75.0 kg");
    expect(pillarHeadline(goal({ no_data: true }))).toBe("No data yet");
    expect(pillarHeadline(goal({ current: 360, progress: 0.55 }))).toBe("6:00 /km → 5:30 /km · 55% there");
    expect(pillarHeadline(goal({ current: 320, progress: 1, status: "complete" }))).toBe("Reached · 5:20 /km");
  });
  it("reads a pace target as m:ss and rejects anything else", () => {
    expect(pillarOf({ ...draftOf(), kind: "goal", metric: "run_pace", target: "5:30" })).toMatchObject({ pillar: { kind: "goal", target: 330, family: null } });
    expect(pillarOf({ ...draftOf(), kind: "goal", metric: "run_pace", target: "5.5" })).toHaveProperty("error");
    expect(pillarOf({ ...draftOf(), kind: "goal", metric: "weight_kg", target: "72.5" })).toMatchObject({ pillar: { target: 72.5 } });
    expect(draftOf({ kind: "goal", metric: "swim_pace", target: 105 }).target).toBe("1:45");
  });
});
