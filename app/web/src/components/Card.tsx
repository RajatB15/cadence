import { clsx } from "clsx";
import type { ElementType, ReactNode } from "react";
import { withAlpha } from "../lib/color";

/** Soft light spilling from a card's top edge in a domain colour: the replacement for hard coloured top bars. */
export function AccentEdge({ color, strength = 0.2 }: { color: string; strength?: number }) {
  return (
    <>
      <span aria-hidden className="pointer-events-none absolute inset-x-6 top-0 z-[1] h-px" style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }} />
      <span aria-hidden className="pointer-events-none absolute inset-0" style={{ background: `radial-gradient(120% 70% at 50% -10%, ${withAlpha(color, strength)}, transparent 62%)` }} />
    </>
  );
}

/**
 * The one card anatomy: `.surface` (gradient fill, 1px rim, top highlight, ambient shadow), optional accent light
 * and consistent padding. Use `as` for sections/links; pass `interactive` for tappable cards (lift + press).
 */
export function Card({
  as: Tag = "section", accent, strength, interactive = false, pad = true, className, children, ...rest
}: {
  as?: ElementType; accent?: string; strength?: number; interactive?: boolean; pad?: boolean; className?: string; children: ReactNode; [k: string]: unknown;
}) {
  return (
    <Tag className={clsx("surface relative overflow-hidden", pad && "p-5 sm:p-7", interactive && "surface-hover press", className)} {...rest}>
      {accent && <AccentEdge color={accent} strength={strength} />}
      <div className="relative">{children}</div>
    </Tag>
  );
}
