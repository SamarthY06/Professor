"""Chapter model."""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.chunk import Chunk


class ChapterStatus(str, enum.Enum):
    """Chapter processing status."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Chapter(Base, TimestampMixin):
    """Chapter model representing a document chapter."""

    __tablename__ = "chapters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[ChapterStatus] = mapped_column(
        Enum(ChapterStatus),
        default=ChapterStatus.PENDING,
        nullable=False,
    )

    sections: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chapters",
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="chapter",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def page_count(self) -> int:
        """Get number of pages in chapter."""
        return self.end_page - self.start_page + 1
