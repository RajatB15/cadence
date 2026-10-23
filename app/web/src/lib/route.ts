import type { FitData } from "./types";

export type TrackKey = "speed" | "hr" | "alt";

export interface TrackPoint {
  lat: number;
  lon: number;
  t: number | null;
  hr: number | null;
  speed: number | null;
  alt: number | null;
  dist: number | null;
}

export interface Track {
  points: TrackPoint[];
  /** Cumulative ground distance along the line, 0..1 — the same measure MapLibre uses for line-progress. */
  progress: number[];
  meters: number;
  bounds: [[number, number], [number, number]];
  elevation: [number, number] | null;
}

export interface Gradient {
  stops: [number, string][];
  lo: number;
  hi: number;
}

export const HEAT = ["#3d6bff", "#6cc7ff", "#5be3b0", "#c8f560", "#ffbe55", "#ff6a55"];
export const RELIEF = ["#1f6f5c", "#5be3b0", "#c8f560", "#d9b26a", "#f2e8cf"];
const MAX_STOPS = 160;

const EARTH = 6_371_008.8;
const rad = (d: number) => (d * Math.PI) / 180;

export function haversine(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Compass bearing from a to b in degrees (0 = north, clockwise). */
export function bearing(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const y = Math.sin(rad(b.lon - a.lon)) * Math.cos(rad(b.lat));
  const x = Math.cos(rad(a.lat)) * Math.sin(rad(b.lat)) - Math.sin(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(rad(b.lon - a.lon));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

export function buildTrack(fit: FitData): Track | null {
  const tr = fit.track;
  const col = (k: keyof TrackPoint, i: number) => tr?.[k]?.[i] ?? null;
  const points: TrackPoint[] =
    tr?.lat?.length && tr.lon?.length
      ? tr.lat.flatMap((lat, i) => {
          const lon = tr.lon![i];
          if (lat == null || lon == null) return [];
          return [{ lat, lon, t: col("t", i), hr: col("hr", i), speed: col("speed", i), alt: col("alt", i), dist: col("dist", i) }];
        })
      : fit.route.map(([lat, lon]) => ({ lat, lon, t: null, hr: null, speed: null, alt: null, dist: null }));
  if (points.length < 2) return null;

  const cum = [0];
  for (let i = 1; i < points.length; i++) cum.push(cum[i - 1] + haversine(points[i - 1], points[i]));
  const meters = cum[cum.length - 1];
  const progress = cum.map((d) => (meters ? d / meters : 0));
  const lons = points.map((p) => p.lon);
  const lats = points.map((p) => p.lat);
  const alts = points.map((p) => p.alt).filter((v): v is number => v != null);
  return {
    points,
    progress,
    meters,
    bounds: [
      [Math.min(...lons), Math.min(...lats)],
      [Math.max(...lons), Math.max(...lats)],
    ],
    elevation: alts.length ? [Math.min(...alts), Math.max(...alts)] : null,
  };
}

/** Moving average that skips gaps, so GPS noise doesn't turn the line into confetti. */
export function smooth(values: (number | null)[], window: number): (number | null)[] {
  const half = Math.max(0, Math.floor(window / 2));
  return values.map((v, i) => {
    if (v == null) return null;
    let sum = 0;
    let n = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(values.length - 1, i + half); j++) {
      const x = values[j];
      if (x != null) {
        sum += x;
        n++;
      }
    }
    return sum / n;
  });
}

function quantile(sorted: number[], q: number): number {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  return sorted[lo] + (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]) * (pos - lo);
}

const hex = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));

export function paletteAt(palette: string[], x: number): string {
  const f = Math.min(1, Math.max(0, Number.isFinite(x) ? x : 0)) * (palette.length - 1);
  const i = Math.min(Math.floor(f), palette.length - 2);
  const a = hex(palette[i]);
  const b = hex(palette[i + 1]);
  return `#${a.map((v, k) => Math.round(v + (b[k] - v) * (f - i)).toString(16).padStart(2, "0")).join("")}`;
}

