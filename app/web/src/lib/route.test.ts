import { describe, expect, it } from "vitest";
import { HEAT, bearing, buildTrack, cameraSigma, joinTracks, chaseHeading, chasePitch, terrainExaggeration, distanceMarks, gradient, locate, paletteAt, sample, smoothPath, steer, turn } from "./route";
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

describe("chase camera", () => {
  // A run heading roughly north with ±15 m of GPS wobble and a couple of tight switchbacks.
  const noisy = () => {
    const n = 1500;
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 2;
    const lat = Array.from({ length: n }, (_, i) => 12.9 + i * 0.00003 + rnd() * 0.00012 + (i > 600 && i < 700 ? Math.sin(i / 4) * 0.0004 : 0));
    const lon = Array.from({ length: n }, (_, i) => 77.6 + rnd() * 0.00012 + (i > 600 && i < 700 ? Math.cos(i / 4) * 0.0004 : 0));
    return buildTrack({ ...fit(n, false), route: lat.map((la, i) => [la, lon[i]]) })!;
  };
  const run = (heading: (p: number) => number, step: (cur: number, target: number) => number) => {
    let cur = heading(0);
    const out = [cur];
    for (let f = 1; f <= 600; f++) {
      cur = step(cur, heading(f / 600));
      out.push(cur);
    }
    return Math.max(...out.slice(1).map((v, i) => Math.abs(turn(v, out[i])))) * 30; // °/s at 30 fps
  };

  it("turns far more calmly than following the instantaneous direction", () => {
    const track = noisy();
    const old = run(
      (p) => bearing(sample(track, p), sample(track, Math.min(1, p + Math.max(0.004, 220 / track.meters)))),
      (cur, target) => (cur + turn(target, cur) * Math.min(1, (1 / 30) * 1.6) + 360) % 360,
    );
    const calm = run((p) => chaseHeading(track, p), (cur, target) => steer(cur, target, 1 / 30));
    expect(calm).toBeLessThanOrEqual(8.001);
    expect(calm).toBeLessThan(old / 2);
  });

  it("never turns faster than the cap, even for a U-turn", () => {
    let h = 0;
    for (let i = 0; i < 30; i++) h = steer(h, 180, 1 / 30);
    expect(Math.abs(turn(h, 0))).toBeLessThanOrEqual(8.001);
    expect(Math.abs(turn(h, 0))).toBeGreaterThan(5);
  });

  it("ignores small differences and settles on the target", () => {
    expect(Math.abs(turn(steer(100, 104, 1 / 30), 100))).toBeLessThan(0.1);
    let h = 0;
    for (let i = 0; i < 30 * 40; i++) h = steer(h, 90, 1 / 30);
    expect(Math.abs(turn(h, 90))).toBeLessThan(6);
  });

  it("looks more top-down on hilly routes", () => {
    const flat = buildTrack(fit(100))!; // 100 m of climb in this fixture
    expect(chasePitch({ ...flat, elevation: [10, 20] })).toBe(62);
    expect(chasePitch({ ...flat, elevation: [0, 120] })).toBe(55);
    expect(chasePitch({ ...flat, elevation: [0, 400] })).toBe(52);
    expect(chasePitch({ ...flat, elevation: null })).toBe(62);
  });

  it("smooths the camera path but starts and ends on the route", () => {
    const n = 800;
    let seed = 3;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 2;
    const lat = Array.from({ length: n }, (_, i) => 12.9 + i * 0.00004);
    const lon = Array.from({ length: n }, () => 77.6 + rnd() * 0.0002); // ±20 m sideways noise
    const track = buildTrack({ ...fit(n, false), route: lat.map((la, i) => [la, lon[i]]) })!;
    const cam = smoothPath(track, 300);
    const wobble = (at: (p: number) => { lon: number }) => {
      const xs = Array.from({ length: 400 }, (_, i) => at(0.1 + (i / 399) * 0.8).lon);
      return Math.max(...xs) - Math.min(...xs);
    };
    expect(wobble(cam)).toBeLessThan(wobble((p) => sample(track, p)) / 4);
    const start = sample(track, 0);
    const end = sample(track, 1);
    expect(cam(0).lat).toBeCloseTo(start.lat, 6);
    expect(cam(0).lon).toBeCloseTo(start.lon, 6);
    expect(cam(1).lat).toBeCloseTo(end.lat, 6);
    expect(cam(1).lon).toBeCloseTo(end.lon, 6);
  });

  it("smooths over more ground when the flight is faster, within bounds", () => {
    expect(cameraSigma(10_000, 12)).toBeLessThan(cameraSigma(10_000, 6));
    expect(cameraSigma(500, 12)).toBe(120);
    expect(cameraSigma(500_000, 6)).toBe(2500);
  });

  it("exaggerates terrain more when the relief is small next to the route", () => {
    const long = buildTrack(fit(2000, false))!; // ~22 km north-south
    const hilly = terrainExaggeration({ ...long, elevation: [800, 1600] });
    const mild = terrainExaggeration({ ...long, elevation: [800, 830] });
    expect(hilly).toBeGreaterThan(1.4);
    expect(mild).toBeGreaterThan(hilly);
    expect(mild).toBeLessThanOrEqual(3.5);
    expect(terrainExaggeration({ ...long, elevation: [0, 8000] })).toBe(1.4);
    expect(terrainExaggeration({ ...long, elevation: null })).toBe(1.4);
  });
});

describe("joinTracks", () => {
  it("runs distance and clock on across legs and keeps one continuous line", () => {
    const a = buildTrack(fit(50))!;
    const b = buildTrack(fit(30))!;
    const j = joinTracks([a, null, b])!;
    expect(j.points).toHaveLength(80);
    expect(j.points[50].dist).toBeCloseTo(a.points[49].dist! + 0, 5);
    expect(j.points[79].dist!).toBeCloseTo(49 * 11.1 + 29 * 11.1, 5);
    expect(j.points[79].t).toBe(49 + 29);
    expect(j.progress[0]).toBe(0);
    expect(j.progress[79]).toBe(1);
  });
  it("returns the single track as is and null for none", () => {
    const a = buildTrack(fit(10))!;
    expect(joinTracks([a])).toBe(a);
    expect(joinTracks([null])).toBeNull();
  });
});
