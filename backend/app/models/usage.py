"""Usage tracking and subscription models for freemium system."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class UserSubscription(Base):
    """User subscription/tier information."""
    
    __tablename__ = "user_subscriptions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(
        String(50), default="free", nullable=False
    )  # free, byok (bring your own key), pro
    
    # Usage limits based on tier
    monthly_book_limit: Mapped[int] = mapped_column(Integer, default=2)  # Books/PDFs per month (free=2, byok=unlimited)
    monthly_message_limit: Mapped[int] = mapped_column(Integer, default=50)
    monthly_quiz_limit: Mapped[int] = mapped_column(Integer, default=30)
    
    # Plan limits
    max_plan_days: Mapped[int] = mapped_column(Integer, default=30)  # Max days in learning plan (free=30, byok=60)
    
    # Current month usage
    books_used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    messages_used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    quizzes_used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    
    # BYOK settings
    preferred_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # gpt-4o, gpt-4o-mini, gpt-5-mini, etc.
    use_batch_api: Mapped[bool] = mapped_column(Boolean, default=False)  # 50% cheaper, async
    
    # Billing cycle
    billing_cycle_start: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class UsageLog(Base):
    """Detailed usage log for tracking API calls and costs."""
    
    __tablename__ = "usage_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # What was used
    usage_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # chat_message, pdf_upload, quiz_generation, embedding, etc.
    
    # Model information
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)  # gpt-4o, gpt-4o-mini, text-embedding-3-small
    
    # Token usage
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)  # For cached input discount
    
    # Cost calculation (in USD cents for precision)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    
    # Who paid - platform or user (BYOK)
    paid_by: Mapped[str] = mapped_column(String(20), default="platform")  # platform, user
    
    # Context
    book_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # Request metadata
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DailyUsageAggregate(Base):
    """Daily aggregated usage for faster analytics queries."""
    
    __tablename__ = "daily_usage_aggregates"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    
    # Counts
    chat_messages: Mapped[int] = mapped_column(Integer, default=0)
    pdfs_uploaded: Mapped[int] = mapped_column(Integer, default=0)
    quizzes_taken: Mapped[int] = mapped_column(Integer, default=0)
    study_time_minutes: Mapped[int] = mapped_column(Integer, default=0)
    
    # Token usage
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    # Costs
    platform_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    user_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    
    # Model breakdown (JSON: {"gpt-4o": 100, "gpt-4o-mini": 500})
    model_usage: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    __table_args__ = (
        # Unique constraint on user_id + date
        {"sqlite_autoincrement": True},
    )


class PlatformUsageAggregate(Base):
    """Platform-wide daily aggregates for admin dashboard."""
    
    __tablename__ = "platform_usage_aggregates"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, unique=True, index=True)
    
    # User metrics
    total_users: Mapped[int] = mapped_column(Integer, default=0)
    new_users: Mapped[int] = mapped_column(Integer, default=0)
    active_users: Mapped[int] = mapped_column(Integer, default=0)
    
    # Tier breakdown
    free_tier_users: Mapped[int] = mapped_column(Integer, default=0)
    byok_users: Mapped[int] = mapped_column(Integer, default=0)
    pro_users: Mapped[int] = mapped_column(Integer, default=0)
    
    # Usage metrics
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_pdfs: Mapped[int] = mapped_column(Integer, default=0)
    total_quizzes: Mapped[int] = mapped_column(Integer, default=0)
    
    # Token usage
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    # Costs
    platform_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    
    # Model breakdown
    model_usage: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelPricing(Base):
    """OpenAI model pricing configuration (easily updatable)."""
    
    __tablename__ = "model_pricing"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Pricing per 1M tokens (in USD cents for precision)
    input_price_per_million: Mapped[int] = mapped_column(Integer, nullable=False)  # cents
    output_price_per_million: Mapped[int] = mapped_column(Integer, nullable=False)  # cents
    cached_input_price_per_million: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # cents
    
    # Model capabilities
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_batch: Mapped[bool] = mapped_column(Boolean, default=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=128000)
    
    # Tier availability
    available_for_free: Mapped[bool] = mapped_column(Boolean, default=False)
    available_for_byok: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class C1EnhancerPricing(Base):
    """C1 Visualize (Response Enhancer) pricing configuration."""
    
    __tablename__ = "c1_enhancer_pricing"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    model_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # anthropic, openai
    
    # Pricing per 1M tokens (in USD cents for precision)
    input_price_per_million: Mapped[int] = mapped_column(Integer, nullable=False)  # cents
    output_price_per_million: Mapped[int] = mapped_column(Integer, nullable=False)  # cents
    
    # Model capabilities
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class UserFeedback(Base):
    """User feedback and ratings."""
    
    __tablename__ = "user_feedback"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Feedback type
    feedback_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # general, bug_report, feature_request, teaching_quality, quiz_quality
    
    # Rating (1-5)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Content
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Context
    book_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    page_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="new")  # new, reviewed, resolved, archived
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
