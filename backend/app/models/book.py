"""Book and Goal database models."""

import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.learning_config import LearningConfig


class Book(Base):
    """Uploaded books/documents."""
    
    __tablename__ = "books"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # For deduplication
    total_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_chapters: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending, processing, completed, failed, ready_for_planning
    processing_progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100 percentage
    processing_step: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Current step description
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    book_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Professor initiation tracking (per Goals.md Step 3)
    professor_greeted: Mapped[bool] = mapped_column(Boolean, default=False)
    professor_greeting_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    chapters: Mapped[list["BookChapter"]] = relationship(
        "BookChapter", back_populates="book", cascade="all, delete-orphan"
    )
    learning_config: Mapped[Optional["LearningConfig"]] = relationship(
        "LearningConfig", backref="book", uselist=False, cascade="all, delete-orphan"
    )


class BookChapter(Base):
    """Chapter detection and storage."""
    
    __tablename__ = "book_chapters"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI-generated after completion
    key_concepts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    prerequisite_chapters: Mapped[Optional[list]] = mapped_column(ARRAY(Integer), nullable=True)
    estimated_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    book: Mapped["Book"] = relationship("Book", back_populates="chapters")
    
    __table_args__ = (
        # Unique constraint on book_id + chapter_number
        {"sqlite_autoincrement": True},
    )


class Goal(Base):
    """Goal-based learning without a document."""
    
    __tablename__ = "goals"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty_level: Mapped[str] = mapped_column(String(20), default="intermediate")
    status: Mapped[str] = mapped_column(
        String(50), default="active"
    )  # active, paused, completed, abandoned
    ai_generated_curriculum: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    chapters: Mapped[list["GoalChapter"]] = relationship(
        "GoalChapter", back_populates="goal", cascade="all, delete-orphan"
    )


class GoalChapter(Base):
    """Virtual chapters for goals."""
    
    __tablename__ = "goal_chapters"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    topics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    learning_objectives: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    goal: Mapped["Goal"] = relationship("Goal", back_populates="chapters")
    
    __table_args__ = (
        # Unique constraint on goal_id + week_number
        {"sqlite_autoincrement": True},
    )
