"""Search API endpoints."""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from openai import OpenAI

from app.config.settings import settings
from app.config.logging import get_logger
from app.schemas.search import SearchRequest, SearchResponse, SearchResult, QueryCost
from app.storage.postgres import get_db_session, PostgresStorage
from app.storage.qdrant import QdrantStorage
from app.activities.cost_tracking import record_cost_sync
from app.models.cost import calculate_cost

logger = get_logger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    """
    Chapter-scoped semantic search.

    Body:
    - document_id: Document to search within
    - chapter_ids: Optional list of chapters to filter by
    - query: Search query string
    - limit: Maximum results (default 10)
    - openai_key: Optional OpenAI API key (uses default if not provided)
    
    Returns:
    - Search results with cost information
    """
    async with get_db_session() as session:
        storage = PostgresStorage(session)

        # Verify document exists
        document = await storage.get_document(request.document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Verify chapters exist if specified
        if request.chapter_ids:
            for chapter_id in request.chapter_ids:
                chapter = await storage.get_chapter(chapter_id)
                if not chapter or chapter.document_id != request.document_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Chapter {chapter_id} not found",
                    )

    # Use provided OpenAI key or fall back to default
    api_key = request.openai_key if request.openai_key else settings.openai_api_key
    
    # Generate query embedding
    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=request.query,
    )
    query_embedding = response.data[0].embedding
    
    # Calculate cost
    query_cost = None
    if response.usage:
        input_tokens = response.usage.total_tokens
        cost_usd = calculate_cost(settings.openai_embedding_model, input_tokens, 0)
        query_cost = QueryCost(
            model=settings.openai_embedding_model,
            input_tokens=input_tokens,
            output_tokens=0,
            cost_usd=f"{cost_usd:.8f}",
        )
        
        # Record cost transaction (only if using default key)
        if not request.openai_key:
            try:
                await record_cost_sync(
                    cost_type="RAG_QUERY",
                    model=settings.openai_embedding_model,
                    input_tokens=input_tokens,
                    output_tokens=0,
                    document_id=str(request.document_id),
                    description=f"Search query: {request.query[:50]}...",
                )
            except Exception as e:
                logger.warning(f"Failed to record search cost: {e}")

    # Search in Qdrant
    qdrant = QdrantStorage()
    search_results = qdrant.search(
        query_vector=query_embedding,
        document_id=request.document_id,
        chapter_ids=request.chapter_ids,
        limit=request.limit,
    )

    # Build response
    results = []
    for point in search_results:
        payload = point.payload or {}

        # Get chapter title from database
        chapter_title = "Unknown Chapter"
        chapter_id_str = payload.get("chapter_id")
        chapter_uuid = None

        if chapter_id_str:
            try:
                chapter_uuid = uuid.UUID(chapter_id_str)
                async with get_db_session() as session:
                    storage = PostgresStorage(session)
                    chapter = await storage.get_chapter(chapter_uuid)
                    if chapter:
                        chapter_title = chapter.title
            except (ValueError, TypeError):
                pass

        # Use vector_id from payload or generate a new one
        chunk_id_str = payload.get("vector_id") or str(point.id)
        try:
            chunk_uuid = uuid.UUID(chunk_id_str)
        except (ValueError, TypeError):
            chunk_uuid = uuid.uuid4()

        results.append(
            SearchResult(
                chunk_id=chunk_uuid,
                chapter_id=chapter_uuid or uuid.uuid4(),
                chapter_title=chapter_title,
                content=payload.get("content", ""),
                score=point.score,
                page_range=(
                    payload.get("start_page", 0),
                    payload.get("end_page", 0),
                ),
                section_title=payload.get("section_title"),
                chunk_type=payload.get("chunk_type", "TEXT"),
            )
        )

    logger.info(
        "Search completed",
        document_id=str(request.document_id),
        query=request.query[:50],
        results_count=len(results),
    )

    return SearchResponse(
        document_id=request.document_id,
        query=request.query,
        total_results=len(results),
        results=results,
        cost=query_cost,
    )
