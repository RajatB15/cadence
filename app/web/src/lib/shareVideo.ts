import { Map as MapLibreMap, setWorkerUrl, type ExpressionSpecification, type LngLatBoundsLike, type LngLatLike } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { DEM_TILES, SKY, STYLES, terrainFor, type Basemap } from "./mapStyle";
import { cameraSigma, chaseHeading, chaseWindow, chasePitch, sample, smoothPath, steer, terrainExaggeration, turn } from "./route";
import { CARD_H, CARD_W, drawCard, fontsReady, makeCanvas, videoSeconds, type CardModel } from "./shareCard";

setWorkerUrl(workerUrl);

export interface VideoOptions {
  speed: number;
  basemap: Basemap;
  /** hd = 1080x1920 at 12 Mbps; sd = 720x1280 at 5 Mbps, for devices that run out of graphics memory at hd. */
  quality: "hd" | "sd";
  onProgress: (done: number) => void;
  signal: AbortSignal;
}

const FPS = 30;
const INTRO_S = 0.8;
const OUTRO_S = 2.6;
const OUTRO_MOVE_S = 1.6;
const PITCH_OVERVIEW = 58;
const LIME = "#c8f560";
/** Room kept clear of the head for the title above and the stats below. */
const FOLLOW_PADDING = { top: 360, bottom: 560, left: 0, right: 0 };
const NONE = "rgba(0,0,0,0)";
const ATTRIBUTION: Record<Basemap, string> = {
  dark: "© OpenStreetMap contributors · OpenFreeMap · Terrain: Mapzen, AWS",
  streets: "© OpenStreetMap contributors · OpenFreeMap · Terrain: Mapzen, AWS",
  satellite: "Sentinel-2 cloudless by EOX IT Services (contains modified Copernicus Sentinel data 2025) · Terrain: Mapzen, AWS",
};

const smooth = (t: number) => t * t * (3 - 2 * t);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

interface Cam {
  center: [number, number];
  zoom: number;
  bearing: number;
  pitch: number;
  padding: { top: number; bottom: number; left: number; right: number };
}

function mix(a: Cam, b: Cam, t: number, bearingTurn = true): Cam {
  return {
    center: [lerp(a.center[0], b.center[0], t), lerp(a.center[1], b.center[1], t)],
    zoom: lerp(a.zoom, b.zoom, t),
    bearing: a.bearing + (bearingTurn ? turn(b.bearing, a.bearing) : b.bearing - a.bearing) * t,
    pitch: lerp(a.pitch, b.pitch, t),
    padding: {
      top: lerp(a.padding.top, b.padding.top, t),
      bottom: lerp(a.padding.bottom, b.padding.bottom, t),
      left: lerp(a.padding.left, b.padding.left, t),
      right: lerp(a.padding.right, b.padding.right, t),
    },
  };
}

/** The route's colours revealed up to `p`, hidden beyond it (a line-gradient expression on line-progress). */
function revealed(stops: [number, string][], p: number): ExpressionSpecification {
  let out: [number, string][];
  if (p <= 0.0005) out = [[0, NONE], [1, NONE]];
  else if (p >= 1) out = stops;
  else {
    const kept = stops.filter(([at]) => at < p - 2e-4);
    const here = (kept[kept.length - 1] ?? stops[0])[1];
    out = [...kept, [p - 1e-4, here], [p, `${here}00`], [1, `${here}00`]];
  }
  const clean: [number, string][] = [];
  for (const s of out) if (!clean.length || s[0] > clean[clean.length - 1][0]) clean.push(s);
  if (clean[0][0] > 0) clean.unshift([0, clean[0][1]]);
  return ["interpolate", ["linear"], ["line-progress"], ...clean.flat()] as ExpressionSpecification;
}

/**
 * The 3D flyover as a video: an off-screen MapLibre scene (terrain, hillshade, the route coloured by pace)
 * stepped one frame at a time, so every frame waits for its tiles. Draws the card's text over it.
 * Fetches map tiles from the same keyless providers as the Route map; the activity itself never leaves the device.
 */
