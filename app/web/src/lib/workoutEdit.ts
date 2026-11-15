import type { GymExercise } from "./types";
import { isFinished, type QueueItem, type Run, type RunEdit, type SetResult, type Target, type WorkItem } from "./workoutQueue";

/**
 * Changing a workout while you are doing it (a machine is taken, you are short of time, you want a different load). Pure functions
 * on a Run: sets already done are never touched, ids stay stable so the log keeps grouping them under the same exercise, and the
 * saved session is not changed. Every edit is added to `run.edits` so the summary can say what changed.
 */

/** What is still to do of one exercise in one round: the undone sets from `idx` on that share a step, plus the rest steps after them. */
export interface Segment {
  id: string; // `${key}@${round}`
  key: string;
  round: number;
  block: string;
  exercise?: string;
  name?: string;
  items: WorkItem[];
  /** Every queue entry the segment owns, in order (its sets and the rest steps trailing them). */
  all: QueueItem[];
  /** Sets of this exercise in this round already finished before now. */
  doneBefore: number;
  target: Target;
  load?: string;
  restAfter: number;
}

export const MAX_WORK_ITEMS = 300;
export const MAX_SETS = 40;
const segId = (key: string, round: number) => `${key}@${round}`;

export function remaining(r: Run): Segment[] {
  const out: Segment[] = [];
  let cur: Segment | undefined;
  for (let i = r.idx; i < r.queue.length; i++) {
    const q = r.queue[i];
    if (q.kind === "rest") {
      if (cur) cur.all.push(q);
      continue;
    }
    if (!cur || cur.key !== q.key || cur.round !== q.round) {
      const done = r.queue.slice(0, r.idx).filter((x) => x.kind === "work" && x.key === q.key && x.round === q.round && r.results[x.id]?.done).length;
      cur = { id: segId(q.key, q.round), key: q.key, round: q.round, block: q.block, exercise: q.exercise, name: q.name, items: [], all: [], doneBefore: done, target: q.target, load: q.load, restAfter: q.restAfter };
      out.push(cur);
    }
    cur.items.push(q);
    cur.all.push(q);
  }
  return out;
}

const record = (r: Run, e: RunEdit): RunEdit[] => [...(r.edits ?? []), e];
const nameOf = (s: Segment) => s.name ?? s.exercise ?? "Exercise";

function rebuild(r: Run, segs: Segment[], edit: RunEdit): Run {
  const queue = [...r.queue.slice(0, r.idx), ...segs.flatMap((s) => s.all)];
  return { ...r, queue, edits: record(r, edit) };
}

/** "Machine busy": the rest of the current exercise moves after the next one, or to the end. Nothing already done changes. */
export function deferExercise(r: Run, where: "after_next" | "end"): Run {
  const segs = remaining(r);
  if (segs.length < 2) return r;
  const [cur, ...rest] = segs;
  const at = where === "end" ? rest.length : 1;
  const order = [...rest.slice(0, at), cur, ...rest.slice(at)];
  return rebuild(r, order, { kind: "defer", label: nameOf(cur) });
}

/** Moves a remaining exercise one place earlier or later among the remaining ones. */
export function moveSegment(r: Run, id: string, dir: -1 | 1): Run {
  const segs = remaining(r);
  const i = segs.findIndex((s) => s.id === id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= segs.length) return r;
  const order = [...segs];
  [order[i], order[j]] = [order[j], order[i]];
  return rebuild(r, order, { kind: "reorder", label: nameOf(segs[i]) });
}

/** Takes an exercise out of today. Unlike skipping, nothing is logged for it: it was simply not part of today. Sets already done stay. */
export function removeSegment(r: Run, id: string): Run {
  const segs = remaining(r);
  const gone = segs.find((s) => s.id === id);
  if (!gone) return r;
  return rebuild(r, segs.filter((s) => s.id !== id), { kind: "remove", label: nameOf(gone) });
}

export interface SegmentPatch { sets?: number; reps?: number; seconds?: number; distance_m?: number; load?: string | null; rest_s?: number }

/** Changes what is left of one exercise: how many sets, reps or seconds, the weight, the rest. Only sets not yet done change. */
export function editRemaining(r: Run, id: string, patch: SegmentPatch): Run {
  const segs = remaining(r);
  const seg = segs.find((s) => s.id === id);
  if (!seg) return r;
  let items = [...seg.items];
  if (patch.sets != null) {
    const total = Math.max(seg.doneBefore + 1, Math.min(MAX_SETS, Math.round(patch.sets)));
    const want = total - seg.doneBefore;
    if (want < items.length) items = items.slice(0, want);
    const last = items[items.length - 1];
    while (items.length < want) items.push({ ...last, id: `${last.id}+${items.length + 1}`, restAfter: last.restAfter });
  }
  const total = seg.doneBefore + items.length;
  const adjusted: WorkItem[] = items.map((it, k) => {
    const target: Target = { ...it.target };
    if (patch.reps != null && target.reps != null) target.reps = Math.max(1, Math.round(patch.reps));
    if (patch.seconds != null && target.seconds != null) target.seconds = Math.max(1, Math.round(patch.seconds));
    if (patch.distance_m != null && target.distance_m != null) target.distance_m = Math.max(1, Math.round(patch.distance_m));
    const next: WorkItem = { ...it, target, set: seg.doneBefore + k + 1, sets: total, restAfter: k < items.length - 1 || it.restAfter ? it.restAfter : 0 };
    if (patch.rest_s != null) next.restAfter = k < items.length - 1 ? Math.max(0, Math.round(patch.rest_s)) : 0;
    if (patch.load !== undefined) {
      if (patch.load === null || patch.load.trim() === "") {
        delete next.load;
        delete next.loadPinned;
      } else {
        next.load = patch.load.trim();
        next.loadPinned = true;
      }
    }
    return next;
  });
  const trailing = seg.all.filter((q): q is Extract<QueueItem, { kind: "rest" }> => q.kind === "rest");
  const rebuilt: Segment = { ...seg, items: adjusted, all: [...adjusted, ...trailing] };
  // The "of N" shown on sets already done in this round follows the new total, like adding an extra set does.
  const queue = r.queue.slice(0, r.idx).map((q) => (q.kind === "work" && q.key === seg.key && q.round === seg.round ? { ...q, sets: total } : q));
  const out = [...queue, ...segs.map((s) => (s.id === id ? rebuilt : s)).flatMap((s) => s.all)];
  return { ...r, queue: out, edits: record(r, { kind: "edit", label: nameOf(seg) }) };
}

