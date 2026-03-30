"""RAG Client - Strict API wrapper for external RAG service.

This client handles all communication with the external RAG service.
It is responsible for:
- Authentication and token management
- HTTP request handling with retries
- Response parsing and validation
- Error handling and logging

IMPORTANT: This client contains NO business logic.
All document intelligence is delegated to the external RAG service.
"""

import asyncio
import time
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union

import httpx
from fastapi import UploadFile

from app.config.rag import RAGConfig, get_rag_config
from app.logs.logger import get_logger
from app.integrations.rag_client.exceptions import (
    RAGAuthenticationError,
    RAGClientError,
    RAGConnectionError,
    RAGNotFoundError,
    RAGServiceUnavailableError,
    RAGTimeoutError,
    RAGValidationError,
)
from app.integrations.rag_client.models import (
    AuthTokenResponse,
    ChapterInfo,
    ChapterListResponse,
    DocumentProgressResponse,
    DocumentTOCResponse,
    DocumentUploadResponse,
    IngestionStatus,
    SearchRequest,
    SearchResponse,
)

logger = get_logger(__name__)


class RAGClient:
    """
    Async HTTP client for the external RAG service.
    
    This client provides a clean interface to all RAG service endpoints.
    It handles authentication, retries, timeouts, and error handling.
    
    Usage:
        async with RAGClient() as client:
            doc = await client.upload_document(file)
            progress = await client.get_document_progress(doc.document_id)
    
    Or use the singleton:
        client = get_rag_client()
        doc = await client.upload_document(file)
    """
    
    def __init__(self, config: Optional[RAGConfig] = None):
        """
        Initialize the RAG client.
        
        Args:
            config: RAG configuration. Uses default if not provided.
        """
        self.config = config or get_rag_config()
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()
    
    async def __aenter__(self) -> "RAGClient":
        """Async context manager entry."""
        await self._ensure_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.rag_request_timeout),
                limits=httpx.Limits(
                    max_connections=self.config.rag_max_connections,
                    max_keepalive_connections=self.config.rag_max_connections // 2,
                    keepalive_expiry=self.config.rag_keepalive_expiry,
                ),
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    # =========================================================================
    # Authentication
    # =========================================================================
    
    async def _ensure_authenticated(self) -> str:
        """
        Ensure we have a valid authentication token.
        
        Returns:
            Valid JWT token
        
        Raises:
            RAGAuthenticationError: If authentication fails
        """
        async with self._lock:
            # Check if token is still valid
            if self._token and self._token_expires_at:
                buffer = timedelta(seconds=self.config.rag_token_refresh_buffer_seconds)
                if datetime.utcnow() + buffer < self._token_expires_at:
                    return self._token
            
            # Need to authenticate
            return await self._authenticate()
    
    async def _authenticate(self) -> str:
        """
        Authenticate with the RAG service.
        
        Returns:
            JWT token
        
        Raises:
            RAGAuthenticationError: If authentication fails
        """
        client = await self._ensure_client()
        
        try:
            response = await client.post(
                self.config.auth_url,
                json={
                    "username": self.config.rag_admin_username,
                    "password": self.config.rag_admin_password,
                },
            )
            
            if response.status_code == 401:
                raise RAGAuthenticationError(
                    "Invalid credentials for RAG service",
                    response_body=response.text,
                )
            
            response.raise_for_status()
            
            data = response.json()
            token_response = AuthTokenResponse(**data)
            
            self._token = token_response.access_token
            
            # Calculate expiry
            if token_response.expires_at:
                self._token_expires_at = token_response.expires_at
            elif token_response.expires_in:
                self._token_expires_at = datetime.utcnow() + timedelta(
                    seconds=token_response.expires_in
                )
            else:
                # Default to 1 hour if not specified
                self._token_expires_at = datetime.utcnow() + timedelta(hours=1)
            
            logger.info(
                "rag_authentication_success",
                expires_at=self._token_expires_at.isoformat(),
            )
            
            return self._token
            
        except httpx.ConnectError as e:
            raise RAGConnectionError(
                f"Failed to connect to RAG service at {self.config.auth_url}",
                original_error=e,
            )
        except httpx.TimeoutException as e:
            raise RAGTimeoutError(
                "Authentication request timed out",
                timeout_seconds=self.config.rag_request_timeout,
            )
        except RAGAuthenticationError:
            raise
        except Exception as e:
            logger.exception("rag_authentication_failed", error=str(e))
            raise RAGAuthenticationError(f"Authentication failed: {str(e)}")
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authorization headers."""
        if not self._token:
            raise RAGAuthenticationError("Not authenticated")
        return {"Authorization": f"Bearer {self._token}"}
    
    # =========================================================================
    # Request Helpers
    # =========================================================================
    
    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        document_id: Optional[str] = None,
        chapter_id: Optional[str] = None,
        retry_count: int = 0,
    ) -> httpx.Response:
        """
        Make an authenticated request to the RAG service.
        
        Args:
            method: HTTP method
            url: Request URL
            json: JSON body
            data: Form data
            files: Files to upload
            params: Query parameters
            user_id: User ID for logging
            document_id: Document ID for logging
            chapter_id: Chapter ID for logging
            retry_count: Current retry attempt
        
        Returns:
            HTTP response
        
        Raises:
            RAGClientError: On request failure
        """
        start_time = time.time()
        client = await self._ensure_client()
        token = await self._ensure_authenticated()
        
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            response = await client.request(
                method=method,
                url=url,
                json=json,
                data=data,
                files=files,
                params=params,
                headers=headers,
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Log the request
            logger.info(
                "rag_api_request",
                method=method,
                url=url,
                status_code=response.status_code,
                latency_ms=round(latency_ms, 2),
                user_id=user_id,
                document_id=document_id,
                chapter_id=chapter_id,
            )
            
            # Handle errors
            if response.status_code == 401:
                # Token expired, re-authenticate and retry
                if retry_count < 1:
                    self._token = None
                    return await self._request(
                        method, url,
                        json=json, data=data, files=files, params=params,
                        user_id=user_id, document_id=document_id, chapter_id=chapter_id,
                        retry_count=retry_count + 1,
                    )
                raise RAGAuthenticationError(
                    "Authentication failed after retry",
                    response_body=response.text,
                )
            
            if response.status_code == 404:
                raise RAGNotFoundError(
                    f"Resource not found: {url}",
                    document_id=document_id,
                    chapter_id=chapter_id,
                )
            
            if response.status_code == 422:
                raise RAGValidationError(
                    "Request validation failed",
                    validation_errors=response.json().get("detail", []),
                )
            
            if response.status_code == 503:
                retry_after = response.headers.get("Retry-After")
                raise RAGServiceUnavailableError(
                    "RAG service is temporarily unavailable",
                    retry_after=int(retry_after) if retry_after else None,
                )
            
            if response.status_code >= 500:
                # Retry on server errors
                if retry_count < self.config.rag_max_retries:
                    await asyncio.sleep(
                        self.config.rag_retry_delay_seconds * (2 ** retry_count)
                    )
                    return await self._request(
                        method, url,
                        json=json, data=data, files=files, params=params,
                        user_id=user_id, document_id=document_id, chapter_id=chapter_id,
                        retry_count=retry_count + 1,
                    )
                raise RAGClientError(
                    f"Server error: {response.status_code}",
                    status_code=response.status_code,
                    response_body=response.text,
                    document_id=document_id,
                )
            
            response.raise_for_status()
            return response
            
        except httpx.ConnectError as e:
            raise RAGConnectionError(
                f"Failed to connect to RAG service: {url}",
                original_error=e,
            )
        except httpx.TimeoutException:
            raise RAGTimeoutError(
                f"Request timed out: {url}",
                timeout_seconds=self.config.rag_request_timeout,
                document_id=document_id,
            )
        except (RAGClientError, RAGAuthenticationError, RAGNotFoundError,
                RAGValidationError, RAGServiceUnavailableError):
            raise
        except Exception as e:
            logger.exception(
                "rag_request_failed",
                method=method,
                url=url,
                error=str(e),
                document_id=document_id,
            )
            raise RAGClientError(f"Request failed: {str(e)}", document_id=document_id)
    
    # =========================================================================
    # Document Operations
    # =========================================================================
    
    async def upload_document(
        self,
        file: UploadFile,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        openai_key: Optional[str] = None,
    ) -> DocumentUploadResponse:
        """
        Upload a document to the RAG service.
        
        Args:
            file: The file to upload
            user_id: User ID for tracking
            metadata: Optional metadata to attach
            openai_key: Custom OpenAI API key for BYOK users
        
        Returns:
            DocumentUploadResponse with document_id
        
        Raises:
            RAGClientError: On upload failure
        """
        # Read file content
        content = await file.read()
        await file.seek(0)  # Reset for potential re-read
        
        files = {
            "file": (file.filename, content, file.content_type or "application/pdf")
        }
        
        # Add openai_key as form data if provided
        data = {}
        if openai_key:
            data["openai_key"] = openai_key
        
        response = await self._request(
            "POST",
            f"{self.config.documents_url}/upload",
            files=files,
            data=data if data else None,
            user_id=user_id,
        )
        
        return DocumentUploadResponse(**response.json())
    
    async def get_document_progress(
        self,
        document_id: str,
        user_id: Optional[str] = None,
    ) -> DocumentProgressResponse:
        """
        Get document ingestion progress.
        
        Args:
            document_id: Document identifier
            user_id: User ID for tracking
        
        Returns:
            DocumentProgressResponse with current status
        
        Raises:
            RAGNotFoundError: If document not found
            RAGClientError: On request failure
        """
        response = await self._request(
            "GET",
            self.config.get_document_progress_url(document_id),
            user_id=user_id,
            document_id=document_id,
        )
        
        return DocumentProgressResponse(**response.json())
    
    async def get_document_toc(
        self,
        document_id: str,
        user_id: Optional[str] = None,
    ) -> DocumentTOCResponse:
        """
        Get document table of contents.
        
        Args:
            document_id: Document identifier
            user_id: User ID for tracking
        
        Returns:
            DocumentTOCResponse with chapters
        
        Raises:
            RAGNotFoundError: If document not found
            RAGClientError: On request failure
        """
        response = await self._request(
            "GET",
            self.config.get_document_toc_url(document_id),
            user_id=user_id,
            document_id=document_id,
        )
        
        return DocumentTOCResponse(**response.json())
    
    async def list_chapters(
        self,
        document_id: str,
        user_id: Optional[str] = None,
    ) -> List[ChapterInfo]:
        """
        List all chapters in a document.
        
        Args:
            document_id: Document identifier
            user_id: User ID for tracking
        
        Returns:
            List of ChapterInfo objects
        
        Raises:
            RAGNotFoundError: If document not found
            RAGClientError: On request failure
        """
        response = await self._request(
            "GET",
            self.config.get_document_chapters_url(document_id),
            user_id=user_id,
            document_id=document_id,
        )
        
        data = response.json()
        chapter_list = ChapterListResponse(**data)
        return chapter_list.get_chapter_infos()
    
    async def get_chapter(
        self,
        document_id: str,
        chapter_id: str,
        user_id: Optional[str] = None,
    ) -> ChapterInfo:
        """
        Get details for a specific chapter.
        
        Args:
            document_id: Document identifier
            chapter_id: Chapter identifier
            user_id: User ID for tracking
        
        Returns:
            ChapterInfo object
        
        Raises:
            RAGNotFoundError: If chapter not found
            RAGClientError: On request failure
        """
        response = await self._request(
            "GET",
            f"{self.config.get_document_chapters_url(document_id)}/{chapter_id}",
            user_id=user_id,
            document_id=document_id,
            chapter_id=chapter_id,
        )
        
        return ChapterInfo(**response.json())
    
    # =========================================================================
    # Search Operations
    # =========================================================================
    
    async def search(
        self,
        query: str,
        document_id: str,
        chapter_ids: Optional[List[str]] = None,
        limit: int = 8,
        user_id: Optional[str] = None,
        min_similarity: Optional[float] = None,
        openai_key: Optional[str] = None,
    ) -> SearchResponse:
        """
        Search for relevant content in a document.
        
        Args:
            query: Search query
            document_id: Document to search
            chapter_ids: Optional list of chapter IDs to scope search
            limit: Maximum results to return
            user_id: User ID for tracking
            min_similarity: Minimum similarity threshold
            openai_key: Custom OpenAI API key for BYOK users
        
        Returns:
            SearchResponse with results and cost info
        
        Raises:
            RAGNotFoundError: If document not found
            RAGClientError: On request failure
        """
        request = SearchRequest(
            query=query,
            document_id=document_id,
            chapter_ids=chapter_ids,
            limit=limit,
            openai_key=openai_key,
        )
        
        chapter_id_for_log = chapter_ids[0] if chapter_ids and len(chapter_ids) == 1 else None
        
        response = await self._request(
            "POST",
            self.config.search_url,
            json=request.model_dump(exclude_none=True),
            user_id=user_id,
            document_id=document_id,
            chapter_id=chapter_id_for_log,
        )
        
        return SearchResponse(**response.json())
    
    async def search_chapter(
        self,
        query: str,
        document_id: str,
        chapter_id: str,
        limit: int = 8,
        user_id: Optional[str] = None,
        openai_key: Optional[str] = None,
    ) -> SearchResponse:
        """
        Search within a specific chapter.
        
        Convenience method that scopes search to a single chapter.
        
        Args:
            query: Search query
            document_id: Document identifier
            chapter_id: Chapter to search within
            limit: Maximum results
            user_id: User ID for tracking
            openai_key: Custom OpenAI API key for BYOK users
        
        Returns:
            SearchResponse with results from the chapter
        """
        return await self.search(
            query=query,
            document_id=document_id,
            chapter_ids=[chapter_id],
            limit=limit,
            user_id=user_id,
            openai_key=openai_key,
        )
    
    async def get_chapter_summary(
        self,
        document_id: str,
        chapter_id: str,
        chapter_title: str = "",
        user_id: Optional[str] = None,
        openai_key: Optional[str] = None,
    ) -> tuple[str, Optional["RAGCostInfo"]]:
        """
        Get a summary of a chapter's content by searching for key topics.
        
        Uses a targeted search query to extract main topics and concepts.
        
        Args:
            document_id: Document identifier
            chapter_id: Chapter identifier
            chapter_title: Chapter title for context
            user_id: User ID for tracking
            openai_key: Custom OpenAI API key for BYOK users
        
        Returns:
            Tuple of (summary text, cost info)
        """
        from app.integrations.rag_client.models import RAGCostInfo
        
        query = f"What are the main topics, concepts, and key points covered in this chapter{': ' + chapter_title if chapter_title else ''}? Summarize the content."
        
        response = await self.search(
            query=query,
            document_id=document_id,
            chapter_ids=[chapter_id],
            limit=5,
            user_id=user_id,
            openai_key=openai_key,
        )
        
        if not response.results:
            return f"Chapter content for {chapter_title or 'this chapter'}", response.cost
        
        # Combine top results into a summary
        content_parts = [r.content[:500] for r in response.results[:3]]
        return " | ".join(content_parts), response.cost
    
    # =========================================================================
    # Polling Helpers
    # =========================================================================
    
    async def wait_for_ingestion(
        self,
        document_id: str,
        user_id: Optional[str] = None,
        timeout_seconds: int = 600,
        poll_interval: Optional[int] = None,
        progress_callback: Optional[callable] = None,
    ) -> DocumentProgressResponse:
        """
        Wait for document ingestion to complete.
        
        Args:
            document_id: Document identifier
            user_id: User ID for tracking
            timeout_seconds: Maximum time to wait
            poll_interval: Polling interval (uses config default if not provided)
            progress_callback: Optional callback for progress updates
        
        Returns:
            Final DocumentProgressResponse
        
        Raises:
            RAGTimeoutError: If ingestion doesn't complete in time
            RAGClientError: If ingestion fails
        """
        interval = poll_interval or self.config.rag_poll_interval_seconds
        start_time = time.time()
        
        while True:
            progress = await self.get_document_progress(document_id, user_id)
            
            if progress_callback:
                await progress_callback(progress)
            
            if progress.is_complete:
                logger.info(
                    "rag_ingestion_complete",
                    document_id=document_id,
                    total_chapters=progress.total_chapters,
                    duration_seconds=round(time.time() - start_time, 2),
                )
                return progress
            
            if progress.is_failed:
                raise RAGClientError(
                    f"Document ingestion failed: {progress.error_message}",
                    document_id=document_id,
                )
            
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                raise RAGTimeoutError(
                    f"Ingestion did not complete within {timeout_seconds} seconds",
                    timeout_seconds=timeout_seconds,
                    document_id=document_id,
                )
            
            await asyncio.sleep(interval)


# =============================================================================
# Singleton Instance
# =============================================================================

_rag_client: Optional[RAGClient] = None


def get_rag_client() -> RAGClient:
    """
    Get the singleton RAG client instance.
    
    Returns:
        RAGClient instance
    """
    global _rag_client
    if _rag_client is None:
        _rag_client = RAGClient()
    return _rag_client


async def close_rag_client() -> None:
    """Close the singleton RAG client."""
    global _rag_client
    if _rag_client:
        await _rag_client.close()
        _rag_client = None
