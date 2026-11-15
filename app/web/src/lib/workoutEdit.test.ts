import { describe, expect, it } from "vitest";
import { defaultSpec, deferExercise, editRemaining, editSummary, etaSeconds, insertExercise, moveSegment, remaining, removeSegment } from "./workoutEdit";
import { currentItem, finishSet, isFinished, progress, seedLoad, startRun, toEntries, workItems } from "./workoutQueue";
import type { GymStep } from "./types";

const steps = (): GymStep[] => [
  { type: "exercise", exercise: "leg-press", sets: 3, reps: 10, load: "100 kg", rest_s: 90 },
  { type: "exercise", exercise: "lat-pulldown", sets: 3, reps: 10, load: "40 kg", rest_s: 60 },
  { type: "exercise", exercise: "plank", sets: 2, seconds: 30, rest_s: 30 },
];
const start = () => startRun(steps(), "gym", 1000);
const order = (r: ReturnType<typeof start>) => remaining(r).map((s) => `${s.exercise}:${s.items.length}`);

describe("what is left", () => {
  it("lists the undone sets per exercise from where you are", () => {
    expect(order(start())).toEqual(["leg-press:3", "lat-pulldown:3", "plank:2"]);
    const after = finishSet(start(), { reps: 10 }, 2000).run;
    const s = remaining(after);
    expect(s[0]).toMatchObject({ exercise: "leg-press", doneBefore: 1 });
    expect(s[0].items).toHaveLength(2);
  });
});

describe("machine busy: do it later", () => {
  it("moves the rest of this exercise after the next one, and the next becomes current", () => {
    let r = finishSet(start(), { reps: 10, load: "100 kg" }, 2000).run;
    r = deferExercise(r, "after_next");
    expect(order(r)).toEqual(["lat-pulldown:3", "leg-press:2", "plank:2"]);
    expect(currentItem(r)).toMatchObject({ exercise: "lat-pulldown", set: 1 });
    expect(progress(r)).toMatchObject({ done: 1, total: 8 });
  });
  it("or to the end, and does nothing when it is the last exercise", () => {
    expect(order(deferExercise(start(), "end"))).toEqual(["lat-pulldown:3", "plank:2", "leg-press:3"]);
    let r = start();
    r = removeSegment(removeSegment(r, remaining(r)[0].id), remaining(removeSegment(r, remaining(r)[0].id))[0].id);
    expect(order(r)).toEqual(["plank:2"]);
    expect(deferExercise(r, "end")).toBe(r);
  });
  it("keeps the sets done before and after the move together in the log, in the order they happened", () => {
    let r = finishSet(start(), { reps: 10, load: "100 kg" }, 2000).run;
    r = deferExercise(r, "end");
    let guard = 0;
    while (!isFinished(r) && guard++ < 40) r = finishSet(r, { reps: 8, load: "90 kg" }, 3000).run;
    const entries = toEntries(r, () => undefined);
    const press = entries.find((e) => e.exercise === "leg-press")!;
    expect(press.sets).toHaveLength(3);
    expect(press.sets[0]).toMatchObject({ reps: 10, load: "100 kg" });
    expect(press.sets[1]).toMatchObject({ reps: 8 });
    expect(entries.map((e) => e.exercise)).toEqual(["leg-press", "lat-pulldown", "plank"]);
  });
});

describe("reordering and removing", () => {
  it("moves an exercise earlier or later among the remaining ones, never past the ends", () => {
    const r = start();
    const [a, b] = remaining(r);
    expect(order(moveSegment(r, b.id, -1))).toEqual(["lat-pulldown:3", "leg-press:3", "plank:2"]);
    expect(moveSegment(r, a.id, -1)).toBe(r);
    expect(moveSegment(r, remaining(r)[2].id, 1)).toBe(r);
  });
  it("removes an exercise without logging it as skipped, and keeps sets already done", () => {
    let r = finishSet(start(), { reps: 10 }, 2000).run;
    r = removeSegment(r, remaining(r)[0].id);
    expect(order(r)).toEqual(["lat-pulldown:3", "plank:2"]);
    expect(currentItem(r)).toMatchObject({ exercise: "lat-pulldown" });
    expect(progress(r)).toMatchObject({ done: 1, skipped: 0, total: 6 });
    expect(toEntries(r, () => undefined).map((e) => e.exercise)).toEqual(["leg-press"]);
  });
  it("finishes when everything left is removed", () => {
    let r = start();
    for (let i = 0; i < 3; i++) r = removeSegment(r, remaining(r)[0].id);
    expect(isFinished(r)).toBe(true);
  });
});

