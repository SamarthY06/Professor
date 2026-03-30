"""Chapter Transition Service - Handles chapter completion and context management."""

from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from sqlalchemy import select, and_

from app.config import settings
from app.db.database import async_session_maker
from app.logs.logger import get_logger

logger = get_logger(__name__)


async def get_cumulative_summary(
    book_id: str,
    up_to_chapter: int,
    user_id: str,
) -> Optional[str]:
    """
    Get the cumulative summary up to a specific chapter.
    
    This returns the 'cumulative' type summary which contains
    a condensed version of ALL previous chapters.
    """
    from app.models.learning import ChapterSummary
    from app.models.book import BookChapter
    
    if up_to_chapter <= 0:
        return None
    
    async with async_session_maker() as db:
        try:
            chapter_result = await db.execute(
                select(BookChapter).where(
                    and_(
                        BookChapter.book_id == UUID(book_id),
                        BookChapter.chapter_number == up_to_chapter
                    )
                )
            )
            chapter = chapter_result.scalar_one_or_none()
            
            if not chapter:
                return None
            
            summary_result = await db.execute(
                select(ChapterSummary).where(
                    and_(
                        ChapterSummary.user_id == UUID(user_id),
                        ChapterSummary.book_id == UUID(book_id),
                        ChapterSummary.chapter_id == chapter.id,
                        ChapterSummary.summary_type == "cumulative"
                    )
                )
            )
            summary = summary_result.scalar_one_or_none()
            
            if summary:
                return summary.summary_text
            
            return None
            
        except Exception as e:
            logger.exception("cumulative_summary_fetch_failed", error=str(e))
            return None


