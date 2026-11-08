// Pure model for the Home "day ring": four concentric rings, one per domain, each a share of an openly stated reference.
// Nothing is blended into one score. A ring with no data is "missing" (empty track, dash), never zero.
import type { HomeEnergy, MetricSummary } from "./types";
import { fraction } from "./home";

export type DayRingKey = "recovery" | "sleep" | "move" | "fuel";

export interface DayRingItem {
  key: DayRingKey;
  label: string;
  /** Accent token name (a key of the palette). */
  accent: "mint" | "violet" | "lime" | "gold";
  /** 0..1 share of the reference; 0 when missing. */
  fraction: number;
  /** Text for the value ("85", "7h 39m", "4,210", "1,840") and its small unit/reference line. */
  value: string;
  sub: string;
  missing: boolean;
  /** Data is from an earlier day: drawn muted, never celebrated. */
  stale: boolean;
  /** Reached the reference with fresh data: eligible for the one-off celebration. */
  closed: boolean;
  to: string;
}

export const STEP_REFERENCE = 10_000;
export const SLEEP_REFERENCE_H = 8;

const hm = (h: number) => `${Math.floor(h)}h ${String(Math.round((h % 1) * 60)).padStart(2, "0")}m`;
const metric = (ms: MetricSummary[], k: string) => ms.find((m) => m.metric === k) ?? null;

export interface DayRingInput {
  metrics: MetricSummary[];
  today: string;
  readiness: number | null;
  sleepNeedH?: number | null;
  energy: HomeEnergy | null | undefined;
}

export function dayRings(i: DayRingInput): DayRingItem[] {
  const out: DayRingItem[] = [];
  const mk = (r: Omit<DayRingItem, "closed" | "missing"> & { missing?: boolean }): DayRingItem => {
    const missing = r.missing ?? false;
    return { ...r, missing, closed: !missing && !r.stale && r.fraction >= 1 };
  };

  out.push(i.readiness == null
    ? mk({ key: "recovery", label: "Recovery", accent: "mint", fraction: 0, value: "—", sub: "no readiness yet", missing: true, stale: false, to: "/coach" })
    : mk({ key: "recovery", label: "Recovery", accent: "mint", fraction: fraction(i.readiness, 100), value: String(Math.round(i.readiness)), sub: "readiness of 100", stale: false, to: "/coach" }));

  const sleep = metric(i.metrics, "sleep_hours");
  const need = i.sleepNeedH && i.sleepNeedH > 0 ? i.sleepNeedH : SLEEP_REFERENCE_H;
  out.push(!sleep
    ? mk({ key: "sleep", label: "Sleep", accent: "violet", fraction: 0, value: "—", sub: "not synced", missing: true, stale: false, to: "/metrics/sleep_hours" })
    : mk({ key: "sleep", label: "Sleep", accent: "violet", fraction: fraction(sleep.latest, need), value: hm(sleep.latest), sub: i.sleepNeedH ? `of your ${need.toFixed(need % 1 ? 1 : 0)} h need` : `of ${need} h reference`, stale: sleep.latest_day < i.today, to: "/metrics/sleep_hours" }));

  const steps = metric(i.metrics, "steps");
  out.push(!steps
    ? mk({ key: "move", label: "Move", accent: "lime", fraction: 0, value: "—", sub: "not synced", missing: true, stale: false, to: "/metrics/steps" })
    : mk({ key: "move", label: "Move", accent: "lime", fraction: fraction(steps.latest, STEP_REFERENCE), value: Math.round(steps.latest).toLocaleString(), sub: "steps of 10,000", stale: steps.latest_day < i.today, to: "/metrics/steps" }));

  const e = i.energy;
  const eaten = e?.eaten?.logged ? e.eaten.kcal : null;
  const target = e?.target?.kcal ?? null;
  const burned = e?.burned?.total ?? null;
  if (eaten != null && target) {
    out.push(mk({ key: "fuel", label: "Fuel", accent: "gold", fraction: fraction(eaten, target), value: Math.round(eaten).toLocaleString(), sub: `kcal eaten of ${Math.round(target).toLocaleString()}`, stale: false, to: "/food" }));
  } else if (burned != null && burned > 0) {
    const ref = e?.projected?.value ?? null;
    out.push(mk({ key: "fuel", label: "Fuel", accent: "gold", fraction: ref ? fraction(burned, ref) : 0, value: Math.round(burned).toLocaleString(), sub: ref ? "kcal burned so far" : "kcal burned, nothing logged", stale: false, to: "/food" }));
  } else {
    out.push(mk({ key: "fuel", label: "Fuel", accent: "gold", fraction: 0, value: "—", sub: "nothing logged", missing: true, stale: false, to: "/food" }));
  }
  return out;
}

/** One sentence for screen readers. */
export function dayRingSummary(rings: DayRingItem[]): string {
  return rings.map((r) => (r.missing ? `${r.label}: no data` : `${r.label}: ${r.value}, ${r.sub}${r.stale ? ", from an earlier day" : ""}`)).join(". ");
}
