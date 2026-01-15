"""
Retrieval Tool - RAG context retrieval for TeacherAgent.

This is a TOOL, not an agent. TeacherAgent calls this to get context.

Key Features:
1. Cross-chapter retrieval with current chapter boost
2. Previous chapter summary inclusion
3. Formatted context ready for TeacherAgent prompt
4. Redis caching for frequently accessed data
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.rag.embeddings import EmbeddingService
from app.services.cache_service import get_cache_service

logger = get_logger(__name__)
cache = get_cache_service()


@dataclass
class RetrievalResult:
    """Result from retrieval tool."""
    chunks: List[Dict[str, Any]]          # Retrieved chunks with content
    previous_summary: Optional[str]        # Summary from previous chapter
    cross_chapter_refs: List[Dict[str, Any]]  # Chunks from other chapters
    formatted_context: str                 # Pre-formatted for prompt


async def retrieve_context(
    query: str,
    book_id: str,
    current_chapter: int,
    user_id: str,
    api_key: Optional[str] = None,
    db: Optional[AsyncSession] = None,
) -> RetrievalResult:
    """
    Retrieve relevant context for TeacherAgent.
    
    This is the main retrieval tool function. It:
    1. Retrieves chunks from current chapter (boosted priority)
    2. Retrieves chunks from other chapters (for cross-references)
    3. Loads previous chapter summary for continuity
    4. Formats everything for the TeacherAgent prompt
    
    Args:
        query: User's message or topic to retrieve context for
        book_id: Book ID to search
        current_chapter: Current chapter number
        user_id: User ID (for personalized summaries)
        api_key: OpenAI API key for embeddings
        db: Database session (will create if not provided)
        
    Returns:
        RetrievalResult with chunks, summary, and formatted context
    """
    from app.db.database import async_session_maker
    
    # Create embedding service
    embedding_service = EmbeddingService(api_key=api_key)
    
    # Use provided db or create new session
    should_close_db = db is None
    if db is None:
        db = async_session_maker()
    
    try:
        # Get query embedding
        query_embedding = await embedding_service.embed_text(query)
        
        # Retrieve from current chapter (primary, boosted)
        current_chapter_chunks = await _retrieve_from_chapter(
            db=db,
            query_embedding=query_embedding,
            book_id=book_id,
            chapter_number=current_chapter,
            limit=6,  # More from current chapter
        )
        
        # Retrieve from other chapters (secondary, for cross-references)
        other_chapter_chunks = await _retrieve_from_other_chapters(
            db=db,
            query_embedding=query_embedding,
            book_id=book_id,
            current_chapter=current_chapter,
            limit=3,  # Fewer from other chapters
        )
        
        # Load previous chapter summary
        previous_summary = await _get_previous_chapter_summary(
            db=db,
            user_id=user_id,
            book_id=book_id,
            current_chapter=current_chapter,
        )
        
        # Merge and format results
        all_chunks = _merge_and_rank_chunks(
            current_chapter_chunks,
            other_chapter_chunks,
            boost_factor=1.5,  # Boost current chapter relevance
        )
        
        # Format for prompt
        formatted_context = _format_context_for_prompt(
            chunks=all_chunks,
            previous_summary=previous_summary,
            current_chapter=current_chapter,
        )
        
        logger.info(
            "retrieval_complete",
            book_id=book_id,
            current_chapter=current_chapter,
            current_chunks=len(current_chapter_chunks),
            other_chunks=len(other_chapter_chunks),
            has_summary=previous_summary is not None,
        )
        
        return RetrievalResult(
            chunks=all_chunks,
            previous_summary=previous_summary,
            cross_chapter_refs=other_chapter_chunks,
            formatted_context=formatted_context,
        )
        
    except Exception as e:
        logger.exception("retrieval_failed", error=str(e))
        # Return empty result on failure
        return RetrievalResult(
            chunks=[],
            previous_summary=None,
            cross_chapter_refs=[],
            formatted_context="No context available.",
        )
    finally:
        if should_close_db:
            await db.close()


async def _retrieve_from_chapter(
    db: AsyncSession,
    query_embedding: List[float],
    book_id: str,
    chapter_number: int,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """Retrieve chunks from a specific chapter."""
    
    # Format embedding as PostgreSQL array literal
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    
    # First try with embeddings (vector similarity search)
    query = text("""
        SELECT 
            dc.id,
            dc.content,
            dc.section_title,
            dc.chunk_index,
            dc.chunk_metadata,
            dc.token_count,
            bc.chapter_number,
            bc.title as chapter_title,
            CASE WHEN dc.embedding IS NOT NULL 
                 THEN 1 - (dc.embedding <=> CAST(:embedding AS vector))
                 ELSE 0.5 
            END as similarity
        FROM document_chunks dc
        JOIN book_chapters bc ON dc.chapter_id = bc.id
        WHERE dc.book_id = CAST(:book_id AS uuid)
          AND bc.chapter_number = :chapter_number
        ORDER BY 
            CASE WHEN dc.embedding IS NOT NULL 
                 THEN dc.embedding <=> CAST(:embedding AS vector)
                 ELSE dc.chunk_index::float / 1000 
            END
        LIMIT :limit
    """)
    
    try:
        result = await db.execute(
            query,
            {
                "embedding": embedding_str,
                "book_id": book_id,
                "chapter_number": chapter_number,
                "limit": limit,
            }
        )
        rows = result.fetchall()
        
        chunks = []
        for row in rows:
            chunks.append({
                "id": str(row.id),
                "content": row.content,
                "section_title": row.section_title,
                "chunk_index": row.chunk_index,
                "metadata": row.chunk_metadata or {},
                "token_count": row.token_count,
                "chapter_number": row.chapter_number,
                "chapter_title": row.chapter_title,
                "similarity": float(row.similarity),
                "is_current_chapter": True,
            })
        
        return chunks
        
    except Exception as e:
        logger.warning("chapter_retrieval_failed", chapter=chapter_number, error=str(e))
        return []


async def _retrieve_from_other_chapters(
    db: AsyncSession,
    query_embedding: List[float],
    book_id: str,
    current_chapter: int,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Retrieve chunks from chapters other than current (for cross-references)."""
    
    # Format embedding as PostgreSQL array literal
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    
    query = text("""
        SELECT 
            dc.id,
            dc.content,
            dc.section_title,
            dc.chunk_index,
            dc.chunk_metadata,
            dc.token_count,
            bc.chapter_number,
            bc.title as chapter_title,
            CASE WHEN dc.embedding IS NOT NULL 
                 THEN 1 - (dc.embedding <=> CAST(:embedding AS vector))
                 ELSE 0.5 
            END as similarity
        FROM document_chunks dc
        JOIN book_chapters bc ON dc.chapter_id = bc.id
        WHERE dc.book_id = CAST(:book_id AS uuid)
          AND bc.chapter_number != :current_chapter
          AND bc.chapter_number < :current_chapter  -- Only from previous chapters
        ORDER BY 
            CASE WHEN dc.embedding IS NOT NULL 
                 THEN dc.embedding <=> CAST(:embedding AS vector)
                 ELSE dc.chunk_index::float / 1000 
            END
        LIMIT :limit
    """)
    
    try:
        result = await db.execute(
            query,
            {
                "embedding": embedding_str,
                "book_id": book_id,
                "current_chapter": current_chapter,
                "limit": limit,
            }
        )
        rows = result.fetchall()
        
        chunks = []
        for row in rows:
            chunks.append({
                "id": str(row.id),
                "content": row.content,
                "section_title": row.section_title,
                "chunk_index": row.chunk_index,
                "metadata": row.chunk_metadata or {},
                "token_count": row.token_count,
                "chapter_number": row.chapter_number,
                "chapter_title": row.chapter_title,
                "similarity": float(row.similarity),
                "is_current_chapter": False,
            })
        
        return chunks
        
    except Exception as e:
        logger.warning("cross_chapter_retrieval_failed", error=str(e))
        return []