describe("changing what is left of an exercise", () => {
  it("changes reps, seconds and rest only for sets not done yet", () => {
    let r = finishSet(start(), { reps: 10 }, 2000).run;
    r = editRemaining(r, remaining(r)[0].id, { reps: 8, rest_s: 45 });
    const press = workItems(r).filter((w) => w.exercise === "leg-press");
    expect(press.map((w) => w.target.reps)).toEqual([10, 8, 8]);
    expect(press[1].restAfter).toBe(45);
    expect(press[2].restAfter).toBe(0);
    expect(r.results[press[0].id]).toMatchObject({ reps: 10 });
    r = editRemaining(r, remaining(r)[1].id, { seconds: 45 });
    expect(workItems(r).find((w) => w.exercise === "lat-pulldown")!.target.seconds).toBeUndefined(); // no unit conversion
  });
  it("adds and removes sets, renumbering, never below one remaining", () => {
    let r = finishSet(start(), { reps: 10 }, 2000).run;
    const id = remaining(r)[0].id;
    r = editRemaining(r, id, { sets: 5 });
    expect(workItems(r).filter((w) => w.exercise === "leg-press").map((w) => `${w.set}/${w.sets}`)).toEqual(["1/5", "2/5", "3/5", "4/5", "5/5"]);
    r = editRemaining(r, id, { sets: 1 });
    expect(workItems(r).filter((w) => w.exercise === "leg-press")).toHaveLength(2); // one done, one left
    expect(new Set(workItems(r).map((w) => w.id)).size).toBe(workItems(r).length);
  });
  it("pins a typed weight so the carry-over from earlier sets does not overwrite it", () => {
    let r = finishSet(start(), { reps: 10, load: "100 kg" }, 2000).run;
    r = editRemaining(r, remaining(r)[0].id, { load: "80 kg" });
    expect(seedLoad(r, currentItem(r) as never)).toBe("80 kg");
    r = editRemaining(r, remaining(r)[0].id, { load: null });
    expect(seedLoad(r, currentItem(r) as never)).toBe("100 kg");
  });
});

describe("adding an exercise mid-workout", () => {
  const spec = { exercise: "goblet-squat", name: "Goblet Squat", sets: 2, reps: 12, rest_s: 45 };
  it("now: it becomes the current set and the one you were on resumes after it", () => {
    const r = insertExercise(finishSet(start(), { reps: 10 }, 2000).run, spec, "now");
    expect(currentItem(r)).toMatchObject({ exercise: "goblet-squat", set: 1, sets: 2 });
    expect(order(r)).toEqual(["goblet-squat:2", "leg-press:2", "lat-pulldown:3", "plank:2"]);
  });
  it("after the current exercise, or at the end", () => {
    expect(order(insertExercise(start(), spec, "after_current"))).toEqual(["leg-press:3", "goblet-squat:2", "lat-pulldown:3", "plank:2"]);
    expect(order(insertExercise(start(), spec, "end"))).toEqual(["leg-press:3", "lat-pulldown:3", "plank:2", "goblet-squat:2"]);
  });
  it("gives each added exercise its own key and unique ids, and logs it like any other", () => {
    let r = insertExercise(start(), spec, "end");
    r = insertExercise(r, { ...spec, exercise: "bicep-curl", name: "Biceps Curl" }, "end");
    const ids = workItems(r).map((w) => w.id);
    expect(new Set(ids).size).toBe(ids.length);
    let guard = 0;
    while (!isFinished(r) && guard++ < 60) r = finishSet(r, { reps: 5 }, 3000).run;
    expect(toEntries(r, () => undefined).map((e) => e.exercise)).toEqual(["leg-press", "lat-pulldown", "plank", "goblet-squat", "bicep-curl"]);
  });
  it("refuses once the workout is full, and does nothing on a finished run", () => {
    const r = start();
    expect(insertExercise(r, { ...spec, sets: 40 }, "end")).not.toBe(r);
    const big = { ...r, queue: [...r.queue, ...Array.from({ length: 300 }, (_, i) => ({ ...(r.queue[0] as object), id: `x${i}`, key: `x${i}` }))] } as typeof r;
    expect(insertExercise(big, spec, "end")).toBe(big);
  });
  it("starts from sensible defaults by how an exercise is measured", () => {
    expect(defaultSpec({ id: "a", name: "A", unit: "reps", pattern: "push" })).toMatchObject({ sets: 3, reps: 10, rest_s: 60 });
    expect(defaultSpec({ id: "a", name: "A", unit: "time", pattern: "core" })).toMatchObject({ sets: 3, seconds: 30 });
    expect(defaultSpec({ id: "a", name: "A", unit: "distance", pattern: "cardio" })).toMatchObject({ sets: 1, distance_m: 1000 });
    expect(defaultSpec(undefined, "Odd machine")).toMatchObject({ name: "Odd machine", reps: 10 });
  });
});

describe("time left and the summary line", () => {
  it("estimates time left only after two timed sets", () => {
    let r = start();
    expect(etaSeconds(r)).toBeNull();
    r = finishSet(r, { reps: 10 }, 1000 + 40_000).run;
    expect(etaSeconds(r)).toBeNull();
    r = finishSet(r, { reps: 10 }, 1000 + 80_000).run;
    expect(etaSeconds(r)).toBeGreaterThan(0);
  });
  it("says what was changed, and nothing when nothing was", () => {
    expect(editSummary(start())).toBeNull();
    let r = deferExercise(start(), "end");
    r = removeSegment(r, remaining(r)[2].id);
    r = insertExercise(r, { exercise: "plank", sets: 1, seconds: 30, rest_s: 0 }, "end");
    expect(editSummary(r)).toBe("1 moved later · 1 removed · 1 added");
  });
});
