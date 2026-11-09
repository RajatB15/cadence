// Pure helpers for the Home page: ring geometry, calorie-card state, vitals ordering and phase-to-cards mapping.
// The backend decides the day phase and its copy; nothing here recomputes it, it only maps what was sent to layout.
import type { HomeEnergy, HomePhase, MetricSummary } from "./types";

// ---- formatting ---------------------------------------------------------------------------

export const formatKcal = (v: number) => Math.round(v).toLocaleString();

/** "14:05" from minutes after local midnight; null when absent. */
export function formatClock(min: number | null | undefined): string | null {
  if (min == null || !Number.isFinite(min) || min < 0 || min >= 1440) return null;
  return `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(Math.round(min % 60)).padStart(2, "0")}`;
}

// ---- ring math ----------------------------------------------------------------------------

/** Clamp value/max into 0..1; missing or non-positive max is 0. */
export function fraction(value: number | null | undefined, max: number | null | undefined): number {
  if (value == null || max == null || !(max > 0) || !(value > 0)) return 0;
  return Math.min(1, value / max);
}

export const circumference = (r: number) => 2 * Math.PI * r;

/** Stroke-dash for an arc that starts at `from` and ends at `to` (both 0..1 of the circle). */
export function arcDash(r: number, from: number, to: number): { dasharray: string; dashoffset: number } {
  const c = circumference(r);
  const a = Math.max(0, Math.min(1, from));
  const b = Math.max(a, Math.min(1, to));
  return { dasharray: `${((b - a) * c).toFixed(2)} ${c.toFixed(2)}`, dashoffset: -a * c };
}

// ---- calorie card state -------------------------------------------------------------------

export type EnergyState =
  | { kind: "missing" } // backend did not send the block (older server)
  | { kind: "unsupported"; demo: boolean } // Garmin reported no calories
  | { kind: "just_started" } // after midnight, before there is a burn to show
  | { kind: "ok"; hasLog: boolean; showLeft: boolean; showProjection: boolean };

/**
 * `calories` is `phase.hints.calories` ("left" | "day_total"): the backend says whether a "left" figure suits this part of the day.
 * An empty log never produces a "left" figure, and a projection is shown only when the backend says it is usable.
 */
export function energyState(energy: HomeEnergy | null | undefined, calories: string | undefined, isDemo = false): EnergyState {
  if (!energy) return { kind: "missing" };
  if (energy.status === "no_garmin_kcal") return { kind: "unsupported", demo: isDemo };
  if (energy.status === "just_started") return { kind: "just_started" };
  const total = energy.burned?.total;
  // Garmin's 0 right after midnight means "not counted yet", not a zero-calorie day.
  if (total == null || total <= 0) return energy.as_of_min != null && energy.as_of_min < 60 ? { kind: "just_started" } : { kind: "unsupported", demo: isDemo };
  const hasLog = Boolean(energy.eaten?.logged) && energy.eaten?.kcal != null;
  const showLeft = hasLog && calories !== "day_total" && (energy.left != null || energy.above_by != null);
  const showProjection = energy.projected != null && (energy.projection_state === "ok" || energy.projection_state === "partial");
  return { kind: "ok", hasLog, showLeft, showProjection };
}

/** Short, non-wording label for the projection cell (the sentence itself is `copy.projection`). */
export function projectionRange(p: NonNullable<HomeEnergy["projected"]>): string {
  return `${formatKcal(p.lo)}–${formatKcal(p.hi)}${p.method === "fallback" ? " · rough" : ""}`;
}

/** Why there is no projection, as the cell's sub-label; the backend's own sentence (`copy.status` or `copy.projection`) wins when it sent one. */
export function projectionMissing(e: HomeEnergy): string | null {
  if (e.projection_state === "hidden") return null; // after 23:00 the day is nearly over: no cell at all
  return e.copy?.status ?? (e.projection_state === "insufficient" ? "Not enough history yet" : "Not available yet");
}

