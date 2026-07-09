"""Database engine and schema initialization."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from shahrazad_agent.config import DATA_DIR
from shahrazad_agent.db.models import Base


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> Engine:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record) -> None:  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_session_factory(database_url: str) -> sessionmaker:
    return sessionmaker(bind=get_engine(database_url), expire_on_commit=False)


def init_db(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))
