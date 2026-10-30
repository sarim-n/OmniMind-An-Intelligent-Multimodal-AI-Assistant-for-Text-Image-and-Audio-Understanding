"""Database engine, session management, and FastAPI dependency."""

import sqlite3
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def get_resolved_database_url(url: str) -> str:
    """Resolve relative SQLite database paths against monorepo root and ensure parent dir exists."""
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        raw_path = url[len("sqlite:///") :]
        p = Path(raw_path)
        if not p.is_absolute():
            # Monorepo root is two levels up from app/db/ (backend/ -> root)
            root_dir = Path(__file__).resolve().parent.parent.parent
            p = (root_dir / raw_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{p.as_posix()}"
    return url


resolved_db_url = get_resolved_database_url(settings.DATABASE_URL)

# Configure connect arguments for SQLite vs PostgreSQL
connect_args: dict[str, bool] = {}
if resolved_db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    resolved_db_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)


# Enforce SQLite foreign key constraints
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
