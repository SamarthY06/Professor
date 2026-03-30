"""Pydantic schemas for API contracts."""
from app.schemas.document import (
    DocumentUploadResponse,
    DocumentProgressResponse,
)
from app.schemas.chapter import (
    ChapterResponse,
    ChapterDetailResponse,
    ChapterListResponse,
)
from app.schemas.search import (
    SearchRequest,
    SearchResult,
    SearchResponse,
)
from app.schemas.toc import (
    TOCSection,
    TOCChapter,
    TOCResponse,
)

__all__ = [
    "DocumentUploadResponse",
    "DocumentProgressResponse",
    "ChapterResponse",
    "ChapterDetailResponse",
    "ChapterListResponse",
    "SearchRequest",
    "SearchResult",
    "SearchResponse",
    "TOCSection",
    "TOCChapter",
    "TOCResponse",
]
