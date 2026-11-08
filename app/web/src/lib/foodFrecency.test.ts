import { describe, expect, it } from "vitest";
import { frecencyScores, logsFromRecent, mealForTime, portionMemory, usualMeals, type LogRecord } from "./foodFrecency";

const L = (day: string, meal: LogRecord["meal"], dishId: number, servings = 1): LogRecord => ({ day, meal, dishId, servings });

describe("frecency", () => {
  it("halves weight every 14 days and normalises to 1", () => {
    const f = frecencyScores([L("2026-11-08", "lunch", 1), L("2026-11-07", "lunch", 1), L("2026-10-25", "lunch", 2), L("2026-10-24", "lunch", 2)], "2026-11-08", "lunch");
    expect(f.get(1)).toBe(1);
    expect(f.get(2)!).toBeGreaterThan(0.3);
    expect(f.get(2)!).toBeLessThan(0.6);
  });
  it("caps a dish seen once at 0.2", () => {
    const f = frecencyScores([L("2026-11-08", "lunch", 1), L("2026-11-07", "lunch", 1), L("2026-11-08", "lunch", 9)], "2026-11-08", "lunch");
    expect(f.get(9)!).toBeLessThanOrEqual(0.2);
  });
  it("gives the same meal and weekday more weight", () => {
    const f = frecencyScores([L("2026-11-01", "dinner", 1), L("2026-11-02", "dinner", 1), L("2026-11-01", "breakfast", 2), L("2026-11-02", "breakfast", 2)], "2026-11-08", "dinner");
    expect(f.get(1)!).toBeGreaterThan(f.get(2)!);
  });
  it("is empty with no history", () => {
    expect(frecencyScores([], "2026-11-08", "lunch").size).toBe(0);
    expect(logsFromRecent([], "2026-11-08", "lunch")).toEqual([]);
  });
  it("picks the meal from the clock", () => {
    const at = (h: number, m = 0) => mealForTime(new Date(2026, 10, 8, h, m));
    expect([at(7), at(10, 59), at(11), at(15, 29), at(15, 30), at(18, 29), at(18, 30), at(23)]).toEqual(["breakfast", "breakfast", "lunch", "lunch", "snack", "snack", "dinner", "dinner"]);
  });
});

describe("usual meals", () => {
  const days = ["2026-11-07", "2026-11-06", "2026-11-05", "2026-11-04"];
  it("clusters repeated sets (Jaccard 0.6) and needs 3 days", () => {
    const logs = [...days.flatMap((d, i) => [L(d, "breakfast", 1, 2), L(d, "breakfast", 2), ...(i === 0 ? [L(d, "breakfast", 3)] : [])]), L("2026-11-03", "breakfast", 7), L("2026-11-02", "breakfast", 7)];
    const u = usualMeals(logs, "2026-11-08", "breakfast");
    expect(u).toHaveLength(1);
    expect(u[0].days).toBe(4);
    expect(u[0].items.find((x) => x.dishId === 1)!.servings).toBe(2);
  });
  it("ignores other meals, today and old days", () => {
    expect(usualMeals(days.map((d) => L(d, "lunch", 1)), "2026-11-08", "breakfast")).toEqual([]);
    expect(usualMeals(days.slice(0, 2).map((d) => L(d, "breakfast", 1)), "2026-11-08", "breakfast")).toEqual([]);
  });
});

describe("portion memory", () => {
  it("remembers the last amount and flags a habit after three identical ones", () => {
    const m = portionMemory([L("2026-11-01", "lunch", 1, 1), L("2026-11-02", "lunch", 1, 2), L("2026-11-03", "lunch", 1, 2), L("2026-11-04", "lunch", 1, 2), L("2026-11-04", "lunch", 5, 3)]);
    expect(m[1]).toMatchObject({ servings: 2, habitual: true });
    expect(m[5]).toMatchObject({ servings: 3, habitual: false });
  });
});
