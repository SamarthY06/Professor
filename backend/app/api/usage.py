"""User-facing usage and subscription API routes."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.models.usage import UserSubscription, ModelPricing, UserFeedback
from app.services.usage_service import UsageService

logger = get_logger(__name__)
router = APIRouter()


# ========================
# Request/Response Models
# ========================

class UsageSummaryResponse(BaseModel):
    """User's usage summary."""
    tier: str
    billing_cycle_start: str
    usage: dict
    tokens: dict
    cost_cents: int
    total_requests: int
    model_breakdown: dict
    preferred_model: Optional[str]
    use_batch_api: bool


class UsageLimitCheckResponse(BaseModel):
    """Response for checking if user can use a feature."""
    can_use: bool
    error_message: Optional[str]
    usage_info: dict


class AvailableModelResponse(BaseModel):
    """Available model for user."""
    model_name: str
    display_name: str
    description: Optional[str]
    input_price_per_million: int
    output_price_per_million: int
    cached_input_price_per_million: Optional[int]
    supports_batch: bool
    max_context_tokens: int
    is_selected: bool


class SetModelRequest(BaseModel):
    """Request to set preferred model."""
    model_name: str


class SetBatchModeRequest(BaseModel):
    """Request to enable/disable batch API mode."""
    use_batch_api: bool


class SubmitFeedbackRequest(BaseModel):
    """Request to submit feedback."""
    feedback_type: str  # general, bug_report, feature_request, teaching_quality, quiz_quality
    rating: Optional[int] = None  # 1-5
    title: Optional[str] = None
    content: str
    book_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    page_url: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Feedback submission response."""
    id: UUID
    feedback_type: str
    status: str
    created_at: datetime


# ========================
# Usage Endpoints
# ========================

@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current user's usage summary including:
    - Current tier and limits
    - Usage this billing cycle
    - Token consumption
    - Cost breakdown by model
    """
    service = UsageService(db)
    summary = await service.get_user_usage_summary(user_id)
    return summary


