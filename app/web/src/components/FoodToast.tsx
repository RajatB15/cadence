import { useCallback, useEffect, useRef, useState } from "react";

export interface ToastState {
  message: string;
  action?: { label: string; run: () => void };
  /** Errors stay until dismissed. */
  tone?: "ok" | "error";
}

/** One toast at a time; auto-dismisses after 6 s (never for errors). Announced politely, no motion needed. */
export function useToast() {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const dismiss = useCallback(() => {
    clearTimeout(timer.current);
    setToast(null);
  }, []);
  const show = useCallback((t: ToastState) => {
    clearTimeout(timer.current);
    setToast(t);
    if (t.tone !== "error") timer.current = setTimeout(() => setToast(null), 6000);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  return { toast, show, dismiss };
}

export function Toast({ toast, onDismiss }: { toast: ToastState | null; onDismiss: () => void }) {
  return (
    <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-4 bottom-24 z-[60] flex justify-center md:bottom-8">
      {toast && (
        <div className="surface-raised pointer-events-auto flex min-h-11 max-w-md items-center gap-3 rounded-full border border-line-strong bg-coal py-1.5 pr-1.5 pl-5 shadow-[var(--shadow-float)]">
          <span className={`min-w-0 text-sm ${toast.tone === "error" ? "text-coral" : "text-paper"}`}>{toast.message}</span>
          {toast.action && (
            <button type="button" className="press min-h-11 shrink-0 rounded-full px-4 text-sm font-bold text-gold" onClick={() => { toast.action!.run(); onDismiss(); }}>
              {toast.action.label}
            </button>
          )}
          <button type="button" className="press grid h-11 w-11 shrink-0 place-items-center rounded-full text-mute hover:text-paper" aria-label="Dismiss" onClick={onDismiss}>×</button>
        </div>
      )}
    </div>
  );
}
