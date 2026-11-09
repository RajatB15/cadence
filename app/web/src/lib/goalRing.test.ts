import { describe, expect, it } from "vitest";
import { goalRing } from "./goalRing";

describe("goalRing", () => {
  it("is within the band and puts the band on the ring", () => {
    const m = goalRing(140, [130, 160]);
    expect(m.status).toBe("within");
    expect(m.scale).toBe(200);
    expect(m.bandFrom).toBeCloseTo(0.65);
    expect(m.bandTo).toBeCloseTo(0.8);
    expect(m.fill).toBeCloseTo(0.7);
    expect(m.gap).toBe(0);
  });
  it("says how far below the low end, and how far above the top", () => {
    expect(goalRing(100, [130, 160])).toMatchObject({ status: "below", gap: 30 });
    expect(goalRing(190, [130, 160])).toMatchObject({ status: "above", gap: 30 });
  });
  it("grows the scale when the value passes the headroom", () => {
    const m = goalRing(300, [130, 160]);
    expect(m.scale).toBe(300);
    expect(m.fill).toBe(1);
  });
  it("keeps missing apart from zero", () => {
    expect(goalRing(null, [130, 160]).status).toBe("none");
    expect(goalRing(0, [130, 160])).toMatchObject({ status: "below", gap: 130, fill: 0 });
  });
  it("has no band and no target status without a target, and tolerates a reversed band", () => {
    expect(goalRing(50, null).status).toBe("no_target");
    expect(goalRing(null, null).status).toBe("none");
    expect(goalRing(140, [160, 130]).status).toBe("within");
  });
});
