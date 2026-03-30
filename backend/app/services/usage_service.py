"""
Usage Tracking Service - Manages freemium limits, usage tracking, and cost calculation.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
from uuid import UUID

from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.models.usage import (
    UserSubscription, UsageLog, DailyUsageAggregate, 
    PlatformUsageAggregate, ModelPricing
)
from app.models.user import User, EncryptedAPIKey

logger = get_logger(__name__)


# Tier configurations
TIER_LIMITS = {
    "free": {
        "monthly_book_limit": 5,
        "monthly_message_limit": 50,
        "monthly_quiz_limit": 10,
        "default_model": "gpt-4o-mini",
    },
    "byok": {
        "monthly_book_limit": -1,  # Unlimited
        "monthly_message_limit": -1,
        "monthly_quiz_limit": -1,
        "default_model": "gpt-4o",
    },
    "pro": {
        "monthly_book_limit": 50,
        "monthly_message_limit": 2000,
        "monthly_quiz_limit": 100,
        "default_model": "gpt-4o",
    },
}

# The external API uses "pdf" as the feature name, but the DB column
# was renamed to "book" in migration 0008_freemium_limits.
FEATURE_TO_DB_FIELD = {"pdf": "book", "message": "message", "quiz": "quiz"}


class UsageService:
    """
    Service for tracking usage, enforcing limits, and calculating costs.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_or_create_subscription(self, user_id: UUID) -> UserSubscription:
        """Get or create a user's subscription record."""
        result = await self.db.execute(
            select(UserSubscription).where(UserSubscription.user_id == user_id)
        )
        subscription = result.scalar_one_or_none()
        
        if not subscription:
            # Check if user has their own API key
            key_result = await self.db.execute(
                select(EncryptedAPIKey).where(
                    EncryptedAPIKey.user_id == user_id,
                    EncryptedAPIKey.is_valid == True
                )
            )
            has_own_key = key_result.scalar_one_or_none() is not None
            
            tier = "byok" if has_own_key else "free"
            limits = TIER_LIMITS[tier]
            
            subscription = UserSubscription(
                user_id=user_id,
                tier=tier,
                monthly_book_limit=limits["monthly_book_limit"],
                monthly_message_limit=limits["monthly_message_limit"],
                monthly_quiz_limit=limits["monthly_quiz_limit"],
                preferred_model=limits["default_model"],
                billing_cycle_start=datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            )
            self.db.add(subscription)
            await self.db.commit()
            await self.db.refresh(subscription)
            
            logger.info("subscription_created", user_id=str(user_id), tier=tier)
        
        return subscription
    
    async def check_and_reset_monthly_usage(self, subscription: UserSubscription) -> UserSubscription:
        """Check if billing cycle needs reset and reset if necessary."""
        now = datetime.utcnow()
        cycle_start = subscription.billing_cycle_start
        
        # If we're in a new month, reset usage
        if now.year > cycle_start.year or (now.year == cycle_start.year and now.month > cycle_start.month):
            subscription.books_used_this_month = 0
            subscription.messages_used_this_month = 0
            subscription.quizzes_used_this_month = 0
            subscription.billing_cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            await self.db.commit()
            
            logger.info("monthly_usage_reset", user_id=str(subscription.user_id))
        
        return subscription
    
    async def can_use_feature(
        self, 
        user_id: UUID, 
        feature: str  # "pdf", "message", "quiz"
    ) -> Tuple[bool, Optional[str], Dict]:
        """
        Check if user can use a feature based on their tier limits.
        
        Returns:
            Tuple of (can_use, error_message, usage_info)
        """
        subscription = await self.get_or_create_subscription(user_id)
        subscription = await self.check_and_reset_monthly_usage(subscription)
        
        # Map external feature name to DB field name
        db_field = FEATURE_TO_DB_FIELD.get(feature, feature)
        
        # BYOK users have unlimited usage
        if subscription.tier == "byok":
            return True, None, {
                "tier": "byok",
                "unlimited": True,
                "used": getattr(subscription, f"{db_field}s_used_this_month", 0),
            }
        
        # Get current usage and limit
        usage_field = f"{db_field}s_used_this_month"
        limit_field = f"monthly_{db_field}_limit"
        
        current_usage = getattr(subscription, usage_field, 0)
        limit = getattr(subscription, limit_field, 0)
        
        # -1 means unlimited
        if limit == -1:
            return True, None, {
                "tier": subscription.tier,
                "unlimited": True,
                "used": current_usage,
            }
        
        can_use = current_usage < limit
        remaining = max(0, limit - current_usage)
        
        usage_info = {
            "tier": subscription.tier,
            "unlimited": False,
            "used": current_usage,
            "limit": limit,
            "remaining": remaining,
            "percentage_used": round((current_usage / limit) * 100, 1) if limit > 0 else 0,
        }
        
        if not can_use:
            error_msg = f"You've reached your monthly {feature} limit ({limit}). Upgrade to BYOK by adding your own OpenAI API key for unlimited usage."
            return False, error_msg, usage_info
        
        return True, None, usage_info
    
    async def increment_usage(
        self,
        user_id: UUID,
        feature: str,  # "pdf", "message", "quiz"
        count: int = 1
    ) -> None:
        """Increment usage counter for a feature."""
        subscription = await self.get_or_create_subscription(user_id)
        
        db_field = FEATURE_TO_DB_FIELD.get(feature, feature)
        usage_field = f"{db_field}s_used_this_month"
        current = getattr(subscription, usage_field, 0)
        setattr(subscription, usage_field, current + count)
        
        await self.db.commit()
        
        logger.debug(
            "usage_incremented",
            user_id=str(user_id),
            feature=feature,
            new_count=current + count,
        )
    
    async def log_api_usage(
        self,
        user_id: UUID,
        usage_type: str,
        model_used: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        book_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        request_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
    ) -> UsageLog:
        """
        Log an API usage event and calculate cost.
        """
        subscription = await self.get_or_create_subscription(user_id)
        
        # Determine who pays
        paid_by = "user" if subscription.tier == "byok" else "platform"
        
        # Calculate cost
        cost_cents = await self._calculate_cost(
            model_used, input_tokens, output_tokens, cached_tokens
        )
        
        # Create log entry
        log = UsageLog(
            user_id=user_id,
            usage_type=usage_type,
            model_used=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_cents=cost_cents,
            paid_by=paid_by,
            book_id=book_id,
            session_id=session_id,
            request_id=request_id,
            latency_ms=latency_ms,
        )
        self.db.add(log)
        await self.db.commit()
        
        logger.debug(
            "api_usage_logged",
            user_id=str(user_id),
            usage_type=usage_type,
            model=model_used,
            tokens=input_tokens + output_tokens,
            cost_cents=cost_cents,
            paid_by=paid_by,
        )
        
        return log
    
    async def log_rag_usage(
        self,
        user_id: UUID,
        usage_type: str,  # "rag_search", "rag_upload", "rag_embedding"
        model_used: str,
        input_tokens: int,
        output_tokens: int = 0,
        cost_usd: Optional[str] = None,
        book_id: Optional[UUID] = None,
        document_id: Optional[str] = None,
        request_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
    ) -> UsageLog:
        """
        Log RAG service usage (search, upload, embedding).
        
        This tracks costs from the external RAG service which uses OpenAI
        for embeddings. The cost can be provided directly from the RAG
        service response or calculated from tokens.
        
        Args:
            user_id: User performing the operation
            usage_type: Type of RAG operation
            model_used: Model used (e.g., text-embedding-3-small)
            input_tokens: Input tokens consumed
            output_tokens: Output tokens (usually 0 for embeddings)
            cost_usd: Cost in USD as string from RAG service
            book_id: Associated book ID
            document_id: RAG service document ID
            request_id: Request tracking ID
            latency_ms: Operation latency
        
        Returns:
            UsageLog entry
        """
        subscription = await self.get_or_create_subscription(user_id)
        
        # Determine who pays
        paid_by = "user" if subscription.tier == "byok" else "platform"
        
        # Calculate cost - prefer RAG service provided cost, fallback to calculation
        if cost_usd:
            try:
                cost_cents = int(float(cost_usd) * 100)
            except (ValueError, TypeError):
                cost_cents = await self._calculate_cost(
                    model_used, input_tokens, output_tokens, 0
                )
        else:
            cost_cents = await self._calculate_cost(
                model_used, input_tokens, output_tokens, 0
            )
        
        # Create log entry
        log = UsageLog(
            user_id=user_id,
            usage_type=usage_type,
            model_used=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=0,
            cost_cents=cost_cents,
            paid_by=paid_by,
            book_id=book_id,
            request_id=request_id or document_id,
            latency_ms=latency_ms,
        )
        self.db.add(log)
        await self.db.commit()
        
        logger.info(
            "rag_usage_logged",
            user_id=str(user_id),
            usage_type=usage_type,
            model=model_used,
            tokens=input_tokens + output_tokens,
            cost_cents=cost_cents,
            cost_usd=cost_usd,
            paid_by=paid_by,
            document_id=document_id,
        )
        
        return log
    
    async def log_rag_document_processing(
        self,
        user_id: UUID,
        book_id: UUID,
        document_id: str,
        embedding_cost: str,
        toc_detection_cost: str,
        image_summary_cost: str,
        total_cost: str,
        total_tokens: int,
    ) -> UsageLog:
        """
        Log the total cost of RAG document processing (upload + embedding).
        
        Called when document ingestion completes with final cost breakdown.
        
        Args:
            user_id: User who uploaded the document
            book_id: Book ID in Professor DB
            document_id: RAG service document ID
            embedding_cost: Embedding generation cost in USD
            toc_detection_cost: TOC detection cost in USD
            image_summary_cost: Image summarization cost in USD
            total_cost: Total processing cost in USD
            total_tokens: Total tokens used
        
        Returns:
            UsageLog entry
        """
        subscription = await self.get_or_create_subscription(user_id)
        paid_by = "user" if subscription.tier == "byok" else "platform"
        
        # Convert total cost to cents
        try:
            cost_cents = int(float(total_cost) * 100)
        except (ValueError, TypeError):
            cost_cents = 0
        
        # Create log entry for document processing
        log = UsageLog(
            user_id=user_id,
            usage_type="rag_document_processing",
            model_used="text-embedding-3-small",  # Primary model for embeddings
            input_tokens=total_tokens,
            output_tokens=0,
            cached_tokens=0,
            cost_cents=cost_cents,
            paid_by=paid_by,
            book_id=book_id,
            request_id=document_id,
            latency_ms=None,
        )
        self.db.add(log)
        await self.db.commit()
        
        logger.info(
            "rag_document_processing_logged",
            user_id=str(user_id),
            book_id=str(book_id),
            document_id=document_id,
            total_cost=total_cost,
            total_tokens=total_tokens,
            cost_cents=cost_cents,
            paid_by=paid_by,
            embedding_cost=embedding_cost,
            toc_detection_cost=toc_detection_cost,
            image_summary_cost=image_summary_cost,
        )
        
        return log
    
    async def _calculate_cost(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
    ) -> int:
        """Calculate cost in cents based on model pricing."""
        result = await self.db.execute(
            select(ModelPricing).where(ModelPricing.model_name == model_name)
        )
        pricing = result.scalar_one_or_none()
        
        if not pricing:
            logger.warning("model_pricing_not_found", model=model_name)
            return 0
        
        # Calculate cost (prices are per million tokens)
        regular_input_tokens = input_tokens - cached_tokens
        
        input_cost = (regular_input_tokens / 1_000_000) * pricing.input_price_per_million
        output_cost = (output_tokens / 1_000_000) * pricing.output_price_per_million
        
        cached_cost = 0
        if cached_tokens > 0 and pricing.cached_input_price_per_million:
            cached_cost = (cached_tokens / 1_000_000) * pricing.cached_input_price_per_million
        
        total_cents = int(round(input_cost + output_cost + cached_cost))
        return total_cents
    
    async def get_user_usage_summary(self, user_id: UUID) -> Dict:
        """Get comprehensive usage summary for a user."""
        subscription = await self.get_or_create_subscription(user_id)
        subscription = await self.check_and_reset_monthly_usage(subscription)
        
        # Get this month's detailed usage
        month_start = subscription.billing_cycle_start
        
        result = await self.db.execute(
            select(
                func.sum(UsageLog.input_tokens).label("total_input"),
                func.sum(UsageLog.output_tokens).label("total_output"),
                func.sum(UsageLog.cost_cents).label("total_cost"),
                func.count(UsageLog.id).label("total_requests"),
            )
            .where(
                UsageLog.user_id == user_id,
                UsageLog.created_at >= month_start,
            )
        )
        row = result.one()
        
        # Get model breakdown
        model_result = await self.db.execute(
            select(
                UsageLog.model_used,
                func.count(UsageLog.id).label("count"),
                func.sum(UsageLog.cost_cents).label("cost"),
            )
            .where(
                UsageLog.user_id == user_id,
                UsageLog.created_at >= month_start,
            )
            .group_by(UsageLog.model_used)
        )
        model_breakdown = {r.model_used: {"count": r.count, "cost_cents": r.cost or 0} for r in model_result}
        
        return {
            "tier": subscription.tier,
            "billing_cycle_start": subscription.billing_cycle_start.isoformat(),
            "usage": {
                "pdfs": {
                    "used": subscription.books_used_this_month,
                    "limit": subscription.monthly_book_limit,
                    "unlimited": subscription.monthly_book_limit == -1,
                },
                "messages": {
                    "used": subscription.messages_used_this_month,
                    "limit": subscription.monthly_message_limit,
                    "unlimited": subscription.monthly_message_limit == -1,
                },
                "quizzes": {
                    "used": subscription.quizzes_used_this_month,
                    "limit": subscription.monthly_quiz_limit,
                    "unlimited": subscription.monthly_quiz_limit == -1,
                },
            },
            "tokens": {
                "input": row.total_input or 0,
                "output": row.total_output or 0,
                "total": (row.total_input or 0) + (row.total_output or 0),
            },
            "cost_cents": row.total_cost or 0,
            "total_requests": row.total_requests or 0,
            "model_breakdown": model_breakdown,
            "preferred_model": subscription.preferred_model,
            "use_batch_api": subscription.use_batch_api,
        }
    
    async def update_user_tier(self, user_id: UUID, new_tier: str) -> UserSubscription:
        """Update user's subscription tier."""
        if new_tier not in TIER_LIMITS:
            raise ValueError(f"Invalid tier: {new_tier}")
        
        subscription = await self.get_or_create_subscription(user_id)
        limits = TIER_LIMITS[new_tier]
        
        subscription.tier = new_tier
        subscription.monthly_book_limit = limits["monthly_book_limit"]
        subscription.monthly_message_limit = limits["monthly_message_limit"]
        subscription.monthly_quiz_limit = limits["monthly_quiz_limit"]
        
        if not subscription.preferred_model:
            subscription.preferred_model = limits["default_model"]
        
        await self.db.commit()
        
        logger.info("tier_updated", user_id=str(user_id), new_tier=new_tier)
        
        return subscription
    
    async def set_preferred_model(self, user_id: UUID, model_name: str) -> UserSubscription:
        """Set user's preferred model (BYOK users only)."""
        subscription = await self.get_or_create_subscription(user_id)
        
        # Verify model exists and is available for user's tier
        result = await self.db.execute(
            select(ModelPricing).where(
                ModelPricing.model_name == model_name,
                ModelPricing.is_available == True,
            )
        )
        model = result.scalar_one_or_none()
        
        if not model:
            raise ValueError(f"Model not available: {model_name}")
        
        if subscription.tier == "free" and not model.available_for_free:
            raise ValueError(f"Model {model_name} is not available for free tier. Add your own API key to use this model.")
        
        subscription.preferred_model = model_name
        await self.db.commit()
        
        logger.info("preferred_model_set", user_id=str(user_id), model=model_name)
        
        return subscription
    
    async def get_available_models(self, user_id: UUID) -> List[Dict]:
        """Get list of models available for user based on their tier."""
        subscription = await self.get_or_create_subscription(user_id)
        
        if subscription.tier == "free":
            result = await self.db.execute(
                select(ModelPricing).where(
                    ModelPricing.is_available == True,
                    ModelPricing.available_for_free == True,
                )
            )
        else:
            result = await self.db.execute(
                select(ModelPricing).where(
                    ModelPricing.is_available == True,
                    ModelPricing.available_for_byok == True,
                )
            )
        
        models = result.scalars().all()
        
        return [
            {
                "model_name": m.model_name,
                "display_name": m.display_name,
                "description": m.description,
                "input_price_per_million": m.input_price_per_million,
                "output_price_per_million": m.output_price_per_million,
                "cached_input_price_per_million": m.cached_input_price_per_million,
                "supports_batch": m.supports_batch,
                "max_context_tokens": m.max_context_tokens,
                "is_selected": m.model_name == subscription.preferred_model,
            }
            for m in models
        ]


