"""Admin API routes with comprehensive usage tracking and analytics."""

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies import require_admin, get_redis
from app.logs.logger import get_logger
from app.models.user import User
from app.models.book import Book
from app.models.learning import LearningState
from app.models.quiz import QuizAttempt
from app.models.admin import AdminLog, SystemMetric, FeatureFlag
from app.models.usage import (
    UserSubscription, UsageLog, DailyUsageAggregate,
    PlatformUsageAggregate, ModelPricing, UserFeedback
)
from app.services.usage_service import AdminUsageService

logger = get_logger(__name__)
router = APIRouter()


class UserListResponse(BaseModel):
    """User list item."""
    id: UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserDetailResponse(UserListResponse):
    """Detailed user response."""
    phone: Optional[str]
    updated_at: datetime
    books_count: int
    goals_count: int
    total_study_time_minutes: int


class DashboardStats(BaseModel):
    """Admin dashboard statistics."""
    total_users: int
    active_users_24h: int
    active_users_7d: int
    total_books: int
    total_quizzes_completed: int
    avg_quiz_pass_rate: float
    avg_study_time_minutes: float


class SystemHealth(BaseModel):
    """System health status."""
    postgres: str
    redis: str
    temporal: str
    disk_usage_percent: float
    memory_usage_percent: float


class FeatureFlagResponse(BaseModel):
    """Feature flag response."""
    id: UUID
    flag_name: str
    is_enabled: bool
    rollout_percentage: int
    conditions: Optional[dict]

    class Config:
        from_attributes = True


class FeatureFlagUpdate(BaseModel):
    """Feature flag update request."""
    is_enabled: Optional[bool] = None
    rollout_percentage: Optional[int] = None
    conditions: Optional[dict] = None


