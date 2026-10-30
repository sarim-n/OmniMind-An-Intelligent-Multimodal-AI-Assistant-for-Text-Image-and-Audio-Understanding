"""Tests to verify Alembic migrations apply cleanly to a fresh database."""

import os
import tempfile
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_migrations_apply_to_fresh_db() -> None:
    """Test running 'alembic upgrade head' against an empty SQLite database."""
    backend_dir = Path(__file__).resolve().parent.parent
    alembic_ini_path = backend_dir / "alembic.ini"
    assert alembic_ini_path.is_file(), f"alembic.ini not found at {alembic_ini_path}"

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        temp_db_path = tmp.name

    try:
        sqlite_url = f"sqlite:///{Path(temp_db_path).as_posix()}"
        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", sqlite_url)
        alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))

        # Apply migrations
        command.upgrade(alembic_cfg, "head")

        # Inspect generated schema
        engine = create_engine(sqlite_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        expected_tables = {
            "users",
            "conversations",
            "messages",
            "attachments",
            "transcripts",
            "image_analyses",
            "reports",
            "metrics",
            "alembic_version",
        }
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

        # Verify columns on users table
        user_cols = {col["name"] for col in inspector.get_columns("users")}
        assert {"id", "email", "hashed_password", "created_at"}.issubset(user_cols)

        # Verify columns on attachments table
        attachment_cols = {col["name"] for col in inspector.get_columns("attachments")}
        assert {
            "id",
            "user_id",
            "message_id",
            "type",
            "path",
            "mime",
            "size",
            "duration_sec",
            "metadata",
            "created_at",
        }.issubset(attachment_cols)
    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except OSError:
                pass
