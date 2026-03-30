"""Chapter API endpoints."""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from app.config.logging import get_logger
from app.models.chunk import ChunkType
from app.schemas.chapter import (
    ChapterResponse,
    ChapterDetailResponse,
    ChapterListResponse,
    ChunkResponse,
    ImageSummaryResponse,
    SectionResponse,
)
from app.storage.postgres import get_db_session, PostgresStorage

logger = get_logger(__name__)
router = APIRouter(prefix="/documents/{document_id}/chapters", tags=["chapters"])


@router.get("", response_model=ChapterListResponse)
async def list_chapters(document_id: uuid.UUID) -> ChapterListResponse:
    """
    List all chapters for a document.

    Returns chapter metadata only (no embeddings).
    """
    async with get_db_session() as session:
        storage = PostgresStorage(session)

        # Verify document exists
        document = await storage.get_document(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        chapters = await storage.get_chapters_by_document(document_id)

        chapter_responses = []
        for chapter in chapters:
            sections = None
            if chapter.sections:
                sections = [
                    SectionResponse(
                        title=s.get("title", ""),
                        start_page=s.get("start_page", 0),
                    )
                    for s in chapter.sections
                ]

            chapter_responses.append(
                ChapterResponse(
                    id=chapter.id,
                    document_id=chapter.document_id,
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    start_page=chapter.start_page,
                    end_page=chapter.end_page,
                    status=chapter.status,
                    chunk_count=chapter.chunk_count,
                    image_count=chapter.image_count,
                    sections=sections,
                )
            )

        return ChapterListResponse(
            document_id=document_id,
            total_chapters=len(chapter_responses),
            chapters=chapter_responses,
        )


@router.get("/{chapter_id}", response_model=ChapterDetailResponse)
async def get_chapter(document_id: uuid.UUID, chapter_id: uuid.UUID) -> ChapterDetailResponse:
    """
    Get chapter with full content.

    Returns:
    - Chunked text
    - Image summaries
    - Section metadata
    """
    async with get_db_session() as session:
        storage = PostgresStorage(session)

        # Verify document exists
        document = await storage.get_document(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Get chapter
        chapter = await storage.get_chapter(chapter_id)
        if not chapter or chapter.document_id != document_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found",
            )

        # Get chunks
        chunks = await storage.get_chunks_by_chapter(chapter_id)

        chunk_responses = []
        image_summaries = []

        for chunk in chunks:
            chunk_responses.append(
                ChunkResponse(
                    id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    chunk_type=chunk.chunk_type.value,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    start_page=chunk.start_page,
                    end_page=chunk.end_page,
                    section_title=chunk.section_title,
                )
            )

            # Extract image summaries from chunk metadata
            if chunk.chunk_metadata and "image_summaries" in chunk.chunk_metadata:
                for img_summary in chunk.chunk_metadata["image_summaries"]:
                    image_summaries.append(
                        ImageSummaryResponse(
                            page=img_summary.get("page", 0),
                            summary=img_summary.get("summary", ""),
                            section_title=chunk.section_title,
                        )
                    )

            # Also check for IMAGE_SUMMARY type chunks
            if chunk.chunk_type == ChunkType.IMAGE_SUMMARY:
                image_summaries.append(
                    ImageSummaryResponse(
                        page=chunk.start_page,
                        summary=chunk.content,
                        section_title=chunk.section_title,
                    )
                )

        # Parse sections
        sections = None
        if chapter.sections:
            sections = [
                SectionResponse(
                    title=s.get("title", ""),
                    start_page=s.get("start_page", 0),
                )
                for s in chapter.sections
            ]

        return ChapterDetailResponse(
            id=chapter.id,
            document_id=chapter.document_id,
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            start_page=chapter.start_page,
            end_page=chapter.end_page,
            status=chapter.status,
            sections=sections,
            chunks=chunk_responses,
            image_summaries=image_summaries,
            started_at=chapter.started_at,
            completed_at=chapter.completed_at,
        )
