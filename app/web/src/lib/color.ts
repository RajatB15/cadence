/** `#rrggbb` plus alpha as an rgba() string; other formats (rgb(), var()) pass through unchanged. */
export function withAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(color);
  if (!m) return color;
  const n = parseInt(m[1], 16);
  const a = Math.max(0, Math.min(1, alpha));
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Inline style for the `.edge` class: soft domain-coloured light from a card's top edge (replaces hard coloured left borders). */
export function edge(color: string): import("react").CSSProperties {
  return { ["--edge" as string]: color } as import("react").CSSProperties;
}