/** Colour stops along line-progress for one channel, or null when the channel is mostly missing. */
export function gradient(track: Track, key: TrackKey, palette: string[]): Gradient | null {
  const raw = track.points.map((p) => p[key]);
  const present = raw.filter((v): v is number => v != null);
  if (present.length < Math.max(2, raw.length * 0.2)) return null;
  const values = smooth(raw, Math.max(3, Math.round(raw.length / 120)));
  const sorted = values.filter((v): v is number => v != null).sort((a, b) => a - b);
  const lo = quantile(sorted, 0.05);
  const hi = Math.max(quantile(sorted, 0.95), lo + 1e-6);

  const n = values.length;
  const buckets = Math.min(MAX_STOPS, n);
  const stops: [number, string][] = [];
  let last = paletteAt(palette, 0.5);
  for (let b = 0; b < buckets; b++) {
    const from = Math.floor((b * n) / buckets);
    const to = Math.max(from + 1, Math.floor(((b + 1) * n) / buckets));
    const chunk = values.slice(from, to).filter((v): v is number => v != null);
    if (chunk.length) last = paletteAt(palette, (chunk.reduce((s, v) => s + v, 0) / chunk.length - lo) / (hi - lo));
    const at = b === 0 ? 0 : b === buckets - 1 ? 1 : track.progress[Math.floor((from + to) / 2)];
    if (!stops.length || at > stops[stops.length - 1][0]) stops.push([at, last]);
  }
  if (stops[stops.length - 1][0] < 1) stops.push([1, last]);
  return { stops, lo, hi };
}

/** Index + fraction of the segment at a given line progress (binary search). */
export function locate(progress: number[], p: number): { i: number; f: number } {
  if (p <= 0) return { i: 0, f: 0 };
  if (p >= 1) return { i: progress.length - 2, f: 1 };
  let lo = 0;
  let hi = progress.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (progress[mid] <= p) lo = mid;
    else hi = mid;
  }
  const span = progress[hi] - progress[lo];
  return { i: lo, f: span > 0 ? (p - progress[lo]) / span : 0 };
}

/** Distance markers at a round interval (≤ 20 of them), placed by the watch's own distance when recorded. */
export function distanceMarks(track: Track): { km: number; lat: number; lon: number }[] {
  const recorded = track.points.filter((p) => p.dist != null);
  const total = recorded.length ? recorded[recorded.length - 1].dist! : track.meters;
  const step = [1, 2, 5, 10, 20, 50, 100].find((s) => total / 1000 / s <= 20) ?? 200;
  const marks: { km: number; lat: number; lon: number }[] = [];
  let from = 0;
  for (let km = step; km * 1000 < total; km += step) {
    if (recorded.length) {
      const i = track.points.findIndex((p, j) => j >= from && p.dist != null && p.dist >= km * 1000);
      if (i < 0) break;
      from = i;
      marks.push({ km, lat: track.points[i].lat, lon: track.points[i].lon });
    } else {
      const at = sample(track, (km * 1000) / track.meters);
      marks.push({ km, lat: at.lat, lon: at.lon });
    }
  }
  return marks;
}

export function sample(track: Track, p: number): TrackPoint {
  const { i, f } = locate(track.progress, p);
  const a = track.points[i];
  const b = track.points[Math.min(i + 1, track.points.length - 1)];
  const mix = (x: number | null, y: number | null) => (x == null ? y : y == null ? x : x + (y - x) * f);
  return {
    lat: a.lat + (b.lat - a.lat) * f,
    lon: a.lon + (b.lon - a.lon) * f,
    t: mix(a.t, b.t),
    hr: mix(a.hr, b.hr),
    speed: mix(a.speed, b.speed),
    alt: mix(a.alt, b.alt),
    dist: mix(a.dist, b.dist),
  };
}
