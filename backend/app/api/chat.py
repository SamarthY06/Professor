"""
Chat API routes - Updated for Agent-Driven Architecture.

Key Changes:
1. Uses simplified state from LearningState (single source of truth)
2. Persists state after each interaction
3. Updates last_active_at for inactivity tracking
4. Works with new phase system
5. Caches learning state and book info for performance
"""

import time
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.dependencies import get_current_user_id, get_redis
from app.logs.logger import get_logger
from app.models.chat import ChatSession, ChatMessage
from app.models.learning import LearningState
from app.services.cache_service import get_cache_service

logger = get_logger(__name__)
router = APIRouter()
cache = get_cache_service()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ChatRequest(BaseModel):
    """Chat message request."""
    message: str
    session_id: Optional[UUID] = None
    book_id: Optional[UUID] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    message: str
    session_id: UUID
    phase: str
    chapter: int
    agent_name: str
    latency_ms: int


class MessageResponse(BaseModel):
    """Message response model."""
    id: UUID
    role: str
    content: str
    agent_name: Optional[str]
    is_quiz_question: bool
    quiz_answer_correct: Optional[bool]
    created_at: datetime

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    """Session response model."""
    id: UUID
    book_id: Optional[UUID]
    chapter_context: Optional[int]
    session_type: str
    is_active: bool
    message_count: int
    created_at: datetime
    last_message_at: Optional[datetime]

    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    """Session detail with messages."""
    messages: List[MessageResponse]


class InitSessionResponse(BaseModel):
    """Response for initializing/getting a learning session."""
    session_id: UUID
    phase: str
    current_chapter: int
    messages: List[MessageResponse]
    has_greeting: bool
    book_title: str
    total_chapters: int
    progress: dict


# ============================================================================
# MAIN CHAT ENDPOINT
# ============================================================================

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
):
    """
    Send a message to Professor.
    
    This is the main chat endpoint that routes through the agent-driven system.
    """
    start_time = time.time()
    
    # Validate input
    if request.session_id is None and request.book_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either session_id or book_id must be provided",
        )
    
    # Get or create session
    if request.session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == request.session_id,
                ChatSession.user_id == user_id,
            )
        )
        session = result.scalar_one_or_none()
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        book_id = session.book_id
    else:
        book_id = request.book_id
        # Get or create learning state and session
        learning_state = await _get_or_create_learning_state(db, user_id, book_id)
        
        # Find existing session or create new
        session_result = await db.execute(
            select(ChatSession)
            .where(ChatSession.book_id == book_id)
            .where(ChatSession.user_id == user_id)
            .where(ChatSession.is_active == True)
            .order_by(ChatSession.created_at.desc())
        )
        session = session_result.scalar()
        
        if session is None:
            session = ChatSession(
                user_id=user_id,
                learning_state_id=learning_state.id,
                book_id=book_id,
                chapter_context=learning_state.current_chapter,
                session_type="learning",
            )
            db.add(session)
            await db.flush()
    
    # Save user message
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.message,
        chapter_at_time=session.chapter_context,
    )
    db.add(user_message)
    
    # Get learning state
    result = await db.execute(
        select(LearningState).where(LearningState.id == session.learning_state_id)
    )
    learning_state = result.scalar_one()
    
    # Get API key
    from app.services.api_key_service import APIKeyService
    api_key_service = APIKeyService(db)
    api_key = None
    try:
        api_key = await api_key_service.get_api_key_for_user(user_id)
    except ValueError:
        pass
    
    # Build current state from LearningState
    current_state = await _build_state_from_learning_state(learning_state, api_key, db)
    
    # Process through agent-driven system
    from app.langgraph.graph import process_message
    
    response_data = await process_message(
        user_id=str(user_id),
        session_id=str(session.id),
        book_id=str(book_id),
        message=request.message,
        current_state=current_state,
    )
    
    # Update learning state from response
    new_state = response_data.get("state", {})
    await _update_learning_state(db, learning_state, new_state)
    
    # Update last_active_at (critical for inactivity detection)
    learning_state.last_active_at = datetime.utcnow()
    
    # Save assistant message
    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=response_data.get("response", ""),
        agent_name=response_data.get("agent_name", "Professor"),
        chapter_at_time=new_state.get("current_chapter", learning_state.current_chapter),
        is_quiz_question=response_data.get("response_type") == "quiz_question",
        latency_ms=int((time.time() - start_time) * 1000),
    )
    db.add(assistant_message)
    
    # Update session
    session.message_count += 2
    session.last_message_at = datetime.utcnow()
    session.chapter_context = new_state.get("current_chapter", session.chapter_context)
    
    await db.commit()
    
    latency_ms = int((time.time() - start_time) * 1000)
    
    logger.info(
        "chat_completed",
        user_id=str(user_id),
        session_id=str(session.id),
        phase=response_data.get("phase"),
        latency_ms=latency_ms,
    )
    
    return ChatResponse(
        message=response_data.get("response", ""),
        session_id=session.id,
        phase=response_data.get("phase", "teaching"),
        chapter=new_state.get("current_chapter", learning_state.current_chapter),
        agent_name=response_data.get("agent_name", "Professor"),
        latency_ms=latency_ms,
    )


