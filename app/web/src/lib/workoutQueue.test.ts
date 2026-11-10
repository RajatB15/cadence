import { describe, expect, it } from "vitest";
import { addSet, bumpLoad, parseKg, buildQueue, currentItem, finishSet, goBack, isFinished, progress, skipExercise, skipSet, startRun, swapRemaining, toEntries, volumeKg, withLastLoads, workItems } from "./workoutQueue";
import type { GymStep } from "./types";

const steps = (): GymStep[] => [
  { type: "exercise", exercise: "back-squat", sets: 3, reps: 5, load: "80 kg", rest_s: 120 },
  { type: "rest", seconds: 30 },
  { type: "group", title: "Finisher", rounds: 2, rest_s: 45, steps: [{ type: "exercise", exercise: "run", sets: 1, distance_m: 400 }, { type: "exercise", exercise: "burpee", sets: 1, reps: 10 }] },
  { type: "exercise", name: "Odd machine", sets: 2, reps: 12 },
];

describe("unrolling a session into sets and rests", () => {
  it("expands sets, rounds and the rests between them", () => {
    const q = buildQueue(steps());
    const kinds = q.map((x) => (x.kind === "rest" ? `rest${x.seconds}` : `${x.exercise ?? x.name}${x.sets > 1 || x.rounds > 1 ? `:${x.round}.${x.set}` : ""}`));
    expect(kinds).toEqual(["back-squat:1.1", "back-squat:1.2", "back-squat:1.3", "rest30", "run:1.1", "burpee:1.1", "rest45", "run:2.1", "burpee:2.1", "Odd machine:1.1", "Odd machine:1.2"]);
    const squat = q[0];
    expect(squat.kind === "work" && squat.restAfter).toBe(120);
    expect(q[2].kind === "work" && q[2].restAfter).toBe(0); // no rest after the last set of an exercise
    expect(q.find((x) => x.kind === "work" && x.exercise === "run")).toMatchObject({ block: "Finisher", rounds: 2, target: { distance_m: 400 } });
  });
});

describe("running through it", () => {
  const start = () => startRun(steps(), "gym", 1000);
  it("finishing a set records it and returns the rest to take, including a rest step that follows", () => {
    let r = start();
    let out = finishSet(r, { reps: 5, load: "80 kg" });
    expect(out.rest).toBe(120);
    expect(out.run.idx).toBe(1);
    r = out.run;
    r = finishSet(r, { reps: 5, load: "80 kg" }).run;
    out = finishSet(r, { reps: 4, load: "80 kg" });
    expect(out.rest).toBe(30); // the rest step after the exercise
    expect(currentItem(out.run)).toMatchObject({ kind: "work", exercise: "run" });
    expect(progress(out.run)).toEqual({ done: 3, total: 9, skipped: 0 });
  });
  it("skips a set or a whole exercise and steps back to redo one", () => {
    let r = skipSet(start());
    expect(r.results[r.queue[0].id]).toEqual({ done: false });
    expect(currentItem(r)).toMatchObject({ set: 2 });
    r = skipExercise(r);
    expect(currentItem(r)).toMatchObject({ exercise: "run" });
    expect(progress(r)).toMatchObject({ skipped: 3 });
    const back = goBack(finishSet(start(), { reps: 5 }).run);
    expect(back.idx).toBe(0);
    expect(back.results).toEqual({});
    expect(goBack(start()).idx).toBe(0);
  });
  it("adds a set to the exercise you're on", () => {
    const r = addSet(start());
    const squats = workItems(r).filter((w) => w.exercise === "back-squat");
    expect(squats).toHaveLength(4);
    expect(squats.every((s) => s.sets === 4)).toBe(true);
    expect(squats[3].set).toBe(4);
    expect(squats[2].restAfter).toBe(120); // the old last set now rests before the new one
    expect(squats[3].restAfter).toBe(0);
  });
  it("swaps only the sets still to do", () => {
    let r = finishSet(start(), { reps: 5 }).run;
    r = swapRemaining(r, "goblet-squat", "Goblet Squat");
    const items = workItems(r).filter((w) => w.key.startsWith("/0"));
    expect(items.map((i) => i.exercise)).toEqual(["back-squat", "goblet-squat", "goblet-squat"]);
    expect(items[1].load).toBeUndefined();
  });
  it("prefills last time's load only where the plan has none", () => {
    const r = withLastLoads(start(), { "back-squat": { load: "70 kg", reps: 5, seconds: null, day: "2026-11-01", sets: 3, hint: null }, burpee: { load: "10 kg", reps: 8, seconds: null, day: "2026-11-01", sets: 1, hint: null } });
    const w = workItems(r);
    expect(w[0].load).toBe("80 kg"); // the plan's own load wins
    expect(w.find((x) => x.exercise === "burpee")?.load).toBe("10 kg");
  });
  it("finishes, then turns into a log with what was aimed for", () => {
    let r = start();
    let guard = 0;
    while (!isFinished(r) && guard++ < 50) r = finishSet(r, { reps: 5, load: "80 kg" }).run;
    expect(isFinished(r)).toBe(true);
    const entries = toEntries(r, () => undefined);
    expect(entries.map((e) => e.exercise ?? e.name)).toEqual(["back-squat", "run", "burpee", "Odd machine"]);
    expect(entries[0].sets).toHaveLength(3);
    expect(entries[0].sets[0]).toEqual({ done: true, reps: 5, load: "80 kg", target_reps: 5 });
    expect(entries[1].sets).toHaveLength(2);
  });
  it("counts volume only from numeric loads", () => {
    expect(volumeKg([{ exercise: "x", sets: [{ done: true, reps: 5, load: "80 kg" }, { done: true, reps: 5, load: "bodyweight" }, { done: false, reps: 5, load: "90" }, { done: true, reps: 3, load: "42,5" }] }])).toBe(400 + 128);
    expect(volumeKg([{ exercise: "x", sets: [{ done: true, reps: 10, load: "bodyweight" }] }])).toBeNull();
  });
});

describe("loads", () => {
  it("parses kilograms and nudges them", () => {
    expect(parseKg("40")).toBe(40);
    expect(parseKg("42,5 kg")).toBe(42.5);
    expect(parseKg("bodyweight")).toBeNull();
    expect(parseKg("")).toBeNull();
    expect(bumpLoad("40 kg", 2.5)).toBe("42.5 kg");
    expect(bumpLoad(undefined, 2.5)).toBe("2.5 kg");
    expect(bumpLoad("2.5 kg", -2.5)).toBe("");
    expect(bumpLoad("20 kg", -5)).toBe("15 kg");
    expect(bumpLoad("band", 2.5)).toBe("2.5 kg");
  });
});
