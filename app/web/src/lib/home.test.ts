import { describe, expect, it } from "vitest";
import { allowance, arcDash, circumference, energyState, formatClock, fraction, isDimmed, localHour, nowView, orderVitals, parseEatBack, parseManualKcal, projectionMissing, projectionRange, ringGeometry, sectionLayout, vitalView, type SectionId } from "./home";
import fixtures from "./__fixtures__/home-payloads.json";
import type { CalorieSettingsView, HomeEnergy, HomePhase, MetricSummary } from "./types";

const metric = (name: string, extra: Partial<MetricSummary> = {}): MetricSummary => ({
  metric: name, label: name, unit: "", higher_is_better: true, latest: 5, latest_day: "2026-11-08", recent_mean: 5, baseline_mean: 5, delta_pct: null, spark: [], ...extra,
});

describe("ring math", () => {
  it("clamps fractions and treats missing as zero", () => {
    expect(fraction(50, 100)).toBe(0.5);
    expect(fraction(500, 100)).toBe(1);
    expect(fraction(null, 100)).toBe(0);
    expect(fraction(10, 0)).toBe(0);
    expect(fraction(-5, 100)).toBe(0);
  });
  it("arc dash starts where asked", () => {
    const c = circumference(10);
    const d = arcDash(10, 0.25, 0.75);
    expect(parseFloat(d.dasharray)).toBeCloseTo(c / 2, 1);
    expect(d.dashoffset).toBeCloseTo(-c / 4, 5);
    expect(parseFloat(arcDash(10, 0.8, 0.2).dasharray)).toBe(0);
  });
  it("stacks active after resting on the projection scale", () => {
    const g = ringGeometry({ burned: 1000, active: 300, resting: 700, projected: { lo: 2000, hi: 2500 }, eaten: 800, target: 2000 });
    expect(g.resting[1]).toBeCloseTo(0.28);
    expect(g.active).toEqual([g.resting[1], g.burnedEnd]);
    expect(g.range![0]).toBeCloseTo(0.8);
    expect(g.range![1]).toBe(1);
    expect(g.eaten).toBeCloseTo(0.4);
  });
  it("draws one arc when the split is unknown or inconsistent", () => {
    const g = ringGeometry({ burned: 1000, active: null, resting: null, projected: null, eaten: null, target: null });
    expect(g.active[0]).toBe(g.active[1]);
    expect(g.resting[1]).toBe(1);
    expect(g.range).toBeNull();
    expect(g.eaten).toBe(0);
  });
});

