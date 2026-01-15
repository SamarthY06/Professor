"""
Background Summarization Service.

After a chapter is completed, this service:
1. Gathers the teaching conversation for that chapter
2. Uses LLM to generate a summary
3. Stores the summary in the database
4. Summary is available for TeacherAgent when starting next chapter

This runs as a fire-and-forget background task.
"""

import asyncio
from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.services.openai_service import OpenAIService

logger = get_logger(__name__)


async def trigger_chapter_summarization(
    user_id: str,
    book_id: str,
    chapter_number: int,
    session_id: str,
) -> None:
    """
    Trigger background summarization for a completed chapter.
    
    This is fire-and-forget - the user doesn't wait for it.
    
    Args:
        user_id: User ID
        book_id: Book ID
        chapter_number: Chapter that was completed
        session_id: Session ID for getting conversation history
    """
    # Run in background
    asyncio.create_task(
        _summarize_chapter(user_id, book_id, chapter_number, session_id)
    )
    logger.info(
        "summarization_triggered",
        user_id=user_id,
        book_id=book_id,
        chapter=chapter_number,
    )


async def _summarize_chapter(
    user_id: str,
    book_id: str,
    chapter_number: int,
    session_id: str,
) -> None:
    """
    Internal function that performs the summarization.
    
    Steps:
    1. Get conversation history for this chapter
    2. Generate summary using LLM
    3. Store summary in database
    """
    from app.db.database import async_session_maker
    from app.models.chat import ChatMessage, ChatSession
    from app.models.learning import ChapterSummary
    from app.models.book import BookChapter
    
    try:
        async with async_session_maker() as db:
            # Get conversation messages for this chapter
            messages = await _get_chapter_messages(
                db=db,
                session_id=session_id,
                chapter_number=chapter_number,
            )
            
            if not messages:
                logger.warning(
                    "no_messages_for_summarization",
                    chapter=chapter_number,
                )
                return
            
            # Get chapter info
            chapter_title = await _get_chapter_title(
                db=db,
                book_id=book_id,
                chapter_number=chapter_number,
            )
            
            # Generate summary
            summary_text, topics_covered = await _generate_summary(
                messages=messages,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
            )
            
            # Get chapter_id
            chapter_id = await _get_chapter_id(
                db=db,
                book_id=book_id,
                chapter_number=chapter_number,
            )
            
            # Store summary
            await _store_summary(
                db=db,
                user_id=user_id,
                book_id=book_id,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                summary_text=summary_text,
                topics_covered=topics_covered,
            )
            
            await db.commit()
            
            logger.info(
                "summarization_complete",
                user_id=user_id,
                book_id=book_id,
                chapter=chapter_number,
                summary_length=len(summary_text),
            )
            
    except Exception as e:
        logger.exception(
            "summarization_failed",
            user_id=user_id,
            book_id=book_id,
            chapter=chapter_number,
            error=str(e),
        )


async def _get_chapter_messages(
    db: AsyncSession,
    session_id: str,
    chapter_number: int,
) -> list:
    """Get conversation messages for a specific chapter."""
    from app.models.chat import ChatMessage
    
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == UUID(session_id))
        .where(ChatMessage.chapter_at_time == chapter_number)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()
    
    return [
        {
            "role": m.role,
            "content": m.content,
            "agent": m.agent_name,
        }
        for m in messages
    ]


async def _get_chapter_title(
    db: AsyncSession,
    book_id: str,
    chapter_number: int,
) -> str:
    """Get chapter title from database."""
    from app.models.book import BookChapter
    
    result = await db.execute(
        select(BookChapter.title)
        .where(BookChapter.book_id == UUID(book_id))
        .where(BookChapter.chapter_number == chapter_number)
    )
    row = result.first()
    return row[0] if row and row[0] else f"Chapter {chapter_number}"


async def _get_chapter_id(
    db: AsyncSession,
    book_id: str,
    chapter_number: int,
) -> Optional[UUID]:
    """Get chapter ID from database."""
    from app.models.book import BookChapter
    
    result = await db.execute(
        select(BookChapter.id)
        .where(BookChapter.book_id == UUID(book_id))
        .where(BookChapter.chapter_number == chapter_number)
    )
    row = result.first()
    return row[0] if row else None


