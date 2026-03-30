"""Temporal worker for document processing."""
import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app.config.settings import settings
from app.config.logging import configure_logging, get_logger
from app.workflows.document_ingestion import DocumentIngestionWorkflow
from app.workflows.chapter_ingestion import ChapterIngestionWorkflow
from app.activities.toc_detection import extract_first_pages, detect_toc
from app.activities.pdf_extraction import extract_text_and_images, extract_chapter_pages
from app.activities.image_summarization import summarize_image, summarize_images_batch
from app.activities.chunking import chunk_text
from app.activities.embedding import generate_embeddings, generate_query_embedding
from app.activities.storage_activities import (
    persist_toc_and_chapters,
    update_chapter_processing_status,
    persist_chunks_and_vectors,
    update_document_completion,
    increment_document_progress,
    set_document_pages,
)

# Configure logging
configure_logging()
logger = get_logger(__name__)


async def run_worker() -> None:
    """Run the Temporal worker."""
    logger.info(
        "Starting Temporal worker",
        temporal_address=settings.temporal_address,
        task_queue=settings.temporal_task_queue,
    )

    # Connect to Temporal
    client = await Client.connect(settings.temporal_address)

    # Create worker with workflows and activities
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[
            DocumentIngestionWorkflow,
            ChapterIngestionWorkflow,
        ],
        activities=[
            # TOC and extraction
            extract_first_pages,
            detect_toc,
            extract_text_and_images,
            extract_chapter_pages,
            # Image processing
            summarize_image,
            summarize_images_batch,
            # Chunking and embedding
            chunk_text,
            generate_embeddings,
            generate_query_embedding,
            # Storage operations
            persist_toc_and_chapters,
            update_chapter_processing_status,
            persist_chunks_and_vectors,
            update_document_completion,
            increment_document_progress,
            set_document_pages,
        ],
        max_concurrent_activities=settings.max_concurrent_chapters,
    )

    logger.info("Worker started, waiting for tasks...")

    # Run worker
    await worker.run()


def main() -> None:
    """Main entry point for worker."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
