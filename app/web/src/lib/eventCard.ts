import { formatDate, formatDuration, formatKm } from "./format";
import { ACTIVITY_FAMILIES } from "./metrics";
import { HEAT, RELIEF, buildTrack, gradient, joinTracks } from "./route";
import { formatClock, type CardModel, type CardStat, type Panel } from "./shareCard";
import type { ActivityDetail, EventDetail } from "./types";

const LIME = "#c8f560";
const familyColor = (f: string) => ACTIVITY_FAMILIES[f]?.color ?? LIME;

/**
 * The share card for a whole event: the event's own totals, one route joined from every recording that has GPS, and, where
 * there is no route, the days (or legs) as rows. `details` are the linked activities as loaded; a recording that isn't
 * archived yet just doesn't add to the route, and the totals come from the event, which never leaves an activity out.
 */
export function buildEventCardModel(e: EventDetail, details: ActivityDetail[]): CardModel {
  const t = e.totals;
  const families = Object.entries(e.families);
  const mixed = families.length > 1;
  const lead = families.sort((a, b) => b[1] - a[1])[0]?.[0] ?? "other";
  const color = mixed ? LIME : familyColor(lead);
  const kicker = [mixed ? "Multisport" : (ACTIVITY_FAMILIES[lead]?.label ?? "Event"), e.span_days > 1 ? `${e.span_days} days` : null]
    .filter(Boolean)
    .join(" · ");

  const stats: CardStat[] = [];
  if (t.distance_m) stats.push({ label: "Distance", value: (t.distance_m / 1000).toFixed(2), unit: "km" });
  const moving = t.moving_s ?? t.duration_s ?? 0;
  stats.push({ label: "Time", value: formatClock(moving) });
  if (e.span_days > 1) stats.push({ label: "Days", value: String(e.span_days) });
  else if (t.avg_hr) stats.push({ label: "Avg HR", value: String(Math.round(t.avg_hr)), unit: "bpm" });
  if (t.elevation_gain_m) stats.push({ label: "Elevation", value: String(Math.round(t.elevation_gain_m)), unit: "m" });
  if (e.span_days > 1 && t.avg_hr) stats.push({ label: "Avg HR", value: String(Math.round(t.avg_hr)), unit: "bpm" });
  if (t.calories) stats.push({ label: "Calories", value: String(Math.round(t.calories)), unit: "kcal" });
  if (t.training_load) stats.push({ label: "Load", value: String(Math.round(t.training_load)) });

  const ordered = [...details].sort((a, b) => a.activity.start_time_utc.localeCompare(b.activity.start_time_utc));
  const track = joinTracks(ordered.map((d) => (d.fit && !d.fit.error ? buildTrack(d.fit) : null)));

  return {
    title: e.name,
    kicker,
    date: e.start && e.end ? (e.start === e.end ? formatDate(e.start) : `${formatDate(e.start)} – ${formatDate(e.end)}`) : "",
    color,
    stats,
    distanceM: t.distance_m ?? null,
    durationS: moving,
    track,
    // One speed scale across a ride and a run would just paint the ride hot, so a mixed event is coloured by elevation.
    heat: track ? (mixed ? gradient(track, "alt", RELIEF) : gradient(track, "speed", HEAT)) : null,
    panel: buildEventPanel(e, details),
  };
}

function buildEventPanel(e: EventDetail, details: ActivityDetail[]): Panel {
  const secs = [1, 2, 3, 4, 5].map((z) =>
    details.reduce((sum, d) => sum + (typeof d.garmin_summary?.[`hrTimeInZone_${z}`] === "number" ? (d.garmin_summary[`hrTimeInZone_${z}`] as number) : 0), 0),
  );
  const total = secs.reduce((a, b) => a + b, 0);
  const zones = total > 0 ? secs.map((s, i) => ({ zone: i + 1, pct: (s / total) * 100 })) : null;

  const byDay = e.span_days > 1;
  const rows: Panel["rows"] = byDay
    ? e.days.map((d) => ({
        label: `Day ${d.number}`,
        right: `${d.totals.distance_m != null ? `${formatKm(d.totals.distance_m)} km · ` : ""}${formatDuration(d.totals.moving_s ?? 0)}`,
        color: familyColor(d.activities[0]?.family ?? "other"),
      }))
    : e.days.flatMap((d) =>
        d.activities.map((a) => ({
          label: a.name,
          right: `${a.distance_m != null ? `${formatKm(a.distance_m)} km · ` : ""}${formatDuration(a.duration_s)}`,
          color: familyColor(a.family),
        })),
      );
  return { hr: null, zones, rowsTitle: byDay ? "Days" : "Legs", rows };
}
