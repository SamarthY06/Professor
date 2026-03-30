"""Qdrant vector storage layer."""
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config.settings import settings
from app.config.logging import get_logger

logger = get_logger(__name__)

# Embedding dimension for text-embedding-3-small
EMBEDDING_DIMENSION = 1536


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client instance."""
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )


class QdrantStorage:
    """Qdrant vector storage operations."""

    def __init__(self, client: Optional[QdrantClient] = None) -> None:
        """Initialize with Qdrant client."""
        self.client = client or get_qdrant_client()
        self.collection_name = settings.qdrant_collection_name

    async def init_collection(self) -> None:
        """Initialize the vector collection if it doesn't exist."""
        collections = self.client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if self.collection_name not in collection_names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            # Create payload indexes for filtering
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="document_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="chapter_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
            logger.info(
                "Created Qdrant collection",
                collection_name=self.collection_name,
            )
        else:
            logger.info(
                "Qdrant collection already exists",
                collection_name=self.collection_name,
            )

    def upsert_vectors(
        self,
        vectors: list[tuple[str, list[float], dict]],
    ) -> None:
        """
        Upsert vectors to Qdrant.

        Args:
            vectors: List of (vector_id, embedding, payload) tuples
        """
        if not vectors:
            return

        points = [
            PointStruct(
                id=vector_id,
                vector=embedding,
                payload=payload,
            )
            for vector_id, embedding, payload in vectors
        ]

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        logger.info("Upserted vectors", count=len(vectors))

    def search(
        self,
        query_vector: list[float],
        document_id: uuid.UUID,
        chapter_ids: Optional[list[uuid.UUID]] = None,
        limit: int = 10,
    ) -> list[models.ScoredPoint]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query embedding
            document_id: Document ID to filter by
            chapter_ids: Optional list of chapter IDs to filter by
            limit: Maximum number of results

        Returns:
            List of scored points
        """
        # Build filter conditions
        must_conditions = [
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=str(document_id)),
            )
        ]

        if chapter_ids:
            must_conditions.append(
                models.FieldCondition(
                    key="chapter_id",
                    match=models.MatchAny(any=[str(cid) for cid in chapter_ids]),
                )
            )

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=models.Filter(must=must_conditions),
            limit=limit,
            with_payload=True,
        )

        logger.info(
            "Vector search completed",
            document_id=str(document_id),
            results_count=len(results),
        )
        return results

    def delete_by_document(self, document_id: uuid.UUID) -> None:
        """Delete all vectors for a document."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=str(document_id)),
                        )
                    ]
                )
            ),
        )
        logger.info("Deleted vectors for document", document_id=str(document_id))

    def delete_by_chapter(self, chapter_id: uuid.UUID) -> None:
        """Delete all vectors for a chapter."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="chapter_id",
                            match=models.MatchValue(value=str(chapter_id)),
                        )
                    ]
                )
            ),
        )
        logger.info("Deleted vectors for chapter", chapter_id=str(chapter_id))

    def get_collection_info(self) -> Optional[models.CollectionInfo]:
        """Get collection information."""
        try:
            return self.client.get_collection(self.collection_name)
        except Exception:
            return None
