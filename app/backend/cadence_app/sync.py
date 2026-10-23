from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from cadence_app.connectors import demo
from cadence_app.importer import ensure_source, write_batch
from cadence_app.models import Source, SyncRun

DEMO_HISTORY_DAYS = 365


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def run_demo_sync(factory: sessionmaker, today: date, now: datetime) -> SyncRun:
    """Import demo history ending yesterday; failures are persisted on the run."""
    with factory() as session:
        ensure_source(session, demo.SOURCE_ID, demo.SOURCE_NAME, "demo")
        run = SyncRun(source_id=demo.SOURCE_ID, started_at=now, status="running", records_written=0)
        session.add(run)
        session.commit()
        run_id = run.id

    try:
        batch = demo.generate(today - timedelta(days=DEMO_HISTORY_DAYS), today - timedelta(days=1))
        with factory() as session, session.begin():
            written = write_batch(session, demo.SOURCE_ID, batch, now)
            session.get(Source, demo.SOURCE_ID).last_synced_at = now
            run = session.get(SyncRun, run_id)
            run.status = "succeeded"
            run.records_written = written
            run.finished_at = utcnow()
    except Exception as exc:
        with factory() as session, session.begin():
            run = session.get(SyncRun, run_id)
            run.status = "failed"
            run.error = type(exc).__name__
            run.finished_at = utcnow()
        raise

    with factory() as session:
        return session.get(SyncRun, run_id)


def latest_runs(session: Session, limit: int = 10) -> list[SyncRun]:
    return (
        session.query(SyncRun).order_by(SyncRun.started_at.desc(), SyncRun.id.desc()).limit(limit).all()
    )
