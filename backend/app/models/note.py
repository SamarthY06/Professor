"""Notes and reminders models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class UserNote(Base):
    """User notes."""
    
    __tablename__ = "user_notes"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True
    )
    goal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="SET NULL"), nullable=True
    )
    chapter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_chapters.id", ondelete="SET NULL"), nullable=True
    )
    
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id"), nullable=True
    )
    tags: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Reminder(Base):
    """Reminders and notifications."""
    
    __tablename__ = "reminders"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learning_state_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_states.id"), nullable=True
    )
    
    reminder_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # daily_study, quiz_due, missed_session, chapter_complete
    channel: Mapped[str] = mapped_column(String(50), nullable=False)  # whatsapp, email, push
    
    message_template: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    message_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, sent, failed, cancelled
    
    dedup_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
