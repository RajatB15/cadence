import { formatPace } from "./format";
import { HEAT, buildTrack, gradient, type Gradient, type Track } from "./route";
import type { ActivityDetail, Json } from "./types";

export const CARD_W = 1080;
export const CARD_H = 1920;
export const VIDEO_SPEEDS = [1, 1.25, 1.5, 2] as const;
export type VideoSpeed = (typeof VIDEO_SPEEDS)[number];
/** Length of the flyover at 1x; faster speeds shorten it. The intro and the closing hold are fixed. */
export const VIDEO_BASE_SECONDS = 12;
const ZONE_COLORS = ["#5c5a55", "#6cc7ff", "#5be3b0", "#c8f560", "#ffbe55", "#ff6a55", "#ff3b6b"];
const KIND_COLOR: Record<string, string> = {
  warmup: "#8d8a82", cooldown: "#8d8a82", strength: "#ff6a55", conditioning: "#ffbe55", core: "#9b8cff", mixed: "#6cc7ff",
};

const PACED = new Set(["run", "walk", "hike"]);
const LIME = "#c8f560";
const CREAM = "#f2e8cf";
const FONT = '"Manrope Variable", system-ui, sans-serif';
const DISPLAY = '"Instrument Serif", Georgia, serif';
const MONO = '"JetBrains Mono Variable", ui-monospace, monospace';

export interface CardStat {
  label: string;
  value: string;
  unit?: string;
}

export interface CardModel {
  title: string;
  kicker: string;
  date: string;
  color: string;
  stats: CardStat[];
  /** Stats shown big at the top; the moving ones in a video. */
  distanceM: number | null;
  durationS: number;
  track: Track | null;
  heat: Gradient | null;
  /** What fills the card when there is no route: heart-rate trace, zone split and a list of blocks or exercises. */
  panel: Panel;
}

export interface Panel {
  hr: number[] | null;
  zones: { zone: number; pct: number }[] | null;
  rowsTitle: string;
  rows: { label: string; right: string; color: string }[];
}

/** Everything the card shows, derived from the activity as loaded; missing values are left out, never zero. */
export function buildCardModel(d: ActivityDetail, color: string, kicker: string): CardModel {
  const a = d.activity;
  const local = (d.garmin_summary?.startTimeLocal as string | undefined) ?? a.start_time_utc;
  const when = new Date(local.replace(" ", "T"));
  const moving = a.moving_duration_s ?? a.duration_s;
  const stats: CardStat[] = [];
  if (a.distance_m) stats.push({ label: "Distance", value: (a.distance_m / 1000).toFixed(2), unit: "km" });
  stats.push({ label: "Time", value: formatClock(a.duration_s) });
  const sets = numOf(d.garmin_summary, "totalSets");
  const reps = numOf(d.garmin_summary, "totalReps");
  if (a.family === "strength") {
    if (sets) stats.push({ label: "Sets", value: String(Math.round(sets)) });
    if (reps) stats.push({ label: "Reps", value: String(Math.round(reps)) });
  }
  if (PACED.has(a.family) && a.distance_m) {
    const pace = formatPace(moving, a.distance_m);
    if (pace) stats.push({ label: "Avg pace", value: pace, unit: "/km" });
  } else if (a.avg_speed_mps) stats.push({ label: "Avg speed", value: (a.avg_speed_mps * 3.6).toFixed(1), unit: "km/h" });
  if (a.avg_hr) stats.push({ label: "Avg HR", value: String(Math.round(a.avg_hr)), unit: "bpm" });
  if (a.elevation_gain_m) stats.push({ label: "Elevation", value: String(Math.round(a.elevation_gain_m)), unit: "m" });
  if (a.calories) stats.push({ label: "Calories", value: String(Math.round(a.calories)), unit: "kcal" });
  if (a.training_load) stats.push({ label: "Load", value: String(Math.round(a.training_load)) });

  const track = d.fit && d.fit.route.length > 1 ? buildTrack(d.fit) : null;
  return {
    title: a.name,
    kicker,
    date: when.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }),
    color,
    stats,
    distanceM: a.distance_m,
    durationS: a.duration_s,
    track,
    heat: track ? gradient(track, "speed", HEAT) : null,
    panel: buildPanel(d),
  };
}