describe("calorie card state", () => {
  const burned = { total: 900, active: 200, resting: 700, as_of: "14:00" };
  const eaten = { kcal: 400, logged: true, entries: 2, protein_g: null };
  const ok: HomeEnergy = { status: "ok", burned, eaten, left: 1500, projected: { value: 2400, lo: 2300, hi: 2500, n: 20, method: "curve" }, projection_state: "ok" };
  it("handles absent blocks, unsupported Garmin kcal and just started", () => {
    expect(energyState(null, "left").kind).toBe("missing");
    expect(energyState({ status: "no_garmin_kcal" }, "left", true)).toEqual({ kind: "unsupported", demo: true });
    expect(energyState({ status: "just_started", burned: null }, "day_total").kind).toBe("just_started");
  });
  it("treats a zero burn right after midnight as just started, later as unsupported", () => {
    expect(energyState({ burned: { ...burned, total: 0 }, as_of_min: 5 }, "day_total").kind).toBe("just_started");
    expect(energyState({ burned: { ...burned, total: 0 }, as_of_min: 600 }, "left").kind).toBe("unsupported");
  });
  it("never shows left from an empty log, nor when the backend says day total", () => {
    expect(energyState(ok, "left")).toEqual({ kind: "ok", hasLog: true, showLeft: true, showProjection: true });
    expect(energyState({ ...ok, eaten: { ...eaten, kcal: null, logged: false }, left: null }, "left")).toMatchObject({ hasLog: false, showLeft: false });
    expect(energyState({ ...ok, eaten: { ...eaten, kcal: 0, logged: false }, left: 2000 }, "left")).toMatchObject({ hasLog: false, showLeft: false });
    expect(energyState(ok, "day_total")).toMatchObject({ showLeft: false });
    expect(energyState({ ...ok, left: null, above_by: 180 }, "left")).toMatchObject({ showLeft: true });
  });
  it("hides the projection unless the backend marks it usable", () => {
    expect(energyState({ ...ok, projection_state: "hidden" }, "left")).toMatchObject({ showProjection: false });
    expect(energyState({ ...ok, projected: null, projection_state: "insufficient" }, "left")).toMatchObject({ showProjection: false });
    expect(projectionRange({ value: 2, lo: 1000, hi: 3000, n: 8, method: "fallback" })).toBe("1,000–3,000 · rough");
    expect(projectionMissing({ projection_state: "hidden" })).toBeNull();
    expect(projectionMissing({ projection_state: "insufficient", copy: { status: "Not enough history yet for a projection (it needs about a week of days)." } })).toContain("about a week");
  });
  it("scales intake against the target plus what is eaten back", () => {
    expect(allowance({ target: { kcal: 2000, source: "history" }, eat_back_kcal: 210 })).toBe(2210);
    expect(allowance({ target: null })).toBeNull();
  });
  it("validates typed settings against the server ranges", () => {
    expect(parseManualKcal("2,350")).toEqual({ ok: true, value: 2350 });
    for (const bad of ["", "abc", "799", "6001", "2300.5"]) expect(parseManualKcal(bad).ok).toBe(false);
    expect(parseManualKcal("700", [500, 6000])).toEqual({ ok: true, value: 700 });
    const r = parseManualKcal("100");
    expect(r.ok === false && r.reason).toBe("Enter a whole number between 800 and 6,000 kcal.");
    expect(parseEatBack("0")).toEqual({ ok: true, value: 0 });
    expect(parseEatBack("100")).toEqual({ ok: true, value: 100 });
    expect(parseEatBack("101").ok).toBe(false);
    expect(parseEatBack("-5").ok).toBe(false);
  });
  it("formats clock minutes", () => {
    expect(formatClock(845)).toBe("14:05");
    expect(formatClock(null)).toBeNull();
    expect(formatClock(1500)).toBeNull();
  });
});

describe("vitals", () => {
  const all = ["steps", "sleep_hours", "hrv", "resting_hr", "body_battery", "stress", "vo2max"].map((n) => metric(n));
  it("orders by phase and drops metrics that are not on the rail", () => {
    expect(orderVitals(all, "morning").map((m) => m.metric)).toEqual(["sleep_hours", "hrv", "resting_hr", "body_battery", "steps", "stress"]);
    expect(orderVitals(all, "evening")[0].metric).toBe("steps");
    expect(orderVitals(all, undefined)[0].metric).toBe("steps");
  });
  it("marks yesterday's value stale and hides the chip without a baseline", () => {
    expect(vitalView(metric("hrv", { latest_day: "2026-11-07" }), "2026-11-08").stale).toBe(true);
    expect(vitalView(metric("hrv"), "2026-11-08").chip).toBeNull();
    expect(vitalView(metric("hrv", { delta_pct: -4.26 }), "2026-11-08").chip).toBe("−4.3% vs usual");
    expect(vitalView(metric("hrv", { delta_pct: 0.2 }), "2026-11-08").chip).toBe("at usual");
  });
  it("keeps the last 7 spark points", () => {
    const spark = Array.from({ length: 12 }, (_, i) => ({ day: String(i), value: i }));
    expect(vitalView(metric("hrv", { spark }), "2026-11-08").spark).toEqual([5, 6, 7, 8, 9, 10, 11]);
  });
});

