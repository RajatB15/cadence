import type { GymExercise, GymExerciseStep, GymStep } from "./types";

/** Pure helpers for editing a session's step tree by path (indexes through groups). Nothing here mutates its input. */

export function stepAt(steps: GymStep[], path: number[]): GymStep | undefined {
  let level: GymStep[] = steps;
  for (let i = 0; i < path.length; i++) {
    const s = level[path[i]];
    if (!s) return undefined;
    if (i === path.length - 1) return s;
    if (s.type !== "group") return undefined;
    level = s.steps;
  }
  return undefined;
}

function mapLevel(steps: GymStep[], path: number[], fn: (level: GymStep[], index: number) => GymStep[]): GymStep[] {
  if (path.length === 1) return fn(steps, path[0]);
  const [head, ...rest] = path;
  return steps.map((s, i) => (i === head && s.type === "group" ? { ...s, steps: mapLevel(s.steps, rest, fn) } : s));
}

export function updateAt(steps: GymStep[], path: number[], patch: (s: GymStep) => GymStep): GymStep[] {
  return mapLevel(steps, path, (level, i) => level.map((s, j) => (j === i ? patch(s) : s)));
}

export function removeAt(steps: GymStep[], path: number[]): GymStep[] {
  return mapLevel(steps, path, (level, i) => level.filter((_, j) => j !== i));
}

/** Moves a step up (-1) or down (+1) within its own list; unchanged at the ends. */
export function moveAt(steps: GymStep[], path: number[], delta: -1 | 1): GymStep[] {
  return mapLevel(steps, path, (level, i) => {
    const to = i + delta;
    if (to < 0 || to >= level.length) return level;
    const copy = [...level];
    [copy[i], copy[to]] = [copy[to], copy[i]];
    return copy;
  });
}

/** Adds a step at the end of the top level, or of the group at `groupPath`. */
export function appendTo(steps: GymStep[], groupPath: number[] | null, step: GymStep): GymStep[] {
  if (!groupPath || groupPath.length === 0) return [...steps, step];
  return updateAt(steps, groupPath, (g) => (g.type === "group" ? { ...g, steps: [...g.steps, step] } : g));
}

/** What a newly added library exercise starts with, by how it is measured. */
export function defaultStep(ex: Pick<GymExercise, "id" | "unit" | "pattern">): GymExerciseStep {
  const base = { type: "exercise" as const, exercise: ex.id };
  switch (ex.unit) {
    case "time":
      return { ...base, sets: 3, seconds: 30, rest_s: 30 };
    case "distance":
      return ex.pattern === "cardio" ? { ...base, sets: 1, distance_m: 1000 } : { ...base, sets: 3, distance_m: 40, rest_s: 60 };
    case "calories":
      return { ...base, sets: 1, calories: 15 };
    default:
      return { ...base, sets: 3, reps: 10, rest_s: 60 };
  }
}

/** How much of one exercise a step asks for, e.g. "3 × 10", "4 × 30 s", "1 km". */
export function amount(s: GymExerciseStep): string {
  const sets = s.sets ?? 1;
  if (s.reps != null) return `${sets} × ${s.reps}`;
  if (s.seconds != null) return sets > 1 ? `${sets} × ${s.seconds} s` : `${s.seconds} s`;
  if (s.distance_m != null) {
    const d = s.distance_m >= 1000 && s.distance_m % 100 === 0 ? `${s.distance_m / 1000} km` : `${s.distance_m} m`;
    return sets > 1 ? `${sets} × ${d}` : d;
  }
  if (s.calories != null) return `${s.calories} cal`;
  return "";
}

/** Exercise ids in the tree, in order (groups expanded once). */
export function exerciseIds(steps: GymStep[]): string[] {
  return steps.flatMap((s) => (s.type === "group" ? exerciseIds(s.steps) : s.type === "exercise" && s.exercise ? [s.exercise] : []));
}

export const pathKey = (path: number[]) => path.join(".");
