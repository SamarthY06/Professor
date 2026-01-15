"""High-performance embedding generation with parallel batching."""

import asyncio
from typing import List, Optional

import numpy as np
from openai import AsyncOpenAI

from app.config import settings
from app.logs.logger import get_logger
from app.rag.chunking import Chunk

logger = get_logger(__name__)


class EmbeddingService:
    """
    High-performance embedding service.
    
    Optimizations:
    - Large batch sizes (up to 2000 texts per API call)
    - Parallel API calls for multiple batches
    - Aggressive caching
    - Connection pooling
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.batch_size = 500  # Larger batches = fewer API calls
        self.max_parallel_batches = 3  # Process 3 batches in parallel
        self._client: Optional[AsyncOpenAI] = None
        self._api_key = api_key
    
    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client with connection pooling."""
        if self._client is None:
            api_key = self._api_key or settings.openai_api_key
            if not api_key:
                raise ValueError("OpenAI API key not configured")
            self._client = AsyncOpenAI(
                api_key=api_key,
                max_retries=3,
                timeout=60.0,
            )
        return self._client
    
    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        client = self._get_client()
        response = await client.embeddings.create(
            model=self.model,
            input=text,
        )
        return response.data[0].embedding
    
    async def embed_chunks(
        self,
        chunks: List[Chunk],
        cache=None,
    ) -> List[Chunk]:
        """
        Generate embeddings with parallel batch processing.
        
        Processes multiple batches simultaneously for maximum speed.
        """
        if not chunks:
            return chunks
        
        client = self._get_client()
        
        # Check cache for existing embeddings
        uncached_chunks = []
        for chunk in chunks:
            if cache:
                try:
                    cached = await cache.get(f"emb:{chunk.content_hash}")
                    if cached:
                        chunk.embedding = cached
                        continue
                except Exception:
                    pass  # Cache miss, continue
            uncached_chunks.append(chunk)
        
        if not uncached_chunks:
            logger.info("embeddings_all_cached", count=len(chunks))
            return chunks
        
        logger.info(
            "embedding_chunks",
            total=len(chunks),
            uncached=len(uncached_chunks),
            batch_size=self.batch_size,
        )
        
        # Create batches
        batches = []
        for i in range(0, len(uncached_chunks), self.batch_size):
            batch = uncached_chunks[i:i + self.batch_size]
            batches.append(batch)
        
        logger.info("embedding_batches_created", num_batches=len(batches))
        
        # Process batches in parallel groups
        for group_start in range(0, len(batches), self.max_parallel_batches):
            group_end = min(group_start + self.max_parallel_batches, len(batches))
            batch_group = batches[group_start:group_end]
            
            # Process this group of batches in parallel
            tasks = [
                self._embed_batch(client, batch, cache)
                for batch in batch_group
            ]
            await asyncio.gather(*tasks)
            
            # Tiny delay between groups to be nice to the API
            if group_end < len(batches):
                await asyncio.sleep(0.05)
        
        logger.info("embeddings_complete", count=len(uncached_chunks))
        return chunks
    
    async def _embed_batch(
        self,
        client: AsyncOpenAI,
        batch: List[Chunk],
        cache=None,
    ) -> None:
        """Embed a single batch of chunks."""
        texts = [c.content for c in batch]
        
        try:
            response = await client.embeddings.create(
                model=self.model,
                input=texts,
            )
            
            # Assign embeddings to chunks
            for j, embedding_data in enumerate(response.data):
                chunk = batch[j]
                chunk.embedding = embedding_data.embedding
                
                # Cache asynchronously (don't wait)
                if cache:
                    asyncio.create_task(
                        self._cache_embedding(cache, chunk.content_hash, chunk.embedding)
                    )
                    
        except Exception as e:
            logger.error("embedding_batch_failed", error=str(e), batch_size=len(batch))
            raise
    
    async def _cache_embedding(self, cache, content_hash: str, embedding: List[float]) -> None:
        """Cache embedding without blocking."""
        try:
            await cache.setex(f"emb:{content_hash}", 86400 * 7, embedding)
        except Exception:
            pass  # Caching failure shouldn't stop processing
    
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.
        
        This is separated from embed_text to allow for
        potential query-specific optimizations in the future.
        
        Args:
            query: The search query
            
        Returns:
            Query embedding
        """
        return await self.embed_text(query)
    
    def cosine_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding
            embedding2: Second embedding
            
        Returns:
            Cosine similarity score (0-1)
        """
        a = np.array(embedding1)
        b = np.array(embedding2)
        
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
