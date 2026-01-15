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
    from app.temporal.workflows.reminder import ReminderWorkflow
    from app.temporal.workflows.quiz_scheduling import QuizSchedulingWorkflow
    from app.temporal.workflows.missed_session import MissedSessionWorkflow
    from app.temporal.workflows.learning_session import LearningSessionWorkflow
    from app.temporal.workflows.inactivity_monitor import InactivityMonitorWorkflow
    
    # Import activities
    from app.temporal.activities.notifications import (
        send_email_notification,
        send_push_notification,
        send_whatsapp_notification,
    )
    from app.temporal.activities.quiz import (
        generate_chapter_quiz,
        process_quiz_results,
    )
    from app.temporal.activities.learning import (
        unlock_next_chapter,
        schedule_review_session,
        update_motivation_score,
        get_user_learning_state,
        check_user_inactivity,
        send_motivation_message,
    )
    from app.temporal.activities.teaching import (
        get_chapter_topics,
        generate_chapter_introduction,
        generate_teaching_segment,
        generate_comprehension_question,
        evaluate_student_response,
        generate_chapter_summary,
    )
    from app.temporal.activities.session import (
        send_professor_message,
        get_pending_student_response,
        save_session_state,
        load_session_state,
        create_learning_session,
    )
    
    client = await get_temporal_client()
    
    # Configure sandbox to pass through ALL modules that use restricted operations
    # This includes pathlib, pydantic_settings, and our app modules
    sandbox_runner = SandboxedWorkflowRunner(
        restrictions=SandboxRestrictions.default.with_passthrough_modules(
            # Python stdlib
            "pathlib",
            "os",
            "dotenv",
            # Pydantic
            "pydantic",
            "pydantic_settings",
            "pydantic_settings.main",
            "pydantic_settings.sources",
            "pydantic_core",
            # Our app
            "app",
            "app.config",
            "app.temporal",
            "app.temporal.client",
            "app.temporal.activities",
            "app.temporal.activities.notifications",
            "app.temporal.activities.quiz",
            "app.temporal.activities.learning",
            "app.temporal.activities.teaching",
            "app.temporal.activities.session",
            "app.temporal.workflows",
            "app.logs",
            "app.logs.logger",
            "app.models",
            "app.db",
            "app.db.database",
            "app.services",
            "app.rag",
            # External libs
            "sqlalchemy",
            "openai",
            "redis",
            "structlog",
            "httpx",
            "anyio",
        )
    )
    
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[
            ReminderWorkflow,
            QuizSchedulingWorkflow,
            MissedSessionWorkflow,
            LearningSessionWorkflow,
            InactivityMonitorWorkflow,
        ],
        activities=[
            send_email_notification,
            send_push_notification,
            send_whatsapp_notification,
            generate_chapter_quiz,
            process_quiz_results,
            unlock_next_chapter,
            schedule_review_session,
            update_motivation_score,
            get_user_learning_state,
            check_user_inactivity,
            send_motivation_message,
            get_chapter_topics,
            generate_chapter_introduction,
            generate_teaching_segment,
            generate_comprehension_question,
            evaluate_student_response,
            generate_chapter_summary,
            send_professor_message,
            get_pending_student_response,
            save_session_state,
            load_session_state,
            create_learning_session,
        ],
        workflow_runner=sandbox_runner,
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
