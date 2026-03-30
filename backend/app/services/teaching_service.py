"""
Teaching service - generates teaching content using external RAG service.

NOTE: This service is largely superseded by the TeacherAgent + RAGOrchestrator.
It's kept for backward compatibility with some Temporal activities.

For new code, use:
- app/agents/teacher.py - TeacherAgent
- app/services/rag_orchestrator.py - RAGOrchestrator
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from openai import AsyncOpenAI
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session_maker
from app.logs.logger import get_logger
from app.models.learning import ChapterSummary
from app.models.book import BookChapter

logger = get_logger(__name__)


async def _retrieve_via_external_rag(
    book_id: str,
    chapter: int,
    query: str,
    user_id: str = "",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Retrieve chunks via external RAG service.
    
    This replaces the old internal retrieve_chapter_chunks function.
    """
    from app.integrations.rag_client import get_rag_client, RAGClientError
    from app.models.book import Book, BookChapter
    
    async with async_session_maker() as db:
        # Get RAG document ID from book
        result = await db.execute(
            select(Book).where(Book.id == UUID(book_id))
        )
        book = result.scalar_one_or_none()
        
        if not book or not book.book_metadata:
            logger.warning("book_not_found_for_rag", book_id=book_id)
            return []
        
        document_id = book.book_metadata.get("rag_document_id")
        if not document_id:
            logger.warning("rag_document_id_not_found", book_id=book_id)
            return []
        
        # Get chapter RAG ID
        chapter_result = await db.execute(
            select(BookChapter)
            .where(BookChapter.book_id == book.id)
            .where(BookChapter.chapter_number == chapter)
        )
        chapter_obj = chapter_result.scalar_one_or_none()
        
        chapter_id = None
        if chapter_obj and chapter_obj.key_concepts:
            chapter_id = chapter_obj.key_concepts.get("rag_chapter_id")
    
    # Call external RAG
    try:
        client = get_rag_client()
        
        if chapter_id:
            response = await client.search(
                query=query,
                document_id=document_id,
                chapter_ids=[chapter_id],
                limit=limit,
                user_id=user_id,
            )
        else:
            response = await client.search(
                query=query,
                document_id=document_id,
                limit=limit,
                user_id=user_id,
            )
        
        return [
            {
                "id": r.chunk_id,
                "content": r.content,
                "section_title": r.section_title,
                "similarity": r.similarity_score,
            }
            for r in response.results
        ]
        
    except RAGClientError as e:
        logger.warning("external_rag_search_failed", error=str(e))
        return []
    except Exception as e:
        logger.exception("rag_retrieval_error", error=str(e))
        return []


async def generate_teaching(
    book_id: str,
    chapter: int,
    topic_index: int,
    user_message: Optional[str],
    api_key: Optional[str] = None,
    user_id: str = "",
) -> Dict[str, Any]:
    """
    Generate teaching content for a chapter topic.
    
    NOTE: For new implementations, use TeacherAgent + RAGOrchestrator instead.
    This function is kept for backward compatibility.
    """
    async with async_session_maker() as db:
        # Get chapter info
        chapter_result = await db.execute(
            select(BookChapter).where(
                BookChapter.book_id == UUID(book_id),
                BookChapter.chapter_number == chapter
            )
        )
        chapter_info = chapter_result.scalar_one_or_none()
        chapter_title = chapter_info.title if chapter_info else f"Chapter {chapter}"
        
        # Get content via external RAG
        search_query = user_message if user_message else f"chapter {chapter} main concepts introduction overview"
        chunks = await _retrieve_via_external_rag(book_id, chapter, search_query, user_id)
        
        if not chunks:
            chunks = await _retrieve_via_external_rag(book_id, chapter, "key concepts fundamentals", user_id)
        
        context = "\n---\n".join([c.get("content", "")[:500] for c in chunks[:5]]) if chunks else ""
        
        client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        
        # Build prompt based on context
        if topic_index == 0 and not user_message:
            prompt = f"""You are Professor, starting to teach Chapter {chapter}: "{chapter_title}".

Content from this chapter:
{context}

INSTRUCTIONS:
1. Begin with an engaging introduction to this chapter
2. Explain why this topic matters and what the student will learn
3. Start teaching the FIRST key concept from the content above
4. Be clear, use examples, and build excitement about learning
5. Keep it 200-300 words
6. End with a transition like "Let's dive deeper into..." or "Now that we understand the basics..."

DO NOT ask "What would you like to learn?" - YOU are the professor, YOU drive the teaching."""

        elif user_message:
            prompt = f"""You are Professor, teaching Chapter {chapter}: "{chapter_title}".

Content from this chapter:
{context}

Student said: {user_message}

INSTRUCTIONS:
1. Address the student's input appropriately
2. If it's a question, answer it using the chapter content
3. If it's confirmation/agreement, continue teaching the next concept
4. Keep explanations clear with examples
5. 200-300 words
6. After addressing their input, guide them to the next topic

Remember: You drive the learning flow, not the student."""

        else:
            prompt = f"""You are Professor, continuing to teach Chapter {chapter}: "{chapter_title}".

We've been covering this chapter. Here's the next section of content:
{context}

INSTRUCTIONS:
1. Continue explaining the next key concept from the content
2. Connect it to what was previously discussed if relevant
3. Use clear explanations and examples
4. Keep it 200-300 words
5. End with a natural transition to the next topic

You are the professor - keep the lesson flowing."""

        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "You are an expert professor who teaches proactively."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.7,
        )
        
        return {
            "content": response.choices[0].message.content,
            "chunks": chunks,
            "next_topic_index": topic_index + 1,
            "topics": [c.get("section_title", f"Topic {i}") for i, c in enumerate(chunks[:5])],
        }


