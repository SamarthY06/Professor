"""Chunk model."""
import enum
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.chapter import Chapter


class ChunkType(str, enum.Enum):
    """Type of chunk content."""

    TEXT = "TEXT"
    IMAGE_SUMMARY = "IMAGE_SUMMARY"


class Chunk(Base, TimestampMixin):
    """Chunk model representing a text or image summary chunk."""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    chapter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[ChunkType] = mapped_column(
        Enum(ChunkType),
        default=ChunkType.TEXT,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)

    section_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    chunk_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Vector ID in Qdrant
    vector_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    chapter: Mapped["Chapter"] = relationship(
        "Chapter",
        back_populates="chunks",
    )
