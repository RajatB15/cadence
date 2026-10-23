import type { CredentialStatus, ProjectionStatus } from "./types";

const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const shortDateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
const weekdayFmt = new Intl.DateTimeFormat(undefined, { weekday: "short", day: "numeric", month: "short" });

/** Parse YYYY-MM-DD as a local calendar date (not UTC midnight). */
export function parseDay(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export const formatDate = (day: string) => dateFmt.format(parseDay(day));
export const formatShortDate = (day: string) => shortDateFmt.format(parseDay(day));
export const formatWeekday = (day: string) => weekdayFmt.format(parseDay(day));

export function formatDuration(seconds: number): string {
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

export function formatKm(meters: number | null, digits = 1): string {
  return meters == null ? "—" : (meters / 1000).toFixed(digits);
}

export function formatPace(seconds: number, meters: number | null): string | null {
  if (!meters) return null;
  const perKm = seconds / (meters / 1000);
  const m = Math.floor(perKm / 60);
  const s = Math.round(perKm % 60);
  return s === 60 ? `${m + 1}:00` : `${m}:${String(s).padStart(2, "0")}`;
}

export function formatMetric(value: number, metric: string): string {
  switch (metric) {
    case "steps":
      return Math.round(value).toLocaleString();
    case "sleep_hours": {
      const h = Math.floor(value);
      const m = Math.round((value - h) * 60);
      return m === 60 ? `${h + 1}:00` : `${h}:${String(m).padStart(2, "0")}`;
    }
    default:
      return Math.round(value).toString();
  }
}

export type Tone = "good" | "bad" | "neutral";

export function deltaTone(delta: number | null, higherIsBetter: boolean | null): Tone {
  if (delta == null || higherIsBetter == null || Math.abs(delta) < 2) return "neutral";
  return delta > 0 === higherIsBetter ? "good" : "bad";
}

export function formatDelta(delta: number | null): string {
  if (delta == null) return "No baseline";
  if (Math.abs(delta) < 0.5) return "At baseline";
  return `${delta > 0 ? "+" : "−"}${Math.abs(delta).toFixed(Math.abs(delta) < 10 ? 1 : 0)}%`;
}

export function greeting(hour: number): string {
  if (hour < 5) return "Late night";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export interface ReminderCopy {
  tone: "info" | "warn" | "danger";
  title: string;
  body: string;
}

/** Banner copy for the Garmin credential, or null when no banner should show. */
export function reminderCopy(status: CredentialStatus): ReminderCopy | null {
  const days = status.days_remaining ?? 0;
  const on = status.expires_on ? formatDate(status.expires_on) : "";
  const plural = days === 1 ? "day" : "days";
  switch (status.level) {
    case "expired":
      return {
        tone: "danger",
        title: "Garmin key expired",
        body: `It expired on ${on}. Generate a new key to resume Garmin features.`,
      };
    case "critical":
      return status.dismissed
        ? null
        : { tone: "danger", title: `Garmin key expires tomorrow`, body: `Renew it before ${on}.` };
    case "warning":
      return status.dismissed
        ? null
        : { tone: "warn", title: `Garmin key expires in ${days} ${plural}`, body: `Renew it before ${on}.` };
    case "notice":
      return status.dismissed
        ? null
        : { tone: "info", title: `Garmin key expires in ${days} ${plural}`, body: `Plan a renewal before ${on}.` };
    case "invalid_expiry":
      return {
        tone: "warn",
        title: "Garmin key expiry unreadable",
        body: "Set GARMIN_API_KEY_EXPIRES_ON as YYYY-MM-DD so renewal reminders work.",
      };
    default:
      return null;
  }
}

export function projectionCopy(status: ProjectionStatus): string {
  return {
    reached: "You're within 0.1 kg of your goal.",
    on_track: "At your 4-week pace",
    off_track: "Your 4-week trend is moving away from this goal.",
    flat: "Your 4-week trend isn't clear enough yet to project a date.",
    insufficient_data: "Need at least 8 weigh-ins in the last 4 weeks to project.",
    too_far: "At your current pace this is more than two years away.",
  }[status];
}
