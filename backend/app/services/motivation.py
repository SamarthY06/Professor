"""
Motivation Service - Generates personalized motivation messages.

This is NOT an agent. It's a simple LLM call triggered by Temporal
when a user is inactive.

Per overview2_part2.md Section 14:
- Temporal detects inactivity
- This service generates a personalized message
- Message sent via WhatsApp/Push notification
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.services.openai_service import OpenAIService

logger = get_logger(__name__)


async def generate_motivation_message(
    user_id: str,
    book_id: str,
    days_inactive: int,
    db: Optional[AsyncSession] = None,
) -> str:
    """
    Generate a personalized motivation message using LLM.
    
    This is a simple LLM call, NOT an agent.
    
    Args:
        user_id: User ID
        book_id: Book ID
        days_inactive: Number of days since last activity
        db: Database session (optional, will create if not provided)
        
    Returns:
        Personalized motivation message string
    """
    from app.db.database import async_session_maker
    from app.models.user import User, UserSettings
    from app.models.book import Book
    from app.models.learning import LearningState
    
    # Get context for personalization
    user_name = "there"
    book_title = "your book"
    chapters_completed = 0
    total_chapters = 0
    professor_style = "balanced"
    
    should_close_db = db is None
    if db is None:
        db = async_session_maker()
    
    try:
        # Get user info
        user_result = await db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = user_result.scalar_one_or_none()
        if user and user.name:
            user_name = user.name.split()[0]  # First name only
        
        # Get user settings for style preference
        settings_result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == UUID(user_id))
        )
        user_settings = settings_result.scalar_one_or_none()
        if user_settings and user_settings.professor_style:
            professor_style = user_settings.professor_style
        
        # Get book info
        book_result = await db.execute(
            select(Book).where(Book.id == UUID(book_id))
        )
        book = book_result.scalar_one_or_none()
        if book:
            book_title = book.title
            total_chapters = book.total_chapters or 0
        
        # Get learning state
        state_result = await db.execute(
            select(LearningState)
            .where(LearningState.user_id == UUID(user_id))
            .where(LearningState.book_id == UUID(book_id))
        )
        learning_state = state_result.scalar_one_or_none()
        if learning_state:
            chapters_completed = len(learning_state.completed_chapters or [])
        
    except Exception as e:
        logger.warning(f"Failed to get context for motivation: {e}")
    finally:
        if should_close_db:
            await db.close()
    
    # Build the prompt
    prompt = f"""Generate a brief, personalized motivation message for a student.

**Context:**
- Student Name: {user_name}
- Book: {book_title}
- Days Inactive: {days_inactive}
- Progress: {chapters_completed}/{total_chapters} chapters completed
- Professor Style: {professor_style}

**Style Guidelines:**
- strict: Brief, goal-focused. "Your goals are waiting. Let's get back on track."
- balanced: Empathetic but practical. "I understand life gets busy, but your progress is waiting."
- encouraging: Warm and supportive. "I miss our sessions! You've made great progress..."

**Requirements:**
1. Keep it under 100 words
2. Make it feel personal, not generic
3. Mention their progress if they've made some
4. End with a gentle call to action
5. Use appropriate emoji (1-2 max)
6. Match the {professor_style} style

Generate ONLY the message, no explanations."""

    try:
        openai_service = OpenAIService()
        message = await openai_service.generate(
            prompt=prompt,
            system_prompt="You are a caring professor sending a brief message to a student who hasn't studied recently.",
            model=settings.openai_model_mini,  # Use faster model
            max_tokens=150,
            temperature=0.7,
        )
        
        logger.info(
            "motivation_message_generated",
            user_id=user_id,
            days_inactive=days_inactive,
            style=professor_style,
        )
        
        return message.strip()
        
    except Exception as e:
        logger.exception("motivation_generation_failed", error=str(e))
        # Fallback to template message
        return _get_fallback_message(user_name, days_inactive, professor_style)


def _get_fallback_message(
    user_name: str,
    days_inactive: int,
    professor_style: str,
) -> str:
    """Get a fallback message when LLM fails."""
    
    if professor_style == "strict":
        if days_inactive <= 2:
            return f"Hi {user_name}. Your learning goals are waiting. Let's continue today."
        else:
            return f"Hi {user_name}. It's been {days_inactive} days. Your progress depends on consistency. Let's get back on track."
    
    elif professor_style == "encouraging":
        if days_inactive <= 2:
            return f"Hi {user_name}! 💙 I missed our session yesterday. Ready to continue your learning journey?"
        else:
            return f"Hi {user_name}! 🌟 It's been {days_inactive} days, but don't worry - your progress is saved and I'm here whenever you're ready!"
    
    else:  # balanced
        if days_inactive <= 2:
            return f"Hi {user_name}! Just checking in. Ready to pick up where we left off?"
        else:
            return f"Hi {user_name}! It's been {days_inactive} days since our last session. Your progress is waiting for you. 📚"


async def should_send_motivation(
    user_id: str,
    book_id: str,
    days_inactive: int,
    notifications_sent: int,
) -> bool:
    """
    Determine if a motivation message should be sent.
    
    Prevents spam and respects user preferences.
    
    Args:
        user_id: User ID
        book_id: Book ID
        days_inactive: Days since last activity
        notifications_sent: Number of notifications already sent
        
    Returns:
        True if should send, False otherwise
    """
    from app.db.database import async_session_maker
    from app.models.user import UserSettings
    from app.models.learning import LearningState
    
    # Max 5 notifications per inactivity period
    if notifications_sent >= 5:
        return False
    
    async with async_session_maker() as db:
        # Check user preferences
        settings_result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == UUID(user_id))
        )
        user_settings = settings_result.scalar_one_or_none()
        
        if user_settings:
            prefs = user_settings.notification_preferences or {}
            # If user disabled all notifications, don't send
            if not prefs.get("whatsapp", True) and not prefs.get("push", True):
                return False
        
        # Check if course is completed
        state_result = await db.execute(
            select(LearningState)
            .where(LearningState.user_id == UUID(user_id))
            .where(LearningState.book_id == UUID(book_id))
        )
        learning_state = state_result.scalar_one_or_none()
        
        # Don't send if no learning state exists
        if not learning_state:
            return False
        
        # Don't send if motivation is already high (user might just be busy)
        if learning_state.motivation_score and learning_state.motivation_score > 0.8:
            return False
    
    return True
