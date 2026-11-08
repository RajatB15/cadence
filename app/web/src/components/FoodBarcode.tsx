import { useQueryClient } from "@tanstack/react-query";
import { Camera, ScanLine } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../lib/api";
import { validBarcode } from "../lib/foodBarcode";
import { rowsFromChip } from "../lib/foodChips";
import type { FoodRow, RowDish } from "../lib/foodRow";
import type { FoodDish } from "../lib/types";
import { Sheet } from "./Sheet";

interface Detector {
  detect: (src: CanvasImageSource) => Promise<{ rawValue: string }[]>;
}
type DetectorCtor = new (opts?: { formats?: string[] }) => Detector;
const detectorCtor = (): DetectorCtor | null => (typeof window !== "undefined" && "BarcodeDetector" in window ? ((window as unknown as { BarcodeDetector: DetectorCtor }).BarcodeDetector) : null);

type Result = { kind: "found"; dish: FoodDish } | { kind: "missing" } | { kind: "unsupported" } | { kind: "error"; message: string };

/**
 * Barcode to one of your own products. Resolution happens only on this server against products you saved (nothing is sent to any
 * outside service). The camera needs BarcodeDetector and a secure connection; otherwise the code is typed.
 */
export function BarcodeSheet({
  open, onClose, dishById, onAdd, onReadLabel,
}: {
  open: boolean;
  onClose: () => void;
  dishById: Map<number, RowDish> | null;
  onAdd: (rows: FoodRow[]) => void;
  /** Open the label reader with this code pre-filled so saving stores the barcode. */
  onReadLabel: (code: string) => void;
}) {
  const client = useQueryClient();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [camera, setCamera] = useState<"off" | "on" | "blocked">("off");
  const video = useRef<HTMLVideoElement>(null);
  const Detector = detectorCtor();
  const secure = typeof window === "undefined" || window.isSecureContext;
  const canScan = !!Detector && secure && typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  const lookup = async (c: string) => {
    if (!validBarcode(c)) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await api.foodBarcode(c);
      setResult(r.found ? { kind: "found", dish: r.dish } : { kind: "missing" });
    } catch (e) {
      setResult(e instanceof ApiError && (e.status === 404 || e.status === 405) ? { kind: "unsupported" } : { kind: "error", message: e instanceof Error ? e.message : "Couldn't look that up." });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!open) {
      setCode("");
      setResult(null);
      setCamera("off");
    }
  }, [open]);

  useEffect(() => {
    if (camera !== "on" || !Detector) return;
    let stream: MediaStream | undefined;
    let timer: ReturnType<typeof setInterval> | undefined;
    let dead = false;
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        if (dead) return s.getTracks().forEach((t) => t.stop());
        stream = s;
        const v = video.current;
        if (!v) return;
        v.srcObject = s;
        void v.play().catch(() => undefined);
        const det = new Detector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e", "code_128"] });
        timer = setInterval(() => {
          det.detect(v).then((found) => {
            const hit = found.map((f) => f.rawValue).find(validBarcode);
            if (hit && !dead) {
              dead = true;
              setCode(hit);
              setCamera("off");
              void lookup(hit);
            }
          }).catch(() => undefined);
        }, 300);
      })
      .catch(() => setCamera("blocked"));
    return () => {
      dead = true;
      clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void lookup(code.trim());
  };

  const found = result?.kind === "found" ? result.dish : null;
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()} eyebrow="Packaged food" title="Barcode">
      <div className="space-y-4">
        <p className="text-sm text-mute">Finds products you saved before. Nothing is sent outside your Cadence server.</p>
        {canScan ? (
          camera === "on" ? (
            <div className="space-y-2">
              <video ref={video} playsInline muted className="aspect-[4/3] w-full rounded-2xl border border-line bg-ink object-cover" aria-label="Camera view" />
              <button type="button" className="chip press min-h-11" onClick={() => setCamera("off")}>Stop camera</button>
            </div>
          ) : (
            <button type="button" className="pop pop-lime !min-h-12" onClick={() => setCamera("on")}><Camera size={16} /> Scan with camera</button>
          )
        ) : (
          <p className="text-sm text-mute">{!secure ? "Camera isn't available on this connection. Type the code instead." : "This browser can't read barcodes with the camera. Type the code instead."}</p>
        )}
        {camera === "blocked" && <p role="alert" className="text-sm text-amber">Camera blocked. You can type the code.</p>}
        <form onSubmit={submit} className="space-y-2">
          <label className="eyebrow block" htmlFor="barcode-code">{canScan ? "Or type the barcode" : "Type the barcode"}</label>
          <div className="flex gap-2">
            <input id="barcode-code" inputMode="numeric" autoComplete="off" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 14))} placeholder="6 to 14 digits" className="num min-h-11 min-w-0 flex-1 rounded-lg border border-line-strong bg-slate/50 px-3 text-lg text-paper" />
            <button type="submit" className="pop pop-ghost !min-h-11 disabled:opacity-40" disabled={!validBarcode(code) || busy}><ScanLine size={16} /> {busy ? "Looking…" : "Find"}</button>
          </div>
        </form>
        <div aria-live="polite" className="space-y-3">
          {found && (
            <div className="surface p-4">
              <p className="text-sm font-bold text-cream">{found.name}</p>
              <p className="text-xs text-mute">Your saved product · per {found.unit}</p>
              <button type="button" className="pop pop-lime mt-3 !min-h-11" onClick={() => { const rows = dishById ? rowsFromChip({ key: "scan", kind: "scan", label: found.name, items: [{ dishId: found.id, name: found.name, servings: 1 }] }, new Map([...dishById, [found.id, found]])) : []; onAdd(rows); onClose(); }}>
                Add to my meal
              </button>
            </div>
          )}
          {result?.kind === "missing" && (
            <div className="space-y-2">
              <p className="text-sm text-mute">No product with this code in your own products yet. Read the label and save it, and the next scan is one tap.</p>
              <button type="button" className="pop pop-ghost !min-h-11" onClick={() => { client.invalidateQueries({ queryKey: ["food-dishes"] }); onReadLabel(code); }}><Camera size={16} /> Read the label</button>
            </div>
          )}
          {result?.kind === "unsupported" && <p className="text-sm text-mute">Barcode lookup isn't available on this server yet. You can still read the label.</p>}
          {result?.kind === "error" && <p role="alert" className="text-sm text-coral">{result.message}</p>}
        </div>
      </div>
    </Sheet>
  );
}
