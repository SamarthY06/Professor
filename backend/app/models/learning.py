"""Learning state and progress models.

NOTE: DocumentChunk model is kept for backwards compatibility but is no longer
used for new documents. All document chunking and embedding is handled by the
external RAG service.
"""

import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class LearningState(Base):
    """Master learning state per user per book/goal."""
    
    __tablename__ = "learning_states"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True
    )
    goal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="CASCADE"), nullable=True, index=True
    )
    
    # Progress tracking - Day-based (primary) and Chapter-based (internal)
    current_day: Mapped[int] = mapped_column(Integer, default=1)  # Current day in the plan
    current_chapter: Mapped[int] = mapped_column(Integer, default=1)  # Current chapter being taught
    current_section: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    completed_days: Mapped[list] = mapped_column(ARRAY(Integer), default=[])  # Days completed
    completed_chapters: Mapped[list] = mapped_column(ARRAY(Integer), default=[])  # Chapters completed
    completed_sections: Mapped[dict] = mapped_column(JSONB, default={})
    
    # Day tracking
    plan_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # When user started the plan
    day_topics_covered: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)  # Topics covered today
    
    # Context management
    summarized_past_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_topic_discussed: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pending_topics: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    
    # Learning configuration
    learning_plan: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    strict_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    professor_level: Mapped[str] = mapped_column(String(20), default="intermediate")
    
    # Engagement metrics
    motivation_score: Mapped[float] = mapped_column(Float, default=1.0)
    attention_score: Mapped[float] = mapped_column(Float, default=1.0)
    comprehension_score: Mapped[float] = mapped_column(Float, default=1.0)
    missed_sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_study_time_minutes: Mapped[int] = mapped_column(Integer, default=0)
    
    # Session info
    last_session_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Phase tracking (greeting, planning, teaching, quiz, completed)
    current_phase: Mapped[str] = mapped_column(String(30), default="greeting")
    
    # Quiz state (legacy field - use current_phase for phase tracking)
    quiz_mode: Mapped[str] = mapped_column(String(20), default="none")
    pending_quiz_questions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Day scope description (derived from plan_data at runtime, cached here for display)
    current_day_scope_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Optimistic locking version for concurrent state updates
    state_version: Mapped[int] = mapped_column(Integer, default=0)
    
    # Day and Chapter Summaries (for context continuity)
    # Structure: {"day_1": {"summary": "...", "topics": [...], "date": "..."}, ...}
    day_summaries: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Structure: {"chapter_2": {"summary": "...", "key_concepts": [...], "completed_at": "..."}, ...}
    chapter_summaries: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Cumulative summary of all completed content (compressed context)
    cumulative_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    __table_args__ = (
        CheckConstraint(
            "(book_id IS NOT NULL AND goal_id IS NULL) OR (book_id IS NULL AND goal_id IS NOT NULL)",
            name="one_learning_target"
        ),
    )


class ProgressSnapshot(Base):
    """Progress snapshots for analytics."""
    
    __tablename__ = "progress_snapshots"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    learning_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_states.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    chapter_progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quiz_scores: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    study_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    topics_covered: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    """
    Document chunks - DEPRECATED for new documents.
    
    NOTE: This model is kept for backwards compatibility with existing data.
    New documents are processed by the external RAG service and chunks are
    NOT stored in Professor's database.
    
    The external RAG service handles:
    - Document chunking
    - Embedding generation
    - Vector storage and search
    
    Professor only stores:
    - Book metadata
    - Chapter information (from RAG TOC)
    - RAG document/chapter IDs for reference
    """
    
    __tablename__ = "document_chunks"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # NOTE: embedding column removed - embeddings are stored in external RAG service
    chunk_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChapterSummary(Base):
    """Chapter summaries for context compression."""
    
    __tablename__ = "chapter_summaries"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_concepts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class TopicRelationship(Base):
    """Topic relationship graph for cross-chapter references."""
    
    __tablename__ = "topic_relationships"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_chapter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_chapters.id"), nullable=True
    )
    target_chapter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_chapters.id"), nullable=True
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    strength: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
