"""Retrieval Agent - RAG-based context retrieval for teaching."""

from typing import Any, Dict, List, Optional
import json

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.config import settings
from app.logs.logger import get_logger
from app.rag.embeddings import EmbeddingService
from app.utils.state_helpers import safe_get, safe_get_int

logger = get_logger(__name__)


class RetrievalAgent(BaseAgent):
    """
    Retrieves relevant context from vector store.
    
    Responsibilities:
    - Embed user queries
    - Perform chapter-scoped vector search
    - Detect cross-chapter references
    - Format retrieved context for teaching
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        super().__init__(api_key, model)
        self.embedding_service = EmbeddingService(api_key=api_key)
    
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieve relevant context for the user's query.
        
        Args:
            state: Current UserState with user_query
            
        Returns:
            Updated state with retrieved_chunks and cross_references
        """
        from app.db.database import async_session_maker
        
        query = safe_get(state, "user_query", "")
        book_id = safe_get(state, "active_book_id")
        current_chapter = safe_get_int(state, "current_chapter", 1)
        
        if not query or not book_id:
            return {
                "retrieved_chunks": [],
                "cross_references": None,
                "agent_name": "RetrievalAgent",
            }
        
        try:
            # Get query embedding
            query_embedding = await self.embedding_service.embed_text(query)
            
            # Create own db session to avoid async context issues
            async with async_session_maker() as db:
                # Perform chapter-scoped retrieval
                chunks = await self._retrieve_chunks(
                    db=db,
                    query_embedding=query_embedding,
                    book_id=book_id,
                    chapter_number=current_chapter,
                    limit=settings.retrieval_top_k,
                )
                
                # Check for cross-chapter references (simplified - skip for now)
                cross_refs = None
            
            # Format chunks for context
            formatted_chunks = self._format_chunks(chunks)
            
            logger.info(
                "retrieval_complete",
                user_id=safe_get(state, "user_id"),
                book_id=book_id,
                chapter=current_chapter,
                chunks_retrieved=len(chunks),
                has_cross_refs=cross_refs is not None,
            )
            
            return {
                "retrieved_chunks": formatted_chunks,
                "cross_references": cross_refs,
                "retrieval_count": len(chunks),
                "agent_name": "RetrievalAgent",
            }
            
        except Exception as e:
            logger.exception(
                "retrieval_failed",
                user_id=safe_get(state, "user_id"),
                error=str(e),
            )
            return {
                "retrieved_chunks": [],
                "cross_references": None,
                "agent_name": "RetrievalAgent",
                "retrieval_error": str(e),
            }
    
    async def _retrieve_chunks(
        self,
        db: Optional[AsyncSession],
        query_embedding: List[float],
        book_id: str,
        chapter_number: int,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks using PGVector similarity search.
        
        Args:
            db: Database session
            query_embedding: Query vector
            book_id: Book ID to search
            chapter_number: Current chapter (strict scope)
            limit: Max chunks to return
            
        Returns:
            List of chunk dictionaries
        """
        if db is None:
            logger.warning("no_db_session_for_retrieval")
            return []
        
        # Format embedding as PostgreSQL array literal
        # Convert list to string format: '[0.1, 0.2, ...]'
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        
        # SQL query with vector similarity search
        # Uses CAST instead of :: to avoid SQLAlchemy parameter parsing issues
        # The cosine distance operator <=> returns values 0-2 (0 = identical, 2 = opposite)
        query = text("""
            SELECT 
                dc.id,
                dc.content,
                dc.section_title,
                dc.chunk_index,
                dc.chunk_metadata,
                dc.token_count,
                1 - (dc.embedding <=> CAST(:embedding AS vector)) as similarity
            FROM document_chunks dc
            JOIN book_chapters bc ON dc.chapter_id = bc.id
            WHERE dc.book_id = CAST(:book_id AS uuid)
              AND bc.chapter_number = :chapter_number
            ORDER BY dc.embedding <=> CAST(:embedding AS vector)
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
                    "similarity": float(row.similarity),
                })
            
            logger.info(
                "chunks_retrieved_from_db",
                book_id=book_id,
                chapter_number=chapter_number,
                count=len(chunks),
            )
            
            return chunks
            
        except Exception as e:
            logger.exception("chunk_retrieval_query_failed", error=str(e))
            return []
    
    async def _detect_cross_references(
        self,
        query: str,
        book_id: str,
        current_chapter: int,
        db: Optional[AsyncSession],
        redis: Optional[Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if query references topics from previous chapters.
        
        Args:
            query: User's query
            book_id: Book ID
            current_chapter: Current chapter number
            db: Database session
            redis: Redis client
            
        Returns:
            Cross-reference data or None
        """
        if current_chapter <= 1:
            # No previous chapters to reference
            return None
        
        # Try to get topic graph from cache
        topic_graph = None
        if redis:
            try:
                cached = await redis.get(f"topics_graph:{book_id}")
                if cached:
                    topic_graph = json.loads(cached)
            except Exception:
                pass
        
        if not topic_graph and db:
            # Build topic graph from database
            topic_graph = await self._build_topic_graph(db, book_id)
            
            # Cache it
            if redis and topic_graph:
                try:
                    await redis.setex(
                        f"topics_graph:{book_id}",
                        settings.cache_ttl_chapter_summary,
                        json.dumps(topic_graph),
                    )
                except Exception:
                    pass
        
        if not topic_graph:
            return None
        
        # Extract topics from query
        query_topics = await self._extract_topics_from_query(query)
        
        # Find matching topics from previous chapters
        references = []
        for topic in query_topics:
            topic_lower = topic.lower()
            for graph_topic, info in topic_graph.items():
                if topic_lower in graph_topic.lower() or graph_topic.lower() in topic_lower:
                    source_chapter = info.get("chapter", 0)
                    if source_chapter < current_chapter:
                        references.append({
                            "topic": graph_topic,
                            "source_chapter": source_chapter,
                            "relationship": info.get("relationship", "related"),
                            "summary": info.get("summary", ""),
                        })
        
        if not references:
            return None
        
        return {
            "references": references,
            "query_topics": query_topics,
        }
    
    async def _build_topic_graph(
        self,
        db: AsyncSession,
        book_id: str,
    ) -> Dict[str, Any]:
        """Build topic relationship graph from database."""
        query = text("""
            SELECT 
                tr.topic,
                bc.chapter_number,
                tr.relationship_type,
                cs.summary_text
            FROM topic_relationships tr
            JOIN book_chapters bc ON tr.source_chapter_id = bc.id
            LEFT JOIN chapter_summaries cs ON cs.chapter_id = bc.id
            WHERE tr.book_id = :book_id
            ORDER BY bc.chapter_number
        """)
        
        try:
            result = await db.execute(query, {"book_id": book_id})
            rows = result.fetchall()
            
            graph = {}
            for row in rows:
                summary_text = row.summary_text[:200] if row.summary_text else ""
                graph[row.topic] = {
                    "chapter": row.chapter_number,
                    "relationship": row.relationship_type,
                    "summary": summary_text,
                }
            
            return graph
            
        except Exception as e:
            logger.warning("topic_graph_build_failed", error=str(e))
            return {}
    
    async def _extract_topics_from_query(self, query: str) -> List[str]:
        """
        Extract key topics from a user query using LLM.
        
        Args:
            query: User's query
            
        Returns:
            List of extracted topics
        """
        prompt = f"""Extract the key topics/concepts from this learning question:

Question: {query}

Return a JSON object with a "topics" array containing 1-5 key topics.
Example: {{"topics": ["topic1", "topic2"]}}"""

        try:
            result = await self.generate_json(
                prompt=prompt,
                system_prompt="You are a topic extraction assistant. Return only valid JSON.",
                max_tokens=100,
                temperature=0.1,
            )
            return result.get("topics", [])
        except Exception:
            # Fallback: extract nouns from query
            return self._simple_topic_extraction(query)
    
    def _simple_topic_extraction(self, query: str) -> List[str]:
        """Simple fallback topic extraction."""
        # Remove common words and extract potential topics
        stop_words = {
            "what", "how", "why", "when", "where", "is", "are", "the", "a", "an",
            "in", "on", "at", "to", "for", "of", "and", "or", "but", "can", "you",
            "me", "this", "that", "about", "explain", "tell", "help", "understand",
        }
        
        words = query.lower().split()
        topics = [w for w in words if w not in stop_words and len(w) > 3]
        return topics[:5]
    
    def _format_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format chunks for teaching context."""
        formatted = []
        for i, chunk in enumerate(chunks):
            similarity = chunk.get('similarity', 0)
            formatted.append({
                "index": i + 1,
                "content": chunk["content"],
                "section": chunk.get("section_title", ""),
                "relevance": f"{similarity*100:.1f}%",
            })
        return formatted
