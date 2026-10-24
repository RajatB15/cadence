import { MoreHorizontal } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

export interface MoreItem {
  label: ReactNode;
  onSelect: () => void;
  hint?: string;
}

/** A three-dot menu for the occasional actions that shouldn't crowd a page. Closes on outside click, Escape or choosing. */
export function MoreMenu({ items, label = "More actions" }: { items: MoreItem[]; label?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  if (!items.length) return null;
  return (
    <div ref={root} className="relative">
      <button type="button" aria-label={label} aria-haspopup="menu" aria-expanded={open} className="pop pop-ghost !px-3" onClick={() => setOpen(!open)}>
        <MoreHorizontal size={16} />
      </button>
      {open && (
        <ul role="menu" className="surface absolute right-0 z-30 mt-2 w-64 max-w-[85vw] divide-y divide-line border-line-strong bg-coal py-1 shadow-xl">
          {items.map((it, i) => (
            <li key={i} role="none">
              <button
                type="button"
                role="menuitem"
                className="block w-full px-4 py-3 text-left text-sm text-paper hover:bg-slate/60"
                onClick={() => {
                  setOpen(false);
                  it.onSelect();
                }}
              >
                {it.label}
                {it.hint && <span className="mt-0.5 block text-xs text-dim">{it.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