async def answer_doubt(
    book_id: str,
    chapter: int,
    question: str,
    api_key: Optional[str] = None,
    user_id: str = "",
) -> str:
    """Answer a student's doubt about the chapter."""
    chunks = await _retrieve_via_external_rag(book_id, chapter, question, user_id, limit=3)
    context = "\n---\n".join([c.get("content", "")[:400] for c in chunks])
    
    client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
    
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": "You are a helpful professor clarifying doubts."},
            {"role": "user", "content": f"Context:\n{context}\n\nStudent's doubt: {question}\n\nAnswer clearly and concisely."}
        ],
        max_tokens=400,
        temperature=0.7,
    )
    
    return response.choices[0].message.content


async def generate_summary(
    book_id: str,
    chapter: int,
    user_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Generate chapter summary and STORE it in DB."""
    chunks = await _retrieve_via_external_rag(book_id, chapter, "summary key concepts", user_id or "")
    context = "\n---\n".join([c.get("content", "")[:300] for c in chunks[:5]])
    
    client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
    
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": "You summarize educational content concisely."},
            {"role": "user", "content": f"Summarize these key points in 3-5 bullet points:\n{context}"}
        ],
        max_tokens=300,
        temperature=0.5,
    )
    
    summary_text = response.choices[0].message.content
    
    # Store summary in database
    if user_id:
        async with async_session_maker() as db:
            try:
                chapter_result = await db.execute(
                    select(BookChapter.id).where(
                        BookChapter.book_id == UUID(book_id),
                        BookChapter.chapter_number == chapter
                    )
                )
                chapter_row = chapter_result.first()
                
                if chapter_row:
                    chapter_id = chapter_row[0]
                    
                    existing = await db.execute(
                        select(ChapterSummary).where(
                            ChapterSummary.user_id == UUID(user_id),
                            ChapterSummary.book_id == UUID(book_id),
                            ChapterSummary.chapter_id == chapter_id,
                            ChapterSummary.summary_type == "completion"
                        )
                    )
                    
                    if not existing.scalar_one_or_none():
                        chapter_summary = ChapterSummary(
                            user_id=UUID(user_id),
                            book_id=UUID(book_id),
                            chapter_id=chapter_id,
                            summary_type="completion",
                            summary_text=summary_text,
                            key_concepts={"chapter": chapter},
                        )
                        db.add(chapter_summary)
                        await db.commit()
                        logger.info("chapter_summary_stored", chapter=chapter, user_id=user_id)
            except Exception as e:
                logger.exception("failed_to_store_summary", error=str(e))
    
    return summary_text


async def get_previous_chapter_recap(
    book_id: str,
    current_chapter: int,
    user_id: str,
) -> Optional[str]:
    """Get recap of previous chapter for continuity."""
    if current_chapter <= 1:
        return None
    
    previous_chapter = current_chapter - 1
    
    async with async_session_maker() as db:
        try:
            chapter_result = await db.execute(
                select(BookChapter.id, BookChapter.title).where(
                    BookChapter.book_id == UUID(book_id),
                    BookChapter.chapter_number == previous_chapter
                )
            )
            chapter_row = chapter_result.first()
            
            if not chapter_row:
                return None
            
            chapter_id, chapter_title = chapter_row
            
            summary_result = await db.execute(
                select(ChapterSummary.summary_text).where(
                    ChapterSummary.user_id == UUID(user_id),
                    ChapterSummary.book_id == UUID(book_id),
                    ChapterSummary.chapter_id == chapter_id,
                    ChapterSummary.summary_type == "completion"
                )
            )
            summary_row = summary_result.first()
            
            if summary_row:
                return f"**Recap of Chapter {previous_chapter}** ({chapter_title or ''}):\n{summary_row[0]}"
            
            return None
            
        except Exception as e:
            logger.exception("failed_to_get_recap", error=str(e))
            return None
