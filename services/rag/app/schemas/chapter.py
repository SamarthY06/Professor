"""Chapter schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.models.chapter import ChapterStatus


class SectionResponse(BaseModel):
    """Section within a chapter."""

    title: str
    start_page: int


class ChunkResponse(BaseModel):
    """Chunk response schema."""

    id: UUID
    chunk_index: int
    chunk_type: str
    content: str
    token_count: int
    start_page: int
    end_page: int
    section_title: Optional[str] = None

    class Config:
        from_attributes = True


class ImageSummaryResponse(BaseModel):
    """Image summary response."""

    page: int
    summary: str
    section_title: Optional[str] = None


class ChapterResponse(BaseModel):
    """Response schema for chapter metadata."""

    id: UUID
    document_id: UUID
    chapter_number: int
    title: str
    start_page: int
    end_page: int
    status: ChapterStatus
    chunk_count: int
    image_count: int
    sections: Optional[list[SectionResponse]] = None

    class Config:
        from_attributes = True


class ChapterDetailResponse(BaseModel):
    """Response schema for chapter with content."""

    id: UUID
    document_id: UUID
    chapter_number: int
    title: str
    start_page: int
    end_page: int
    status: ChapterStatus
    sections: Optional[list[SectionResponse]] = None
    chunks: list[ChunkResponse]
    image_summaries: list[ImageSummaryResponse]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChapterListResponse(BaseModel):
    """Response schema for list of chapters."""

    document_id: UUID
    total_chapters: int
    chapters: list[ChapterResponse]
