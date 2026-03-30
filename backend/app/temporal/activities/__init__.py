"""Temporal activities for Professor workflows."""

from app.temporal.activities.chat import (
    generate_day_summary,
    get_initial_greeting,
    load_chat_state,
    load_conversation_history,
    process_chat_message,
    save_chat_state,
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
from app.temporal.activities.pricing_sync import (
    aggregate_daily_usage,
    check_and_alert_health_issues,
    collect_server_metrics,
    store_metrics_snapshot,
    sync_openai_pricing,
)
from app.temporal.activities.teaching import (
    generate_chapter_summary,
)

__all__ = [
    # Chat (LangGraph / state)
    "generate_day_summary",
    "get_initial_greeting",
    "load_chat_state",
    "load_conversation_history",
    "process_chat_message",
    "save_chat_state",
    # Teaching
    "generate_chapter_summary",
    # Document ingestion (external RAG)
    "upload_document_to_rag",
    "poll_ingestion_progress",
    "update_book_progress",
    "fetch_and_store_toc",
    "fetch_chapter_summaries",
    "mark_book_ready_for_planning",
    "mark_book_ingestion_failed",
    "trigger_professor_greeting",
    "log_rag_processing_cost",
    # Pricing sync & monitoring
    "sync_openai_pricing",
    "collect_server_metrics",
    "store_metrics_snapshot",
    "check_and_alert_health_issues",
    "aggregate_daily_usage",
]
