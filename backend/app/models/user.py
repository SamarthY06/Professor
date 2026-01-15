"""User-related database models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, LargeBinary
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    """Core user table."""
    
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # bcrypt hashed password
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="student")  # student, admin, superadmin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    auth_providers: Mapped[list["UserAuth"]] = relationship(
        "UserAuth", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    settings: Mapped[Optional["UserSettings"]] = relationship(
        "UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    api_key: Mapped[Optional["EncryptedAPIKey"]] = relationship(
        "EncryptedAPIKey", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserAuth(Base):
    """OAuth provider authentication records."""
    
    __tablename__ = "user_auth"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # google, github
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    refresh_token_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="auth_providers")
    
    __table_args__ = (
        # Unique constraint on provider + provider_user_id
        {"sqlite_autoincrement": True},
    )


class EncryptedAPIKey(Base):
    """Encrypted OpenAI API keys for users."""
    
    __tablename__ = "encrypted_api_keys"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # Fernet encrypted
    key_iv: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # For validation without decryption
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_key")


class UserSession(Base):
    """Active user sessions."""
    
    __tablename__ = "user_sessions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    device_info: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 compatible
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")


class UserSettings(Base):
    """User preferences and settings."""
    
    __tablename__ = "user_settings"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    professor_style: Mapped[str] = mapped_column(
        String(50), default="balanced"
    )  # strict, balanced, encouraging
    notification_preferences: Mapped[dict] = mapped_column(
        JSONB, default={"email": True, "whatsapp": True, "push": True}
    )
    whatsapp_number: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # WhatsApp phone number with country code (e.g., +917038021340)
    study_schedule: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="settings")