describe("phase to cards", () => {
  const all: SectionId[] = ["vitals", "calories", "now", "planned", "status", "scores", "checkin", "tonight", "week", "recent", "weather", "strain", "read", "improve", "whatif", "gain", "streaks", "wins"];
  const avail = new Set(all);
  it("keeps every available card reachable (primary plus More)", () => {
    for (const phase of [undefined, "morning", "late", "sick", "race_day", "time_off"]) {
      const { primary, more } = sectionLayout(phase ? { phase, cards: ["now", "calories", "more"], hidden: ["checkin"] } : null, avail);
      expect(new Set([...primary, ...more])).toEqual(avail);
      expect(primary.filter((x) => more.includes(x))).toEqual([]);
    }
  });
  it("honours the backend's card order, maps readiness to the dials and ignores unknown ids and the more marker", () => {
    const { primary } = sectionLayout({ phase: "morning", cards: ["week", "bogus", "now", "readiness", "week", "more"] }, avail);
    expect(primary).toEqual(["week", "now", "planned", "scores"]);
  });
  it("puts the plan after Now only when the session is still relevant", () => {
    expect(sectionLayout({ cards: ["now", "week"], session_state: "open" }, avail).primary).toEqual(["now", "planned", "week"]);
    for (const s of ["deferred", "window_closed", "rest"]) {
      const { primary, more } = sectionLayout({ cards: ["now", "week"], session_state: s }, avail);
      expect(primary).toEqual(["now", "week"]);
      expect(more).toContain("planned");
    }
  });
  it("skips cards without content and falls back to a fixed order without a phase", () => {
    expect(sectionLayout({ cards: ["vitals", "now", "week"] }, new Set<SectionId>(["now", "week"])).primary).toEqual(["now", "week"]);
    expect(sectionLayout(null, avail).primary.slice(0, 3)).toEqual(["vitals", "calories", "now"]);
  });
  it("reads the backend copy as sent", () => {
    expect(nowView(null)).toBeNull();
    expect(nowView({ phase: "late", copy: {} })).toBeNull();
    const v = nowView({ phase: "late", copy: { headline: "Day done", session: { title: "Not today", detail: "Tomorrow." }, sleep: "Sleep not synced yet", flags: ["No Garmin data for today yet."] } });
    expect(v).toMatchObject({ eyebrow: "Winding down", headline: "Day done", session: { title: "Not today" }, notes: ["Sleep not synced yet", "No Garmin data for today yet."] });
  });
  it("dims by the backend's list, with readiness meaning the dials", () => {
    expect(isDimmed({ dimmed: ["readiness"] }, "scores")).toBe(true);
    expect(isDimmed({ dimmed: [] }, "scores")).toBe(false);
    expect(isDimmed(null, "scores")).toBe(false);
  });
  it("uses the backend's vitals order when given", () => {
    const all = ["steps", "hrv", "stress"].map((n) => metric(n));
    expect(orderVitals(all, "morning", ["stress", "steps"]).map((m) => m.metric)).toEqual(["stress", "steps"]);
  });
});

// ---- real payloads from the backend (synthetic data, trimmed) -----------------------------------------------------

interface Scenario { energy: HomeEnergy; phase: HomePhase; coach_today: { kind: string; title: string; status: string | null }; metrics: string[]; planned_today: { title: string; status: string }[] }
const F = fixtures as unknown as Record<string, Scenario & CalorieSettingsView & { body: unknown; status: number; resp: { detail: unknown } }>;
const scenario = (n: string) => F[`overview_${n}`] as Scenario;
const allText = (s: Scenario) => JSON.stringify([s.phase.copy, s.energy.copy, s.coach_today.title]);

