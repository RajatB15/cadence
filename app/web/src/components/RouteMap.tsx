import { clsx } from "clsx";
import {
  FullscreenControl,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  setWorkerUrl,
  type ExpressionSpecification,
  type LngLatBoundsLike,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { Pause, Play, Scan } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { formatPace } from "../lib/format";
import { BASEMAPS, DEM_ATTRIBUTION, DEM_TILES, SKY, STYLES, terrainFor, type Basemap } from "../lib/mapStyle";
import {
  HEAT,
  RELIEF,
  buildTrack,
  cameraSigma,
  chaseHeading,
  chaseWindow,
  chasePitch,
  distanceMarks,
  gradient,
  sample,
  smoothPath,
  steer,
  terrainExaggeration,
  type Gradient,
  type Track,
  type TrackKey,
} from "../lib/route";
import type { FitData } from "../lib/types";

type Mode = TrackKey | "plain";

const BASEMAP_KEY = "cadence.map.basemap";
const LIME = "#c8f560";
const PACED = new Set(["run", "walk", "hike"]);
const PITCH_3D = 58;

let webgl: boolean | null = null;
setWorkerUrl(workerUrl);
function hasWebGL(): boolean {
  if (webgl == null) {
    try {
      const canvas = document.createElement("canvas");
      webgl = !!(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
    } catch {
      webgl = false;
    }
  }
  return webgl;
}

export default function RouteMap({ fit, family, fallback }: { fit: FitData; family: string; fallback: ReactNode }) {
  const track = useMemo(() => buildTrack(fit), [fit]);
  const [failed, setFailed] = useState(false);
  if (!track || failed || !hasWebGL()) return <>{fallback}</>;
  return <MapView track={track} paced={PACED.has(family)} onFail={() => setFailed(true)} />;
}

function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

function pin(className: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = className;
  return el;
}

/** Round badge behind km labels, drawn at 2x for crisp edges. */
function badge(): { width: number; height: number; data: Uint8ClampedArray } {
  const size = 44;
  const ctx = document.createElement("canvas").getContext("2d")!;
  ctx.canvas.width = ctx.canvas.height = size;
  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(11,11,12,0.88)";
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(255,255,255,0.35)";
  ctx.stroke();
  return { width: size, height: size, data: ctx.getImageData(0, 0, size, size).data };
}

function MapView({ track, paced, onFail }: { track: Track; paced: boolean; onFail: () => void }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const headRef = useRef<Marker | null>(null);
  const rafRef = useRef(0);
  const anim = useRef({ p: 0, last: 0, bearing: 0 });

  const gradients = useMemo<Record<TrackKey, Gradient | null>>(
    () => ({ speed: gradient(track, "speed", HEAT), hr: gradient(track, "hr", HEAT), alt: gradient(track, "alt", RELIEF) }),
    [track],
  );
  const modes = (["speed", "hr", "alt"] as TrackKey[]).filter((k) => gradients[k]);
  const relief = track.elevation ? track.elevation[1] - track.elevation[0] : 0;

  const [basemap, setBasemap] = useState<Basemap>(() => {
    const saved = localStorage.getItem(BASEMAP_KEY);
    return saved && saved in STYLES ? (saved as Basemap) : "dark";
  });
  const [is3d, setIs3d] = useState(relief >= 60);
  const [mode, setMode] = useState<Mode>(modes[0] ?? "plain");
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [full, setFull] = useState(false);

  // Map event handlers outlive renders; they read the latest choices from here.
  const live = useRef({ basemap, is3d, mode, playing });
  useEffect(() => {
    live.current = { ...live.current, basemap, is3d, mode };
  });

  const line = useMemo(
    () => ({
      type: "Feature" as const,
      properties: {},
      geometry: { type: "LineString" as const, coordinates: track.points.map((p) => [p.lon, p.lat]) },
    }),
    [track],
  );
  const marks = useMemo(
    () => ({
      type: "FeatureCollection" as const,
      features: distanceMarks(track).map((m) => ({
        type: "Feature" as const,
        properties: { km: m.km },
        geometry: { type: "Point" as const, coordinates: [m.lon, m.lat] },
      })),
    }),
    [track],
  );
  const duration = Math.min(50, Math.max(18, (track.meters / 1000) * 2.4));
  const followPitch = chasePitch(track);
  const terrain = useMemo(() => terrainFor(terrainExaggeration(track)), [track]);
  // The camera follows a smoothed copy of the route (GPS jitter would otherwise shake it); the marker stays on the real fixes.
  const sigma = cameraSigma(track.meters, duration);
  const cam = useMemo(() => smoothPath(track, sigma), [track, sigma]);
  const reach = chaseWindow(sigma);
  const followZoom = Math.min(15.6, Math.max(12.6, 16.2 - Math.log2(Math.max(1, track.meters / 1000)) * 0.55));

  const lineColor = (m: Mode): ExpressionSpecification => {
    const stops = (m !== "plain" && gradients[m]?.stops) || [
      [0, LIME],
      [1, LIME],
    ];
    return ["interpolate", ["linear"], ["line-progress"], ...stops.flat()] as ExpressionSpecification;
  };

  const overview = (animate: boolean) => {
    const map = mapRef.current;
    if (!map) return;
    const tilt = live.current.is3d;
    map.fitBounds(track.bounds as LngLatBoundsLike, {
      padding: { top: 90, bottom: 70, left: 40, right: 56 },
      pitch: tilt ? PITCH_3D : 0,
      bearing: tilt ? -18 : 0,
      maxZoom: 16,
      duration: animate ? 1800 : 0,
    });
  };

  const decorate = (map: MapLibreMap) => {
    const { basemap: base, is3d: tilt, mode: m } = live.current;
    const dem = { type: "raster-dem" as const, tiles: [DEM_TILES], tileSize: 256, maxzoom: 14, encoding: "terrarium" as const };
    map.addSource("dem", { ...dem, attribution: DEM_ATTRIBUTION });
    map.addSource("dem-shade", dem);
    const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
    map.addLayer(
      {
        id: "relief",
        type: "hillshade",
        source: "dem-shade",
        paint: {
          "hillshade-exaggeration": base === "satellite" ? 0.15 : 0.4,
          "hillshade-shadow-color": "rgba(0,0,0,0.6)",
          "hillshade-highlight-color": "rgba(255,255,255,0.18)",
          "hillshade-accent-color": "rgba(0,0,0,0.25)",
        },
      },
      firstLabel,
    );
    map.addSource("route", { type: "geojson", data: line, lineMetrics: true });
    const join = { "line-join": "round", "line-cap": "round" } as const;
    const width = (lo: number, hi: number): ExpressionSpecification => ["interpolate", ["linear"], ["zoom"], 10, lo, 16, hi];
    const color = lineColor(m);
    map.addLayer({
      id: "route-casing",
      type: "line",
      source: "route",
      layout: join,
      paint: { "line-color": "#0b0b0c", "line-width": width(5, 11), "line-opacity": 0.75 },
    });
    map.addLayer({
      id: "route-glow",
      type: "line",
      source: "route",
      layout: join,
      paint: { "line-gradient": color, "line-width": width(10, 24), "line-blur": width(6, 14), "line-opacity": 0.45 },
    });
    map.addLayer({
      id: "route-line",
      type: "line",
      source: "route",
      layout: join,
      paint: { "line-gradient": color, "line-width": width(2.5, 6) },
    });
    if (!map.hasImage("km-badge")) map.addImage("km-badge", badge(), { pixelRatio: 2 });
    map.addSource("marks", { type: "geojson", data: marks });
    map.addLayer({
      id: "route-km",
      type: "symbol",
      source: "marks",
      layout: {
        "icon-image": "km-badge",
        "text-field": ["to-string", ["get", "km"]],
        "text-font": ["Noto Sans Bold"],
        "text-size": 10,
        "symbol-sort-key": ["get", "km"],
        "icon-padding": 4,
      },
      paint: { "text-color": "#f2e8cf" },
    });
    map.setSky(SKY);
    map.setTerrain(tilt ? terrain : null);
  };

  const place = (p: number) => {
    const here = sample(track, p);
    const head = headRef.current;
    if (head) {
      head.setLngLat([here.lon, here.lat]);
      (head.getElement().firstElementChild as HTMLElement).style.opacity = p > 0 ? "1" : "0";
    }
    return here;
  };

  const stop = () => {
    cancelAnimationFrame(rafRef.current);
    anim.current.last = 0;
    live.current.playing = false;
    setPlaying(false);
  };

  const step = (now: number) => {
    const map = mapRef.current;
    if (!map) return;
    const s = anim.current;
    const dt = s.last ? Math.min(0.1, (now - s.last) / 1000) : 0;
    s.last = now;
    s.p = Math.min(1, s.p + dt / duration);
    place(s.p);
    const tilt = live.current.is3d;
    if (tilt && s.p < 0.999) s.bearing = steer(s.bearing, chaseHeading(track, s.p, reach.ahead, reach.behind, cam), dt);
    const eye = cam(s.p);
    map.jumpTo({ center: [eye.lon, eye.lat], bearing: tilt ? s.bearing : 0, pitch: tilt ? followPitch : 0 });
    setProgress(s.p);
    if (s.p >= 1) {
      stop();
      overview(true);
      return;
    }
    rafRef.current = requestAnimationFrame(step);
  };

  const play = () => {
    const map = mapRef.current;
    if (!map) return;
    const s = anim.current;
    if (s.p >= 1) s.p = 0;
    place(s.p);
    const tilt = live.current.is3d;
    s.bearing = tilt ? chaseHeading(track, s.p, reach.ahead, reach.behind, cam) : 0;
    s.last = 0;
    live.current.playing = true;
    setPlaying(true);
    map.flyTo({
      center: [cam(s.p).lon, cam(s.p).lat],
      zoom: followZoom,
      pitch: tilt ? followPitch : 0,
      bearing: s.bearing,
      duration: 1800,
      essential: true,
    });
    map.once("moveend", () => {
      if (live.current.playing) rafRef.current = requestAnimationFrame(step);
    });
  };

  const seek = (p: number) => {
    anim.current.p = p;
    place(p);
    setProgress(p);
  };

  useEffect(() => {
    const box = boxRef.current;
    const wrap = wrapRef.current;
    if (!box || !wrap) return;
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
        container: box,
        style: STYLES[live.current.basemap],
        bounds: track.bounds as LngLatBoundsLike,
        fitBoundsOptions: { padding: 48 },
        maxPitch: 80,
        cooperativeGestures: true,
        attributionControl: { compact: true },
      });
    } catch {
      onFail();
      return;
    }
    mapRef.current = map;
    let styled = false;
    map.on("style.load", () => {
      styled = true;
      decorate(map);
    });
    map.on("error", (e) => {
      // Only a style that never loads is fatal; a missing tile or sprite just leaves a gap.
      if (!styled && !(e as { sourceId?: string }).sourceId) onFail();
    });
    map.once("load", () => overview(false));
    map.on("dragstart", (e) => {
      if (e.originalEvent && live.current.playing) stop();
    });

    // Touch screens pinch and twist natively; buttons there would only crowd the overlays.
    if (!matchMedia("(pointer: coarse)").matches) map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
    const fullscreen = new FullscreenControl({ container: wrap });
    map.addControl(fullscreen, "top-right");
    fullscreen.on("fullscreenstart", () => {
      setFull(true);
      map.cooperativeGestures.disable();
    });
    fullscreen.on("fullscreenend", () => {
      setFull(false);
      map.cooperativeGestures.enable();
    });

    const first = track.points[0];
    const last = track.points[track.points.length - 1];
    new Marker({ element: pin("h-5 w-5 rounded-full bg-coral shadow-[0_0_14px_#ff6a55] ring-[3px] ring-ink") })
      .setLngLat([last.lon, last.lat])
      .addTo(map);
    new Marker({ element: pin("h-5 w-5 rounded-full border-[4px] border-lime bg-ink shadow-[0_0_14px_#c8f560]") })
      .setLngLat([first.lon, first.lat])
      .addTo(map);
    const head = pin("h-6 w-6");
    head.innerHTML =
      '<div class="relative h-full w-full opacity-0 transition-opacity duration-300">' +
      '<span class="absolute inset-0 animate-ping rounded-full bg-lime/60"></span>' +
      '<span class="absolute inset-[5px] rounded-full bg-lime ring-2 ring-ink"></span></div>';
    headRef.current = new Marker({ element: head, opacityWhenCovered: "1" }).setLngLat([first.lon, first.lat]).addTo(map);

    return () => {
      cancelAnimationFrame(rafRef.current);
      live.current.playing = false;
      headRef.current = null;
      mapRef.current = null;
      map.remove();
    };
    // Rebuilt only for a different track; the other choices are applied by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track]);

  const shownBasemap = useRef(basemap);
  useEffect(() => {
    localStorage.setItem(BASEMAP_KEY, basemap);
    const map = mapRef.current;
    if (!map || shownBasemap.current === basemap) return;
    shownBasemap.current = basemap;
    map.setStyle(STYLES[basemap], { diff: false });
  }, [basemap]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("dem")) return;
    map.setTerrain(is3d ? terrain : null);
    if (!live.current.playing) overview(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [is3d]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getLayer("route-line")) return;
    const color = lineColor(mode);
    map.setPaintProperty("route-line", "line-gradient", color);
    map.setPaintProperty("route-glow", "line-gradient", color);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  const here = sample(track, progress);
  const g = mode === "plain" ? null : gradients[mode];
  const speedText = (v: number | null) =>
    v == null || v < 0.3 ? "—" : paced ? `${formatPace(1000 / v, 1000)} /km` : `${(v * 3.6).toFixed(1)} km/h`;
  const modeLabel: Record<Mode, string> = { speed: paced ? "Pace" : "Speed", hr: "HR", alt: "Elevation", plain: "Plain" };
  const legend = (v: number) =>
    mode === "speed" ? speedText(v).replace(" /km", "").replace(" km/h", "") : mode === "hr" ? `${Math.round(v)}` : `${Math.round(v)} m`;

  return (
    <div ref={wrapRef} className={clsx("bg-ink", full && "flex h-full w-full flex-col gap-4 p-4")}>
      <div className={clsx("relative overflow-hidden border border-line", full ? "min-h-0 flex-1" : "h-[440px] sm:h-[560px]")}>
        <div ref={boxRef} style={{ position: "absolute", inset: 0 }} aria-label="Route map" />
        <div className="pointer-events-none absolute top-3 left-3 z-10 flex flex-col items-start gap-2">
          <Pills label="Map style" options={BASEMAPS} value={basemap} onChange={setBasemap} />
          <Pills
            label="View"
            options={[
              { value: "2d", label: "2D" },
              { value: "3d", label: "3D terrain" },
            ]}
            value={is3d ? "3d" : "2d"}
            onChange={(v) => setIs3d(v === "3d")}
          />
          {modes.length > 0 && (
            <Pills
              label="Colour route by"
              options={[...modes, "plain" as const].map((m) => ({ value: m, label: modeLabel[m] }))}
              value={mode}
              onChange={setMode}
            />
          )}
          {g && (
            <div className="flex items-center gap-2 rounded-full border border-white/10 bg-ink/70 px-3 py-1 font-mono text-[10px] text-paper/80 backdrop-blur-md">
              <span>{legend(g.lo)}</span>
              <span
                className="h-1.5 w-20 rounded-full"
                style={{ background: `linear-gradient(90deg, ${(mode === "alt" ? RELIEF : HEAT).join(", ")})` }}
              />
              <span>{legend(g.hi)}</span>
            </div>
          )}
        </div>
      </div>

      <div className={clsx("flex items-center gap-4", !full && "mt-4")}>
        <button
          type="button"
          className="pop pop-lime grid h-11 w-11 shrink-0 place-items-center !p-0"
          onClick={() => (playing ? stop() : play())}
          aria-label={playing ? "Pause flyover" : "Play flyover"}
        >
          {playing ? <Pause size={18} /> : <Play size={18} />}
        </button>
        <Profile track={track} gradient={g} progress={progress} onSeek={seek} />
        <button
          type="button"
          className="pop pop-ghost grid h-11 w-11 shrink-0 place-items-center !p-0"
          onClick={() => {
            stop();
            overview(true);
          }}
          aria-label="Show whole route"
          title="Show whole route"
        >
          <Scan size={18} />
        </button>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-x-4 gap-y-3 sm:grid-cols-5">
        <Readout label="Time" value={here.t == null ? "—" : clock(here.t)} />
        <Readout label="Distance" value={`${((here.dist ?? progress * track.meters) / 1000).toFixed(2)} km`} />
        {gradients.speed && <Readout label={paced ? "Pace" : "Speed"} value={speedText(here.speed)} />}
        {gradients.hr && <Readout label="Heart rate" value={here.hr == null ? "—" : `${Math.round(here.hr)} bpm`} />}
        {gradients.alt && <Readout label="Elevation" value={here.alt == null ? "—" : `${Math.round(here.alt)} m`} />}
      </div>
    </div>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className="font-mono text-lg text-cream tabular-nums">{value}</p>
    </div>
  );
}

/** Elevation silhouette (or the colour channel when there's no altitude) doubling as the playback scrubber. */
function Profile({
  track,
  gradient: g,
  progress,
  onSeek,
}: {
  track: Track;
  gradient: Gradient | null;
  progress: number;
  onSeek: (p: number) => void;
}) {
  const id = useId();
  const path = useMemo(() => {
    const key: TrackKey | null = track.elevation ? "alt" : track.points.some((p) => p.speed != null) ? "speed" : null;
    if (!key) return null;
    const n = 240;
    const values = Array.from({ length: n }, (_, i) => sample(track, i / (n - 1))[key]);
    const present = values.filter((v): v is number => v != null);
    if (!present.length) return null;
    const lo = Math.min(...present);
    const span = Math.max(...present) - lo || 1;
    const pts = values.map((v, i) => `L${((i / (n - 1)) * 1000).toFixed(1)},${(100 - (((v ?? lo) - lo) / span) * 82 - 6).toFixed(1)}`);
    return `M0,100 ${pts.join(" ")} L1000,100 Z`;
  }, [track]);
  const stops = g ? g.stops.filter((_, i) => i % Math.ceil(g.stops.length / 40) === 0 || i === g.stops.length - 1) : null;
  return (
    <div className="relative h-12 min-w-0 flex-1 overflow-hidden border border-line bg-coal">
      <svg viewBox="0 0 1000 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" aria-hidden>
        <defs>
          <linearGradient id={id} x1="0" x2="1" y1="0" y2="0">
            {stops ? (
              stops.map(([at, color]) => <stop key={at} offset={at} stopColor={color} />)
            ) : (
              <stop offset={0} stopColor={LIME} />
            )}
          </linearGradient>
        </defs>
        {path ? (
          <path d={path} fill={`url(#${CSS.escape(id)})`} opacity={0.55} />
        ) : (
          <rect x={0} y={44} width={1000} height={12} fill={`url(#${CSS.escape(id)})`} opacity={0.55} />
        )}
        <rect x={0} y={0} width={progress * 1000} height={100} fill="#ecebe6" opacity={0.08} />
        <line x1={progress * 1000} x2={progress * 1000} y1={0} y2={100} stroke="#f2e8cf" strokeWidth={3} vectorEffect="non-scaling-stroke" />
      </svg>
      <input
        type="range"
        min={0}
        max={1000}
        value={Math.round(progress * 1000)}
        onChange={(e) => onSeek(Number(e.target.value) / 1000)}
        aria-label="Playback position"
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
      />
    </div>
  );
}

function Pills<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="pointer-events-auto flex rounded-full border border-white/10 bg-ink/70 p-0.5 shadow-lg backdrop-blur-md"
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={clsx(
              "rounded-full px-3 py-1 text-[11px] font-semibold tracking-wider uppercase transition-colors",
              active ? "bg-cream text-ink" : "text-paper/70 hover:text-paper",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
