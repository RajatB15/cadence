import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
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
                className="fixed inset-0 z-50 bg-ink/70 backdrop-blur-sm"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              />
            </Dialog.Overlay>
            <Dialog.Content asChild forceMount aria-describedby={undefined}>
              <motion.div
                style={lifted}
                className="fixed inset-x-0 bottom-0 z-50 max-h-[88dvh] overflow-y-auto border-t border-line-strong bg-coal pb-[env(safe-area-inset-bottom)] md:inset-y-0 md:right-0 md:left-auto md:max-h-none md:w-[min(560px,92vw)] md:border-t-0 md:border-l"
                initial={wide() ? { x: "100%" } : { y: "100%" }}
                animate={{ y: 0, x: 0 }}
                exit={wide() ? { x: "100%" } : { y: "100%" }}
                transition={{ type: "spring", stiffness: 260, damping: 32 }}
              >
                <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-line bg-coal/95 px-6 py-5 backdrop-blur">
                  <div>
                    {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
                    <Dialog.Title className="font-display text-3xl text-cream">{title}</Dialog.Title>
                  </div>
                  <Dialog.Close className="grid h-9 w-9 shrink-0 place-items-center border border-line text-mute hover:text-paper" aria-label="Close">
                    <X size={16} />
                  </Dialog.Close>
                </div>
                <div className="p-6">{children}</div>
                <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-line-strong md:hidden" aria-hidden />
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
