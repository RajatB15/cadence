import { describe, expect, it } from "vitest";
import { buildTrack } from "./route";
import { VIDEO_SPEEDS, buildCardModel, fileName, formatClock, projectRoute, videoSeconds } from "./shareCard";
import type { ActivityDetail, FitData } from "./types";

const fit = (route: [number, number][]): FitData =>
  ({ streams: {}, stream_stats: {}, route, zones: null, messages: {}, streamed_counts: {}, unknown_messages: [], decode_errors: [] }) as FitData;

const detail = (over: Partial<ActivityDetail["activity"]>, f: FitData | null): ActivityDetail =>
  ({
    activity: { id: 1, source_id: "demo", start_time_utc: "2026-01-02 07:00:00", timezone: "UTC", type: "running", family: "run", name: "Morning Run", duration_s: 1800, distance_m: 5000, avg_hr: null, max_hr: null, elevation_gain_m: null, calories: null, training_load: null, ...over },
    garmin_summary: null, detail: null, workouts: null, fit: f, missing: [], stored: {}, coach: null, strength: null, planned: null,
  }) as ActivityDetail;

describe("share card", () => {
  it("scales video length by speed", () => {
    expect(VIDEO_SPEEDS.map(videoSeconds)).toEqual([12, 9.6, 8, 6]);
  });

  it("omits stats that are missing rather than showing zero", () => {
    const m = buildCardModel(detail({}, null), "#fff", "Run");
    expect(m.stats.map((s) => s.label)).toEqual(["Distance", "Time", "Avg pace"]);
    expect(m.track).toBeNull();
    expect(m.stats[2].value).toBe("6:00");
  });

  it("builds a track only when there is a route", () => {
    const route: [number, number][] = [[50, 8], [50.01, 8.01], [50.02, 8.0]];
    expect(buildCardModel(detail({}, fit(route)), "#fff", "Run").track).not.toBeNull();
    expect(buildCardModel(detail({}, fit([])), "#fff", "Run").track).toBeNull();
  });

  it("fits the route inside its box without stretching", () => {
    const track = buildTrack(fit([[50, 8], [50.02, 8], [50.02, 8.001]]))!;
    const box = { x: 10, y: 20, w: 400, h: 300 };
    const pts = projectRoute(track, box);
    for (const [x, y] of pts) {
      expect(x).toBeGreaterThanOrEqual(box.x - 1e-6);
      expect(x).toBeLessThanOrEqual(box.x + box.w + 1e-6);
      expect(y).toBeGreaterThanOrEqual(box.y - 1e-6);
      expect(y).toBeLessThanOrEqual(box.y + box.h + 1e-6);
    }
    expect(pts[0][1]).toBeGreaterThan(pts[1][1]); // north is up
  });

  it("formats clocks and file names", () => {
    expect(formatClock(3725)).toBe("1:02:05");
    expect(formatClock(65)).toBe("1:05");
    const m = buildCardModel(detail({ name: "Café run!" }, null), "#fff", "Run");
    expect(fileName(m, "png", true)).toBe("cadence-caf-run-transparent.png");
  });

  it("fills a strength card from blocks, exercises, zones and heart rate", () => {
    const f = { ...fit([]), streams: { heart_rate: Array.from({ length: 200 }, (_, i) => 90 + (i % 40)) }, zones: [{ zone: 2, low: 100, high: 120, seconds: 600 }, { zone: 4, low: 140, high: 160, seconds: 200 }] } as FitData;
    const d = detail({ family: "strength", type: "strength_training", distance_m: null }, f);
    d.garmin_summary = { totalSets: 20, totalReps: 180, summarizedExerciseSets: [{ category: "BENCH_PRESS", sets: 4, reps: 32 }, { category: "ROW", sets: 5, reps: 50 }] };
    const m = buildCardModel(d, "#f00", "Strength");
    expect(m.stats.map((s) => s.label)).toEqual(["Time", "Sets", "Reps"]);
    expect(m.panel.hr).toHaveLength(140);
    expect(m.panel.zones?.map((z) => Math.round(z.pct))).toEqual([75, 25]);
    expect(m.panel.rowsTitle).toBe("Exercises");
    expect(m.panel.rows.map((r) => r.label)).toEqual(["Row", "Bench Press"]);
    expect(m.panel.rows[0].right).toBe("5 sets · 50 reps");
  });

  it("shows the saved class, not Garmin's UNKNOWN sets", () => {
    const d = detail({ family: "strength", type: "strength_training", distance_m: null }, null);
    d.garmin_summary = { summarizedExerciseSets: [{ category: "UNKNOWN", sets: 8, reps: 80 }] };
    expect(buildCardModel(d, "#f00", "Strength").panel.rows).toEqual([]);
    d.strength = { label: { text: "x", summary: {} as never, blocks: [{ name: "Endurance WOD: 50s ON, 15s OFF", kind: "conditioning", exercises: [{}, {}, {}] as never }] }, templates: [] } as never;
    const m = buildCardModel(d, "#f00", "Strength");
    expect(m.panel.rowsTitle).toBe("Class blocks");
    expect(m.panel.rows.map((r) => [r.label, r.right])).toEqual([["Endurance WOD: 50s ON, 15s OFF", "3 exercises"]]);
  });

  it("leaves the panel empty when nothing was recorded", () => {
    const m = buildCardModel(detail({ family: "strength" }, null), "#f00", "Strength");
    expect(m.panel).toEqual({ hr: null, zones: null, rowsTitle: "", rows: [] });
  });
});
