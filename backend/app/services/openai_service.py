"""
OpenAI Service - Centralized LLM interaction service.

Handles all OpenAI API calls with user-specific API keys.
Includes usage tracking for cost monitoring.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.services.api_key_service import APIKeyService
from app.models.usage import UsageLog

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
        usage_type: str = "chat",
        book_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        track_usage: bool = True,
    ) -> str:
        """
        Generate a chat completion with usage tracking.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            user_id: Optional user ID for user-specific API key
            model: Model to use (defaults to settings.openai_model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            json_mode: Request JSON response format
            usage_type: Type of usage (chat, quiz, embedding, etc.)
            book_id: Optional book ID for tracking
            session_id: Optional session ID for tracking
            track_usage: Whether to log usage to database
            
        Returns:
            Generated response text
        """
        client = await self._get_client(user_id)
        used_model = model or settings.openai_model
        
        kwargs: Dict[str, Any] = {
            "model": used_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        
        try:
            response = await client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            
            # Track usage
            if track_usage and response.usage:
                await self._log_usage(
                    user_id=user_id,
                    usage_type=usage_type,
                    model_used=used_model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    cached_tokens=getattr(response.usage, 'prompt_tokens_details', {}).get('cached_tokens', 0) if hasattr(response.usage, 'prompt_tokens_details') else 0,
                    book_id=book_id,
                    session_id=session_id,
                )
            
            logger.debug(
                "chat_completion_success",
                user_id=str(user_id) if user_id else "default",
                model=used_model,
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
    
    async def _log_usage(
        self,
        user_id: Optional[UUID],
        usage_type: str,
        model_used: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        book_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        latency_ms: Optional[int] = None,
    ) -> None:
        """Log API usage to database for cost tracking."""
        if not user_id:
            return  # Don't track anonymous usage
        
        try:
            # Determine who pays based on whether user has their own key
            from app.models.user import EncryptedAPIKey
            from sqlalchemy import select
            
            key_result = await self.db.execute(
                select(EncryptedAPIKey).where(
                    EncryptedAPIKey.user_id == user_id,
                    EncryptedAPIKey.is_valid == True
                )
            )
            has_own_key = key_result.scalar_one_or_none() is not None
            paid_by = "user" if has_own_key else "platform"
            
            # Calculate cost (simplified - use pricing service for accuracy)
            cost_cents = await self._calculate_cost(model_used, input_tokens, output_tokens, cached_tokens)
            
            # Create usage log
            usage_log = UsageLog(
                user_id=user_id,
                usage_type=usage_type,
                model_used=model_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=cached_tokens,
                cost_cents=cost_cents,
                paid_by=paid_by,
                book_id=book_id,
                session_id=session_id,
                latency_ms=latency_ms,
            )
            self.db.add(usage_log)
            await self.db.commit()
            
            logger.info(
                "usage_logged",
                user_id=str(user_id),
                usage_type=usage_type,
                model=model_used,
                tokens=input_tokens + output_tokens,
                cost_cents=cost_cents,
                paid_by=paid_by,
            )
        except Exception as e:
            logger.warning("usage_logging_failed", error=str(e))
            # Don't fail the main request if usage logging fails
    
    async def _calculate_cost(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> int:
        """Calculate cost in cents based on model pricing."""
        from app.models.usage import ModelPricing
        from sqlalchemy import select
        
        try:
            result = await self.db.execute(
                select(ModelPricing).where(ModelPricing.model_name == model_name)
            )
            pricing = result.scalar_one_or_none()
            
            if not pricing:
                # Fallback pricing (GPT-4o-mini rates)
                input_price = 15  # $0.15/1M
                output_price = 60  # $0.60/1M
                cached_price = 8
            else:
                input_price = pricing.input_price_per_million
                output_price = pricing.output_price_per_million
                cached_price = pricing.cached_input_price_per_million or input_price // 2
            
            regular_input_tokens = input_tokens - cached_tokens
            input_cost = (regular_input_tokens / 1_000_000) * input_price
            output_cost = (output_tokens / 1_000_000) * output_price
            cached_cost = (cached_tokens / 1_000_000) * cached_price if cached_tokens > 0 else 0
            
            return int(round(input_cost + output_cost + cached_cost))
        except Exception:
            return 0
    
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
