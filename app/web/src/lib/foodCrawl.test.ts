import { describe, expect, it } from "vitest";
import { crawlSegments, librarySegments, percent, roughDuration } from "./foodCrawl";

describe("crawl progress helpers", () => {
  it("keeps all three states even when one is empty", () => {
    const s = crawlSegments({ parsed: 10, failed: 0, untried: 90 });
    expect(s.map((x) => [x.key, x.pages])).toEqual([["parsed", 10], ["failed", 0], ["untried", 90]]);
  });

  it("does not turn a missing catalogue into zero dishes", () => {
    expect(librarySegments({ pages: null, dishes: null, merged: null, dropped: [], no_latin_name: null, with_portion: null, unverified: null })).toBeNull();
    const s = librarySegments({ pages: 100, dishes: 30, merged: 60, dropped: [{ reason: "a", pages: 4 }, { reason: "b", pages: 3 }], no_latin_name: 3, with_portion: 20, unverified: 25 })!;
    expect(s.map((x) => x.pages)).toEqual([30, 60, 7, 3]);
  });

  it("formats shares and rough durations", () => {
    expect(percent(0, 0)).toBe("0%");
    expect(percent(1, 1000)).toBe("<1%");
    expect(percent(1, 4)).toBe("25%");
    expect(roughDuration("2026-10-24T10:00:00Z", "2026-10-24T10:42:00Z")).toBe("about 40 min");
    expect(roughDuration("2026-10-24T10:00:00Z", "2026-10-24T17:00:00Z")).toBe("about 7.0 h");
    expect(roughDuration("2026-10-24T10:00:00Z", "2026-10-25T10:00:00Z")).toBe("about 24 h");
  });
});
