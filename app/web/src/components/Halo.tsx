import { Check } from "lucide-react";
import { C } from "../lib/theme";

/** A small check badge whose ring breathes out once (the `.ring-halo` keyframes): the one celebration for a goal met. No confetti. */
export function CheckHalo({ size = 22, color = C.lime }: { size?: number; color?: string }) {
  return (
    <span aria-hidden className="relative inline-grid shrink-0 place-items-center overflow-visible" style={{ width: size, height: size, color }}>
      <svg viewBox="0 0 24 24" className="absolute inset-0 h-full w-full overflow-visible">
        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.5" />
        <circle className="ring-halo" cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="3" style={{ transformOrigin: "12px 12px", opacity: 0 }} />
      </svg>
      <Check size={size * 0.55} strokeWidth={3} className="relative" />
    </span>
  );
}
