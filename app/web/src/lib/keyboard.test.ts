import { describe, expect, it } from "vitest";
import { keyboardInset } from "./keyboard";

describe("keyboardInset", () => {
  it("is the height the keyboard covers", () => {
    expect(keyboardInset(800, 480, 0)).toBe(320);
  });
  it("ignores small differences such as browser toolbars", () => {
    expect(keyboardInset(800, 760, 0)).toBe(0);
  });
  it("accounts for the visual viewport being scrolled", () => {
    expect(keyboardInset(800, 480, 100)).toBe(220);
  });
});
