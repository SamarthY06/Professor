"""Cost tracking models."""
import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, Integer, String, Text, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document


class CostType(str, enum.Enum):
    """Type of OpenAI API cost."""
    
    EMBEDDING = "EMBEDDING"           # text-embedding-3-small
    TOC_DETECTION = "TOC_DETECTION"   # gpt-4o for TOC
    IMAGE_SUMMARY = "IMAGE_SUMMARY"   # gpt-4o-vision for images
    RAG_QUERY = "RAG_QUERY"           # Query embedding generation


class CostTransaction(Base, TimestampMixin):
    """Individual cost transaction record."""
    
    __tablename__ = "cost_transactions"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Link to document (optional - RAG queries may not have document)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # User tracking (for future user-based billing)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    # Cost type
    cost_type: Mapped[CostType] = mapped_column(
        Enum(CostType),
        nullable=False,
    )
    
    # Model used
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Token counts
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Cost in USD (using Decimal for precision)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=8),
        nullable=False,
    )
    
    # Additional metadata
    cost_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationship
    document: Mapped[Optional["Document"]] = relationship(
        "Document",
        backref="cost_transactions",
    )


class CostSummary(Base, TimestampMixin):
    """Aggregated cost summary by day/user."""
    
    __tablename__ = "cost_summaries"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    
    # Summary date (UTC)
    summary_date: Mapped[datetime] = mapped_column(nullable=False)
    
    # User (null for system-wide)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    # Aggregated costs by type
    embedding_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=8),
        default=Decimal("0"),
        nullable=False,
    )
    toc_detection_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=8),
        default=Decimal("0"),
        nullable=False,
    )
    image_summary_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=8),
        default=Decimal("0"),
        nullable=False,
    )
    rag_query_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=8),
        default=Decimal("0"),
        nullable=False,
    )
    
    # Total
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=8),
        default=Decimal("0"),
        nullable=False,
    )
    
    # Token counts
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Transaction count
    transaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# OpenAI Pricing (as of Jan 2026 - update as needed)
# https://platform.openai.com/docs/pricing
OPENAI_PRICING = {
    # Embedding models (per 1M tokens)
    "text-embedding-3-small": {
        "input": Decimal("0.02"),  # $0.02 per 1M tokens
    },
    "text-embedding-3-large": {
        "input": Decimal("0.13"),  # $0.13 per 1M tokens
    },
    # GPT-4o (per 1M tokens)
    "gpt-4o": {
        "input": Decimal("2.50"),   # $2.50 per 1M input tokens
        "output": Decimal("10.00"), # $10.00 per 1M output tokens
    },
    "gpt-4o-mini": {
        "input": Decimal("0.15"),   # $0.15 per 1M input tokens
        "output": Decimal("0.60"),  # $0.60 per 1M output tokens
    },
    # GPT-4 Turbo
    "gpt-4-turbo": {
        "input": Decimal("10.00"),  # $10.00 per 1M input tokens
        "output": Decimal("30.00"), # $30.00 per 1M output tokens
    },
}


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
) -> Decimal:
    """
    Calculate cost in USD for given token usage.
    
    Args:
        model: OpenAI model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens (for chat models)
        
    Returns:
        Cost in USD as Decimal
    """
    pricing = OPENAI_PRICING.get(model)
    if not pricing:
        # Default to gpt-4o pricing if model not found
        pricing = OPENAI_PRICING["gpt-4o"]
    
    # Calculate cost (pricing is per 1M tokens)
    input_cost = (Decimal(input_tokens) / Decimal("1000000")) * pricing.get("input", Decimal("0"))
    output_cost = (Decimal(output_tokens) / Decimal("1000000")) * pricing.get("output", Decimal("0"))
    
    return input_cost + output_cost
