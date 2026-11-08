import { describe, expect, it } from "vitest";
import { chartAnimation, isFreshDay, routeDirection, routeMotion, staggerDelay } from "./motion";

describe("motion helpers", () => {
  it("caps stagger delay", () => {
    expect(staggerDelay(0)).toBe(0);
    expect(staggerDelay(3)).toBeCloseTo(0.135);
    expect(staggerDelay(50)).toBeCloseTo(0.36);
    expect(staggerDelay(-2)).toBe(0);
  });

  it("derives route direction from tab order and depth", () => {
    expect(routeDirection(null, "/coach")).toBe(0);
    expect(routeDirection("/plan", "/plan")).toBe(0);
    expect(routeDirection("/", "/coach")).toBe(1);
    expect(routeDirection("/activities", "/plan")).toBe(-1);
    expect(routeDirection("/activities", "/activities/12")).toBe(1);
    expect(routeDirection("/activities/12", "/activities")).toBe(-1);
    expect(routeDirection("/metrics/hrv", "/")).toBe(-1);
  });

  it("route motion is instant with reduced motion", () => {
    const m = routeMotion(1, true);
    expect(m.transition.duration).toBe(0);
    expect(m.initial.opacity).toBe(1);
    expect(routeMotion(-1, false).initial.x).toBeLessThan(0);
    expect(routeMotion(0, false).initial.x).toBe(0);
  });

  it("charts animate only on first paint and never when reduced", () => {
    expect(chartAnimation(true, false).animation).toBe(true);
    expect(chartAnimation(false, false).animation).toBe(false);
    expect(chartAnimation(true, true).animation).toBe(false);
    expect(chartAnimation(true, false, false).animation).toBe(false);
    expect(chartAnimation(false, false).animationDuration).toBe(0);
  });

  it("treats only recent days as fresh", () => {
    const now = new Date("2026-11-08T10:00:00");
    expect(isFreshDay("2026-11-07", now)).toBe(true);
    expect(isFreshDay("2026-10-01", now)).toBe(false);
    expect(isFreshDay(null, now)).toBe(false);
    expect(isFreshDay("garbage", now)).toBe(false);
  });
});
