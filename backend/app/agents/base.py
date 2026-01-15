"""Base agent class with production-ready LLM integration."""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)


class BaseAgent(ABC):
    """
    Base class for all Professor agents.
    
    Provides:
    - Async OpenAI client management
    - Structured output generation
    - JSON response parsing
    - Error handling with fallbacks
    - User-specific API key support
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize the agent.
        
        Args:
            api_key: OpenAI API key (uses settings if not provided)
            model: Model to use (uses settings.openai_model if not provided)
        """
        self.model = model or settings.openai_model
        self._client: Optional[AsyncOpenAI] = None
        self._api_key = api_key
        self.agent_name = self.__class__.__name__
    
    def _get_client(self, api_key: Optional[str] = None) -> AsyncOpenAI:
        """
        Get or create OpenAI client.
        
        Args:
            api_key: Optional API key to use (overrides instance key)
        """
        # Use provided key, then instance key, then settings key
        key_to_use = api_key or self._api_key or settings.openai_api_key
        
        if not key_to_use:
            raise ValueError("OpenAI API key not configured")
        
        # Create a new client if key differs or no client exists
        if self._client is None or (api_key and api_key != self._api_key):
            return AsyncOpenAI(api_key=key_to_use)
        
        return self._client
    
    def _get_api_key_from_state(self, state: Dict[str, Any]) -> Optional[str]:
        """Extract API key from state if present."""
        return state.get("api_key")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 600,
        temperature: float = 0.7,
        json_mode: bool = False,
        api_key: Optional[str] = None,
    ) -> str:
        """
        Generate a response using the LLM.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-2)
            json_mode: If True, request JSON response format
            api_key: Optional user-specific API key
            
        Returns:
            The generated response text
        """
        client = self._get_client(api_key)
        
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        kwargs: Dict[str, Any] = {
            "model": self.model,
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
                "llm_generation_complete",
                agent=self.agent_name,
                model=self.model,
                tokens_used=response.usage.total_tokens if response.usage else None,
            )
            
            return content or ""
            
        except Exception as e:
            logger.exception(
                "llm_generation_failed",
                agent=self.agent_name,
                error=str(e),
            )
            raise
    
    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 600,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a JSON response from the LLM.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt (should request JSON output)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            api_key: Optional user-specific API key
            
        Returns:
            Parsed JSON as a dictionary
        """
        response = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
            api_key=api_key,
        )
        
        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.warning(
                "json_parse_failed",
                agent=self.agent_name,
                response_preview=response[:200],
                error=str(e),
            )
            # Try to extract JSON from the response
            return self._extract_json(response)
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Attempt to extract JSON from text that may contain other content.
        
        Args:
            text: Text potentially containing JSON
            
        Returns:
            Extracted JSON or empty dict
        """
        # Try to find JSON object in the text
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            try:
                return json.loads(text[start_idx:end_idx + 1])
            except json.JSONDecodeError:
                pass
        
        return {}
    
    async def generate_with_retry(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 600,
        temperature: float = 0.7,
        max_retries: int = 3,
        fallback_response: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        """
        Generate with automatic retry on failure.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            max_retries: Number of retry attempts
            fallback_response: Response to return if all retries fail
            api_key: Optional user-specific API key
            
        Returns:
            Generated response or fallback
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    api_key=api_key,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "generation_retry",
                    agent=self.agent_name,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e),
                )
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
        
        if fallback_response is not None:
            logger.warning(
                "using_fallback_response",
                agent=self.agent_name,
                error=str(last_error),
            )
            return fallback_response
        
        raise last_error  # type: ignore
    
    @abstractmethod
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the state and return updated state.
        
        Args:
            state: Current UserState dictionary
            
        Returns:
            Updated state dictionary (partial update)
        """
        pass
