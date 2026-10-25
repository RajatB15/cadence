import { ACTIVITY_FAMILIES } from "./metrics";
import type { HabitOption, PhaseBody, PhaseSummary, PillarResult, PillarSpec, PillarStatus } from "./types";

export const PHASE_COLORS = ["#6cc7ff", "#ff6a55", "#c8f560", "#ffbe55", "#9b8cff", "#5be3b0", "#d9b26a"];
export const PHASE_EMOJI = ["❄️", "🔥", "🏔️", "🌱", "☀️", "⚡", "🌙", "🎯"];

export const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const n = (v: number) => (Number.isInteger(v) ? v.toLocaleString() : String(Math.round(v * 10) / 10));

export const MEASURES: Record<PillarSpec["kind"], Record<string, { label: string; unit: string }>> = {
  daily: {
    moved: { label: "Minutes moved", unit: "min" },
    steps: { label: "Steps", unit: "steps" },
    sleep_h: { label: "Hours slept", unit: "h" },
    distance_km: { label: "Distance", unit: "km" },
  },
  total: {
    distance_km: { label: "Distance", unit: "km" },
    duration_h: { label: "Training time", unit: "h" },
    sessions: { label: "Sessions", unit: "sessions" },
    ascent_m: { label: "Climbing", unit: "m" },
    load: { label: "Training load", unit: "load" },
  },
  weekly: {
    sessions: { label: "Sessions", unit: "sessions" },
    distance_km: { label: "Distance", unit: "km" },
    duration_h: { label: "Training time", unit: "h" },
    load: { label: "Training load", unit: "load" },
  },
  habit: {},
  goal: {
    weight_kg: { label: "Weight", unit: "kg" },
    run_pace: { label: "Average run pace", unit: "/km" },
    run_best_pace: { label: "Fastest run pace (3 km+)", unit: "/km" },
    ride_speed: { label: "Average ride speed", unit: "km/h" },
    swim_pace: { label: "Average swim pace", unit: "/100 m" },
    longest_km: { label: "Longest single session", unit: "km" },
    resting_hr: { label: "Resting heart rate (7-day average)", unit: "bpm" },
    hrv: { label: "HRV (7-day average)", unit: "ms" },
    sleep_h: { label: "Sleep (7-day average)", unit: "h" },
    vo2max: { label: "VO₂max", unit: "" },
  },
};

/** Goals whose target is a time per distance, typed as m:ss and stored as seconds. */
export const PACE_METRICS = new Set(["run_pace", "run_best_pace", "swim_pace"]);

