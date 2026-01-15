"""Learning state and progress API routes."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies import get_current_user_id, get_redis
from app.logs.logger import get_logger
from app.models.learning import LearningState, ProgressSnapshot
from app.models.chat import ChatSession, ChatMessage
from app.models.book import Book

logger = get_logger(__name__)
router = APIRouter()


class LearningStateResponse(BaseModel):
    """Learning state response model."""
    id: UUID
    book_id: Optional[UUID]
    goal_id: Optional[UUID]
    current_chapter: int
    current_section: Optional[str]
    completed_chapters: List[int]
    strict_mode: bool
    professor_level: str
    motivation_score: float
    attention_score: float
    comprehension_score: float
    total_study_time_minutes: int
    quiz_mode: str
    last_active_at: Optional[datetime]

    class Config:
        from_attributes = True


class LearningStateUpdate(BaseModel):
    """Learning state update request."""
    strict_mode: Optional[bool] = None
    professor_level: Optional[str] = None  # beginner, intermediate, advanced


class ProgressResponse(BaseModel):
    """Progress response model."""
    chapter_progress: int
    total_chapters: int
    completion_percentage: float
    total_study_time_minutes: int
    quiz_pass_rate: float
    avg_attention_score: float
    avg_comprehension_score: float


@router.get("/state", response_model=List[LearningStateResponse])
async def list_learning_states(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all learning states for the user."""
    result = await db.execute(
        select(LearningState)
        .where(LearningState.user_id == user_id)
        .order_by(LearningState.last_active_at.desc().nullslast())
    )
    states = result.scalars().all()
    return states


@router.get("/state/{book_id}", response_model=LearningStateResponse)
async def get_learning_state(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get learning state for a specific book."""
    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == book_id,
        )
    )
    state = result.scalar_one_or_none()
    
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning state not found",
        )
    
    return state


@router.patch("/state/{book_id}", response_model=LearningStateResponse)
async def update_learning_state(
    book_id: UUID,
    updates: LearningStateUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update learning state settings."""
    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == book_id,
        )
    )
    state = result.scalar_one_or_none()
    
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning state not found",
        )
    
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(state, field, value)
    
    await db.commit()
    await db.refresh(state)
    
    logger.info(
        "learning_state_updated",
        user_id=str(user_id),
        book_id=str(book_id),
        fields=list(update_data.keys()),
    )
    
    return state


@router.get("/progress/{book_id}", response_model=ProgressResponse)
async def get_progress(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed progress for a book."""
    from app.models.book import Book
    from app.models.quiz import QuizAttempt
    
    # Get learning state
    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == book_id,
        )
    )
    state = result.scalar_one_or_none()
    
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning state not found",
        )
    
    # Get book total chapters
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    total_chapters = book.total_chapters or 1
    
    # Calculate quiz pass rate
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.learning_state_id == state.id,
            QuizAttempt.completed_at.isnot(None),
        )
    )
    attempts = result.scalars().all()
    
    if attempts:
        quiz_pass_rate = sum(1 for a in attempts if a.passed) / len(attempts)
    else:
        quiz_pass_rate = 0.0
    
    # Calculate completion percentage
    completed_count = len(state.completed_chapters) if state.completed_chapters else 0
    completion_percentage = (completed_count / total_chapters) * 100
    
    return ProgressResponse(
        chapter_progress=completed_count,
        total_chapters=total_chapters,
        completion_percentage=round(completion_percentage, 1),
        total_study_time_minutes=state.total_study_time_minutes,
        quiz_pass_rate=round(quiz_pass_rate * 100, 1),
        avg_attention_score=round(state.attention_score * 100, 1),
        avg_comprehension_score=round(state.comprehension_score * 100, 1),
    )


@router.post("/state/{book_id}/reset")
async def reset_learning_state(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Reset learning state (start over)."""
    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == book_id,
        )
    )
    state = result.scalar_one_or_none()
    
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning state not found",
        )
    
    # Reset state
    state.current_chapter = 1
    state.current_section = None
    state.completed_chapters = []
    state.completed_sections = {}
    state.summarized_past_context = None
    state.last_topic_discussed = None
    state.pending_topics = None
    state.motivation_score = 1.0
    state.attention_score = 1.0
    state.comprehension_score = 1.0
    state.total_study_time_minutes = 0
    state.quiz_mode = "none"
    state.pending_quiz_questions = None
    
    await db.commit()
    
    logger.info("learning_state_reset", user_id=str(user_id), book_id=str(book_id))
    
    return {"message": "Learning state reset successfully"}


