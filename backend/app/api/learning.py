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
    # Day-based tracking (primary)
    current_day: int = 1
    completed_days: List[int] = []
    # Chapter-based tracking (internal)
    current_chapter: int
    current_section: Optional[str]
    completed_chapters: List[int]
    # Settings
    strict_mode: bool
    professor_level: str
    # Metrics
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
        .order_by(LearningState.created_at.desc())
        .limit(1)
    )
    state = result.scalars().first()
    
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
        .order_by(LearningState.created_at.desc())
        .limit(1)
    )
    state = result.scalars().first()
    
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
        .order_by(LearningState.created_at.desc())
        .limit(1)
    )
    state = result.scalars().first()
    
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
    """Comprehensive reset — clears ALL state so the user can start over.

    Resets:
        - LearningState (progress, topics, quiz, summaries, phase)
        - ChatSessions + messages (conversation history)
    """
    from sqlalchemy import update as sql_update

    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == book_id,
        )
        .order_by(LearningState.created_at.desc())
        .limit(1)
    )
    state = result.scalars().first()

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning state not found",
        )

    # ---- LearningState: reset every mutable field ----
    state.current_day = 1
    state.current_chapter = 1
    state.current_section = None
    state.completed_days = []
    state.completed_chapters = []
    state.completed_sections = {}
    state.plan_start_date = None
    state.day_topics_covered = []
    state.summarized_past_context = None
    state.last_topic_discussed = None
    state.pending_topics = None
    state.motivation_score = 1.0
    state.attention_score = 1.0
    state.comprehension_score = 1.0
    state.total_study_time_minutes = 0
    state.missed_sessions = 0
    state.last_session_summary = None
    state.quiz_mode = "none"
    state.pending_quiz_questions = None
    state.current_day_scope_description = None
    if hasattr(state, "current_phase"):
        state.current_phase = "teaching"
    if hasattr(state, "state_version"):
        state.state_version = 0
    if hasattr(state, "day_summaries"):
        state.day_summaries = None
    if hasattr(state, "chapter_summaries"):
        state.chapter_summaries = None
    if hasattr(state, "cumulative_summary"):
        state.cumulative_summary = None

    # Clear learning_plan via raw SQL (JSONB NULL requires this)
    await db.execute(
        sql_update(LearningState)
        .where(LearningState.id == state.id)
        .values(learning_plan=None)
    )

    # ---- ChatSessions: delete for a clean conversation ----
    sessions_result = await db.execute(
        select(ChatSession).where(
            ChatSession.book_id == book_id,
            ChatSession.user_id == user_id,
        )
    )
    for session in sessions_result.scalars().all():
        await db.delete(session)

    await db.commit()

    # ---- Terminate running Temporal workflow so it doesn't use stale state ----
    try:
        from app.temporal.client import get_temporal_client
        from temporalio.client import WorkflowExecutionStatus

        client = await get_temporal_client()
        workflow_id = f"chat-{user_id}-{book_id}"
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status == WorkflowExecutionStatus.RUNNING:
            await handle.terminate(reason="Learning state reset by user")
            logger.info("temporal_workflow_terminated", workflow_id=workflow_id)
    except Exception as e:
        logger.warning("temporal_workflow_terminate_skipped", error=str(e))

    logger.info("learning_state_reset", user_id=str(user_id), book_id=str(book_id))

    return {"message": "Learning state reset successfully"}


class DayProgress(BaseModel):
    """Day progress within a chapter."""
    day: int
    title: str
    is_completed: bool
    is_current: bool
    is_rest: bool = False


class ChapterProgress(BaseModel):
    """Chapter progress with nested days."""
    chapter_number: int
    title: str
    is_completed: bool
    is_current: bool
    days: List[DayProgress] = []


class DetailedProgressResponse(BaseModel):
    """Detailed progress response with chapter->day hierarchy for sidebar."""
    # Current position
    current_day: int = 1
    current_chapter: int = 1
    
    # Completion tracking
    completed_days: List[int] = []
    completed_chapters: List[int] = []
    total_days: int = 1
    total_chapters: int = 1
    
    # Percentages
    day_completion_percentage: float = 0.0
    chapter_completion_percentage: float = 0.0
    
    # Sidebar data: Chapters with nested days
    sidebar_chapters: List[ChapterProgress] = []
    
    # Time tracking
    total_study_time_minutes: int = 0
    
    # Performance metrics
    quiz_pass_rate: float = 0.0
    motivation_score: float = 100.0
    
    # Current phase
    current_phase: str = "greeting"
    
    # Intra-day scope progress
    scope_completion_percentage: float = 0.0
    scope_remaining_topics: List[str] = []
    scope_total_topics: int = 0
    scope_covered_topics: int = 0
    
    # Plan info
    plan_data: Optional[dict] = None


