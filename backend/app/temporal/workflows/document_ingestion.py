"""Temporal Workflow: TrackDocumentIngestionWorkflow

This workflow manages the document ingestion lifecycle:
1. Upload document to external RAG service
2. Poll for ingestion progress
3. Update Professor DB with progress
4. Fetch and store TOC on completion
5. Trigger professor greeting

Professor never blocks waiting for ingestion - this workflow handles it asynchronously.
"""

from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.document_ingestion import (
        upload_document_to_rag,
        poll_ingestion_progress,
        update_book_progress,
        fetch_and_store_toc,
        fetch_chapter_summaries,
        mark_book_ready_for_planning,
        mark_book_ingestion_failed,
        trigger_professor_greeting,
        log_rag_processing_cost,
    )


@workflow.defn
class TrackDocumentIngestionWorkflow:
    """
    Workflow to track document ingestion in the external RAG service.
    
    This workflow:
    1. Uploads the document to RAG service
    2. Polls for ingestion progress at regular intervals
    3. Updates Professor DB with progress (for frontend polling/websocket)
    4. On completion, fetches TOC and stores chapters
    5. Triggers professor greeting
    
    The workflow is fault-tolerant and can resume from any point.
    """
    
    def __init__(self):
        self._cancelled = False
        self._current_progress = 0.0
        self._current_status = "pending"
    
    @workflow.run
    async def run(
        self,
        book_id: str,
        user_id: str,
        file_path: str,
        filename: str,
        poll_interval_seconds: int = 5,
        max_wait_seconds: int = 1800,  # 30 minutes max
    ) -> dict:
        """
        Execute the document ingestion tracking workflow.
        
        Args:
            book_id: Book ID in Professor DB
            user_id: User ID
            file_path: Path to the PDF file
            filename: Original filename
            poll_interval_seconds: How often to poll for progress
            max_wait_seconds: Maximum time to wait for ingestion
        
        Returns:
            Dict with final status and document info
        """
        workflow.logger.info(
            f"Starting document ingestion workflow for book {book_id}"
        )
        
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(minutes=1),
            backoff_coefficient=2.0,
        )
        
        try:
            # Step 1: Upload document to RAG service
            workflow.logger.info("Uploading document to RAG service")
            
            upload_result = await workflow.execute_activity(
                upload_document_to_rag,
                args=[file_path, filename, user_id, book_id, None],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=retry_policy,
            )
            
            document_id = upload_result["document_id"]
            workflow.logger.info(f"Document uploaded, RAG document_id: {document_id}")
            
            # Step 2: Poll for ingestion progress
            elapsed_seconds = 0
            
            while elapsed_seconds < max_wait_seconds and not self._cancelled:
                # Poll progress
                progress_data = await workflow.execute_activity(
                    poll_ingestion_progress,
                    args=[document_id, user_id],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                
                self._current_progress = progress_data.get("progress_percentage", 0)
                self._current_status = progress_data.get("status", "processing")
                
                # Update Professor DB with progress
                await workflow.execute_activity(
                    update_book_progress,
                    args=[book_id, progress_data],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                
                # Check if complete
                if progress_data.get("is_complete"):
                    workflow.logger.info("Ingestion completed successfully")
                    
                    # Log RAG processing cost if available
                    if progress_data.get("cost"):
                        workflow.logger.info("Logging RAG processing cost")
                        await workflow.execute_activity(
                            log_rag_processing_cost,
                            args=[book_id, user_id, document_id, progress_data["cost"]],
                            start_to_close_timeout=timedelta(minutes=2),
                            retry_policy=retry_policy,
                        )
                    
                    break
                
                # Check if failed
                if progress_data.get("is_failed"):
                    error_msg = progress_data.get("error_message", "Unknown error")
                    workflow.logger.error(f"Ingestion failed: {error_msg}")
                    
                    await workflow.execute_activity(
                        mark_book_ingestion_failed,
                        args=[book_id, error_msg],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=retry_policy,
                    )
                    
                    return {
                        "status": "failed",
                        "book_id": book_id,
                        "document_id": document_id,
                        "error": error_msg,
                    }
                
                # Wait before next poll
                await workflow.sleep(timedelta(seconds=poll_interval_seconds))
                elapsed_seconds += poll_interval_seconds
            
            # Check for timeout
            if elapsed_seconds >= max_wait_seconds:
                error_msg = f"Ingestion timed out after {max_wait_seconds} seconds"
                workflow.logger.error(error_msg)
                
                await workflow.execute_activity(
                    mark_book_ingestion_failed,
                    args=[book_id, error_msg],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                
                return {
                    "status": "timeout",
                    "book_id": book_id,
                    "document_id": document_id,
                    "error": error_msg,
                }
            
            # Check for cancellation
            if self._cancelled:
                return {
                    "status": "cancelled",
                    "book_id": book_id,
                    "document_id": document_id,
                }
            
            # Step 3: Fetch and store TOC
            workflow.logger.info("Fetching TOC from RAG service")
            
            toc_result = await workflow.execute_activity(
                fetch_and_store_toc,
                args=[document_id, book_id, user_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )
            
            # Step 3.5: Fetch chapter summaries for better plan generation
            workflow.logger.info("Fetching chapter summaries from RAG service")
            
            try:
                summaries_result = await workflow.execute_activity(
                    fetch_chapter_summaries,
                    args=[document_id, book_id, user_id],
                    start_to_close_timeout=timedelta(minutes=10),  # Allow more time for parallel fetches
                    retry_policy=retry_policy,
                )
                workflow.logger.info(
                    f"Fetched summaries for {len(summaries_result.get('summaries', []))} chapters"
                )
            except Exception as e:
                # Non-fatal - continue without summaries
                workflow.logger.warning(f"Failed to fetch chapter summaries: {e}")
            
            # Step 4: Mark book as ready for planning
            await workflow.execute_activity(
                mark_book_ready_for_planning,
                args=[book_id, document_id],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            # Step 5: Trigger professor greeting
            workflow.logger.info("Triggering professor greeting")
            
            greeting_result = await workflow.execute_activity(
                trigger_professor_greeting,
                args=[book_id, user_id],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )
            
            workflow.logger.info(
                f"Document ingestion workflow completed for book {book_id}"
            )
            
            return {
                "status": "completed",
                "book_id": book_id,
                "document_id": document_id,
                "total_chapters": toc_result.get("total_chapters"),
                "session_id": greeting_result.get("session_id"),
            }
            
        except Exception as e:
            workflow.logger.exception(f"Workflow failed: {str(e)}")
            
            # Mark book as failed
            try:
                await workflow.execute_activity(
                    mark_book_ingestion_failed,
                    args=[book_id, str(e)],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
            except Exception:
                pass  # Best effort
            
            return {
                "status": "failed",
                "book_id": book_id,
                "error": str(e),
            }
    
    @workflow.signal
    def cancel_ingestion(self):
        """Signal to cancel the ingestion workflow."""
        self._cancelled = True
    
    @workflow.query
    def get_progress(self) -> dict:
        """Query current progress."""
        return {
            "progress_percentage": self._current_progress,
            "status": self._current_status,
        }


@workflow.defn
class ResumeIngestionTrackingWorkflow:
    """
    Workflow to resume tracking an already-uploaded document.
    
    Use this when Professor restarts and needs to resume tracking
    a document that was already uploaded to RAG.
    """
    
    @workflow.run
    async def run(
        self,
        book_id: str,
        document_id: str,
        user_id: str,
        poll_interval_seconds: int = 5,
        max_wait_seconds: int = 1800,
    ) -> dict:
        """
        Resume tracking an existing document ingestion.
        
        Args:
            book_id: Book ID in Professor DB
            document_id: RAG document ID
            user_id: User ID
            poll_interval_seconds: Polling interval
            max_wait_seconds: Maximum wait time
        
        Returns:
            Dict with final status
        """
        workflow.logger.info(
            f"Resuming ingestion tracking for document {document_id}"
        )
        
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(minutes=1),
        )
        
        elapsed_seconds = 0
        
        while elapsed_seconds < max_wait_seconds:
            # Poll progress
            progress_data = await workflow.execute_activity(
                poll_ingestion_progress,
                args=[document_id, user_id],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            # Update Professor DB
            await workflow.execute_activity(
                update_book_progress,
                args=[book_id, progress_data],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            if progress_data.get("is_complete"):
                # Fetch TOC and complete
                toc_result = await workflow.execute_activity(
                    fetch_and_store_toc,
                    args=[document_id, book_id, user_id],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=retry_policy,
                )
                
                await workflow.execute_activity(
                    mark_book_ready_for_planning,
                    args=[book_id, document_id],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                
                greeting_result = await workflow.execute_activity(
                    trigger_professor_greeting,
                    args=[book_id, user_id],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=retry_policy,
                )
                
                return {
                    "status": "completed",
                    "book_id": book_id,
                    "document_id": document_id,
                    "total_chapters": toc_result.get("total_chapters"),
                }
            
            if progress_data.get("is_failed"):
                error_msg = progress_data.get("error_message", "Unknown error")
                
                await workflow.execute_activity(
                    mark_book_ingestion_failed,
                    args=[book_id, error_msg],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                
                return {
                    "status": "failed",
                    "book_id": book_id,
                    "document_id": document_id,
                    "error": error_msg,
                }
            
            await workflow.sleep(timedelta(seconds=poll_interval_seconds))
            elapsed_seconds += poll_interval_seconds
        
        return {
            "status": "timeout",
            "book_id": book_id,
            "document_id": document_id,
        }
