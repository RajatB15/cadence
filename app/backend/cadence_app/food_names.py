"""Your own names for dishes ("my name") and the dish search that uses them.

A dish keeps its library name; you add names you actually use (a local word, a family word) and may mark one as the name
to show. Names are stored per dish; for library dishes also under the dish's catalogue code, so a catalogue re-seed
(`foodlog.ensure_catalogue` deletes and re-adds rows) re-attaches them (`reattach`) and nothing you typed is lost.
The matching and ranking are pure and live in `analytics/foodsearch.py`; this module loads and stores.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from cadence_app import food_quick, foodlog
from cadence_app.analytics import foodrank, foodsearch
from cadence_app.models import FoodDish, FoodUserAlias

MAX_NAME = 60
MAX_PER_DISH = 12


def clean_name(name: str) -> tuple[str, str]:
    text = " ".join((name or "").split())
    if not text:
        raise foodlog.FoodError("Give the name some letters")
    if len(text) > MAX_NAME:
        raise foodlog.FoodError(f"Keep the name to {MAX_NAME} characters")
    if any(unicodedata.category(c).startswith("C") for c in text):
        raise foodlog.FoodError("The name has characters that cannot be shown")
    folded = foodsearch.fold(text)
    if not folded:
        raise foodlog.FoodError("Give the name some letters or digits")
    return text, folded


def _dish(session: Session, dish_id: int) -> FoodDish:
    d = session.get(FoodDish, dish_id)
    if d is None:
        raise LookupError("No such dish")
    return d


def _check(d: FoodDish, name: str, folded: str, exclude_id: int | None = None) -> None:
    if folded == foodsearch.fold(d.name):
        raise foodlog.FoodError("That is already the dish's own name")
    if any(a.folded == folded and a.id != exclude_id for a in d.user_aliases):
        raise foodlog.FoodError("You already have that name on this dish")


def add(session: Session, dish_id: int, name: str, preferred: bool, now: datetime) -> tuple[FoodDish, FoodUserAlias]:
    d = _dish(session, dish_id)
    text, folded = clean_name(name)
    _check(d, text, folded)
    if len(d.user_aliases) >= MAX_PER_DISH:
        raise foodlog.FoodError(f"A dish can have {MAX_PER_DISH} names of yours; remove one first")
    row = FoodUserAlias(dish_id=d.id, ref_code=d.ref_code if d.source == "library" else None, alias=text, folded=folded,
                        preferred=False, created_at=now, use_count=0)
    session.add(row)
    session.flush()
    if preferred:
        _prefer(session, d.id, row.id)
    session.commit()
    session.refresh(d)
    return d, row


def _prefer(session: Session, dish_id: int, alias_id: int | None) -> None:
    session.execute(update(FoodUserAlias).where(FoodUserAlias.dish_id == dish_id).values(preferred=False))
    if alias_id is not None:
        session.execute(update(FoodUserAlias).where(FoodUserAlias.id == alias_id).values(preferred=True))


def update_name(session: Session, dish_id: int, alias_id: int, values: dict) -> tuple[FoodDish, FoodUserAlias]:
    d = _dish(session, dish_id)
    row = session.get(FoodUserAlias, alias_id)
    if row is None or row.dish_id != d.id:
        raise LookupError("No such name")
    if values.get("name") is not None:
        text, folded = clean_name(values["name"])
        _check(d, text, folded, exclude_id=row.id)
        row.alias, row.folded = text, folded
    if values.get("preferred") is not None:
        if values["preferred"]:
            _prefer(session, d.id, row.id)
        else:
            row.preferred = False
    session.commit()
    session.refresh(d)
    session.refresh(row)
    return d, row


def remove(session: Session, dish_id: int, alias_id: int) -> FoodDish:
    d = _dish(session, dish_id)
    row = session.get(FoodUserAlias, alias_id)
    if row is None or row.dish_id != d.id:
        raise LookupError("No such name")
    session.delete(row)
    session.commit()
    session.refresh(d)
    return d


def bump(session: Session, dish_id: int | None, alias_id: int | None, now: datetime) -> None:
    """You chose this dish by one of your names: count it (a no-op for a name that is not on that dish). Caller commits."""
    if dish_id is None or alias_id is None:
        return
    row = session.get(FoodUserAlias, alias_id)
    if row is not None and row.dish_id == dish_id:
        row.use_count, row.last_used_at = (row.use_count or 0) + 1, now


def search(session: Session, query: str, today: date, limit: int = 20) -> list[dict]:
    rows = list(session.scalars(select(FoodDish).where(FoodDish.active.is_(True))))
    pool = [{"id": d.id, "name": d.name, "aliases": json.loads(d.aliases) if d.aliases else [], "my_names": foodlog.my_names(d)} for d in rows]
    by_id = {d.id: d for d in rows}
    freq = foodrank.frecency(food_quick.history(session, today), today)
    out = []
    for r in foodsearch.rank(query, pool, freq, limit):
        d = by_id[r["id"]]
        out.append({"dish": foodlog.dish_dict(d), "score": r["score"],
                    "match": {"kind": r["kind"], "text": r["text"], "alias_id": r["alias_id"]}})
    return out
