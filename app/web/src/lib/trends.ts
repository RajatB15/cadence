import type { TimeOffItem, TimeOffKind, TrainingStatusKey } from "./types";

export const STATUS_STYLE: Record<TrainingStatusKey, { color: string; short: string }> = {
  progressing: { color: "#c8f560", short: "Up" },
  not_adapting: { color: "#ff9f5a", short: "Stuck" },
  maintaining: { color: "#6cc7ff", short: "Hold" },
  overloading: { color: "#ff6a55", short: "Over" },
  deloading: { color: "#ffbe55", short: "Easy" },
  returning: { color: "#b794f6", short: "Back" },
  off: { color: "#8d8a82", short: "Off" },
  detraining: { color: "#ff9f5a", short: "Slip" },
  unknown: { color: "#5c5a55", short: "–" },
};

export const KIND_LABEL: Record<TimeOffKind, string> = { travel: "Travel", vacation: "Holiday", sick: "Ill", injury: "Injured" };

/** "+3.2 vs previous 4 weeks", or null when the previous stretch had too little data to compare. */
export function deltaText(delta: number | null, windowDays: number): string | null {
  if (delta == null) return null;
  const span = windowDays === 7 ? "week" : windowDays === 28 ? "4 weeks" : `${Math.round(windowDays / 7)} weeks`;
  if (Math.abs(delta) < 0.5) return `level with the previous ${span}`;
  return `${delta > 0 ? "+" : "−"}${Math.abs(delta).toFixed(1)} vs the previous ${span}`;
}

/** One line describing what an entry will do to the plan, from the numbers it uses. */
export function usesText(item: TimeOffItem): string {
  const u = item.uses;
  const ease = u.return_weeks > 0 ? `then ${u.return_weeks} week${u.return_weeks === 1 ? "" : "s"} easing back from ${u.return_start_pct}%` : "no easing-back period";
  if (item.kind === "sick" || item.kind === "injury") return `No training planned, ${ease}`;
  const act = { none: "No training planned", light: "Light movement only", full: "Training as normal" }[u.activity];
  return u.activity === "full" ? act : `${act}, ${ease}`;
}

/** Days from `start` to `end` (or today when open), inclusive. */
export function spanDays(start: string, end: string | null, today: string): number {
  const ms = (d: string) => new Date(`${d}T00:00:00Z`).getTime();
  return Math.round(((end ? ms(end) : Math.max(ms(today), ms(start))) - ms(start)) / 86_400_000) + 1;
}
