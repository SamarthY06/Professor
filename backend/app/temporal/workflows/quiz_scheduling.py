"""Quiz scheduling workflow."""

import asyncio
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.quiz import generate_chapter_quiz, process_quiz_results
    from app.temporal.activities.notifications import send_push_notification
    from app.temporal.activities.learning import unlock_next_chapter, schedule_review_session


@workflow.defn
class QuizSchedulingWorkflow:
    """
    Workflow for scheduling and managing chapter quizzes.
    Handles quiz generation, reminders, and progress unlocking.
    """
    
    def __init__(self):
        self._chapter_teaching_complete = False
        self._quiz_completed = False
        self._quiz_passed = False
    
    @workflow.run
    async def run(
        self,
        user_id: str,
        book_id: str,
        chapter_id: str,
    ) -> dict:
        """
        Execute the quiz scheduling workflow.
        
        Args:
            user_id: The user's ID
            book_id: The book's ID
            chapter_id: The chapter's ID
            
        Returns:
            Result of the quiz workflow
        """
        workflow.logger.info(
            f"Starting quiz workflow for user {user_id}, chapter {chapter_id}"
        )
        
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(minutes=1),
        )
        
        # Wait for chapter teaching to complete
        await workflow.wait_condition(lambda: self._chapter_teaching_complete)
        
        # Generate quiz
        quiz_id = await workflow.execute_activity(
            generate_chapter_quiz,
            args=[book_id, chapter_id, user_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        
        # Notify user that quiz is ready
        await workflow.execute_activity(
            send_push_notification,
            args=[user_id, "quiz_ready", {"quiz_id": quiz_id, "chapter_id": chapter_id}],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
        
        # Wait for quiz completion with timeout and reminders
        retry_count = 0
        max_retries = 3
        
        while not self._quiz_completed and retry_count < max_retries:
            try:
                await workflow.wait_condition(
                    lambda: self._quiz_completed,
                    timeout=timedelta(hours=24),
                )
            except asyncio.TimeoutError:
                retry_count += 1
                
                # Send reminder
                await workflow.execute_activity(
                    send_push_notification,
                    args=[
                        user_id,
                        "quiz_reminder",
                        {"quiz_id": quiz_id, "reminder_number": retry_count},
                    ],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                
                workflow.logger.info(
                    f"Sent quiz reminder #{retry_count} for user {user_id}"
                )
        
        if not self._quiz_completed:
            workflow.logger.warning(
                f"Quiz not completed after {max_retries} reminders for user {user_id}"
            )
            return {
                "user_id": user_id,
                "quiz_id": quiz_id,
                "status": "timeout",
            }
        
        # Process quiz results
        result = await workflow.execute_activity(
            process_quiz_results,
            args=[user_id, quiz_id],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
        
        if self._quiz_passed:
            # Unlock next chapter
            await workflow.execute_activity(
                unlock_next_chapter,
                args=[user_id, book_id, chapter_id],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            workflow.logger.info(f"Next chapter unlocked for user {user_id}")
        else:
            # Schedule review session
            await workflow.execute_activity(
                schedule_review_session,
                args=[user_id, chapter_id, result.get("weak_areas", [])],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            workflow.logger.info(f"Review session scheduled for user {user_id}")
        
        return {
            "user_id": user_id,
            "quiz_id": quiz_id,
            "passed": self._quiz_passed,
            "status": "completed",
        }
    
    @workflow.signal
    def chapter_teaching_done(self):
        """Signal that chapter teaching is complete."""
        self._chapter_teaching_complete = True
    
    @workflow.signal
    def quiz_done(self, passed: bool):
        """Signal that quiz is complete."""
        self._quiz_completed = True
        self._quiz_passed = passed
