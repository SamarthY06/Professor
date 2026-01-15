"""
Professor services.

Core Services:
- APIKeyService: User API key management
- OpenAIService: OpenAI API wrapper
- CacheService: Redis caching

New Services (Agent-Driven Architecture):
- progress: Progress tracking utility functions (replaces ProgressAgent)
- summarization: Background chapter summarization
- motivation: LLM-based motivation message generation (not an agent)
"""

from app.services.api_key_service import APIKeyService, get_api_key_service
from app.services.openai_service import OpenAIService, get_openai_service
from app.services.cache_service import CacheService, get_cache_service

# New services for agent-driven architecture
from app.services import progress
from app.services import summarization
from app.services import motivation

__all__ = [
    # Core services
    "APIKeyService",
    "get_api_key_service",
    "OpenAIService",
    "get_openai_service",
    "CacheService",
    "get_cache_service",
    # New modules
    "progress",
    "summarization",
    "motivation",
]
