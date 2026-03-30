"""Authentication API endpoints."""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt

from app.config.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Security
security = HTTPBearer()

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Hardcoded users (in production, use a database)
USERS = {
    "admin": {
        "id": "1",
        "username": "admin",
        "password": "admin123",  # In production, use hashed passwords
        "role": "admin",
    },
    "viewer": {
        "id": "2",
        "username": "viewer",
        "password": "viewer123",
        "role": "viewer",
    },
}


class LoginRequest(BaseModel):
    """Login request schema."""
    username: str
    password: str


class UserResponse(BaseModel):
    """User response schema."""
    id: str
    username: str
    role: str


class LoginResponse(BaseModel):
    """Login response schema."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify JWT token and return payload."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserResponse:
    """Get current user from JWT token."""
    payload = verify_token(credentials.credentials)
    username = payload.get("sub")
    
    if not username or username not in USERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    
    user_data = USERS[username]
    return UserResponse(
        id=user_data["id"],
        username=user_data["username"],
        role=user_data["role"],
    )


async def require_admin(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Require admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """
    Authenticate user and return JWT token.
    
    Default credentials:
    - Admin: username=admin, password=admin123
    - Viewer: username=viewer, password=viewer123
    """
    user = USERS.get(request.username)
    
    if not user or user["password"] != request.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]}
    )
    
    logger.info("User logged in", username=user["username"], role=user["role"])
    
    return LoginResponse(
        access_token=access_token,
        user=UserResponse(
            id=user["id"],
            username=user["username"],
            role=user["role"],
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Get current authenticated user."""
    return current_user
