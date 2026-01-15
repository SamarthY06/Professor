"""Reminder workflow for scheduled notifications."""

from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.notifications import send_email_notification, send_push_notification


@workflow.defn
class ReminderWorkflow:
    """
    Workflow for sending scheduled reminders.
    Handles daily study reminders and notification scheduling.
    """
    
    def __init__(self):
        self._cancelled = False
    
    @workflow.run
    async def run(
        self,
        user_id: str,
        reminder_type: str,
        channel: str,
        message_data: dict,
        scheduled_time: Optional[str] = None,
    ) -> dict:
        """
        Execute the reminder workflow.
        
        Args:
            user_id: The user to remind
            reminder_type: Type of reminder (daily_study, quiz_due, etc.)
            channel: Notification channel (email, push)
            message_data: Data for the message template
            scheduled_time: Optional ISO timestamp for scheduling
            
        Returns:
            Result of the notification
        """
        workflow.logger.info(
            f"Starting reminder workflow for user {user_id}, type: {reminder_type}"
        )
        
        # Wait until scheduled time if specified
        if scheduled_time:
            # Parse and wait
            pass  # Would implement actual waiting
        
        # Send notification based on channel
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=10),
            maximum_interval=timedelta(minutes=5),
            backoff_coefficient=2.0,
        )
        
        result = None
        
        if channel == "email":
            result = await workflow.execute_activity(
                send_email_notification,
                args=[user_id, reminder_type, message_data],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
        elif channel == "push":
            result = await workflow.execute_activity(
                send_push_notification,
                args=[user_id, reminder_type, message_data],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
        
        workflow.logger.info(f"Reminder sent for user {user_id}")
        
        return {
            "user_id": user_id,
            "reminder_type": reminder_type,
            "channel": channel,
            "status": "sent" if result else "failed",
        }
    
    @workflow.signal
    def cancel(self):
        """Cancel the reminder."""
        self._cancelled = True
