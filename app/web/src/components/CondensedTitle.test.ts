import { describe, expect, it } from "vitest";
import { isCondensed } from "./CondensedTitle";

describe("isCondensed", () => {
  it("is false while the large title is on screen", () => expect(isCondensed(120)).toBe(false));
  it("is true once it has scrolled above the top", () => expect(isCondensed(-4)).toBe(true));
  it("respects a top inset", () => expect(isCondensed(40, 48)).toBe(true));
});
