
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings, get_settings
from .models import Base

__all__ = ["init_engine", "get_engine", "get_sessionmaker", "session_scope", "create_all"]

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None

def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    if not hasattr(dbapi_connection, "execute"):
        return
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
    except Exception:
        pass

def init_engine(settings: Settings | None = None, echo: bool = False) -> Engine:
    global _engine, _session_factory
    settings = settings or get_settings()

    url = settings.database_url
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" not in url:
            path = Path(url.split("sqlite:///", 1)[-1])
            path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(url, echo=echo, future=True, connect_args=connect_args)
    if url.startswith("sqlite"):
        event.listen(_engine, "connect", _configure_sqlite)

    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    logger.info("database engine initialised: %s", url.split("://", 1)[0])
    return _engine

def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine

def get_sessionmaker() -> sessionmaker[Session]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory

def _add_missing_columns(engine: Engine) -> None:
    with engine.connect() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(profiles)")}
        if "poll_interval_seconds" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE profiles ADD COLUMN poll_interval_seconds INTEGER"
            )
            connection.commit()

def create_all(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    if engine.url.get_backend_name() == "sqlite":
        _add_missing_columns(engine)

@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
