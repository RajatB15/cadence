import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

/** Styled replacement for window.confirm: works in standalone PWAs, is keyboard and screen-reader friendly. */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Delete",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: ReactNode;
  body?: ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onCancel()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-ink/70 backdrop-blur-sm" />
        <Dialog.Content
          role="alertdialog"
          aria-describedby={body ? "confirm-body" : undefined}
          className="fixed top-1/2 left-1/2 z-[60] w-[min(420px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 border border-line-strong bg-coal p-6"
        >
          <Dialog.Title className="font-display text-2xl text-cream">{title}</Dialog.Title>
          {body && (
            <Dialog.Description id="confirm-body" className="mt-2 text-sm text-mute">
              {body}
            </Dialog.Description>
          )}
          <div className="mt-6 flex justify-end gap-3">
            <button type="button" className="pop pop-ghost" onClick={onCancel}>
              Cancel
            </button>
            <button type="button" className="pop pop-coral" onClick={onConfirm}>
              {confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