export interface InsertSpec { exercise?: string; name?: string; sets: number; reps?: number; seconds?: number; distance_m?: number; calories?: number; load?: string; rest_s: number }

/** What an exercise added mid-workout starts with, by how it is measured (the same defaults as the session editor). */
export function defaultSpec(ex: Pick<GymExercise, "id" | "name" | "unit" | "pattern"> | undefined, name?: string): InsertSpec {
  const base = ex ? { exercise: ex.id, name: ex.name } : { name: name ?? "Exercise" };
  switch (ex?.unit) {
    case "time": return { ...base, sets: 3, seconds: 30, rest_s: 30 };
    case "distance": return ex.pattern === "cardio" ? { ...base, sets: 1, distance_m: 1000, rest_s: 0 } : { ...base, sets: 3, distance_m: 40, rest_s: 60 };
    case "calories": return { ...base, sets: 1, calories: 15, rest_s: 0 };
    default: return { ...base, sets: 3, reps: 10, rest_s: 60 };
  }
}

/** Adds an exercise to the workout: right now (the one you are on resumes after it), after the current exercise, or at the end. */
export function insertExercise(r: Run, spec: InsertSpec, at: "now" | "after_current" | "end"): Run {
  if (isFinished(r)) return r;
  const sets = Math.max(1, Math.min(MAX_SETS, Math.round(spec.sets)));
  const work = r.queue.filter((q) => q.kind === "work").length;
  if (work + sets > MAX_WORK_ITEMS) return r;
  const cur = r.queue[r.idx];
  if (!cur || cur.kind !== "work") return r;
  const n = new Set(r.queue.flatMap((q) => (q.kind === "work" && q.key.startsWith("ins") ? [q.key] : []))).size;
  const key = `ins${n}`;
  const target: Target = {};
  if (spec.reps != null) target.reps = spec.reps;
  if (spec.seconds != null) target.seconds = spec.seconds;
  if (spec.distance_m != null) target.distance_m = spec.distance_m;
  if (spec.calories != null) target.calories = spec.calories;
  const inherit = at !== "end";
  const items: WorkItem[] = Array.from({ length: sets }, (_, k) => ({
    kind: "work", id: `${key}.${k + 1}`, key, exercise: spec.exercise, name: spec.name, block: inherit ? cur.block : "", round: inherit ? cur.round : 1, rounds: inherit ? cur.rounds : 1,
    set: k + 1, sets, target: { ...target }, load: spec.load, restAfter: k < sets - 1 ? spec.rest_s : 0, inserted: true as const,
  }));
  const segs = remaining(r);
  const rest = segs.flatMap((s) => s.all);
  const head = r.queue.slice(0, r.idx);
  let queue: QueueItem[];
  if (at === "now") queue = [...head, ...items, ...rest];
  else if (at === "after_current") queue = [...head, ...segs[0].all, ...items, ...segs.slice(1).flatMap((s) => s.all)];
  else queue = [...head, ...rest, ...items];
  return { ...r, queue, edits: record(r, { kind: "insert", label: spec.name ?? spec.exercise ?? "Exercise" }) };
}

/** Rough time left: sets still to do at the median time per timed set so far, plus the rests. Null until two sets have been timed. */
export function etaSeconds(r: Run): number | null {
  const took = Object.values(r.results as Record<string, SetResult>).flatMap((x) => (x.done && x.took_s != null ? [x.took_s] : [])).sort((a, b) => a - b);
  if (took.length < 2) return null;
  const median = took[Math.floor(took.length / 2)];
  const left = r.queue.slice(r.idx);
  const sets = left.filter((q) => q.kind === "work").length;
  const rests = left.reduce((s, q) => s + (q.kind === "rest" ? q.seconds : q.restAfter), 0);
  return sets * median + rests;
}

/** One line for the summary: what you changed during the workout. Null when nothing was. */
export function editSummary(r: Run): string | null {
  const e = r.edits ?? [];
  if (!e.length) return null;
  const count = (k: RunEdit["kind"]) => e.filter((x) => x.kind === k).length;
  const parts: [number, string][] = [[count("defer"), "moved later"], [count("reorder"), "reordered"], [count("remove"), "removed"], [count("insert"), "added"], [count("edit"), "adjusted"], [count("swap"), "swapped"]];
  return parts.filter(([n]) => n > 0).map(([n, w]) => `${n} ${w}`).join(" · ");
}
