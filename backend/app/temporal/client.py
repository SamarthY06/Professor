"""Temporal client configuration with retry logic."""

import asyncio
from typing import Optional

from temporalio.client import Client

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)

_client: Optional[Client] = None


async def get_temporal_client(max_retries: int = 10, retry_delay: float = 2.0) -> Client:
    """
    Get or create Temporal client with retry logic.
    
    Handles startup race conditions when Temporal server isn't ready yet.
    """
    global _client
    
    if _client is not None:
        return _client
    
    last_error = None
    for attempt in range(max_retries):
        try:
            _client = await Client.connect(settings.temporal_host)
            logger.info(
                "temporal_client_connected", 
                host=settings.temporal_host,
                attempt=attempt + 1
            )
            return _client
        except Exception as e:
            last_error = e
            logger.warning(
                "temporal_connection_retry",
                host=settings.temporal_host,
                attempt=attempt + 1,
                max_retries=max_retries,
                error=str(e)
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
    
    logger.error("temporal_connection_failed", error=str(last_error))
    raise last_error


async def close_temporal_client() -> None:
    """Close Temporal client."""
    global _client
    
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("temporal_client_closed")
