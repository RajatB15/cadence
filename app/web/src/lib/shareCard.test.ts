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
});
