import { describe, expect, it } from "vitest";
import { PALETTES, readChoice, resolveTheme, writeChoice } from "./theme";

const mem = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
};
const broken = {
  getItem: () => { throw new Error("blocked"); },
  setItem: () => { throw new Error("blocked"); },
  removeItem: () => { throw new Error("blocked"); },
};

describe("theme", () => {
  it("follows the clock until a choice is stored", () => {
    expect(resolveTheme(null, false, 12 * 60)).toBe("light");
    expect(resolveTheme(undefined, true, 22 * 60)).toBe("dark");
    expect(resolveTheme("garbage", true, 7 * 60)).toBe("light");
    expect(resolveTheme("garbage", false, 3 * 60)).toBe("dark");
  });
  it("a pinned choice or the device preference beats the clock", () => {
    expect(resolveTheme("dark", true, 12 * 60)).toBe("dark");
    expect(resolveTheme("light", false, 23 * 60)).toBe("light");
    expect(resolveTheme("system", true, 23 * 60)).toBe("light");
    expect(resolveTheme("system", false, 12 * 60)).toBe("dark");
  });
  it("persists and clears a choice", () => {
    const s = mem();
    expect(readChoice(s)).toBe("auto");
    expect(writeChoice("light", s)).toBe(true);
    expect(readChoice(s)).toBe("light");
    writeChoice("system", s);
    expect(readChoice(s)).toBe("system");
    writeChoice("auto", s);
    expect(readChoice(s)).toBe("auto");
  });
  it("falls back when storage throws or is missing", () => {
    expect(readChoice(broken)).toBe("auto");
    expect(writeChoice("dark", broken)).toBe(false);
    expect(writeChoice("dark", null)).toBe(false);
  });
  it("light and dark palettes define the same keys", () => {
    expect(Object.keys(PALETTES.light).sort()).toEqual(Object.keys(PALETTES.dark).sort());
  });
});
