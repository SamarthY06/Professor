"""User-related API routes including API key management."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.models.user import User, UserSettings
from app.services.api_key_service import APIKeyService

logger = get_logger(__name__)
router = APIRouter()


# ========================
# Request/Response Models
# ========================

class APIKeyRequest(BaseModel):
    """Request to save API key."""
    api_key: str
    validate_key: bool = True


class APIKeyStatusResponse(BaseModel):
    """API key status response."""
    has_key: bool
    is_valid: bool
    last_validated: Optional[str]
    masked_key: Optional[str]
    using_default: bool


class APIKeyResponse(BaseModel):
    """Generic API key operation response."""
    success: bool
    message: str


class UserSettingsUpdate(BaseModel):
    """User settings update request."""
    professor_style: Optional[str] = None
    notification_preferences: Optional[dict] = None
    whatsapp_number: Optional[str] = None  # WhatsApp phone with country code
    study_schedule: Optional[dict] = None
    timezone: Optional[str] = None


class UserSettingsResponse(BaseModel):
    """User settings response."""
    professor_style: str
    notification_preferences: dict
    whatsapp_number: Optional[str]
    study_schedule: Optional[dict]
    timezone: str


class UserProfileUpdate(BaseModel):
    """User profile update request."""
    name: Optional[str] = None
    phone: Optional[str] = None


class UserProfileResponse(BaseModel):
    """User profile response."""
    id: UUID
    email: str
    name: str
    phone: Optional[str]
    role: str
    is_active: bool
    created_at: datetime


# ========================
# API Key Endpoints
# ========================

@router.get("/api-key/status", response_model=APIKeyStatusResponse)
async def get_api_key_status(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of the user's OpenAI API key.
    
    Returns information about whether a key is stored and if it's valid.
    Does NOT return the actual key.
    """
    service = APIKeyService(db)
    status = await service.get_key_status(user_id)
    
    return APIKeyStatusResponse(**status)


@router.post("/api-key", response_model=APIKeyResponse)
async def save_api_key(
    request: APIKeyRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Save or update the user's OpenAI API key.
    
    The key is encrypted before storage and optionally validated against OpenAI.
    """
    service = APIKeyService(db)
    
    success, error = await service.save_api_key(
        user_id=user_id,
        api_key=request.api_key,
        validate=request.validate_key,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Failed to save API key",
        )
    
    return APIKeyResponse(
        success=True,
        message="API key saved successfully",
    )


@router.delete("/api-key", response_model=APIKeyResponse)
async def delete_api_key(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete the user's stored OpenAI API key.
    
    After deletion, the user will use the default backend key (if available).
    """
    service = APIKeyService(db)
    
    deleted = await service.delete_api_key(user_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No API key found to delete",
        )
    
    return APIKeyResponse(
        success=True,
        message="API key deleted successfully",
    )


@router.post("/api-key/validate", response_model=APIKeyResponse)
async def validate_api_key(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-validate the user's stored API key against OpenAI.
    
    Updates the is_valid status in the database.
    """
    service = APIKeyService(db)
    
    is_valid = await service.validate_stored_key(user_id)
    
    return APIKeyResponse(
        success=is_valid,
        message="API key is valid" if is_valid else "API key validation failed",
    )


# ========================
# User Profile Endpoints
# ========================

@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's profile."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.patch("/profile", response_model=UserProfileResponse)
async def update_profile(
    update_data: UserProfileUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile."""
    # Build update values
    update_values = {}
    if update_data.name is not None:
        update_values["name"] = update_data.name
    if update_data.phone is not None:
        update_values["phone"] = update_data.phone
    
    if not update_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    
    update_values["updated_at"] = datetime.utcnow()
    
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(**update_values)
    )
    await db.commit()
    
    # Fetch updated user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    
    logger.info("user_profile_updated", user_id=str(user_id), fields=list(update_values.keys()))
    
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


# ========================
# User Settings Endpoints
# ========================

@router.get("/settings", response_model=UserSettingsResponse)
async def get_settings(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's settings."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings_obj = result.scalar_one_or_none()
    
    if not settings_obj:
        # Create default settings
        settings_obj = UserSettings(user_id=user_id)
        db.add(settings_obj)
        await db.commit()
        await db.refresh(settings_obj)
    
    return UserSettingsResponse(
        professor_style=settings_obj.professor_style,
        notification_preferences=settings_obj.notification_preferences or {},
        whatsapp_number=settings_obj.whatsapp_number,
        study_schedule=settings_obj.study_schedule,
        timezone=settings_obj.timezone,
    )


@router.patch("/settings", response_model=UserSettingsResponse)
async def update_settings(
    update_data: UserSettingsUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's settings."""
    # Validate professor_style if provided
    if update_data.professor_style:
        valid_styles = ["strict", "balanced", "encouraging"]
        if update_data.professor_style not in valid_styles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid professor_style. Must be one of: {valid_styles}",
            )
    
    # Build update values
    update_values = {}
    if update_data.professor_style is not None:
        update_values["professor_style"] = update_data.professor_style
    if update_data.notification_preferences is not None:
        update_values["notification_preferences"] = update_data.notification_preferences
    if update_data.whatsapp_number is not None:
        # Validate phone number format
        phone = update_data.whatsapp_number.strip()
        if phone and not phone.startswith("+"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WhatsApp number must include country code (e.g., +917038021340)"
            )
        update_values["whatsapp_number"] = phone
    if update_data.study_schedule is not None:
        update_values["study_schedule"] = update_data.study_schedule
    if update_data.timezone is not None:
        update_values["timezone"] = update_data.timezone
    
    if not update_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    
    # Check if settings exist
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        await db.execute(
            update(UserSettings)
            .where(UserSettings.user_id == user_id)
            .values(**update_values)
        )
    else:
        new_settings = UserSettings(user_id=user_id, **update_values)
        db.add(new_settings)
    
    await db.commit()
    
    # Fetch updated settings
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings_obj = result.scalar_one()
    
    logger.info("user_settings_updated", user_id=str(user_id), fields=list(update_values.keys()))
    
    return UserSettingsResponse(
        professor_style=settings_obj.professor_style,
        notification_preferences=settings_obj.notification_preferences or {},
        whatsapp_number=settings_obj.whatsapp_number,
        study_schedule=settings_obj.study_schedule,
        timezone=settings_obj.timezone,
    )