describe("real payloads: card order", () => {
  const avail = new Set<SectionId>(["vitals", "calories", "now", "planned", "status", "scores", "checkin", "week", "recent", "tonight"]);
  it("follows the order the backend sent in the morning, at midday and late", () => {
    expect(sectionLayout(scenario("0700_nofood").phase, avail).primary).toEqual(["vitals", "now", "planned", "scores", "checkin", "calories", "week", "recent"]);
    expect(sectionLayout(scenario("1300_food").phase, avail).primary).toEqual(["vitals", "calories", "now", "planned", "scores", "checkin", "week", "recent"]);
    const late = sectionLayout(scenario("2130_planned").phase, avail);
    expect(late.primary).toEqual(["now", "vitals", "calories", "week", "scores"]);
    expect(late.more).toEqual(expect.arrayContaining(["planned", "checkin", "recent"]));
  });
  it("time off and the rest of the states keep Now first or vitals first as sent", () => {
    expect(sectionLayout(scenario("1300_timeoff").phase, avail).primary).toEqual(["now", "vitals", "calories", "checkin"]);
    expect(scenario("1300_timeoff").phase.phase).toBe("time_off");
  });
  it("dims the dials late and orders the rail evening style", () => {
    const p = scenario("2130_planned").phase;
    expect(isDimmed(p, "scores")).toBe(true);
    const metrics = scenario("2130_planned").metrics.map((m) => metric(m));
    expect(orderVitals(metrics, p.phase, p.vitals_order)[0].metric).toBe("steps");
  });
});

describe("real payloads: late evening never says a workout is open", () => {
  for (const name of ["2130_planned", "2330_food"]) {
    it(`${name}: session deferred, no 'open' wording anywhere, plan card is quiet`, () => {
      const s = scenario(name);
      expect(s.phase.session_state).toBe("deferred");
      expect(s.coach_today.status).toBe("deferred");
      expect(allText(s).toLowerCase()).not.toMatch(/\bstill open\b|\bopen\b/);
      const { primary, more } = sectionLayout(s.phase, new Set<SectionId>(["vitals", "calories", "now", "planned", "week", "scores"]));
      expect(primary).not.toContain("planned");
      expect(more).toContain("planned");
      const v = nowView(s.phase)!;
      expect(v.session?.title).toBe("Not today");
    });
  }
  it("at 23:30 the projection is hidden and the card has no projection cell", () => {
    const e = scenario("2330_food").energy;
    expect(e.projection_state).toBe("hidden");
    expect(energyState(e, scenario("2330_food").phase.hints?.calories)).toMatchObject({ kind: "ok", showProjection: false, showLeft: false });
    expect(projectionMissing(e)).toBeNull();
  });
  it("at 21:30 the backend says day total, so no left figure is shown even though one exists", () => {
    const s = scenario("2130_planned");
    expect(s.energy.left).toBe(500);
    expect(energyState(s.energy, s.phase.hints?.calories)).toMatchObject({ showLeft: false, showProjection: true });
  });
  it("just after midnight shows just-started with yesterday and no burn", () => {
    const s = scenario("0030_justdawn");
    expect(s.energy.status).toBe("just_started");
    expect(energyState(s.energy, s.phase.hints?.calories).kind).toBe("just_started");
  });
});

