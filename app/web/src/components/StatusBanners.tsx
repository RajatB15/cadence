import { WifiOff, RefreshCw } from "lucide-react";
import { useOnline } from "../lib/online";
import { useUpdateReady } from "../lib/useAppLifecycle";

/** Offline notice (data shown may be the last saved copy) and the "new version" prompt. */
export function StatusBanners() {
  const online = useOnline();
  const update = useUpdateReady();
  if (online && !update) return null;
  return (
    <div className="mb-6 flex flex-col gap-2">
      {!online && (
        <div role="status" className="surface flex items-center gap-3 border-l-2 border-amber/50 px-4 py-3 text-sm text-amber">
          <WifiOff size={16} aria-hidden />
          <p className="min-w-0 flex-1 text-paper">
            You're offline. Showing the last saved data; changes can't be saved until you reconnect.
          </p>
        </div>
      )}
      {update && (
        <div role="status" className="surface flex items-center gap-3 border-l-2 border-gold/40 px-4 py-3 text-sm text-gold">
          <RefreshCw size={16} aria-hidden />
          <p className="min-w-0 flex-1 text-paper">A new version of Cadence is ready.</p>
          <button type="button" className="eyebrow min-h-11 px-2 !text-current hover:underline" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )}
    </div>
  );
}
