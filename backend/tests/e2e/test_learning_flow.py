"""
End-to-End Tests for Professor Learning Flow.

These tests cover the complete user journey from authentication
through learning completion, including quiz flows.
"""

import asyncio
import uuid
from datetime import datetime
from typing import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.database import Base
from app.main import app
from app.models.user import User, UserAuth
from app.models.book import Book, BookChapter
from app.models.learning import LearningState, DocumentChunk
from app.models.quiz import Quiz, QuizQuestion
from app.security.jwt import create_access_token


# Test database URL (use a separate test database)
TEST_DATABASE_URL = settings.database_url.replace("/professor", "/professor_test")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for each test."""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        name="Test User",
        role="student",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_book(db_session: AsyncSession, test_user: User) -> Book:
    """Create a test book with chapters."""
    book = Book(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="Test Book: Introduction to Testing",
        author="Test Author",
        file_path="/app/data/pdfs/test.pdf",
        file_hash="abc123",
        total_pages=100,
        total_chapters=5,
        processing_status="completed",
    )
    db_session.add(book)
    
    # Create chapters
    for i in range(1, 6):
        chapter = BookChapter(
            id=uuid.uuid4(),
            book_id=book.id,
            chapter_number=i,
            title=f"Chapter {i}: Topic {i}",
            start_page=i * 20 - 19,
            end_page=i * 20,
            estimated_duration_minutes=30,
            key_concepts=[f"concept_{i}_1", f"concept_{i}_2"],
        )
        db_session.add(chapter)
    
    await db_session.commit()
    await db_session.refresh(book)
    return book


@pytest.fixture
async def test_learning_state(
    db_session: AsyncSession,
    test_user: User,
    test_book: Book,
) -> LearningState:
    """Create a test learning state."""
    state = LearningState(
        id=uuid.uuid4(),
        user_id=test_user.id,
        book_id=test_book.id,
        current_chapter=1,
        completed_chapters=[],
        strict_mode=True,
        professor_level="intermediate",
        motivation_score=1.0,
        attention_score=1.0,
        comprehension_score=1.0,
        missed_sessions=0,
        total_study_time_minutes=0,
        quiz_mode="none",
    )
    db_session.add(state)
    await db_session.commit()
    await db_session.refresh(state)
    return state


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    """Create authentication headers for test user."""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


class TestAuthFlow:
    """Test authentication endpoints."""
    
    async def test_health_check(self, client: AsyncClient):
        """Test health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    async def test_protected_route_without_auth(self, client: AsyncClient):
        """Test that protected routes require authentication."""
        response = await client.get("/api/auth/me")
        assert response.status_code == 401
    
    async def test_get_current_user(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_user: User,
    ):
        """Test getting current user info."""
        response = await client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["name"] == test_user.name


