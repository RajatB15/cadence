import { formatPace } from "./format";
import { HEAT, buildTrack, gradient, type Gradient, type Track } from "./route";
import type { ActivityDetail } from "./types";

export const CARD_W = 1080;
export const CARD_H = 1920;
export const VIDEO_SPEEDS = [1, 1.25, 1.5, 2] as const;
export type VideoSpeed = (typeof VIDEO_SPEEDS)[number];
/** Length of the route-drawing video at 1x; faster speeds shorten it. */
export const VIDEO_BASE_SECONDS = 12;
const FPS = 30;
const HOLD_SECONDS = 1.5;

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
  if (PACED.has(a.family) && a.distance_m) {
    const pace = formatPace(moving, a.distance_m);
    if (pace) stats.push({ label: "Avg pace", value: pace, unit: "/km" });
  } else if (a.avg_speed_mps) stats.push({ label: "Avg speed", value: (a.avg_speed_mps * 3.6).toFixed(1), unit: "km/h" });
  if (a.avg_hr) stats.push({ label: "Avg HR", value: String(Math.round(a.avg_hr)), unit: "bpm" });
  if (a.elevation_gain_m) stats.push({ label: "Elevation", value: String(Math.round(a.elevation_gain_m)), unit: "m" });
  if (a.calories) stats.push({ label: "Calories", value: String(Math.round(a.calories)), unit: "kcal" });

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
  };
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

export function drawCard(ctx: CanvasRenderingContext2D, m: CardModel, { transparent, progress }: DrawOptions): void {
  ctx.clearRect(0, 0, CARD_W, CARD_H);
  if (!transparent) {
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
    ctx.shadowColor = on && transparent ? "rgba(0,0,0,0.55)" : "transparent";
    ctx.shadowBlur = on && transparent ? 18 : 0;
    ctx.shadowOffsetY = on && transparent ? 3 : 0;
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
  if (m.track) drawRoute(ctx, m, mapBox, progress, transparent);

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
    ctx.fillText(live(lead), pad, statsTop + 110);
    const w = ctx.measureText(live(lead)).width;
    if (lead.unit) {
      ctx.fillStyle = "rgba(242,232,207,0.7)";
      ctx.font = `500 52px ${FONT}`;
      ctx.fillText(lead.unit, pad + w + 18, statsTop + 110);
    }
    ctx.font = `600 26px ${FONT}`;
    ctx.fillStyle = "rgba(242,232,207,0.7)";
    ctx.fillText(lead.label.toUpperCase(), pad, statsTop + 28);
  }
  const row = rest.slice(0, 3);
  const colW = (CARD_W - pad * 2) / Math.max(1, row.length);
  row.forEach((s, i) => {
    const x = pad + i * colW;
    ctx.fillStyle = "rgba(242,232,207,0.7)";
    ctx.font = `600 24px ${FONT}`;
    ctx.fillText(s.label.toUpperCase(), x, statsTop + 230);
    ctx.fillStyle = CREAM;
    ctx.font = `600 66px ${MONO}`;
    const v = live(s);
    ctx.fillText(v, x, statsTop + 305);
    if (s.unit) {
      const w = ctx.measureText(v).width;
      ctx.fillStyle = "rgba(242,232,207,0.7)";
      ctx.font = `500 28px ${FONT}`;
      ctx.fillText(s.unit, x + w + 10, statsTop + 305);
    }
  });

  ctx.fillStyle = "rgba(242,232,207,0.55)";
  ctx.font = `700 26px ${FONT}`;
  ctx.textAlign = "right";
  ctx.fillText("CADENCE", CARD_W - pad, CARD_H - 70);
  ctx.textAlign = "left";
  shade(false);
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

function makeCanvas(): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = CARD_W;
  canvas.height = CARD_H;
  return canvas;
}

async function fontsReady(): Promise<void> {
  try {
    await Promise.all([`600 40px ${MONO}`, `700 30px ${FONT}`, `400 40px ${DISPLAY}`].map((f) => document.fonts.load(f)));
  } catch {
    // Fall back to the system fonts already named in the stacks.
  }
}

export async function renderPng(m: CardModel, transparent: boolean): Promise<Blob> {
  await fontsReady();
  const canvas = makeCanvas();
  drawCard(canvas.getContext("2d")!, m, { transparent, progress: 1 });
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("The browser couldn't make the image."))), "image/png"));
}

/** Whether this browser can encode H.264 video (WebCodecs); Safari 16.4+, Chrome and Edge can. */
export async function canRenderVideo(): Promise<boolean> {
  if (typeof VideoEncoder === "undefined") return false;
  try {
    const { canEncodeVideo } = await import("mediabunny");
    return await canEncodeVideo("avc", { width: CARD_W, height: CARD_H });
  } catch {
    return false;
  }
}

/** MP4 of the route drawing itself, then holding on the finished card. MP4 has no alpha, so video always has the dark backdrop. */
export async function renderVideo(m: CardModel, speed: number, onProgress: (done: number) => void, signal: AbortSignal): Promise<Blob> {
  await fontsReady();
  const { Output, Mp4OutputFormat, BufferTarget, CanvasSource, QUALITY_HIGH } = await import("mediabunny");
  const canvas = makeCanvas();
  const ctx = canvas.getContext("2d")!;
  const output = new Output({ format: new Mp4OutputFormat(), target: new BufferTarget() });
  const source = new CanvasSource(canvas, { codec: "avc", bitrate: QUALITY_HIGH });
  output.addVideoTrack(source, { frameRate: FPS });
  await output.start();
  const drawFrames = Math.round(videoSeconds(speed) * FPS);
  const total = drawFrames + Math.round(HOLD_SECONDS * FPS);
  try {
    for (let f = 0; f < total; f++) {
      if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
      const t = Math.min(1, f / drawFrames);
      drawCard(ctx, m, { transparent: false, progress: t });
      await source.add(f / FPS, 1 / FPS);
      if (f % 10 === 0) onProgress(f / total);
    }
    source.close();
    await output.finalize();
  } catch (e) {
    await output.cancel().catch(() => {});
    throw e;
  }
  onProgress(1);
  return new Blob([output.target.buffer!], { type: "video/mp4" });
}

export function fileName(m: CardModel, ext: "png" | "mp4", transparent: boolean): string {
  const slug = m.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "activity";
  return `cadence-${slug}${transparent ? "-transparent" : ""}.${ext}`;
}
