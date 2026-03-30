"""Document ingestion workflow."""
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.activities.toc_detection import extract_first_pages, detect_toc
    from app.activities.pdf_extraction import get_pdf_page_count
    from app.activities.storage_activities import (
        persist_toc_and_chapters,
        update_document_completion,
        set_document_pages,
    )
    from app.workflows.chapter_ingestion import (
        ChapterIngestionWorkflow,
        ChapterIngestionInput,
        ChapterIngestionResult,
    )
    from app.config.settings import settings


@dataclass
class DocumentIngestionInput:
    """Input for document ingestion workflow."""

    document_id: str
    pdf_path: str
    filename: str


@dataclass
class DocumentIngestionResult:
    """Result of document ingestion workflow."""

    document_id: str
    success: bool
    total_chapters: int
    completed_chapters: int
    failed_chapters: int
    error: Optional[str] = None


@dataclass
class ChapterInfo:
    """Chapter information from TOC."""

    chapter_id: str
    chapter_number: int
    title: str
    start_page: int
    end_page: int


@workflow.defn
class DocumentIngestionWorkflow:
    """
    Main workflow for document ingestion.

    Steps:
    1. Extract first 10-20 pages
    2. Detect and parse TOC
    3. Persist TOC and create chapter records
    4. Process chapters in batches
    5. Track completion
    """

    def __init__(self) -> None:
        self._chapters: list[ChapterInfo] = []
        self._completed_chapters: int = 0
        self._failed_chapters: int = 0
        self._current_phase: str = "UPLOAD"
        self._error: Optional[str] = None

    @workflow.run
    async def run(self, input: DocumentIngestionInput) -> DocumentIngestionResult:
        """Execute document ingestion workflow."""
        workflow.logger.info(f"Starting document ingestion: {input.filename}")

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )

        try:
            # Get total pages
            total_pages = get_pdf_page_count(input.pdf_path)
            workflow.logger.info(f"Document has {total_pages} pages")

            # Set document pages
            await workflow.execute_activity(
                set_document_pages,
                args=[input.document_id, total_pages],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )

            # Step 1: Extract first pages for TOC detection
            self._current_phase = "TOC"
            pages_to_extract = min(settings.toc_pages_to_extract, total_pages)

            first_pages_text = await workflow.execute_activity(
                extract_first_pages,
                args=[input.pdf_path, pages_to_extract],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )

            # Step 2: Detect TOC
            toc_data = await workflow.execute_activity(
                detect_toc,
                args=[input.pdf_path, first_pages_text, total_pages],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )

            workflow.logger.info(
                f"TOC detection complete: {len(toc_data.get('chapters', []))} chapters found"
            )

            # Step 3: Prepare chapter info for persistence
            chapters_to_persist = []
            for idx, chapter_data in enumerate(toc_data.get("chapters", [])):
                chapters_to_persist.append({
                    "chapter_number": idx + 1,
                    "title": chapter_data["title"],
                    "start_page": chapter_data["start_page"],
                    "end_page": chapter_data["end_page"],
                    "sections": chapter_data.get("sections", []),
                })

            if not chapters_to_persist:
                # Fallback: single chapter for entire document
                chapters_to_persist.append({
                    "chapter_number": 1,
                    "title": "Full Document",
                    "start_page": 1,
                    "end_page": total_pages,
                    "sections": [],
                })

            # Persist TOC and chapters
            chapter_ids = await workflow.execute_activity(
                persist_toc_and_chapters,
                args=[input.document_id, toc_data, chapters_to_persist],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )

            # Build chapter info list
            self._chapters = []
            for idx, chapter_id in enumerate(chapter_ids):
                chapter_data = chapters_to_persist[idx]
                self._chapters.append(
                    ChapterInfo(
                        chapter_id=chapter_id,
                        chapter_number=chapter_data["chapter_number"],
                        title=chapter_data["title"],
                        start_page=chapter_data["start_page"],
                        end_page=chapter_data["end_page"],
                    )
                )

            # Step 4: Process chapters in batches
            self._current_phase = "CHAPTER_INGESTION"
            batch_size = settings.chapter_batch_size
            max_concurrent = settings.max_concurrent_chapters

            # Create batches
            batches = [
                self._chapters[i : i + batch_size]
                for i in range(0, len(self._chapters), batch_size)
            ]

            workflow.logger.info(
                f"Processing {len(self._chapters)} chapters in {len(batches)} batches"
            )

            # Process batches sequentially, chapters within batch in parallel
            for batch_idx, batch in enumerate(batches):
                workflow.logger.info(
                    f"Processing batch {batch_idx + 1}/{len(batches)} "
                    f"({len(batch)} chapters)"
                )

                # Start child workflows for chapters in this batch
                chapter_handles = []
                for chapter in batch:
                    chapter_input = ChapterIngestionInput(
                        document_id=input.document_id,
                        chapter_id=chapter.chapter_id,
                        pdf_path=input.pdf_path,
                        chapter_number=chapter.chapter_number,
                        title=chapter.title,
                        start_page=chapter.start_page,
                        end_page=chapter.end_page,
                    )

                    handle = await workflow.start_child_workflow(
                        ChapterIngestionWorkflow.run,
                        chapter_input,
                        id=f"chapter-{chapter.chapter_id}",
                        task_queue=settings.temporal_task_queue,
                    )
                    chapter_handles.append((chapter, handle))

                # Wait for all chapters in batch to complete
                for chapter, handle in chapter_handles:
                    try:
                        result: ChapterIngestionResult = await handle
                        if result.success:
                            self._completed_chapters += 1
                            workflow.logger.info(
                                f"Chapter '{chapter.title}' completed: "
                                f"{result.chunk_count} chunks, {result.image_count} images"
                            )
                        else:
                            self._failed_chapters += 1
                            workflow.logger.error(
                                f"Chapter '{chapter.title}' failed: {result.error}"
                            )
                    except Exception as e:
                        self._failed_chapters += 1
                        workflow.logger.error(
                            f"Chapter '{chapter.title}' workflow error: {e}"
                        )

                workflow.logger.info(
                    f"Batch {batch_idx + 1} complete: "
                    f"{self._completed_chapters}/{len(self._chapters)} chapters done"
                )

            # Step 5: Mark completion
            self._current_phase = "COMPLETED"

            success = self._failed_chapters == 0
            error_msg = None
            if self._failed_chapters > 0:
                error_msg = f"{self._failed_chapters} chapters failed to process"
                if self._completed_chapters > 0:
                    workflow.logger.warning(
                        f"Document ingestion partially complete: "
                        f"{self._completed_chapters} succeeded, {self._failed_chapters} failed"
                    )

            # Update document completion status
            await workflow.execute_activity(
                update_document_completion,
                args=[input.document_id, success, error_msg],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )

            return DocumentIngestionResult(
                document_id=input.document_id,
                success=success,
                total_chapters=len(self._chapters),
                completed_chapters=self._completed_chapters,
                failed_chapters=self._failed_chapters,
            )

        except Exception as e:
            self._error = str(e)
            workflow.logger.error(f"Document ingestion failed: {e}")

            # Update document as failed
            try:
                await workflow.execute_activity(
                    update_document_completion,
                    args=[input.document_id, False, str(e)],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )
            except Exception:
                pass

            return DocumentIngestionResult(
                document_id=input.document_id,
                success=False,
                total_chapters=len(self._chapters),
                completed_chapters=self._completed_chapters,
                failed_chapters=self._failed_chapters,
                error=str(e),
            )

    @workflow.query
    def get_progress(self) -> dict:
        """Query current progress."""
        return {
            "total_chapters": len(self._chapters),
            "completed_chapters": self._completed_chapters,
            "failed_chapters": self._failed_chapters,
            "current_phase": self._current_phase,
            "error": self._error,
        }

    @workflow.query
    def get_chapters(self) -> list[dict]:
        """Query chapter information."""
        return [
            {
                "chapter_id": c.chapter_id,
                "chapter_number": c.chapter_number,
                "title": c.title,
                "start_page": c.start_page,
                "end_page": c.end_page,
            }
            for c in self._chapters
        ]
