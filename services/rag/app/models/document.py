"""Document model."""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.chapter import Chapter


class DocumentStatus(str, enum.Enum):
    """Document processing status."""

    PENDING = "PENDING"
    INGESTING = "INGESTING"
    COMPLETED = "COMPLETED"
    PARTIAL_READY = "PARTIAL_READY"
    FAILED = "FAILED"


class DocumentPhase(str, enum.Enum):
    """Current processing phase."""

    UPLOAD = "UPLOAD"
    TOC = "TOC"
    CHAPTER_INGESTION = "CHAPTER_INGESTION"
    EMBEDDING = "EMBEDDING"
    COMPLETED = "COMPLETED"


class Document(Base, TimestampMixin):
    """Document model representing an uploaded PDF."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    total_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus),
        default=DocumentStatus.PENDING,
        nullable=False,
    )
    current_phase: Mapped[DocumentPhase] = mapped_column(
        Enum(DocumentPhase),
        default=DocumentPhase.UPLOAD,
        nullable=False,
    )

    total_chapters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_chapters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    toc_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relationships
    chapters: Mapped[list["Chapter"]] = relationship(
        "Chapter",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total_chapters == 0:
            return 0.0
        return round((self.completed_chapters / self.total_chapters) * 100, 2)
