"""
Progress Tracking Utility Functions.

These are simple Python functions, NOT an agent.
No LLM calls - just arithmetic and database updates.

Replaces the old ProgressAgent with efficient utility functions.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# SCORE UPDATE FUNCTIONS
# ============================================================================

def update_study_time(state: Dict[str, Any], minutes: int = 2) -> Dict[str, Any]:
    """
    Update total study time.
    
    Called after each teaching interaction.
    Default 2 minutes per message exchange.
    
    Args:
        state: Current state dict
        minutes: Minutes to add (default 2)
        
    Returns:
        Updated state dict
    """
    current = state.get("total_study_time_minutes", 0)
    state["total_study_time_minutes"] = current + minutes
    return state


def update_attention_score(state: Dict[str, Any], correct: bool) -> Dict[str, Any]:
    """
    Update attention score based on attention question result.
    
    Args:
        state: Current state dict
        correct: Whether the attention question was answered correctly
        
    Returns:
        Updated state dict
    """
    current = state.get("attention_score", 1.0)
    
    if correct:
        new_score = min(1.0, current + 0.1)
    else:
        new_score = max(0.0, current - 0.15)
    
    state["attention_score"] = new_score
    return state


def update_comprehension_score(state: Dict[str, Any], quiz_score: float) -> Dict[str, Any]:
    """
    Update comprehension score based on quiz result.
    
    Uses blending: 30% old score + 70% new quiz score.
    This weights recent performance more heavily.
    
    Args:
        state: Current state dict
        quiz_score: Quiz score (0-1)
        
    Returns:
        Updated state dict
    """
    current = state.get("comprehension_score", 1.0)
    new_score = 0.3 * current + 0.7 * quiz_score
    state["comprehension_score"] = max(0.0, min(1.0, new_score))
    return state


def update_motivation_score(state: Dict[str, Any], event: str) -> Dict[str, Any]:
    """
    Update motivation score based on events.
    
    Events and their effects:
    - chapter_complete: +0.2
    - quiz_passed: +0.15
    - quiz_failed: -0.1
    - active_session: +0.05 (when message_count > 5)
    - missed_session: -0.1
    - returned_after_break: +0.1
    - motivation_shown: +0.1 (after encouragement displayed)
    
    Args:
        state: Current state dict
        event: Event type string
        
    Returns:
        Updated state dict
    """
    deltas = {
        "chapter_complete": 0.2,
        "quiz_passed": 0.15,
        "quiz_failed": -0.1,
        "active_session": 0.05,
        "missed_session": -0.1,
        "returned_after_break": 0.1,
        "motivation_shown": 0.1,
    }
    
    delta = deltas.get(event, 0)
    current = state.get("motivation_score", 1.0)
    new_score = max(0.0, min(1.0, current + delta))
    state["motivation_score"] = new_score
    
    logger.debug(
        "motivation_score_updated",
        event=event,
        old_score=current,
        new_score=new_score,
    )
    
    return state


# ============================================================================
# TOPIC TRACKING FUNCTIONS
# ============================================================================

def add_topic_covered(state: Dict[str, Any], topic: str) -> Dict[str, Any]:
    """
    Add a topic to the list of covered topics.
    
    Implements context windowing - if list gets too long,
    older topics are summarized.
    
    Args:
        state: Current state dict
        topic: Topic to add
        
    Returns:
        Updated state dict
    """
    topics = list(state.get("topics_covered_this_chapter", []))
    
    if topic and topic not in topics:
        topics.append(topic)
    
    # Context windowing - keep list manageable
    if len(topics) > 20:
        # Summarize old topics
        old_topics = topics[:-10]
        topics = topics[-10:]
        
        # Add to summarized context
        summary = state.get("summarized_past_context", "")
        summary += f"\nPreviously covered: {', '.join(old_topics)}"
        state["summarized_past_context"] = summary[-2000:]  # Limit length
    
    state["topics_covered_this_chapter"] = topics
    return state


# ============================================================================
# CHAPTER COMPLETION FUNCTIONS
# ============================================================================

def mark_chapter_complete(state: Dict[str, Any], chapter_number: int) -> Dict[str, Any]:
    """
    Mark a chapter as complete.
    
    Args:
        state: Current state dict
        chapter_number: Chapter number to mark complete
        
    Returns:
        Updated state dict
    """
    completed = list(state.get("chapters_completed", []))
    
    if chapter_number not in completed:
        completed.append(chapter_number)
        completed.sort()
    
    state["chapters_completed"] = completed
    
    # Update motivation for chapter completion
    state = update_motivation_score(state, "chapter_complete")
    
    logger.info(
        "chapter_marked_complete",
        chapter=chapter_number,
        total_completed=len(completed),
    )
    
    return state


async def create_progress_snapshot(
    db: AsyncSession,
    learning_state_id: UUID,
    state: Dict[str, Any],
) -> None:
    """
    Create a progress snapshot for analytics.
    
    Called at chapter completion.
    
    Args:
        db: Database session
        learning_state_id: ID of the LearningState
        state: Current state dict
    """
    from app.models.learning import ProgressSnapshot
    
    snapshot = ProgressSnapshot(
        learning_state_id=learning_state_id,
        snapshot_date=date.today(),
        chapter_progress=state.get("current_chapter", 1),
        quiz_scores={
            "last_score": state.get("quiz_score"),
            "comprehension": state.get("comprehension_score"),
        },
        study_duration_minutes=state.get("total_study_time_minutes", 0),
        topics_covered=state.get("topics_covered_this_chapter", []),
    )
    
    db.add(snapshot)
    await db.flush()
    
    logger.info(
        "progress_snapshot_created",
        learning_state_id=str(learning_state_id),
        chapter=state.get("current_chapter"),
    )


# ============================================================================
# PROGRESS SUMMARY FUNCTIONS
# ============================================================================

def get_progress_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a summary of progress for display.
    
    Args:
        state: Current state dict
        
    Returns:
        Summary dict with formatted values
    """
    chapters_completed = len(state.get("chapters_completed", []))
    total_chapters = state.get("total_chapters", 1)
    total_minutes = state.get("total_study_time_minutes", 0)
    
    # Format study time
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0:
        time_str = f"{hours}h {minutes}m"
    else:
        time_str = f"{minutes}m"
    
    return {
        "chapters_completed": chapters_completed,
        "total_chapters": total_chapters,
        "completion_percentage": round(chapters_completed / max(total_chapters, 1) * 100, 1),
        "total_study_time": time_str,
        "total_study_time_minutes": total_minutes,
        "comprehension_score": round(state.get("comprehension_score", 1.0) * 100),
        "attention_score": round(state.get("attention_score", 1.0) * 100),
        "motivation_score": round(state.get("motivation_score", 1.0) * 100),
    }


