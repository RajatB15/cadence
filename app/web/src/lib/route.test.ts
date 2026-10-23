import { describe, expect, it } from "vitest";
import { HEAT, bearing, buildTrack, distanceMarks, gradient, locate, paletteAt, sample } from "./route";
import type { FitData } from "./types";

function fit(n: number, withTrack = true): FitData {
  const lat = Array.from({ length: n }, (_, i) => 12.9 + i * 0.0001);
  const lon = Array.from({ length: n }, () => 77.6);
  return {
    streams: {},
    stream_stats: {},
    route: lat.map((la, i) => [la, lon[i]]),
    track: withTrack
      ? {
          lat,
          lon,
          t: lat.map((_, i) => i),
          hr: lat.map((_, i) => 120 + i),
          speed: lat.map(() => 3),
          alt: lat.map((_, i) => 900 + i),
          dist: lat.map((_, i) => i * 11.1),
        }
      : undefined,
    zones: null,
    messages: {},
    streamed_counts: {},
    unknown_messages: [],
    decode_errors: [],
  };
}

describe("route", () => {
  it("builds progress by ground distance", () => {
    const t = buildTrack(fit(300))!;
    expect(t.progress[0]).toBe(0);
    expect(t.progress.at(-1)).toBe(1);
    expect(t.progress.every((p, i) => i === 0 || p >= t.progress[i - 1])).toBe(true);
    expect(t.meters).toBeGreaterThan(3200);
    expect(t.meters).toBeLessThan(3400);
    expect(t.elevation).toEqual([900, 1199]);
  });

  it("falls back to the bare route when there is no track", () => {
    const t = buildTrack(fit(10, false))!;
    expect(t.points[3].hr).toBeNull();
    expect(gradient(t, "hr", HEAT)).toBeNull();
  });

  it("emits strictly increasing gradient stops spanning the line", () => {
    const g = gradient(buildTrack(fit(2000))!, "hr", HEAT)!;
    expect(g.stops[0][0]).toBe(0);
    expect(g.stops.at(-1)![0]).toBe(1);
    expect(g.stops.length).toBeLessThanOrEqual(161);
    expect(g.stops.every(([p], i) => i === 0 || p > g.stops[i - 1][0])).toBe(true);
    // rising heart rate runs cool to hot
    expect(g.stops[0][1]).toBe(HEAT[0]);
    expect(g.stops.at(-1)![1]).toBe(HEAT.at(-1));
  });

  it("interpolates palette colours and positions", () => {
    expect(paletteAt(["#000000", "#ffffff"], 0.5)).toBe("#808080");
    expect(paletteAt(HEAT, 2)).toBe(HEAT.at(-1));
    expect(locate([0, 0.5, 1], 0.75)).toEqual({ i: 1, f: 0.5 });
    const t = buildTrack(fit(3))!;
    expect(sample(t, 0.5).alt).toBeCloseTo(901);
  });

  it("places distance marks by recorded distance and computes bearings", () => {
    const marks = distanceMarks(buildTrack(fit(300))!);
    expect(marks.map((m) => m.km)).toEqual([1, 2, 3]);
    expect(bearing({ lat: 0, lon: 0 }, { lat: 1, lon: 0 })).toBeCloseTo(0);
    expect(bearing({ lat: 0, lon: 0 }, { lat: 0, lon: 1 })).toBeCloseTo(90);
  });
});
