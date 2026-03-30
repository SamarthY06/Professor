"""Document schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.document import DocumentPhase, DocumentStatus


class DocumentCostBreakdown(BaseModel):
    """Cost breakdown for document processing."""
    
    embedding_cost: str
    toc_detection_cost: str
    image_summary_cost: str
    total_cost: str
    total_tokens: int


class DocumentUploadResponse(BaseModel):
    """Response schema for document upload."""

    document_id: UUID
    status: DocumentStatus
    message: str = "Document uploaded and processing started"

    class Config:
        from_attributes = True


class DocumentProgressResponse(BaseModel):
    """Response schema for document progress."""

    document_id: UUID
    status: DocumentStatus
    total_chapters: int
    completed_chapters: int
    percentage: float = Field(ge=0, le=100)
    current_phase: DocumentPhase
    error_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cost: Optional[DocumentCostBreakdown] = Field(
        default=None,
        description="Cost breakdown for document processing (available after completion)"
    )

    class Config:
        from_attributes = True
