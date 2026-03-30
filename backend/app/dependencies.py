"""FastAPI dependencies for dependency injection."""

from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.logs.logger import get_logger

logger = get_logger(__name__)

# HTTP Bearer token security
security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Redis connection pool
_redis_pool: Optional[redis.ConnectionPool] = None


async def get_redis_pool() -> redis.ConnectionPool:
    """Get or create Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=50,
            decode_responses=True,
        )
    return _redis_pool


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """Get Redis connection from pool."""
    pool = await get_redis_pool()
    client = redis.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.close()


async def get_current_user_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """
    Extract and validate the current user from JWT token.

    Resolution order:
      1. httpOnly cookie ``professor_access_token`` (preferred, XSS-safe)
      2. ``Authorization: Bearer <token>`` header (backward compat)

    Raises 401 if no valid token is found.
    """
    from app.security.jwt import verify_access_token

    token_value: Optional[str] = request.cookies.get("professor_access_token")

    if not token_value and credentials:
        token_value = credentials.credentials

    if not token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_access_token(token_value)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return UUID(user_id)


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[UUID]:
    """
    Extract user from JWT token if present (cookie → header fallback).
    Returns None if no token is provided (for public endpoints).
    """
    from app.security.jwt import verify_access_token

    token_value: Optional[str] = request.cookies.get("professor_access_token")
    if not token_value and credentials:
        token_value = credentials.credentials
    if not token_value:
        return None

    payload = verify_access_token(token_value)
    if payload is None:
        return None

    user_id = payload.get("sub")
    return UUID(user_id) if user_id else None


async def require_admin(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    """Require the current user to be an admin."""
    from sqlalchemy import select
    from app.models.user import User
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    
    if user is None or user.role not in ("admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    
    return user_id


class RateLimiter:
    """Simple rate limiter using Redis."""
    
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
    
    async def __call__(
        self,
        request: Request,
        redis_client: redis.Redis = Depends(get_redis),
    ) -> None:
        """Check rate limit for the request."""
        # Get client identifier (user ID or IP)
        client_id = request.client.host if request.client else "unknown"
        
        key = f"rate_limit:{client_id}"
        
        # Increment counter
        current = await redis_client.incr(key)
        
        # Set expiry on first request
        if current == 1:
            await redis_client.expire(key, 60)
        
        # Check limit
        if current > self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )


# Default rate limiter
rate_limiter = RateLimiter(requests_per_minute=60)
