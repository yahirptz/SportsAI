"""Database engine + session management."""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import Base

_connect_args = {"check_same_thread": False} if settings.tracking_database_url.startswith("sqlite") else {}
_engine = create_engine(settings.tracking_database_url, connect_args=_connect_args, future=True)
_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(_engine)
    # Lightweight migration: add columns introduced after a DB was created.
    cols = {c["name"] for c in inspect(_engine).get_columns("tracked_picks")}
    if "context" not in cols:
        with _engine.begin() as conn:
            conn.execute(text("ALTER TABLE tracked_picks ADD COLUMN context VARCHAR"))


@contextmanager
def get_session() -> Session:
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
