// Pure model for the Home "Today" meters: one per domain, each a share of an openly stated reference, ordered and worded for the
// time of day. Nothing is blended into one score. A meter with no data is "missing" (empty track, dash), never zero.
// Calories live in the balance block of the same card, so they are not repeated here; protein is the fuel meter.
import type { HomeEnergy, MetricSummary } from "./types";
import { fraction } from "./home";
import { dayShare, moment, WAKE_END_MIN, WAKE_START_MIN, type Moment } from "./moment";

export type DayRingKey = "recovery" | "sleep" | "move" | "protein";

export interface DayRingItem {
  key: DayRingKey;
  label: string;
  /** Accent token name (a key of the palette). */
  accent: "mint" | "violet" | "lime" | "sky";
  /** 0..1 share of the reference; 0 when missing. */
  fraction: number;
  /** Text for the value ("85", "7h 39m", "4,210", "1,840") and its small unit/reference line. */
  value: string;
  sub: string;
  missing: boolean;
  /** 0..1 share of the reference you would have reached by now at an even pace (steps); null when pacing does not apply. */
  pace: number | null;
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
  /** Minutes after local midnight. Without it the order is fixed and nothing is paced. */
  minutes?: number | null;
}

/** Which meters matter most now: recovery and sleep after waking, movement and protein through the day, sleep from when eating is done. */
export const ORDER: Record<Moment, DayRingKey[]> = {
  morning: ["recovery", "sleep", "move", "protein"],
  midday: ["move", "protein", "recovery", "sleep"],
  afternoon: ["protein", "move", "recovery", "sleep"],
  evening: ["sleep", "protein", "recovery", "move"],
  night: ["sleep", "recovery", "protein", "move"],
};

export function dayRings(i: DayRingInput): DayRingItem[] {
  const out: DayRingItem[] = [];
  const mk = (r: Omit<DayRingItem, "closed" | "missing" | "pace"> & { missing?: boolean; pace?: number | null }): DayRingItem => {
    const missing = r.missing ?? false;
    return { ...r, pace: r.pace ?? null, missing, closed: !missing && !r.stale && r.fraction >= 1 };
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
  const min = i.minutes ?? null;
  out.push(!steps
    ? mk({ key: "move", label: "Move", accent: "lime", fraction: 0, value: "—", sub: "not synced", missing: true, stale: false, to: "/metrics/steps" })
    : (() => {
      const stale = steps.latest_day < i.today;
      const paced = min != null && !stale && min > WAKE_START_MIN && min < WAKE_END_MIN;
      const expected = paced ? dayShare(min!) * STEP_REFERENCE : 0;
      return mk({ key: "move", label: "Move", accent: "lime", fraction: fraction(steps.latest, STEP_REFERENCE), value: Math.round(steps.latest).toLocaleString(), sub: paced ? stepNote(steps.latest, expected) : "steps of 10,000", pace: paced ? dayShare(min!) : null, stale, to: "/metrics/steps" });
    })());

  const e = i.energy;
  const g = e?.eaten?.logged ? e.eaten.protein_g : null;
  const band = e?.target?.protein ? ([e.target.protein.low_g, e.target.protein.high_g] as const) : null;
  out.push(g == null || !band
    ? mk({ key: "protein", label: "Protein", accent: "sky", fraction: 0, value: "—", sub: !band ? "no target yet" : e?.eaten?.logged ? "no protein figures" : "nothing logged", missing: true, stale: false, to: "/food" })
    : mk({ key: "protein", label: "Protein", accent: "sky", fraction: fraction(g, band[0]), value: `${Math.round(g)} g`, sub: g < band[0] ? `${Math.round(band[0] - g)} g to the low end of ${band[0]}–${band[1]} g` : g <= band[1] ? `in your ${band[0]}–${band[1]} g range` : `above your ${band[0]}–${band[1]} g range`, stale: false, to: "/food" }));

  if (min != null) {
    const order = ORDER[moment(min)];
    out.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
    if (moment(min) !== "morning") for (const it of out) if (it.key === "sleep" && !it.missing) it.sub = `last night, ${it.sub}`;
  }
  return out;
}

/** One sentence for screen readers. */
export function dayRingSummary(rings: DayRingItem[]): string {
  return rings.map((r) => (r.missing ? `${r.label}: no data` : `${r.label}: ${r.value}, ${r.sub}${r.stale ? ", from an earlier day" : ""}`)).join(". ");
}

/** Where steps stand against an even pace for this time of day; wording stays descriptive, never praise or blame. */
export function stepNote(steps: number, expected: number): string {
  const diff = Math.round(steps - expected);
  const tol = Math.max(300, expected * 0.1);
  if (Math.abs(diff) <= tol) return "about on pace for the time of day";
  return diff > 0 ? `${Math.abs(diff).toLocaleString()} ahead of an even pace` : `${Math.abs(diff).toLocaleString()} behind an even pace`;
}
