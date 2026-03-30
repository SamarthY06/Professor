"""
Temporal activities for OpenAI pricing synchronization and system monitoring.
"""

from datetime import datetime
from typing import Dict, Any

from temporalio import activity

from app.logs.logger import get_logger

logger = get_logger(__name__)


@activity.defn
async def sync_openai_pricing() -> Dict[str, Any]:
    """
    Activity to sync OpenAI model pricing to database.
    
    This activity:
    1. Fetches available models from OpenAI API
    2. Updates pricing in database
    3. Detects new models and price changes
    
    Returns:
        Summary of changes made
    """
    from app.db.database import async_session_maker as async_session_factory
    from app.services.openai_pricing_service import OpenAIPricingService
    
    logger.info("pricing_sync_activity_started")
    
    try:
        async with async_session_factory() as db:
            service = OpenAIPricingService(db)
            result = await service.sync_pricing_to_database()
            
            logger.info(
                "pricing_sync_activity_completed",
                added=len(result.get("added", [])),
                updated=len(result.get("updated", [])),
                errors=len(result.get("errors", [])),
            )
            
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "changes": result,
            }
            
    except Exception as e:
        logger.exception("pricing_sync_activity_failed", error=str(e))
        return {
            "success": False,
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
        }


@activity.defn
async def collect_server_metrics() -> Dict[str, Any]:
    """
    Activity to collect server utilization metrics.
    
    This activity:
    1. Collects CPU, memory, disk, network metrics
    2. Identifies health issues
    3. Returns comprehensive server status
    
    Returns:
        Complete server metrics snapshot
    """
    from app.services.system_monitor_service import get_server_metrics
    
    logger.info("server_metrics_activity_started")
    
    try:
        metrics = await get_server_metrics()
        
        logger.info(
            "server_metrics_activity_completed",
            health_status=metrics.get("health_status"),
            cpu_percent=metrics.get("cpu", {}).get("usage_percent"),
            memory_percent=metrics.get("memory", {}).get("usage_percent"),
        )
        
        return {
            "success": True,
            "metrics": metrics,
        }
        
    except Exception as e:
        logger.exception("server_metrics_activity_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def store_metrics_snapshot(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Activity to store metrics snapshot in database for historical tracking.
    
    Args:
        metrics: Server metrics to store
        
    Returns:
        Result of storage operation
    """
    from app.db.database import async_session_maker as async_session_factory
    from app.models.admin import SystemMetric
    from datetime import datetime
    
    logger.info("store_metrics_activity_started")
    
    try:
        async with async_session_factory() as db:
            # Store key metrics as individual records
            timestamp = datetime.utcnow()
            
            metrics_to_store = [
                ("cpu_usage_percent", metrics.get("cpu", {}).get("usage_percent", 0)),
                ("memory_usage_percent", metrics.get("memory", {}).get("usage_percent", 0)),
                ("disk_usage_percent", metrics.get("disk", {}).get("usage_percent", 0)),
                ("network_bytes_recv_per_sec", metrics.get("network", {}).get("bytes_recv_per_sec", 0)),
                ("network_bytes_sent_per_sec", metrics.get("network", {}).get("bytes_sent_per_sec", 0)),
                ("process_count", metrics.get("processes", {}).get("total_processes", 0)),
            ]
            
            for metric_name, metric_value in metrics_to_store:
                metric = SystemMetric(
                    metric_name=metric_name,
                    metric_value=float(metric_value),
                    dimensions={
                        "health_status": metrics.get("health_status"),
                        "platform": metrics.get("system_info", {}).get("platform"),
                    },
                    recorded_at=timestamp,
                )
                db.add(metric)
            
            await db.commit()
            
            logger.info("store_metrics_activity_completed", metrics_count=len(metrics_to_store))
            
            return {
                "success": True,
                "stored_count": len(metrics_to_store),
            }
            
    except Exception as e:
        logger.exception("store_metrics_activity_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


@activity.defn
async def check_and_alert_health_issues(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Activity to check for health issues and send alerts if needed.
    
    Args:
        metrics: Server metrics to check
        
    Returns:
        Alert status
    """
    logger.info("health_check_activity_started")
    
    try:
        health_status = metrics.get("health_status", "unknown")
        health_issues = metrics.get("health_issues", [])
        
        if health_status == "critical":
            # Log critical alert (in production, this would send to PagerDuty, Slack, etc.)
            logger.critical(
                "server_health_critical",
                issues=health_issues,
                cpu=metrics.get("cpu", {}).get("usage_percent"),
                memory=metrics.get("memory", {}).get("usage_percent"),
                disk=metrics.get("disk", {}).get("usage_percent"),
            )
            
            # TODO: Integrate with alerting service (PagerDuty, Slack, email)
            return {
                "alert_sent": True,
                "severity": "critical",
                "issues": health_issues,
            }
            
        elif health_status == "warning":
            logger.warning(
                "server_health_warning",
                issues=health_issues,
            )
            
            return {
                "alert_sent": False,
                "severity": "warning",
                "issues": health_issues,
            }
        
        return {
            "alert_sent": False,
            "severity": "healthy",
            "issues": [],
        }
        
    except Exception as e:
        logger.exception("health_check_activity_failed", error=str(e))
        return {
            "alert_sent": False,
            "error": str(e),
        }


@activity.defn
async def aggregate_daily_usage() -> Dict[str, Any]:
    """
    Activity to aggregate daily usage statistics.
    
    This runs once per day to create aggregated usage records
    for faster analytics queries.
    
    Returns:
        Aggregation result
    """
    from app.db.database import async_session_maker as async_session_factory
    from app.models.usage import UsageLog, DailyUsageAggregate, PlatformUsageAggregate, UserSubscription
    from app.models.user import User
    from sqlalchemy import select, func, and_
    from datetime import datetime, timedelta
    
    logger.info("daily_aggregation_activity_started")
    
    try:
        async with async_session_factory() as db:
            # Get yesterday's date range
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday = today - timedelta(days=1)
            
            # Aggregate per-user usage
            user_usage = await db.execute(
                select(
                    UsageLog.user_id,
                    func.count(UsageLog.id).filter(UsageLog.usage_type == "chat_message").label("messages"),
                    func.count(UsageLog.id).filter(UsageLog.usage_type == "pdf_upload").label("pdfs"),
                    func.count(UsageLog.id).filter(UsageLog.usage_type == "quiz_generation").label("quizzes"),
                    func.sum(UsageLog.input_tokens).label("input_tokens"),
                    func.sum(UsageLog.output_tokens).label("output_tokens"),
                    func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "platform").label("platform_cost"),
                    func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "user").label("user_cost"),
                )
                .where(
                    UsageLog.created_at >= yesterday,
                    UsageLog.created_at < today,
                )
                .group_by(UsageLog.user_id)
            )
            
            user_aggregates_created = 0
            for row in user_usage:
                aggregate = DailyUsageAggregate(
                    user_id=row.user_id,
                    date=yesterday,
                    chat_messages=row.messages or 0,
                    pdfs_uploaded=row.pdfs or 0,
                    quizzes_taken=row.quizzes or 0,
                    total_input_tokens=row.input_tokens or 0,
                    total_output_tokens=row.output_tokens or 0,
                    platform_cost_cents=row.platform_cost or 0,
                    user_cost_cents=row.user_cost or 0,
                )
                db.add(aggregate)
                user_aggregates_created += 1
            
            # Create platform-wide aggregate
            total_users = await db.execute(select(func.count(User.id)))
            new_users = await db.execute(
                select(func.count(User.id))
                .where(User.created_at >= yesterday, User.created_at < today)
            )
            active_users = await db.execute(
                select(func.count(func.distinct(UsageLog.user_id)))
                .where(UsageLog.created_at >= yesterday, UsageLog.created_at < today)
            )
            
            # Tier breakdown
            tier_counts = await db.execute(
                select(UserSubscription.tier, func.count(UserSubscription.id))
                .group_by(UserSubscription.tier)
            )
            tier_breakdown = {row[0]: row[1] for row in tier_counts}
            
            # Total usage
            total_usage = await db.execute(
                select(
                    func.count(UsageLog.id).filter(UsageLog.usage_type == "chat_message").label("messages"),
                    func.count(UsageLog.id).filter(UsageLog.usage_type == "pdf_upload").label("pdfs"),
                    func.count(UsageLog.id).filter(UsageLog.usage_type == "quiz_generation").label("quizzes"),
                    func.sum(UsageLog.input_tokens).label("input_tokens"),
                    func.sum(UsageLog.output_tokens).label("output_tokens"),
                    func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "platform").label("platform_cost"),
                )
                .where(UsageLog.created_at >= yesterday, UsageLog.created_at < today)
            )
            usage_row = total_usage.one()
            
            platform_aggregate = PlatformUsageAggregate(
                date=yesterday,
                total_users=total_users.scalar() or 0,
                new_users=new_users.scalar() or 0,
                active_users=active_users.scalar() or 0,
                free_tier_users=tier_breakdown.get("free", 0),
                byok_users=tier_breakdown.get("byok", 0),
                pro_users=tier_breakdown.get("pro", 0),
                total_messages=usage_row.messages or 0,
                total_pdfs=usage_row.pdfs or 0,
                total_quizzes=usage_row.quizzes or 0,
                total_input_tokens=usage_row.input_tokens or 0,
                total_output_tokens=usage_row.output_tokens or 0,
                platform_cost_cents=usage_row.platform_cost or 0,
            )
            db.add(platform_aggregate)
            
            await db.commit()
            
            logger.info(
                "daily_aggregation_activity_completed",
                user_aggregates=user_aggregates_created,
                platform_cost_cents=usage_row.platform_cost or 0,
            )
            
            return {
                "success": True,
                "date": yesterday.isoformat(),
                "user_aggregates_created": user_aggregates_created,
                "platform_cost_cents": usage_row.platform_cost or 0,
            }
            
    except Exception as e:
        logger.exception("daily_aggregation_activity_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }
