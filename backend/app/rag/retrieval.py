"""RAG retrieval functions."""

from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)


class RetrievalService:
    """Service wrapper for retrieval functions."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
    
    async def retrieve(self, db: AsyncSession, book_id: str, chapter: int, query: str) -> List[Dict]:
        return await retrieve_chapter_chunks(db, book_id, chapter, query, self.api_key)


async def retrieve_chapter_chunks(
    db: AsyncSession,
    book_id: str,
    chapter_number: int,
    query: str,
    api_key: Optional[str] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Retrieve relevant chunks from a chapter using vector similarity."""
    
    if not query:
        query = "main concepts introduction"
    
    client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
    
    try:
        embedding_response = await client.embeddings.create(
            model=settings.embedding_model,
            input=query,
        )
        query_embedding = embedding_response.data[0].embedding
    except Exception as e:
        logger.exception("embedding_failed", error=str(e))
        return []
    
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    
    sql = text("""
        SELECT 
            dc.id,
            dc.content,
            dc.section_title,
            dc.chunk_index,
            1 - (dc.embedding <=> CAST(:embedding AS vector)) as similarity
        FROM document_chunks dc
        JOIN book_chapters bc ON dc.chapter_id = bc.id
        WHERE dc.book_id = CAST(:book_id AS uuid)
          AND bc.chapter_number = :chapter_number
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)
    
    try:
        result = await db.execute(sql, {
            "embedding": embedding_str,
            "book_id": book_id,
            "chapter_number": chapter_number,
            "limit": limit,
        })
        rows = result.fetchall()
        
        chunks = [
            {
                "id": str(row.id),
                "content": row.content,
                "section_title": row.section_title,
                "chunk_index": row.chunk_index,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]
        
        logger.info("chunks_retrieved", book_id=book_id, chapter=chapter_number, count=len(chunks))
        return chunks
        
    except Exception as e:
        logger.exception("retrieval_failed", error=str(e))
        return []