class DetailedProgressResponse(BaseModel):
    """Detailed progress response with chapter-by-chapter tracking."""
    # Overall progress
    completed_chapters: List[int]
    total_chapters: int
    completion_percentage: float
    current_chapter: int
    
    # Time tracking
    total_study_time_minutes: int
    avg_time_per_chapter: float
    
    # Performance metrics
    quiz_pass_rate: float
    avg_attention_score: float
    avg_comprehension_score: float
    motivation_score: float
    
    # Chapter details
    chapter_summaries: List[dict]
    
    # Current phase
    current_phase: str
    
    # Plan info
    plan_data: Optional[dict] = None
    estimated_completion_date: Optional[str] = None


@router.get("/progress/{book_id}/detailed", response_model=DetailedProgressResponse)
async def get_detailed_progress(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed progress with chapter-by-chapter tracking.
    
    Includes:
    - Per-chapter completion status
    - Time spent on each chapter
    - Quiz scores per chapter
    - Overall metrics
    - Current learning phase
    """
    from app.models.book import Book, BookChapter
    from app.models.quiz import QuizAttempt
    from app.models.learning_config import ConversationState, LearningConfig
    
    # Get learning state
    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == book_id,
        )
    )
    state = result.scalar_one_or_none()
    
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning state not found",
        )
    
    # Get book with chapters
    result = await db.execute(
        select(Book).where(Book.id == book_id)
    )
    book = result.scalar_one_or_none()
    total_chapters = book.total_chapters or 1
    
    # Get chapters
    chapters_result = await db.execute(
        select(BookChapter)
        .where(BookChapter.book_id == book_id)
        .order_by(BookChapter.chapter_number)
    )
    chapters = chapters_result.scalars().all()
    
    # Get conversation state for current phase
    conv_result = await db.execute(
        select(ConversationState)
        .where(ConversationState.user_id == user_id)
        .where(ConversationState.book_id == book_id)
    )
    conv_state = conv_result.scalar_one_or_none()
    current_phase = conv_state.phase if conv_state else "greeting"
    
    # Get learning config for plan data
    config_result = await db.execute(
        select(LearningConfig).where(LearningConfig.book_id == book_id)
    )
    config = config_result.scalar_one_or_none()
    
    # Calculate quiz pass rate
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.learning_state_id == state.id,
            QuizAttempt.completed_at.isnot(None),
        )
    )
    attempts = result.scalars().all()
    
    quiz_pass_rate = 0.0
    if attempts:
        quiz_pass_rate = sum(1 for a in attempts if a.passed) / len(attempts)
    
    # Calculate completion percentage
    completed_list = list(state.completed_chapters) if state.completed_chapters else []
    completed_count = len(completed_list)
    completion_percentage = (completed_count / total_chapters) * 100
    
    # Calculate average time per chapter
    avg_time = state.total_study_time_minutes / completed_count if completed_count > 0 else 0
    
    # Build chapter summaries
    chapter_summaries = []
    for ch in chapters:
        is_completed = ch.chapter_number in completed_list
        chapter_summaries.append({
            "chapter_number": ch.chapter_number,
            "title": ch.title or f"Chapter {ch.chapter_number}",
            "is_completed": is_completed,
            "is_current": ch.chapter_number == state.current_chapter,
            "summary": ch.summary,
            "estimated_duration_minutes": ch.estimated_duration_minutes or 45,
        })
    
    # Get plan data if available
    plan_data = None
    estimated_completion = None
    if config:
        if config.deadline:
            estimated_completion = config.deadline.isoformat()
    
    return DetailedProgressResponse(
        completed_chapters=completed_list,
        total_chapters=total_chapters,
        completion_percentage=round(completion_percentage, 1),
        current_chapter=state.current_chapter,
        total_study_time_minutes=state.total_study_time_minutes,
        avg_time_per_chapter=round(avg_time, 1),
        quiz_pass_rate=round(quiz_pass_rate * 100, 1),
        avg_attention_score=round(state.attention_score * 100, 1),
        avg_comprehension_score=round(state.comprehension_score * 100, 1),
        motivation_score=round(state.motivation_score * 100, 1),
        chapter_summaries=chapter_summaries,
        current_phase=current_phase,
        plan_data=plan_data,
        estimated_completion_date=estimated_completion,
    )


@router.post("/state/{book_id}/advance-chapter")
async def advance_chapter(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually advance to the next chapter (for testing/admin).
    In production, this is controlled by quiz results.
    """
    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == book_id,
        )
    )
    state = result.scalar_one_or_none()
    
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning state not found",
        )
    
    # Get book total chapters
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    total_chapters = book.total_chapters or 1
    
    if state.current_chapter >= total_chapters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already at the last chapter",
        )
    
    # Mark current chapter as completed and advance
    completed = list(state.completed_chapters) if state.completed_chapters else []
    if state.current_chapter not in completed:
        completed.append(state.current_chapter)
    
    state.completed_chapters = completed
    state.current_chapter += 1
    state.current_section = None
    state.pending_topics = None
    
    await db.commit()
    
    logger.info(
        "chapter_advanced",
        user_id=str(user_id),
        book_id=str(book_id),
        new_chapter=state.current_chapter,
    )
    
    return {"message": f"Advanced to chapter {state.current_chapter}"}


