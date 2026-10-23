import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

interface Props {
  value: number;
  format: (value: number) => string;
  className?: string;
  duration?: number;
  /** Start right away instead of waiting to scroll into view (for above-the-fold numbers). */
  immediate?: boolean;
}

/** Counts up when first scrolled into view, then animates between values; instant when motion is reduced. */
export function CountUp({ value, format, className, duration = 1.1, immediate = false }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const from = useRef(0);
  const reduce = useReducedMotion();
  const seen = useInView(ref, { once: true, amount: 0.4 });
  const inView = immediate || seen;

  useEffect(() => {
    const node = ref.current;
    if (!node || !inView) return;
    if (reduce) {
      node.textContent = format(value);
      from.current = value;
      return;
    }
    const controls = animate(from.current, value, {
      duration,
      ease: [0.2, 0.9, 0.1, 1],
      onUpdate: (v) => (node.textContent = format(v)),
    });
    from.current = value;
    return () => controls.stop();
  }, [value, format, reduce, inView, duration]);

  return (
    <span ref={ref} className={className}>
      {format(reduce ? value : 0)}
    </span>
  );
}
