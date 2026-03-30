"""Search schemas."""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Request schema for search."""

    document_id: UUID
    chapter_ids: Optional[list[UUID]] = None
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    openai_key: Optional[str] = Field(
        default=None,
        description="Optional OpenAI API key. If provided, uses this key instead of the default."
    )


class SearchResult(BaseModel):
    """Individual search result."""

    chunk_id: UUID
    chapter_id: UUID
    chapter_title: str
    content: str
    score: float
    page_range: tuple[int, int]
    section_title: Optional[str] = None
    chunk_type: str


class QueryCost(BaseModel):
    """Cost information for the query."""
    
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: str
    

class SearchResponse(BaseModel):
    """Response schema for search."""

    document_id: UUID
    query: str
    total_results: int
    results: list[SearchResult]
    cost: Optional[QueryCost] = Field(
        default=None,
        description="Cost information for this query"
    )
