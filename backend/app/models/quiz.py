"""Quiz and assessment models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Quiz(Base):
    """Quiz definitions."""
    
    __tablename__ = "quizzes"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quiz_type: Mapped[str] = mapped_column(String(50), nullable=False)  # chapter_end, random_attention, review
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_questions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passing_score: Mapped[float] = mapped_column(Float, default=0.7)
    time_limit_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    questions: Mapped[list["QuizQuestion"]] = relationship(
        "QuizQuestion", back_populates="quiz", cascade="all, delete-orphan"
    )
    attempts: Mapped[list["QuizAttempt"]] = relationship(
        "QuizAttempt", back_populates="quiz", cascade="all, delete-orphan"
    )


class QuizQuestion(Base):
    """Quiz questions."""
    
    __tablename__ = "quiz_questions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id"), nullable=True
    )
    chapter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_chapters.id"), nullable=True
    )
    
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str] = mapped_column(String(50), nullable=False)  # mcq, true_false, short_answer, explain
    options: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # For MCQ
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    topic: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id"), nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="questions")
    responses: Mapped[list["QuestionResponse"]] = relationship(
        "QuestionResponse", back_populates="question", cascade="all, delete-orphan"
    )


class QuizAttempt(Base):
    """User quiz attempts."""
    
    __tablename__ = "quiz_attempts"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learning_state_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_states.id"), nullable=True
    )
    
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    time_taken_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    answers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # {question_id: user_answer}
    feedback: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # AI-generated feedback
    
    # Relationships
    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="attempts")
    responses: Mapped[list["QuestionResponse"]] = relationship(
        "QuestionResponse", back_populates="attempt", cascade="all, delete-orphan"
    )


class QuestionResponse(Base):
    """Individual question responses for analytics."""
    
    __tablename__ = "question_responses"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    time_taken_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    attempt: Mapped["QuizAttempt"] = relationship("QuizAttempt", back_populates="responses")
    question: Mapped["QuizQuestion"] = relationship("QuizQuestion", back_populates="responses")


class AttentionQuestion(Base):
    """Random attention questions during teaching."""
    
    __tablename__ = "attention_questions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True
    )
    chapter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("book_chapters.id"), nullable=True
    )
    
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Context
    topic_being_taught: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # time_based, topic_completion, random