async def _generate_summary(
    messages: list,
    chapter_number: int,
    chapter_title: str,
) -> tuple:
    """
    Generate summary using LLM.
    
    Returns:
        Tuple of (summary_text, topics_covered)
    """
    # Format conversation for prompt
    conversation = _format_conversation(messages)
    
    prompt = f"""Summarize this teaching session for Chapter {chapter_number}: {chapter_title}.

**CONVERSATION:**
{conversation}

**CREATE A SUMMARY THAT INCLUDES:**
1. Key topics that were explained
2. Important concepts covered
3. Questions the student asked and key clarifications made
4. Any areas where the student seemed to struggle

This summary will be used by Professor when teaching the next chapter to maintain continuity.

**FORMAT:**
Return a JSON object:
{{
    "summary": "<concise summary under 500 words>",
    "topics_covered": ["topic1", "topic2", "topic3"],
    "student_questions": ["question1", "question2"],
    "areas_of_difficulty": ["area1", "area2"]
}}"""

    try:
        openai_service = OpenAIService()
        result = await openai_service.generate_json(
            prompt=prompt,
            system_prompt="You are a teaching assistant that creates concise summaries. Return valid JSON.",
            model=settings.openai_model_mini,  # Use faster model for summarization
            max_tokens=800,
            temperature=0.3,
        )
        
        summary_text = result.get("summary", "")
        topics_covered = result.get("topics_covered", [])
        
        # If JSON parsing failed, use the raw response
        if not summary_text:
            summary_text = str(result)
            topics_covered = []
        
        return summary_text, topics_covered
        
    except Exception as e:
        logger.warning(f"Summary generation failed: {e}")
        # Return basic summary
        return _create_fallback_summary(messages, chapter_number), []


def _format_conversation(messages: list) -> str:
    """Format messages for the summarization prompt."""
    parts = []
    for msg in messages[-30:]:  # Limit to last 30 messages
        role = msg["role"].upper()
        content = msg["content"][:500]  # Truncate long messages
        parts.append(f"{role}: {content}")
    
    return "\n\n".join(parts)


def _create_fallback_summary(messages: list, chapter_number: int) -> str:
    """Create a basic summary when LLM fails."""
    user_messages = [m for m in messages if m["role"] == "user"]
    assistant_messages = [m for m in messages if m["role"] == "assistant"]
    
    return (
        f"Chapter {chapter_number} session summary:\n"
        f"- {len(assistant_messages)} teaching exchanges\n"
        f"- {len(user_messages)} student interactions\n"
        f"Topics were covered through interactive discussion."
    )


async def _store_summary(
    db: AsyncSession,
    user_id: str,
    book_id: str,
    chapter_id: Optional[UUID],
    chapter_number: int,
    summary_text: str,
    topics_covered: list,
) -> None:
    """Store summary in database."""
    from app.models.learning import ChapterSummary
    
    # Check if summary already exists
    existing = await db.execute(
        select(ChapterSummary)
        .where(ChapterSummary.user_id == UUID(user_id))
        .where(ChapterSummary.book_id == UUID(book_id))
        .where(ChapterSummary.chapter_id == chapter_id)
    )
    existing_summary = existing.scalar_one_or_none()
    
    if existing_summary:
        # Update existing
        existing_summary.summary_text = summary_text
        existing_summary.key_concepts = {"topics": topics_covered}
    else:
        # Create new
        summary = ChapterSummary(
            user_id=UUID(user_id),
            book_id=UUID(book_id),
            chapter_id=chapter_id,
            summary_type="completion",
            summary_text=summary_text,
            key_concepts={"topics": topics_covered},
        )
        db.add(summary)


# ============================================================================
# SUMMARY RETRIEVAL FUNCTIONS
# ============================================================================

async def get_chapter_summary(
    user_id: str,
    book_id: str,
    chapter_number: int,
) -> Optional[str]:
    """
    Get the summary for a specific chapter.
    
    Used by TeacherAgent when starting a new chapter.
    
    Args:
        user_id: User ID
        book_id: Book ID
        chapter_number: Chapter number
        
    Returns:
        Summary text or None if not available
    """
    from app.db.database import async_session_maker
    from app.models.learning import ChapterSummary
    from app.models.book import BookChapter
    
    async with async_session_maker() as db:
        # Get chapter_id first
        chapter_result = await db.execute(
            select(BookChapter.id)
            .where(BookChapter.book_id == UUID(book_id))
            .where(BookChapter.chapter_number == chapter_number)
        )
        chapter_row = chapter_result.first()
        if not chapter_row:
            return None
        
        chapter_id = chapter_row[0]
        
        # Get summary
        result = await db.execute(
            select(ChapterSummary.summary_text)
            .where(ChapterSummary.user_id == UUID(user_id))
            .where(ChapterSummary.book_id == UUID(book_id))
            .where(ChapterSummary.chapter_id == chapter_id)
            .order_by(ChapterSummary.created_at.desc())
        )
        row = result.first()
        
        return row[0] if row else None


async def get_all_chapter_summaries(
    user_id: str,
    book_id: str,
) -> dict:
    """
    Get all chapter summaries for a book.
    
    Returns:
        Dict mapping chapter_number to summary_text
    """
    from app.db.database import async_session_maker
    from app.models.learning import ChapterSummary
    from app.models.book import BookChapter
    
    async with async_session_maker() as db:
        result = await db.execute(
            select(BookChapter.chapter_number, ChapterSummary.summary_text)
            .join(ChapterSummary, ChapterSummary.chapter_id == BookChapter.id)
            .where(ChapterSummary.user_id == UUID(user_id))
            .where(ChapterSummary.book_id == UUID(book_id))
            .order_by(BookChapter.chapter_number)
        )
        rows = result.fetchall()
        
        return {row[0]: row[1] for row in rows}
