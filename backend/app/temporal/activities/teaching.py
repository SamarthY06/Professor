"""Teaching activities used by ChatWorkflow."""

from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from temporalio import activity
from openai import AsyncOpenAI

from app.config import settings
from app.logs.logger import get_logger
from app.models.book import Book, BookChapter
from app.models.learning import DocumentChunk, ChapterSummary, LearningState

logger = get_logger(__name__)

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncSession:
    factory = get_session_factory()
    return factory()


def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


@activity.defn
async def generate_chapter_summary(
    user_id: str,
    book_id: str,
    chapter_number: int,
) -> Dict[str, Any]:
    """Generate a comprehensive summary of a completed chapter."""
    activity.logger.info(f"Generating summary for chapter {chapter_number}")

    async with await get_db_session() as db:
        try:
            chapter_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
                .where(BookChapter.chapter_number == chapter_number)
            )
            chapter = chapter_result.scalar_one_or_none()

            if not chapter:
                return {"success": False, "summary": "Great work completing this chapter!"}

            chunks_result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.chapter_id == chapter.id)
                .order_by(DocumentChunk.chunk_index)
                .limit(10)
            )
            chunks = chunks_result.scalars().all()
            context = "\n---\n".join([c.content[:400] for c in chunks])

            client = get_openai_client()

            prompt = f"""Summarize Chapter {chapter_number}: {chapter.title or 'This Chapter'}

Chapter content:
{context}

Generate a summary that:
1. Lists 3-5 key concepts learned
2. Explains how they connect to each other
3. Notes any practical applications
4. Is around 150-200 words

Format with bullet points for key concepts."""

            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You summarize educational content clearly and concisely."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=400,
                temperature=0.5,
            )

            summary = response.choices[0].message.content

            chapter_summary = ChapterSummary(
                user_id=UUID(user_id),
                book_id=UUID(book_id),
                chapter_id=chapter.id,
                summary_type="completion",
                summary_text=summary,
                created_at=datetime.utcnow(),
            )
            db.add(chapter_summary)
            await db.commit()

            return {
                "success": True,
                "summary": summary,
                "chapter_title": chapter.title,
            }

        except Exception as e:
            logger.exception("generate_summary_failed", error=str(e))
            return {
                "success": False,
                "summary": "You've completed this chapter! The key concepts will help you in the upcoming chapters.",
            }
