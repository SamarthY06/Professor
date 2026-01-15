"""
Cache Service - Redis caching for performance.

Provides multi-layer caching for sub-second responses.
"""

import json
from typing import Any, Callable, Optional, TypeVar

import redis.asyncio as redis

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheService:
    """
    Multi-layer caching service using Redis.
    
    Cache layers:
    - User state (1 hour)
    - Chapter chunks (1 hour)
    - Chapter summaries (24 hours)
    - Conversation (30 min)
    - Embeddings (7 days)
    """
    
    # TTL configuration (in seconds)
    TTLS = {
        "user_state": settings.cache_ttl_user_state,      # 1 hour
        "chapter_chunks": settings.cache_ttl_chapter_chunks,  # 1 hour
        "chapter_summary": settings.cache_ttl_chapter_summary,  # 24 hours
        "conversation": settings.cache_ttl_conversation,    # 30 min
        "embeddings": settings.cache_ttl_embeddings,      # 7 days
    }
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
    
    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=0,
                decode_responses=True,
            )
        return self._client
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        try:
            client = await self._get_client()
            value = await client.get(key)
            
            if value is not None:
                logger.debug("cache_hit", key=key[:50])
                return json.loads(value)
            
            logger.debug("cache_miss", key=key[:50])
            return None
            
        except Exception as e:
            logger.warning("cache_get_error", key=key[:50], error=str(e))
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            client = await self._get_client()
            serialized = json.dumps(value, default=str)
            
            if ttl:
                await client.setex(key, ttl, serialized)
            else:
                await client.set(key, serialized)
            
            logger.debug("cache_set", key=key[:50], ttl=ttl)
            return True
            
        except Exception as e:
            logger.warning("cache_set_error", key=key[:50], error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Delete a value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted
        """
        try:
            client = await self._get_client()
            await client.delete(key)
            logger.debug("cache_delete", key=key[:50])
            return True
            
        except Exception as e:
            logger.warning("cache_delete_error", key=key[:50], error=str(e))
            return False
    
    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], T],
        ttl: Optional[int] = None,
    ) -> T:
        """
        Get from cache or compute and store.
        
        Args:
            key: Cache key
            compute_fn: Async function to compute value if not cached
            ttl: Time to live in seconds
            
        Returns:
            Cached or computed value
        """
        cached = await self.get(key)
        if cached is not None:
            return cached
        
        # Compute and cache
        result = await compute_fn()
        await self.set(key, result, ttl)
        return result
    
    # ===============================
    # Specialized cache methods
    # ===============================
    
    async def get_user_state(
        self,
        user_id: str,
        book_id: str,
    ) -> Optional[dict]:
        """Get cached user learning state."""
        key = f"state:{user_id}:{book_id}"
        return await self.get(key)
    
    async def set_user_state(
        self,
        user_id: str,
        book_id: str,
        state: dict,
    ) -> bool:
        """Cache user learning state."""
        key = f"state:{user_id}:{book_id}"
        return await self.set(key, state, self.TTLS["user_state"])
    
    async def get_chapter_chunks(
        self,
        user_id: str,
        book_id: str,
        chapter_id: str,
    ) -> Optional[list]:
        """Get cached chapter chunks."""
        key = f"chunks:{user_id}:{book_id}:{chapter_id}"
        return await self.get(key)
    
    async def set_chapter_chunks(
        self,
        user_id: str,
        book_id: str,
        chapter_id: str,
        chunks: list,
    ) -> bool:
        """Cache chapter chunks."""
        key = f"chunks:{user_id}:{book_id}:{chapter_id}"
        return await self.set(key, chunks, self.TTLS["chapter_chunks"])
    
    async def get_chapter_summary(
        self,
        user_id: str,
        chapter_id: str,
    ) -> Optional[str]:
        """Get cached chapter summary."""
        key = f"summary:{user_id}:{chapter_id}"
        return await self.get(key)
    
    async def set_chapter_summary(
        self,
        user_id: str,
        chapter_id: str,
        summary: str,
    ) -> bool:
        """Cache chapter summary."""
        key = f"summary:{user_id}:{chapter_id}"
        return await self.set(key, summary, self.TTLS["chapter_summary"])
    
    async def get_conversation(
        self,
        session_id: str,
    ) -> Optional[list]:
        """Get cached conversation messages."""
        key = f"convo:{session_id}"
        return await self.get(key)
    
    async def set_conversation(
        self,
        session_id: str,
        messages: list,
    ) -> bool:
        """Cache conversation messages."""
        key = f"convo:{session_id}"
        return await self.set(key, messages, self.TTLS["conversation"])
    
    async def append_to_conversation(
        self,
        session_id: str,
        message: dict,
        max_messages: int = 10,
    ) -> bool:
        """Append a message to cached conversation."""
        key = f"convo:{session_id}"
        messages = await self.get(key) or []
        
        messages.append(message)
        
        # Keep only the last N messages
        if len(messages) > max_messages:
            messages = messages[-max_messages:]
        
        return await self.set(key, messages, self.TTLS["conversation"])
    
    async def get_topic_graph(
        self,
        book_id: str,
    ) -> Optional[dict]:
        """Get cached topic relationship graph."""
        key = f"topics_graph:{book_id}"
        return await self.get(key)
    
    async def set_topic_graph(
        self,
        book_id: str,
        graph: dict,
    ) -> bool:
        """Cache topic relationship graph."""
        key = f"topics_graph:{book_id}"
        return await self.set(key, graph, self.TTLS["chapter_summary"])
    
    async def get_embedding(
        self,
        content_hash: str,
    ) -> Optional[list]:
        """Get cached embedding."""
        key = f"emb:{content_hash}"
        return await self.get(key)
    
    async def set_embedding(
        self,
        content_hash: str,
        embedding: list,
    ) -> bool:
        """Cache embedding."""
        key = f"emb:{content_hash}"
        return await self.set(key, embedding, self.TTLS["embeddings"])
    
    async def preload_chapter_context(
        self,
        user_id: str,
        book_id: str,
        chapter_id: str,
        chunks: list,
        summary: str,
    ):
        """
        Preload chapter context into cache.
        
        Called when user starts a chapter for fast subsequent requests.
        """
        await self.set_chapter_chunks(user_id, book_id, chapter_id, chunks)
        await self.set_chapter_summary(user_id, chapter_id, summary)
        
        logger.info(
            "chapter_context_preloaded",
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            chunks_count=len(chunks),
        )
    
    async def invalidate_user_cache(
        self,
        user_id: str,
        book_id: Optional[str] = None,
    ):
        """
        Invalidate all cache entries for a user.
        
        Used when user data changes significantly.
        """
        client = await self._get_client()
        
        patterns = [f"state:{user_id}:*"]
        if book_id:
            patterns.append(f"chunks:{user_id}:{book_id}:*")
        
        for pattern in patterns:
            async for key in client.scan_iter(pattern):
                await client.delete(key)
        
        logger.info(
            "user_cache_invalidated",
            user_id=user_id,
            book_id=book_id,
        )
    
    async def health_check(self) -> bool:
        """Check if Redis is healthy."""
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception:
            return False


# Singleton instance
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get the cache service singleton."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
