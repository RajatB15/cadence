import { describe, expect, it } from "vitest";
import { checkedAgo, filterCards, filterFeed, sourceLine } from "./reading";
import type { ReadingCard, ReadingFeedItem } from "./types";

const card = (id: string, topic: string, status: ReadingCard["status"]): ReadingCard => ({
  id, topic, title: id, summary: "s", takeaways: [], read_min: 3, evidence: "review", caution: null, status, picked_day: null,
  source: { name: "Source", url: "https://www.example.org/a", licence: "Link only" },
});

describe("reading library", () => {
  const cards = [card("a", "nutrition", "new"), card("b", "nutrition", "read"), card("c", "training", "saved"), card("d", "training", "skipped"), card("e", "training", "shown")];
  it("filters by topic and state", () => {
    expect(filterCards(cards, null, "all")).toHaveLength(5);
    expect(filterCards(cards, "nutrition", "all").map((c) => c.id)).toEqual(["a", "b"]);
    expect(filterCards(cards, null, "unread").map((c) => c.id)).toEqual(["a", "e"]);
    expect(filterCards(cards, "training", "saved").map((c) => c.id)).toEqual(["c"]);
    expect(filterCards(cards, null, "read").map((c) => c.id)).toEqual(["b"]);
  });
  it("shows where a card comes from, and survives a bad link", () => {
    expect(sourceLine(cards[0])).toBe("Source · example.org");
    expect(sourceLine({ ...cards[0], source: { name: "Source", url: "nope", licence: "" } })).toBe("Source");
  });
});

describe("research feed", () => {
  const item = (id: string, topic: string, status: ReadingFeedItem["status"]): ReadingFeedItem => ({
    id, topic, title: id, journal: "J", published: "2026-10-01", evidence: "review", snippet: "s", url: "https://doi.org/x", licence: "CC BY", status,
  });
  it("filters by topic and saved", () => {
    const items = [item("a", "nutrition", "new"), item("b", "nutrition", "saved"), item("c", "training", "saved")];
    expect(filterFeed(items, "nutrition", false).map((i) => i.id)).toEqual(["a", "b"]);
    expect(filterFeed(items, null, true).map((i) => i.id)).toEqual(["b", "c"]);
  });
  it("says when it last checked, and nothing when it never did", () => {
    const now = new Date("2026-10-26T12:00:00");
    expect(checkedAgo(null, now)).toBeNull();
    expect(checkedAgo("2026-10-26T11:40:00", now)).toBe("Checked just now");
    expect(checkedAgo("2026-10-26T06:00:00", now)).toBe("Checked 6 h ago");
    expect(checkedAgo("2026-10-21T12:00:00", now)).toBe("Checked 5 days ago");
  });
});
