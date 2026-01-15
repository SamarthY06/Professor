"""Missed session workflow for handling inactive users."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.notifications import send_email_notification, send_push_notification
    from app.temporal.activities.learning import update_motivation_score


@workflow.defn
class MissedSessionWorkflow:
    """
    Workflow for handling missed study sessions.
    Sends reminders and updates motivation scores.
    """
    
    def __init__(self):
        self._user_returned = False
    
    @workflow.run
    async def run(
        self,
        user_id: str,
        book_id: str,
        days_inactive: int,
    ) -> dict:
        """
        Execute the missed session workflow.
        
        Args:
            user_id: The user's ID
            book_id: The book they were studying
            days_inactive: Number of days since last activity
            
        Returns:
            Result of the workflow
        """
        workflow.logger.info(
            f"Starting missed session workflow for user {user_id}, "
            f"inactive for {days_inactive} days"
        )
        
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=10),
        )
        
        # Determine reminder message based on inactivity
        if days_inactive <= 2:
            message_type = "gentle_reminder"
            message_data = {
                "title": "We miss you!",
                "body": "You were making great progress. Ready to continue?",
            }
        elif days_inactive <= 5:
            message_type = "encouragement"
            message_data = {
                "title": "Don't give up!",
                "body": "Learning takes consistency. Let's get back on track!",
            }
        else:
            message_type = "re_engagement"
            message_data = {
                "title": "Your learning journey awaits",
                "body": "It's never too late to continue. We're here when you're ready.",
            }
        
        # Send push notification
        await workflow.execute_activity(
            send_push_notification,
            args=[user_id, message_type, message_data],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
        
        # If very inactive, also send email
        if days_inactive >= 5:
            await workflow.execute_activity(
                send_email_notification,
                args=[user_id, message_type, message_data],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
        
        # Wait to see if user returns
        try:
            await workflow.wait_condition(
                lambda: self._user_returned,
                timeout=timedelta(days=1),
            )
            
            workflow.logger.info(f"User {user_id} returned after reminder")
            
            return {
                "user_id": user_id,
                "status": "user_returned",
                "days_inactive": days_inactive,
            }
            
        except Exception:
            # User didn't return, update motivation score
            await workflow.execute_activity(
                update_motivation_score,
                args=[user_id, book_id, -0.1],  # Decrease motivation
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            workflow.logger.info(
                f"User {user_id} did not return, motivation score decreased"
            )
            
            return {
                "user_id": user_id,
                "status": "no_return",
                "days_inactive": days_inactive + 1,
            }
    
    @workflow.signal
    def user_active(self):
        """Signal that the user has become active."""
        self._user_returned = True
