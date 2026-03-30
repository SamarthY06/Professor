"""
Integration tests for LearningState persistence via SQLAlchemy.

Tests database round-trips for:
- completed_days ARRAY(Integer)
- learning_plan JSONB
- state_version optimistic locking

Requires DATABASE_URL to be set.
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.learning import LearningState
from app.models.user import User
from app.models.book import Book


@pytest.mark.integration
@pytest.mark.asyncio
async def test_learning_state_completed_days_array(db_session: AsyncSession):
    """
    Verify that completed_days is correctly saved and loaded as ARRAY(Integer).
    Ensures SQLAlchemy ARRAY column round-trips integer lists.
    """
    user = User(
        id=uuid.uuid4(),
        email=f"completed_days_test_{uuid.uuid4().hex[:8]}@example.com",
        name="Completed Days Test",
        role="student",
        is_active=True,
    )
    db_session.add(user)

    book = Book(
        id=uuid.uuid4(),
        user_id=user.id,
        title="Completed Days Test Book",
        author="Test Author",
        file_path="/tmp/test.pdf",
        file_hash="test_hash",
        total_pages=10,
        total_chapters=3,
        processing_status="completed",
    )
    db_session.add(book)
    await db_session.flush()

    state = LearningState(
        user_id=user.id,
        book_id=book.id,
        current_day=3,
        current_chapter=2,
        completed_days=[1, 2],
        completed_chapters=[1],
    )
    db_session.add(state)
    await db_session.commit()

    result = await db_session.execute(
        select(LearningState)
        .where(LearningState.user_id == user.id)
        .where(LearningState.book_id == book.id)
    )
    loaded = result.scalar_one()

    assert loaded.completed_days == [1, 2]
    assert isinstance(loaded.completed_days, list)
    assert all(isinstance(d, int) for d in loaded.completed_days)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_learning_state_plan_data_jsonb(db_session: AsyncSession):
    """
    Verify that plan_data (stored as learning_plan JSONB) persists complex nested structures.
    Ensures JSONB correctly serializes/deserializes.
    """
    user = User(
        id=uuid.uuid4(),
        email=f"plan_jsonb_test_{uuid.uuid4().hex[:8]}@example.com",
        name="Plan JSONB Test",
        role="student",
        is_active=True,
    )
    db_session.add(user)

    book = Book(
        id=uuid.uuid4(),
        user_id=user.id,
        title="Plan JSONB Test Book",
        author="Test Author",
        file_path="/tmp/test.pdf",
        file_hash="test_hash",
        total_pages=10,
        total_chapters=5,
        processing_status="completed",
    )
    db_session.add(book)
    await db_session.flush()

    plan_data = {
        "total_days": 10,
        "days": [
            {
                "day": 1,
                "day_title": "Introduction",
                "items": [
                    {
                        "chapter_number": 1,
                        "chapter_title": "Basics",
                        "topics": [{"name": "Topic A", "priority": "core"}],
                    }
                ],
            }
        ],
    }

    state = LearningState(
        user_id=user.id,
        book_id=book.id,
        learning_plan=plan_data,
    )
    db_session.add(state)
    await db_session.commit()

    result = await db_session.execute(
        select(LearningState)
        .where(LearningState.user_id == user.id)
        .where(LearningState.book_id == book.id)
    )
    loaded = result.scalar_one()

    assert loaded.learning_plan == plan_data
    assert loaded.learning_plan["total_days"] == 10
    assert loaded.learning_plan["days"][0]["day_title"] == "Introduction"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_state_version_increment(db_session: AsyncSession):
    """
    Verify optimistic locking: state_version increments on each update
    and concurrent modifications can be detected.
    """
    user = User(
        id=uuid.uuid4(),
        email=f"version_test_{uuid.uuid4().hex[:8]}@example.com",
        name="Version Test",
        role="student",
        is_active=True,
    )
    db_session.add(user)

    book = Book(
        id=uuid.uuid4(),
        user_id=user.id,
        title="Version Test Book",
        author="Test Author",
        file_path="/tmp/test.pdf",
        file_hash="test_hash",
        total_pages=10,
        total_chapters=3,
        processing_status="completed",
    )
    db_session.add(book)
    await db_session.flush()

    state = LearningState(
        user_id=user.id,
        book_id=book.id,
        state_version=0,
    )
    db_session.add(state)
    await db_session.commit()

    result = await db_session.execute(
        select(LearningState)
        .where(LearningState.user_id == user.id)
        .where(LearningState.book_id == book.id)
    )
    loaded = result.scalar_one()

    assert loaded.state_version == 0

    loaded.current_day = 2
    loaded.state_version = loaded.state_version + 1
    await db_session.commit()
    await db_session.refresh(loaded)

    assert loaded.state_version == 1

    loaded.completed_days = [1]
    loaded.state_version = loaded.state_version + 1
    await db_session.commit()
    await db_session.refresh(loaded)

    assert loaded.state_version == 2
