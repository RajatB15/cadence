import { afterEach, describe, expect, it } from "vitest";
import { entryBundle, hasUnsavedWork, shouldAutoSync } from "./useAppLifecycle";

describe("entryBundle", () => {
  it("finds the hashed entry script", () => {
    expect(entryBundle('<head><script type="module" crossorigin src="/assets/index-BQY-rFjz.js"></script>')).toBe("/assets/index-BQY-rFjz.js");
  });
  it("returns null without one", () => expect(entryBundle("<html></html>")).toBeNull());
});

describe("shouldAutoSync", () => {
  const now = Date.parse("2026-10-24T12:00:00Z");
  it("syncs when never synced", () => expect(shouldAutoSync(null, false, now)).toBe(true));
  it("skips while a job runs", () => expect(shouldAutoSync(null, true, now)).toBe(false));
  it("skips inside the cooldown", () => expect(shouldAutoSync("2026-10-24T11:55:00", false, now)).toBe(false));
  it("syncs after the cooldown", () => expect(shouldAutoSync("2026-10-24T11:40:00Z", false, now)).toBe(true));
});

describe("hasUnsavedWork", () => {
  afterEach(() => (document.body.innerHTML = ""));
  it("is false on a quiet page", () => expect(hasUnsavedWork()).toBe(false));
  it("is true with an open dialog", () => {
    document.body.innerHTML = '<div role="dialog" data-state="open"></div>';
    expect(hasUnsavedWork()).toBe(true);
  });
  it("ignores a closed dialog", () => {
    document.body.innerHTML = '<div role="dialog" data-state="closed"></div>';
    expect(hasUnsavedWork()).toBe(false);
  });
  it("is true while typing into a field, false when it is empty", () => {
    document.body.innerHTML = "<input />";
    const input = document.querySelector("input")!;
    input.focus();
    expect(hasUnsavedWork()).toBe(false);
    input.value = "abc";
    expect(hasUnsavedWork()).toBe(true);
  });
});