@router.get("/progress/{book_id}/detailed", response_model=DetailedProgressResponse)
async def get_detailed_progress(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed progress with chapter->day hierarchy for sidebar.
    
    Structure: Chapters contain nested days based on the learning plan.
    """
    from app.models.book import Book, BookChapter
    from app.models.quiz import QuizAttempt
    from app.models.learning_config import LearningConfig
    
    result = await db.execute(
        select(LearningState).where(
            LearningState.user_id == user_id,
            LearningState.book_id == book_id,
        )
        .order_by(LearningState.created_at.desc())
        .limit(1)
    )
    state = result.scalars().first()
    
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning state not found",
        )
    
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    total_chapters = book.total_chapters or 1
    
    chapters_result = await db.execute(
        select(BookChapter)
        .where(BookChapter.book_id == book_id)
        .order_by(BookChapter.chapter_number)
    )
    chapters = chapters_result.scalars().all()
    
    current_phase = getattr(state, "current_phase", "greeting") or "greeting"
    
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.learning_state_id == state.id,
            QuizAttempt.completed_at.isnot(None),
        )
    )
    attempts = result.scalars().all()
    quiz_pass_rate = (sum(1 for a in attempts if a.passed) / len(attempts) * 100) if attempts else 0.0
    
    plan_data = state.learning_plan
    current_day = getattr(state, 'current_day', 1) or 1
    current_chapter = state.current_chapter or 1
    completed_days = list(getattr(state, 'completed_days', []) or [])
    completed_chapters = list(state.completed_chapters) if state.completed_chapters else []
    
    # Build sidebar structure: chapters with nested days
    sidebar_chapters: List[ChapterProgress] = []
    chapter_to_days: dict = {}  # Map chapter_number -> list of days
    total_days = 1
    
    if plan_data and "days" in plan_data:
        total_days = plan_data.get("total_days", len(plan_data["days"]))
        
        # Track the last chapter seen for rest days
        last_chapter_seen = 1
        
        # Group days by chapter
        for day_data in plan_data["days"]:
            day_num = day_data.get("day", 0)
            is_rest = day_data.get("rest", False)
            day_title = day_data.get("day_title", f"Day {day_num}")
            
            day_progress = DayProgress(
                day=day_num,
                title=day_title,
                is_completed=day_num in completed_days,
                is_current=day_num == current_day,
                is_rest=is_rest,
            )
            
            # Get chapters for this day
            items = day_data.get("items", [])
            if items:
                for item in items:
                    ch_num = item.get("chapter_number")
                    if ch_num:
                        last_chapter_seen = ch_num
                        if ch_num not in chapter_to_days:
                            chapter_to_days[ch_num] = []
                        chapter_to_days[ch_num].append(day_progress)
            else:
                # Rest/review days go under the last chapter seen
                if last_chapter_seen not in chapter_to_days:
                    chapter_to_days[last_chapter_seen] = []
                chapter_to_days[last_chapter_seen].append(day_progress)
    
    # Build chapter list with nested days
    for ch in chapters:
        ch_num = ch.chapter_number
        days_for_chapter = chapter_to_days.get(ch_num, [])
        
        sidebar_chapters.append(ChapterProgress(
            chapter_number=ch_num,
            title=ch.title or f"Chapter {ch_num}",
            is_completed=ch_num in completed_chapters,
            is_current=ch_num == current_chapter,
            days=days_for_chapter,
        ))
    
    day_pct = (len(completed_days) / total_days * 100) if total_days > 0 else 0
    chapter_pct = (len(completed_chapters) / total_chapters * 100) if total_chapters > 0 else 0
    
    # Compute intra-day scope progress
    scope_completion_percentage = 0.0
    scope_remaining_topics: List[str] = []
    scope_total_topics = 0
    scope_covered_topics = 0
    
    if plan_data:
        from app.services.scope_service import (
            extract_scope_from_plan,
            update_scope_coverage,
        )
        scope = extract_scope_from_plan(plan_data, current_day)
        topics_covered = list(state.pending_topics or [])
        scope = update_scope_coverage(scope, topics_covered)
        scope_completion_percentage = scope.completion_percentage
        scope_remaining_topics = [i.topic_name for i in scope.remaining_items]
        scope_total_topics = scope.total_items
        scope_covered_topics = scope.covered_items
    
    return DetailedProgressResponse(
        current_day=current_day,
        current_chapter=current_chapter,
        completed_days=completed_days,
        completed_chapters=completed_chapters,
        total_days=total_days,
        total_chapters=total_chapters,
        day_completion_percentage=round(day_pct, 1),
        chapter_completion_percentage=round(chapter_pct, 1),
        sidebar_chapters=sidebar_chapters,
        total_study_time_minutes=state.total_study_time_minutes,
        quiz_pass_rate=round(quiz_pass_rate, 1),
        motivation_score=round(state.motivation_score * 100, 1),
        current_phase=current_phase,
        scope_completion_percentage=round(scope_completion_percentage, 1),
        scope_remaining_topics=scope_remaining_topics,
        scope_total_topics=scope_total_topics,
        scope_covered_topics=scope_covered_topics,
        plan_data=plan_data,
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
        .order_by(LearningState.created_at.desc())
        .limit(1)
    )
    state = result.scalars().first()
    
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