function numOf(obj: Json | null | undefined, key: string): number | null {
  const v = obj?.[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

const title = (s: string) => s.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

function buildPanel(d: ActivityDetail): Panel {
  const raw = d.fit?.streams.heart_rate ?? [];
  const present = raw.filter((v): v is number => v != null && v > 30);
  let hr: number[] | null = null;
  if (present.length >= 30) {
    const n = Math.min(140, present.length);
    hr = Array.from({ length: n }, (_, i) => {
      const chunk = present.slice(Math.floor((i * present.length) / n), Math.max(Math.floor(((i + 1) * present.length) / n), Math.floor((i * present.length) / n) + 1));
      return chunk.reduce((x, y) => x + y, 0) / chunk.length;
    });
  }

  let secs = (d.fit?.zones ?? []).filter((z) => z.zone >= 1 && z.zone <= 5).map((z) => ({ zone: z.zone, seconds: z.seconds }));
  if (!secs.some((z) => z.seconds > 0)) {
    secs = [1, 2, 3, 4, 5].map((z) => ({ zone: z, seconds: numOf(d.garmin_summary, `hrTimeInZone_${z}`) ?? 0 }));
  }
  const total = secs.reduce((x, z) => x + z.seconds, 0);
  const zones = total > 0 ? secs.map((z) => ({ zone: z.zone, pct: (z.seconds / total) * 100 })) : null;

  const label = d.strength?.label;
  const segments = label?.segments?.segments ?? [];
  const exercises = ((d.garmin_summary?.summarizedExerciseSets as Json[] | undefined) ?? []).flatMap((e) => {
    const name = [e.category, e.subCategory, e.exerciseName].find((v): v is string => typeof v === "string" && v.length > 0);
    if (!name) return [];
    const sets = numOf(e, "sets");
    const reps = numOf(e, "reps");
    const right = [sets ? `${sets} ${sets === 1 ? "set" : "sets"}` : null, reps ? `${reps} reps` : null].filter(Boolean).join(" · ");
    return [{ label: title(name), right, color: "#ff6a55", sets: sets ?? 0 }];
  });
  let rowsTitle = "";
  let rows: Panel["rows"] = [];
  if (segments.length) {
    rowsTitle = "Class blocks";
    rows = segments.map((g) => ({
      label: g.name,
      right: `${Math.max(1, Math.round((g.end_s - g.start_s) / 60))} min${g.avg_hr ? ` · ${Math.round(g.avg_hr)} bpm` : ""}`,
      color: KIND_COLOR[g.kind] ?? "#6cc7ff",
    }));
  } else if (exercises.length) {
    rowsTitle = "Exercises";
    rows = exercises.sort((x, y) => y.sets - x.sets).map(({ label: l, right, color }) => ({ label: l, right, color }));
  } else if (label?.blocks.length) {
    rowsTitle = "Blocks";
    rows = label.blocks.map((b) => ({ label: b.name, right: `${b.exercises.length} exercises`, color: KIND_COLOR[b.kind] ?? "#6cc7ff" }));
  }
  return { hr, zones, rowsTitle, rows };
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

export function videoSeconds(speed: number): number {
  return VIDEO_BASE_SECONDS / speed;
}

/** Whether this browser can run the 3D scene and encode H.264 (WebGL + WebCodecs). */
export async function canRenderVideo(): Promise<boolean> {
  if (typeof VideoEncoder === "undefined") return false;
  try {
    const gl = document.createElement("canvas").getContext("webgl2");
    if (!gl) return false;
    const { canEncodeVideo } = await import("mediabunny");
    return await canEncodeVideo("avc", { width: CARD_W, height: CARD_H });
  } catch {
    return false;
  }
}

export async function renderVideo(m: CardModel, opts: import("./shareVideo").VideoOptions): Promise<Blob> {
  const { renderFlyover } = await import("./shareVideo");
  return renderFlyover(m, opts);
}

/** Equirectangular fit of the route into a box, north up, never stretched. */
export function projectRoute(track: Track, box: { x: number; y: number; w: number; h: number }, maxPoints = 700): [number, number][] {
  const step = Math.max(1, Math.ceil(track.points.length / maxPoints));
  const pts = track.points.filter((_, i) => i % step === 0 || i === track.points.length - 1);
  const k = Math.cos(((track.bounds[0][1] + track.bounds[1][1]) / 2) * (Math.PI / 180));
  const xs = pts.map((p) => p.lon * k);
  const ys = pts.map((p) => -p.lat);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const w = Math.max(...xs) - minX || 1e-9;
  const h = Math.max(...ys) - minY || 1e-9;
  const scale = Math.min(box.w / w, box.h / h);
  const ox = box.x + (box.w - w * scale) / 2;
  const oy = box.y + (box.h - h * scale) / 2;
  return pts.map((_, i) => [ox + (xs[i] - minX) * scale, oy + (ys[i] - minY) * scale]);
}

function colorAt(heat: Gradient | null, fallback: string, p: number): string {
  if (!heat) return fallback;
  const stops = heat.stops;
  let lo = 0;
  while (lo < stops.length - 1 && stops[lo + 1][0] <= p) lo++;
  return stops[lo][1];
}

interface DrawOptions {
  /** No backdrop: for laying over a photo or video in another app. */
  transparent: boolean;
  /** 0..1 how much of the route is drawn and how far the counters have run. */
  progress: number;
  /** Your own picture behind the card, cropped to fill and dimmed so the text stays readable. */
  photo?: ImageBitmap | null;
  /** Text only, no backdrop, route or panel: composited over a rendered map for video. */
  overlay?: boolean;
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(next).width > maxWidth) {
      lines.push(line);
      line = word;
    } else line = next;
  }
  if (line) lines.push(line);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    let last = kept[maxLines - 1];
    while (last.length > 1 && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1);
    kept[maxLines - 1] = `${last}…`;
    return kept;
  }
  return lines;
}

