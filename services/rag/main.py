"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.config.logging import configure_logging, get_logger
from app.storage.postgres import init_db, close_db
from app.storage.qdrant import QdrantStorage
from app.api import (
    documents_router,
    chapters_router,
    search_router,
    progress_router,
)
from app.api.auth import router as auth_router
from app.api.costs import router as costs_router

# Configure logging
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    logger.info("Starting application", app_name=settings.app_name)

    # Initialize database
    await init_db()

    # Initialize Qdrant collection
    try:
        qdrant = QdrantStorage()
        await qdrant.init_collection()
    except Exception as e:
        logger.warning(f"Could not initialize Qdrant: {e}")

    # Ensure directories exist
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)

    yield

    # Cleanup
    await close_db()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Document Intelligence & RAG Service",
    description="Production-grade document processing and retrieval-augmented generation service",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chapters_router)
app.include_router(search_router)
app.include_router(progress_router)
app.include_router(costs_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "service": "Document Intelligence & RAG Service",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
