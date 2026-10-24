import { formatDate, formatDuration, formatKm } from "./format";
import type { EventTotals } from "./types";

/** One headline figure per field; a field no linked activity reported shows as missing, never 0. */
export function eventStats(t: EventTotals): { label: string; value: string }[] {
  const stats = [
    { label: "km", value: t.distance_m != null ? formatKm(t.distance_m) : null },
    { label: "moving", value: t.moving_s != null ? formatDuration(t.moving_s) : null },
    { label: "elapsed", value: t.elapsed_s != null ? formatDuration(t.elapsed_s) : null },
    { label: "m up", value: t.elevation_gain_m != null ? Math.round(t.elevation_gain_m).toLocaleString() : null },
    { label: "bpm avg", value: t.avg_hr != null ? Math.round(t.avg_hr).toString() : null },
    { label: "load", value: t.training_load != null ? Math.round(t.training_load).toString() : null },
    { label: "kcal", value: t.calories != null ? Math.round(t.calories).toLocaleString() : null },
  ];
  return stats.map((s) => ({ label: s.label, value: s.value ?? "—" }));
}

export function eventDates(start: string | null, end: string | null): string {
  if (!start || !end) return "No activities found in the vault";
  return start === end ? formatDate(start) : `${formatDate(start)} – ${formatDate(end)}`;
}

export function dayLabel(number: number): string {
  return `Day ${number}`;
}