/** The ring's intake scale: the base target plus what the user chose to eat back (the same basis as `left`). */
export function allowance(e: HomeEnergy): number | null {
  const t = e.target?.kcal;
  return t == null ? null : t + (e.eat_back_kcal ?? 0);
}

export const MANUAL_RANGE: [number, number] = [800, 6000];
export const EAT_BACK_RANGE: [number, number] = [0, 100];

type Parsed = { ok: true; value: number } | { ok: false; reason: string };

function parseWhole(raw: string, [lo, hi]: [number, number], unit: string): Parsed {
  const text = raw.replace(/[,\s]/g, "");
  const n = Number(text);
  const range = `between ${lo.toLocaleString()} and ${hi.toLocaleString()}${unit}`;
  if (!text || !Number.isFinite(n)) return { ok: false, reason: `Enter a whole number ${range}.` };
  if (!Number.isInteger(n) || n < lo || n > hi) return { ok: false, reason: `Enter a whole number ${range}.` };
  return { ok: true, value: n };
}

/** Validate a typed manual target against the server's range (GET /api/settings/calories `ranges`). */
export const parseManualKcal = (raw: string, range: [number, number] = MANUAL_RANGE) => parseWhole(raw, range, " kcal");
/** Validate a typed eat-back percentage. */
export const parseEatBack = (raw: string, range: [number, number] = EAT_BACK_RANGE) => parseWhole(raw, range, " percent");

// ---- vitals rail --------------------------------------------------------------------------

export const RAIL_METRICS = ["steps", "sleep_hours", "hrv", "resting_hr", "body_battery", "stress"] as const;
const MORNING_ORDER = ["sleep_hours", "hrv", "resting_hr", "body_battery", "steps", "stress"];
const EVENING_ORDER = ["steps", "stress", "body_battery", "sleep_hours", "hrv", "resting_hr"];
const DEFAULT_ORDER = [...RAIL_METRICS] as string[];

export function railOrderFor(phase: string | undefined): string[] {
  switch (phase) {
    case "dawn":
    case "morning":
      return MORNING_ORDER;
    case "evening":
    case "late":
    case "post_workout":
      return EVENING_ORDER;
    default:
      return DEFAULT_ORDER;
  }
}

/** `vitalsOrder` is `phase.vitals_order` from the backend; the phase table is only the fallback for an older server. */
export function orderVitals<T extends { metric: string }>(metrics: T[], phase: string | undefined, vitalsOrder?: readonly string[] | null): T[] {
  const order = vitalsOrder?.length ? [...vitalsOrder] : railOrderFor(phase);
  const want = metrics.filter((m) => order.includes(m.metric));
  return want.sort((a, b) => order.indexOf(a.metric) - order.indexOf(b.metric));
}

export interface VitalView {
  stale: boolean;
  /** "vs usual" chip text, null under the baseline minimum (the backend leaves delta null then). */
  chip: string | null;
  spark: number[];
  baseline: number | null;
}

export function vitalView(m: MetricSummary, today: string): VitalView {
  const stale = m.latest_day < today;
  const d = m.delta_pct;
  const chip = d == null ? null : Math.abs(d) < 0.5 ? "at usual" : `${d > 0 ? "+" : "−"}${Math.abs(d).toFixed(Math.abs(d) < 10 ? 1 : 0)}% vs usual`;
  return { stale, chip, spark: m.spark.slice(-7).map((p) => p.value), baseline: m.baseline_mean };
}

// ---- phase to cards -----------------------------------------------------------------------

/** Every Home block has an id. Backend card ids map in via BACKEND_ID (its "readiness" is the score dials). */
export const PRIMARY_IDS = ["vitals", "calories", "now", "planned", "status", "scores", "checkin", "tonight", "week", "recent", "weather", "strain"] as const;
export const MORE_IDS = ["read", "improve", "whatif", "gain", "streaks", "wins"] as const;
export type SectionId = (typeof PRIMARY_IDS)[number] | (typeof MORE_IDS)[number];
const ALL: SectionId[] = [...PRIMARY_IDS, ...MORE_IDS];

