"""Chat and session models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ChatSession(Base):
    """Chat sessions (multiple per book)."""
    
    __tablename__ = "chat_sessions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learning_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_states.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True
    )
    goal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    chapter_context: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    session_type: Mapped[str] = mapped_column(String(50), default="learning")  # learning, quiz, review
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    """Individual chat messages with full metadata."""
    
    __tablename__ = "chat_messages"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Message content
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Agent tracking
    agent_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    agent_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Context tracking
    context_used: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    chapter_at_time: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Quiz-specific
    is_quiz_question: Mapped[bool] = mapped_column(Boolean, default=False)
    quiz_answer_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Metadata
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")


class AgentLog(Base):
    """Full agent execution logs for debugging and analytics."""
    
    __tablename__ = "agent_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True
    )
    book_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    chapter_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # Execution details
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # State tracking
    state_before: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    state_after: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Performance
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
