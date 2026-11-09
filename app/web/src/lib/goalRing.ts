// Pure model for a single-goal ring (protein, calories on the Food page): how much is logged against a target band.
// A missing value is "none", never zero. The band is drawn on the ring itself so the target is visible, not just stated.
export type GoalStatus = "none" | "no_target" | "below" | "within" | "above";

export interface GoalRingModel {
  /** Full circle represents this much. */
  scale: number;
  fill: number;
  bandFrom: number;
  bandTo: number;
  status: GoalStatus;
  /** Amount still to the low end of the band (when below) or over the top of it (when above); 0 otherwise. */
  gap: number;
}

export const BAND_HEADROOM = 1.25; // the ring runs a quarter past the top of the band so "above" has room to show

const share = (v: number, scale: number) => Math.max(0, Math.min(1, v / scale));

export function goalRing(value: number | null, band: [number, number] | null): GoalRingModel {
  const v = value != null && Number.isFinite(value) && value >= 0 ? value : null;
  if (!band) {
    return { scale: Math.max(v ?? 0, 1), fill: v == null ? 0 : 1, bandFrom: 0, bandTo: 0, status: v == null ? "none" : "no_target", gap: 0 };
  }
  const [lo, hi] = band[0] <= band[1] ? band : [band[1], band[0]];
  const scale = Math.max(hi * BAND_HEADROOM, v ?? 0, 1);
  const status: GoalStatus = v == null ? "none" : v < lo ? "below" : v > hi ? "above" : "within";
  return {
    scale, fill: v == null ? 0 : share(v, scale), bandFrom: share(lo, scale), bandTo: share(hi, scale), status,
    gap: v == null ? 0 : status === "below" ? lo - v : status === "above" ? v - hi : 0,
  };
}
