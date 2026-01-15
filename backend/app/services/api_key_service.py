"""
API Key Service - Manages user OpenAI API keys.

Handles encryption/decryption, masking, validation, and fallback to default key.
"""

from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.models.user import EncryptedAPIKey, User
from app.security.encryption import (
    encrypt_api_key,
    decrypt_api_key,
    hash_api_key,
    validate_openai_key,
)

logger = get_logger(__name__)


class APIKeyService:
    """
    Service for managing user OpenAI API keys.
    
    Features:
    - Encrypt and store user API keys
    - Decrypt keys for use (never exposed)
    - Mask keys for display (sk-...xxxx)
    - Fallback to default backend key
    - Validate keys against OpenAI API
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_api_key_for_user(self, user_id: UUID) -> str:
        """
        Get the OpenAI API key to use for a user.
        
        Priority:
        1. User's own key (if valid)
        2. Default backend key
        
        Args:
            user_id: The user's ID
            
        Returns:
            The API key to use
            
        Raises:
            ValueError: If no API key is available
        """
        # Try to get user's own key
        user_key = await self._get_user_key(user_id)
        if user_key:
            logger.debug(
                "using_user_api_key",
                user_id=str(user_id),
                key_suffix=user_key[-4:],
            )
            return user_key
        
        # Fallback to default backend key
        if settings.openai_api_key:
            logger.debug(
                "using_default_api_key",
                user_id=str(user_id),
            )
            return settings.openai_api_key
        
        logger.error(
            "no_api_key_available",
            user_id=str(user_id),
        )
        raise ValueError(
            "No OpenAI API key available. Please add your API key in settings "
            "or contact support."
        )
    
    async def _get_user_key(self, user_id: UUID) -> Optional[str]:
        """
        Get and decrypt user's stored API key.
        
        Returns None if no key stored or key is invalid.
        """
        result = await self.db.execute(
            select(EncryptedAPIKey)
            .where(EncryptedAPIKey.user_id == user_id)
        )
        key_record = result.scalar_one_or_none()
        
        if not key_record:
            return None
        
        if not key_record.is_valid:
            logger.warning(
                "user_api_key_invalid",
                user_id=str(user_id),
            )
            return None
        
        try:
            decrypted = decrypt_api_key(
                key_record.encrypted_key,
                key_record.key_iv,
            )
            return decrypted
        except Exception as e:
            logger.exception(
                "api_key_decryption_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return None
    
    async def save_api_key(
        self,
        user_id: UUID,
        api_key: str,
        validate: bool = True,
    ) -> Tuple[bool, Optional[str]]:
        """
        Save or update a user's OpenAI API key.
        
        Args:
            user_id: The user's ID
            api_key: The API key to save
            validate: Whether to validate the key first
            
        Returns:
            Tuple of (success, error_message)
        """
        # Validate key format
        if not api_key.startswith("sk-"):
            return False, "Invalid API key format. Key should start with 'sk-'"
        
        if len(api_key) < 20:
            return False, "API key is too short"
        
        # Optionally validate against OpenAI
        if validate:
            is_valid = await validate_openai_key(api_key)
            if not is_valid:
                return False, "API key validation failed. Please check your key."
        
        try:
            # Encrypt the key
            encrypted_key, iv = encrypt_api_key(api_key)
            key_hash = hash_api_key(api_key)
            
            # Check if user already has a key
            existing = await self.db.execute(
                select(EncryptedAPIKey)
                .where(EncryptedAPIKey.user_id == user_id)
            )
            existing_record = existing.scalar_one_or_none()
            
            if existing_record:
                # Update existing key
                await self.db.execute(
                    update(EncryptedAPIKey)
                    .where(EncryptedAPIKey.user_id == user_id)
                    .values(
                        encrypted_key=encrypted_key,
                        key_iv=iv,
                        key_hash=key_hash,
                        is_valid=True,
                        last_validated_at=datetime.utcnow(),
                    )
                )
            else:
                # Create new record
                new_key = EncryptedAPIKey(
                    user_id=user_id,
                    encrypted_key=encrypted_key,
                    key_iv=iv,
                    key_hash=key_hash,
                    is_valid=True,
                    last_validated_at=datetime.utcnow(),
                )
                self.db.add(new_key)
            
            await self.db.commit()
            
            logger.info(
                "api_key_saved",
                user_id=str(user_id),
                key_suffix=api_key[-4:],
            )
            
            return True, None
            
        except Exception as e:
            await self.db.rollback()
            logger.exception(
                "api_key_save_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return False, "Failed to save API key. Please try again."
    
    async def delete_api_key(self, user_id: UUID) -> bool:
        """
        Delete a user's stored API key.
        
        Args:
            user_id: The user's ID
            
        Returns:
            True if deleted, False if not found
        """
        try:
            result = await self.db.execute(
                delete(EncryptedAPIKey)
                .where(EncryptedAPIKey.user_id == user_id)
            )
            await self.db.commit()
            
            deleted = result.rowcount > 0  # type: ignore
            
            if deleted:
                logger.info("api_key_deleted", user_id=str(user_id))
            
            return deleted
            
        except Exception as e:
            await self.db.rollback()
            logger.exception(
                "api_key_delete_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return False
    
    async def get_key_status(self, user_id: UUID) -> dict:
        """
        Get the status of a user's API key.
        
        Returns info about whether a key exists, if it's valid, etc.
        Does NOT return the actual key.
        """
        result = await self.db.execute(
            select(EncryptedAPIKey)
            .where(EncryptedAPIKey.user_id == user_id)
        )
        key_record = result.scalar_one_or_none()
        
        if not key_record:
            return {
                "has_key": False,
                "is_valid": False,
                "last_validated": None,
                "masked_key": None,
                "using_default": bool(settings.openai_api_key),
            }
        
        # Get masked key for display
        try:
            decrypted = decrypt_api_key(
                key_record.encrypted_key,
                key_record.key_iv,
            )
            masked = self.mask_key(decrypted)
        except Exception:
            masked = "sk-****"
        
        return {
            "has_key": True,
            "is_valid": key_record.is_valid,
            "last_validated": key_record.last_validated_at.isoformat() if key_record.last_validated_at else None,
            "masked_key": masked,
            "using_default": False,
        }
    
    async def validate_stored_key(self, user_id: UUID) -> bool:
        """
        Re-validate a user's stored API key against OpenAI.
        
        Updates the is_valid status in the database.
        """
        key = await self._get_user_key(user_id)
        if not key:
            return False
        
        is_valid = await validate_openai_key(key)
        
        # Update status in database
        await self.db.execute(
            update(EncryptedAPIKey)
            .where(EncryptedAPIKey.user_id == user_id)
            .values(
                is_valid=is_valid,
                last_validated_at=datetime.utcnow(),
            )
        )
        await self.db.commit()
        
        logger.info(
            "api_key_revalidated",
            user_id=str(user_id),
            is_valid=is_valid,
        )
        
        return is_valid
    
    @staticmethod
    def mask_key(api_key: str) -> str:
        """
        Mask an API key for safe display.
        
        Example: sk-abc123...xyz789 -> sk-abc1****xyz7
        """
        if len(api_key) < 12:
            return "sk-****"
        
        prefix = api_key[:7]  # "sk-abc"
        suffix = api_key[-4:]  # Last 4 chars
        
        return f"{prefix}****{suffix}"


# Dependency injection helper
async def get_api_key_service(db: AsyncSession) -> APIKeyService:
    """Get an APIKeyService instance."""
    return APIKeyService(db)
