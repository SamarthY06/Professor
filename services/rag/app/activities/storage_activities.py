"""Storage activities for persisting data to PostgreSQL and Qdrant."""
import uuid
from typing import Optional

from temporalio import activity

from app.config.logging import get_logger
from app.models.chapter import ChapterStatus
from app.models.chunk import ChunkType, Chunk
from app.models.document import DocumentPhase, DocumentStatus
from app.storage.postgres import get_db_session, PostgresStorage
from app.storage.qdrant import QdrantStorage

logger = get_logger(__name__)


@activity.defn
async def persist_toc_and_chapters(
    document_id: str,
    toc_data: dict,
    chapters: list[dict],
) -> list[str]:
    """
    Persist TOC data and create chapter records.

    Args:
        document_id: Document UUID string
        toc_data: Parsed TOC data
        chapters: List of chapter info dicts

    Returns:
        List of created chapter IDs
    """
    activity.logger.info(f"Persisting TOC and {len(chapters)} chapters for document {document_id}")

    doc_uuid = uuid.UUID(document_id)
    chapter_ids = []

    async with get_db_session() as session:
        storage = PostgresStorage(session)

        # Update document with TOC data
        await storage.update_document_toc(
            document_id=doc_uuid,
            toc_data=toc_data,
            total_chapters=len(chapters),
        )

        # Create chapter records
        for chapter_data in chapters:
            chapter = await storage.create_chapter(
                document_id=doc_uuid,
                chapter_number=chapter_data["chapter_number"],
                title=chapter_data["title"],
                start_page=chapter_data["start_page"],
                end_page=chapter_data["end_page"],
                sections=chapter_data.get("sections"),
            )
            chapter_ids.append(str(chapter.id))

    activity.logger.info(f"Created {len(chapter_ids)} chapter records")
    return chapter_ids


@activity.defn
async def update_chapter_processing_status(
    chapter_id: str,
    status: str,
    error_reason: Optional[str] = None,
    chunk_count: Optional[int] = None,
    image_count: Optional[int] = None,
) -> None:
    """Update chapter processing status."""
    activity.logger.info(f"Updating chapter {chapter_id} status to {status}")

    chapter_uuid = uuid.UUID(chapter_id)
    chapter_status = ChapterStatus(status)

    async with get_db_session() as session:
        storage = PostgresStorage(session)
        await storage.update_chapter_status(
            chapter_id=chapter_uuid,
            status=chapter_status,
            error_reason=error_reason,
            chunk_count=chunk_count,
            image_count=image_count,
        )


@activity.defn
async def persist_chunks_and_vectors(
    document_id: str,
    chapter_id: str,
    chunks_with_embeddings: list[dict],
) -> int:
    """
    Persist chunks to PostgreSQL and vectors to Qdrant.

    Args:
        document_id: Document UUID string
        chapter_id: Chapter UUID string
        chunks_with_embeddings: List of chunk dicts with embeddings

    Returns:
        Number of chunks persisted
    """
    if not chunks_with_embeddings:
        return 0

    activity.logger.info(
        f"Persisting {len(chunks_with_embeddings)} chunks for chapter {chapter_id}"
    )

    chapter_uuid = uuid.UUID(chapter_id)

    # Prepare vectors for Qdrant
    vectors = []
    chunk_records = []

    for chunk_data in chunks_with_embeddings:
        vector_id = chunk_data.get("vector_id", str(uuid.uuid4()))

        # Create chunk record
        chunk = Chunk(
            chapter_id=chapter_uuid,
            chunk_index=chunk_data["chunk_index"],
            chunk_type=ChunkType.TEXT,
            content=chunk_data["content"],
            token_count=chunk_data["token_count"],
            start_page=chunk_data["start_page"],
            end_page=chunk_data["end_page"],
            section_title=chunk_data.get("section_title"),
            chunk_metadata={"image_summaries": chunk_data.get("image_summaries", [])},
            vector_id=vector_id,
        )
        chunk_records.append(chunk)

        # Prepare vector payload
        payload = {
            "document_id": document_id,
            "chapter_id": chapter_id,
            "chunk_id": str(chunk.id),
            "chunk_index": chunk_data["chunk_index"],
            "content": chunk_data["content"],
            "token_count": chunk_data["token_count"],
            "start_page": chunk_data["start_page"],
            "end_page": chunk_data["end_page"],
            "section_title": chunk_data.get("section_title"),
            "chunk_type": "TEXT",
        }

        if "image_summaries" in chunk_data:
            payload["image_summaries"] = chunk_data["image_summaries"]

        vectors.append((
            vector_id,
            chunk_data["embedding"],
            payload,
        ))

    # Persist to PostgreSQL
    async with get_db_session() as session:
        storage = PostgresStorage(session)
        await storage.create_chunks_batch(chunk_records)

    # Persist to Qdrant
    qdrant = QdrantStorage()
    qdrant.upsert_vectors(vectors)

    activity.logger.info(f"Persisted {len(chunk_records)} chunks and vectors")
    return len(chunk_records)


@activity.defn
async def update_document_completion(
    document_id: str,
    success: bool,
    error_reason: Optional[str] = None,
) -> None:
    """Update document status on completion."""
    activity.logger.info(f"Updating document {document_id} completion status")

    doc_uuid = uuid.UUID(document_id)

    async with get_db_session() as session:
        storage = PostgresStorage(session)

        if success:
            await storage.update_document_status(
                document_id=doc_uuid,
                status=DocumentStatus.COMPLETED,
                phase=DocumentPhase.COMPLETED,
            )
        else:
            # Check if any chapters completed
            document = await storage.get_document(doc_uuid)
            if document and document.completed_chapters > 0:
                await storage.update_document_status(
                    document_id=doc_uuid,
                    status=DocumentStatus.PARTIAL_READY,
                    error_reason=error_reason,
                )
            else:
                await storage.update_document_status(
                    document_id=doc_uuid,
                    status=DocumentStatus.FAILED,
                    error_reason=error_reason,
                )


@activity.defn
async def increment_document_progress(document_id: str) -> None:
    """Increment completed chapters count for document."""
    doc_uuid = uuid.UUID(document_id)

    async with get_db_session() as session:
        storage = PostgresStorage(session)
        await storage.increment_completed_chapters(doc_uuid)


@activity.defn
async def set_document_pages(document_id: str, total_pages: int) -> None:
    """Set total pages for document."""
    doc_uuid = uuid.UUID(document_id)

    async with get_db_session() as session:
        storage = PostgresStorage(session)
        await storage.set_document_total_pages(doc_uuid, total_pages)