async def generate_chapter_summary(
    book_id: str,
    chapter_number: int,
    user_id: str,
    topics_covered: List[str],
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a concise summary of the completed chapter.
    
    SMART SUMMARY MANAGEMENT:
    - For Chapter 1: Just summarize Chapter 1
    - For Chapter N (N > 1): 
      1. Get cumulative summary from Chapter N-1
      2. Summarize current chapter
      3. Merge into NEW cumulative summary (condensed, not appended)
    
    This prevents context explosion while maintaining continuity.
    """
    from app.integrations.rag_client import get_rag_client, RAGClientError
    from app.models.book import Book, BookChapter
    from app.models.learning import ChapterSummary
    
    llm = ChatOpenAI(
        model=settings.openai_model_mini,
        api_key=api_key or settings.openai_api_key,
        temperature=0.3,
        max_tokens=500,
    )
    
    async with async_session_maker() as db:
        book_result = await db.execute(
            select(Book).where(Book.id == UUID(book_id))
        )
        book = book_result.scalar_one_or_none()
        
        chapter_result = await db.execute(
            select(BookChapter)
            .where(BookChapter.book_id == UUID(book_id))
            .where(BookChapter.chapter_number == chapter_number)
        )
        chapter = chapter_result.scalar_one_or_none()
        
        if not book or not chapter:
            logger.warning("chapter_summary_failed_no_book", book_id=book_id, chapter=chapter_number)
            return {"summary_text": "", "key_topics": topics_covered, "success": False}
        
        chapter_title = chapter.title or f"Chapter {chapter_number}"
        
        # Get RAG content for current chapter
        rag_context = ""
        document_id = book.book_metadata.get("rag_document_id") if book.book_metadata else None
        chapter_id = chapter.key_concepts.get("rag_chapter_id") if chapter.key_concepts else None
        
        if document_id:
            try:
                client = get_rag_client()
                response = await client.search(
                    query=f"Key takeaways and main concepts from chapter {chapter_number}: {chapter_title}",
                    document_id=document_id,
                    chapter_ids=[chapter_id] if chapter_id else None,
                    limit=5,
                    user_id=user_id,
                )
                rag_context = "\n".join([r.content[:300] for r in response.results])
            except RAGClientError as e:
                logger.warning("rag_summary_fetch_failed", error=str(e))
        
        # Generate CURRENT chapter summary (always needed)
        current_chapter_prompt = f"""Summarize Chapter {chapter_number}: "{chapter_title}" CONCISELY.

TOPICS COVERED:
{', '.join(topics_covered) if topics_covered else 'General chapter content'}

CHAPTER CONTENT:
{rag_context if rag_context else 'No additional content available'}

Generate:
1. ONE sentence overview
2. 3-5 KEY CONCEPTS (bullet points, just names)

Keep it under 100 words."""

        try:
            response = await llm.ainvoke([HumanMessage(content=current_chapter_prompt)])
            current_summary = response.content.strip()
        except Exception as e:
            logger.exception("current_summary_generation_failed", error=str(e))
            current_summary = f"Chapter {chapter_number} covered: {', '.join(topics_covered[:5])}"
        
        # For Chapter 1, current summary IS the cumulative summary
        if chapter_number == 1:
            cumulative_summary = current_summary
        else:
            # Get previous cumulative summary
            previous_cumulative = await get_cumulative_summary(book_id, chapter_number - 1, user_id)
            
            if previous_cumulative:
                # SMART MERGE: Condense previous + current into new cumulative
                merge_prompt = f"""You have learned through {chapter_number} chapters. Create a CONDENSED summary.

PREVIOUS CHAPTERS SUMMARY (Chapters 1-{chapter_number - 1}):
{previous_cumulative}

CURRENT CHAPTER (Chapter {chapter_number}: {chapter_title}):
{current_summary}

Create a NEW condensed summary that:
1. Captures the ESSENTIAL concepts from ALL chapters so far
2. Shows how concepts BUILD on each other
3. Is NO LONGER than 150 words total
4. Uses bullet points for key concepts

DO NOT just append - CONDENSE and SYNTHESIZE."""

                try:
                    response = await llm.ainvoke([HumanMessage(content=merge_prompt)])
                    cumulative_summary = response.content.strip()
                except Exception as e:
                    logger.exception("cumulative_merge_failed", error=str(e))
                    # Fallback: just use current summary
                    cumulative_summary = current_summary
            else:
                # No previous cumulative, use current
                cumulative_summary = current_summary
        
        # Store BOTH summaries in DB
        try:
            # Store current chapter summary (type: completion)
            existing_completion = await db.execute(
                select(ChapterSummary).where(
                    and_(
                        ChapterSummary.user_id == UUID(user_id),
                        ChapterSummary.book_id == UUID(book_id),
                        ChapterSummary.chapter_id == chapter.id,
                        ChapterSummary.summary_type == "completion"
                    )
                )
            )
            existing = existing_completion.scalar_one_or_none()
            
            if existing:
                existing.summary_text = current_summary
                existing.key_concepts = {"topics": topics_covered}
            else:
                db.add(ChapterSummary(
                    user_id=UUID(user_id),
                    book_id=UUID(book_id),
                    chapter_id=chapter.id,
                    summary_type="completion",
                    summary_text=current_summary,
                    key_concepts={"topics": topics_covered},
                ))
            
            # Store cumulative summary (type: cumulative)
            existing_cumulative = await db.execute(
                select(ChapterSummary).where(
                    and_(
                        ChapterSummary.user_id == UUID(user_id),
                        ChapterSummary.book_id == UUID(book_id),
                        ChapterSummary.chapter_id == chapter.id,
                        ChapterSummary.summary_type == "cumulative"
                    )
                )
            )
            existing_cum = existing_cumulative.scalar_one_or_none()
            
            if existing_cum:
                existing_cum.summary_text = cumulative_summary
            else:
                db.add(ChapterSummary(
                    user_id=UUID(user_id),
                    book_id=UUID(book_id),
                    chapter_id=chapter.id,
                    summary_type="cumulative",
                    summary_text=cumulative_summary,
                    key_concepts={"chapters_covered": list(range(1, chapter_number + 1))},
                ))
            
            await db.commit()
            logger.info(
                "chapter_summaries_stored",
                chapter=chapter_number,
                user_id=user_id,
                current_len=len(current_summary),
                cumulative_len=len(cumulative_summary),
            )
            
        except Exception as e:
            logger.exception("summary_storage_failed", error=str(e))
        
        return {
            "summary_text": current_summary,  # For display
            "cumulative_summary": cumulative_summary,  # For context
            "key_topics": topics_covered,
            "chapter_title": chapter_title,
            "chapter_number": chapter_number,
            "success": True,
        }


async def archive_chapter_conversation(
    book_id: str,
    chapter_number: int,
    user_id: str,
    session_id: str,
    messages: List[Dict[str, Any]],
) -> bool:
    """
    Archive the conversation history for a completed chapter.
    
    This stores the full conversation so users can view it in UI,
    but it's NOT loaded into context for future chapters.
    """
    from app.models.chat import ChatSession, ChatMessage
    
    async with async_session_maker() as db:
        try:
            session_result = await db.execute(
                select(ChatSession).where(
                    and_(
                        ChatSession.user_id == UUID(user_id),
                        ChatSession.book_id == UUID(book_id),
                        ChatSession.session_metadata.contains({"chapter_number": chapter_number})
                    )
                )
            )
            session = session_result.scalar_one_or_none()
            
            if not session:
                session = ChatSession(
                    user_id=UUID(user_id),
                    book_id=UUID(book_id),
                    session_metadata={
                        "chapter_number": chapter_number,
                        "archived": True,
                        "archived_at": datetime.utcnow().isoformat(),
                    },
                )
                db.add(session)
                await db.flush()
            
            for msg in messages:
                chat_msg = ChatMessage(
                    session_id=session.id,
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    message_metadata=msg.get("metadata", {}),
                )
                db.add(chat_msg)
            
            await db.commit()
            logger.info("chapter_conversation_archived", chapter=chapter_number, messages=len(messages))
            return True
            
        except Exception as e:
            logger.exception("conversation_archive_failed", error=str(e))
            return False


async def get_previous_chapter_context(
    book_id: str,
    current_chapter: int,
    user_id: str,
) -> Dict[str, Optional[str]]:
    """
    Get context for starting a new chapter.
    
    Returns:
        - previous_summary: Summary of just the previous chapter (for recap)
        - cumulative_summary: Condensed summary of ALL previous chapters (for context)
    """
    from app.models.learning import ChapterSummary
    from app.models.book import BookChapter
    
    if current_chapter <= 1:
        return {"previous_summary": None, "cumulative_summary": None}
    
    previous_chapter = current_chapter - 1
    
    async with async_session_maker() as db:
        try:
            chapter_result = await db.execute(
                select(BookChapter).where(
                    and_(
                        BookChapter.book_id == UUID(book_id),
                        BookChapter.chapter_number == previous_chapter
                    )
                )
            )
            chapter = chapter_result.scalar_one_or_none()
            
            if not chapter:
                return {"previous_summary": None, "cumulative_summary": None}
            
            # Get completion summary (just previous chapter)
            completion_result = await db.execute(
                select(ChapterSummary).where(
                    and_(
                        ChapterSummary.user_id == UUID(user_id),
                        ChapterSummary.book_id == UUID(book_id),
                        ChapterSummary.chapter_id == chapter.id,
                        ChapterSummary.summary_type == "completion"
                    )
                )
            )
            completion = completion_result.scalar_one_or_none()
            
            # Get cumulative summary (all chapters up to previous)
            cumulative_result = await db.execute(
                select(ChapterSummary).where(
                    and_(
                        ChapterSummary.user_id == UUID(user_id),
                        ChapterSummary.book_id == UUID(book_id),
                        ChapterSummary.chapter_id == chapter.id,
                        ChapterSummary.summary_type == "cumulative"
                    )
                )
            )
            cumulative = cumulative_result.scalar_one_or_none()
            
            return {
                "previous_summary": completion.summary_text if completion else None,
                "cumulative_summary": cumulative.summary_text if cumulative else None,
            }
            
        except Exception as e:
            logger.exception("previous_context_fetch_failed", error=str(e))
            return {"previous_summary": None, "cumulative_summary": None}


async def prepare_new_chapter_context(
    book_id: str,
    new_chapter_number: int,
    user_id: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepare context for starting a new chapter.
    
    Returns:
        - previous_summary: Just the previous chapter (for "In Chapter X we covered...")
        - cumulative_summary: All previous chapters condensed (for teacher context)
        - new_chapter_overview: What this chapter is about
    """
    from app.integrations.rag_client import get_rag_client, RAGClientError
    from app.models.book import Book, BookChapter
    
    async with async_session_maker() as db:
        book_result = await db.execute(
            select(Book).where(Book.id == UUID(book_id))
        )
        book = book_result.scalar_one_or_none()
        
        chapter_result = await db.execute(
            select(BookChapter).where(
                and_(
                    BookChapter.book_id == UUID(book_id),
                    BookChapter.chapter_number == new_chapter_number
                )
            )
        )
        chapter = chapter_result.scalar_one_or_none()
        
        if not book or not chapter:
            return {
                "previous_summary": None,
                "cumulative_summary": None,
                "new_chapter_overview": None,
                "new_chapter_title": f"Chapter {new_chapter_number}",
                "success": False,
            }
        
        new_chapter_title = chapter.title or f"Chapter {new_chapter_number}"
        
        # Get previous chapter context (both types)
        prev_context = await get_previous_chapter_context(book_id, new_chapter_number, user_id)
        
        # Get new chapter overview from RAG
        new_chapter_overview = None
        document_id = book.book_metadata.get("rag_document_id") if book.book_metadata else None
        chapter_id = chapter.key_concepts.get("rag_chapter_id") if chapter.key_concepts else None
        
        if document_id:
            try:
                client = get_rag_client()
                response = await client.search(
                    query=f"What topics and concepts are introduced in chapter {new_chapter_number}: {new_chapter_title}?",
                    document_id=document_id,
                    chapter_ids=[chapter_id] if chapter_id else None,
                    limit=3,
                    user_id=user_id,
                )
                if response.results:
                    new_chapter_overview = response.results[0].content[:500]
            except RAGClientError as e:
                logger.warning("new_chapter_overview_fetch_failed", error=str(e))
        
        return {
            "previous_summary": prev_context.get("previous_summary"),
            "cumulative_summary": prev_context.get("cumulative_summary"),
            "new_chapter_overview": new_chapter_overview,
            "new_chapter_title": new_chapter_title,
            "new_chapter_number": new_chapter_number,
            "book_title": book.title,
            "success": True,
        }


def format_chapter_transition_message(
    previous_chapter: int,
    previous_summary: Optional[str],
    new_chapter: int,
    new_chapter_title: str,
    new_chapter_overview: Optional[str],
) -> str:
    """Format the transition message when moving to a new chapter."""
    parts = []
    
    if previous_summary:
        parts.append(f"🎉 **You finished Chapter {previous_chapter}!**")
        parts.append("")
        parts.append("Here's what we covered together:")
        parts.append(previous_summary)
        parts.append("")
        parts.append("---")
        parts.append("")
    
    parts.append(f"📖 **Next up: Chapter {new_chapter} - {new_chapter_title}**")
    parts.append("")
    
    if new_chapter_overview:
        parts.append("Here's a taste of what we'll explore:")
        parts.append(new_chapter_overview[:300])
    else:
        parts.append("I'm excited to walk you through the key ideas in this chapter.")
    
    parts.append("")
    parts.append("Take a moment if you need it. When you're ready, just say **let's go** and we'll begin!")
    
    return "\n".join(parts)
