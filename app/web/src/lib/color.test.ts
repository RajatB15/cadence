import { describe, expect, it } from "vitest";
import { withAlpha } from "./color";

describe("withAlpha", () => {
  it("converts hex to rgba", () => expect(withAlpha("#ff8a3d", 0.5)).toBe("rgba(255,138,61,0.5)"));
  it("clamps alpha", () => expect(withAlpha("#000000", 2)).toBe("rgba(0,0,0,1)"));
  it("passes non-hex through", () => expect(withAlpha("var(--x)", 0.4)).toBe("var(--x)"));
});

import { edge as edgeStyle } from "./color";
describe("edge", () => {
  it("sets the --edge custom property only", () => {
    expect(edgeStyle("#ff8a3d")).toEqual({ "--edge": "#ff8a3d" });
  });
});
