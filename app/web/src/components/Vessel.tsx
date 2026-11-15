import { useReducedMotion } from "motion/react";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

/** A big numeral drawn as a glass that fills to `fill` (0 to 1) when it appears. The number is ordinary text; the fill is decoration. */
export function Vessel({ fill, color, className, children }: { fill: number; color: string; className?: string; children: ReactNode }) {
  const reduce = useReducedMotion();
  const target = Math.max(0, Math.min(1, Number.isFinite(fill) ? fill : 0));
  const [f, setF] = useState(reduce ? target : 0);
  useEffect(() => {
    if (reduce) { setF(target); return; }
    const t = requestAnimationFrame(() => setF(target));
    return () => cancelAnimationFrame(t);
  }, [target, reduce]);
  return <span className={`vessel ${className ?? ""}`} style={{ "--fill": f, "--c": color } as CSSProperties}>{children}</span>;
}
