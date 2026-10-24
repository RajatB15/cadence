import type { Point } from "./types";
import { parseDay } from "./format";

const DAY_MS = 86_400_000;
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/**
 * Trailing average over calendar days (not over the last N readings), one entry per day from the first to the last reading.
 * Days with fewer than `minPoints` readings in the window come out as null, so a chart line breaks over real gaps
 * instead of bridging them or averaging readings that are weeks apart.
 */
export function calendarAverage(points: Point[], window = 7, minPoints = 3): [string, number | null][] {
  if (!points.length) return [];
  const byDay = new Map(points.map((p) => [p.day, p.value]));
  const start = parseDay(points[0].day);
  const end = parseDay(points[points.length - 1].day);
  const out: [string, number | null][] = [];
  for (let t = start.getTime(); t <= end.getTime(); t += DAY_MS) {
    const d = new Date(t);
    const values: number[] = [];
    for (let k = 0; k < window; k++) {
      const v = byDay.get(iso(new Date(t - k * DAY_MS)));
      if (v != null) values.push(v);
    }
    out.push([iso(d), values.length >= minPoints ? +(values.reduce((a, b) => a + b, 0) / values.length).toFixed(2) : null]);
  }
  return out;
}
