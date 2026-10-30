"""Pytest fixtures for backend tests with isolated SQLite database and test clients."""

import shutil
import sqlite3
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User

# In-memory SQLite engine with StaticPool for test isolation
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """Setup temporary storage directory and create database tables."""
    import app.db.session
    from app.services.memory_service import MemoryService
    from app.services.search_service import SearchService

    temp_dir = tempfile.mkdtemp(prefix="assistant_test_storage_")
    orig_storage = settings.STORAGE_DIR
    orig_chroma = settings.CHROMA_PERSIST_DIR
    orig_vault = settings.VAULT_CHROMA_PATH

    settings.STORAGE_DIR = Path(temp_dir) / "uploads"
    settings.CHROMA_PERSIST_DIR = Path(temp_dir) / "chroma"
    settings.VAULT_CHROMA_PATH = Path(temp_dir) / "chroma_vault"

    MemoryService._instance = None
    SearchService._instance = None

    orig_session_local = app.db.session.SessionLocal
    app.db.session.SessionLocal = TestingSessionLocal

    Base.metadata.create_all(bind=test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)
    app.db.session.SessionLocal = orig_session_local
    settings.STORAGE_DIR = orig_storage
    settings.CHROMA_PERSIST_DIR = orig_chroma
    settings.VAULT_CHROMA_PATH = orig_vault
    MemoryService._instance = None
    SearchService._instance = None
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Yield a database session and clean tables after each test."""
    connection = test_engine.connect()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    for table in reversed(Base.metadata.sorted_tables):
        connection.execute(table.delete())
    connection.commit()
    connection.close()


@pytest.fixture
async def client(db: Session) -> AsyncGenerator[AsyncClient, None]:
    """Async test client with get_db overridden to use test session."""

    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db: Session) -> User:
    """Create and return a primary test user."""
    user = User(
        email="testuser@example.com",
        hashed_password=hash_password("Password123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """Return Bearer authorization headers for primary test user."""
    token = create_access_token(subject=test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_user_b(db: Session) -> User:
    """Create and return a secondary test user for isolation tests."""
    user = User(
        email="user_b@example.com",
        hashed_password=hash_password("Password123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers_b(test_user_b: User) -> dict[str, str]:
    """Return Bearer authorization headers for secondary test user."""
    token = create_access_token(subject=test_user_b.id)
    return {"Authorization": f"Bearer {token}"}
