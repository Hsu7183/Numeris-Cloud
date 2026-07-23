from __future__ import annotations

import sqlite3
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.paths import ensure_directories


class Base(DeclarativeBase):
    pass


ensure_directories()
engine: Engine = create_engine(
    get_settings().database_url,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    # WAL已在資料庫建立時持久化；多個短命測試程序切換期間可能暫時持鎖。
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_status() -> dict[str, object]:
    with engine.connect() as connection:
        version = connection.execute(text("select sqlite_version()")).scalar_one()
        integrity = connection.execute(text("pragma quick_check")).scalar_one()
    return {"sqlite_version": version, "integrity": integrity}
