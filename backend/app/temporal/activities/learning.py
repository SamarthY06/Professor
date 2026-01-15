"""Learning-related Temporal activities with real database operations."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from temporalio import activity

from app.config import settings
from app.logs.logger import get_logger
from app.models.learning import LearningState, ProgressSnapshot
from app.models.book import BookChapter

logger = get_logger(__name__)

# Create async engine for activities
_engine = None
_session_factory = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncSession:
    """Get a database session for activities."""
    factory = get_session_factory()
    return factory()


@activity.defn
async def unlock_next_chapter(
    user_id: str,
    book_id: str,
    current_chapter_id: str,
) -> dict:
    """
    Unlock the next chapter for a user after passing quiz.
    
    Args:
        user_id: The user's ID
        book_id: The book's ID
        current_chapter_id: The current chapter's ID
        
    Returns:
        Dict with next chapter info
    """
    activity.logger.info(
        f"Unlocking next chapter for user {user_id} after {current_chapter_id}"
    )
    
    async with await get_db_session() as db:
        try:
            # Get current learning state
            result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            learning_state = result.scalar_one_or_none()
            
            if not learning_state:
                logger.error(
                    "learning_state_not_found",
                    user_id=user_id,
                    book_id=book_id,
                )
                return {"success": False, "error": "Learning state not found"}
            
            current_chapter = learning_state.current_chapter
            
            # Get total chapters in book
            chapter_count_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
            )
            total_chapters = len(chapter_count_result.scalars().all())
            
            # Check if there's a next chapter
            if current_chapter >= total_chapters:
                # Book complete!
                logger.info(
                    "book_completed",
                    user_id=user_id,
                    book_id=book_id,
                )
                return {
                    "success": True,
                    "book_complete": True,
                    "total_chapters": total_chapters,
                }
            
            # Update learning state
            next_chapter = current_chapter + 1
            completed_chapters = list(learning_state.completed_chapters or [])
            if current_chapter not in completed_chapters:
                completed_chapters.append(current_chapter)
            
            await db.execute(
                update(LearningState)
                .where(LearningState.id == learning_state.id)
                .values(
                    current_chapter=next_chapter,
                    completed_chapters=completed_chapters,
                    current_section=None,  # Reset section
                    pending_topics=[],  # Will be populated by planner
                    quiz_mode="none",
                    pending_quiz_questions=None,
                    last_active_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            
            # Create progress snapshot
            snapshot = ProgressSnapshot(
                learning_state_id=learning_state.id,
                snapshot_date=datetime.utcnow().date(),
                chapter_progress=next_chapter,
                quiz_scores={"chapter": current_chapter, "passed": True},
                topics_covered=[],
            )
            db.add(snapshot)
            
            await db.commit()
            
            logger.info(
                "chapter_unlocked",
                user_id=user_id,
                book_id=book_id,
                previous_chapter=current_chapter,
                new_chapter=next_chapter,
            )
            
            return {
                "success": True,
                "book_complete": False,
                "previous_chapter": current_chapter,
                "new_chapter": next_chapter,
                "total_chapters": total_chapters,
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("unlock_chapter_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def schedule_review_session(
    user_id: str,
    chapter_id: str,
    weak_areas: List[str],
) -> dict:
    """
    Schedule a review session for weak areas after failed quiz.
    
    Args:
        user_id: The user's ID
        chapter_id: The chapter's ID
        weak_areas: List of topics to review
        
    Returns:
        Dict with review session info
    """
    activity.logger.info(
        f"Scheduling review session for user {user_id}, chapter {chapter_id}"
    )
    
    async with await get_db_session() as db:
        try:
            # Get learning state
            result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
            )
            learning_state = result.scalar_one_or_none()
            
            if not learning_state:
                return {"success": False, "error": "Learning state not found"}
            
            # Update learning state for review mode
            await db.execute(
                update(LearningState)
                .where(LearningState.id == learning_state.id)
                .values(
                    quiz_mode="none",  # Exit quiz mode
                    pending_topics=weak_areas,  # Set topics to review
                    last_session_summary=f"Review needed for: {', '.join(weak_areas)}",
                    updated_at=datetime.utcnow(),
                )
            )
            
            await db.commit()
            
            logger.info(
                "review_session_scheduled",
                user_id=user_id,
                chapter_id=chapter_id,
                weak_areas=weak_areas,
            )
            
            return {
                "success": True,
                "chapter_id": chapter_id,
                "weak_areas": weak_areas,
                "review_topics_count": len(weak_areas),
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("schedule_review_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def update_motivation_score(
    user_id: str,
    book_id: str,
    delta: float,
) -> dict:
    """
    Update user's motivation score.
    
    Args:
        user_id: The user's ID
        book_id: The book's ID
        delta: Change in motivation score (-1 to 1)
        
    Returns:
        Dict with new score info
    """
    activity.logger.info(
        f"Updating motivation score for user {user_id} by {delta}"
    )
    
    async with await get_db_session() as db:
        try:
            # Get current learning state
            result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            learning_state = result.scalar_one_or_none()
            
            if not learning_state:
                return {"success": False, "error": "Learning state not found"}
            
            # Calculate new score (bounded 0-1)
            current_score = learning_state.motivation_score or 1.0
            new_score = max(0.0, min(1.0, current_score + delta))
            
            # Update in database
            await db.execute(
                update(LearningState)
                .where(LearningState.id == learning_state.id)
                .values(
                    motivation_score=new_score,
                    updated_at=datetime.utcnow(),
                )
            )
            
            await db.commit()
            
            logger.info(
                "motivation_score_updated",
                user_id=user_id,
                book_id=book_id,
                previous_score=current_score,
                delta=delta,
                new_score=new_score,
            )
            
            return {
                "success": True,
                "previous_score": current_score,
                "delta": delta,
                "new_score": new_score,
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("update_motivation_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def record_missed_session(
    user_id: str,
    book_id: str,
) -> dict:
    """
    Record a missed study session.
    
    Args:
        user_id: The user's ID
        book_id: The book's ID
        
    Returns:
        Dict with updated session count
    """
    activity.logger.info(f"Recording missed session for user {user_id}")
    
    async with await get_db_session() as db:
        try:
            # Get current learning state
            result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            learning_state = result.scalar_one_or_none()
            
            if not learning_state:
                return {"success": False, "error": "Learning state not found"}
            
            # Increment missed sessions
            new_missed = (learning_state.missed_sessions or 0) + 1
            
            # Also decrease motivation
            new_motivation = max(0.0, (learning_state.motivation_score or 1.0) - 0.1)
            
            await db.execute(
                update(LearningState)
                .where(LearningState.id == learning_state.id)
                .values(
                    missed_sessions=new_missed,
                    motivation_score=new_motivation,
                    updated_at=datetime.utcnow(),
                )
            )
            
            await db.commit()
            
            logger.info(
                "missed_session_recorded",
                user_id=user_id,
                book_id=book_id,
                total_missed=new_missed,
            )
            
            return {
                "success": True,
                "missed_sessions": new_missed,
                "new_motivation_score": new_motivation,
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("record_missed_session_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def check_user_inactivity(
    user_id: str,
    book_id: str,
    inactivity_threshold_hours: int = 24,
) -> dict:
    """
    Check if user has been inactive beyond threshold (Goals.md Section 8).
    
    Uses LearningState.last_active_at as the single source of truth.
    
    Args:
        user_id: The user's ID
        book_id: The book's ID
        inactivity_threshold_hours: Hours of inactivity before triggering
        
    Returns:
        Dict with inactivity status and days inactive
    """
    activity.logger.info(f"Checking inactivity for user {user_id}")
    
    async with await get_db_session() as db:
        try:
            # Use LearningState as single source of truth
            result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            learning_state = result.scalar_one_or_none()
            
            if not learning_state:
                return {"success": False, "is_inactive": False, "error": "No learning state found"}
            
            last_active = learning_state.last_active_at
            
            if not last_active:
                # User never started - not inactive, just hasn't begun
                return {"success": True, "is_inactive": False, "reason": "User has not started learning"}
            
            hours_since = (datetime.utcnow() - last_active).total_seconds() / 3600
            days_inactive = int(hours_since / 24)
            
            is_inactive = hours_since >= inactivity_threshold_hours
            
            # Check if course is completed - don't send motivation if done
            total_chapters = len(learning_state.completed_chapters or [])
            # If we have completed chapters and current chapter is beyond them, might be done
            # This is a simple check - in production, compare against book.total_chapters
            
            logger.info(
                "inactivity_check",
                user_id=user_id,
                hours_since=round(hours_since, 1),
                threshold=inactivity_threshold_hours,
                is_inactive=is_inactive,
                days_inactive=days_inactive,
            )
            
            return {
                "success": True,
                "is_inactive": is_inactive,
                "hours_since_last_interaction": round(hours_since, 1),
                "days_inactive": days_inactive,
                "last_interaction": last_active.isoformat(),
                "current_chapter": learning_state.current_chapter,
                "chapters_completed": len(learning_state.completed_chapters or []),
                "motivation_score": learning_state.motivation_score,
            }
            
        except Exception as e:
            logger.exception("inactivity_check_failed", error=str(e))
            return {"success": False, "is_inactive": False, "error": str(e)}


@activity.defn
async def send_motivation_message(
    user_id: str,
    book_id: str,
    days_inactive: int,
) -> dict:
    """
    Send motivational message to inactive user (Goals.md Section 9).
    
    Uses the motivation service to generate personalized messages via LLM.
    Sends via WhatsApp if configured, otherwise falls back to push notification.
    """
    from app.temporal.activities.notifications import send_whatsapp_notification, send_push_notification
    from app.services.motivation import generate_motivation_message, should_send_motivation
    
    activity.logger.info(f"Sending motivation message to user {user_id}, inactive {days_inactive} days")
    
    # Generate personalized message using LLM
    try:
        message = await generate_motivation_message(
            user_id=user_id,
            book_id=book_id,
            days_inactive=days_inactive,
        )
    except Exception as e:
        logger.warning(f"Motivation generation failed, using fallback: {e}")
        # Fallback message
        if days_inactive <= 1:
            message = "👋 Hi! Ready to continue your learning journey? Your progress is waiting!"
        elif days_inactive <= 3:
            message = f"📚 It's been {days_inactive} days. Let's continue learning together!"
        else:
            message = f"🙏 Whenever you're ready to continue, I'll be here. Your progress is saved."
    
    # Try WhatsApp first
    whatsapp_result = await send_whatsapp_notification(
        user_id=user_id,
        message=message,
        notification_type="motivation",
    )
    
    if whatsapp_result.get("success"):
        logger.info("motivation_message_sent_whatsapp", user_id=user_id)
        return {"success": True, "channel": "whatsapp", "message": message}
    
    # Fallback to push
    push_result = await send_push_notification(
        user_id=user_id,
        title="Your Professor Misses You!",
        message=message,
        notification_type="motivation",
    )
    
    return {
        "success": push_result.get("success", False),
        "channel": "push",
        "message": message,
        "whatsapp_error": whatsapp_result.get("error"),
    }


@activity.defn
async def get_user_learning_state(
    user_id: str,
    book_id: Optional[str] = None,
) -> dict:
    """
    Get user's current learning state.
    
    Args:
        user_id: The user's ID
        book_id: Optional book ID filter
        
    Returns:
        Dict with learning state data
    """
    async with await get_db_session() as db:
        try:
            query = select(LearningState).where(
                LearningState.user_id == UUID(user_id)
            )
            
            if book_id:
                query = query.where(LearningState.book_id == UUID(book_id))
            
            result = await db.execute(query)
            learning_state = result.scalar_one_or_none()
            
            if not learning_state:
                return {"success": False, "error": "Learning state not found"}
            
            return {
                "success": True,
                "current_chapter": learning_state.current_chapter,
                "completed_chapters": list(learning_state.completed_chapters or []),
                "motivation_score": learning_state.motivation_score,
                "attention_score": learning_state.attention_score,
                "comprehension_score": learning_state.comprehension_score,
                "missed_sessions": learning_state.missed_sessions,
                "total_study_time_minutes": learning_state.total_study_time_minutes,
                "quiz_mode": learning_state.quiz_mode,
                "last_active_at": learning_state.last_active_at.isoformat() if learning_state.last_active_at else None,
            }
            
        except Exception as e:
            logger.exception("get_learning_state_failed", error=str(e))
            return {"success": False, "error": str(e)}