const BACKEND_ID: Record<string, SectionId> = { vitals: "vitals", calories: "calories", now: "now", readiness: "scores", checkin: "checkin", week: "week", recent: "recent" };
const FALLBACK: SectionId[] = ["vitals", "calories", "now", "planned", "status", "scores", "checkin", "week", "recent"];

/** Session states in which the plan card says nothing new (the Now card carries the backend's wording for them). */
const QUIET_SESSION = new Set(["deferred", "window_closed", "rest"]);
const QUIET_PHASE = new Set(["time_off", "sick"]);

/** True when the backend asked for this card to be shown muted (a morning metric late in the day, say). */
export const isDimmed = (phase: HomePhase | null | undefined, id: SectionId): boolean =>
  (phase?.dimmed ?? []).some((c) => BACKEND_ID[c] === id);

/**
 * Order the blocks. `available` says which ids have content today. The backend's `cards` list is the order and `hidden` is
 * left out of the main flow; with no phase block (older server) a fixed order is used. Anything available but not placed lands
 * under "More", so nothing becomes unreachable.
 */
export function sectionLayout(phase: HomePhase | null | undefined, available: ReadonlySet<SectionId>): { primary: SectionId[]; more: SectionId[] } {
  let base: SectionId[];
  if (phase?.cards?.length) {
    base = [];
    for (const c of phase.cards) {
      const id = BACKEND_ID[c];
      if (!id) continue; // "more" and unknown ids
      base.push(id);
      if (id === "now" && !QUIET_SESSION.has(phase.session_state ?? "") && !QUIET_PHASE.has(phase.phase ?? "")) base.push("planned");
    }
  } else base = FALLBACK;
  const primary = base.filter((id, i) => base.indexOf(id) === i && available.has(id));
  const more = ALL.filter((id) => available.has(id) && !primary.includes(id));
  return { primary, more };
}

export interface NowView {
  eyebrow: string | null;
  headline: string | null;
  session: { title: string; detail: string } | null;
  /** Small supporting lines the backend chose to say (recap, sleep, steps, flags), in order. */
  notes: string[];
}

/** Reads the backend's copy block as sent. Null when there is no phase copy (the older Today card is shown instead). */
export function nowView(phase: HomePhase | null | undefined): NowView | null {
  const c = phase?.copy;
  if (!c) return null;
  const headline = c.headline ?? null;
  const session = c.session && (c.session.title || c.session.detail) ? c.session : null;
  if (!headline && !session) return null;
  const notes = [c.recap, c.sleep, c.steps, c.protein_check, ...(c.flags ?? [])].filter((x): x is string => Boolean(x));
  return { eyebrow: phase?.phase ? PHASE_LABEL[phase.phase] ?? null : null, headline, session, notes };
}

export const PHASE_LABEL: Record<string, string> = {
  dawn: "Early start", morning: "Morning", midday: "Midday", afternoon: "Afternoon", evening: "Evening", late: "Winding down",
  post_workout: "After your session", rest_day: "Rest day", race_week: "Race week", race_day: "Race day", time_off: "Time off", sick: "Rest up",
};

/** Ambient accent for the header by phase (token names, never raw colours). */
export function phaseAccent(phase: string | undefined, hour: number): "gold" | "sky" | "violet" | "mint" | "coral" {
  switch (phase) {
    case "sick": return "coral";
    case "time_off": case "rest_day": return "mint";
    case "late": case "evening": return "violet";
    case "post_workout": return "mint";
    case "morning": case "dawn": return "gold";
    case "midday": case "afternoon": return "sky";
  }
  return hour < 11 ? "gold" : hour < 17 ? "sky" : "violet";
}

/** The hour on the user's clock: the server's local time (their timezone setting) when it sent one, else the device's. */
export function localHour(nowLocal: string | null | undefined, fallback: number): number {
  const m = /^(\d{1,2}):(\d{2})/.exec(nowLocal ?? "");
  const h = m ? Number(m[1]) : NaN;
  return Number.isInteger(h) && h >= 0 && h <= 23 ? h : fallback;
}