# ============================================================================
# PROFESSOR-DRIVEN LEARNING SESSION API
# ============================================================================

class StartSessionRequest(BaseModel):
    """Request to start a learning session."""
    book_id: UUID
    target_chapters: int = 5  # How many chapters to cover in this session


class StartSessionResponse(BaseModel):
    """Response after starting a learning session."""
    session_id: UUID
    workflow_id: str
    current_chapter: int
    message: str


class StudentResponseRequest(BaseModel):
    """Student's response to professor."""
    session_id: UUID
    message: str


class StudentResponseResponse(BaseModel):
    """Acknowledgment of student response."""
    success: bool
    message: str


class PendingMessagesResponse(BaseModel):
    """Response with pending professor messages."""
    messages: List[dict]
    has_more: bool


@router.post("/session/start", response_model=StartSessionResponse)
async def start_learning_session(
    request: StartSessionRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
):
    """
    Start a new professor-driven learning session.
    
    This creates a chat session and starts a Temporal workflow
    that drives the teaching process.
    """
    from app.temporal.client import get_temporal_client
    from app.temporal.workflows.learning_session import LearningSessionWorkflow
    from app.config import settings
    
    # Check book exists and is ready
    result = await db.execute(
        select(Book).where(Book.id == request.book_id)
    )
    book = result.scalar_one_or_none()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    if book.processing_status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Book is not ready for learning. Status: {book.processing_status}",
        )
    
    # Get or create learning state
    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == request.book_id,
        )
    )
    learning_state = result.scalar_one_or_none()
    
    if not learning_state:
        learning_state = LearningState(
            user_id=user_id,
            book_id=request.book_id,
            current_chapter=1,
            completed_chapters=[],
        )
        db.add(learning_state)
        await db.flush()
    
    # Create chat session
    session = ChatSession(
        user_id=user_id,
        learning_state_id=learning_state.id,
        book_id=request.book_id,
        chapter_context=learning_state.current_chapter,
        session_type="learning",
    )
    db.add(session)
    await db.commit()
    
    # Generate workflow ID
    workflow_id = f"learning-{user_id}-{request.book_id}-{session.id}"
    
    # Start Temporal workflow
    try:
        client = await get_temporal_client()
        
        await client.start_workflow(
            LearningSessionWorkflow.run,
            args=[
                str(user_id),
                str(request.book_id),
                str(session.id),
                learning_state.current_chapter,
                request.target_chapters,
            ],
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
        )
        
        logger.info(
            "learning_session_started",
            user_id=str(user_id),
            book_id=str(request.book_id),
            session_id=str(session.id),
            workflow_id=workflow_id,
        )
        
    except Exception as e:
        logger.exception("failed_to_start_workflow", error=str(e))
        # Even if workflow fails, we can still use the session for traditional chat
        workflow_id = "fallback"
    
    return StartSessionResponse(
        session_id=session.id,
        workflow_id=workflow_id,
        current_chapter=learning_state.current_chapter,
        message=f"Learning session started! Professor will begin teaching Chapter {learning_state.current_chapter}.",
    )


