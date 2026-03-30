"""Rate Limiter Service using Redis.

Provides rate limiting for API endpoints to prevent abuse.
Uses a sliding window algorithm for accurate rate limiting.
"""

from typing import Optional, Tuple
from datetime import datetime
import time

from app.logs.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """
    Redis-based rate limiter using sliding window algorithm.
    
    Usage:
        limiter = RateLimiter(redis_client)
        allowed, remaining, reset_at = await limiter.check("user:123:chat", limit=10, window=60)
        if not allowed:
            raise HTTPException(429, "Rate limit exceeded")
    """
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def check(
        self,
        key: str,
        limit: int = 10,
        window: int = 60,
    ) -> Tuple[bool, int, int]:
        """
        Check if a request is allowed under the rate limit.
        
        Args:
            key: Unique identifier for the rate limit (e.g., "user:123:chat")
            limit: Maximum number of requests allowed in the window
            window: Time window in seconds
            
        Returns:
            Tuple of (allowed, remaining, reset_at)
            - allowed: Whether the request is allowed
            - remaining: Number of requests remaining in the window
            - reset_at: Unix timestamp when the window resets
        """
        if not self.redis:
            # No Redis, allow all requests
            return True, limit, int(time.time()) + window
        
        now = time.time()
        window_start = now - window
        redis_key = f"ratelimit:{key}"
        
        try:
            pipe = self.redis.pipeline()
            
            # Remove old entries outside the window
            pipe.zremrangebyscore(redis_key, 0, window_start)
            
            # Count current entries in the window
            pipe.zcard(redis_key)
            
            # Add current request
            pipe.zadd(redis_key, {str(now): now})
            
            # Set expiry on the key
            pipe.expire(redis_key, window + 1)
            
            results = await pipe.execute()
            current_count = results[1]
            
            allowed = current_count < limit
            remaining = max(0, limit - current_count - 1) if allowed else 0
            reset_at = int(now + window)
            
            if not allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    key=key,
                    limit=limit,
                    window=window,
                    count=current_count,
                )
            
            return allowed, remaining, reset_at
            
        except Exception as e:
            logger.error("rate_limit_check_failed", error=str(e), key=key)
            # On error, allow the request (fail open)
            return True, limit, int(time.time()) + window
    
    async def get_remaining(self, key: str, limit: int = 10, window: int = 60) -> int:
        """Get the number of remaining requests in the current window."""
        if not self.redis:
            return limit
        
        now = time.time()
        window_start = now - window
        redis_key = f"ratelimit:{key}"
        
        try:
            # Remove old entries and count
            await self.redis.zremrangebyscore(redis_key, 0, window_start)
            current_count = await self.redis.zcard(redis_key)
            return max(0, limit - current_count)
        except Exception:
            return limit


# Rate limit configurations
RATE_LIMITS = {
    "chat": {
        "limit": 30,      # 30 messages
        "window": 60,     # per minute
    },
    "chat_burst": {
        "limit": 5,       # 5 messages
        "window": 10,     # per 10 seconds (burst protection)
    },
    "planning": {
        "limit": 10,      # 10 plan generations
        "window": 3600,   # per hour
    },
    "quiz": {
        "limit": 20,      # 20 quiz interactions
        "window": 300,    # per 5 minutes
    },
}


async def check_rate_limit(
    redis_client,
    user_id: str,
    endpoint: str,
) -> Tuple[bool, int, int]:
    """
    Check rate limit for a user and endpoint.
    
    Args:
        redis_client: Redis client instance
        user_id: User's ID
        endpoint: Endpoint name (chat, planning, quiz)
        
    Returns:
        Tuple of (allowed, remaining, reset_at)
    """
    config = RATE_LIMITS.get(endpoint, RATE_LIMITS["chat"])
    limiter = RateLimiter(redis_client)
    
    key = f"{user_id}:{endpoint}"
    return await limiter.check(key, config["limit"], config["window"])


async def check_chat_rate_limit(
    redis_client,
    user_id: str,
) -> Tuple[bool, str]:
    """
    Check both regular and burst rate limits for chat.
    
    Args:
        redis_client: Redis client instance
        user_id: User's ID
        
    Returns:
        Tuple of (allowed, error_message)
    """
    limiter = RateLimiter(redis_client)
    
    # Check burst limit first (stricter)
    burst_config = RATE_LIMITS["chat_burst"]
    burst_allowed, _, burst_reset = await limiter.check(
        f"{user_id}:chat_burst",
        burst_config["limit"],
        burst_config["window"],
    )
    
    if not burst_allowed:
        return False, f"Too many messages. Please wait a few seconds before sending another message."
    
    # Check regular limit
    chat_config = RATE_LIMITS["chat"]
    chat_allowed, remaining, reset_at = await limiter.check(
        f"{user_id}:chat",
        chat_config["limit"],
        chat_config["window"],
    )
    
    if not chat_allowed:
        return False, f"Rate limit exceeded. You can send {chat_config['limit']} messages per minute. Please wait."
    
    return True, ""
