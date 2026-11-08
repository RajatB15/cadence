import { AnimatePresence, motion } from "motion/react";
import { edge } from "../lib/color";
import { EASE } from "../lib/motion";
import { C } from "../lib/theme";
import { WifiOff, RefreshCw } from "lucide-react";
import { useOnline } from "../lib/online";
import { useUpdateReady } from "../lib/useAppLifecycle";

/** Offline notice (data shown may be the last saved copy) and the "new version" prompt. */
export function StatusBanners() {
  const online = useOnline();
  const update = useUpdateReady();
  const pop = { initial: { opacity: 0, y: -10 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -8 }, transition: { duration: 0.3, ease: EASE.outExpo } };
  return (
    <AnimatePresence initial={false}>
      {(!online || update) && (
    <motion.div key="banners" {...pop} className="mb-6 flex flex-col gap-2">
      {!online && (
        <div role="status" className="surface edge flex items-center gap-3 px-4 py-3 text-sm text-amber" style={edge(C.amber)}>
          <WifiOff size={16} aria-hidden />
          <p className="min-w-0 flex-1 text-paper">
            You're offline. Showing the last saved data; changes can't be saved until you reconnect.
          </p>
        </div>
      )}
      {update && (
        <div role="status" className="surface edge flex items-center gap-3 px-4 py-3 text-sm text-gold" style={edge(C.gold)}>
          <RefreshCw size={16} aria-hidden />
          <p className="min-w-0 flex-1 text-paper">A new version of Cadence is ready.</p>
          <button type="button" className="eyebrow min-h-11 px-2 !text-current hover:underline" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )}
    </motion.div>
      )}
    </AnimatePresence>
  );
}
