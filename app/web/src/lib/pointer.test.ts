import { describe, expect, it } from "vitest";
import { hasFinePointer } from "./pointer";

const win = (matches: boolean) => ({ matchMedia: () => ({ matches }) as MediaQueryList });

describe("hasFinePointer", () => {
  it("is true for mouse", () => expect(hasFinePointer(win(true))).toBe(true));
  it("is false for touch", () => expect(hasFinePointer(win(false))).toBe(false));
  it("defaults to true without matchMedia", () => expect(hasFinePointer({} as Window)).toBe(true));
});
