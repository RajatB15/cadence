import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Pure: show the condensed bar once the large title has scrolled fully above the viewport top. */
export function isCondensed(bottom: number, topInset = 0): boolean {
  return bottom < topInset + 8;
}

/**
 * Wraps a page's large title. When it scrolls away, a slim glass bar with the short title fades in at the top
 * (Apple-style large title that condenses). `title` is the short text; non-string titles produce no bar.
 */
export function CondensedTitle({ title, children }: { title: ReactNode; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [condensed, setCondensed] = useState(false);
  const text = typeof title === "string" ? title.replace(/[.]$/, "") : null;

  useEffect(() => {
    const node = ref.current;
    if (!node || !text || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      ([entry]) => setCondensed(!entry.isIntersecting && isCondensed(entry.boundingClientRect.bottom)),
      { threshold: [0, 1] },
    );
    io.observe(node);
    return () => io.disconnect();
  }, [text]);

  return (
    <div ref={ref}>
      {children}
      {text && typeof document !== "undefined" &&
        createPortal(
          <AnimatePresence>
            {condensed && (
              <motion.div
                aria-hidden
                initial={{ opacity: 0, y: -12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                className="surface-glass fixed inset-x-0 top-0 z-30 flex h-[calc(48px+env(safe-area-inset-top))] items-end justify-center rounded-none border-x-0 border-t-0 pb-3 md:left-24"
              >
                <span className="text-[15px] font-extrabold tracking-tight text-cream">{text}</span>
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )}
    </div>
  );
}
