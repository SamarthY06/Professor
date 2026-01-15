"""Authentication API routes."""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
import bcrypt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.models.user import User, UserAuth, UserSession, UserSettings
from app.security.jwt import create_access_token, create_refresh_token, verify_refresh_token

logger = get_logger(__name__)
router = APIRouter()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


class GoogleAuthRequest(BaseModel):
    """Google OAuth callback request."""
    code: str
    redirect_uri: str


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str


class UserResponse(BaseModel):
    """User response model."""
    id: UUID
    email: str
    name: str
    role: str
    has_api_key: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/google", response_model=TokenResponse)
async def google_auth(
    request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with Google OAuth.
    Exchange authorization code for tokens and create/update user.
    """
    import httpx
    
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": request.code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": request.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        
        if token_response.status_code != 200:
            logger.warning("google_token_exchange_failed", status=token_response.status_code)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange authorization code",
            )
        
        tokens = token_response.json()
        google_access_token = tokens.get("access_token")
        
        # Get user info from Google
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        
        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from Google",
            )
        
        userinfo = userinfo_response.json()
    
    google_user_id = userinfo.get("id")
    email = userinfo.get("email")
    name = userinfo.get("name", email.split("@")[0])
    
    # Check if user exists by Google ID
    result = await db.execute(
        select(UserAuth).where(
            UserAuth.provider == "google",
            UserAuth.provider_user_id == google_user_id,
        )
    )
    user_auth = result.scalar_one_or_none()
    
    if user_auth:
        # Existing user
        user_id = user_auth.user_id
        logger.info("user_logged_in", user_id=str(user_id), provider="google")
    else:
        # Check if user exists by email
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if user:
            # Link Google account to existing user
            user_auth = UserAuth(
                user_id=user.id,
                provider="google",
                provider_user_id=google_user_id,
            )
            db.add(user_auth)
            user_id = user.id
            logger.info("google_account_linked", user_id=str(user_id))
        else:
            # Create new user
            user = User(email=email, name=name)
            db.add(user)
            await db.flush()
            
            # Create user auth
            user_auth = UserAuth(
                user_id=user.id,
                provider="google",
                provider_user_id=google_user_id,
            )
            db.add(user_auth)
            
            # Create default settings
            user_settings = UserSettings(user_id=user.id)
            db.add(user_settings)
            
            user_id = user.id
            logger.info("user_created", user_id=str(user_id), provider="google")
    
    await db.commit()
    
    # Create JWT tokens
    access_token = create_access_token(str(user_id))
    refresh_token = create_refresh_token(str(user_id))
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token."""
    payload = verify_refresh_token(request.refresh_token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    
    user_id = payload.get("sub")
    
    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    # Create new tokens
    access_token = create_access_token(user_id)
    new_refresh_token = create_refresh_token(user_id)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Check if user has API key
    from app.models.user import EncryptedAPIKey
    result = await db.execute(
        select(EncryptedAPIKey).where(EncryptedAPIKey.user_id == user_id)
    )
    api_key = result.scalar_one_or_none()
    
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        has_api_key=api_key is not None and api_key.is_valid,
        created_at=user.created_at,
    )


@router.post("/logout")
async def logout(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Logout current user (invalidate sessions)."""
    # Delete all user sessions
    await db.execute(
        UserSession.__table__.delete().where(UserSession.user_id == user_id)
    )
    await db.commit()
    
    logger.info("user_logged_out", user_id=str(user_id))
    
    return {"message": "Logged out successfully"}


class SignupRequest(BaseModel):
    """User signup request."""
    email: EmailStr
    password: str
    name: str
    phone: Optional[str] = None
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class SigninRequest(BaseModel):
    """User signin request."""
    email: EmailStr
    password: str


@router.post("/signup", response_model=TokenResponse)
async def signup(
    request: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with email and password.
    """
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == request.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please sign in.",
        )
    
    # Hash password
    password_hash = hash_password(request.password)
    
    # Create new user with all details
    user = User(
        email=request.email,
        password_hash=password_hash,
        name=request.name,
        phone=request.phone,
    )
    db.add(user)
    await db.flush()
    
    # Create default settings
    user_settings = UserSettings(
        user_id=user.id,
        professor_style="balanced",
    )
    db.add(user_settings)
    
    await db.commit()
    
    logger.info("user_registered", user_id=str(user.id), email=request.email)
    
    # Create JWT tokens
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/signin", response_model=TokenResponse)
async def signin(
    request: SigninRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Sign in an existing user with email and password.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    
    # Verify password
    if not user.password_hash or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )
    
    logger.info("user_signed_in", user_id=str(user.id), email=request.email)
    
    # Create JWT tokens
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


class DevLoginRequest(BaseModel):
    """Dev login request for testing without Google OAuth."""
    email: str
    name: str = "Test User"


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(
    request: DevLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Development login endpoint - creates or gets user without OAuth.
    Only enabled in development mode.
    """
    if settings.environment != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev login is only available in development mode",
        )
    
    # Check if user exists by email
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    
    if user:
        user_id = user.id
        logger.info("dev_login_existing_user", user_id=str(user_id))
    else:
        # Create new user
        user = User(email=request.email, name=request.name)
        db.add(user)
        await db.flush()
        
        # Create default settings
        user_settings = UserSettings(user_id=user.id)
        db.add(user_settings)
        
        user_id = user.id
        logger.info("dev_login_new_user", user_id=str(user_id))
    
    await db.commit()
    
    # Create JWT tokens
    access_token = create_access_token(str(user_id))
    refresh_token = create_refresh_token(str(user_id))
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )
