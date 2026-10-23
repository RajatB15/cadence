from __future__ import annotations

import hashlib
import json
import os
import zlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cadence_app.models import RawResponse

SOURCE_ID = "garmin"


@dataclass(frozen=True)
class StoredResponse:
    dataset: str
    payload: Any
    window_start: date | None
    window_end: date | None
    fetched_at: datetime


def decode(body: bytes | None) -> Any:
    if not body:
        return None
    try:
        return json.loads(zlib.decompress(body))
    except (zlib.error, ValueError):
        return None


def store(
    session: Session,
    *,
    dataset: str,
    request_key: str,
    path: str,
    params: dict,
    status: int,
    content_type: str | None,
    body: bytes,
    fetched_at: datetime,
    final: bool,
    item_count: int,
    window: tuple[date | None, date | None] = (None, None),
    file_path: str | None = None,
) -> None:
    compressed = None if file_path else zlib.compress(body, 6)
    values = dict(
        source_id=SOURCE_ID,
        dataset=dataset,
        request_key=request_key,
        path=path,
        params=json.dumps(params, sort_keys=True),
        window_start=window[0],
        window_end=window[1],
        status_code=status,
        content_type=content_type,
        fetched_at=fetched_at,
        final=final,
        item_count=item_count,
        body=compressed,
        body_bytes=len(body),
        stored_bytes=len(compressed) if compressed is not None else len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        file_path=file_path,
    )
    existing = session.scalar(
        select(RawResponse).where(RawResponse.source_id == SOURCE_ID, RawResponse.request_key == request_key)
    )
    if existing is None:
        session.add(RawResponse(**values))
    else:
        for key, value in values.items():
            setattr(existing, key, value)


def prune_provisional(session: Session, dataset: str, keep: set[str]) -> None:
    """Drop provisional (unsettled) responses superseded by the latest recent fetch."""
    session.execute(
        delete(RawResponse).where(
            RawResponse.source_id == SOURCE_ID,
            RawResponse.dataset == dataset,
            RawResponse.final.is_(False),
            RawResponse.request_key.not_in(keep),
        )
    )


def has_final(session: Session, request_key: str) -> bool:
    return (
        session.scalar(
            select(func.count())
            .select_from(RawResponse)
            .where(
                RawResponse.source_id == SOURCE_ID,
                RawResponse.request_key == request_key,
                RawResponse.final.is_(True),
            )
        )
        > 0
    )


def load(session: Session, request_key: str) -> tuple[RawResponse | None, Any]:
    raw = session.scalar(
        select(RawResponse).where(RawResponse.source_id == SOURCE_ID, RawResponse.request_key == request_key)
    )
    return raw, (decode(raw.body) if raw is not None else None)


_summary_cache: dict[str, Any] = {"key": None, "index": {}}


def activity_summaries(session: Session) -> dict[str, dict]:
    """activityId -> full Garmin list item (all ~200 fields), cached until the vault changes."""
    key = session.execute(
        select(func.count(RawResponse.id), func.max(RawResponse.fetched_at)).where(
            RawResponse.source_id == SOURCE_ID, RawResponse.dataset == "activities"
        )
    ).one()
    if _summary_cache["key"] != tuple(key):
        index: dict[str, dict] = {}
        for stored in iter_stored(session, {"activities"}):
            for item in stored.payload if isinstance(stored.payload, list) else []:
                if isinstance(item, dict) and item.get("activityId") is not None:
                    index[str(item["activityId"])] = item
        _summary_cache.update(key=tuple(key), index=index)
    return _summary_cache["index"]


def iter_stored(session: Session, datasets: set[str]):
    """Yield decoded payloads oldest-fetch first so newer responses win on upsert."""
    rows = session.execute(
        select(RawResponse.id)
        .where(
            RawResponse.source_id == SOURCE_ID,
            RawResponse.dataset.in_(datasets),
            RawResponse.status_code == 200,
            RawResponse.body.is_not(None),
        )
        .order_by(RawResponse.fetched_at, RawResponse.id)
    ).scalars().all()
    for raw_id in rows:
        raw = session.get(RawResponse, raw_id)
        yield StoredResponse(
            raw.dataset, decode(raw.body), raw.window_start, raw.window_end, raw.fetched_at
        )
        session.expunge(raw)


def write_file(root: Path, relative: str, body: bytes) -> str:
    target = (root / relative).resolve()
    if root.resolve() not in target.parents:
        raise ValueError("Archive path escapes the archive directory")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(body)
    os.replace(tmp, target)
    return relative


def stats(session: Session) -> dict:
    row = session.execute(
        select(
            func.count(RawResponse.id),
            func.coalesce(func.sum(RawResponse.body_bytes), 0),
            func.coalesce(func.sum(RawResponse.stored_bytes), 0),
            func.count(RawResponse.file_path),
        ).where(RawResponse.source_id == SOURCE_ID)
    ).one()
    files_bytes = session.scalar(
        select(func.coalesce(func.sum(RawResponse.stored_bytes), 0)).where(
            RawResponse.source_id == SOURCE_ID, RawResponse.file_path.is_not(None)
        )
    )
    return {
        "responses": row[0],
        "raw_bytes": row[1],
        "stored_bytes": row[2],
        "files": row[3],
        "file_bytes": files_bytes,
    }