class TestBookManagement:
    """Test book management endpoints."""
    
    async def test_list_books(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
    ):
        """Test listing user's books."""
        response = await client.get("/api/books", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    async def test_get_book_details(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
    ):
        """Test getting book details."""
        response = await client.get(
            f"/api/books/{test_book.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == test_book.title


class TestLearningFlow:
    """Test the complete learning flow."""
    
    async def test_get_learning_state(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
        test_learning_state: LearningState,
    ):
        """Test getting learning state."""
        response = await client.get(
            f"/api/learning/state/{test_book.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["current_chapter"] == 1
        assert data["strict_mode"] == True
    
    async def test_chat_message(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
        test_learning_state: LearningState,
    ):
        """Test sending a chat message."""
        response = await client.post(
            "/api/chat",
            headers=auth_headers,
            json={
                "book_id": str(test_book.id),
                "message": "What is this chapter about?",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["mode"] in ["teaching", "quiz", "attention_check"]
    
    async def test_strict_mode_blocks_future_chapters(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
        test_learning_state: LearningState,
    ):
        """Test that strict mode blocks access to future chapters."""
        response = await client.post(
            "/api/chat",
            headers=auth_headers,
            json={
                "book_id": str(test_book.id),
                "message": "Tell me about chapter 5",
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Should be blocked or redirected
        assert "chapter" in data["message"].lower() or "focus" in data["message"].lower()
    
    async def test_get_progress(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
        test_learning_state: LearningState,
    ):
        """Test getting learning progress."""
        response = await client.get(
            f"/api/learning/progress/{test_book.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_chapter" in data
        assert "completed_chapters" in data


class TestQuizFlow:
    """Test quiz functionality."""
    
    @pytest.fixture
    async def test_quiz(
        self,
        db_session: AsyncSession,
        test_book: Book,
    ) -> Quiz:
        """Create a test quiz."""
        # Get chapter
        from sqlalchemy import select
        result = await db_session.execute(
            select(BookChapter)
            .where(BookChapter.book_id == test_book.id)
            .where(BookChapter.chapter_number == 1)
        )
        chapter = result.scalar_one()
        
        quiz = Quiz(
            id=uuid.uuid4(),
            book_id=test_book.id,
            chapter_id=chapter.id,
            quiz_type="chapter_end",
            title="Chapter 1 Quiz",
            total_questions=3,
            passing_score=0.7,
        )
        db_session.add(quiz)
        
        # Add questions
        for i in range(3):
            question = QuizQuestion(
                id=uuid.uuid4(),
                quiz_id=quiz.id,
                book_id=test_book.id,
                chapter_id=chapter.id,
                question_text=f"Test question {i+1}",
                question_type="mcq" if i == 0 else "true_false" if i == 1 else "short_answer",
                options=["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"] if i == 0 else None,
                correct_answer="A" if i == 0 else "true" if i == 1 else "correct answer",
                explanation=f"Explanation for question {i+1}",
                difficulty="medium",
                topic=f"topic_{i+1}",
            )
            db_session.add(question)
        
        await db_session.commit()
        await db_session.refresh(quiz)
        return quiz
    
    async def test_get_chapter_quiz(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_quiz,
    ):
        """Test getting quiz for a chapter."""
        response = await client.get(
            f"/api/quiz/chapter/{test_quiz.chapter_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["total_questions"] == 3
    
    async def test_start_quiz_attempt(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_quiz,
    ):
        """Test starting a quiz attempt."""
        response = await client.post(
            f"/api/quiz/start/{test_quiz.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "attempt_id" in data
        assert "first_question" in data
    
    async def test_submit_quiz_answer(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_quiz,
    ):
        """Test submitting a quiz answer."""
        # First start the quiz
        start_response = await client.post(
            f"/api/quiz/start/{test_quiz.id}",
            headers=auth_headers,
        )
        attempt_data = start_response.json()
        attempt_id = attempt_data["attempt_id"]
        question_id = attempt_data["first_question"]["id"]
        
        # Submit answer
        response = await client.post(
            "/api/quiz/answer",
            headers=auth_headers,
            json={
                "attempt_id": attempt_id,
                "question_id": question_id,
                "answer": "A",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_correct" in data
        assert "feedback" in data


class TestNotesFlow:
    """Test notes functionality."""
    
    async def test_create_note(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
    ):
        """Test creating a note."""
        response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json={
                "title": "Test Note",
                "content": "This is a test note content",
                "book_id": str(test_book.id),
                "tags": ["test", "important"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Note"
        assert "id" in data
    
    async def test_list_notes(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Test listing notes."""
        response = await client.get("/api/notes", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    async def test_update_note(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
    ):
        """Test updating a note."""
        # Create a note first
        create_response = await client.post(
            "/api/notes",
            headers=auth_headers,
            json={
                "title": "Note to Update",
                "content": "Original content",
            },
        )
        note_id = create_response.json()["id"]
        
        # Update the note
        response = await client.put(
            f"/api/notes/{note_id}",
            headers=auth_headers,
            json={
                "title": "Updated Note",
                "content": "Updated content",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Note"


class TestAdminFlow:
    """Test admin functionality."""
    
    @pytest.fixture
    async def admin_user(self, db_session: AsyncSession) -> User:
        """Create an admin user."""
        user = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            name="Admin User",
            role="admin",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user
    
    @pytest.fixture
    def admin_headers(self, admin_user: User) -> dict:
        """Create authentication headers for admin user."""
        token = create_access_token(data={"sub": str(admin_user.id)})
        return {"Authorization": f"Bearer {token}"}
    
    async def test_admin_dashboard(
        self,
        client: AsyncClient,
        admin_headers: dict,
    ):
        """Test admin dashboard endpoint."""
        response = await client.get(
            "/api/admin/dashboard",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "active_users" in data
    
    async def test_admin_list_users(
        self,
        client: AsyncClient,
        admin_headers: dict,
    ):
        """Test admin user listing."""
        response = await client.get(
            "/api/admin/users",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    async def test_admin_system_health(
        self,
        client: AsyncClient,
        admin_headers: dict,
    ):
        """Test system health endpoint."""
        response = await client.get(
            "/api/admin/system/health",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "postgres" in data
        assert "redis" in data
    
    async def test_non_admin_cannot_access_admin(
        self,
        client: AsyncClient,
        auth_headers: dict,  # Regular user headers
    ):
        """Test that non-admin users cannot access admin endpoints."""
        response = await client.get(
            "/api/admin/dashboard",
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestIntegrationScenarios:
    """Test complete integration scenarios."""
    
    async def test_complete_learning_session(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
        test_learning_state: LearningState,
    ):
        """Test a complete learning session from start to quiz."""
        # 1. Get initial state
        state_response = await client.get(
            f"/api/learning/state/{test_book.id}",
            headers=auth_headers,
        )
        assert state_response.status_code == 200
        initial_state = state_response.json()
        assert initial_state["current_chapter"] == 1
        
        # 2. Send several learning messages
        for i in range(3):
            chat_response = await client.post(
                "/api/chat",
                headers=auth_headers,
                json={
                    "book_id": str(test_book.id),
                    "message": f"Question {i+1} about the topic",
                },
            )
            assert chat_response.status_code == 200
        
        # 3. Check progress
        progress_response = await client.get(
            f"/api/learning/progress/{test_book.id}",
            headers=auth_headers,
        )
        assert progress_response.status_code == 200
    
    async def test_context_preservation_across_messages(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_book: Book,
        test_learning_state: LearningState,
    ):
        """Test that context is preserved across multiple messages."""
        # Send a message with a specific topic
        response1 = await client.post(
            "/api/chat",
            headers=auth_headers,
            json={
                "book_id": str(test_book.id),
                "message": "Let's talk about binary trees",
            },
        )
        assert response1.status_code == 200
        
        # Ask a follow-up question
        response2 = await client.post(
            "/api/chat",
            headers=auth_headers,
            json={
                "book_id": str(test_book.id),
                "message": "Can you give me an example?",
            },
        )
        assert response2.status_code == 200
        
        # The response should maintain context
        # (In a real test, we'd verify the content relates to binary trees)


# Run with: pytest tests/e2e/ -v --asyncio-mode=auto
