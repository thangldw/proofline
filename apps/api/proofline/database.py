from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    read_only = os.getenv("PROOFLINE_DATABASE_READ_ONLY", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    if url.startswith("sqlite:///"):
        database = make_url(url).database
        if database is None:
            raise ValueError("SQLite database path is unavailable")
        if read_only and database != ":memory:":
            encoded_path = quote(database, safe="/:")
            url = f"sqlite:///file:{encoded_path}?mode=ro&uri=true"
        elif not read_only:
            Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url, connect_args={"check_same_thread": False} if "sqlite" in url else {}
    )

    if "sqlite" in url:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_constraints(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def initialize_database(target: Engine = engine) -> None:
    from .migrations import run_migrations

    run_migrations(target)
