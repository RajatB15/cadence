import type { FoodCrawlProgress } from "./types";

export const CRAWL_COLOR = { parsed: "#c8f560", failed: "#ff6a55", untried: "#5c5a55" } as const;
export const LIBRARY_COLOR = { dishes: "#6cc7ff", merged: "#9b8cff", dropped: "#ffbe55", noName: "#8d8a82" } as const;

export interface Segment {
  key: string;
  label: string;
  pages: number;
  color: string;
}

/** The three states a page can be in, in the order they read left to right. Segments with no pages are kept so the legend stays put. */
export function crawlSegments(p: Pick<FoodCrawlProgress, "parsed" | "failed" | "untried">): Segment[] {
  return [
    { key: "parsed", label: "Parsed", pages: p.parsed, color: CRAWL_COLOR.parsed },
    { key: "failed", label: "Failed, waiting to retry", pages: p.failed, color: CRAWL_COLOR.failed },
    { key: "untried", label: "Not tried yet", pages: p.untried, color: CRAWL_COLOR.untried },
  ];
}

/** What the parsed pages became. Null before the first catalogue build, so it never reads as zero. */
export function librarySegments(lib: NonNullable<FoodCrawlProgress["library"]>): Segment[] | null {
  if (lib.dishes == null || lib.merged == null) return null;
  const dropped = lib.dropped.reduce((s, d) => s + d.pages, 0);
  return [
    { key: "dishes", label: "Became a dish", pages: lib.dishes, color: LIBRARY_COLOR.dishes },
    { key: "merged", label: "Merged into a dish as another name", pages: lib.merged, color: LIBRARY_COLOR.merged },
    { key: "dropped", label: "Dropped by the sanity checks", pages: dropped, color: LIBRARY_COLOR.dropped },
    { key: "noName", label: "Skipped: no English name", pages: lib.no_latin_name ?? 0, color: LIBRARY_COLOR.noName },
  ];
}

export function percent(part: number, whole: number): string {
  if (!whole) return "0%";
  const p = (part / whole) * 100;
  return p > 0 && p < 1 ? "<1%" : `${Math.round(p)}%`;
}

/** "about 7 h", "about 40 min": a rough projection, never a promise. */
export function roughDuration(fromIso: string, toIso: string): string {
  const mins = Math.max(0, (new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60000);
  if (mins < 90) return `about ${Math.max(5, Math.round(mins / 5) * 5)} min`;
  const h = mins / 60;
  return h < 10 ? `about ${h.toFixed(1)} h` : `about ${Math.round(h)} h`;
}
