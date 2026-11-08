/**
 * Sizing for the text in the middle of a ring gauge. The hole inside the innermost stroke is a circle, so a block of
 * text fits only if every corner of every line sits inside it: a wide line near the top or bottom reaches the stroke
 * long before a narrow one. `fitNumeral` finds the largest numeral size whose whole block (numeral plus an optional
 * small label under it) stays inside the hole with some padding. Widths are estimates for tabular Manrope 800.
 */

/** Advance widths in em for the numeral face (tabular, heavy). Unknown characters count as a digit. */
const EM: Record<string, number> = { ",": 0.32, ".": 0.32, " ": 0.3, ":": 0.32, "—": 0.9, "-": 0.5, "%": 0.95, h: 0.62, m: 0.97, k: 0.6, s: 0.5 };
const DIGIT_EM = 0.66;
const NUMERAL_TRACKING_EM = -0.05;

/** Width of numeral text in em. */
export function numeralWidthEm(text: string): number {
  let w = 0;
  for (const ch of text) w += (EM[ch] ?? DIGIT_EM) + NUMERAL_TRACKING_EM;
  return w;
}

/** Width in px of a small label at `px` size; uppercase eyebrows are wider and carry letter-spacing. */
export function labelWidthPx(text: string, px = 11, { upper = false, trackingEm = 0 }: { upper?: boolean; trackingEm?: number } = {}): number {
  return [...text].length * px * ((upper ? 0.7 : 0.56) + trackingEm);
}

export interface FitInput {
  /** Radius in px of the hole inside the innermost stroke. */
  radius: number;
  text: string;
  /** A small line under the numeral, as its measured width and height in px. */
  label?: { width: number; height: number };
  /** Space between numeral and label, px. */
  gap?: number;
  /** Clearance kept between any corner and the stroke, px. */
  pad?: number;
  min?: number;
  max?: number;
  /** Numeral line-height as a multiple of its size (the .numeral class uses 0.9). */
  lineHeight?: number;
}

/** Largest corner distance from the block centre for a numeral of size `f`. */
function reach(f: number, i: Required<Pick<FitInput, "gap" | "lineHeight">> & FitInput): number {
  const numH = f * i.lineHeight;
  const lab = i.label;
  const total = numH + (lab ? i.gap + lab.height : 0);
  const top = -total / 2;
  const numBottom = top + numH;
  const numCorner = Math.hypot((numeralWidthEm(i.text) * f) / 2, Math.max(Math.abs(top), Math.abs(numBottom)));
  if (!lab) return numCorner;
  const labTop = numBottom + i.gap;
  const labCorner = Math.hypot(lab.width / 2, Math.max(Math.abs(labTop), Math.abs(labTop + lab.height)));
  return Math.max(numCorner, labCorner);
}

/** Largest numeral font size in px (between min and max) that keeps the block inside the hole. Returns `min` if even that cannot fit. */
export function fitNumeral(input: FitInput): number {
  const { radius, min = 14, max = 48, pad = 4, gap = 3, lineHeight = 0.9 } = input;
  const i = { ...input, gap, lineHeight };
  const limit = radius - pad;
  if (reach(min, i) > limit) return min;
  if (reach(max, i) <= limit) return max;
  let lo = min;
  let hi = max;
  for (let n = 0; n < 24; n++) {
    const mid = (lo + hi) / 2;
    if (reach(mid, i) <= limit) lo = mid;
    else hi = mid;
  }
  return Math.floor(lo * 2) / 2;
}

/** Radius in px of the inner hole for a ring drawn in a 200-unit viewBox at `size` px: innermost radius minus half its stroke. */
export function holeRadius(size: number, innermostR: number, stroke: number): number {
  return ((innermostR - stroke / 2) / 200) * size;
}