@router.get("/users", response_model=List[UserListResponse])
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    conditions = []
    
    if search:
        conditions.append(
            (User.email.ilike(f"%{search}%")) | (User.name.ilike(f"%{search}%"))
        )
    
    query = select(User)
    if conditions:
        query = query.where(*conditions)
    
    query = query.order_by(User.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    # Log admin action
    await _log_admin_action(db, admin_id, "list_users", {"search": search})
    
    return users


@router.get("/users-with-usage")
async def list_users_with_usage(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    tier: Optional[str] = None,
    sort_by: str = Query("created_at", regex="^(created_at|total_requests|total_cost|last_active)$"),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    List all users with their usage statistics.
    
    Returns comprehensive usage data for each user including:
    - Subscription tier (free/byok/pro)
    - Total API requests (all time and this month)
    - Total tokens consumed
    - Total cost (platform-paid for freemium, user-paid for BYOK)
    - Books uploaded
    - Last active timestamp
    """
    from datetime import timedelta
    from sqlalchemy import case, literal_column
    
    # Get current month start
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Base query for users
    conditions = []
    if search:
        conditions.append(
            or_(User.email.ilike(f"%{search}%"), User.name.ilike(f"%{search}%"))
        )
    
    # Get users with their subscription info
    user_query = select(User)
    if conditions:
        user_query = user_query.where(*conditions)
    user_query = user_query.order_by(User.created_at.desc())
    user_query = user_query.offset((page - 1) * per_page).limit(per_page)
    
    users_result = await db.execute(user_query)
    users = users_result.scalars().all()
    
    # Get usage stats for each user
    user_ids = [u.id for u in users]
    
    if not user_ids:
        return []
    
    # Get subscription info for all users
    subs_result = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id.in_(user_ids))
    )
    subscriptions = {s.user_id: s for s in subs_result.scalars().all()}
    
    # Get all-time usage stats per user
    all_time_stats = await db.execute(
        select(
            UsageLog.user_id,
            func.count(UsageLog.id).label("total_requests"),
            func.sum(UsageLog.input_tokens + UsageLog.output_tokens).label("total_tokens"),
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "platform").label("platform_cost"),
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "user").label("user_cost"),
            func.max(UsageLog.created_at).label("last_active"),
        )
        .where(UsageLog.user_id.in_(user_ids))
        .group_by(UsageLog.user_id)
    )
    all_time_by_user = {r.user_id: r for r in all_time_stats}
    
    # Get this month's usage stats per user
    month_stats = await db.execute(
        select(
            UsageLog.user_id,
            func.count(UsageLog.id).label("requests"),
            func.sum(UsageLog.input_tokens + UsageLog.output_tokens).label("tokens"),
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "platform").label("platform_cost"),
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "user").label("user_cost"),
        )
        .where(
            UsageLog.user_id.in_(user_ids),
            UsageLog.created_at >= month_start,
        )
        .group_by(UsageLog.user_id)
    )
    month_by_user = {r.user_id: r for r in month_stats}
    
    # Get books count per user
    books_stats = await db.execute(
        select(
            Book.user_id,
            func.count(Book.id).label("count"),
        )
        .where(Book.user_id.in_(user_ids))
        .group_by(Book.user_id)
    )
    books_by_user = {r.user_id: r.count for r in books_stats}
    
    # Build response
    result = []
    for user in users:
        sub = subscriptions.get(user.id)
        all_time = all_time_by_user.get(user.id)
        month = month_by_user.get(user.id)
        books_count = books_by_user.get(user.id, 0)
        
        tier = sub.tier if sub else "free"
        
        result.append({
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
            "tier": tier,
            "preferred_model": sub.preferred_model if sub else None,
            "books_count": books_count,
            "usage": {
                "all_time": {
                    "requests": all_time.total_requests if all_time else 0,
                    "tokens": all_time.total_tokens or 0 if all_time else 0,
                    "platform_cost_cents": all_time.platform_cost or 0 if all_time else 0,
                    "user_cost_cents": all_time.user_cost or 0 if all_time else 0,
                },
                "this_month": {
                    "requests": month.requests if month else 0,
                    "tokens": month.tokens or 0 if month else 0,
                    "platform_cost_cents": month.platform_cost or 0 if month else 0,
                    "user_cost_cents": month.user_cost or 0 if month else 0,
                },
                "subscription": {
                    "pdfs_used": sub.books_used_this_month if sub else 0,
                    "messages_used": sub.messages_used_this_month if sub else 0,
                    "quizzes_used": sub.quizzes_used_this_month if sub else 0,
                    "pdf_limit": sub.monthly_book_limit if sub else 5,
                    "message_limit": sub.monthly_message_limit if sub else 50,
                    "quiz_limit": sub.monthly_quiz_limit if sub else 10,
                } if sub else None,
            },
            "last_active": all_time.last_active.isoformat() if all_time and all_time.last_active else None,
        })
    
    # Sort if needed
    if sort_by == "total_requests":
        result.sort(key=lambda x: x["usage"]["all_time"]["requests"], reverse=True)
    elif sort_by == "total_cost":
        result.sort(key=lambda x: x["usage"]["all_time"]["platform_cost_cents"] + x["usage"]["all_time"]["user_cost_cents"], reverse=True)
    elif sort_by == "last_active":
        result.sort(key=lambda x: x["last_active"] or "", reverse=True)
    
    return result


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: UUID,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed user information."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Get counts
    books_result = await db.execute(
        select(func.count(Book.id)).where(Book.user_id == user_id)
    )
    books_count = books_result.scalar() or 0
    
    from app.models.book import Goal
    goals_result = await db.execute(
        select(func.count(Goal.id)).where(Goal.user_id == user_id)
    )
    goals_count = goals_result.scalar() or 0
    
    # Get total study time
    study_result = await db.execute(
        select(func.sum(LearningState.total_study_time_minutes))
        .where(LearningState.user_id == user_id)
    )
    total_study_time = study_result.scalar() or 0
    
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        phone=user.phone,
        created_at=user.created_at,
        updated_at=user.updated_at,
        books_count=books_count,
        goals_count=goals_count,
        total_study_time_minutes=total_study_time,
    )


@router.patch("/users/{user_id}/status")
async def toggle_user_status(
    user_id: UUID,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enable/disable a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    user.is_active = not user.is_active
    await db.commit()
    
    await _log_admin_action(
        db, admin_id, "toggle_user_status",
        {"user_id": str(user_id), "is_active": user.is_active},
        target_type="user", target_id=user_id
    )
    
    logger.info(
        "user_status_changed",
        admin_id=str(admin_id),
        user_id=str(user_id),
        is_active=user.is_active,
    )
    
    return {"is_active": user.is_active}


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get admin dashboard statistics."""
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    
    # Total users
    result = await db.execute(select(func.count(User.id)))
    total_users = result.scalar() or 0
    
    # Active users (24h)
    result = await db.execute(
        select(func.count(LearningState.id.distinct()))
        .where(LearningState.last_active_at >= day_ago)
    )
    active_24h = result.scalar() or 0
    
    # Active users (7d)
    result = await db.execute(
        select(func.count(LearningState.id.distinct()))
        .where(LearningState.last_active_at >= week_ago)
    )
    active_7d = result.scalar() or 0
    
    # Total books
    result = await db.execute(select(func.count(Book.id)))
    total_books = result.scalar() or 0
    
    # Total quizzes completed
    result = await db.execute(
        select(func.count(QuizAttempt.id))
        .where(QuizAttempt.completed_at.isnot(None))
    )
    quizzes_completed = result.scalar() or 0
    
    # Average quiz pass rate
    result = await db.execute(
        select(func.avg(QuizAttempt.score))
        .where(QuizAttempt.completed_at.isnot(None))
    )
    avg_pass_rate = result.scalar() or 0
    
    # Average study time
    result = await db.execute(
        select(func.avg(LearningState.total_study_time_minutes))
    )
    avg_study_time = result.scalar() or 0
    
    return DashboardStats(
        total_users=total_users,
        active_users_24h=active_24h,
        active_users_7d=active_7d,
        total_books=total_books,
        total_quizzes_completed=quizzes_completed,
        avg_quiz_pass_rate=round(avg_pass_rate * 100, 1) if avg_pass_rate else 0,
        avg_study_time_minutes=round(avg_study_time, 1) if avg_study_time else 0,
    )


@router.get("/system/health", response_model=SystemHealth)
async def get_system_health(
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
):
    """Get basic system health status."""
    import psutil
    import platform
    
    # Check Postgres
    try:
        await db.execute(select(1))
        postgres_status = "healthy"
    except Exception:
        postgres_status = "unhealthy"
    
    # Check Redis
    try:
        await redis.ping()
        redis_status = "healthy"
    except Exception:
        redis_status = "unhealthy"
    
    # Check Temporal
    try:
        from app.temporal.client import get_temporal_client
        client = await get_temporal_client(max_retries=1, retry_delay=1.0)
        temporal_status = "healthy"
    except Exception:
        temporal_status = "unhealthy"
    
    # System metrics (cross-platform)
    if platform.system() == "Windows":
        disk_usage = psutil.disk_usage("C:\\").percent
    else:
        disk_usage = psutil.disk_usage("/").percent
    memory_usage = psutil.virtual_memory().percent
    
    return SystemHealth(
        postgres=postgres_status,
        redis=redis_status,
        temporal=temporal_status,
        disk_usage_percent=disk_usage,
        memory_usage_percent=memory_usage,
    )


@router.get("/system/metrics")
async def get_detailed_server_metrics(
    admin_id: UUID = Depends(require_admin),
):
    """
    Get comprehensive server utilization metrics.
    
    Returns detailed CPU, memory, disk, network, and process metrics.
    Works cross-platform (Linux, macOS, Windows).
    """
    from app.services.system_monitor_service import get_server_metrics
    
    metrics = await get_server_metrics()
    return metrics


@router.get("/system/metrics/history")
async def get_metrics_history(
    hours: int = Query(24, ge=1, le=168),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical server metrics for charts.
    
    Args:
        hours: Number of hours of history to retrieve (1-168, default 24)
    """
    from app.models.admin import SystemMetric
    
    start_time = datetime.utcnow() - timedelta(hours=hours)
    
    result = await db.execute(
        select(SystemMetric)
        .where(SystemMetric.recorded_at >= start_time)
        .order_by(SystemMetric.recorded_at)
    )
    metrics = result.scalars().all()
    
    # Group by metric name
    grouped = {}
    for m in metrics:
        if m.metric_name not in grouped:
            grouped[m.metric_name] = []
        grouped[m.metric_name].append({
            "timestamp": m.recorded_at.isoformat(),
            "value": m.metric_value,
        })
    
    return {
        "period_hours": hours,
        "metrics": grouped,
    }


@router.post("/system/pricing/sync")
async def trigger_pricing_sync(
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger OpenAI pricing sync.
    
    This fetches the latest model information from OpenAI
    and updates pricing in the database.
    """
    from app.services.openai_pricing_service import OpenAIPricingService
    
    service = OpenAIPricingService(db)
    result = await service.sync_pricing_to_database()
    
    await _log_admin_action(
        db, admin_id, "manual_pricing_sync",
        {"result": result},
    )
    
    return {
        "success": True,
        "changes": result,
    }


@router.get("/feature-flags", response_model=List[FeatureFlagResponse])
async def list_feature_flags(
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all feature flags."""
    result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.flag_name))
    flags = result.scalars().all()
    return flags


@router.patch("/feature-flags/{flag_name}", response_model=FeatureFlagResponse)
async def update_feature_flag(
    flag_name: str,
    updates: FeatureFlagUpdate,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a feature flag."""
    result = await db.execute(
        select(FeatureFlag).where(FeatureFlag.flag_name == flag_name)
    )
    flag = result.scalar_one_or_none()
    
    if flag is None:
        # Create new flag
        flag = FeatureFlag(flag_name=flag_name)
        db.add(flag)
    
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(flag, field, value)
    
    await db.commit()
    await db.refresh(flag)
    
    await _log_admin_action(
        db, admin_id, "update_feature_flag",
        {"flag_name": flag_name, "updates": update_data}
    )
    
    logger.info(
        "feature_flag_updated",
        admin_id=str(admin_id),
        flag_name=flag_name,
    )
    
    return flag


@router.get("/logs/admin", response_model=List[dict])
async def get_admin_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get admin activity logs (admin only)."""
    from app.models.admin import AdminLog
    
    result = await db.execute(
        select(AdminLog)
        .order_by(AdminLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    logs = result.scalars().all()
    
    return [
        {
            "id": str(log.id),
            "admin_user_id": str(log.admin_user_id),
            "action": log.action,
            "target_type": log.target_type,
            "target_id": str(log.target_id) if log.target_id else None,
            "details": log.details,
            "ip_address": str(log.ip_address) if log.ip_address else None,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.get("/logs/agents", response_model=List[dict])
async def get_agent_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    user_id_filter: Optional[UUID] = None,
    agent_name: Optional[str] = None,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get agent execution logs (admin only).
    
    Admins can view ALL user agent logs for debugging and monitoring.
    """
    from app.models.chat import AgentLog
    
    query = select(AgentLog)
    
    if user_id_filter:
        query = query.where(AgentLog.user_id == user_id_filter)
    if agent_name:
        query = query.where(AgentLog.agent_name == agent_name)
    
    query = query.order_by(AgentLog.timestamp.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return [
        {
            "id": str(log.id),
            "user_id": str(log.user_id) if log.user_id else None,
            "session_id": str(log.session_id) if log.session_id else None,
            "agent_name": log.agent_name,
            "action": log.action,
            "execution_time_ms": log.execution_time_ms,
            "error": log.error,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]


@router.get("/logs/chat/{user_id}", response_model=List[dict])
async def get_user_chat_history(
    user_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get chat history for a specific user (admin only).
    
    Admins can view any user's chat history for support/debugging.
    """
    from app.models.chat import ChatMessage, ChatSession
    
    result = await db.execute(
        select(ChatMessage)
        .join(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    messages = result.scalars().all()
    
    return [
        {
            "id": str(msg.id),
            "session_id": str(msg.session_id),
            "role": msg.role,
            "content": msg.content[:500] + "..." if len(msg.content) > 500 else msg.content,
            "agent_name": msg.agent_name,
            "is_quiz_question": msg.is_quiz_question,
            "quiz_answer_correct": msg.quiz_answer_correct,
            "latency_ms": msg.latency_ms,
            "created_at": msg.created_at.isoformat(),
        }
        for msg in messages
    ]


async def _log_admin_action(
    db: AsyncSession,
    admin_id: UUID,
    action: str,
    details: dict = None,
    target_type: str = None,
    target_id: UUID = None,
):
    """Log an admin action."""
    log = AdminLog(
        admin_user_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    db.add(log)
    await db.flush()


# ========================
# Usage & Analytics Endpoints
# ========================

class PlatformStatsResponse(BaseModel):
    """Comprehensive platform statistics."""
    users: dict
    usage_today: dict
    costs: dict
    model_breakdown: List[dict]


class UsageTimelineResponse(BaseModel):
    """Daily usage timeline data point."""
    date: Optional[str]
    requests: int
    tokens: int
    platform_cost_cents: int
    active_users: int


class TopUserResponse(BaseModel):
    """Top user by usage."""
    user_id: str
    email: str
    name: str
    tier: str
    requests: int
    tokens: int
    cost_cents: int


class UserUsageDetailResponse(BaseModel):
    """Detailed user usage information."""
    user: dict
    subscription: Optional[dict]
    all_time: dict
    recent_logs: List[dict]


class FeedbackResponse(BaseModel):
    """User feedback item."""
    id: UUID
    user_id: UUID
    user_email: Optional[str]
    user_name: Optional[str]
    feedback_type: str
    rating: Optional[int]
    title: Optional[str]
    content: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackUpdateRequest(BaseModel):
    """Update feedback status."""
    status: str
    admin_notes: Optional[str] = None


class ModelPricingResponse(BaseModel):
    """Model pricing information."""
    id: UUID
    model_name: str
    display_name: str
    input_price_per_million: int
    output_price_per_million: int
    cached_input_price_per_million: Optional[int]
    is_available: bool
    supports_batch: bool
    available_for_free: bool
    available_for_byok: bool
    description: Optional[str]

    class Config:
        from_attributes = True


class ModelPricingUpdateRequest(BaseModel):
    """Update model pricing."""
    input_price_per_million: Optional[int] = None
    output_price_per_million: Optional[int] = None
    cached_input_price_per_million: Optional[int] = None
    is_available: Optional[bool] = None
    available_for_free: Optional[bool] = None
    available_for_byok: Optional[bool] = None
    description: Optional[str] = None


@router.get("/analytics/platform-stats", response_model=PlatformStatsResponse)
async def get_platform_stats(
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive platform statistics including:
    - User counts and tier breakdown
    - Today's usage metrics
    - Platform costs (freemium users)
    - Model usage breakdown
    """
    service = AdminUsageService(db)
    stats = await service.get_platform_stats()
    return stats


@router.get("/analytics/usage-timeline", response_model=List[UsageTimelineResponse])
async def get_usage_timeline(
    days: int = Query(30, ge=1, le=90),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get daily usage timeline for charts (last N days)."""
    service = AdminUsageService(db)
    timeline = await service.get_usage_timeline(days)
    return timeline


@router.get("/analytics/top-users", response_model=List[TopUserResponse])
async def get_top_users(
    limit: int = Query(20, ge=1, le=100),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get top users by usage this month."""
    service = AdminUsageService(db)
    users = await service.get_top_users(limit)
    return users


@router.get("/analytics/user/{user_id}", response_model=UserUsageDetailResponse)
async def get_user_usage_detail(
    user_id: UUID,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed usage information for a specific user."""
    service = AdminUsageService(db)
    detail = await service.get_user_detailed_usage(user_id)
    
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return detail


@router.get("/analytics/costs-breakdown")
async def get_costs_breakdown(
    days: int = Query(30, ge=1, le=90),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed cost breakdown:
    - By model
    - By usage type
    - Platform vs User paid
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Cost by model
    model_costs = await db.execute(
        select(
            UsageLog.model_used,
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "platform").label("platform_cost"),
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "user").label("user_cost"),
            func.count(UsageLog.id).label("requests"),
        )
        .where(UsageLog.created_at >= start_date)
        .group_by(UsageLog.model_used)
        .order_by(func.sum(UsageLog.cost_cents).desc())
    )
    
    # Cost by usage type
    type_costs = await db.execute(
        select(
            UsageLog.usage_type,
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "platform").label("platform_cost"),
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "user").label("user_cost"),
            func.count(UsageLog.id).label("requests"),
        )
        .where(UsageLog.created_at >= start_date)
        .group_by(UsageLog.usage_type)
        .order_by(func.sum(UsageLog.cost_cents).desc())
    )
    
    # Total costs
    totals = await db.execute(
        select(
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "platform").label("platform_total"),
            func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "user").label("user_total"),
        )
        .where(UsageLog.created_at >= start_date)
    )
    total_row = totals.one()
    
    return {
        "period_days": days,
        "by_model": [
            {
                "model": r.model_used,
                "platform_cost_cents": r.platform_cost or 0,
                "user_cost_cents": r.user_cost or 0,
                "requests": r.requests,
            }
            for r in model_costs
        ],
        "by_usage_type": [
            {
                "type": r.usage_type,
                "platform_cost_cents": r.platform_cost or 0,
                "user_cost_cents": r.user_cost or 0,
                "requests": r.requests,
            }
            for r in type_costs
        ],
        "totals": {
            "platform_cost_cents": total_row.platform_total or 0,
            "platform_cost_usd": round((total_row.platform_total or 0) / 100, 2),
            "user_cost_cents": total_row.user_total or 0,
            "user_cost_usd": round((total_row.user_total or 0) / 100, 2),
        },
    }


# ========================
# User Subscription Management
# ========================

@router.get("/subscriptions")
async def list_subscriptions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    tier: Optional[str] = None,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all user subscriptions with usage info."""
    query = (
        select(
            UserSubscription,
            User.email,
            User.name,
        )
        .join(User, User.id == UserSubscription.user_id)
    )
    
    if tier:
        query = query.where(UserSubscription.tier == tier)
    
    query = query.order_by(UserSubscription.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        {
            "id": str(row.UserSubscription.id),
            "user_id": str(row.UserSubscription.user_id),
            "email": row.email,
            "name": row.name,
            "tier": row.UserSubscription.tier,
            "preferred_model": row.UserSubscription.preferred_model,
            "usage": {
                "pdfs": row.UserSubscription.books_used_this_month,
                "messages": row.UserSubscription.messages_used_this_month,
                "quizzes": row.UserSubscription.quizzes_used_this_month,
            },
            "limits": {
                "pdfs": row.UserSubscription.monthly_book_limit,
                "messages": row.UserSubscription.monthly_message_limit,
                "quizzes": row.UserSubscription.monthly_quiz_limit,
            },
            "billing_cycle_start": row.UserSubscription.billing_cycle_start.isoformat(),
        }
        for row in rows
    ]


@router.patch("/subscriptions/{user_id}/tier")
async def update_user_tier(
    user_id: UUID,
    tier: str = Query(..., regex="^(free|byok|pro)$"),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Manually update a user's subscription tier."""
    from app.services.usage_service import UsageService, TIER_LIMITS
    
    if tier not in TIER_LIMITS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {list(TIER_LIMITS.keys())}",
        )
    
    service = UsageService(db)
    subscription = await service.update_user_tier(user_id, tier)
    
    await _log_admin_action(
        db, admin_id, "update_user_tier",
        {"user_id": str(user_id), "new_tier": tier},
        target_type="user", target_id=user_id
    )
    
    return {
        "success": True,
        "user_id": str(user_id),
        "new_tier": tier,
    }


# ========================
# Feedback Management
# ========================

@router.get("/feedback", response_model=List[FeedbackResponse])
async def list_feedback(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = None,
    feedback_type: Optional[str] = None,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all user feedback."""
    query = (
        select(UserFeedback, User.email, User.name)
        .join(User, User.id == UserFeedback.user_id)
    )
    
    if status_filter:
        query = query.where(UserFeedback.status == status_filter)
    if feedback_type:
        query = query.where(UserFeedback.feedback_type == feedback_type)
    
    query = query.order_by(UserFeedback.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        FeedbackResponse(
            id=row.UserFeedback.id,
            user_id=row.UserFeedback.user_id,
            user_email=row.email,
            user_name=row.name,
            feedback_type=row.UserFeedback.feedback_type,
            rating=row.UserFeedback.rating,
            title=row.UserFeedback.title,
            content=row.UserFeedback.content,
            status=row.UserFeedback.status,
            created_at=row.UserFeedback.created_at,
        )
        for row in rows
    ]


@router.patch("/feedback/{feedback_id}")
async def update_feedback_status(
    feedback_id: UUID,
    update: FeedbackUpdateRequest,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update feedback status and add admin notes."""
    result = await db.execute(
        select(UserFeedback).where(UserFeedback.id == feedback_id)
    )
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found",
        )
    
    feedback.status = update.status
    if update.admin_notes:
        feedback.admin_notes = update.admin_notes
    feedback.reviewed_at = datetime.utcnow()
    
    await db.commit()
    
    await _log_admin_action(
        db, admin_id, "update_feedback",
        {"feedback_id": str(feedback_id), "new_status": update.status},
    )
    
    return {"success": True, "status": update.status}


# ========================
# Model Pricing Management
# ========================

@router.get("/models/pricing", response_model=List[ModelPricingResponse])
async def list_model_pricing(
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all model pricing configurations."""
    result = await db.execute(
        select(ModelPricing).order_by(ModelPricing.model_name)
    )
    return result.scalars().all()


@router.patch("/models/pricing/{model_name}")
async def update_model_pricing(
    model_name: str,
    update: ModelPricingUpdateRequest,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update model pricing or availability."""
    result = await db.execute(
        select(ModelPricing).where(ModelPricing.model_name == model_name)
    )
    model = result.scalar_one_or_none()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )
    
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(model, field, value)
    
    await db.commit()
    
    await _log_admin_action(
        db, admin_id, "update_model_pricing",
        {"model_name": model_name, "updates": update_data},
    )
    
    return {"success": True, "model_name": model_name}


# ========================
# Books & Learning Analytics
# ========================

@router.get("/analytics/books")
async def get_books_analytics(
    days: int = Query(30, ge=1, le=90),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get book upload and completion analytics."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total books
    total_books = await db.execute(select(func.count(Book.id)))
    
    # Books uploaded in period
    new_books = await db.execute(
        select(func.count(Book.id))
        .where(Book.created_at >= start_date)
    )
    
    # Books by processing status
    status_breakdown = await db.execute(
        select(
            Book.processing_status,
            func.count(Book.id).label("count"),
        )
        .group_by(Book.processing_status)
    )
    
    # Daily uploads - use literal_column for GROUP BY and ORDER BY
    from sqlalchemy import literal_column
    daily_uploads = await db.execute(
        select(
            func.date_trunc('day', Book.created_at).label("date"),
            func.count(Book.id).label("count"),
        )
        .where(Book.created_at >= start_date)
        .group_by(literal_column("1"))
        .order_by(literal_column("1"))
    )
    
    # Completion stats
    completion_stats = await db.execute(
        select(
            func.count(LearningState.id).label("total_learning"),
            func.avg(LearningState.total_study_time_minutes).label("avg_study_time"),
        )
    )
    completion_row = completion_stats.one()
    
    return {
        "total_books": total_books.scalar() or 0,
        "new_books_period": new_books.scalar() or 0,
        "status_breakdown": {r.processing_status: r.count for r in status_breakdown},
        "daily_uploads": [
            {"date": r.date.isoformat() if r.date else None, "count": r.count}
            for r in daily_uploads
        ],
        "learning_stats": {
            "total_active_learners": completion_row.total_learning or 0,
            "avg_study_time_minutes": round(completion_row.avg_study_time or 0, 1),
        },
    }


@router.get("/analytics/quizzes")
async def get_quiz_analytics(
    days: int = Query(30, ge=1, le=90),
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get quiz completion and performance analytics."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Total quizzes
    total_quizzes = await db.execute(
        select(func.count(QuizAttempt.id))
        .where(QuizAttempt.completed_at.isnot(None))
    )
    
    # Quizzes in period
    period_quizzes = await db.execute(
        select(func.count(QuizAttempt.id))
        .where(
            QuizAttempt.completed_at.isnot(None),
            QuizAttempt.completed_at >= start_date,
        )
    )
    
    # Average score
    avg_score = await db.execute(
        select(func.avg(QuizAttempt.score))
        .where(QuizAttempt.completed_at.isnot(None))
    )
    
    # Pass rate
    pass_rate = await db.execute(
        select(
            func.count(QuizAttempt.id).filter(QuizAttempt.passed == True).label("passed"),
            func.count(QuizAttempt.id).label("total"),
        )
        .where(QuizAttempt.completed_at.isnot(None))
    )
    pass_row = pass_rate.one()
    
    # Daily completions - use literal_column for GROUP BY and ORDER BY
    daily_completions = await db.execute(
        select(
            func.date_trunc('day', QuizAttempt.completed_at).label("date"),
            func.count(QuizAttempt.id).label("count"),
            func.avg(QuizAttempt.score).label("avg_score"),
        )
        .where(
            QuizAttempt.completed_at.isnot(None),
            QuizAttempt.completed_at >= start_date,
        )
        .group_by(literal_column("1"))
        .order_by(literal_column("1"))
    )
    
    return {
        "total_completed": total_quizzes.scalar() or 0,
        "completed_in_period": period_quizzes.scalar() or 0,
        "average_score": round((avg_score.scalar() or 0) * 100, 1),
        "pass_rate": round((pass_row.passed / pass_row.total * 100) if pass_row.total > 0 else 0, 1),
        "daily_completions": [
            {
                "date": r.date.isoformat() if r.date else None,
                "count": r.count,
                "avg_score": round((r.avg_score or 0) * 100, 1),
            }
            for r in daily_completions
        ],
    }


@router.get("/books")
async def list_all_books(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user_id: Optional[UUID] = None,
    status: Optional[str] = None,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all books with user information (admin only)."""
    query = (
        select(
            Book,
            User.email.label("user_email"),
            User.name.label("user_name"),
        )
        .join(User, User.id == Book.user_id)
    )
    
    if user_id:
        query = query.where(Book.user_id == user_id)
    if status:
        query = query.where(Book.processing_status == status)
    
    query = query.order_by(Book.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        {
            "id": str(row.Book.id),
            "title": row.Book.title,
            "author": row.Book.author,
            "processing_status": row.Book.processing_status,
            "processing_progress": row.Book.processing_progress,
            "processing_step": row.Book.processing_step,
            "total_chapters": row.Book.total_chapters,
            "created_at": row.Book.created_at.isoformat(),
            "user_id": str(row.Book.user_id),
            "user_email": row.user_email,
            "user_name": row.user_name,
        }
        for row in rows
    ]


@router.get("/books/{book_id}")
async def get_book_detail(
    book_id: UUID,
    admin_id: UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed book information including learning states (admin only)."""
    # Get book with user info
    result = await db.execute(
        select(Book, User.email, User.name)
        .join(User, User.id == Book.user_id)
        .where(Book.id == book_id)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    book = row.Book
    
    # Get learning state for this book
    learning_result = await db.execute(
        select(LearningState)
        .where(LearningState.book_id == book_id)
    )
    learning_state = learning_result.scalar_one_or_none()
    
    # Get quiz attempts for this book
    quiz_result = await db.execute(
        select(func.count(QuizAttempt.id), func.avg(QuizAttempt.score))
        .where(QuizAttempt.book_id == book_id)
        .where(QuizAttempt.completed_at.isnot(None))
    )
    quiz_row = quiz_result.one()
    
    return {
        "id": str(book.id),
        "title": book.title,
        "author": book.author,
        "processing_status": book.processing_status,
        "processing_progress": book.processing_progress,
        "processing_step": book.processing_step,
        "processing_error": book.processing_error,
        "total_pages": book.total_pages,
        "total_chapters": book.total_chapters,
        "created_at": book.created_at.isoformat(),
        "user": {
            "id": str(book.user_id),
            "email": row.email,
            "name": row.name,
        },
        "learning": {
            "current_day": learning_state.current_day if learning_state else None,
            "current_chapter": learning_state.current_chapter if learning_state else None,
            "total_study_time_minutes": learning_state.total_study_time_minutes if learning_state else 0,
            "last_active_at": learning_state.last_active_at.isoformat() if learning_state and learning_state.last_active_at else None,
        } if learning_state else None,
        "quizzes": {
            "total_completed": quiz_row[0] or 0,
            "average_score": round((quiz_row[1] or 0) * 100, 1),
        },
    }


# C1 Response Enhancer endpoints have been removed.
# Response formatting is now handled client-side using KaTeX and react-markdown.
