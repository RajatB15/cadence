import { describe, expect, it } from "vitest";
import { buildEventCardModel } from "./eventCard";
import type { ActivityDetail, EventDay, EventDetail, FitData } from "./types";

const act = (id: number, family: string, km: number, h: number) => ({
  id, name: `Leg ${id}`, type: family, family, start_time_utc: `2026-10-0${id}T08:00:00`, timezone: "UTC+0", local_date: `2026-10-0${id}`,
  duration_s: h * 3600, distance_m: km * 1000, elevation_gain_m: null, avg_hr: null, training_load: null,
});
const day = (n: number, a: ReturnType<typeof act>): EventDay => ({
  day: a.local_date, number: n, totals: { count: 1, distance_m: a.distance_m, moving_s: a.duration_s }, recovery: null, activities: [a],
});
const event = (days: EventDay[], families: Record<string, number>): EventDetail => ({
  id: 1, name: "Brick", created_at: "", start: days[0].day, end: days[days.length - 1].day, span_days: days.length, families,
  totals: { count: days.length, distance_m: 40000, moving_s: 14400, elapsed_s: 20000, calories: null, avg_hr: 140 }, linked: days.length, missing: 0, days,
});
const fit = (lat0: number): FitData => ({
  streams: {}, stream_stats: {}, route: Array.from({ length: 20 }, (_, i) => [lat0 + i * 0.001, 77.6] as [number, number]),
  zones: null, messages: {}, streamed_counts: {}, unknown_messages: [], decode_errors: [],
});
const detail = (a: ReturnType<typeof act>, f: FitData | null): ActivityDetail =>
  ({ activity: { ...a, source_id: "garmin" }, garmin_summary: { hrTimeInZone_2: 600, hrTimeInZone_4: 600 }, fit: f }) as unknown as ActivityDetail;

describe("event share card", () => {
  it("uses the event's totals, one joined route and the days as rows", () => {
    const a = act(1, "walk", 20, 6);
    const b = act(2, "walk", 20, 4);
    const m = buildEventCardModel(event([day(1, a), day(2, b)], { walk: 2 }), [detail(b, fit(13)), detail(a, fit(12.9))]);
    expect(m.kicker).toBe("Walk & hike · 2 days");
    expect(m.stats[0]).toEqual({ label: "Distance", value: "40.00", unit: "km" });
    expect(m.stats.some((s) => s.label === "Days" && s.value === "2")).toBe(true);
    expect(m.track?.points).toHaveLength(40);
    expect(m.track!.points[0].lat).toBeCloseTo(12.9, 5); // ordered by start time, not by load order
    expect(m.panel.rowsTitle).toBe("Days");
    expect(m.panel.zones?.map((z) => Math.round(z.pct))).toEqual([0, 50, 0, 50, 0]);
  });
  it("is a multisport card without a route when no recording has GPS, listing the legs", () => {
    const r = act(1, "ride", 30, 1.5);
    const u = act(1, "run", 10, 1);
    const ev = event([{ ...day(1, r), activities: [r, u] }], { ride: 1, run: 1 });
    const m = buildEventCardModel(ev, [detail(r, null), detail(u, null)]);
    expect(m.kicker).toBe("Multisport");
    expect(m.track).toBeNull();
    expect(m.panel.rowsTitle).toBe("Legs");
    expect(m.panel.rows).toHaveLength(2);
  });
  it("leaves out a stat nobody recorded rather than showing zero", () => {
    const a = act(1, "walk", 20, 6);
    const m = buildEventCardModel(event([day(1, a)], { walk: 1 }), []);
    expect(m.stats.find((s) => s.label === "Calories")).toBeUndefined();
  });
});
