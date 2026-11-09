import type { BookView } from "./types";

type Progress = NonNullable<BookView["progress"]>;

/** "3 h 20 min", "45 min": reading time left, never a false "0 min" for something unfinished. */
export function spanMinutes(min: number): string {
  if (min < 60) return `${Math.max(1, Math.round(min))} min`;
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Where you are in the book, in plain words. Pace is an arithmetic note (one part a day), not a target. */
export function leftNote(p: Progress): string {
  if (p.finished) return "You’ve finished the book.";
  const left = p.parts - p.parts_done;
  const parts = `${left} part${left === 1 ? "" : "s"} left`;
  if (p.parts_done === 0) return `${p.parts} parts, about ${spanMinutes(p.minutes_left)} in all. One part a day takes about ${Math.ceil(p.parts / 30)} month${p.parts > 45 ? "s" : ""}.`;
  return `${parts} · about ${spanMinutes(p.minutes_left)} · roughly ${left} day${left === 1 ? "" : "s"} at one part a day`;
}

export const percentRead = (p: Progress) => (p.parts ? Math.round((p.parts_done / p.parts) * 100) : 0);
