"""Which reading card to show today.

Pure and deterministic: the same cards, history and signals always give the same pick, so the choice only needs
storing so that it doesn't change when live readiness moves during the day. Selection is a transparent score, not a
model: a topic rotation keeps the week varied (day-of-year picks the topic of the day), and today's call nudges the
choice, so a rest day or a low readiness leans to recovery reading and a hard session day to fuelling and pushing
hard. The same topic isn't shown two days running, cards you read or skipped aren't offered again until everything
unread is used up, and ties break on a stable hash. Nothing here claims the reading will change your results; the
nudge is about relevance only.
"""

from __future__ import annotations

import hashlib
from datetime import date

TOPICS = {
    "nutrition": "Nutrition",
    "sports-science": "Sports science",
    "training": "Training",
    "recovery": "Sleep & recovery",
    "wellbeing": "Wellbeing",
    "pushing-hard": "Pushing hard",
}
ORDER = tuple(TOPICS)
LOW_READINESS = 60


def signal_topics(signals: dict | None) -> tuple[tuple[str, ...], str | None]:
    """Topics that fit today's call, with a plain-language reason. `signals`: {"kind": plan kind, "readiness": score}."""
    kind = (signals or {}).get("kind")
    score = (signals or {}).get("readiness")
    if score is not None and score < LOW_READINESS:
        return ("recovery", "wellbeing"), f"Readiness is low today ({round(score)}), so something on recovery."
    if kind == "rest":
        return ("recovery", "wellbeing"), "Today's call is rest, so something on recovery."
    if kind in ("key", "long"):
        return ("nutrition", "pushing-hard"), "Today has a hard session, so fuelling or pushing hard."
    if kind == "done":
        return ("recovery", "nutrition"), "You've trained today, so recovery or fuelling."
    if kind == "easy":
        return ("training", "sports-science"), "An easy day, a good time for training theory."
    return (), None


def _tie(day: date, card_id: str) -> int:
    return int(hashlib.sha1(f"{day.isoformat()}|{card_id}".encode()).hexdigest()[:8], 16)


def pick(cards: list[dict], status: dict[str, str], day: date, signals: dict | None = None,
         yesterday_topic: str | None = None) -> dict | None:
    """The card for `day`: {"card", "why", "repeat"}, or None when there are no cards.

    `status` maps card id to shown/read/saved/skipped. A saved card stays eligible (it is a bookmark, not a read).
    """
    if not cards:
        return None
    fresh = [c for c in cards if status.get(c["id"]) not in ("read", "skipped")]
    repeat = not fresh
    pool = fresh or [c for c in cards if status.get(c["id"]) != "skipped"] or cards
    topics = [t for t in ORDER if any(c["topic"] == t for c in pool)] or sorted({c["topic"] for c in pool})
    rotation = topics[day.toordinal() % len(topics)]
    wanted, signal_why = signal_topics(signals)

    def score(c: dict) -> tuple:
        s = 0
        s += 3 if c["topic"] in wanted else 0
        s += 2 if c["topic"] == rotation else 0
        s -= 2 if c["topic"] == yesterday_topic else 0
        s += 1 if status.get(c["id"]) == "saved" else 0
        return (-s, _tie(day, c["id"]))

    best = min(pool, key=score)
    if signal_why and best["topic"] in wanted:
        why = signal_why
    elif best["topic"] == rotation:
        why = f"Topic of the day: {TOPICS.get(rotation, rotation)}."
    else:
        why = "Picked to keep the week varied."
    if repeat:
        why = "You've been through every card, so this is a repeat. " + why
    return {"card": best, "why": why, "repeat": repeat}
