import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { AnimatePresence, motion, useDragControls } from "motion/react";
import type { ReactNode } from "react";
import { useKeyboardInset } from "../lib/keyboard";

const wide = () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches;

/** Detail drawer: slides up from the bottom on phones, in from the right on wider screens. */
export function Sheet({
  open,
  onOpenChange,
  title,
  eyebrow,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  eyebrow?: ReactNode;
  children: ReactNode;
}) {
  const controls = useDragControls();
  const { inset, visibleHeight } = useKeyboardInset(open && !wide());
  // With the phone keyboard open, lift the sheet above it and keep it within the visible area so nothing hides behind the keys.
  const lifted = inset > 0 && visibleHeight != null ? { bottom: inset, maxHeight: visibleHeight - 8 } : undefined;
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <motion.div
                className="fixed inset-0 z-50 bg-black/55 backdrop-blur-[3px]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              />
            </Dialog.Overlay>
            <Dialog.Content asChild forceMount aria-describedby={undefined}>
              <motion.div
                style={lifted}
                className="surface-raised fixed inset-x-0 bottom-0 z-50 max-h-[90dvh] overflow-y-auto rounded-t-[var(--radius-sheet)] border border-b-0 border-[var(--rim-top)] bg-coal pb-[env(safe-area-inset-bottom)] shadow-[0_-24px_60px_-20px_rgb(0_0_0/0.7)] md:inset-y-0 md:right-0 md:left-auto md:max-h-none md:w-[min(560px,92vw)] md:rounded-l-[var(--radius-sheet)] md:rounded-tr-none md:border-b md:border-r-0"
                drag={wide() ? false : "y"}
                dragConstraints={{ top: 0, bottom: 0 }}
                dragElastic={{ top: 0, bottom: 0.6 }}
                dragListener={false}
                dragControls={controls}
                onDragEnd={(_, info) => { if (info.offset.y > 120 || info.velocity.y > 600) onOpenChange(false); }}
                initial={wide() ? { x: "100%" } : { y: "100%" }}
                animate={{ y: 0, x: 0 }}
                exit={wide() ? { x: "100%" } : { y: "100%" }}
                transition={{ type: "spring", stiffness: 340, damping: 34, mass: 0.9 }}
              >
                <div
                  className="sticky top-0 z-10 flex touch-none items-start justify-between gap-4 border-b border-line bg-coal/90 px-6 pt-7 pb-4 backdrop-blur-xl md:touch-auto md:py-5"
                  onPointerDown={(e) => { if (!wide()) controls.start(e); }}
                >
                  <div className="absolute top-2.5 left-1/2 h-1 w-10 -translate-x-1/2 rounded-full bg-line-strong md:hidden" aria-hidden />
                  <div>
                    {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
                    <Dialog.Title className="text-[28px] leading-tight font-extrabold tracking-tight text-cream">{title}</Dialog.Title>
                  </div>
                  <Dialog.Close className="press grid h-11 w-11 shrink-0 place-items-center rounded-full border border-line bg-slate/60 text-mute hover:text-paper" aria-label="Close">
                    <X size={16} />
                  </Dialog.Close>
                </div>
                <div className="p-6">{children}</div>
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
