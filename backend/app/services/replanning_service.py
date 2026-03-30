"""Dynamic replanning service - Goals.md Section 10.

Handles replanning when user:
- Delays learning
- Requests postponement
- Changes availability

Professor replans remaining chapters with LLM reasoning.
"""

from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta
from openai import AsyncOpenAI
import json

from sqlalchemy import select, update

from app.config import settings
from app.db.database import async_session_maker
from app.logs.logger import get_logger
from app.models.learning_config import LearningConfig, LearningPlan
from app.models.learning import LearningState
from app.models.book import Book, BookChapter

logger = get_logger(__name__)


async def check_needs_replanning(
    book_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Check if user's learning plan needs adjustment based on delays.
    
    Returns:
        Dict with needs_replanning flag and reason
    """
    async with async_session_maker() as db:
        try:
            # Get learning config
            config_result = await db.execute(
                select(LearningConfig).where(
                    LearningConfig.book_id == UUID(book_id),
                    LearningConfig.user_id == UUID(user_id)
                )
            )
            config = config_result.scalar_one_or_none()
            
            if not config or not config.deadline:
                return {"needs_replanning": False, "reason": "No deadline set"}
            
            # Get learning state
            ls_result = await db.execute(
                select(LearningState).where(
                    LearningState.book_id == UUID(book_id),
                    LearningState.user_id == UUID(user_id)
                )
            )
            ls = ls_result.scalar_one_or_none()

            if not ls:
                return {"needs_replanning": False, "reason": "No learning state"}

            book_result = await db.execute(
                select(Book.total_chapters).where(Book.id == UUID(book_id))
            )
            book_row = book_result.first()
            total_chapters = book_row[0] if book_row else 5

            current_chapter = ls.current_chapter
            chapters_completed = len(ls.completed_chapters or [])
            chapters_remaining = total_chapters - chapters_completed
            
            deadline = config.deadline
            days_remaining = (deadline - datetime.now().date()).days
            
            if days_remaining <= 0:
                return {
                    "needs_replanning": True,
                    "reason": "Deadline has passed",
                    "days_remaining": days_remaining,
                    "chapters_remaining": chapters_remaining,
                }
            
            # Calculate if we're behind schedule
            expected_progress = (total_chapters / max(1, days_remaining)) * chapters_completed
            actual_progress = chapters_completed
            
            if chapters_remaining > days_remaining:
                return {
                    "needs_replanning": True,
                    "reason": "Not enough days for remaining chapters",
                    "days_remaining": days_remaining,
                    "chapters_remaining": chapters_remaining,
                    "daily_chapters_needed": chapters_remaining / max(1, days_remaining),
                }
            
            return {
                "needs_replanning": False,
                "days_remaining": days_remaining,
                "chapters_remaining": chapters_remaining,
            }
            
        except Exception as e:
            logger.exception("check_replanning_failed", error=str(e))
            return {"needs_replanning": False, "error": str(e)}


async def generate_replan(
    book_id: str,
    user_id: str,
    new_deadline: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a new learning plan based on current progress (Goals.md Section 10).
    
    Uses LLM reasoning - no hardcoded rules.
    """
    async with async_session_maker() as db:
        try:
            # Get learning state
            ls_result = await db.execute(
                select(LearningState).where(
                    LearningState.book_id == UUID(book_id),
                    LearningState.user_id == UUID(user_id)
                )
            )
            ls = ls_result.scalar_one_or_none()
            
            # Get learning config
            config_result = await db.execute(
                select(LearningConfig).where(
                    LearningConfig.book_id == UUID(book_id),
                    LearningConfig.user_id == UUID(user_id)
                )
            )
            config = config_result.scalar_one_or_none()
            
            # Get book info
            book_result = await db.execute(
                select(Book).where(Book.id == UUID(book_id))
            )
            book = book_result.scalar_one_or_none()
            
            # Get chapters
            chapters_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
                .order_by(BookChapter.chapter_number)
            )
            chapters = chapters_result.scalars().all()
            
            current_chapter = ls.current_chapter if ls else 1
            chapters_completed = list(ls.completed_chapters or []) if ls else []
            total_chapters = len(chapters)
            
            deadline = new_deadline or (config.deadline.isoformat() if config and config.deadline else None)
            
            # Use LLM to generate replan
            client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
            
            prompt = f"""You are a learning planner. The student needs a revised learning plan.

Current Situation:
- Book: {book.title if book else 'Unknown'}
- Total chapters: {total_chapters}
- Chapters completed: {chapters_completed}
- Current chapter: {current_chapter}
- Deadline: {deadline or 'No deadline'}
- Daily study time: {config.daily_study_minutes if config else 60} minutes

Remaining chapters to cover:
{[{"number": c.chapter_number, "title": c.title} for c in chapters if c.chapter_number not in chapters_completed]}

Create a realistic revised learning plan. Consider:
1. The student may have been delayed - be encouraging
2. If deadline is tight, suggest compressed schedule OR extend deadline
3. Prioritize understanding over rushing

Respond with JSON:
{{
    "recommendation": "continue|compress|extend",
    "message": "Friendly message explaining the new plan",
    "revised_schedule": [
        {{"day": 1, "chapters": [1], "duration_minutes": 60}},
        ...
    ],
    "total_days_needed": N,
    "can_meet_deadline": true/false
}}"""

            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are a supportive learning planner. Return JSON only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            
            replan = json.loads(response.choices[0].message.content)
            
            logger.info("replan_generated", user_id=user_id, book_id=book_id)
            
            return {
                "success": True,
                "replan": replan,
                "current_chapter": current_chapter,
                "chapters_remaining": total_chapters - len(chapters_completed),
            }
            
        except Exception as e:
            logger.exception("generate_replan_failed", error=str(e))
            return {"success": False, "error": str(e)}


async def offer_replan(
    book_id: str,
    user_id: str,
    api_key: Optional[str] = None,
) -> str:
    """
    Generate professor's offer to replan (Goals.md Section 10).
    
    Returns a message the professor can say to offer replanning.
    """
    check_result = await check_needs_replanning(book_id, user_id)
    
    if not check_result.get("needs_replanning"):
        return None
    
    reason = check_result.get("reason", "")
    days_remaining = check_result.get("days_remaining", 0)
    chapters_remaining = check_result.get("chapters_remaining", 0)
    
    if days_remaining <= 0:
        return (
            f"📅 I notice your original deadline has passed. No worries - life happens! "
            f"You still have {chapters_remaining} chapters to go. "
            f"Would you like me to create a new learning schedule? Just let me know your new timeline."
        )
    else:
        daily_needed = check_result.get("daily_chapters_needed", 1)
        return (
            f"⏰ I see we're a bit behind schedule. With {chapters_remaining} chapters remaining "
            f"and {days_remaining} days until your deadline, we'd need to cover about "
            f"{daily_needed:.1f} chapters per day. Would you like to:\n\n"
            f"1. **Compress the schedule** - Study more intensively\n"
            f"2. **Extend the deadline** - Take more time\n\n"
            f"What works best for you?"
        )
