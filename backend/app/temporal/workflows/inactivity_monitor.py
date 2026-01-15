"""Inactivity monitoring workflow - Goals.md Section 8.

This workflow monitors user activity and triggers the Motivation Agent
when users become inactive beyond their configured threshold.
"""

from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.learning import (
        check_user_inactivity,
        send_motivation_message,
        update_motivation_score,
    )


@workflow.defn
class InactivityMonitorWorkflow:
    """
    Workflow that monitors user inactivity and triggers motivation agent.
    
    Per Goals.md Section 8:
    - Detects inactivity based on configured threshold
    - Triggers Motivation Agent
    - Sends WhatsApp reminder
    - Shows progress snapshot
    """
    
    def __init__(self):
        self._should_stop = False
    
    @workflow.run
    async def run(
        self,
        user_id: str,
        book_id: str,
        inactivity_threshold_hours: int = 24,
        check_interval_hours: int = 6,
    ) -> dict:
        """
        Monitor user activity and send motivation messages when inactive.
        
        Args:
            user_id: The user's ID
            book_id: The book being studied
            inactivity_threshold_hours: Hours before triggering (default 24)
            check_interval_hours: How often to check (default 6)
            
        Returns:
            Final status of the workflow
        """
        workflow.logger.info(
            f"Starting inactivity monitor for user {user_id}, "
            f"threshold: {inactivity_threshold_hours}h"
        )
        
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=30),
        )
        
        messages_sent = 0
        max_messages = 5  # Don't spam the user
        
        while not self._should_stop and messages_sent < max_messages:
            # Wait for check interval
            await workflow.sleep(timedelta(hours=check_interval_hours))
            
            if self._should_stop:
                break
            
            # Check inactivity
            inactivity_result = await workflow.execute_activity(
                check_user_inactivity,
                args=[user_id, book_id, inactivity_threshold_hours],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            if not inactivity_result.get("success"):
                workflow.logger.warning(f"Inactivity check failed: {inactivity_result}")
                continue
            
            if inactivity_result.get("is_inactive"):
                days_inactive = inactivity_result.get("days_inactive", 1)
                
                workflow.logger.info(
                    f"User {user_id} inactive for {days_inactive} days, sending motivation"
                )
                
                # Send motivation message
                await workflow.execute_activity(
                    send_motivation_message,
                    args=[user_id, book_id, days_inactive],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                
                messages_sent += 1
                
                # Update motivation score (decrease slightly)
                if days_inactive > 2:
                    await workflow.execute_activity(
                        update_motivation_score,
                        args=[user_id, book_id, -0.05],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=retry_policy,
                    )
            else:
                workflow.logger.info(f"User {user_id} is active, resetting message count")
                messages_sent = 0  # Reset if user becomes active
        
        return {
            "user_id": user_id,
            "book_id": book_id,
            "messages_sent": messages_sent,
            "stopped": self._should_stop,
        }
    
    @workflow.signal
    def user_active(self):
        """Signal that user has become active - stop monitoring."""
        workflow.logger.info("User active signal received")
        self._should_stop = True
    
    @workflow.signal
    def stop_monitoring(self):
        """Signal to stop the monitoring workflow."""
        self._should_stop = True
