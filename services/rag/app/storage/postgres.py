"""PostgreSQL storage layer."""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.config.logging import get_logger
from app.models.base import Base
from app.models.document import Document, DocumentPhase, DocumentStatus
from app.models.chapter import Chapter, ChapterStatus
from app.models.chunk import Chunk, ChunkType

logger = get_logger(__name__)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Create session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session context manager."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class PostgresStorage:
    """PostgreSQL storage operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize with database session."""
        self.session = session

    # Document operations
    async def create_document(
        self,
        filename: str,
        original_filename: str,
        file_path: str,
        file_size: int,
        total_pages: Optional[int] = None,
    ) -> Document:
        """Create a new document record."""
        document = Document(
            filename=filename,
            original_filename=original_filename,
            file_path=file_path,
            file_size=file_size,
            total_pages=total_pages,
            status=DocumentStatus.PENDING,
            current_phase=DocumentPhase.UPLOAD,
        )
        self.session.add(document)
        await self.session.flush()
        logger.info("Created document", document_id=str(document.id), filename=filename)
        return document

    async def get_document(self, document_id: uuid.UUID) -> Optional[Document]:
        """Get document by ID."""
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def update_document_status(
        self,
        document_id: uuid.UUID,
        status: DocumentStatus,
        phase: Optional[DocumentPhase] = None,
        error_reason: Optional[str] = None,
    ) -> None:
        """Update document status."""
        values: dict = {"status": status}
        if phase is not None:
            values["current_phase"] = phase
        if error_reason is not None:
            values["error_reason"] = error_reason
        if status == DocumentStatus.INGESTING:
            values["started_at"] = datetime.utcnow()
        if status in (DocumentStatus.COMPLETED, DocumentStatus.FAILED):
            values["completed_at"] = datetime.utcnow()

        await self.session.execute(
            update(Document).where(Document.id == document_id).values(**values)
        )
        logger.info(
            "Updated document status",
            document_id=str(document_id),
            status=status.value,
        )

    async def update_document_toc(
        self,
        document_id: uuid.UUID,
        toc_data: dict,
        total_chapters: int,
    ) -> None:
        """Update document with TOC data."""
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                toc_data=toc_data,
                total_chapters=total_chapters,
                current_phase=DocumentPhase.CHAPTER_INGESTION,
            )
        )
        logger.info(
            "Updated document TOC",
            document_id=str(document_id),
            total_chapters=total_chapters,
        )

    async def increment_completed_chapters(self, document_id: uuid.UUID) -> None:
        """Increment completed chapters count."""
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(completed_chapters=Document.completed_chapters + 1)
        )

    async def set_document_total_pages(
        self, document_id: uuid.UUID, total_pages: int
    ) -> None:
        """Set document total pages."""
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(total_pages=total_pages)
        )

    # Chapter operations
    async def create_chapter(
        self,
        document_id: uuid.UUID,
        chapter_number: int,
        title: str,
        start_page: int,
        end_page: int,
        sections: Optional[list] = None,
    ) -> Chapter:
        """Create a new chapter record."""
        chapter = Chapter(
            document_id=document_id,
            chapter_number=chapter_number,
            title=title,
            start_page=start_page,
            end_page=end_page,
            sections=sections,
            status=ChapterStatus.PENDING,
        )
        self.session.add(chapter)
        await self.session.flush()
        logger.info(
            "Created chapter",
            chapter_id=str(chapter.id),
            document_id=str(document_id),
            title=title,
        )
        return chapter

    async def get_chapter(self, chapter_id: uuid.UUID) -> Optional[Chapter]:
        """Get chapter by ID."""
        result = await self.session.execute(
            select(Chapter).where(Chapter.id == chapter_id)
        )
        return result.scalar_one_or_none()

    async def get_chapters_by_document(
        self, document_id: uuid.UUID
    ) -> Sequence[Chapter]:
        """Get all chapters for a document."""
        result = await self.session.execute(
            select(Chapter)
            .where(Chapter.document_id == document_id)
            .order_by(Chapter.chapter_number)
        )
        return result.scalars().all()

    async def update_chapter_status(
        self,
        chapter_id: uuid.UUID,
        status: ChapterStatus,
        error_reason: Optional[str] = None,
        chunk_count: Optional[int] = None,
        image_count: Optional[int] = None,
    ) -> None:
        """Update chapter status."""
        values: dict = {"status": status}
        if error_reason is not None:
            values["error_reason"] = error_reason
        if chunk_count is not None:
            values["chunk_count"] = chunk_count
        if image_count is not None:
            values["image_count"] = image_count
        if status == ChapterStatus.PROCESSING:
            values["started_at"] = datetime.utcnow()
        if status in (ChapterStatus.COMPLETED, ChapterStatus.FAILED):
            values["completed_at"] = datetime.utcnow()

        await self.session.execute(
            update(Chapter).where(Chapter.id == chapter_id).values(**values)
        )
        logger.info(
            "Updated chapter status",
            chapter_id=str(chapter_id),
            status=status.value,
        )

    # Chunk operations
    async def create_chunk(
        self,
        chapter_id: uuid.UUID,
        chunk_index: int,
        chunk_type: ChunkType,
        content: str,
        token_count: int,
        start_page: int,
        end_page: int,
        section_title: Optional[str] = None,
        metadata: Optional[dict] = None,
        vector_id: Optional[str] = None,
    ) -> Chunk:
        """Create a new chunk record."""
        chunk = Chunk(
            chapter_id=chapter_id,
            chunk_index=chunk_index,
            chunk_type=chunk_type,
            content=content,
            token_count=token_count,
            start_page=start_page,
            end_page=end_page,
            section_title=section_title,
            metadata=metadata,
            vector_id=vector_id,
        )
        self.session.add(chunk)
        await self.session.flush()
        return chunk

    async def create_chunks_batch(self, chunks: list[Chunk]) -> None:
        """Create multiple chunks in batch."""
        self.session.add_all(chunks)
        await self.session.flush()
        logger.info("Created chunks batch", count=len(chunks))

    async def get_chunks_by_chapter(self, chapter_id: uuid.UUID) -> Sequence[Chunk]:
        """Get all chunks for a chapter."""
        result = await self.session.execute(
            select(Chunk)
            .where(Chunk.chapter_id == chapter_id)
            .order_by(Chunk.chunk_index)
        )
        return result.scalars().all()

    async def get_chunk_by_vector_id(self, vector_id: str) -> Optional[Chunk]:
        """Get chunk by vector ID."""
        result = await self.session.execute(
            select(Chunk).where(Chunk.vector_id == vector_id)
        )
        return result.scalar_one_or_none()

    async def update_chunk_vector_id(
        self, chunk_id: uuid.UUID, vector_id: str
    ) -> None:
        """Update chunk with vector ID."""
        await self.session.execute(
            update(Chunk).where(Chunk.id == chunk_id).values(vector_id=vector_id)
        )
