import type {
  ImproveCitation,
  ImproveDriver,
  ImproveNumber,
  ImproveReport,
  ImproveReview,
  ImproveStart,
  ImproveSummary,
  ImproveWatch,
} from "./types";

export const IMPROVE_METRICS = ["hrv", "resting_hr", "vo2max"] as const;
export const supportsImprove = (metric: string): boolean => (IMPROVE_METRICS as readonly string[]).includes(metric);

export const ASSOCIATION_NOTE =
  "Everything here is an association in your own history, not proof, and never medical advice. Days without a value are skipped, not counted as zero.";

export type SectionKey = "moving" | "start" | "watch" | "focus" | "review" | "compare";

export const SECTION_LABEL: Record<SectionKey, string> = {
  moving: "What's moving it",
  start: "What to start",
  watch: "What to watch",
  focus: "Next 4 weeks",
  review: "Did it work?",
  compare: "How you compare",
};

const num = (v: number | null | undefined, digits = 1): string =>
  v == null || !Number.isFinite(v) ? "—" : Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(digits).replace(/\.0$/, "");

/** Signed number with a real minus sign. */
export function signed(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const s = num(Math.abs(v), digits);
  return v < 0 ? `−${s}` : v > 0 ? `+${s}` : s;
}

export function ciText(ci: [number, number] | null | undefined, unit = ""): string | null {
  if (!ci || ci.length !== 2 || ci.some((x) => x == null || !Number.isFinite(x))) return null;
  const u = unit ? ` ${unit}` : "";
  return `95% range ${signed(ci[0])} to ${signed(ci[1])}${u}`;
}

/** Does the interval exclude zero? null when unknown. */
export function ciExcludesZero(ci: [number, number] | null | undefined): boolean | null {
  if (!ci || ci.length !== 2) return null;
  return ci[0] > 0 || ci[1] < 0;
}

/** "On 9 nights with 2+ drinks (vs 41 no drinks) your HRV was 7.4 ms lower (95% range ...)". Non-causal wording. */
export function driverSentence(d: ImproveDriver, outcome: string): string {
  if (d.statement) return d.statement; // the backend wording already carries sample sizes, range and the not-proof caveat
  const unit = d.unit ?? "";
  const parts: string[] = [];
  const exposed = d.n_exposed != null ? `${d.n_exposed} ` : "";
  const ref = d.n_reference != null ? ` (vs ${d.n_reference}${d.reference ? ` ${d.reference}` : ""})` : d.reference ? ` (vs ${d.reference})` : "";
  parts.push(`On ${exposed}${d.exposure ?? "days"}${ref}`);
  if (d.diff == null) return `${parts[0]}, the difference could not be estimated.`;
  const dir = d.diff === 0 ? "the same" : d.diff > 0 ? "higher" : "lower";
  const size = d.diff === 0 ? "" : `${num(Math.abs(d.diff))}${unit ? ` ${unit}` : ""} `;
  const pct = d.pct != null ? ` (${signed(d.pct, 0)}%)` : "";
  const ci = ciText(d.ci, unit);
  return `${parts[0]} your ${outcome} was ${size}${dir}${pct}${ci ? ` (${ci})` : ""}.`;
}

export function sampleText(d: { n_exposed?: number; n_reference?: number; n_effective?: number }): string | null {
  const bits: string[] = [];
  if (d.n_exposed != null) bits.push(`${d.n_exposed} exposed`);
  if (d.n_reference != null) bits.push(`${d.n_reference} reference`);
  if (d.n_effective != null) bits.push(`~${num(d.n_effective, 0)} effective`);
  return bits.length ? `n = ${bits.join(" · ")}` : null;
}

