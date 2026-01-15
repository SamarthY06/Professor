"""Learning configuration models.

Stores user preferences collected during PDF upload as specified in Goals.md:
- Learning level
- Selected chapters
- Deadline/timeline
- Quiz preferences
- Reminder settings
"""

import uuid
from datetime import datetime, date
from typing import Optional, List

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class LearningConfig(Base):
    """
    Learning configuration for a book.
    
    This stores all user preferences collected during upload
    as specified in Goals.md Step 1.
    """
    
    __tablename__ = "learning_configs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    
    # Learning Level (BTech / MTech / Research / Custom)
    learning_level: Mapped[str] = mapped_column(
        String(50), nullable=False, default="intermediate"
    )  # beginner, intermediate, advanced, research
    
    # Chapter Selection
    study_all_chapters: Mapped[bool] = mapped_column(Boolean, default=True)
    selected_chapters: Mapped[Optional[List[int]]] = mapped_column(
        JSONB, nullable=True
    )  # List of chapter numbers to study, null = all (stored as JSON array)
    
    # Timeline
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    preferred_study_days: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(10)), nullable=True
    )  # ['monday', 'wednesday', 'friday']
    daily_study_minutes: Mapped[int] = mapped_column(Integer, default=60)
    
    # Quiz Preferences (as per Goals.md)
    quiz_frequency: Mapped[str] = mapped_column(
        String(30), nullable=False, default="after_each_chapter"
    )  # 'after_each_chapter', 'after_n_chapters', 'final_only'
    quiz_after_n_chapters: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # Only used if quiz_frequency = 'after_n_chapters'
    questions_per_quiz: Mapped[int] = mapped_column(Integer, default=5)
    quiz_difficulty: Mapped[str] = mapped_column(
        String(20), default="match_level"
    )  # 'easy', 'medium', 'hard', 'match_level'
    
    # Reminder & Inactivity Preferences
    enable_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_channel: Mapped[str] = mapped_column(
        String(20), default="push"
    )  # 'push', 'email', 'whatsapp', 'all'
    inactivity_threshold_hours: Mapped[int] = mapped_column(Integer, default=24)
    
    # Learning Plan Status
    plan_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class LearningPlan(Base):
    """
    AI-generated learning plan for a book.
    
    Created by Planner Agent, reviewed and accepted by user
    before teaching starts (as per Goals.md Step 4).
    """
    
    __tablename__ = "learning_plans"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Plan Details (structured JSON)
    plan_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Structure:
    # {
    #   "total_duration_days": 14,
    #   "chapters": [
    #     {
    #       "chapter_number": 1,
    #       "title": "...",
    #       "scheduled_date": "2026-01-15",
    #       "estimated_duration_minutes": 45,
    #       "topics": ["...", "..."],
    #       "quiz_after": true
    #     },
    #     ...
    #   ],
    #   "milestones": [
    #     {"name": "Chapter 3 Complete", "date": "...", "type": "checkpoint"}
    #   ]
    # }
    
    # Human-readable summary
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Version tracking (for plan revisions)
    version: Mapped[int] = mapped_column(Integer, default=1)
    
    # Status
    status: Mapped[str] = mapped_column(
        String(20), default="draft"
    )  # 'draft', 'pending_review', 'accepted', 'rejected', 'superseded'
    
    # User feedback
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ConversationState(Base):
    """
    Tracks the current state of professor-student conversation.
    
    This enables the professor to know where they are in the flow:
    - greeting → planning → teaching → doubt_resolution → quiz → next_chapter
    """
    
    __tablename__ = "conversation_states"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Current phase in the learning journey
    phase: Mapped[str] = mapped_column(
        String(30), nullable=False, default="greeting"
    )
    # Phases (in order per Goals.md):
    # 'greeting' - Professor has greeted, waiting for user response
    # 'planning' - Planner is generating/iterating on plan
    # 'plan_review' - User is reviewing the plan
    # 'teaching' - Active teaching in progress
    # 'doubt_resolution' - Clearing doubts after chapter
    # 'quiz' - Quiz in progress
    # 'chapter_complete' - Chapter done, transitioning
    # 'completed' - All chapters done
    # 'paused' - User paused learning
    
    # Current chapter context
    current_chapter: Mapped[int] = mapped_column(Integer, default=1)
    current_topic_index: Mapped[int] = mapped_column(Integer, default=0)
    
    # Chapter completion tracking
    chapters_taught: Mapped[List[int]] = mapped_column(ARRAY(Integer), default=[])
    chapters_quizzed: Mapped[List[int]] = mapped_column(ARRAY(Integer), default=[])
    
    # Doubt resolution flag
    doubts_cleared: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Quiz state (persisted between calls)
    quiz_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Structure: {"questions": [...], "current_index": 0, "scores": [...]}
    
    # Last professor message (for context)
    last_professor_action: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Temporal workflow ID (if active)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Timestamps
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
