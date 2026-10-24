import { Download, ImageUp, Share2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { BASEMAPS, type Basemap } from "../lib/mapStyle";
import { Segmented } from "./Shell";
import { Sheet } from "./Sheet";
import {
  CARD_H,
  CARD_W,
  VIDEO_SPEEDS,
  canRenderVideo,
  drawCard,
  fileName,
  renderPng,
  renderVideo,
  videoSeconds,
  type CardModel,
  type VideoSpeed,
} from "../lib/shareCard";

type Kind = "image" | "video";
type Backdrop = "dark" | "transparent" | "photo";

/** Share button + sheet: a still card (opaque or transparent PNG) and, with GPS, a route video at 1x–2x. */
export function ShareCardButton({ model }: { model: CardModel }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="pop pop-ghost inline-flex items-center gap-2" onClick={() => setOpen(true)}>
        <Share2 size={14} /> Share
      </button>
      <Sheet open={open} onOpenChange={setOpen} eyebrow="Share" title="Activity card">
        <ShareBody model={model} />
      </Sheet>
    </>
  );
}

function ShareBody({ model }: { model: CardModel }) {
  const hasRoute = !!model.track;
  const [kind, setKind] = useState<Kind>("image");
  const [backdrop, setBackdrop] = useState<Backdrop>("dark");
  const [speed, setSpeed] = useState<VideoSpeed>(1);
  const [basemap, setBasemap] = useState<Basemap>("dark");
  const [photo, setPhoto] = useState<ImageBitmap | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [videoOk, setVideoOk] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    let alive = true;
    if (hasRoute) canRenderVideo().then((ok) => alive && setVideoOk(ok));
    return () => {
      alive = false;
      abort.current?.abort();
    };
  }, [hasRoute]);

  const video = kind === "video";
  const transparent = !video && backdrop === "transparent";
  const shownPhoto = !video && backdrop === "photo" ? photo : null;

  const pickPhoto = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      const bitmap = await createImageBitmap(file);
      setPhoto((old) => {
        old?.close();
        return bitmap;
      });
      setBackdrop("photo");
    } catch {
      setError("That file couldn't be read as a picture. Try a JPEG or PNG.");
    }
  };

  // The file is made first and shared from a fresh tap: browsers (iOS especially) refuse navigator.share() once the tap that
  // asked for it is old, which a minute-long video render always is.
  const [ready, setReady] = useState<File | null>(null);
  useEffect(() => {
    setReady(null);
    setError(null);
    if (video) return;
    let stale = false;
    renderPng(model, transparent, shownPhoto).then(
      (blob) => !stale && setReady(new File([blob], fileName(model, "png", transparent), { type: "image/png" })),
      (e: Error) => !stale && setError(e.message),
    );
    return () => {
      stale = true;
    };
  }, [model, video, transparent, shownPhoto]);
  useEffect(() => {
    setReady(null);
  }, [speed, basemap]);

  const renderNow = async () => {
    setError(null);
    setBusy(0);
    abort.current = new AbortController();
    try {
      const blob = await renderVideo(model, { speed, basemap, onProgress: setBusy, signal: abort.current.signal });
      setReady(new File([blob], fileName(model, "mp4", false), { type: "video/mp4" }));
    } catch (e) {
      const err = e as Error;
      if (err.name !== "AbortError") setError(err.message || "Couldn't render the video.");
    } finally {
      setBusy(null);
      abort.current = null;
    }
  };

  const share = async () => {
    if (!ready) return;
    setError(null);
    try {
      await navigator.share({ files: [ready], title: model.title });
    } catch (e) {
      const err = e as Error;
      if (err.name !== "AbortError") setError(`Sharing didn't work (${err.name}: ${err.message || "no details"}). Use Save and share the file from your gallery or Files.`);
    }
  };

  const save = () => {
    if (!ready) return;
    const url = URL.createObjectURL(ready);
    Object.assign(document.createElement("a"), { href: url, download: ready.name }).click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };

  const canShareFiles = !!ready && typeof navigator.canShare === "function" && navigator.canShare({ files: [ready] });
  const videoBlocked = hasRoute && videoOk === false;

  return (
    <div className="space-y-6">
      <Preview model={model} transparent={transparent} photo={shownPhoto} />

      {hasRoute && (
        <Segmented
          label="Format"
          options={[
            { value: "image" as Kind, label: "Image" },
            { value: "video" as Kind, label: "Video" },
          ]}
          value={kind}
          onChange={setKind}
        />
      )}

      {!video && (
        <div className="space-y-2">
          <p className="eyebrow">Background</p>
          <Segmented
            label="Background"
            options={[
              { value: "dark" as Backdrop, label: "Dark" },
              { value: "transparent" as Backdrop, label: "Transparent" },
              { value: "photo" as Backdrop, label: "Photo" },
            ]}
            value={backdrop}
            onChange={(v) => (v === "photo" && !photo ? fileInput.current?.click() : setBackdrop(v))}
          />
          <input ref={fileInput} type="file" accept="image/*" className="hidden" onChange={(e) => { pickPhoto(e.target.files?.[0]); e.target.value = ""; }} />
          {backdrop === "photo" && (
            <button type="button" className="pop pop-ghost inline-flex items-center gap-2" onClick={() => fileInput.current?.click()}>
              <ImageUp size={14} /> {photo ? "Choose a different photo" : "Choose a photo"}
            </button>
          )}
          {backdrop === "photo" && <p className="text-xs text-dim">Picked from your gallery and used only in this window. It is cropped to fill and dimmed so the text reads.</p>}
          {transparent && <p className="text-xs text-dim">A PNG with no backdrop, to lay over a photo or story in another app.</p>}
        </div>
      )}

      {video && (
        <div className="space-y-2">
          <p className="eyebrow">Speed</p>
          <Segmented
            label="Video speed"
            options={VIDEO_SPEEDS.map((s) => ({ value: s, label: `${s}x` }))}
            value={speed}
            onChange={setSpeed}
          />
          <p className="eyebrow pt-2">Map</p>
          <Segmented label="Map style" options={BASEMAPS} value={basemap} onChange={setBasemap} />
          <p className="text-xs text-dim">
            A 3D terrain flyover that follows you along the route: {videoSeconds(speed).toFixed(1)} s of travel plus a short intro and
            closing view. Rendering waits for map tiles frame by frame, so it takes about a minute: keep this window open. MP4 can't carry
            transparency.
          </p>
          {videoBlocked && <p className="text-sm text-coral">This browser can't render 3D video (it needs WebGL 2 and the WebCodecs video encoder). Try Safari 16.4+ or a current Chrome.</p>}
        </div>
      )}

      {busy != null && (
        <div className="h-1.5 bg-line" role="progressbar" aria-valuenow={Math.round(busy * 100)} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-lime transition-[width]" style={{ width: `${Math.max(3, busy * 100)}%` }} />
        </div>
      )}
      {error && <p className="text-sm text-coral">{error}</p>}

      <div className="flex flex-wrap gap-3">
        {video && !ready && (
          <button type="button" className="pop pop-lime inline-flex items-center gap-2" disabled={busy != null || videoOk !== true} onClick={renderNow}>
            {busy != null ? "Rendering…" : "Render video"}
          </button>
        )}
        {video && busy != null && (
          <button type="button" className="pop pop-ghost" onClick={() => abort.current?.abort()}>
            Cancel
          </button>
        )}
        {(!video || ready) && (
          <>
            {(canShareFiles || !ready) && (
              <button type="button" className="pop pop-lime inline-flex items-center gap-2" disabled={!canShareFiles} onClick={share}>
                <Share2 size={14} /> Share
              </button>
            )}
            <button
              type="button"
              className={canShareFiles ? "pop pop-ghost inline-flex items-center gap-2" : "pop pop-lime inline-flex items-center gap-2"}
              disabled={!ready}
              onClick={save}
            >
              <Download size={14} /> {video ? "Save MP4" : "Save PNG"}
            </button>
          </>
        )}
      </div>
      {video && ready && <p className="text-xs text-dim">Video ready ({(ready.size / 1e6).toFixed(1)} MB). Changing the speed or map renders a new one.</p>}
      <p className="text-xs text-dim">Made on this device from your own activity; nothing is uploaded. {video ? "Video fetches map tiles for the area, the same as the Route map." : ""}</p>
    </div>
  );
}

function Preview({ model, transparent, photo }: { model: CardModel; transparent: boolean; photo: ImageBitmap | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const stable = useMemo(() => model, [model]);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let alive = true;
    const paint = () => alive && drawCard(canvas.getContext("2d")!, stable, { transparent, progress: 1, photo });
    paint();
    // The card fonts may still be loading on first open; repaint once they are.
    document.fonts?.ready.then(paint);
    return () => {
      alive = false;
    };
  }, [stable, transparent, photo]);
  return (
    <div
      className="mx-auto w-full max-w-[280px] overflow-hidden border border-line"
      style={
        transparent
          ? { backgroundImage: "repeating-conic-gradient(#2a2a2e 0% 25%, #3a3a40 0% 50%)", backgroundSize: "20px 20px" }
          : undefined
      }
    >
      <canvas ref={ref} width={CARD_W} height={CARD_H} className="block h-auto w-full" aria-label="Card preview" />
    </div>
  );
}