/** One display string for a "numbers" value: arrays are ranges, booleans yes/no, nulls are skipped by the caller. */
export function numberText(v: ImproveNumber): string {
  if (Array.isArray(v)) return v.map((x) => (typeof x === "number" ? signed(x).replace("+", "") : String(x))).join(" to ");
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

/** Plain-language names for watch flags: the backend title is always the generic "Worth a look". */
const WATCH_LABEL: Record<string, string> = {
  overreach_pattern: "Load is high and overnight numbers are below your usual",
  illness_signature: "Overnight numbers look unusual for a couple of nights",
  sleep_debt: "Several short nights in a row",
  detraining: "A long gap without aerobic activity",
};
export function watchLabel(w: { id?: string; title?: string }): string {
  return (w.id && WATCH_LABEL[w.id]) || w.title || "Worth a look";
}

/** blocked_by carries a rule id, never display text. */
export function blockedText(id: string | null | undefined): string | null {
  return id ? (WATCH_LABEL[id] ?? id.replace(/_/g, " ")) : null;
}

export function confidenceLabel(c: number | undefined): string {
  return c == null ? "confidence unknown" : c >= 3 ? "higher confidence" : c === 2 ? "medium confidence" : "early, low confidence";
}

/** Clear drivers first, then hints; within a grade by q ascending (missing q last). Max `limit`. */
export function orderDrivers(drivers: ImproveDriver[] | undefined, limit = 5): ImproveDriver[] {
  const rank = (d: ImproveDriver) => (d.grade === "clear" ? 0 : d.grade === "hint" ? 1 : 2);
  return [...(drivers ?? [])]
    .filter((d) => d.grade === "clear" || d.grade === "hint")
    .sort((a, b) => rank(a) - rank(b) || (a.q ?? 1) - (b.q ?? 1) || Math.abs(b.pct ?? 0) - Math.abs(a.pct ?? 0))
    .slice(0, limit);
}

/** Highest score first, ties by id so the order is deterministic. */
export function orderStarts(items: ImproveStart[] | undefined): ImproveStart[] {
  return [...(items ?? [])].sort((a, b) => (b.score ?? 0) - (a.score ?? 0) || a.id.localeCompare(b.id));
}

/** Act before look, ties by id. */
export function orderWatch(items: ImproveWatch[] | undefined): ImproveWatch[] {
  const rank = (w: ImproveWatch) => (w.severity === "act" ? 0 : 1);
  return [...(items ?? [])].sort((a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id));
}

export function normalizeCitations(c: ImproveReport["citations"]): Record<string, ImproveCitation> {
  if (!c) return {};
  if (Array.isArray(c)) return Object.fromEntries(c.filter((x) => x && x.id).map((x) => [x.id, x]));
  return Object.fromEntries(Object.entries(c).map(([k, v]) => [k, { ...v, id: v?.id || k }]));
}

/** Chip text: short label if the payload gave one, otherwise the id (never invented). */
export function citationLabel(id: string, c: Record<string, ImproveCitation>): string {
  return c[id]?.short ?? c[id]?.title ?? id;
}

export function doiUrl(c: ImproveCitation): string | null {
  if (c.url && /^https?:\/\//.test(c.url)) return c.url;
  if (c.doi) return `https://doi.org/${c.doi.replace(/^https?:\/\/(dx\.)?doi\.org\//, "")}`;
  return null;
}

export type SectionStatus = "ready" | "collecting" | "empty";

export interface SectionInfo {
  key: SectionKey;
  status: SectionStatus;
  count: number;
}

/** Per-section status so the UI can show "not enough data yet" instead of silently hiding a section. */
export function sectionStatuses(r: ImproveReport): SectionInfo[] {
  const collecting = r.state === "collecting";
  const mk = (key: SectionKey, count: number, hasMore = false): SectionInfo => ({
    key,
    count,
    status: count > 0 ? "ready" : collecting || hasMore ? "collecting" : "empty",
  });
  const compare = r.benchmarks ? Object.entries(r.benchmarks).filter(([k, v]) => k !== "profile_missing" && v && typeof v === "object" && (v as { value?: number }).value != null).length : 0;
  return [
    mk("moving", orderDrivers(r.drivers).length, (r.progress?.length ?? 0) > 0),
    mk("start", collecting ? 0 : (r.start?.length ?? 0)),
    mk("watch", collecting ? 0 : (r.watch?.length ?? 0)),
    mk("focus", collecting ? 0 : (r.focus?.priorities?.length ?? 0)),
    mk("review", r.review?.verdict ? 1 : 0, !!reviewNote(r.review)),
    mk("compare", compare, r.benchmarks?.profile_missing === true),
  ];
}

/** "What's needed" line: nights counted against the minimum plus the open progress items. */
export function neededText(r: ImproveReport): string {
  const bits: string[] = [];
  const d = r.data;
  if (d?.needed != null && d.nights != null && d.nights < d.needed) {
    bits.push(`${d.nights} of ${d.needed} days with data (${d.needed - d.nights} more needed)`);
  }
  for (const p of r.progress ?? []) {
    if (p.have < p.needed) bits.push(`${p.label ?? p.key.replace(/_/g, " ")}: ${p.have} of ${p.needed}`);
  }
  return bits.join(" · ");
}

export function progressPct(have: number, needed: number): number {
  if (!(needed > 0)) return 0;
  return Math.max(0, Math.min(100, Math.round((have / needed) * 100)));
}

export function verdictText(r: ImproveReview | null | undefined): string | null {
  if (!r?.verdict) return null;
  if (r.statement) return r.statement;
  const unit = r.unit ? ` ${r.unit}` : "";
  const n = r.window ? ` (n = ${r.window.n_before ?? "?"} before vs ${r.window.n_after ?? "?"} after)` : "";
  if (r.verdict === "no_clear_change") return `No clear change in the 4 weeks after you started${n}.`;
  const dir = r.verdict === "higher" ? "higher" : "lower";
  const size = r.change != null ? ` by ${num(Math.abs(r.change))}${unit}` : "";
  const ci = ciText(r.ci, r.unit);
  return `Your average was ${dir}${size}${ci ? ` (${ci})` : ""}${n}. Other things changed over the same weeks.`;
}

/** The review block can carry a statement without a verdict (too few readings): show it instead of a generic empty state. */
export function reviewNote(r: ImproveReview | null | undefined): string | null {
  return r && !r.verdict && r.statement ? r.statement : null;
}

export type HomeCard =
  | { kind: "watch"; text: string; severity: "look" | "act"; metric?: string }
  | { kind: "focus"; text: string; detail?: string; checkOn?: string; metric?: string };

/** What the compact Home card shows: an active watch flag outranks a focus; null means hide the card. */
export function homeCard(s: ImproveSummary | undefined | null): HomeCard | null {
  if (!s || s.state === "unsupported" || s.state === "error") return null;
  const flag = [...(s.watch ?? [])].sort((a, b) => (a.severity === "act" ? 0 : 1) - (b.severity === "act" ? 0 : 1))[0];
  if (flag?.title || flag?.id) return { kind: "watch", text: watchLabel(flag), severity: flag.severity ?? "look", metric: flag.metric };
  const p = s.focus?.priority;
  if (p?.title) return { kind: "focus", text: p.title, detail: p.behaviour, checkOn: s.focus?.check_on, metric: s.focus?.metric ?? p.target_metrics?.[0] };
  return null;
}

/** Copy shown by the UI itself must not claim causation or diagnose (checked by a test). */
export const FORBIDDEN_WORDS = /\b(causes?|caused|because of|proves?|proven|overtrained|sick|will improve)\b/i;
