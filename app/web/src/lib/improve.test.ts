import { describe, expect, it } from "vitest";
import {
  ASSOCIATION_NOTE, FORBIDDEN_WORDS, ciExcludesZero, ciText, citationLabel, doiUrl, driverSentence, homeCard, neededText,
  normalizeCitations, orderDrivers, orderStarts, orderWatch, progressPct, sectionStatuses, signed, supportsImprove, verdictText,
} from "./improve";
import type { ImproveReport } from "./types";

const driver = { id: "alcohol_hrv", exposure: "2+ drinks", reference: "no drinks", diff: -7.4, unit: "ms", pct: -11.9, ci: [-12.1, -2.7] as [number, number], n_exposed: 9, n_reference: 41, grade: "clear" as const, q: 0.03 };

describe("formatting", () => {
  it("signs with a real minus and tolerates missing", () => {
    expect(signed(-7.4)).toBe("−7.4");
    expect(signed(3)).toBe("+3");
    expect(signed(null)).toBe("—");
    expect(ciText([-12.1, -2.7], "ms")).toBe("95% range −12.1 to −2.7 ms");
    expect(ciText(null)).toBeNull();
    expect(ciExcludesZero([-1, 2])).toBe(false);
    expect(ciExcludesZero([1, 2])).toBe(true);
  });
  it("writes a non-causal sentence with sample sizes", () => {
    const s = driverSentence(driver, "overnight HRV");
    expect(s).toContain("On 9 2+ drinks (vs 41 no drinks) your overnight HRV was 7.4 ms lower (−12%)");
    expect(s).toContain("95% range");
    expect(s).not.toMatch(FORBIDDEN_WORDS);
    expect(driverSentence({ id: "x" }, "HRV")).toContain("could not be estimated");
  });
  it("copy constants avoid causal or diagnostic words", () => {
    expect(ASSOCIATION_NOTE).not.toMatch(FORBIDDEN_WORDS);
    expect(verdictText({ verdict: "higher", change: 4.1, ci: [-1, 9.2], unit: "ms", window: { n_before: 27, n_after: 26 } })).not.toMatch(FORBIDDEN_WORDS);
  });
});

describe("ordering", () => {
  it("orders drivers clear first, hides untested grades, caps at 5", () => {
    const ds = [
      { id: "a", grade: "hint" as const, q: 0.1 },
      { id: "b", grade: "clear" as const, q: 0.04 },
      { id: "c" },
      { id: "d", grade: "clear" as const, q: 0.01 },
      ...Array.from({ length: 6 }, (_, i) => ({ id: `z${i}`, grade: "hint" as const, q: 0.15 })),
    ];
    const out = orderDrivers(ds);
    expect(out.map((d) => d.id).slice(0, 3)).toEqual(["d", "b", "a"]);
    expect(out).toHaveLength(5);
    expect(orderDrivers(undefined)).toEqual([]);
  });
  it("orders starts by score then id, watch act before look", () => {
    expect(orderStarts([{ id: "b", score: 5 }, { id: "a", score: 5 }, { id: "c", score: 9 }, { id: "d" }]).map((s) => s.id)).toEqual(["c", "a", "b", "d"]);
    expect(orderWatch([{ id: "x", severity: "look" }, { id: "y", severity: "act" }]).map((w) => w.id)).toEqual(["y", "x"]);
  });
});

describe("citations", () => {
  it("accepts a map or a list and never invents labels", () => {
    expect(normalizeCitations([{ id: "a", short: "A 2010" }]).a.short).toBe("A 2010");
    expect(normalizeCitations({ b: { id: "", short: "B" } }).b.id).toBe("b");
    expect(normalizeCitations(undefined)).toEqual({});
    expect(citationLabel("seiler2010", {})).toBe("seiler2010");
    expect(citationLabel("a", { a: { id: "a", short: "Seiler 2010" } })).toBe("Seiler 2010");
    expect(doiUrl({ id: "a", doi: "10.1/x" })).toBe("https://doi.org/10.1/x");
    expect(doiUrl({ id: "a", url: "javascript:alert(1)" })).toBeNull();
  });
});

describe("empty-state logic", () => {
  it("collecting shows needs and no advice; ready with nothing is empty", () => {
    const r: ImproveReport = { metric: "hrv", state: "collecting", data: { nights: 12, needed: 40 }, progress: [{ key: "late_meal", have: 4, needed: 8 }], start: [{ id: "x" }] };
    const st = Object.fromEntries(sectionStatuses(r).map((s) => [s.key, s.status]));
    expect(st.start).toBe("collecting");
    expect(st.moving).toBe("collecting");
    expect(neededText(r)).toBe("12 of 40 days with data (28 more needed) · late meal: 4 of 8");
    const ready = Object.fromEntries(sectionStatuses({ metric: "hrv", state: "ready" }).map((s) => [s.key, s.status]));
    expect(ready.start).toBe("empty");
    expect(Object.fromEntries(sectionStatuses({ metric: "hrv", state: "ready", benchmarks: { profile_missing: true } }).map((s) => [s.key, s.status])).compare).toBe("collecting");
  });
  it("progress is clamped and zero-safe", () => {
    expect(progressPct(12, 40)).toBe(30);
    expect(progressPct(5, 0)).toBe(0);
    expect(progressPct(99, 40)).toBe(100);
  });
  it("verdict words are cautious", () => {
    expect(verdictText({ verdict: "no_clear_change", window: { n_before: 27, n_after: 26 } })).toContain("No clear change");
    expect(verdictText(null)).toBeNull();
  });
});

describe("home card", () => {
  it("prefers a watch flag, then focus, else hides", () => {
    expect(homeCard(null)).toBeNull();
    expect(homeCard({ state: "unsupported" })).toBeNull();
    expect(homeCard({ watch: [{ title: "Look", severity: "look" }, { title: "Act", severity: "act" }] })).toMatchObject({ kind: "watch", text: "Act" });
    expect(homeCard({ focus: { check_on: "2026-12-07", priority: { title: "Sleep", target_metrics: ["hrv"] } } })).toMatchObject({ kind: "focus", metric: "hrv" });
    expect(homeCard({ focus: { priority: null } })).toBeNull();
  });
  it("supports only the three metrics", () => {
    expect(supportsImprove("hrv")).toBe(true);
    expect(supportsImprove("steps")).toBe(false);
  });
});
