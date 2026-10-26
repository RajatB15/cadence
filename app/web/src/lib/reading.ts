import type { ReadingCard, ReadingFeedItem, ReadingEvidence, ReadingStatus } from "./types";

export const EVIDENCE: Record<ReadingEvidence, { label: string; note: string }> = {
  guideline: { label: "Guideline", note: "Written by an expert body or agency." },
  review: { label: "Review", note: "Pools or summarises several studies." },
  trial: { label: "Trial", note: "One controlled experiment, often small." },
  observational: { label: "Observational", note: "Shows an association, not cause and effect." },
  expert: { label: "Expert opinion", note: "A consensus or position, not new data." },
};

export type ReadingFilter = "all" | "unread" | "saved" | "read";

const isUnread = (s: ReadingStatus) => s === "new" || s === "shown";

/** Library listing: optionally one topic and one state; skipped cards only show under "all". */
export function filterCards(cards: ReadingCard[], topic: string | null, filter: ReadingFilter): ReadingCard[] {
  return cards.filter((c) => {
    if (topic && c.topic !== topic) return false;
    if (filter === "unread") return isUnread(c.status);
    if (filter === "saved") return c.status === "saved";
    if (filter === "read") return c.status === "read";
    return true;
  });
}

export function sourceLine(card: ReadingCard): string {
  const host = (() => {
    try {
      return new URL(card.source.url).hostname.replace(/^www\./, "");
    } catch {
      return "";
    }
  })();
  return host ? `${card.source.name} · ${host}` : card.source.name;
}

export const readTime = (card: ReadingCard) => `${card.read_min} min`;

/** Feed listing: one topic or all, unread first-come newest order is kept from the server; saved items can be isolated. */
export function filterFeed(items: ReadingFeedItem[], topic: string | null, savedOnly: boolean): ReadingFeedItem[] {
  return items.filter((i) => (!topic || i.topic === topic) && (!savedOnly || i.status === "saved"));
}

/** "Checked 3 days ago" from the server's timestamp (naive local time), or null when it never ran. */
export function checkedAgo(fetchedAt: string | null, now: Date = new Date()): string | null {
  if (!fetchedAt) return null;
  const hours = Math.max(0, (now.getTime() - new Date(fetchedAt).getTime()) / 36e5);
  if (hours < 1) return "Checked just now";
  if (hours < 48) return `Checked ${Math.round(hours)} h ago`;
  return `Checked ${Math.round(hours / 24)} days ago`;
}
