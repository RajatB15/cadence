"""Daily reading: cards from the private `reading-data` folder, plus what you did with each.

The cards are short, cited summaries written in our own words (public-domain or open-access sources, linked, never
copied wholesale) and live outside this public repo, in `reading-data/cards/*.json`: a list of objects per file.
Only your state (shown, read, saved, skipped) is stored in the database, keyed by card id, so replacing or growing
the library never loses it. A card with a missing field, an unknown topic or no http(s) source link is skipped
rather than shown half-formed; `load_cards` reports how many were skipped. Picking is `analytics/reading.py`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from cadence_app.analytics import reading as picker
from cadence_app import reading_feed
from cadence_app.models import ReadingFeedItem, ReadingItem

STATUSES = ("read", "saved", "skipped", "unread")
EVIDENCE = ("guideline", "review", "trial", "observational", "expert")
_cache: dict[Path, tuple[tuple, tuple[list[dict], int]]] = {}


def _clean(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    text = lambda k: raw.get(k).strip() if isinstance(raw.get(k), str) else ""  # noqa: E731
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    url = (source.get("url") or "").strip() if isinstance(source.get("url"), str) else ""
    takeaways = [t.strip() for t in raw.get("takeaways", []) if isinstance(t, str) and t.strip()] if isinstance(raw.get("takeaways"), list) else []
    card = {"id": text("id"), "topic": text("topic"), "title": text("title"), "summary": text("summary"),
            "takeaways": takeaways, "read_min": raw.get("read_min") if isinstance(raw.get("read_min"), int) else 3,
            "evidence": text("evidence"), "caution": text("caution") or None,
            "source": {"name": (source.get("name") or "").strip() if isinstance(source.get("name"), str) else "",
                       "url": url, "licence": (source.get("licence") or "").strip() if isinstance(source.get("licence"), str) else ""}}
    if not (card["id"] and card["title"] and card["summary"] and card["source"]["name"]):
        return None
    if card["topic"] not in picker.TOPICS or card["evidence"] not in EVIDENCE or not url.startswith(("http://", "https://")):
        return None
    return card


def load_cards(reading_dir: Path | None) -> tuple[list[dict], int]:
    """(valid cards, number skipped). Empty when the folder isn't there; cached until a file changes."""
    folder = reading_dir / "cards" if reading_dir else None
    if folder is None or not folder.is_dir():
        return [], 0
    files = sorted(folder.glob("*.json"))
    stamp = tuple((f.name, f.stat().st_mtime_ns) for f in files)
    hit = _cache.get(folder)
    if hit and hit[0] == stamp:
        return hit[1]
    cards, skipped, seen = [], 0, set()
    for f in files:
        try:
            raw = json.loads(f.read_text())
        except (OSError, ValueError):
            skipped += 1
            continue
        for item in raw if isinstance(raw, list) else []:
            card = _clean(item)
            if card is None or card["id"] in seen:
                skipped += 1
                continue
            seen.add(card["id"])
            cards.append(card)
    _cache[folder] = (stamp, (cards, skipped))
    return cards, skipped


def _statuses(session: Session) -> dict[str, str]:
    return {r.card_id: r.status for r in session.scalars(select(ReadingItem))}


def _row(session: Session, card_id: str, now: datetime) -> ReadingItem:
    row = session.get(ReadingItem, card_id)
    if row is None:
        row = ReadingItem(card_id=card_id, status="shown", picked_day=None, updated_at=now)
        session.add(row)
    return row


def today_pick(session: Session, cards: list[dict], day: date, signals: Callable[[], dict | None], now: datetime) -> dict | None:
    """Today's card, chosen once and kept for the day. `signals` is only called when a new pick is needed."""
    by_id = {c["id"]: c for c in cards}
    existing = session.scalars(select(ReadingItem).where(ReadingItem.picked_day == day)).first()
    if existing and existing.card_id in by_id:
        return {"card": by_id[existing.card_id], "why": existing.why or "Today's pick.", "repeat": existing.why.startswith("You've been")}
    status = _statuses(session)
    prev = session.scalars(select(ReadingItem).where(ReadingItem.picked_day == day - timedelta(days=1))).first()
    chosen = picker.pick(cards, status, day, signals(), by_id[prev.card_id]["topic"] if prev and prev.card_id in by_id else None)
    if chosen is None:
        return None
    row = _row(session, chosen["card"]["id"], now)
    row.picked_day, row.why, row.updated_at = day, chosen['why'], now
    session.commit()
    return chosen


def feed_items(session: Session, status: dict[str, str]) -> list[dict]:
    """Recent papers from the research feed, newest first, with what you did with each. Dismissed ones are hidden."""
    rows = session.scalars(select(ReadingFeedItem).order_by(ReadingFeedItem.published.desc(), ReadingFeedItem.id)).all()
    return [{"id": r.id, "topic": r.topic, "title": r.title, "journal": r.journal, "published": r.published, "evidence": r.evidence,
             "snippet": r.snippet, "url": r.url, "licence": r.licence, "status": status.get(r.id, "new")}
            for r in rows if status.get(r.id) != "skipped"]


def view(session: Session, reading_dir: Path | None, day: date, signals: Callable[[], dict | None], now: datetime,
         feed_available: bool = False) -> dict:
    cards, skipped = load_cards(reading_dir)
    today = today_pick(session, cards, day, signals, now)
    status = _statuses(session)
    days = {r.card_id: r.picked_day for r in session.scalars(select(ReadingItem))}
    items = [{**c, "status": status.get(c["id"], "new"), "picked_day": days.get(c["id"])} for c in cards]
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("new", "shown", "read", "saved", "skipped")}
    return {
        "available": bool(cards),
        "skipped_invalid": skipped,
        "topics": [{"key": k, "label": v, "count": sum(1 for c in cards if c["topic"] == k)} for k, v in picker.TOPICS.items()],
        "today": ({**today["card"], "status": status.get(today["card"]["id"], "shown"), "why": today["why"], "repeat": today["repeat"]}
                  if today else None),
        "cards": items,
        "counts": counts,
        "feed": {"available": feed_available, "enabled": reading_feed.enabled(session),
                 "fetched_at": reading_feed.state(session).get("fetched_at"), "items": feed_items(session, status)},
    }


def set_status(session: Session, reading_dir: Path | None, card_id: str, new_status: str, day: date, now: datetime) -> bool:
    """Records read/saved/skipped (or clears it). Skipping today's card frees today's slot for another pick."""
    if new_status not in STATUSES:
        raise ValueError("Unknown status")
    cards, _ = load_cards(reading_dir)
    if card_id not in {c["id"] for c in cards} and session.get(ReadingFeedItem, card_id) is None:
        return False
    row = _row(session, card_id, now)
    row.status = "shown" if new_status == "unread" else new_status
    row.updated_at = now
    if new_status == "skipped" and row.picked_day == day:
        row.picked_day = None
    session.commit()
    return True
