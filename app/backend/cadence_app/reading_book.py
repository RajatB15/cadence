"""A book to read a little of each day, from the private `reading-data/books/<id>/` folder.

`book.json` names the book, its licence and the ordered chapter files; each chapter file holds its paragraphs as
`[kind, text]` blocks (`h` heading, `p` paragraph, `li` list item). The text is the author's own, licensed for
reuse (the bundled book is CC BY-NC, so it is for private personal reading and the source is always shown), which
is why it lives outside this public repo, like the reading cards.

The book is cut into parts of about `PART_WORDS` words at paragraph boundaries (a heading stays with the text that
follows it, nothing is ever split mid-paragraph). Your place is one number, the next part to read, plus the days you
read on, in `app_settings`: no schema change, and re-cutting the book never loses more than a part of your place.
A day with no part read is simply not in the list; nothing counts a missed day against you.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from cadence_app.models import AppSetting

PART_WORDS = 900  # about four minutes at a relaxed 230 words per minute
WORDS_PER_MIN = 230
STATE_KEY = "reading_book"
_cache: dict[Path, tuple[tuple, dict | None]] = {}


def _words(blocks: list[list[str]]) -> int:
    return sum(len(t.split()) for _, t in blocks)


def _cut(blocks: list[list[str]]) -> list[list[list[str]]]:
    """Groups blocks into parts of at least PART_WORDS (except the last). A heading is held back to open the next part."""
    parts: list[list[list[str]]] = []
    cur: list[list[str]] = []
    for i, block in enumerate(blocks):
        cur.append(block)
        if _words(cur) >= PART_WORDS and not (i + 1 < len(blocks) and block[0] == "h"):
            parts.append(cur)
            cur = []
    if cur:
        if parts and _words(cur) < PART_WORDS // 3:
            parts[-1] += cur
        else:
            parts.append(cur)
    return parts


def _clean_blocks(raw: object) -> list[list[str]]:
    out = []
    for b in raw if isinstance(raw, list) else []:
        if isinstance(b, list) and len(b) == 2 and b[0] in ("h", "p", "li") and isinstance(b[1], str) and b[1].strip():
            out.append([b[0], b[1].strip()])
    return out


def load_book(reading_dir: Path | None) -> dict | None:
    """The first book found, cut into parts: {id, title, authors, url, licence, licence_url, note, chapters, parts}. None when absent."""
    root = reading_dir / "books" if reading_dir else None
    if root is None or not root.is_dir():
        return None
    files = sorted(root.glob("*/book.json")) + sorted(root.glob("*/chapters/*.json"))
    stamp = tuple((str(f), f.stat().st_mtime_ns) for f in files)
    hit = _cache.get(root)
    if hit and hit[0] == stamp:
        return hit[1]
    book = _load(sorted(root.glob("*/book.json"))[0]) if any(f.name == "book.json" for f in files) else None
    _cache[root] = (stamp, book)
    return book


def _load(meta_file: Path) -> dict | None:
    try:
        meta = json.loads(meta_file.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or not all(isinstance(meta.get(k), str) and meta[k] for k in ("id", "title", "url", "licence")):
        return None
    chapters, parts = [], []
    for name in meta.get("chapters", []) if isinstance(meta.get("chapters"), list) else []:
        try:
            raw = json.loads((meta_file.parent / "chapters" / str(name)).read_text())
        except (OSError, ValueError):
            continue
        blocks = _clean_blocks(raw.get("blocks") if isinstance(raw, dict) else None)
        title = raw.get("title") if isinstance(raw, dict) and isinstance(raw.get("title"), str) else ""
        if not blocks or not title:
            continue
        cut = _cut(blocks)
        first = len(parts)
        for n, part in enumerate(cut, 1):
            parts.append({"chapter": len(chapters), "chapter_title": title, "n": n, "of": len(cut), "blocks": part,
                          "words": _words(part), "read_min": max(1, round(_words(part) / WORDS_PER_MIN))})
        chapters.append({"title": title, "first": first, "parts": len(cut), "url": raw.get("url", "")})
    if not parts:
        return None
    return {**{k: meta.get(k) or "" for k in ("id", "title", "authors", "url", "licence", "licence_url", "note")},
            "chapters": chapters, "parts": parts}


def _state(session: Session, book_id: str) -> dict:
    row = session.get(AppSetting, STATE_KEY)
    try:
        data = json.loads(row.value) if row else {}
    except ValueError:
        data = {}
    mine = data.get(book_id) if isinstance(data, dict) else None
    mine = mine if isinstance(mine, dict) else {}
    days = [d for d in mine.get("days", []) if isinstance(d, str)] if isinstance(mine.get("days"), list) else []
    nxt = mine.get("next") if isinstance(mine.get("next"), int) and mine.get("next") >= 0 else 0
    return {"next": nxt, "days": days}


def _save(session: Session, book_id: str, state: dict) -> None:
    row = session.get(AppSetting, STATE_KEY)
    try:
        data = json.loads(row.value) if row else {}
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    data[book_id] = {"next": state["next"], "days": state["days"][-400:]}
    if row:
        row.value = json.dumps(data)
    else:
        session.add(AppSetting(key=STATE_KEY, value=json.dumps(data)))
    session.commit()


def view(session: Session, reading_dir: Path | None, day: date) -> dict:
    """{available, book, current (the part to read now, in full), progress, chapters, read_today, days_read}."""
    book = load_book(reading_dir)
    if book is None:
        return {"available": False}
    state = _state(session, book["id"])
    total = len(book["parts"])
    nxt = min(state["next"], total)
    done = nxt >= total
    part = None if done else book["parts"][nxt]
    words_left = sum(p["words"] for p in book["parts"][nxt:])
    iso = day.isoformat()
    return {
        "available": True,
        "book": {k: book[k] for k in ("id", "title", "authors", "url", "licence", "licence_url", "note")},
        "current": None if part is None else {"index": nxt, **part},
        "progress": {"parts_done": nxt, "parts": total, "finished": done, "minutes_left": round(words_left / WORDS_PER_MIN)},
        "chapters": [{"title": c["title"], "first": c["first"], "parts": c["parts"], "url": c["url"],
                      "done": max(0, min(c["parts"], nxt - c["first"]))} for c in book["chapters"]],
        "read_today": iso in state["days"],
        "days_read": len(set(state["days"])),
    }


def mark_read(session: Session, reading_dir: Path | None, day: date) -> bool:
    """Finishes the current part and moves on. False when there is no book or it is already finished."""
    book = load_book(reading_dir)
    if book is None:
        return False
    state = _state(session, book["id"])
    if state["next"] >= len(book["parts"]):
        return False
    state["next"] += 1
    iso = day.isoformat()
    if iso not in state["days"]:
        state["days"].append(iso)
    _save(session, book["id"], state)
    return True


def set_position(session: Session, reading_dir: Path | None, part: int) -> bool:
    """Moves your place (to a chapter's first part, say). Reading days are kept."""
    book = load_book(reading_dir)
    if book is None or not 0 <= part < len(book["parts"]):
        return False
    state = _state(session, book["id"])
    state["next"] = part
    _save(session, book["id"], state)
    return True