@router.get("/check/{feature}", response_model=UsageLimitCheckResponse)
async def check_usage_limit(
    feature: str,  # pdf, message, quiz
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if user can use a specific feature based on their tier limits.
    
    Features:
    - pdf: Upload a new PDF
    - message: Send a chat message
    - quiz: Take a quiz
    """
    if feature not in ["pdf", "message", "quiz"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid feature. Must be one of: pdf, message, quiz",
        )
    
    service = UsageService(db)
    can_use, error_message, usage_info = await service.can_use_feature(user_id, feature)
    
    return UsageLimitCheckResponse(
        can_use=can_use,
        error_message=error_message,
        usage_info=usage_info,
    )


@router.get("/tier")
async def get_current_tier(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get user's current subscription tier and limits."""
    service = UsageService(db)
    subscription = await service.get_or_create_subscription(user_id)
    
    return {
        "tier": subscription.tier,
        "limits": {
            "pdfs": subscription.monthly_book_limit,
            "messages": subscription.monthly_message_limit,
            "quizzes": subscription.monthly_quiz_limit,
        },
        "usage": {
            "pdfs": subscription.books_used_this_month,
            "messages": subscription.messages_used_this_month,
            "quizzes": subscription.quizzes_used_this_month,
        },
        "preferred_model": subscription.preferred_model,
        "use_batch_api": subscription.use_batch_api,
        "billing_cycle_start": subscription.billing_cycle_start.isoformat(),
        "is_unlimited": subscription.tier == "byok",
    }


# ========================
# Model Selection (BYOK)
# ========================

@router.get("/models", response_model=List[AvailableModelResponse])
async def get_available_models(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of available models for the user based on their tier.
    
    Free tier users can only use models marked as available_for_free.
    BYOK users can use all models marked as available_for_byok.
    """
    service = UsageService(db)
    models = await service.get_available_models(user_id)
    return models


@router.post("/models/select")
async def set_preferred_model(
    request: SetModelRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Set the user's preferred model.
    
    BYOK users can select any available model.
    Free tier users are limited to free-tier models.
    """
    service = UsageService(db)
    
    try:
        subscription = await service.set_preferred_model(user_id, request.model_name)
        return {
            "success": True,
            "preferred_model": subscription.preferred_model,
            "message": f"Model set to {request.model_name}",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/batch-mode")
async def set_batch_mode(
    request: SetBatchModeRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Enable or disable batch API mode (50% cheaper, async processing).
    
    Only available for BYOK users.
    """
    service = UsageService(db)
    subscription = await service.get_or_create_subscription(user_id)
    
    if subscription.tier != "byok":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Batch API mode is only available for BYOK users. Add your own API key to enable this feature.",
        )
    
    subscription.use_batch_api = request.use_batch_api
    await db.commit()
    
    return {
        "success": True,
        "use_batch_api": subscription.use_batch_api,
        "message": "Batch mode enabled - requests will be 50% cheaper but processed asynchronously" if request.use_batch_api else "Batch mode disabled - requests will be processed immediately",
    }


# ========================
# Feedback
# ========================

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: SubmitFeedbackRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit feedback about the platform.
    
    Feedback types:
    - general: General feedback
    - bug_report: Report a bug
    - feature_request: Request a new feature
    - teaching_quality: Feedback on teaching quality
    - quiz_quality: Feedback on quiz quality
    """
    valid_types = ["general", "bug_report", "feature_request", "teaching_quality", "quiz_quality"]
    if request.feedback_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid feedback type. Must be one of: {valid_types}",
        )
    
    if request.rating is not None and (request.rating < 1 or request.rating > 5):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating must be between 1 and 5",
        )
    
    feedback = UserFeedback(
        user_id=user_id,
        feedback_type=request.feedback_type,
        rating=request.rating,
        title=request.title,
        content=request.content,
        book_id=request.book_id,
        session_id=request.session_id,
        page_url=request.page_url,
        status="new",
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    
    logger.info(
        "feedback_submitted",
        user_id=str(user_id),
        feedback_type=request.feedback_type,
        feedback_id=str(feedback.id),
    )
    
    return FeedbackResponse(
        id=feedback.id,
        feedback_type=feedback.feedback_type,
        status=feedback.status,
        created_at=feedback.created_at,
    )


@router.get("/feedback/mine")
async def get_my_feedback(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get all feedback submitted by the current user."""
    result = await db.execute(
        select(UserFeedback)
        .where(UserFeedback.user_id == user_id)
        .order_by(UserFeedback.created_at.desc())
    )
    feedback_list = result.scalars().all()
    
    return [
        {
            "id": str(f.id),
            "feedback_type": f.feedback_type,
            "rating": f.rating,
            "title": f.title,
            "content": f.content,
            "status": f.status,
            "created_at": f.created_at.isoformat(),
        }
        for f in feedback_list
    ]


# ========================
# BYOK User Dashboard
# ========================

class BYOKDashboardResponse(BaseModel):
    """BYOK user dashboard data."""
    is_byok: bool
    current_month: dict
    daily_breakdown: list
    model_usage: list
    recent_activity: list
    cost_projections: dict


class DailyUsageItem(BaseModel):
    """Daily usage breakdown."""
    date: str
    requests: int
    input_tokens: int
    output_tokens: int
    cost_cents: int


class ModelUsageItem(BaseModel):
    """Model usage breakdown."""
    model_name: str
    display_name: str
    requests: int
    input_tokens: int
    output_tokens: int
    cost_cents: int
    percentage: float


class RecentActivityItem(BaseModel):
    """Recent activity item."""
    id: str
    type: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_cents: int
    book_title: Optional[str]
    created_at: str


@router.get("/byok/dashboard", response_model=BYOKDashboardResponse)
async def get_byok_dashboard(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get comprehensive dashboard data for BYOK users.
    Shows real-time expense tracking, usage breakdown, and projections.
    
    Only available for BYOK tier users.
    """
    from sqlalchemy import func, and_
    from datetime import timedelta
    from app.models.book import Book
    
    service = UsageService(db)
    subscription = await service.get_or_create_subscription(user_id)
    
    # Check if user is BYOK
    if subscription.tier != "byok":
        return BYOKDashboardResponse(
            is_byok=False,
            current_month={},
            daily_breakdown=[],
            model_usage=[],
            recent_activity=[],
            cost_projections={},
        )
    
    now = datetime.utcnow()
    month_start = subscription.billing_cycle_start
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Current month totals
    month_result = await db.execute(
        select(
            func.count(UsageLog.id).label("requests"),
            func.sum(UsageLog.input_tokens).label("input_tokens"),
            func.sum(UsageLog.output_tokens).label("output_tokens"),
            func.sum(UsageLog.cached_tokens).label("cached_tokens"),
            func.sum(UsageLog.cost_cents).label("cost_cents"),
        )
        .where(
            UsageLog.user_id == user_id,
            UsageLog.created_at >= month_start,
        )
    )
    month_row = month_result.one()
    
    # Today's totals
    today_result = await db.execute(
        select(
            func.count(UsageLog.id).label("requests"),
            func.sum(UsageLog.cost_cents).label("cost_cents"),
        )
        .where(
            UsageLog.user_id == user_id,
            UsageLog.created_at >= today,
        )
    )
    today_row = today_result.one()
    
    # Daily breakdown for last 30 days
    thirty_days_ago = today - timedelta(days=30)
    daily_result = await db.execute(
        select(
            func.date_trunc('day', UsageLog.created_at).label("date"),
            func.count(UsageLog.id).label("requests"),
            func.sum(UsageLog.input_tokens).label("input_tokens"),
            func.sum(UsageLog.output_tokens).label("output_tokens"),
            func.sum(UsageLog.cost_cents).label("cost_cents"),
        )
        .where(
            UsageLog.user_id == user_id,
            UsageLog.created_at >= thirty_days_ago,
        )
        .group_by(func.date_trunc('day', UsageLog.created_at))
        .order_by(func.date_trunc('day', UsageLog.created_at))
    )
    daily_breakdown = [
        {
            "date": r.date.strftime("%Y-%m-%d") if r.date else "",
            "requests": r.requests or 0,
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
            "cost_cents": r.cost_cents or 0,
        }
        for r in daily_result
    ]
    
    # Model usage breakdown
    model_result = await db.execute(
        select(
            UsageLog.model_used,
            func.count(UsageLog.id).label("requests"),
            func.sum(UsageLog.input_tokens).label("input_tokens"),
            func.sum(UsageLog.output_tokens).label("output_tokens"),
            func.sum(UsageLog.cost_cents).label("cost_cents"),
        )
        .where(
            UsageLog.user_id == user_id,
            UsageLog.created_at >= month_start,
        )
        .group_by(UsageLog.model_used)
        .order_by(func.sum(UsageLog.cost_cents).desc())
    )
    
    total_cost = month_row.cost_cents or 1  # Avoid division by zero
    
    # Get model display names
    pricing_result = await db.execute(select(ModelPricing))
    model_names = {m.model_name: m.display_name for m in pricing_result.scalars().all()}
    
    model_usage = [
        {
            "model_name": r.model_used,
            "display_name": model_names.get(r.model_used, r.model_used),
            "requests": r.requests or 0,
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
            "cost_cents": r.cost_cents or 0,
            "percentage": round(((r.cost_cents or 0) / total_cost) * 100, 1) if total_cost > 0 else 0,
        }
        for r in model_result
    ]
    
    # Recent activity (last 50 items)
    recent_result = await db.execute(
        select(UsageLog, Book.title)
        .outerjoin(Book, Book.id == UsageLog.book_id)
        .where(UsageLog.user_id == user_id)
        .order_by(UsageLog.created_at.desc())
        .limit(50)
    )
    recent_activity = [
        {
            "id": str(log.id),
            "type": log.usage_type,
            "model": log.model_used,
            "input_tokens": log.input_tokens,
            "output_tokens": log.output_tokens,
            "cost_cents": log.cost_cents,
            "book_title": title,
            "created_at": log.created_at.isoformat(),
        }
        for log, title in recent_result
    ]
    
    # Cost projections
    days_in_month = (now.replace(month=now.month % 12 + 1, day=1) - timedelta(days=1)).day
    days_elapsed = (now - month_start).days + 1
    
    if days_elapsed > 0 and month_row.cost_cents:
        daily_avg = (month_row.cost_cents or 0) / days_elapsed
        projected_monthly = daily_avg * days_in_month
    else:
        daily_avg = 0
        projected_monthly = 0
    
    # Get last month's cost for comparison
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_result = await db.execute(
        select(func.sum(UsageLog.cost_cents))
        .where(
            UsageLog.user_id == user_id,
            UsageLog.created_at >= last_month_start,
            UsageLog.created_at < month_start,
        )
    )
    last_month_cost = last_month_result.scalar() or 0
    
    cost_projections = {
        "daily_average_cents": round(daily_avg),
        "projected_monthly_cents": round(projected_monthly),
        "last_month_cents": last_month_cost,
        "month_over_month_change": round(
            ((projected_monthly - last_month_cost) / last_month_cost * 100) if last_month_cost > 0 else 0, 1
        ),
    }
    
    return BYOKDashboardResponse(
        is_byok=True,
        current_month={
            "requests": month_row.requests or 0,
            "input_tokens": month_row.input_tokens or 0,
            "output_tokens": month_row.output_tokens or 0,
            "cached_tokens": month_row.cached_tokens or 0,
            "total_tokens": (month_row.input_tokens or 0) + (month_row.output_tokens or 0),
            "cost_cents": month_row.cost_cents or 0,
            "cost_usd": round((month_row.cost_cents or 0) / 100, 2),
            "today_requests": today_row.requests or 0,
            "today_cost_cents": today_row.cost_cents or 0,
            "billing_cycle_start": month_start.isoformat(),
        },
        daily_breakdown=daily_breakdown,
        model_usage=model_usage,
        recent_activity=recent_activity,
        cost_projections=cost_projections,
    )


@router.get("/byok/realtime")
async def get_byok_realtime_stats(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Get real-time stats for BYOK users (lightweight endpoint for polling).
    Returns only essential metrics for live updates.
    """
    from sqlalchemy import func
    
    service = UsageService(db)
    subscription = await service.get_or_create_subscription(user_id)
    
    if subscription.tier != "byok":
        return {"is_byok": False}
    
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = subscription.billing_cycle_start
    
    # Get today's and month's totals in one query
    result = await db.execute(
        select(
            func.sum(UsageLog.cost_cents).filter(UsageLog.created_at >= today).label("today_cost"),
            func.sum(UsageLog.cost_cents).filter(UsageLog.created_at >= month_start).label("month_cost"),
            func.count(UsageLog.id).filter(UsageLog.created_at >= today).label("today_requests"),
            func.count(UsageLog.id).filter(UsageLog.created_at >= month_start).label("month_requests"),
        )
        .where(UsageLog.user_id == user_id)
    )
    row = result.one()
    
    # Get last activity
    last_activity = await db.execute(
        select(UsageLog)
        .where(UsageLog.user_id == user_id)
        .order_by(UsageLog.created_at.desc())
        .limit(1)
    )
    last_log = last_activity.scalar_one_or_none()
    
    return {
        "is_byok": True,
        "today": {
            "cost_cents": row.today_cost or 0,
            "cost_usd": round((row.today_cost or 0) / 100, 2),
            "requests": row.today_requests or 0,
        },
        "month": {
            "cost_cents": row.month_cost or 0,
            "cost_usd": round((row.month_cost or 0) / 100, 2),
            "requests": row.month_requests or 0,
        },
        "last_activity": {
            "type": last_log.usage_type if last_log else None,
            "model": last_log.model_used if last_log else None,
            "cost_cents": last_log.cost_cents if last_log else 0,
            "created_at": last_log.created_at.isoformat() if last_log else None,
        } if last_log else None,
        "preferred_model": subscription.preferred_model,
        "timestamp": now.isoformat(),
    }


# ========================
# Pricing Info (Public)
# ========================

@router.get("/pricing")
async def get_pricing_info(
    db: AsyncSession = Depends(get_db),
):
    """
    Get pricing information for all tiers and models.
    This endpoint is public (no auth required).
    """
    # Get all available models
    result = await db.execute(
        select(ModelPricing)
        .where(ModelPricing.is_available == True)
        .order_by(ModelPricing.model_name)
    )
    models = result.scalars().all()
    
    return {
        "tiers": {
            "free": {
                "name": "Free",
                "price": "$0/month",
                "limits": {
                    "pdfs": 5,
                    "messages": 50,
                    "quizzes": 10,
                },
                "features": [
                    "Upload up to 5 PDFs per month",
                    "50 chat messages per month",
                    "10 quizzes per month",
                    "Access to GPT-4o Mini",
                    "Basic learning features",
                ],
            },
            "byok": {
                "name": "Bring Your Own Key",
                "price": "Your OpenAI costs",
                "limits": {
                    "pdfs": "Unlimited",
                    "messages": "Unlimited",
                    "quizzes": "Unlimited",
                },
                "features": [
                    "Unlimited PDFs",
                    "Unlimited messages",
                    "Unlimited quizzes",
                    "Access to all models (GPT-4o, GPT-5, etc.)",
                    "Model selection",
                    "Batch API mode (50% cheaper)",
                    "Priority support",
                ],
            },
        },
        "models": [
            {
                "model_name": m.model_name,
                "display_name": m.display_name,
                "description": m.description,
                "pricing": {
                    "input_per_million": f"${m.input_price_per_million / 100:.3f}",
                    "output_per_million": f"${m.output_price_per_million / 100:.3f}",
                    "cached_input_per_million": f"${m.cached_input_price_per_million / 100:.3f}" if m.cached_input_price_per_million else None,
                },
                "available_for_free": m.available_for_free,
                "supports_batch": m.supports_batch,
            }
            for m in models
        ],
    }