@router.post("/session/respond", response_model=StudentResponseResponse)
async def respond_to_professor(
    request: StudentResponseRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
):
    """
    Submit a response to the professor's teaching or questions.
    
    This stores the message and signals the Temporal workflow.
    """
    from app.temporal.client import get_temporal_client
    from app.temporal.workflows.learning_session import LearningSessionWorkflow
    
    # Verify session belongs to user
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == request.session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Store the message
    message = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.message,
        chapter_at_time=session.chapter_context,
    )
    db.add(message)
    
    session.message_count += 1
    session.last_message_at = datetime.utcnow()
    
    await db.commit()
    
    # Push to Redis for workflow to pick up
    await redis.lpush(
        f"session:{session.id}:student_responses",
        json.dumps({
            "content": request.message,
            "timestamp": datetime.utcnow().isoformat(),
        })
    )
    await redis.expire(f"session:{session.id}:student_responses", 3600)
    
    # Signal the workflow if it exists
    try:
        client = await get_temporal_client()
        workflow_id = f"learning-{user_id}-{session.book_id}-{session.id}"
        
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(LearningSessionWorkflow.student_response, request.message)
        
        logger.info(
            "student_response_sent",
            session_id=str(session.id),
            workflow_id=workflow_id,
        )
        
    except Exception as e:
        # Workflow might not exist (using fallback mode)
        logger.warning("workflow_signal_failed", error=str(e))
    
    return StudentResponseResponse(
        success=True,
        message="Response received. Professor is processing...",
    )


@router.get("/session/{session_id}/messages", response_model=PendingMessagesResponse)
async def get_pending_messages(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
):
    """
    Get pending messages from the professor.
    
    This is used for polling to receive professor messages.
    For real-time, use WebSocket subscription.
    """
    # Verify session belongs to user
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Get pending messages from Redis
    messages = []
    while True:
        msg = await redis.rpop(f"session:{session_id}:pending")
        if not msg:
            break
        messages.append(json.loads(msg))
        if len(messages) >= 10:  # Limit per request
            break
    
    # Check if more messages exist
    remaining = await redis.llen(f"session:{session_id}:pending")
    
    return PendingMessagesResponse(
        messages=messages,
        has_more=remaining > 0,
    )


@router.post("/session/{session_id}/pause")
async def pause_session(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Pause the current learning session.
    
    The session can be resumed later from where it stopped.
    """
    from app.temporal.client import get_temporal_client
    from app.temporal.workflows.learning_session import LearningSessionWorkflow
    
    # Verify session
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Signal the workflow to pause
    try:
        client = await get_temporal_client()
        workflow_id = f"learning-{user_id}-{session.book_id}-{session.id}"
        
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(LearningSessionWorkflow.pause_session)
        
        logger.info("session_paused", session_id=str(session_id))
        
    except Exception as e:
        logger.warning("pause_signal_failed", error=str(e))
    
    return {"message": "Session paused. Your progress has been saved."}


@router.post("/session/{session_id}/end")
async def end_session(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    End the current learning session.
    """
    from app.temporal.client import get_temporal_client
    from app.temporal.workflows.learning_session import LearningSessionWorkflow
    
    # Verify session
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    # Mark session as inactive
    session.is_active = False
    await db.commit()
    
    # Signal workflow to end
    try:
        client = await get_temporal_client()
        workflow_id = f"learning-{user_id}-{session.book_id}-{session.id}"
        
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(LearningSessionWorkflow.end_session)
        
    except Exception as e:
        logger.warning("end_signal_failed", error=str(e))
    
    logger.info("session_ended", session_id=str(session_id))
    
    return {"message": "Session ended. Your progress has been saved."}
