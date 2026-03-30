"""Chapter ingestion workflow."""
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

# Maximum pages per sub-batch to avoid Temporal payload size limits
MAX_PAGES_PER_BATCH = 50

with workflow.unsafe.imports_passed_through():
    from app.activities.pdf_extraction import extract_text_and_images
    from app.activities.chunking import chunk_text, merge_image_summaries_with_chunks
    from app.activities.embedding import generate_embeddings
    from app.activities.storage_activities import (
        update_chapter_processing_status,
        persist_chunks_and_vectors,
        increment_document_progress,
    )


@dataclass
class ChapterIngestionInput:
    """Input for chapter ingestion workflow."""

    document_id: str
    chapter_id: str
    pdf_path: str
    chapter_number: int
    title: str
    start_page: int
    end_page: int


@dataclass
class ChapterIngestionResult:
    """Result of chapter ingestion workflow."""

    chapter_id: str
    success: bool
    chunk_count: int
    image_count: int
    error: Optional[str] = None


@workflow.defn
class ChapterIngestionWorkflow:
    """
    Workflow for processing a single chapter.

    Steps:
    1. Mark chapter as processing
    2. Split large chapters into sub-batches (max 50 pages each)
    3. For each sub-batch:
       a. Extract text and images from pages
       b. Chunk text into appropriate sizes
       c. Generate embeddings
       d. Persist chunks and vectors
    4. Mark chapter as completed

    Note: Image summarization is skipped to avoid Temporal payload size limits.
    Images are tracked but not processed through vision API in this version.
    """

    def _get_page_batches(
        self, start_page: int, end_page: int
    ) -> list[tuple[int, int]]:
        """
        Split page range into sub-batches to avoid Temporal payload size limits.
        
        Args:
            start_page: Start page (1-indexed)
            end_page: End page (1-indexed, inclusive)
            
        Returns:
            List of (batch_start, batch_end) tuples
        """
        batches = []
        current_start = start_page
        
        while current_start <= end_page:
            batch_end = min(current_start + MAX_PAGES_PER_BATCH - 1, end_page)
            batches.append((current_start, batch_end))
            current_start = batch_end + 1
            
        return batches

    @workflow.run
    async def run(self, input: ChapterIngestionInput) -> ChapterIngestionResult:
        """Execute chapter ingestion workflow."""
        total_pages = input.end_page - input.start_page + 1
        batches = self._get_page_batches(input.start_page, input.end_page)
        
        workflow.logger.info(
            f"Starting chapter ingestion: {input.title} "
            f"(pages {input.start_page}-{input.end_page}, {total_pages} pages, "
            f"{len(batches)} batch(es))"
        )

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )

        try:
            # Mark chapter as processing
            await workflow.execute_activity(
                update_chapter_processing_status,
                args=[input.chapter_id, "PROCESSING"],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )

            total_chunk_count = 0
            total_image_count = 0
            
            # Process each sub-batch
            for batch_idx, (batch_start, batch_end) in enumerate(batches):
                workflow.logger.info(
                    f"Processing batch {batch_idx + 1}/{len(batches)}: "
                    f"pages {batch_start}-{batch_end}"
                )
                
                # Step 1: Extract text and images for this batch
                extraction_result = await workflow.execute_activity(
                    extract_text_and_images,
                    args=[
                        input.pdf_path,
                        input.chapter_id,
                        batch_start,
                        batch_end,
                    ],
                    start_to_close_timeout=timedelta(minutes=10),
                    retry_policy=retry_policy,
                )

                text_blocks = extraction_result["text_blocks"]
                images = extraction_result["images"]
                total_image_count += len(images)

                workflow.logger.info(
                    f"Batch {batch_idx + 1}: Extracted {len(text_blocks)} text blocks "
                    f"and {len(images)} images"
                )

                # Step 2: Chunk text
                if text_blocks:
                    chunks = await workflow.execute_activity(
                        chunk_text,
                        args=[text_blocks, input.chapter_id],
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=retry_policy,
                    )

                    workflow.logger.info(
                        f"Batch {batch_idx + 1}: Created {len(chunks)} text chunks"
                    )

                    # Step 3: Generate embeddings
                    if chunks:
                        chunks_with_embeddings = await workflow.execute_activity(
                            generate_embeddings,
                            args=[chunks, input.document_id, input.chapter_id],
                            start_to_close_timeout=timedelta(minutes=10),
                            retry_policy=retry_policy,
                        )

                        # Step 4: Persist chunks and vectors
                        batch_chunk_count = await workflow.execute_activity(
                            persist_chunks_and_vectors,
                            args=[input.document_id, input.chapter_id, chunks_with_embeddings],
                            start_to_close_timeout=timedelta(minutes=5),
                            retry_policy=retry_policy,
                        )

                        total_chunk_count += batch_chunk_count
                        workflow.logger.info(
                            f"Batch {batch_idx + 1}: Persisted {batch_chunk_count} chunks"
                        )

            # Step 5: Mark chapter as completed
            await workflow.execute_activity(
                update_chapter_processing_status,
                args=[
                    input.chapter_id,
                    "COMPLETED",
                    None,
                    total_chunk_count,
                    total_image_count,
                ],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )

            # Increment document progress
            await workflow.execute_activity(
                increment_document_progress,
                args=[input.document_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )

            workflow.logger.info(
                f"Chapter completed: {total_chunk_count} total chunks, "
                f"{total_image_count} total images"
            )

            return ChapterIngestionResult(
                chapter_id=input.chapter_id,
                success=True,
                chunk_count=total_chunk_count,
                image_count=total_image_count,
            )

        except Exception as e:
            workflow.logger.error(f"Chapter ingestion failed: {e}")

            # Mark chapter as failed
            try:
                await workflow.execute_activity(
                    update_chapter_processing_status,
                    args=[input.chapter_id, "FAILED", str(e)],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )
            except Exception:
                pass

            return ChapterIngestionResult(
                chapter_id=input.chapter_id,
                success=False,
                chunk_count=0,
                image_count=0,
                error=str(e),
            )
