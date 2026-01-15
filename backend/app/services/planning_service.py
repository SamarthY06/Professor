"""Planning service - generates learning plans."""

from typing import Dict, Any, Optional
from uuid import UUID
from openai import AsyncOpenAI
import json

from sqlalchemy import select

from app.config import settings
from app.db.database import async_session_maker
from app.models.book import Book, BookChapter
from app.models.learning_config import LearningConfig
from app.logs.logger import get_logger

logger = get_logger(__name__)


async def generate_plan(
    book_id: str,
    user_id: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a learning plan for the book."""
    
    async with async_session_maker() as db:
        book_result = await db.execute(select(Book).where(Book.id == UUID(book_id)))
        book = book_result.scalar_one_or_none()
        
        if not book:
            return {"summary": "Book not found.", "chapters": []}
        
        chapters_result = await db.execute(
            select(BookChapter)
            .where(BookChapter.book_id == UUID(book_id))
            .order_by(BookChapter.chapter_number)
        )
        chapters = chapters_result.scalars().all()
        
        config_result = await db.execute(
            select(LearningConfig).where(LearningConfig.book_id == UUID(book_id))
        )
        config = config_result.scalar_one_or_none()
        
        level = config.learning_level if config else "intermediate"
        daily_mins = config.daily_study_minutes if config else 60
        quiz_freq = config.quiz_frequency if config else "after_each_chapter"
        
        chapters_info = [
            {
                "number": c.chapter_number,
                # Ensure we have a meaningful title, not just a number
                "title": c.title if c.title and len(c.title) > 2 and not c.title.isdigit() else f"Chapter {c.chapter_number}",
                # Cap duration at reasonable values (max 120 min per session)
                "duration": min(c.estimated_duration_minutes or 45, 120),
            }
            for c in chapters
        ]
        
        # Calculate realistic day distribution
        total_minutes = sum(c["duration"] for c in chapters_info)
        total_days = max(1, total_minutes // daily_mins)
        
        plan_data = {
            "total_days": total_days,
            "chapters": [
                {
                    "number": c["number"],
                    "title": c["title"],
                    "day": i + 1,
                    "duration": c["duration"],
                    "quiz_after": quiz_freq == "after_each_chapter" or 
                                 (quiz_freq == "after_n_chapters" and (i + 1) % 2 == 0),
                }
                for i, c in enumerate(chapters_info)
            ],
        }
        
        summary = f"""📚 **Learning Plan for {book.title}**

**Duration:** {total_days} days | **Level:** {level}
**Study Time:** {daily_mins} min/day | **Chapters:** {len(chapters_info)}

**Your Schedule:**
"""
        for i, ch in enumerate(plan_data["chapters"]):
            quiz = "📝 (Quiz)" if ch["quiz_after"] else ""
            summary += f"\n• **{ch['title']}** (~{ch['duration']} min) {quiz}"
        
        summary += f"\n\n*I'll guide you through each chapter step by step. Ready to begin?*"
        
        return {
            "summary": summary,
            "plan_data": plan_data,
            "total_chapters": len(chapters_info),
        }
