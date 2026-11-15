// The day as one 24-hour ring, built only from things Cadence actually knows: last night's sleep, sessions done today, a planned session,
// the usual eating window and tonight's bedtime. Midnight is at the bottom, 06:00 at the left, noon at the top and 18:00 at the right, so
// the sun arcs over the top like it does outside. Pure: minutes after local midnight in, arcs and the next thing out.
import { EAT_END_MIN, EAT_START_MIN } from "./moment";

export type OrbitKind = "sleep" | "session" | "planned" | "eat";
export interface OrbitArc { kind: OrbitKind; from: number; to: number; label: string; dashed?: boolean }
export interface OrbitInput {
  minutes: number;
  /** Hours slept last night and the usual wake time (minutes), which together place the sleep arc; both needed. */
  sleepH?: number | null;
  wakeMin?: number | null;
  /** Sessions already done today. */
  sessions?: { startMin: number; minutes: number; label: string }[];
  /** A session planned for today and not done. */
  planned?: { startMin: number; minutes: number; label: string }[];
  bedMin?: number | null;
}
export interface OrbitModel {
  arcs: OrbitArc[];
  now: number;
  bed: number | null;
  /** What is coming next today, or null when there is nothing left to say. */
  next: { label: string; at: number } | null;
}

const norm = (m: number) => ((Math.round(m) % 1440) + 1440) % 1440;

export function orbitModel(i: OrbitInput): OrbitModel {
  const now = norm(i.minutes);
  const arcs: OrbitArc[] = [];
  if (i.sleepH != null && i.sleepH > 0 && i.wakeMin != null) {
    const wake = norm(i.wakeMin);
    arcs.push({ kind: "sleep", from: norm(wake - i.sleepH * 60), to: wake, label: `Slept ${Math.floor(i.sleepH)} h ${Math.round((i.sleepH % 1) * 60)} min` });
  }
  arcs.push({ kind: "eat", from: EAT_START_MIN, to: EAT_END_MIN, label: "Usual eating window" });
  for (const s of i.sessions ?? []) arcs.push({ kind: "session", from: norm(s.startMin), to: norm(s.startMin + Math.max(10, s.minutes)), label: s.label });
  for (const s of i.planned ?? []) arcs.push({ kind: "planned", from: norm(s.startMin), to: norm(s.startMin + Math.max(10, s.minutes)), label: s.label, dashed: true });
  const bed = i.bedMin != null ? norm(i.bedMin) : null;
  const upcoming = [
    ...(i.planned ?? []).filter((p) => norm(p.startMin) > now).map((p) => ({ label: p.label, at: norm(p.startMin) })),
    ...(bed != null && bed > now ? [{ label: "In bed by", at: bed }] : []),
  ].sort((a, b) => a.at - b.at);
  return { arcs, now, bed, next: upcoming[0] ?? null };
}

/** Degrees clockwise from the bottom of the ring for a time of day. */
export const orbitAngle = (min: number): number => (norm(min) / 1440) * 360;

/** A point on a circle of radius r at a time of day: midnight at the bottom, clockwise as seen on screen (06:00 left, noon top). */
export function orbitPoint(cx: number, cy: number, r: number, min: number): { x: number; y: number } {
  const a = (orbitAngle(min) * Math.PI) / 180;
  return { x: cx - r * Math.sin(a), y: cy + r * Math.cos(a) };
}

/** SVG arc path along the ring from one time to another (clockwise); a span past 24 h or zero draws nothing. */
export function orbitPath(cx: number, cy: number, r: number, from: number, to: number): string {
  const span = ((norm(to) - norm(from)) + 1440) % 1440;
  if (span === 0) return "";
  const a = orbitPoint(cx, cy, r, from);
  const b = orbitPoint(cx, cy, r, from + span);
  // On screen the ring runs clockwise from the bottom through the left, which is sweep flag 1 in SVG's y-down space.
  return `M ${a.x.toFixed(2)} ${a.y.toFixed(2)} A ${r} ${r} 0 ${span > 720 ? 1 : 0} 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

/** Minutes after local midnight (on the device) for an ISO timestamp; null when it will not parse. */
export function minutesOfIso(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = new Date(iso.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isFinite(d.getTime()) ? d.getHours() * 60 + d.getMinutes() : null;
}
