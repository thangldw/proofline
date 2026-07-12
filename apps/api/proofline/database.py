from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
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
    from . import models  # noqa: F401

    Base.metadata.create_all(target)
    with target.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search USING fts5(
                chunk_id UNINDEXED,
                source_id UNINDEXED,
                content,
                tokenize = 'unicode61'
            )
            """
        )
