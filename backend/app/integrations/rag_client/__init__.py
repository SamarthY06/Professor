"""RAG Client integration package.

This package provides a strict API wrapper for the external RAG service.
ProfessorOS delegates all document intelligence operations to this service.
"""

from app.integrations.rag_client.client import RAGClient, get_rag_client
from app.integrations.rag_client.models import (
    DocumentUploadResponse,
    DocumentProgressResponse,
    DocumentTOCResponse,
    ChapterInfo,
    SearchRequest,
    SearchResponse,
    SearchResult,
    IngestionStatus,
)
from app.integrations.rag_client.exceptions import (
    RAGClientError,
    RAGAuthenticationError,
    RAGConnectionError,
    RAGTimeoutError,
    RAGNotFoundError,
    RAGValidationError,
    RAGServiceUnavailableError,
)

__all__ = [
    # Client
    "RAGClient",
    "get_rag_client",
    # Models
    "DocumentUploadResponse",
    "DocumentProgressResponse",
    "DocumentTOCResponse",
    "ChapterInfo",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "IngestionStatus",
    # Exceptions
    "RAGClientError",
    "RAGAuthenticationError",
    "RAGConnectionError",
    "RAGTimeoutError",
    "RAGNotFoundError",
    "RAGValidationError",
    "RAGServiceUnavailableError",
]
