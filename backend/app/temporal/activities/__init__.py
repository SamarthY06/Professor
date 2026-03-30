"""Temporal activities for Professor workflows."""

from app.temporal.activities.teaching import (
    generate_chapter_summary,
)

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

__all__ = [
    # Teaching (used by ChatWorkflow)
    "generate_chapter_summary",

    # Document Ingestion (External RAG)
    "upload_document_to_rag",
    "poll_ingestion_progress",
    "update_book_progress",
    "fetch_and_store_toc",
    "fetch_chapter_summaries",
    "mark_book_ready_for_planning",
    "mark_book_ingestion_failed",
    "trigger_professor_greeting",
    "log_rag_processing_cost",
]
