"""Pytest configuration and fixtures."""

import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.db.database import Base, get_db
from app.config import settings


# Test database URL - prefer DATABASE_URL for integration tests (skip if not set)
DATABASE_URL = os.getenv("DATABASE_URL")
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://professor:professor_dev_password@localhost:5432/professor_test"
)

# Convert postgresql:// to postgresql+asyncpg:// if needed
def _ensure_async_url(url: str) -> str:
    if url and url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url or ""


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine (uses TEST_DATABASE_URL)."""
    url = TEST_DATABASE_URL
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Test database session using DATABASE_URL. Skips if DATABASE_URL is not set.
    Use for integration tests that require a real database.
    """
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL not set - skipping database-dependent tests")

    url = _ensure_async_url(DATABASE_URL)
    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_always(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session using TEST_DATABASE_URL (never skips)."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session_always: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database override."""
    async def override_get_db():
        yield db_session_always

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def mock_user_data():
    """Mock user data for tests."""
    return {
        "email": "test@example.com",
        "name": "Test User",
        "role": "student",
    }


@pytest.fixture
def mock_book_data():
    """Mock book data for tests."""
    return {
        "title": "Test Book",
        "author": "Test Author",
        "total_chapters": 5,
    }


@pytest.fixture
def mock_api_key():
    """Mock OpenAI API key for tests."""
    return "sk-test-key-1234567890abcdef"
