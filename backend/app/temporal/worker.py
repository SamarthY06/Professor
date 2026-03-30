"""Temporal worker for executing workflows."""

import asyncio
import os
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from app.logs.logger import get_logger

logger = get_logger(__name__)


async def create_worker() -> Worker:
    """Create and configure Temporal worker."""
    # Import here to avoid circular imports and sandbox issues
    from app.config import settings
    from app.temporal.client import get_temporal_client
    
    # Import workflows
    from app.temporal.workflows.document_ingestion import (
        TrackDocumentIngestionWorkflow,
        ResumeIngestionTrackingWorkflow,
    )
    from app.temporal.workflows.system_monitoring import (
        PricingSyncWorkflow,
        ServerMonitoringWorkflow,
        DailyAggregationWorkflow,
        ContinuousMonitoringWorkflow,
    )
    from app.temporal.workflows.chat_workflow import ChatWorkflow

    # Import activities
    from app.temporal.activities.teaching import generate_chapter_summary
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
        sync_openai_pricing,
        collect_server_metrics,
        store_metrics_snapshot,
        check_and_alert_health_issues,
        aggregate_daily_usage,
    )
    from app.temporal.activities.chat import (
        load_chat_state,
        save_chat_state,
        get_initial_greeting,
        process_chat_message,
        generate_day_summary,
        load_conversation_history,
    )
    
    client = await get_temporal_client()
    
    # Sandbox passthrough: only modules actually imported by active workflows.
    # ChatWorkflow imports activities.chat, activities.teaching (generate_chapter_summary).
    # DocumentIngestion workflows import activities.document_ingestion.
    # System monitoring workflows import activities.pricing_sync.
    sandbox_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules(
            # Python stdlib needed by pydantic/config
            "pathlib",
            "os",
            "dotenv",
            "io",
            # Pydantic (settings deserialization in workflow init)
            "pydantic",
            "pydantic_settings",
            "pydantic_settings.main",
            "pydantic_settings.sources",
            "pydantic_core",
            # App config
            "app",
            "app.config",
            "app.config.rag",
            # Active activity modules
            "app.temporal.activities.chat",
            "app.temporal.activities.teaching",
            "app.temporal.activities.document_ingestion",
            "app.temporal.activities.pricing_sync",
            # Logging
            "app.logs",
            "app.logs.logger",
            # External libs used in workflow code
            "structlog",
        )
    )
    
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[
            ChatWorkflow,
            TrackDocumentIngestionWorkflow,
            ResumeIngestionTrackingWorkflow,
            PricingSyncWorkflow,
            ServerMonitoringWorkflow,
            DailyAggregationWorkflow,
            ContinuousMonitoringWorkflow,
        ],
        activities=[
            # Chat (main learning flow via LangGraph)
            load_chat_state,
            save_chat_state,
            get_initial_greeting,
            process_chat_message,
            generate_day_summary,
            load_conversation_history,
            # Teaching (chapter summary, used by ChatWorkflow)
            generate_chapter_summary,
            # Document Ingestion (External RAG)
            upload_document_to_rag,
            poll_ingestion_progress,
            update_book_progress,
            fetch_and_store_toc,
            fetch_chapter_summaries,
            mark_book_ready_for_planning,
            mark_book_ingestion_failed,
            trigger_professor_greeting,
            log_rag_processing_cost,
            # System Monitoring & Pricing Sync
            sync_openai_pricing,
            collect_server_metrics,
            store_metrics_snapshot,
            check_and_alert_health_issues,
            aggregate_daily_usage,
        ],
        workflow_runner=sandbox_runner,
        max_concurrent_activities=50,
        max_concurrent_workflow_tasks=100,
        max_concurrent_activity_task_polls=5,
        max_concurrent_workflow_task_polls=5,
    )
    
    logger.info("temporal_worker_created", task_queue=settings.temporal_task_queue)
    return worker


async def run_worker() -> None:
    """Run the Temporal worker."""
    worker = await create_worker()
    logger.info("temporal_worker_starting")
    
    try:
        await worker.run()
    except asyncio.CancelledError:
        logger.info("temporal_worker_cancelled")
    except Exception as e:
        logger.exception("temporal_worker_error", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(run_worker())
