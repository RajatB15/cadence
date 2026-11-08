import { describe, expect, it } from "vitest";
import fixtures from "./__fixtures__/improve-payloads.json";
import {
  FORBIDDEN_WORDS, blockedText, citationLabel, doiUrl, driverSentence, homeCard, neededText, normalizeCitations, numberText, orderDrivers,
  orderStarts, orderWatch, reviewNote, sectionStatuses, supportsImprove, verdictText, watchLabel,
} from "./improve";
import type { ImproveReport, ImproveSummary } from "./types";

// Real-shape payloads from the backend (synthetic data), trimmed. Regenerate with the throwaway script described in the PR notes.
const F = fixtures as unknown as Record<string, ImproveReport & ImproveSummary>;
const reports = Object.entries(F).filter(([k]) => !k.startsWith("summary_"));
const summaries = Object.entries(F).filter(([k]) => k.startsWith("summary_"));

describe("real payload shapes", () => {
  it("routes the backend slugs", () => {
    for (const m of ["hrv", "resting_hr", "vo2max"]) expect(supportsImprove(m)).toBe(true);
    expect(supportsImprove("rhr")).toBe(false);
    for (const [, r] of reports) expect(supportsImprove(r.metric)).toBe(true);
  });

  it.each(reports)("%s passes through every pure helper without throwing", (_name, r) => {
    const cites = normalizeCitations(r.citations);
    for (const id of Object.keys(cites)) {
      expect(citationLabel(id, cites)).toBeTruthy();
      expect(() => doiUrl(cites[id])).not.toThrow();
    }
    const drivers = orderDrivers(r.drivers);
    for (const d of drivers) {
      const s = driverSentence(d, "overnight HRV");
      expect(s).toBeTruthy();
      expect(s).not.toMatch(FORBIDDEN_WORDS);
    }
    for (const s of orderStarts(r.start)) for (const v of Object.values(s.numbers ?? {})) expect(typeof numberText(v)).toBe("string");
    for (const w of orderWatch(r.watch)) expect(watchLabel(w)).not.toBe("");
    expect(sectionStatuses(r)).toHaveLength(6);
    expect(() => neededText(r)).not.toThrow();
    expect(() => verdictText(r.review)).not.toThrow();
    expect(blockedText(r.focus?.blocked_by)).toSatisfy((v: string | null) => v === null || !v.includes("_"));
  });

  it("ready HRV: drivers use the backend statement, starts are ordered, nothing is empty", () => {
    const r = F.hrv_ready;
    const st = Object.fromEntries(sectionStatuses(r).map((s) => [s.key, s.status]));
    expect(st.moving).toBe("ready");
    expect(st.start).toBe("ready");
    expect(st.focus).toBe("ready");
    expect(st.review).toBe("empty");
    expect(st.compare).toBe("ready");
    const [d] = orderDrivers(r.drivers);
    expect(d.grade).toBe("clear");
    expect(driverSentence(d, "overnight HRV")).toBe(d.statement);
    const starts = orderStarts(r.start);
    expect(starts.map((s) => s.score ?? 0)).toEqual([...starts.map((s) => s.score ?? 0)].sort((a, b) => b - a));
    expect(r.baseline?.mean_7d).toBeTypeOf("number");
    // ci arrays inside numbers render as a range, not "a,b"
    expect(numberText([-8.5, -6.2])).toBe("−8.5 to −6.2");
  });

  it("collecting VO2max shows progress and 'what's needed', not empty sections", () => {
    const r = F.vo2max_collecting;
    expect(r.state).toBe("collecting");
    expect(neededText(r)).toMatch(/3 of 6/);
    const st = sectionStatuses(r);
    expect(st.filter((s) => s.key !== "compare").every((s) => s.status !== "ready")).toBe(true);
    expect(st.find((s) => s.key === "moving")?.status).toBe("collecting");
    expect(st.find((s) => s.key === "start")?.status).toBe("collecting");
  });

  it("unsupported payloads carry empty collections and a message, and the summary hides the home card", () => {
    for (const k of ["vo2max_unsupported", "hrv_unsupported_api"]) {
      const r = F[k];
      expect(r.state).toBe("unsupported");
      expect(r.message).toBeTruthy();
      expect(orderDrivers(r.drivers)).toEqual([]);
      expect(() => sectionStatuses(r)).not.toThrow();
    }
    expect(homeCard(F.summary_unsupported)).toBeNull();
  });

  it("act-severity watch outranks look and gets a readable label; blocked focus has no raw id", () => {
    const r = F.hrv_act;
    const w = orderWatch(r.watch);
    expect(w[0].severity).toBe("act");
    expect(watchLabel(w[0])).not.toBe("Worth a look");
    expect(blockedText(r.focus?.blocked_by)).toBe(watchLabel({ id: r.focus?.blocked_by ?? "" }));
    const card = homeCard(F.summary_act);
    expect(card?.kind).toBe("watch");
    expect(card && "severity" in card ? card.severity : null).toBe("act");
  });

  it("home card falls back to the focus priority when there is no flag", () => {
    const card = homeCard(F.summary_ready);
    expect(card?.kind).toBe("focus");
    expect(card && card.kind === "focus" ? card.checkOn : null).toBeTruthy();
    expect(homeCard(F.summary_collecting)).toBeNull();
  });

  it.each(summaries)("%s never throws in homeCard", (_n, s) => {
    expect(() => homeCard(s)).not.toThrow();
  });

  it("review: statement is used verbatim and the verdict maps to the section", () => {
    const r = F.hrv_reviewed;
    expect(r.review?.verdict).toBe("no_clear_change");
    expect(verdictText(r.review)).toBe(r.review?.statement);
    expect(sectionStatuses(r).find((s) => s.key === "review")?.status).toBe("ready");
    expect(reviewNote({ statement: "Not enough readings to compare yet (3 before, 0 after; at least 14 each side)." })).toMatch(/Not enough/);
    expect(F.hrv_with_focus.focus?.proposed).toBe(false);
  });

  it("citation map values tolerate missing doi/url/summary and unverified entries", () => {
    const cites = normalizeCitations(F.hrv_ready.citations);
    for (const c of Object.values(cites)) {
      expect(c.id).toBeTruthy();
      expect(doiUrl(c) === null || /^https?:\/\//.test(doiUrl(c)!)).toBe(true);
    }
  });
});
