import { describe, expect, it } from "vitest";
import { amount, appendTo, defaultStep, exerciseIds, moveAt, removeAt, stepAt, updateAt } from "./gymSteps";
import type { GymStep } from "./types";

const tree = (): GymStep[] => [
  { type: "exercise", exercise: "air-squat", sets: 3, reps: 10 },
  { type: "group", title: "Round", rounds: 4, steps: [{ type: "exercise", exercise: "run", sets: 1, distance_m: 1000 }, { type: "exercise", exercise: "burpee", sets: 1, reps: 10 }] },
  { type: "rest", seconds: 60 },
];

describe("gym step tree editing", () => {
  it("finds steps by path through groups", () => {
    expect(stepAt(tree(), [0])).toMatchObject({ exercise: "air-squat" });
    expect(stepAt(tree(), [1, 1])).toMatchObject({ exercise: "burpee" });
    expect(stepAt(tree(), [2, 0])).toBeUndefined();
    expect(stepAt(tree(), [5])).toBeUndefined();
    expect(stepAt(tree(), [])).toBeUndefined();
  });
  it("updates, removes and moves without touching the original", () => {
    const t = tree();
    const edited = updateAt(t, [1, 0], (s) => ({ ...s, distance_m: 400 } as GymStep));
    expect(stepAt(edited, [1, 0])).toMatchObject({ distance_m: 400 });
    expect(stepAt(t, [1, 0])).toMatchObject({ distance_m: 1000 });
    expect(removeAt(t, [1, 0])).toHaveLength(3);
    expect((removeAt(t, [1, 0])[1] as { steps: unknown[] }).steps).toHaveLength(1);
    expect(removeAt(t, [0]).map((s) => s.type)).toEqual(["group", "rest"]);
    expect(moveAt(t, [0], 1).map((s) => s.type)).toEqual(["group", "exercise", "rest"]);
    expect(moveAt(t, [0], -1)).toEqual(t);
    expect(moveAt(t, [2], 1)).toEqual(t);
    const inner = moveAt(t, [1, 1], -1);
    expect(stepAt(inner, [1, 0])).toMatchObject({ exercise: "burpee" });
  });
  it("appends to the top level or into a group", () => {
    const add: GymStep = { type: "rest", seconds: 30 };
    expect(appendTo(tree(), null, add)).toHaveLength(4);
    const g = appendTo(tree(), [1], add);
    expect((g[1] as { steps: unknown[] }).steps).toHaveLength(3);
    expect(appendTo(tree(), [0], add)).toEqual(tree()); // not a group: unchanged
  });
  it("starts new exercises with a sensible prescription for how they are measured", () => {
    expect(defaultStep({ id: "push-up", unit: "reps", pattern: "push" })).toMatchObject({ sets: 3, reps: 10 });
    expect(defaultStep({ id: "plank", unit: "time", pattern: "core" })).toMatchObject({ seconds: 30 });
    expect(defaultStep({ id: "run", unit: "distance", pattern: "cardio" })).toMatchObject({ sets: 1, distance_m: 1000 });
    expect(defaultStep({ id: "farmers-carry", unit: "distance", pattern: "carry" })).toMatchObject({ distance_m: 40 });
    expect(defaultStep({ id: "assault-bike", unit: "calories", pattern: "cardio" })).toMatchObject({ calories: 15 });
  });
  it("words amounts and lists exercises", () => {
    expect(amount({ type: "exercise", sets: 4, reps: 5 })).toBe("4 × 5");
    expect(amount({ type: "exercise", sets: 1, seconds: 45 })).toBe("45 s");
    expect(amount({ type: "exercise", sets: 3, seconds: 30 })).toBe("3 × 30 s");
    expect(amount({ type: "exercise", sets: 1, distance_m: 1000 })).toBe("1 km");
    expect(amount({ type: "exercise", sets: 1, distance_m: 80 })).toBe("80 m");
    expect(amount({ type: "exercise", sets: 1, distance_m: 1500 })).toBe("1.5 km");
    expect(amount({ type: "exercise", calories: 20 })).toBe("20 cal");
    expect(exerciseIds(tree())).toEqual(["air-squat", "run", "burpee"]);
  });
});