export function drawCard(ctx: CanvasRenderingContext2D, m: CardModel, { transparent, progress, photo, overlay }: DrawOptions): void {
  if (!overlay) ctx.clearRect(0, 0, CARD_W, CARD_H);
  const floating = transparent || !!photo;
  if (photo) {
    const k = Math.max(CARD_W / photo.width, CARD_H / photo.height);
    ctx.drawImage(photo, (CARD_W - photo.width * k) / 2, (CARD_H - photo.height * k) / 2, photo.width * k, photo.height * k);
    const scrim = ctx.createLinearGradient(0, 0, 0, CARD_H);
    scrim.addColorStop(0, "rgba(0,0,0,0.5)");
    scrim.addColorStop(0.45, "rgba(0,0,0,0.22)");
    scrim.addColorStop(1, "rgba(0,0,0,0.72)");
    ctx.fillStyle = scrim;
    ctx.fillRect(0, 0, CARD_W, CARD_H);
  } else if (!transparent) {
    const bg = ctx.createLinearGradient(0, 0, 0, CARD_H);
    bg.addColorStop(0, "#14171c");
    bg.addColorStop(1, "#0b0b0c");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, CARD_W, CARD_H);
    const glow = ctx.createRadialGradient(150, 160, 0, 150, 160, 700);
    glow.addColorStop(0, `${m.color}40`);
    glow.addColorStop(1, `${m.color}00`);
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, CARD_W, CARD_H);
  }
  // Over a photo there is no dark backdrop to lean on, so everything carries its own soft shadow.
  const shade = (on: boolean) => {
    ctx.shadowColor = on && floating ? "rgba(0,0,0,0.55)" : "transparent";
    ctx.shadowBlur = on && floating ? 18 : 0;
    ctx.shadowOffsetY = on && floating ? 3 : 0;
  };
  const pad = 84;
  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "left";

  shade(true);
  ctx.fillStyle = m.color;
  ctx.font = `700 30px ${FONT}`;
  ctx.fillText(m.kicker.toUpperCase().split("").join(" "), pad, 150);
  ctx.fillStyle = "rgba(242,232,207,0.78)";
  ctx.font = `500 32px ${FONT}`;
  ctx.fillText(m.date, pad, 200);

  ctx.fillStyle = CREAM;
  ctx.font = `400 120px ${DISPLAY}`;
  const titleLines = wrap(ctx, m.title, CARD_W - pad * 2, 2);
  titleLines.forEach((line, i) => ctx.fillText(line, pad, 340 + i * 118));
  const titleBottom = 340 + (titleLines.length - 1) * 118;

  const statsTop = 1440;
  const mapBox = { x: pad, y: titleBottom + 70, w: CARD_W - pad * 2, h: statsTop - 100 - (titleBottom + 70) };
  if (!overlay) {
    if (m.track) drawRoute(ctx, m, mapBox, progress, transparent);
    else drawPanel(ctx, m.panel, mapBox);
  }

  // Stats: the first one leads, the rest sit in a row of up to three.
  const [lead, ...rest] = m.stats;
  const live = (s: CardStat): string => {
    if (progress >= 1) return s.value;
    if (s.label === "Distance" && m.distanceM) return ((m.distanceM / 1000) * progress).toFixed(2);
    if (s.label === "Time") return formatClock(m.durationS * progress);
    return s.value;
  };
  if (lead) {
    ctx.fillStyle = CREAM;
    ctx.font = `600 150px ${MONO}`;
    ctx.fillText(live(lead), pad, statsTop + 135);
    const w = ctx.measureText(live(lead)).width;
    if (lead.unit) {
      ctx.fillStyle = "rgba(242,232,207,0.7)";
      ctx.font = `500 52px ${FONT}`;
      ctx.fillText(lead.unit, pad + w + 18, statsTop + 135);
    }
    ctx.font = `600 26px ${FONT}`;
    ctx.fillStyle = "rgba(242,232,207,0.7)";
    ctx.fillText(lead.label.toUpperCase(), pad, statsTop - 8);
  }
  const row = rest.slice(0, 3);
  const colW = (CARD_W - pad * 2) / Math.max(1, row.length);
  row.forEach((s, i) => {
    const x = pad + i * colW;
    ctx.fillStyle = "rgba(242,232,207,0.7)";
    ctx.font = `600 24px ${FONT}`;
    ctx.fillText(s.label.toUpperCase(), x, statsTop + 255);
    ctx.fillStyle = CREAM;
    ctx.font = `600 58px ${MONO}`;
    const v = live(s);
    ctx.fillText(v, x, statsTop + 330);
    if (s.unit) {
      const w = ctx.measureText(v).width;
      ctx.fillStyle = "rgba(242,232,207,0.7)";
      ctx.font = `500 28px ${FONT}`;
      ctx.fillText(s.unit, x + w + 10, statsTop + 330);
    }
  });

  ctx.fillStyle = "rgba(242,232,207,0.55)";
  ctx.font = `700 26px ${FONT}`;
  ctx.textAlign = "right";
  ctx.fillText("CADENCE", CARD_W - pad, CARD_H - 70);
  ctx.textAlign = "left";
  shade(false);
}

