"""Embedding generation activities."""
import uuid
from typing import Optional

from openai import OpenAI
from temporalio import activity

from app.config.settings import settings
from app.config.logging import get_logger
from app.activities.cost_tracking import record_cost_sync

logger = get_logger(__name__)


@activity.defn
async def generate_embeddings(
    chunks: list[dict],
    document_id: str,
    chapter_id: str,
) -> list[dict]:
    """
    Generate embeddings for text chunks.

    Args:
        chunks: List of chunk dictionaries with content
        document_id: Document identifier
        chapter_id: Chapter identifier

    Returns:
        List of chunks with embeddings and vector IDs
    """
    if not chunks:
        return []

    activity.logger.info(
        f"Generating embeddings for {len(chunks)} chunks, "
        f"document={document_id}, chapter={chapter_id}"
    )

    client = OpenAI(api_key=settings.openai_api_key)

    # Extract texts for batch embedding
    texts = [chunk["content"] for chunk in chunks]

    # Generate embeddings in batch
    response = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )

    # Track token usage from response
    total_tokens = response.usage.total_tokens if response.usage else 0
    
    # Record cost transaction
    try:
        await record_cost_sync(
            cost_type="EMBEDDING",
            model=settings.openai_embedding_model,
            input_tokens=total_tokens,
            output_tokens=0,
            document_id=document_id,
            description=f"Embedding generation for {len(chunks)} chunks in chapter {chapter_id}",
            metadata={
                "chapter_id": chapter_id,
                "chunk_count": len(chunks),
            },
        )
    except Exception as e:
        activity.logger.warning(f"Failed to record cost: {e}")

    # Attach embeddings and metadata to chunks
    for i, chunk in enumerate(chunks):
        vector_id = str(uuid.uuid4())
        chunk["embedding"] = response.data[i].embedding
        chunk["vector_id"] = vector_id
        chunk["document_id"] = document_id
        chunk["chapter_id"] = chapter_id

    activity.logger.info(f"Generated {len(chunks)} embeddings, tokens used: {total_tokens}")
    return chunks


@activity.defn
async def generate_query_embedding(
    query: str,
    user_id: Optional[str] = None,
) -> list[float]:
    """
    Generate embedding for a search query.

    Args:
        query: Search query text
        user_id: Optional user ID for cost tracking

    Returns:
        Query embedding vector
    """
    activity.logger.info(f"Generating query embedding for: {query[:50]}...")

    client = OpenAI(api_key=settings.openai_api_key)

    response = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=query,
    )

    # Track token usage
    total_tokens = response.usage.total_tokens if response.usage else 0
    
    # Record cost transaction
    try:
        await record_cost_sync(
            cost_type="RAG_QUERY",
            model=settings.openai_embedding_model,
            input_tokens=total_tokens,
            output_tokens=0,
            user_id=user_id,
            description=f"Query embedding: {query[:50]}...",
        )
    except Exception as e:
        activity.logger.warning(f"Failed to record cost: {e}")

    return response.data[0].embedding


def prepare_vectors_for_qdrant(
    chunks: list[dict],
) -> list[tuple[str, list[float], dict]]:
    """
    Prepare chunk data for Qdrant upsert.

    Args:
        chunks: List of chunks with embeddings

    Returns:
        List of (vector_id, embedding, payload) tuples
    """
    vectors = []

    for chunk in chunks:
        if "embedding" not in chunk or "vector_id" not in chunk:
            continue

        payload = {
            "document_id": chunk["document_id"],
            "chapter_id": chunk["chapter_id"],
            "chunk_index": chunk["chunk_index"],
            "content": chunk["content"],
            "token_count": chunk["token_count"],
            "start_page": chunk["start_page"],
            "end_page": chunk["end_page"],
            "section_title": chunk.get("section_title"),
            "chunk_type": chunk.get("chunk_type", "TEXT"),
        }

        # Include image summaries if present
        if "image_summaries" in chunk:
            payload["image_summaries"] = chunk["image_summaries"]

        vectors.append((
            chunk["vector_id"],
            chunk["embedding"],
            payload,
        ))

    return vectors
