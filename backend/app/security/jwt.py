"""JWT token management."""

from datetime import datetime, timedelta
from typing import Any, Optional

from jose import JWTError, jwt

from app.config import settings


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode = {
        "sub": subject,
        "exp": expire,
        "type": "access",
        "iat": datetime.utcnow(),
    }
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    
    return encoded_jwt


def create_refresh_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT refresh token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    
    to_encode = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
        "iat": datetime.utcnow(),
    }
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    
    return encoded_jwt


def verify_access_token(token: str) -> Optional[dict[str, Any]]:
    """Verify and decode an access token."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        
        if payload.get("type") != "access":
            return None
        
        return payload
    except JWTError:
        return None


def verify_refresh_token(token: str) -> Optional[dict[str, Any]]:
    """Verify and decode a refresh token."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        
        if payload.get("type") != "refresh":
            return None
        
        return payload
    except JWTError:
        return None