describe("real payloads: empty and missing states", () => {
  it("no food logged: nothing is zero and there is no left", () => {
    const s = scenario("1300_nofood");
    expect(s.energy.eaten).toMatchObject({ kcal: null, logged: false, entries: 0 });
    expect(s.energy.left).toBeNull();
    expect(energyState(s.energy, s.phase.hints?.calories)).toMatchObject({ hasLog: false, showLeft: false });
    expect(s.energy.copy?.eaten).toBe("Nothing logged yet");
  });
  it("no Garmin kcal: unsupported, with the backend's sentence", () => {
    const s = scenario("1300_no_kcal");
    expect(energyState(s.energy, s.phase.hints?.calories)).toEqual({ kind: "unsupported", demo: false });
    expect(s.energy.burned).toBeNull();
    expect(s.energy.copy?.status).toBeTruthy();
  });
  it("insufficient history: burn is shown, projection is not, and the reason is the backend's", () => {
    const s = scenario("1300_insufficient");
    expect(energyState(s.energy, s.phase.hints?.calories)).toMatchObject({ kind: "ok", showProjection: false });
    expect(projectionMissing(s.energy)).toBe(s.energy.copy?.status);
  });
  it("food logged with a target: left is on the same basis as the ring", () => {
    const s = scenario("1300_food");
    const e = s.energy;
    expect(energyState(e, s.phase.hints?.calories)).toMatchObject({ showLeft: true, showProjection: true });
    expect(allowance(e)! - e.eaten!.kcal!).toBe(e.left);
  });
  it("manual target comes through as source manual with the floor note, never as a block", () => {
    const e = scenario("1300_manual").energy;
    expect(e.target).toMatchObject({ kcal: 1300, source: "manual", below_floor: true });
    expect(e.settings).toMatchObject({ mode: "manual", manual_kcal: 1300 });
    expect(e.copy?.target_notes?.length).toBeGreaterThan(0);
  });
});

describe("real payloads: ring math", () => {
  it("uses the real burn, projection and allowance at 13:00", () => {
    const e = scenario("1300_food").energy;
    const g = ringGeometry({ burned: e.burned!.total, active: e.burned!.active, resting: e.burned!.resting, projected: e.projected!, eaten: e.eaten!.kcal, target: allowance(e) });
    const scale = e.projected!.hi;
    expect(g.resting[1]).toBeCloseTo(e.burned!.resting! / scale, 5);
    expect(g.active[1]).toBeCloseTo(e.burned!.total! / scale, 5);
    expect(g.range![1]).toBe(1);
    expect(g.eaten).toBeCloseTo(e.eaten!.kcal! / allowance(e)!, 5);
    expect(g.burnedEnd).toBeLessThan(0.6);
  });
  it("without a projection the burn arc fills to the whole scale", () => {
    const e = scenario("2330_food").energy;
    const g = ringGeometry({ burned: e.burned!.total, active: e.burned!.active, resting: e.burned!.resting, projected: null, eaten: e.eaten!.kcal, target: allowance(e) });
    expect(g.burnedEnd).toBe(1);
    expect(g.range).toBeNull();
  });
});

describe("real payloads: settings", () => {
  it("reads the settings shape", () => {
    const g = F.settings_get as unknown as CalorieSettingsView;
    expect(g).toMatchObject({ mode: "auto", manual_kcal: null, eat_back_pct: 50, pace: true, ranges: { manual_kcal: [800, 6000], eat_back_pct: [0, 100] }, floor_kcal: 1500 });
  });
  it("our validators agree with every body the server accepted or refused", () => {
    const get = (i: number) => F[`settings_put_${i}`] as unknown as { body: Record<string, number | string | null>; status: number };
    expect(get(0).status).toBe(200);
    expect(parseManualKcal(String(get(0).body.manual_kcal)).ok).toBe(true);
    expect(parseEatBack(String(get(0).body.eat_back_pct)).ok).toBe(true);
    expect(get(1).status).toBe(422);
    expect(parseManualKcal(String(get(1).body.manual_kcal)).ok).toBe(false);
    expect(parseManualKcal(String(get(2).body.manual_kcal)).ok).toBe(false);
    expect(parseEatBack(String(get(3).body.eat_back_pct)).ok).toBe(false);
    expect(get(4).status).toBe(400);
  });
});

describe("localHour", () => {
  it("prefers the server's local time over the device clock", () => {
    expect(localHour("22:15", 9)).toBe(22);
    expect(localHour("07:00", 21)).toBe(7);
  });
  it("falls back when missing or malformed", () => {
    expect(localHour(undefined, 9)).toBe(9);
    expect(localHour(null, 9)).toBe(9);
    expect(localHour("soon", 9)).toBe(9);
    expect(localHour("27:00", 9)).toBe(9);
  });
});
