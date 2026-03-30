"""Custom exceptions for RAG client operations.

These exceptions provide clear error handling for all RAG service interactions.
"""

from typing import Optional


class RAGClientError(Exception):
    """Base exception for all RAG client errors."""
    
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        document_id: Optional[str] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        self.document_id = document_id
        super().__init__(self.message)
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code:
            parts.append(f"status_code={self.status_code}")
        if self.document_id:
            parts.append(f"document_id={self.document_id}")
        return " | ".join(parts)


class RAGAuthenticationError(RAGClientError):
    """Raised when authentication with the RAG service fails."""
    
    def __init__(
        self,
        message: str = "Authentication with RAG service failed",
        status_code: Optional[int] = 401,
        response_body: Optional[str] = None,
    ):
        super().__init__(message, status_code, response_body)


class RAGConnectionError(RAGClientError):
    """Raised when connection to the RAG service fails."""
    
    def __init__(
        self,
        message: str = "Failed to connect to RAG service",
        original_error: Optional[Exception] = None,
    ):
        self.original_error = original_error
        super().__init__(message)


class RAGTimeoutError(RAGClientError):
    """Raised when a request to the RAG service times out."""
    
    def __init__(
        self,
        message: str = "Request to RAG service timed out",
        timeout_seconds: Optional[float] = None,
        document_id: Optional[str] = None,
    ):
        self.timeout_seconds = timeout_seconds
        super().__init__(message, document_id=document_id)


class RAGNotFoundError(RAGClientError):
    """Raised when a requested resource is not found."""
    
    def __init__(
        self,
        message: str = "Resource not found in RAG service",
        document_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
    ):
        self.chapter_id = chapter_id
        super().__init__(message, status_code=404, document_id=document_id)


class RAGValidationError(RAGClientError):
    """Raised when request validation fails."""
    
    def __init__(
        self,
        message: str = "Request validation failed",
        validation_errors: Optional[list] = None,
        status_code: int = 422,
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message, status_code=status_code)


class RAGServiceUnavailableError(RAGClientError):
    """Raised when the RAG service is unavailable."""
    
    def __init__(
        self,
        message: str = "RAG service is currently unavailable",
        retry_after: Optional[int] = None,
    ):
        self.retry_after = retry_after
        super().__init__(message, status_code=503)


class RAGIngestionError(RAGClientError):
    """Raised when document ingestion fails."""
    
    def __init__(
        self,
        message: str = "Document ingestion failed",
        document_id: Optional[str] = None,
        error_details: Optional[str] = None,
    ):
        self.error_details = error_details
        super().__init__(message, document_id=document_id)