async def _get_previous_chapter_summary(
    db: AsyncSession,
    user_id: str,
    book_id: str,
    current_chapter: int,
) -> Optional[str]:
    """Get summary from the previous chapter for continuity."""
    
    if current_chapter <= 1:
        return None
    
    previous_chapter = current_chapter - 1
    
    # Try cache first
    cache_key = f"chapter_summary:{user_id}:{book_id}:{previous_chapter}"
    cached_summary = await cache.get(cache_key)
    if cached_summary:
        logger.debug("chapter_summary_cache_hit", chapter=previous_chapter)
        return cached_summary
    
    query = text("""
        SELECT cs.summary_text
        FROM chapter_summaries cs
        JOIN book_chapters bc ON cs.chapter_id = bc.id
        WHERE cs.user_id = CAST(:user_id AS uuid)
          AND cs.book_id = CAST(:book_id AS uuid)
          AND bc.chapter_number = :chapter_number
        ORDER BY cs.created_at DESC
        LIMIT 1
    """)
    
    try:
        result = await db.execute(
            query,
            {
                "user_id": user_id,
                "book_id": book_id,
                "chapter_number": previous_chapter,
            }
        )
        row = result.fetchone()
        
        if row:
            # Cache the summary for future requests
            await cache.set(cache_key, row.summary_text, settings.cache_ttl_chapter_summary)
            return row.summary_text
        return None
        
    except Exception as e:
        logger.warning("summary_retrieval_failed", error=str(e))
        return None


