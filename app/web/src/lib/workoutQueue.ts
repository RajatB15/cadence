import type { GymExerciseStep, GymLastLoad, GymLoggedSet, GymStep, GymWorkoutEntry } from "./types";

/**
 * The workout runner's logic, kept pure: a session's step tree is unrolled into a queue of sets and rests (rounds and sets expanded),
 * and a run is a plain JSON object (so it can be saved in the browser and resumed). Nothing here touches the clock or the network.
 */

export interface Target { reps?: number; seconds?: number; distance_m?: number; calories?: number }
export interface WorkItem {
  kind: "work";
  id: string;
  key: string; // the step this set belongs to (all sets of one exercise share it)
  exercise?: string;
  name?: string;
  block: string;
  round: number;
  rounds: number;
  set: number;
  sets: number;
  target: Target;
  load?: string;
  restAfter: number;
  note?: string;
}
export interface RestItem { kind: "rest"; id: string; seconds: number }
export type QueueItem = WorkItem | RestItem;
export interface SetResult { done: boolean; reps?: number; seconds?: number; distance_m?: number; calories?: number; load?: string }
export interface Run { queue: QueueItem[]; idx: number; results: Record<string, SetResult>; startedAt: number; setting: "gym" | "home" }

const MEASURES = ["reps", "seconds", "distance_m", "calories"] as const;

export function buildQueue(steps: GymStep[]): QueueItem[] {
  const out: QueueItem[] = [];
  let n = 0;
  const id = () => `q${n++}`;
  const walk = (list: GymStep[], block: string, round: number, rounds: number, trail: string) => {
    list.forEach((s, i) => {
      const key = `${trail}/${i}`;
      if (s.type === "rest") {
        out.push({ kind: "rest", id: id(), seconds: s.seconds });
      } else if (s.type === "group") {
        for (let r = 1; r <= s.rounds; r++) {
          walk(s.steps, s.title || "Round", r, s.rounds, `${key}#${r}`);
          if (r < s.rounds && s.rest_s) out.push({ kind: "rest", id: id(), seconds: s.rest_s });
        }
      } else {
        const e = s as GymExerciseStep;
        const sets = Math.max(1, e.sets ?? 1);
        const target: Target = {};
        for (const m of MEASURES) if (e[m] != null) target[m] = e[m];
        for (let k = 1; k <= sets; k++) {
          out.push({ kind: "work", id: id(), key, exercise: e.exercise, name: e.name, block, round, rounds, set: k, sets, target, load: e.load, restAfter: k < sets ? e.rest_s ?? 0 : 0, note: e.note });
        }
      }
    });
  };
  walk(steps, "", 1, 1, "");
  return out;
}

export const startRun = (steps: GymStep[], setting: "gym" | "home", now: number): Run => ({ queue: buildQueue(steps), idx: 0, results: {}, startedAt: now, setting });

export const currentItem = (r: Run): QueueItem | undefined => r.queue[r.idx];
export const workItems = (r: Run): WorkItem[] => r.queue.filter((q): q is WorkItem => q.kind === "work");
export const isFinished = (r: Run) => r.idx >= r.queue.length;

/** Index of the next work item at or after `from`, skipping rests. */
function nextWork(queue: QueueItem[], from: number): number {
  let i = from;
  while (i < queue.length && queue[i].kind === "rest") i++;
  return i;
}

/** Records the current set as done and moves on; returns the rest to take now (the set's own rest, or a rest step that follows). */
export function finishSet(r: Run, result: Omit<SetResult, "done">): { run: Run; rest: number } {
  const it = r.queue[r.idx];
  if (!it || it.kind !== "work") return { run: r, rest: 0 };
  const results = { ...r.results, [it.id]: { ...result, done: true } };
  let idx = r.idx + 1;
  let rest = it.restAfter;
  if (idx < r.queue.length && r.queue[idx].kind === "rest") {
    rest = Math.max(rest, (r.queue[idx] as RestItem).seconds);
    idx = nextWork(r.queue, idx);
  }
  return { run: { ...r, idx, results }, rest };
}

/** Skips the current set (kept in the log as not done). */
export function skipSet(r: Run): Run {
  const it = r.queue[r.idx];
  if (!it || it.kind !== "work") return r;
  return { ...r, idx: nextWork(r.queue, r.idx + 1), results: { ...r.results, [it.id]: { done: false } } };
}

/** Skips every remaining set of the current exercise. */
export function skipExercise(r: Run): Run {
  const it = r.queue[r.idx];
  if (!it || it.kind !== "work") return r;
  const results = { ...r.results };
  let idx = r.idx;
  while (idx < r.queue.length) {
    const q = r.queue[idx];
    if (q.kind === "work" && q.key !== it.key) break;
    if (q.kind === "work") results[q.id] = { done: false };
    idx++;
  }
  return { ...r, idx: nextWork(r.queue, idx), results };
}

