"""API routes."""
from app.api.documents import router as documents_router
from app.api.chapters import router as chapters_router
from app.api.search import router as search_router
from app.api.progress import router as progress_router

__all__ = [
    "documents_router",
    "chapters_router",
    "search_router",
    "progress_router",
]
