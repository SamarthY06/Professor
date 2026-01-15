"""
OpenAI Service - Centralized LLM interaction service.

Handles all OpenAI API calls with user-specific API keys.
"""

import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.services.api_key_service import APIKeyService

logger = get_logger(__name__)


class OpenAIService:
    """
    Service for OpenAI API interactions.
    
    Features:
    - User-specific API key handling
    - Chat completions
    - Embeddings
    - Retry logic
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_key_service = APIKeyService(db)
        self._client_cache: Dict[str, AsyncOpenAI] = {}
    
    async def _get_client(self, user_id: Optional[UUID] = None) -> AsyncOpenAI:
        """
        Get OpenAI client for a user.
        
        Uses cached clients for performance.
        """
        cache_key = str(user_id) if user_id else "default"
        
        if cache_key not in self._client_cache:
            if user_id:
                api_key = await self.api_key_service.get_api_key_for_user(user_id)
            else:
                api_key = settings.openai_api_key
                if not api_key:
                    raise ValueError("No default OpenAI API key configured")
            
            self._client_cache[cache_key] = AsyncOpenAI(api_key=api_key)
        
        return self._client_cache[cache_key]
    
    def _clear_client_cache(self, user_id: Optional[UUID] = None):
        """Clear cached client for a user."""
        cache_key = str(user_id) if user_id else "default"
        self._client_cache.pop(cache_key, None)
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        user_id: Optional[UUID] = None,
        model: Optional[str] = None,
        max_tokens: int = 600,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> str:
        """
        Generate a chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            user_id: Optional user ID for user-specific API key
            model: Model to use (defaults to settings.openai_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            json_mode: Request JSON response format
            
        Returns:
            Generated response text
        """
        client = await self._get_client(user_id)
        
        kwargs: Dict[str, Any] = {
            "model": model or settings.openai_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        try:
            response = await client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            
            logger.debug(
                "chat_completion_success",
                user_id=str(user_id) if user_id else "default",
                model=kwargs["model"],
                tokens=response.usage.total_tokens if response.usage else None,
            )
            
            return content or ""
            
        except Exception as e:
            logger.exception(
                "chat_completion_failed",
                user_id=str(user_id) if user_id else "default",
                error=str(e),
            )
            raise
    
    async def generate_embedding(
        self,
        text: str,
        user_id: Optional[UUID] = None,
        model: Optional[str] = None,
    ) -> List[float]:
        """
        Generate an embedding for text.
        
        Args:
            text: Text to embed
            user_id: Optional user ID for user-specific API key
            model: Embedding model to use
            
        Returns:
            Embedding vector as list of floats
        """
        client = await self._get_client(user_id)
        
        try:
            response = await client.embeddings.create(
                model=model or settings.embedding_model,
                input=text,
            )
            
            return response.data[0].embedding
            
        except Exception as e:
            logger.exception(
                "embedding_generation_failed",
                user_id=str(user_id) if user_id else "default",
                error=str(e),
            )
            raise
    
    async def generate_embeddings_batch(
        self,
        texts: List[str],
        user_id: Optional[UUID] = None,
        model: Optional[str] = None,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            user_id: Optional user ID for user-specific API key
            model: Embedding model to use
            
        Returns:
            List of embedding vectors
        """
        client = await self._get_client(user_id)
        
        try:
            response = await client.embeddings.create(
                model=model or settings.embedding_model,
                input=texts,
            )
            
            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]
            
        except Exception as e:
            logger.exception(
                "batch_embedding_failed",
                user_id=str(user_id) if user_id else "default",
                count=len(texts),
                error=str(e),
            )
            raise


# Dependency injection helper
async def get_openai_service(db: AsyncSession) -> OpenAIService:
    """Get an OpenAIService instance."""
    return OpenAIService(db)
