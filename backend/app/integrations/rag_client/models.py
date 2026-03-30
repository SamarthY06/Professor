"""Data Transfer Objects (DTOs) for RAG client.

All request/response models for interacting with the external RAG service.
These models ensure type safety and validation for all API interactions.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IngestionStatus(str, Enum):
    """Document ingestion status values."""
    PENDING = "PENDING"
    INGESTING = "INGESTING"
    COMPLETED = "COMPLETED"
    PARTIAL_READY = "PARTIAL_READY"
    FAILED = "FAILED"


# =============================================================================
# Document Upload
# =============================================================================

class DocumentUploadResponse(BaseModel):
    """Response from document upload endpoint."""
    document_id: str = Field(..., description="Unique identifier for the uploaded document")
    status: IngestionStatus = Field(..., description="Current ingestion status")
    filename: Optional[str] = Field(None, description="Original filename")
    message: Optional[str] = Field(None, description="Status message")
    created_at: Optional[datetime] = Field(None, description="Upload timestamp")
    
    class Config:
        use_enum_values = True


# =============================================================================
# Document Progress
# =============================================================================

class DocumentProgressCost(BaseModel):
    """Cost breakdown for document processing."""
    embedding_cost: str = Field("0.00000000", description="Embedding generation cost")
    toc_detection_cost: str = Field("0.00000000", description="TOC detection cost")
    image_summary_cost: str = Field("0.00000000", description="Image summarization cost")
    total_cost: str = Field("0.00000000", description="Total processing cost")
    total_tokens: int = Field(0, description="Total tokens used")
    
    @property
    def total_cost_cents(self) -> int:
        """Convert total cost to cents."""
        try:
            return int(float(self.total_cost) * 100)
        except (ValueError, TypeError):
            return 0


class DocumentProgressResponse(BaseModel):
    """Response from document progress endpoint."""
    document_id: str = Field(..., description="Document identifier")
    status: IngestionStatus = Field(..., description="Current ingestion status")
    total_chapters: int = Field(0, description="Total chapters detected")
    completed_chapters: int = Field(0, description="Chapters fully processed")
    percentage: float = Field(0.0, ge=0, le=100, description="Progress percentage")
    current_phase: Optional[str] = Field(None, description="Current processing phase")
    error_reason: Optional[str] = Field(None, description="Error message if failed")
    started_at: Optional[datetime] = Field(None, description="Processing start time")
    completed_at: Optional[datetime] = Field(None, description="Processing completion time")
    cost: Optional[DocumentProgressCost] = Field(None, description="Processing cost breakdown")
    
    class Config:
        use_enum_values = True
    
    @property
    def progress_percentage(self) -> float:
        """Alias for percentage field."""
        return self.percentage
    
    @property
    def current_step(self) -> Optional[str]:
        """Alias for current_phase field."""
        return self.current_phase
    
    @property
    def error_message(self) -> Optional[str]:
        """Alias for error_reason field."""
        return self.error_reason
    
    @property
    def is_complete(self) -> bool:
        """Check if ingestion is complete."""
        return self.status == IngestionStatus.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        """Check if ingestion failed."""
        return self.status == IngestionStatus.FAILED
    
    @property
    def is_in_progress(self) -> bool:
        """Check if ingestion is still in progress."""
        return self.status in (IngestionStatus.PENDING, IngestionStatus.INGESTING)


# =============================================================================
# Table of Contents
# =============================================================================

class TOCEntry(BaseModel):
    """A single entry in the table of contents (maps to ChapterResponse)."""
    id: str = Field(..., description="Unique chapter identifier")
    document_id: str = Field(..., description="Parent document ID")
    chapter_number: int = Field(..., description="Chapter number (1-indexed)")
    title: str = Field(..., description="Chapter title")
    start_page: int = Field(..., description="Starting page number")
    end_page: int = Field(..., description="Ending page number")
    status: Optional[str] = Field(None, description="Chapter processing status")
    chunk_count: Optional[int] = Field(None, description="Number of chunks")
    image_count: Optional[int] = Field(None, description="Number of images")
    sections: Optional[List[Dict[str, Any]]] = Field(None, description="Sections in chapter")
    estimated_duration_minutes: Optional[int] = Field(None, description="Estimated reading time")
    
    class Config:
        populate_by_name = True
    
    @property
    def chapter_id(self) -> str:
        """Alias for id field."""
        return self.id
    
    @property
    def pages(self) -> int:
        """Get page count from start/end."""
        return max(1, self.end_page - self.start_page + 1)


class DocumentTOCResponse(BaseModel):
    """Response from document TOC endpoint."""
    document_id: str = Field(..., description="Document identifier")
    title: Optional[str] = Field(None, description="Document title")
    total_chapters: int = Field(..., description="Total number of chapters")
    total_pages: Optional[int] = Field(None, description="Total pages in document")
    chapters: List[TOCEntry] = Field(default_factory=list, description="List of chapters")
    
    def get_chapter_by_number(self, chapter_number: int) -> Optional[TOCEntry]:
        """Get a chapter by its number."""
        for chapter in self.chapters:
            if chapter.chapter_number == chapter_number:
                return chapter
        return None
    
    def get_chapter_by_id(self, chapter_id: str) -> Optional[TOCEntry]:
        """Get a chapter by its ID."""
        for chapter in self.chapters:
            if chapter.chapter_id == chapter_id:
                return chapter
        return None


# =============================================================================
# Chapter Information
# =============================================================================

class ChapterInfo(BaseModel):
    """Detailed chapter information (maps to ChapterResponse)."""
    id: str = Field(..., description="Unique chapter identifier")
    document_id: str = Field(..., description="Parent document identifier")
    chapter_number: int = Field(..., description="Chapter number (1-indexed)")
    title: str = Field(..., description="Chapter title")
    start_page: int = Field(..., description="Starting page number")
    end_page: int = Field(..., description="Ending page number")
    status: str = Field(..., description="Chapter processing status")
    chunk_count: int = Field(0, description="Number of chunks")
    image_count: int = Field(0, description="Number of images")
    sections: Optional[List[Dict[str, Any]]] = Field(None, description="Sections in chapter")
    estimated_duration_minutes: Optional[int] = Field(None, description="Estimated reading time")
    summary: Optional[str] = Field(None, description="Chapter summary")
    
    class Config:
        populate_by_name = True
    
    @property
    def chapter_id(self) -> str:
        """Alias for id field."""
        return self.id


class ChapterListResponse(BaseModel):
    """Response from chapters list endpoint."""
    document_id: str = Field(..., description="Document identifier")
    total_chapters: int = Field(..., description="Total number of chapters")
    chapters: List[Dict[str, Any]] = Field(default_factory=list, description="List of chapters")
    
    def get_chapter_infos(self) -> List[ChapterInfo]:
        """Convert raw chapter dicts to ChapterInfo objects."""
        return [ChapterInfo(**ch) for ch in self.chapters]


# =============================================================================
# Search
# =============================================================================

class RAGCostInfo(BaseModel):
    """Cost information from RAG service operations."""
    model: str = Field(..., description="Model used for the operation")
    input_tokens: int = Field(0, description="Input tokens consumed")
    output_tokens: int = Field(0, description="Output tokens consumed")
    cost_usd: str = Field("0.00000000", description="Cost in USD as string")
    
    @property
    def cost_cents(self) -> int:
        """Convert USD string to cents."""
        try:
            return int(float(self.cost_usd) * 100)
        except (ValueError, TypeError):
            return 0
    
    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens


class SearchRequest(BaseModel):
    """Request body for search endpoint."""
    document_id: str = Field(..., description="Document to search within")
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    chapter_ids: Optional[List[str]] = Field(None, description="Limit search to specific chapters")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results to return")
    openai_key: Optional[str] = Field(None, description="Custom OpenAI API key for BYOK users")


class SearchResult(BaseModel):
    """A single search result."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    chapter_id: str = Field(..., description="Chapter containing this chunk")
    chapter_title: str = Field(..., description="Chapter title")
    content: str = Field(..., description="Chunk text content")
    score: float = Field(..., description="Similarity score")
    page_range: List[int] = Field(..., description="Page range [start, end]")
    section_title: Optional[str] = Field(None, description="Section title if available")
    chunk_type: str = Field(..., description="Type of chunk")
    
    @property
    def similarity_score(self) -> float:
        """Alias for score field."""
        return self.score
    
    @property
    def chapter_number(self) -> int:
        """Extract chapter number from title or return 0."""
        return 0  # Will be populated from chapter_title if needed