export async function renderFlyover(m: CardModel, { speed, basemap, quality, onProgress, signal }: VideoOptions): Promise<Blob> {
  const track = m.track;
  if (!track) throw new Error("This activity has no GPS route.");
  await fontsReady();
  const { Output, Mp4OutputFormat, BufferTarget, CanvasSource } = await import("mediabunny");

  const holder = document.createElement("div");
  holder.setAttribute("aria-hidden", "true");
  holder.style.cssText = `position:fixed;left:-10000px;top:0;width:${CARD_W}px;height:${CARD_H}px;pointer-events:none`;
  document.body.appendChild(holder);
  const scale = quality === "sd" ? 2 / 3 : 1;
  const gate = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
  let map: MapLibreMap | null = null;
  let output: { cancel: () => Promise<void> } | null = null;
  try {
    map = new MapLibreMap({
      container: holder,
      style: STYLES[basemap],
      bounds: track.bounds as LngLatBoundsLike,
      pixelRatio: scale,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      maxPitch: 80,
      canvasContextAttributes: { preserveDrawingBuffer: true },
    });
    const mp = map;
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(() => reject(new Error("The map didn't load. Check your connection and try again.")), 20_000);
      mp.once("load", () => {
        clearTimeout(t);
        resolve();
      });
      mp.once("error", (e) => {
        if (!mp.loaded()) {
          clearTimeout(t);
          reject(new Error(`The map didn't load: ${(e as unknown as { error?: Error }).error?.message ?? "unknown error"}`));
        }
      });
    });

    // Scene: relief, the route (dim full line + coloured reveal), a start pin; the moving head is drawn over the finished frame.
    const dem = { type: "raster-dem" as const, tiles: [DEM_TILES], tileSize: 256, maxzoom: 14, encoding: "terrarium" as const };
    mp.addSource("dem", dem);
    mp.addSource("dem-shade", dem);
    const firstLabel = mp.getStyle().layers.find((l) => l.type === "symbol")?.id;
    mp.addLayer(
      {
        id: "relief",
        type: "hillshade",
        source: "dem-shade",
        paint: {
          "hillshade-exaggeration": basemap === "satellite" ? 0.3 : 0.7,
          "hillshade-shadow-color": "rgba(0,0,0,0.6)",
          "hillshade-highlight-color": "rgba(255,255,255,0.18)",
          "hillshade-accent-color": "rgba(0,0,0,0.25)",
        },
      },
      firstLabel,
    );
    if (track.elevation && basemap !== "satellite") {
      // A soft height tint under the route (valleys cool and dark, ridges warm and pale) so climbs read as colour as well as shape.
      const [lo, hi] = track.elevation;
      const span = Math.max(hi - lo, 50);
      const at = (f: number) => lo - span * 0.6 + f * span * 2.2;
      mp.addLayer(
        {
          id: "height-tint",
          type: "color-relief",
          source: "dem-shade",
          paint: {
            "color-relief-opacity": 0.4,
            "color-relief-color": ["interpolate", ["linear"], ["elevation"], at(0), "#14324a", at(0.35), "#2f6f6a", at(0.65), "#9a8a4a", at(1), "#f2e8cf"],
          },
        },
        "relief",
      );
    }
    const coords = track.points.map((p) => [p.lon, p.lat]);
    mp.addSource("route", { type: "geojson", lineMetrics: true, data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } } });
    const point = (lon: number, lat: number) => ({ type: "Feature" as const, properties: {}, geometry: { type: "Point" as const, coordinates: [lon, lat] } });
    mp.addSource("start", { type: "geojson", data: point(coords[0][0], coords[0][1]) });
    const join = { "line-join": "round", "line-cap": "round" } as const;
    // Drawn into a 1080-wide frame that is viewed small on a phone, so much heavier than the on-screen map's line.
    const width = (lo: number, hi: number): ExpressionSpecification => ["interpolate", ["linear"], ["zoom"], 10, lo, 16, hi];
    const stops: [number, string][] = m.heat?.stops ?? [[0, LIME], [1, LIME]];
    mp.addLayer({ id: "route-dim", type: "line", source: "route", layout: join, paint: { "line-color": "#f2e8cf", "line-opacity": 0.22, "line-width": width(5, 9) } });
    mp.addLayer({ id: "route-casing", type: "line", source: "route", layout: join, paint: { "line-gradient": revealed([[0, "#0b0b0c"], [1, "#0b0b0c"]], 0), "line-width": width(17, 38), "line-opacity": 0.85 } });
    mp.addLayer({ id: "route-glow", type: "line", source: "route", layout: join, paint: { "line-gradient": revealed(stops, 0), "line-width": width(26, 56), "line-blur": width(14, 30), "line-opacity": 0.5 } });
    mp.addLayer({ id: "route-line", type: "line", source: "route", layout: join, paint: { "line-gradient": revealed(stops, 0), "line-width": width(10, 24) } });
    mp.addLayer({ id: "start-pin", type: "circle", source: "start", paint: { "circle-radius": 16, "circle-color": "#0b0b0c", "circle-stroke-color": LIME, "circle-stroke-width": 6, "circle-pitch-alignment": "map" } });
    mp.setSky(SKY);
    mp.setTerrain(terrainFor(terrainExaggeration(track)));

    // Cameras: the whole route from above-ish, and the head-following chase view.
    const fitted = mp.cameraForBounds(track.bounds as LngLatBoundsLike, {
      padding: { top: 380, bottom: 620, left: 100, right: 100 },
      absolutePadding: true,
      bearing: -18,
      pitch: PITCH_OVERVIEW,
      maxZoom: 16,
    });
    const c = fitted?.center ? (Array.isArray(fitted.center) ? fitted.center : [(fitted.center as { lng: number }).lng, (fitted.center as { lat: number }).lat]) : coords[0];
    const overview: Cam = {
      center: [c[0], c[1]],
      zoom: fitted?.zoom ?? 12,
      bearing: -18,
      pitch: PITCH_OVERVIEW,
      padding: { top: 0, bottom: 0, left: 0, right: 0 },
    };
    const followZoom = Math.min(15.6, Math.max(12.6, 16.2 - Math.log2(Math.max(1, track.meters / 1000)) * 0.55));
    const pitchFollow = chasePitch(track);
    // The camera glides along a smoothed copy of the route; the marker stays on the real fixes.
    const sigma = cameraSigma(track.meters, videoSeconds(speed));
    const cam = smoothPath(track, sigma);
    const reach = chaseWindow(sigma);
    const follow = (p: number, heading: number): Cam => {
      const here = cam(p);
      return { center: [here.lon, here.lat], zoom: followZoom, bearing: heading, pitch: pitchFollow, padding: FOLLOW_PADDING };
    };
    const headingAt = (p: number) => chaseHeading(track, p, reach.ahead, reach.behind, cam);

    const settled = () =>
      new Promise<void>((resolve) => {
        const t = setTimeout(resolve, 6000);
        mp.once("idle", () => {
          clearTimeout(t);
          resolve();
        });
        mp.triggerRepaint();
      });
    const setReveal = (p: number) => {
      mp.setPaintProperty("route-line", "line-gradient", revealed(stops, p));
      mp.setPaintProperty("route-glow", "line-gradient", revealed(stops, p));
      mp.setPaintProperty("route-casing", "line-gradient", revealed([[0, "#0b0b0c"], [1, "#0b0b0c"]], p));
    };

    const canvas = makeCanvas();
    canvas.width = Math.round(CARD_W * scale);
    canvas.height = Math.round(CARD_H * scale);
    const ctx = canvas.getContext("2d")!;
    ctx.scale(scale, scale);
    let lost = false;
    mp.getCanvas().addEventListener("webglcontextlost", () => (lost = true));
    const target = new BufferTarget();
    const out = new Output({ format: new Mp4OutputFormat(), target });
    output = out;
    const source = new CanvasSource(canvas, { codec: "avc", bitrate: scale < 1 ? 5_000_000 : 12_000_000 });
    out.addVideoTrack(source, { frameRate: FPS });
    await out.start();

    const introF = Math.round(INTRO_S * FPS);
    const flightF = Math.round(videoSeconds(speed) * FPS);
    const outroF = Math.round(OUTRO_S * FPS);
    const moveF = Math.round(OUTRO_MOVE_S * FPS);
    const total = introF + flightF + outroF;
    let heading = headingAt(0);
    let last: Cam = follow(0, heading);

    for (let f = 0; f < total; f++) {
      if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
      if (lost) throw new Error("The browser ran out of graphics memory. Choose 720p quality, close other tabs, or try the Dark map.");
      let p = 0;
      let cam: Cam;
      if (f < introF) {
        cam = mix(overview, follow(0, heading), smooth((f + 1) / introF));
        p = 0;
      } else if (f < introF + flightF) {
        p = (f - introF + 1) / flightF;
        heading = steer(heading, headingAt(p), 1 / FPS);
        cam = follow(p, heading);
        last = cam;
      } else {
        p = 1;
        cam = mix(last, overview, smooth(Math.min(1, (f - introF - flightF + 1) / moveF)));
      }
      setReveal(p);
      const ready = settled();
      mp.jumpTo({ center: cam.center as LngLatLike, zoom: cam.zoom, bearing: cam.bearing, pitch: cam.pitch, padding: cam.padding });
      await ready;

      ctx.clearRect(0, 0, CARD_W, CARD_H);
      ctx.drawImage(mp.getCanvas(), 0, 0, CARD_W, CARD_H);
      const top = ctx.createLinearGradient(0, 0, 0, 560);
      top.addColorStop(0, "rgba(11,11,12,0.82)");
      top.addColorStop(1, "rgba(11,11,12,0)");
      ctx.fillStyle = top;
      ctx.fillRect(0, 0, CARD_W, 560);
      const bottom = ctx.createLinearGradient(0, CARD_H - 640, 0, CARD_H);
      bottom.addColorStop(0, "rgba(11,11,12,0)");
      bottom.addColorStop(1, "rgba(11,11,12,0.88)");
      ctx.fillStyle = bottom;
      ctx.fillRect(0, CARD_H - 640, CARD_W, 640);
      // The runner is drawn on top of the map, not in it, so a ridge in front of them never hides where they are.
      const here = sample(track, p);
      const at = mp.project([here.lon, here.lat]);
      if (at.x > -40 && at.x < CARD_W + 40 && at.y > -40 && at.y < CARD_H + 40) {
        ctx.beginPath();
        ctx.arc(at.x, at.y, 38, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(200,245,96,0.3)";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(at.x, at.y, 17, 0, Math.PI * 2);
        ctx.fillStyle = LIME;
        ctx.fill();
        ctx.lineWidth = 5;
        ctx.strokeStyle = "#0b0b0c";
        ctx.stroke();
      }
      drawCard(ctx, m, { transparent: true, progress: p, overlay: true });
      ctx.fillStyle = "rgba(242,232,207,0.5)";
      ctx.font = '500 17px "Manrope Variable", system-ui, sans-serif';
      ctx.fillText(ATTRIBUTION[basemap], 84, CARD_H - 26);

      await source.add(f / FPS, 1 / FPS);
      if (f % 5 === 0) {
        onProgress(f / total);
        await gate(0);
      }
    }
    source.close();
    await out.finalize();
    onProgress(1);
    return new Blob([target.buffer!], { type: "video/mp4" });
  } catch (e) {
    await output?.cancel().catch(() => {});
    throw e;
  } finally {
    map?.remove();
    holder.remove();
  }
}
