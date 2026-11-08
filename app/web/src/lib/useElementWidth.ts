import { useLayoutEffect, useState, type RefObject } from "react";

/** Live content-box width of an element (px), starting from `initial` so the first paint is already close. */
export function useElementWidth(ref: RefObject<HTMLElement | null>, initial: number): number {
  const [w, setW] = useState(initial);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const read = () => setW((prev) => { const next = node.getBoundingClientRect().width || initial; return Math.abs(next - prev) < 0.5 ? prev : next; });
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(node);
    return () => ro.disconnect();
  }, [ref, initial]);
  return w;
}
