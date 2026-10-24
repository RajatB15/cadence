import { Download, Share2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
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
type Backdrop = "dark" | "transparent";

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

  const make = async (): Promise<File> => {
    if (video) {
      abort.current = new AbortController();
      const blob = await renderVideo(model, speed, setBusy, abort.current.signal);
      return new File([blob], fileName(model, "mp4", false), { type: "video/mp4" });
    }
    const blob = await renderPng(model, transparent);
    return new File([blob], fileName(model, "png", transparent), { type: "image/png" });
  };

  const run = async (how: "share" | "save") => {
    setError(null);
    setBusy(0);
    try {
      const file = await make();
      if (how === "share" && navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: model.title });
      } else {
        const url = URL.createObjectURL(file);
        const a = Object.assign(document.createElement("a"), { href: url, download: file.name });
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 10_000);
      }
    } catch (e) {
      const err = e as Error;
      if (err.name !== "AbortError") setError(err.message || "Couldn't create the file.");
    } finally {
      setBusy(null);
      abort.current = null;
    }
  };

  const canShareFiles = typeof navigator !== "undefined" && typeof navigator.canShare === "function";
  const videoBlocked = hasRoute && videoOk === false;

  return (
    <div className="space-y-6">
      <Preview model={model} transparent={transparent} />

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
            ]}
            value={backdrop}
            onChange={setBackdrop}
          />
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
          <p className="text-xs text-dim">
            {videoSeconds(speed).toFixed(1)} s of route drawing, then a short hold. MP4 can't carry transparency, so video keeps the
            dark backdrop.
          </p>
          {videoBlocked && <p className="text-sm text-coral">This browser can't encode video. Try Safari 16.4+ or a current Chrome.</p>}
        </div>
      )}

      {busy != null && video && (
        <div className="h-1.5 bg-line" role="progressbar" aria-valuenow={Math.round(busy * 100)} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-lime transition-[width]" style={{ width: `${Math.max(3, busy * 100)}%` }} />
        </div>
      )}
      {error && <p className="text-sm text-coral">{error}</p>}

      <div className="flex flex-wrap gap-3">
        {canShareFiles && (
          <button type="button" className="pop pop-lime inline-flex items-center gap-2" disabled={busy != null || (video && videoOk !== true)} onClick={() => run("share")}>
            <Share2 size={14} /> {busy != null ? (video ? "Rendering…" : "Preparing…") : "Share"}
          </button>
        )}
        <button
          type="button"
          className={canShareFiles ? "pop pop-ghost inline-flex items-center gap-2" : "pop pop-lime inline-flex items-center gap-2"}
          disabled={busy != null || (video && videoOk !== true)}
          onClick={() => run("save")}
        >
          <Download size={14} /> {video ? "Save MP4" : "Save PNG"}
        </button>
        {busy != null && video && (
          <button type="button" className="pop pop-ghost" onClick={() => abort.current?.abort()}>
            Cancel
          </button>
        )}
      </div>
      <p className="text-xs text-dim">Made on this device from your own activity. Nothing is uploaded.</p>
    </div>
  );
}

function Preview({ model, transparent }: { model: CardModel; transparent: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const stable = useMemo(() => model, [model]);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let alive = true;
    const paint = () => alive && drawCard(canvas.getContext("2d")!, stable, { transparent, progress: 1 });
    paint();
    // The card fonts may still be loading on first open; repaint once they are.
    document.fonts?.ready.then(paint);
    return () => {
      alive = false;
    };
  }, [stable, transparent]);
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