const fit = (ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string => {
  let t = text;
  while (t.length > 1 && ctx.measureText(t).width > maxWidth) t = t.slice(0, -1);
  return t === text ? t : `${t.trimEnd()}…`;
};

function drawPanel(ctx: CanvasRenderingContext2D, p: Panel, box: { x: number; y: number; w: number; h: number }): void {
  const eyebrow = (text: string, y: number) => {
    ctx.fillStyle = "rgba(242,232,207,0.7)";
    ctx.font = `600 24px ${FONT}`;
    ctx.fillText(text.toUpperCase(), box.x, y);
  };
  let y = box.y;
  if (p.hr) {
    eyebrow("Heart rate", y + 24);
    const top = y + 50;
    const h = 170;
    const lo = Math.min(...p.hr);
    const span = Math.max(...p.hr) - lo || 1;
    const at = (i: number) => [box.x + (i / (p.hr!.length - 1)) * box.w, top + h - ((p.hr![i] - lo) / span) * h] as const;
    const area = ctx.createLinearGradient(0, top, 0, top + h);
    area.addColorStop(0, "rgba(255,106,85,0.55)");
    area.addColorStop(1, "rgba(255,106,85,0)");
    ctx.beginPath();
    ctx.moveTo(box.x, top + h);
    p.hr.forEach((_, i) => ctx.lineTo(...at(i)));
    ctx.lineTo(box.x + box.w, top + h);
    ctx.closePath();
    ctx.fillStyle = area;
    ctx.fill();
    ctx.beginPath();
    p.hr.forEach((_, i) => (i ? ctx.lineTo(...at(i)) : ctx.moveTo(...at(i))));
    ctx.lineWidth = 5;
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#ff6a55";
    ctx.stroke();
    ctx.fillStyle = "rgba(242,232,207,0.7)";
    ctx.font = `500 24px ${MONO}`;
    ctx.textAlign = "right";
    ctx.fillText(`${Math.round(lo)}–${Math.round(lo + span)} bpm`, box.x + box.w, y + 24);
    ctx.textAlign = "left";
    y = top + h + 60;
  }
  if (p.zones) {
    eyebrow("Time in zones", y + 24);
    let x = box.x;
    const barY = y + 44;
    for (const z of p.zones) {
      const w = (z.pct / 100) * box.w;
      ctx.fillStyle = ZONE_COLORS[z.zone] ?? CREAM;
      ctx.fillRect(x, barY, w, 30);
      if (z.pct >= 9) {
        ctx.fillStyle = "rgba(242,232,207,0.85)";
        ctx.font = `600 22px ${MONO}`;
        ctx.fillText(`Z${z.zone} ${Math.round(z.pct)}%`, x, barY + 62);
      }
      x += w;
    }
    y = barY + 110;
  }
  if (p.rows.length) {
    eyebrow(p.rowsTitle, y + 24);
    y += 50;
    const rowH = 64;
    const room = Math.floor((box.y + box.h - y) / rowH);
    const shown = p.rows.slice(0, Math.max(0, Math.min(7, room)));
    shown.forEach((r, i) => {
      const ry = y + i * rowH;
      ctx.fillStyle = r.color;
      ctx.fillRect(box.x, ry + 8, 8, rowH - 22);
      ctx.textAlign = "right";
      ctx.fillStyle = "rgba(242,232,207,0.78)";
      ctx.font = `500 28px ${MONO}`;
      const rw = ctx.measureText(r.right).width;
      ctx.fillText(r.right, box.x + box.w, ry + 40);
      ctx.textAlign = "left";
      ctx.fillStyle = CREAM;
      ctx.font = `600 34px ${FONT}`;
      ctx.fillText(fit(ctx, r.label, box.w - rw - 60), box.x + 28, ry + 40);
    });
    if (shown.length < p.rows.length) {
      ctx.fillStyle = "rgba(242,232,207,0.6)";
      ctx.font = `500 26px ${FONT}`;
      ctx.fillText(`+ ${p.rows.length - shown.length} more`, box.x + 28, y + shown.length * rowH + 34);
    }
  }
}

function drawRoute(
  ctx: CanvasRenderingContext2D,
  m: CardModel,
  box: { x: number; y: number; w: number; h: number },
  progress: number,
  transparent: boolean,
): void {
  const track = m.track!;
  const pts = projectRoute(track, box);
  const n = pts.length;
  // Point i sits at this share of the way along the line (decimation keeps the ends).
  const at = (i: number) => track.progress[Math.min(track.points.length - 1, Math.round((i / (n - 1)) * (track.points.length - 1)))];
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  const stroke = (width: number, color: (i: number) => string, upTo: number, shadow: boolean) => {
    ctx.lineWidth = width;
    ctx.shadowColor = shadow ? "rgba(0,0,0,0.6)" : "transparent";
    ctx.shadowBlur = shadow ? 16 : 0;
    for (let i = 1; i <= upTo; i++) {
      ctx.beginPath();
      ctx.moveTo(pts[i - 1][0], pts[i - 1][1]);
      ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.strokeStyle = color(i);
      ctx.stroke();
    }
  };
  const last = Math.max(1, Math.min(n - 1, Math.floor(progress * (n - 1))));
  // A faint full route first, so a video shows where it is heading.
  if (progress < 1) stroke(10, () => "rgba(242,232,207,0.16)", n - 1, false);
  if (!transparent) stroke(26, () => "rgba(0,0,0,0.5)", last, false);
  stroke(14, (i) => colorAt(m.heat, LIME, at(i)), last, transparent);
  ctx.shadowColor = "transparent";
  ctx.shadowBlur = 0;

  const next = Math.min(n - 1, last + 1);
  const span = at(next) - at(last);
  const f = span > 0 ? Math.min(1, Math.max(0, (progress - at(last)) / span)) : 0;
  const head = [pts[last][0] + (pts[next][0] - pts[last][0]) * f, pts[last][1] + (pts[next][1] - pts[last][1]) * f];
  dot(ctx, pts[0], 20, "#0b0b0c", LIME, 8);
  if (progress >= 1) dot(ctx, pts[n - 1], 20, "#ff6a55", "#0b0b0c", 6);
  else dot(ctx, head, 22, LIME, "#0b0b0c", 7);
}

function dot(ctx: CanvasRenderingContext2D, [x, y]: [number, number] | number[], r: number, fill: string, ring: string, ringWidth: number) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.lineWidth = ringWidth;
  ctx.strokeStyle = ring;
  ctx.stroke();
}

export function makeCanvas(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = CARD_W;
  canvas.height = CARD_H;
  return canvas;
}

export async function fontsReady(): Promise<void> {
  try {
    await Promise.all([`600 40px ${MONO}`, `700 30px ${FONT}`, `400 40px ${DISPLAY}`].map((f) => document.fonts.load(f)));
  } catch {
    // Fall back to the system fonts already named in the stacks.
  }
}

export async function renderPng(m: CardModel, transparent: boolean, photo?: ImageBitmap | null): Promise<Blob> {
  await fontsReady();
  const canvas = makeCanvas();
  drawCard(canvas.getContext("2d")!, m, { transparent, progress: 1, photo });
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("The browser couldn't make the image."))), "image/png"));
}

export function fileName(m: CardModel, ext: "png" | "mp4", transparent: boolean): string {
  const slug = m.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "activity";
  return `cadence-${slug}${transparent ? "-transparent" : ""}.${ext}`;
}