# ============================================================================
# SESSION INITIALIZATION
# ============================================================================

@router.get("/init/{book_id}", response_model=InitSessionResponse)
async def init_or_get_session(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Initialize or get existing learning session for a book.
    
    Returns the session with messages and current state.
    """
    from app.models.book import Book
    from app.services.progress import get_progress_summary
    
    # Get book
    book_result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = book_result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    # Check if book processing is complete
    if book.processing_status not in ["completed", "ready_for_planning", "ready"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Book is still processing: {book.processing_status}",
        )
    
    # Get or create learning state
    learning_state = await _get_or_create_learning_state(db, user_id, book_id)
    
    # Get or create session
    sessions_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.book_id == book_id, ChatSession.user_id == user_id)
        .options(selectinload(ChatSession.messages))
        .order_by(ChatSession.created_at.desc())
    )
    session = sessions_result.scalar()
    
    if session is None:
        # Create new session
        session = ChatSession(
            user_id=user_id,
            learning_state_id=learning_state.id,
            book_id=book_id,
            chapter_context=learning_state.current_chapter,
            session_type="learning",
        )
        db.add(session)
        await db.flush()
        
        # Reload with messages
        sessions_result = await db.execute(
            select(ChatSession)
            .where(ChatSession.id == session.id)
            .options(selectinload(ChatSession.messages))
        )
        session = sessions_result.scalar()
    
    # Determine phase
    phase = _determine_phase(learning_state, session)
    
    # Check for greeting
    has_greeting = any(
        m.role == "assistant" and m.agent_name in ["Professor", "GreetingAgent"]
        for m in session.messages
    )
    
    # Build progress summary
    state_dict = await _build_state_from_learning_state(learning_state, None, db)
    progress = get_progress_summary(state_dict)
    
    await db.commit()
    
    return InitSessionResponse(
        session_id=session.id,
        phase=phase,
        current_chapter=learning_state.current_chapter,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                agent_name=m.agent_name,
                is_quiz_question=m.is_quiz_question,
                quiz_answer_correct=m.quiz_answer_correct,
                created_at=m.created_at,
            )
            for m in sorted(session.messages, key=lambda x: x.created_at)
        ],
        has_greeting=has_greeting,
        book_title=book.title,
        total_chapters=book.total_chapters or 0,
        progress=progress,
    )


# ============================================================================
# OTHER ENDPOINTS
# ============================================================================

@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    book_id: Optional[UUID] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List chat sessions for the user."""
    conditions = [ChatSession.user_id == user_id]
    
    if book_id:
        conditions.append(ChatSession.book_id == book_id)
    
    result = await db.execute(
        select(ChatSession)
        .where(and_(*conditions))
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    
    return sessions


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get session details with messages."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .options(selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    return SessionDetailResponse(
        id=session.id,
        book_id=session.book_id,
        chapter_context=session.chapter_context,
        session_type=session.session_type,
        is_active=session.is_active,
        message_count=session.message_count,
        created_at=session.created_at,
        last_message_at=session.last_message_at,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                agent_name=m.agent_name,
                is_quiz_question=m.is_quiz_question,
                quiz_answer_correct=m.quiz_answer_correct,
                created_at=m.created_at,
            )
            for m in sorted(session.messages, key=lambda x: x.created_at)
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    await db.delete(session)
    await db.commit()
    
    return {"message": "Session deleted"}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _get_or_create_learning_state(
    db: AsyncSession,
    user_id: UUID,
    book_id: UUID,
) -> LearningState:
    """Get or create a learning state for the user's book."""
    # Try cache first
    cache_key = f"learning_state:{user_id}:{book_id}"
    
    result = await db.execute(
        select(LearningState)
        .where(LearningState.user_id == user_id)
        .where(LearningState.book_id == book_id)
    )
    learning_state = result.scalar_one_or_none()
    
    if learning_state is None:
        # Get book info for defaults
        from app.models.book import Book
        from app.models.learning_config import LearningConfig
        
        book_result = await db.execute(select(Book).where(Book.id == book_id))
        book = book_result.scalar_one_or_none()
        
        config_result = await db.execute(
            select(LearningConfig).where(LearningConfig.book_id == book_id)
        )
        config = config_result.scalar_one_or_none()
        
        learning_state = LearningState(
            user_id=user_id,
            book_id=book_id,
            current_chapter=1,
            completed_chapters=[],
            professor_level=config.learning_level if config else "intermediate",
            motivation_score=1.0,
            attention_score=1.0,
            comprehension_score=1.0,
            total_study_time_minutes=0,
        )
        db.add(learning_state)
        await db.flush()
        
        # Invalidate cache since we created new state
        await cache.delete(cache_key)
    
    return learning_state


async def _get_cached_book_info(
    db: AsyncSession,
    book_id: UUID,
) -> Optional[dict]:
    """Get book info with caching."""
    from app.models.book import Book
    
    cache_key = f"book_info:{book_id}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    
    if book:
        book_info = {
            "id": str(book.id),
            "title": book.title,
            "total_chapters": book.total_chapters,
            "processing_status": book.processing_status,
        }
        await cache.set(cache_key, book_info, 3600)  # Cache for 1 hour
        return book_info
    
    return None


async def _build_state_from_learning_state(
    learning_state: LearningState,
    api_key: Optional[str],
    db: AsyncSession,
) -> dict:
    """Build ProfessorState dict from LearningState model."""
    from app.models.book import Book
    
    # Get book info for total_chapters
    book_result = await db.execute(
        select(Book).where(Book.id == learning_state.book_id)
    )
    book = book_result.scalar_one_or_none()
    total_chapters = book.total_chapters if book else 1
    book_title = book.title if book else "Learning Material"
    
    return {
        "user_id": str(learning_state.user_id),
        "book_id": str(learning_state.book_id),
        "book_title": book_title,
        "total_chapters": total_chapters,
        "current_chapter": learning_state.current_chapter,
        "chapters_completed": list(learning_state.completed_chapters or []),
        "learning_level": learning_state.professor_level or "intermediate",
        "motivation_score": learning_state.motivation_score or 1.0,
        "attention_score": learning_state.attention_score or 1.0,
        "comprehension_score": learning_state.comprehension_score or 1.0,
        "total_study_time_minutes": learning_state.total_study_time_minutes or 0,
        "topics_covered_this_chapter": list(learning_state.pending_topics or []),
        "session_message_count": learning_state.total_study_time_minutes // 2 if learning_state.total_study_time_minutes else 0,  # Estimate from study time
        "quiz_questions": learning_state.pending_quiz_questions.get("questions", []) if learning_state.pending_quiz_questions else [],
        "quiz_current_index": learning_state.pending_quiz_questions.get("current_index", 0) if learning_state.pending_quiz_questions else 0,
        "quiz_scores": learning_state.pending_quiz_questions.get("scores", []) if learning_state.pending_quiz_questions else [],
        "awaiting_quiz_decision": learning_state.pending_quiz_questions.get("awaiting_decision", False) if learning_state.pending_quiz_questions else False,
        "plan_data": learning_state.learning_plan,
        "plan_accepted": learning_state.learning_plan is not None,
        "api_key": api_key,
        "phase": _determine_phase_from_state(learning_state),
    }


def _determine_phase(learning_state: LearningState, session: ChatSession) -> str:
    """Determine current phase based on state."""
    # Check if we have messages
    if not session.messages:
        return "greeting"
    
    # Check if plan exists
    if not learning_state.learning_plan:
        return "planning" if len(session.messages) > 1 else "greeting"
    
    # Check if in quiz
    if learning_state.pending_quiz_questions:
        return "quiz"
    
    # Check if completed
    total_chapters = len(learning_state.completed_chapters or [])
    # This is a simplification - would need book.total_chapters
    
    return "teaching"


def _determine_phase_from_state(learning_state: LearningState) -> str:
    """Determine phase from learning state alone."""
    # Check quiz_mode first - it's the most reliable indicator
    quiz_mode = learning_state.quiz_mode
    
    if quiz_mode == "chapter_transition":
        return "chapter_transition"
    
    if quiz_mode == "quiz_feedback":
        return "quiz_feedback"
    
    if quiz_mode in ["chapter_quiz", "attention_quiz"]:
        return "quiz"
    
    if not learning_state.learning_plan:
        return "greeting"
    
    if learning_state.pending_quiz_questions:
        return "quiz"
    
    return "teaching"


async def _update_learning_state(
    db: AsyncSession,
    learning_state: LearningState,
    new_state: dict,
) -> None:
    """Update learning state from response state."""
    # Update basic fields
    if "current_chapter" in new_state:
        learning_state.current_chapter = new_state["current_chapter"]
    
    if "chapters_completed" in new_state:
        learning_state.completed_chapters = new_state["chapters_completed"]
    
    if "motivation_score" in new_state:
        learning_state.motivation_score = new_state["motivation_score"]
    
    if "attention_score" in new_state:
        learning_state.attention_score = new_state["attention_score"]
    
    if "comprehension_score" in new_state:
        learning_state.comprehension_score = new_state["comprehension_score"]
    
    if "total_study_time_minutes" in new_state:
        learning_state.total_study_time_minutes = new_state["total_study_time_minutes"]
    
    if "plan_data" in new_state:
        learning_state.learning_plan = new_state["plan_data"]
    
    # Update topics covered
    if "topics_covered_this_chapter" in new_state:
        learning_state.pending_topics = new_state["topics_covered_this_chapter"]
    
    # Update quiz state
    phase = new_state.get("phase", "teaching")
    
    if new_state.get("quiz_questions"):
        learning_state.pending_quiz_questions = {
            "questions": new_state.get("quiz_questions", []),
            "current_index": new_state.get("quiz_current_index", 0),
            "scores": new_state.get("quiz_scores", []),
            "awaiting_decision": new_state.get("awaiting_quiz_decision", False),
        }
        learning_state.quiz_mode = "chapter_quiz"
    elif phase == "quiz_feedback":
        learning_state.quiz_mode = "quiz_feedback"
    elif phase == "chapter_transition":
        learning_state.quiz_mode = "chapter_transition"
        learning_state.pending_quiz_questions = None
    elif phase in ["quiz"]:
        # Phase is quiz but no questions yet - mark as pending quiz
        learning_state.quiz_mode = "chapter_quiz"
    else:
        # Clear quiz state when not in quiz
        learning_state.pending_quiz_questions = None
        learning_state.quiz_mode = "none"
