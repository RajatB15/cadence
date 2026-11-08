/**
 * Local frecency, "usual for this meal" clustering and portion memory (docs/food-logging-design.md 2b, 2c), computed from what this
 * device has logged plus the server's recent-dish list. Used when /api/food/quick is absent or while it loads. Pure except the
 * small localStorage-backed history (try/catch everywhere; works without it). Nothing leaves the device.
 */
import { shiftDay } from "./food";
import type { Meal } from "./types";

export interface LogRecord {
  /** YYYY-MM-DD of the eating day. */
  day: string;
  meal: Meal;
  dishId: number;
  servings: number;
  unit?: string | null;
}

export const HALF_LIFE_DAYS = 14;

const dayNumber = (day: string): number => {
  const [y, m, d] = day.split("-").map(Number);
  return Math.floor(Date.UTC(y, m - 1, d) / 86_400_000);
};
const weekday = (day: string) => new Date(dayNumber(day) * 86_400_000).getUTCDay();

/** Meal for the clock: before 11 breakfast, to 15:30 lunch, to 18:30 snack, then dinner. */
export function mealForTime(d: Date): Meal {
  const m = d.getHours() * 60 + d.getMinutes();
  return m < 11 * 60 ? "breakfast" : m < 15 * 60 + 30 ? "lunch" : m < 18 * 60 + 30 ? "snack" : "dinner";
}

/** f(d) = sum w * 0.5^(age/14) * (1 + 0.5 same meal + 0.3 same weekday), normalised to 0..1. Dishes seen once are capped at 0.2. */
export function frecencyScores(logs: LogRecord[], today: string, meal: Meal): Map<number, number> {
  const raw = new Map<number, number>();
  const count = new Map<number, number>();
  const t = dayNumber(today);
  const wd = weekday(today);
  for (const l of logs) {
    const age = Math.max(0, t - dayNumber(l.day));
    const w = Math.pow(0.5, age / HALF_LIFE_DAYS) * (1 + (l.meal === meal ? 0.5 : 0) + (weekday(l.day) === wd ? 0.3 : 0));
    raw.set(l.dishId, (raw.get(l.dishId) ?? 0) + w);
    count.set(l.dishId, (count.get(l.dishId) ?? 0) + 1);
  }
  const max = Math.max(0, ...raw.values());
  const out = new Map<number, number>();
  if (max <= 0) return out;
  for (const [id, v] of raw) out.set(id, (count.get(id) ?? 0) >= 2 ? v / max : Math.min(0.2, v / max));
  return out;
}

/** Server-side recency (most recent first) as pseudo logs, so a fresh device still ranks recent dishes higher. */
export function logsFromRecent(ids: number[], today: string, meal: Meal): LogRecord[] {
  return ids.slice(0, 30).map((dishId, i) => ({ day: shiftDay(today, -Math.min(i, 20)), meal, dishId, servings: 1 }));
}

export interface Usual {
  meal: Meal;
  /** Dish ids with the median servings across the cluster's days. */
  items: { dishId: number; servings: number; unit?: string | null }[];
  days: number;
  score: number;
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};

/** Sets of dishes per day and meal over the last 60 days, clustered by Jaccard >= 0.6; clusters with 3+ days, ranked by recency. */
export function usualMeals(logs: LogRecord[], today: string, meal: Meal): Usual[] {
  const t = dayNumber(today);
  const byDay = new Map<string, Map<number, LogRecord>>();
  for (const l of logs) {
    if (l.meal !== meal || t - dayNumber(l.day) > 60 || l.day === today) continue;
    const m = byDay.get(l.day) ?? new Map();
    m.set(l.dishId, l);
    byDay.set(l.day, m);
  }
  const clusters: { ids: Set<number>; days: string[]; logs: LogRecord[] }[] = [];
  for (const [day, m] of [...byDay].sort((a, b) => (a[0] < b[0] ? 1 : -1))) {
    const ids = new Set(m.keys());
    const hit = clusters.find((c) => {
      const inter = [...ids].filter((x) => c.ids.has(x)).length;
      return inter / (ids.size + c.ids.size - inter) >= 0.6;
    });
    if (hit) {
      hit.days.push(day);
      hit.logs.push(...m.values());
      ids.forEach((x) => hit.ids.add(x));
    } else clusters.push({ ids, days: [day], logs: [...m.values()] });
  }
  const wd = weekday(today);
  return clusters
    .filter((c) => c.days.length >= 3)
    .map((c) => ({
      meal,
      days: c.days.length,
      score: c.days.reduce((a, d) => a + Math.pow(0.5, (t - dayNumber(d)) / HALF_LIFE_DAYS) + (weekday(d) === wd ? 0.3 / c.days.length : 0), 0),
      items: [...c.ids].map((dishId) => {
        const ls = c.logs.filter((l) => l.dishId === dishId);
        return { dishId, servings: median(ls.map((l) => l.servings)), unit: ls[ls.length - 1]?.unit ?? null };
      }),
    }))
    .sort((a, b) => b.score - a.score);
}

/** Portion memory: the last servings used per dish; after three identical amounts the dish counts as habitual (the same default). */
export function portionMemory(logs: LogRecord[]): Record<number, { servings: number; unit?: string | null; habitual: boolean }> {
  const out: Record<number, { servings: number; unit?: string | null; habitual: boolean }> = {};
  const lastN = new Map<number, number[]>();
  for (const l of [...logs].reverse()) {
    const xs = lastN.get(l.dishId) ?? [];
    if (xs.length < 3) xs.push(l.servings);
    lastN.set(l.dishId, xs);
    if (!out[l.dishId]) out[l.dishId] = { servings: l.servings, unit: l.unit ?? null, habitual: false };
  }
  for (const [id, xs] of lastN) out[id].habitual = xs.length === 3 && xs.every((x) => x === xs[0]);
  return out;
}

// ---- device history ------------------------------------------------------------------------------------------------------

const KEY = "cadence.food.history";
const MAX_RECORDS = 600;
let memoryOnly: LogRecord[] = [];

const valid = (x: unknown): x is LogRecord =>
  !!x && typeof x === "object" && typeof (x as LogRecord).day === "string" && typeof (x as LogRecord).dishId === "number" && typeof (x as LogRecord).servings === "number";

export function readHistory(): LogRecord[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(valid) : memoryOnly;
  } catch {
    return memoryOnly;
  }
}

export function recordHistory(add: LogRecord[]): void {
  const next = [...readHistory(), ...add].slice(-MAX_RECORDS);
  memoryOnly = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* private mode or full: the in-memory copy still serves this session */
  }
}