def format_progress_for_display(state: Dict[str, Any]) -> str:
    """
    Format progress as a display string.
    
    Args:
        state: Current state dict
        
    Returns:
        Formatted progress string
    """
    summary = get_progress_summary(state)
    
    return (
        f"📊 **Your Progress**\n"
        f"• Chapters: {summary['chapters_completed']}/{summary['total_chapters']} "
        f"({summary['completion_percentage']}%)\n"
        f"• Study Time: {summary['total_study_time']}\n"
        f"• Comprehension: {summary['comprehension_score']}%\n"
        f"• Attention: {summary['attention_score']}%\n"
        f"• Motivation: {summary['motivation_score']}%"
    )


# ============================================================================
# DATABASE PERSISTENCE FUNCTIONS
# ============================================================================

async def persist_progress_to_db(
    db: AsyncSession,
    user_id: UUID,
    book_id: UUID,
    state: Dict[str, Any],
) -> None:
    """
    Persist progress state to database.
    
    Updates the LearningState record with current progress.
    
    Args:
        db: Database session
        user_id: User ID
        book_id: Book ID
        state: Current state dict
    """
    from app.models.learning import LearningState
    
    result = await db.execute(
        select(LearningState)
        .where(LearningState.user_id == user_id)
        .where(LearningState.book_id == book_id)
    )
    learning_state = result.scalar_one_or_none()
    
    if learning_state:
        # Update fields
        learning_state.current_chapter = state.get("current_chapter", learning_state.current_chapter)
        learning_state.completed_chapters = state.get("chapters_completed", learning_state.completed_chapters)
        learning_state.motivation_score = state.get("motivation_score", learning_state.motivation_score)
        learning_state.attention_score = state.get("attention_score", learning_state.attention_score)
        learning_state.comprehension_score = state.get("comprehension_score", learning_state.comprehension_score)
        learning_state.total_study_time_minutes = state.get("total_study_time_minutes", learning_state.total_study_time_minutes)
        learning_state.last_active_at = datetime.utcnow()
        
        await db.flush()
        
        logger.debug(
            "progress_persisted",
            user_id=str(user_id),
            book_id=str(book_id),
            chapter=learning_state.current_chapter,
        )