class AdminUsageService:
    """
    Admin service for platform-wide usage analytics.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_platform_stats(self) -> Dict:
        """Get comprehensive platform statistics."""
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Total users
        total_users_result = await self.db.execute(select(func.count(User.id)))
        total_users = total_users_result.scalar() or 0
        
        # New users today
        new_today_result = await self.db.execute(
            select(func.count(User.id)).where(User.created_at >= today)
        )
        new_users_today = new_today_result.scalar() or 0
        
        # New users this week
        new_week_result = await self.db.execute(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )
        new_users_week = new_week_result.scalar() or 0
        
        # Tier breakdown
        tier_result = await self.db.execute(
            select(
                UserSubscription.tier,
                func.count(UserSubscription.id).label("count")
            ).group_by(UserSubscription.tier)
        )
        tier_breakdown = {r.tier: r.count for r in tier_result}
        
        # Today's usage
        today_usage = await self.db.execute(
            select(
                func.sum(UsageLog.input_tokens).label("input"),
                func.sum(UsageLog.output_tokens).label("output"),
                func.sum(UsageLog.cost_cents).label("cost"),
                func.count(UsageLog.id).label("requests"),
            )
            .where(UsageLog.created_at >= today)
        )
        today_row = today_usage.one()
        
        # Platform cost (only where paid_by = 'platform')
        platform_cost_result = await self.db.execute(
            select(func.sum(UsageLog.cost_cents))
            .where(
                UsageLog.created_at >= today,
                UsageLog.paid_by == "platform",
            )
        )
        platform_cost_today = platform_cost_result.scalar() or 0
        
        # This month's platform cost
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_cost_result = await self.db.execute(
            select(func.sum(UsageLog.cost_cents))
            .where(
                UsageLog.created_at >= month_start,
                UsageLog.paid_by == "platform",
            )
        )
        platform_cost_month = monthly_cost_result.scalar() or 0
        
        # Active users (users with usage logs in last 24h)
        active_24h_result = await self.db.execute(
            select(func.count(func.distinct(UsageLog.user_id)))
            .where(UsageLog.created_at >= today - timedelta(days=1))
        )
        active_24h = active_24h_result.scalar() or 0
        
        # Active users (7 days)
        active_7d_result = await self.db.execute(
            select(func.count(func.distinct(UsageLog.user_id)))
            .where(UsageLog.created_at >= week_ago)
        )
        active_7d = active_7d_result.scalar() or 0
        
        # Model usage breakdown today
        model_usage_result = await self.db.execute(
            select(
                UsageLog.model_used,
                func.count(UsageLog.id).label("count"),
                func.sum(UsageLog.cost_cents).label("cost"),
                func.sum(UsageLog.input_tokens + UsageLog.output_tokens).label("tokens"),
            )
            .where(UsageLog.created_at >= today)
            .group_by(UsageLog.model_used)
        )
        model_breakdown = [
            {
                "model": r.model_used,
                "requests": r.count,
                "cost_cents": r.cost or 0,
                "tokens": r.tokens or 0,
            }
            for r in model_usage_result
        ]
        
        return {
            "users": {
                "total": total_users,
                "new_today": new_users_today,
                "new_this_week": new_users_week,
                "active_24h": active_24h,
                "active_7d": active_7d,
                "tier_breakdown": tier_breakdown,
            },
            "usage_today": {
                "requests": today_row.requests or 0,
                "input_tokens": today_row.input or 0,
                "output_tokens": today_row.output or 0,
                "total_tokens": (today_row.input or 0) + (today_row.output or 0),
            },
            "costs": {
                "platform_today_cents": platform_cost_today,
                "platform_today_usd": round(platform_cost_today / 100, 2),
                "platform_month_cents": platform_cost_month,
                "platform_month_usd": round(platform_cost_month / 100, 2),
            },
            "model_breakdown": model_breakdown,
        }
    
    async def get_usage_timeline(self, days: int = 30) -> List[Dict]:
        """Get daily usage timeline for charts."""
        from sqlalchemy import literal_column
        
        end_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=days)
        
        result = await self.db.execute(
            select(
                func.date_trunc('day', UsageLog.created_at).label("date"),
                func.count(UsageLog.id).label("requests"),
                func.sum(UsageLog.input_tokens + UsageLog.output_tokens).label("tokens"),
                func.sum(UsageLog.cost_cents).filter(UsageLog.paid_by == "platform").label("platform_cost"),
                func.count(func.distinct(UsageLog.user_id)).label("active_users"),
            )
            .where(UsageLog.created_at >= start_date)
            .group_by(literal_column("1"))
            .order_by(literal_column("1"))
        )
        
        return [
            {
                "date": r.date.isoformat() if r.date else None,
                "requests": r.requests or 0,
                "tokens": r.tokens or 0,
                "platform_cost_cents": r.platform_cost or 0,
                "active_users": r.active_users or 0,
            }
            for r in result
        ]
    
    async def get_top_users(self, limit: int = 20) -> List[Dict]:
        """Get top users by usage."""
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        result = await self.db.execute(
            select(
                UsageLog.user_id,
                User.email,
                User.name,
                UserSubscription.tier,
                func.count(UsageLog.id).label("requests"),
                func.sum(UsageLog.input_tokens + UsageLog.output_tokens).label("tokens"),
                func.sum(UsageLog.cost_cents).label("cost"),
            )
            .join(User, User.id == UsageLog.user_id)
            .outerjoin(UserSubscription, UserSubscription.user_id == UsageLog.user_id)
            .where(UsageLog.created_at >= month_start)
            .group_by(UsageLog.user_id, User.email, User.name, UserSubscription.tier)
            .order_by(func.sum(UsageLog.cost_cents).desc())
            .limit(limit)
        )
        
        return [
            {
                "user_id": str(r.user_id),
                "email": r.email,
                "name": r.name,
                "tier": r.tier or "free",
                "requests": r.requests or 0,
                "tokens": r.tokens or 0,
                "cost_cents": r.cost or 0,
            }
            for r in result
        ]
    
    async def get_user_detailed_usage(self, user_id: UUID) -> Dict:
        """Get detailed usage for a specific user (admin view)."""
        # Get user info
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            return None
        
        # Get subscription
        sub_result = await self.db.execute(
            select(UserSubscription).where(UserSubscription.user_id == user_id)
        )
        subscription = sub_result.scalar_one_or_none()
        
        # Get all-time usage
        all_time_result = await self.db.execute(
            select(
                func.count(UsageLog.id).label("requests"),
                func.sum(UsageLog.input_tokens + UsageLog.output_tokens).label("tokens"),
                func.sum(UsageLog.cost_cents).label("cost"),
            )
            .where(UsageLog.user_id == user_id)
        )
        all_time = all_time_result.one()
        
        # Get recent usage logs
        recent_result = await self.db.execute(
            select(UsageLog)
            .where(UsageLog.user_id == user_id)
            .order_by(UsageLog.created_at.desc())
            .limit(50)
        )
        recent_logs = recent_result.scalars().all()
        
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat(),
            },
            "subscription": {
                "tier": subscription.tier if subscription else "free",
                "preferred_model": subscription.preferred_model if subscription else None,
                "pdfs_used": subscription.books_used_this_month if subscription else 0,
                "messages_used": subscription.messages_used_this_month if subscription else 0,
                "quizzes_used": subscription.quizzes_used_this_month if subscription else 0,
            } if subscription else None,
            "all_time": {
                "requests": all_time.requests or 0,
                "tokens": all_time.tokens or 0,
                "cost_cents": all_time.cost or 0,
            },
            "recent_logs": [
                {
                    "id": str(log.id),
                    "type": log.usage_type,
                    "model": log.model_used,
                    "tokens": log.input_tokens + log.output_tokens,
                    "cost_cents": log.cost_cents,
                    "paid_by": log.paid_by,
                    "created_at": log.created_at.isoformat(),
                }
                for log in recent_logs
            ],
        }