export function clock(seconds: number): string {
  const t = Math.round(seconds);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

/** A goal figure with its unit: 5:30 /km, 72.4 kg … */
export function goalValue(metric: string, v: number | null | undefined): string {
  if (v == null) return "—";
  const unit = MEASURES.goal[metric]?.unit ?? "";
  if (PACE_METRICS.has(metric)) return `${clock(v)} ${unit}`;
  const digits = metric === "weight_kg" || metric === "sleep_h" || metric === "ride_speed" || metric === "longest_km" ? 1 : 0;
  return `${v.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

export const KIND_LABEL: Record<PillarSpec["kind"], string> = {
  daily: "Every day",
  total: "Phase total",
  weekly: "Every week",
  habit: "Journal habit",
  goal: "Outcome goal",
};

export const KIND_HELP: Record<PillarSpec["kind"], string> = {
  daily: "A day counts when it meets the bar. Gives streaks; rest passes are the misses you allow.",
  total: "One running total for the whole phase, against a straight-line pace.",
  weekly: "Each Monday–Sunday week has its own bar. Partial weeks at the edges are never counted as misses.",
  goal: "A result to reach by the end: weight, pace, speed, longest session or a body marker. Measured from where you start.",
  habit: "Counts the days you answered your journal check-in the way you want. Unanswered days are unknown, not misses.",
};

const familyName = (family?: string | null) => (family ? ACTIVITY_FAMILIES[family]?.label ?? family : null);

/** The line a pillar goes by, unless you gave it your own label. */
export function describePillar(p: PillarSpec, habits: HabitOption[] = []): string {
  if (p.label) return p.label;
  const t = p.target ?? 0;
  const fam = familyName(p.family);
  if (p.kind === "goal") return `${MEASURES.goal[p.metric ?? ""]?.label ?? "Goal"}: ${goalValue(p.metric ?? "", t)}${p.metric === "longest_km" && fam ? ` · ${fam}` : ""}`;
  if (p.kind === "habit") {
    const label = habits.find((h) => h.key === p.behaviour)?.label ?? p.behaviour ?? "habit";
    return p.want === "yes" ? label : `No ${label.toLowerCase()}`;
  }
  if (p.kind === "daily") {
    if (p.metric === "moved") return `${fam ? `${fam}: ` : "Move "}${n(t)}+ min a day`;
    if (p.metric === "steps") return `${n(t)}+ steps a day`;
    if (p.metric === "sleep_h") return `Sleep ${n(t)}+ h a night`;
    return `${fam ? `${fam}: ` : ""}${n(t)}+ km a day`;
  }
  const unit = { distance_km: "km", duration_h: "h of training", sessions: "sessions", ascent_m: "m climbed", load: "training load" }[p.metric ?? ""] ?? "";
  const body = `${n(t)} ${unit}${fam ? ` · ${fam}` : ""}`;
  return p.kind === "weekly" ? `${body} a week` : body;
}

export const STATUS: Record<PillarStatus, { label: string; color: string }> = {
  early: { label: "Just started", color: "#8d8a82" },
  upcoming: { label: "Not started", color: "#8d8a82" },
  on: { label: "On track", color: "#5be3b0" },
  ahead: { label: "Ahead", color: "#c8f560" },
  complete: { label: "Done", color: "#c8f560" },
  slipping: { label: "Slipping", color: "#ffbe55" },
  behind: { label: "Behind", color: "#ff6a55" },
};

const unitOf = (p: PillarResult) => (p.kind === "total" || p.kind === "weekly" ? MEASURES[p.kind][p.metric ?? ""]?.unit ?? "" : "");

/** The one-line state of a pillar, for cards and the Home banner. */
export function pillarHeadline(p: PillarResult): string {
  if (p.kind === "daily" || p.kind === "habit") {
    if (p.judged === 0 && !p.streak) return "Nothing to judge yet";
    if (p.streak) return `${p.streak}-day streak`;
    return p.best_streak ? `Streak restarts today · best ${p.best_streak}` : "No streak yet";
  }
  if (p.kind === "goal") {
    if (p.no_data) return "No data yet";
    const pct = p.progress != null && p.status !== "complete" ? ` · ${Math.round(p.progress * 100)}% there` : "";
    return p.status === "complete" ? `Reached · ${goalValue(p.metric ?? "", p.current)}` : `${goalValue(p.metric ?? "", p.current)} → ${goalValue(p.metric ?? "", p.target)}${pct}`;
  }
  if (p.kind === "total") return `${n(p.value ?? 0)} of ${n(p.target ?? 0)} ${unitOf(p)}`;
  return p.judged ? `${p.hits} of ${p.judged} weeks hit` : "First full week still running";
}

/** What the daily pillar's rest passes and misses mean, in words. */
export function passesLine(p: PillarResult): string {
  const misses = p.misses ?? 0;
  const passes = p.passes ?? 0;
  if (!passes && !misses) return "No rest passes: every day counts";
  if (!passes) return "No rest passes allowed";
  if (!p.intact) return `${misses} missed, only ${passes} rest pass${passes === 1 ? "" : "es"} allowed`;
  return `${p.passes_left} of ${passes} rest pass${passes === 1 ? "" : "es"} left`;
}

export function totalPaceLine(p: PillarResult): string {
  if (p.status === "complete") return "Target reached";
  const gap = (p.value ?? 0) - (p.expected ?? 0);
  const unit = unitOf(p);
  const base = `${n(Math.abs(Math.round(gap * 10) / 10))} ${unit} ${gap >= 0 ? "ahead of" : "behind"} an even pace`;
  if (p.projection != null) return `${base} · heading for about ${n(Math.round(p.projection))}`;
  return base;
}

/** Phase length and how far through it we are. */
export function dayLine(p: PhaseSummary): string {
  if (p.state === "upcoming") return `Starts in ${p.starts_in} day${p.starts_in === 1 ? "" : "s"}`;
  if (p.state === "done") return `Finished · ${p.total_days} days`;
  return p.days_left === 0 ? `Final day · ${p.total_days} days` : `Day ${p.day_number} of ${p.total_days} · ${p.days_left} left`;
}

/** The sentence under the Home banner. */
export function bannerLine(p: PhaseSummary, habits: HabitOption[] = []): string {
  if (p.state === "upcoming") return p.tagline || "Get ready";
  const lead = p.pillars.find((x) => x.status !== "early" && x.status !== "upcoming") ?? p.pillars[0];
  if (!lead) return p.tagline || `${p.totals.sessions} session${p.totals.sessions === 1 ? "" : "s"} so far`;
  return `${describePillar(lead, habits)} · ${pillarHeadline(lead)}`;
}

export function onTrackLine(p: PhaseSummary): string {
  return p.judged ? `${p.on_track} of ${p.judged} on track` : p.pillars.length ? "Too early to judge" : "No pillars set";
}

// ---- templates -----------------------------------------------------------------------------

export interface PhaseTemplate {
  key: string;
  label: string;
  body: PhaseBody;
  needsHabit?: string;
}

const addDays = (d: Date, days: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);

/** The next calendar window (month/day to month/day, inclusive) that hasn't ended by `today`. */
export function nextWindow(today: Date, from: [number, number], to: [number, number]): [string, string] {
  for (let y = today.getFullYear(); ; y++) {
    const start = new Date(y, from[0] - 1, from[1]);
    const end = new Date(from[0] > to[0] ? y + 1 : y, to[0] - 1, to[1]);
    if (end >= new Date(today.getFullYear(), today.getMonth(), today.getDate())) return [isoDay(start), isoDay(end)];
  }
}

const daily = (metric: string, target: number, passes = 0, family: string | null = null): PillarSpec => ({ kind: "daily", metric, target, passes, family });

export function templates(today: Date): PhaseTemplate[] {
  const mk = (key: string, label: string, emoji: string, color: string, tagline: string, [start, end]: [string, string], pillars: PillarSpec[], needsHabit?: string): PhaseTemplate => ({
    key, label, needsHabit, body: { name: label, tagline, emoji, color, start, end, pillars },
  });
  const monday = addDays(today, (8 - today.getDay()) % 7 || 7);
  return [
    mk("winter", "Winter Arc", "❄️", "#6cc7ff", "Build quietly through the dark months.", nextWindow(today, [10, 1], [12, 31]), [daily("moved", 20, 12), { kind: "weekly", metric: "sessions", target: 4 }, daily("sleep_h", 7, 15)]),
    mk("nobreak", "No Break November", "🔥", "#ff6a55", "Move every single day.", nextWindow(today, [11, 1], [11, 30]), [daily("moved", 20, 0)]),
    mk("dry", "Dry January", "🌱", "#5be3b0", "A month without alcohol.", nextWindow(today, [1, 1], [1, 31]), [{ kind: "habit", behaviour: "alcohol", want: "no", passes: 0 }], "alcohol"),
    mk("steps", "30 days of steps", "👟", "#ffbe55", "Ten thousand, every day.", [isoDay(today), isoDay(addDays(today, 29))], [daily("steps", 10000, 3)]),
    mk("block", "Eight-week block", "🎯", "#c8f560", "Show up four times a week.", [isoDay(monday), isoDay(addDays(monday, 55))], [{ kind: "weekly", metric: "sessions", target: 4 }, { kind: "total", metric: "duration_h", target: 40 }]),
  ];
}

// ---- form <-> request ----------------------------------------------------------------------

/** Editable pillar: numbers are strings while typing. */
export interface PillarDraft {
  kind: PillarSpec["kind"];
  metric: string;
  family: string;
  target: string;
  passes: string;
  behaviour: string;
  want: "no" | "yes";
  label: string;
}

export function draftOf(p?: PillarSpec): PillarDraft {
  return {
    kind: p?.kind ?? "daily", metric: p?.metric ?? "moved", family: p?.family ?? "", target: p?.target == null ? "20" : PACE_METRICS.has(p.metric ?? "") ? clock(p.target) : String(p.target),
    passes: String(p?.passes ?? 0), behaviour: p?.behaviour ?? "", want: p?.want ?? "no", label: p?.label ?? "",
  };
}

export function defaultMetric(kind: PillarSpec["kind"]): string {
  return Object.keys(MEASURES[kind])[0] ?? "habit";
}

/** Turns a draft into the request pillar, or the first thing wrong with it. */
export function pillarOf(d: PillarDraft): { pillar: PillarSpec } | { error: string } {
  const label = d.label.trim();
  if (d.kind === "habit") {
    if (!d.behaviour) return { error: "Choose a journal habit" };
    return { pillar: { kind: "habit", behaviour: d.behaviour, want: d.want, passes: Math.max(0, Math.round(Number(d.passes) || 0)), label } };
  }
  const parsed = d.kind === "goal" && PACE_METRICS.has(d.metric) ? parseClock(d.target) : Number(d.target.replace(",", "."));
  if (Number.isNaN(parsed)) return { error: "Write a pace as minutes:seconds, like 5:30" };
  const target = parsed;
  if (!d.target.trim() || !Number.isFinite(target) || target <= 0) return { error: "Every pillar needs a target above zero" };
  const pillar: PillarSpec = { kind: d.kind, metric: d.metric, target, family: d.family || null, label };
  if (d.kind === "goal" && d.metric !== "longest_km") pillar.family = null;
  if (d.kind === "daily") pillar.passes = Math.max(0, Math.round(Number(d.passes) || 0));
  return { pillar };
}

function parseClock(text: string): number {
  const m = /^\s*(\d+):([0-5]\d)\s*$/.exec(text);
  return m ? Number(m[1]) * 60 + Number(m[2]) : NaN;
}

export function validateBody(b: PhaseBody): string | null {
  if (!b.name.trim()) return "Give the phase a name";
  if (!b.start || !b.end) return "Pick a start and an end date";
  if (b.end < b.start) return "The phase can’t end before it starts";
  return null;
}