def _merge_and_rank_chunks(
    current_chunks: List[Dict[str, Any]],
    other_chunks: List[Dict[str, Any]],
    boost_factor: float = 1.5,
) -> List[Dict[str, Any]]:
    """
    Merge chunks from current and other chapters, applying boost to current chapter.
    
    Args:
        current_chunks: Chunks from current chapter
        other_chunks: Chunks from other chapters
        boost_factor: Multiplier for current chapter similarity scores
        
    Returns:
        Merged and sorted list of chunks
    """
    # Apply boost to current chapter chunks
    for chunk in current_chunks:
        chunk["boosted_similarity"] = chunk["similarity"] * boost_factor
    
    # Other chapters keep original similarity
    for chunk in other_chunks:
        chunk["boosted_similarity"] = chunk["similarity"]
    
    # Merge all chunks
    all_chunks = current_chunks + other_chunks
    
    # Sort by boosted similarity
    all_chunks.sort(key=lambda x: x["boosted_similarity"], reverse=True)
    
    # Take top 8 chunks total
    return all_chunks[:8]


def _format_context_for_prompt(
    chunks: List[Dict[str, Any]],
    previous_summary: Optional[str],
    current_chapter: int,
) -> str:
    """
    Format retrieved context for inclusion in TeacherAgent prompt.
    
    Creates a structured context string that TeacherAgent can use.
    """
    parts = []
    
    # Add previous chapter summary if available
    if previous_summary:
        parts.append(f"**PREVIOUS CHAPTER SUMMARY (Chapter {current_chapter - 1}):**")
        parts.append(previous_summary)
        parts.append("")
    else:
        parts.append("**PREVIOUS CHAPTER SUMMARY:**")
        parts.append("This is the first chapter or no summary available.")
        parts.append("")
    
    # Add current chapter content
    parts.append(f"**RETRIEVED CONTENT FOR CHAPTER {current_chapter}:**")
    parts.append("")
    
    current_chapter_chunks = [c for c in chunks if c.get("is_current_chapter", True)]
    other_chapter_chunks = [c for c in chunks if not c.get("is_current_chapter", True)]
    
    # Format current chapter chunks
    for i, chunk in enumerate(current_chapter_chunks, 1):
        section = chunk.get("section_title", "")
        section_label = f" ({section})" if section else ""
        content = chunk.get("content", "")
        relevance = chunk.get("similarity", 0) * 100
        
        parts.append(f"[{i}]{section_label} (Relevance: {relevance:.0f}%):")
        parts.append(content)
        parts.append("")
    
    # Format cross-chapter references
    if other_chapter_chunks:
        parts.append("**RELATED CONTENT FROM PREVIOUS CHAPTERS:**")
        parts.append("(Reference these naturally if the student asks about related concepts)")
        parts.append("")
        
        for chunk in other_chapter_chunks:
            ch_num = chunk.get("chapter_number", "?")
            ch_title = chunk.get("chapter_title", "")
            section = chunk.get("section_title", "")
            content = chunk.get("content", "")[:300]  # Truncate for brevity
            
            parts.append(f"[From Chapter {ch_num}: {ch_title}]")
            if section:
                parts.append(f"Section: {section}")
            parts.append(f"{content}...")
            parts.append("")
    
    return "\n".join(parts)


# Convenience function for simple retrieval
async def quick_retrieve(
    query: str,
    book_id: str,
    chapter: int,
    api_key: Optional[str] = None,
) -> str:
    """
    Quick retrieval that returns just the formatted context string.
    
    Use this when you just need the context for a prompt.
    """
    from app.db.database import async_session_maker
    
    async with async_session_maker() as db:
        result = await retrieve_context(
            query=query,
            book_id=book_id,
            current_chapter=chapter,
            user_id="",  # Not needed for basic retrieval
            api_key=api_key,
            db=db,
        )
        return result.formatted_context
