"""
Temporal workflows for system monitoring and pricing synchronization.

These workflows run on schedules to:
1. Sync OpenAI pricing (every 6 hours)
2. Collect server metrics (every minute)
3. Aggregate daily usage (once per day)
"""

from datetime import timedelta
from typing import Dict, Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.pricing_sync import (
        sync_openai_pricing,
        collect_server_metrics,
        store_metrics_snapshot,
        check_and_alert_health_issues,
        aggregate_daily_usage,
    )


@workflow.defn
class PricingSyncWorkflow:
    """
    Workflow to periodically sync OpenAI model pricing.
    
    This workflow:
    1. Fetches current models from OpenAI API
    2. Updates pricing in database
    3. Detects new models and price changes
    4. Runs every 6 hours
    """
    
    @workflow.run
    async def run(self) -> Dict[str, Any]:
        """Execute pricing sync."""
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=10),
            maximum_interval=timedelta(minutes=5),
            maximum_attempts=3,
            backoff_coefficient=2.0,
        )
        
        result = await workflow.execute_activity(
            sync_openai_pricing,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        
        return result


@workflow.defn
class ServerMonitoringWorkflow:
    """
    Workflow to continuously monitor server health.
    
    This workflow:
    1. Collects server metrics (CPU, memory, disk, network)
    2. Stores metrics for historical tracking
    3. Checks for health issues and alerts
    4. Runs every minute
    """
    
    @workflow.run
    async def run(self) -> Dict[str, Any]:
        """Execute server monitoring."""
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=2,
            backoff_coefficient=2.0,
        )
        
        # Collect metrics
        metrics_result = await workflow.execute_activity(
            collect_server_metrics,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )
        
        if not metrics_result.get("success"):
            return metrics_result
        
        metrics = metrics_result.get("metrics", {})
        
        # Store metrics snapshot (fire and forget, don't fail workflow if this fails)
        try:
            await workflow.execute_activity(
                store_metrics_snapshot,
                args=[metrics],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
        except Exception:
            # Log but don't fail the workflow
            pass
        
        # Check health and alert if needed
        alert_result = await workflow.execute_activity(
            check_and_alert_health_issues,
            args=[metrics],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )
        
        return {
            "success": True,
            "metrics": metrics,
            "alert": alert_result,
        }


@workflow.defn
class DailyAggregationWorkflow:
    """
    Workflow to aggregate daily usage statistics.
    
    This workflow:
    1. Aggregates per-user usage for the previous day
    2. Creates platform-wide daily statistics
    3. Runs once per day at midnight UTC
    """
    
    @workflow.run
    async def run(self) -> Dict[str, Any]:
        """Execute daily aggregation."""
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=30),
            maximum_interval=timedelta(minutes=10),
            maximum_attempts=5,
            backoff_coefficient=2.0,
        )
        
        result = await workflow.execute_activity(
            aggregate_daily_usage,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=retry_policy,
        )
        
        return result


@workflow.defn
class ContinuousMonitoringWorkflow:
    """
    Long-running workflow that continuously monitors the system.
    
    This workflow:
    1. Runs server monitoring every minute
    2. Syncs pricing every 6 hours
    3. Aggregates usage daily
    4. Never terminates (runs indefinitely)
    """
    
    @workflow.run
    async def run(self) -> None:
        """Run continuous monitoring loop. Uses continue_as_new to bound history."""
        pricing_sync_interval = timedelta(hours=6)
        metrics_interval = timedelta(minutes=1)
        aggregation_interval = timedelta(hours=24)
        
        last_pricing_sync = workflow.now()
        last_aggregation = workflow.now()
        iteration_count = 0
        max_iterations = 1000
        
        while iteration_count < max_iterations:
            iteration_count += 1
            current_time = workflow.now()
            
            # Check if we need to sync pricing
            if current_time - last_pricing_sync >= pricing_sync_interval:
                try:
                    await workflow.execute_child_workflow(
                        PricingSyncWorkflow.run,
                        id=f"pricing-sync-{current_time.isoformat()}",
                    )
                    last_pricing_sync = current_time
                except Exception:
                    pass
            
            # Check if we need to run daily aggregation
            if current_time - last_aggregation >= aggregation_interval:
                try:
                    await workflow.execute_child_workflow(
                        DailyAggregationWorkflow.run,
                        id=f"daily-aggregation-{current_time.date().isoformat()}",
                    )
                    last_aggregation = current_time
                except Exception:
                    pass
            
            # Run server monitoring
            try:
                await workflow.execute_child_workflow(
                    ServerMonitoringWorkflow.run,
                    id=f"server-monitoring-{current_time.isoformat()}",
                )
            except Exception:
                pass
            
            await workflow.sleep(metrics_interval)
        
        # Restart to bound workflow history growth
        workflow.continue_as_new()