/** Steps back to the previous set and clears its result, so it can be redone. */
export function goBack(r: Run): Run {
  let i = r.idx - 1;
  while (i >= 0 && r.queue[i].kind === "rest") i--;
  if (i < 0) return r;
  const results = { ...r.results };
  delete results[r.queue[i].id];
  return { ...r, idx: i, results };
}

/** One more set of the current exercise, straight after the current one (the exercise's set count goes up everywhere). */
export function addSet(r: Run): Run {
  const it = r.queue[r.idx];
  if (!it || it.kind !== "work") return r;
  const sameKey = (q: QueueItem): q is WorkItem => q.kind === "work" && q.key === it.key && q.round === it.round;
  const last = [...r.queue].map((q, i) => ({ q, i })).filter(({ q }) => sameKey(q)).pop()!;
  const lastItem = last.q as WorkItem;
  const extra: WorkItem = { ...lastItem, id: `${lastItem.id}+${lastItem.sets + 1}`, set: lastItem.sets + 1, sets: lastItem.sets + 1, restAfter: 0 };
  const queue = r.queue.map((q) => (sameKey(q) ? { ...q, sets: q.sets + 1 } : q));
  const prev = queue[last.i] as WorkItem;
  queue[last.i] = { ...prev, restAfter: prev.restAfter || it.restAfter };
  queue.splice(last.i + 1, 0, { ...extra, restAfter: 0 });
  return { ...r, queue };
}

/** Replaces the exercise in every set of the current step that hasn't been done yet (the sets already done keep their own exercise). */
export function swapRemaining(r: Run, exercise: string, name?: string): Run {
  const it = r.queue[r.idx];
  if (!it || it.kind !== "work") return r;
  const queue = r.queue.map((q, i) => (q.kind === "work" && q.key === it.key && i >= r.idx && !(q.id in r.results) ? { ...q, exercise, name, key: `${q.key}~${exercise}`, load: undefined } : q));
  return { ...r, queue };
}

/** Fills the starting load from what you used last time, only where the plan didn't set one. */
export function withLastLoads(r: Run, loads: Record<string, GymLastLoad>): Run {
  return { ...r, queue: r.queue.map((q) => (q.kind === "work" && !q.load && q.exercise && loads[q.exercise] ? { ...q, load: loads[q.exercise].load } : q)) };
}

export function progress(r: Run): { done: number; total: number; skipped: number } {
  const work = workItems(r);
  const res = work.map((w) => r.results[w.id]);
  return { done: res.filter((x) => x?.done).length, total: work.length, skipped: res.filter((x) => x && !x.done).length };
}

/** The workout as a log: per exercise (in order) its sets, with what was aimed for so next time's suggestion can compare. */
export function toEntries(r: Run, nameOf: (id: string) => string | undefined): GymWorkoutEntry[] {
  const order: string[] = [];
  const map = new Map<string, GymWorkoutEntry>();
  for (const w of workItems(r)) {
    const res = r.results[w.id];
    if (!res) continue;
    const ident = w.exercise ?? `name:${w.name ?? "Exercise"}`;
    let e = map.get(ident);
    if (!e) {
      e = w.exercise ? { exercise: w.exercise, sets: [] } : { name: w.name ?? "Exercise", sets: [] };
      map.set(ident, e);
      order.push(ident);
    }
    const set: GymLoggedSet = { done: res.done };
    for (const m of MEASURES) if (res[m] != null) set[m] = res[m];
    if (res.load) set.load = res.load;
    if (w.target.reps != null) set.target_reps = w.target.reps;
    e.sets.push(set);
  }
  void nameOf;
  return order.map((k) => map.get(k)!);
}

/** Kilograms moved across done sets with a numeric load and reps, or null when nothing has both. */
export function volumeKg(entries: GymWorkoutEntry[]): number | null {
  let total = 0;
  let any = false;
  for (const e of entries) {
    for (const s of e.sets) {
      const kg = s.load ? Number(s.load.toLowerCase().replace(/kgs?$/, "").replace(",", ".").trim()) : NaN;
      if (s.done && s.reps != null && Number.isFinite(kg) && kg > 0) {
        total += kg * s.reps;
        any = true;
      }
    }
  }
  return any ? Math.round(total) : null;
}

export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Kilograms from text like "40", "40 kg" or "42,5"; null for bodyweight, bands or anything not a plain number. */
export function parseKg(load: string | undefined | null): number | null {
  const m = String(load ?? "").toLowerCase().trim().match(/^(\d+(?:[.,]\d+)?)\s*(kg|kgs)?$/);
  return m ? Number(m[1].replace(",", ".")) : null;
}

/** A load nudged by `delta` kg (never below zero); from nothing or text it starts at the nudge. */
export function bumpLoad(load: string | undefined, delta: number): string {
  const kg = parseKg(load) ?? 0;
  const next = Math.max(0, Math.round((kg + delta) * 100) / 100);
  return next === 0 ? "" : `${next} kg`;
}
