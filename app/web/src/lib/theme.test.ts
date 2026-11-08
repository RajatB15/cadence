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
  it("follows the system until a choice is stored", () => {
    expect(resolveTheme(null, true)).toBe("light");
    expect(resolveTheme(undefined, false)).toBe("dark");
    expect(resolveTheme("dark", true)).toBe("dark");
    expect(resolveTheme("light", false)).toBe("light");
    expect(resolveTheme("garbage", true)).toBe("light");
  });
  it("persists and clears a choice", () => {
    const s = mem();
    expect(readChoice(s)).toBe("system");
    expect(writeChoice("light", s)).toBe(true);
    expect(readChoice(s)).toBe("light");
    writeChoice("system", s);
    expect(readChoice(s)).toBe("system");
  });
  it("falls back when storage throws or is missing", () => {
    expect(readChoice(broken)).toBe("system");
    expect(writeChoice("dark", broken)).toBe(false);
    expect(writeChoice("dark", null)).toBe(false);
  });
  it("light and dark palettes define the same keys", () => {
    expect(Object.keys(PALETTES.light).sort()).toEqual(Object.keys(PALETTES.dark).sort());
  });
});
