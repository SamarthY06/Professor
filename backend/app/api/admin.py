"""Admin API routes."""

from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies import require_admin, get_redis
from app.logs.logger import get_logger
from app.models.user import User
from app.models.book import Book
from app.models.learning import LearningState
from app.models.quiz import QuizAttempt
from app.models.admin import AdminLog, SystemMetric, FeatureFlag

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
    """Get system health status."""
    import psutil
    
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
    
    # Check Temporal (placeholder)
    temporal_status = "healthy"  # Would check actual Temporal connection
    
    # System metrics
    disk_usage = psutil.disk_usage("/").percent
    memory_usage = psutil.virtual_memory().percent
    
    return SystemHealth(
        postgres=postgres_status,
        redis=redis_status,
        temporal=temporal_status,
        disk_usage_percent=disk_usage,
        memory_usage_percent=memory_usage,
    )


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