class SearchResponse(BaseModel):
    """Response from search endpoint."""
    document_id: str = Field(..., description="Document searched")
    query: str = Field(..., description="Original search query")
    total_results: int = Field(..., description="Total matching results")
    results: List[SearchResult] = Field(default_factory=list, description="Search results")
    cost: Optional[RAGCostInfo] = Field(None, description="Cost information for this search")
    
    def get_top_results(self, n: int = 5) -> List[SearchResult]:
        """Get top N results by similarity score."""
        return sorted(self.results, key=lambda x: x.score, reverse=True)[:n]
    
    def get_results_for_chapter(self, chapter_id: str) -> List[SearchResult]:
        """Get results filtered to a specific chapter."""
        return [r for r in self.results if r.chapter_id == chapter_id]
    
    def format_context(self, max_chunks: int = 8) -> str:
        """Format search results as context for LLM prompts."""
        if not self.results:
            return "No relevant content found."
        
        parts = []
        for i, result in enumerate(self.results[:max_chunks], 1):
            section = f" ({result.section_title})" if result.section_title else ""
            chapter_info = f"{result.chapter_title or 'Untitled'}"
            relevance = f"{result.score * 100:.0f}%"
            
            parts.append(f"[{i}] {chapter_info}{section} (Relevance: {relevance})")
            parts.append(result.content)
            parts.append("")
        
        return "\n".join(parts)


# =============================================================================
# Authentication
# =============================================================================

class AuthTokenResponse(BaseModel):
    """Response from authentication endpoint."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: Optional[int] = Field(None, description="Token expiry in seconds")
    expires_at: Optional[datetime] = Field(None, description="Token expiry timestamp")


# Enable forward references for nested models
TOCEntry.model_rebuild()
