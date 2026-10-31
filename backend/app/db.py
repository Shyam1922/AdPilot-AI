"""Database engine + session. SQLite for the MVP; swap DATABASE_URL for PostgreSQL later."""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_sqlite = settings.database_url.startswith("sqlite")
# timeout: wait up to 30 s for a lock instead of failing with "database is locked" (a background render and a
# request writing at the same moment was the main cause of random 500s).
_connect_args = {"check_same_thread": False, "timeout": 30} if _sqlite else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)

if _sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):          # WAL = readers never block the writer
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(engine)
    ensure_columns()


def ensure_columns() -> list[str]:
    """Tiny forward-only migration for SQLite: add any column the models have but the file doesn't.
    Pulling a newer version no longer needs `delete adpilot.db`. (New columns are nullable.)"""
    if not _sqlite:
        return []
    from sqlalchemy import inspect, text

    added: list[str] = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    ddl = col.type.compile(engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))
                    added.append(f"{table.name}.{col.name}")
    return added


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def recover_interrupted() -> dict:
    """Run at startup. If the server was stopped or crashed mid-job, nothing is left 'running' forever:
    stuck renders become 'failed' (the UI shows Retry) and half-created brands are removed."""
    from sqlmodel import select

    from .models import Asset, Brand

    out = {"renders_marked_failed": 0, "brands_removed": 0, "meko_syncs_reset": 0}
    with Session(engine) as session:
        for a in session.exec(select(Asset).where(Asset.status.in_(["queued", "rendering"]))).all():
            a.status, a.error = "failed", "Interrupted by a server restart. Click Generate video again."
            session.add(a)
            out["renders_marked_failed"] += 1
        for b in session.exec(select(Brand)).all():
            if b.name == "Analyzing…" and not b.profile:
                session.delete(b)
                out["brands_removed"] += 1
            elif (b.integrations or {}).get("meko", {}).get("status") == "syncing":
                b.integrations = {**b.integrations, "meko": {**b.integrations["meko"], "status": "pending"}}
                session.add(b)
                out["meko_syncs_reset"] += 1
        session.commit()
    return out
