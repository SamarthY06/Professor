"""Freemium service for managing subscription limits.

This service handles:
- Checking user subscription tier
- Enforcing limits (max books, max plan days)
- Providing upgrade prompts
"""

from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.logs.logger import get_logger
from app.models.usage import UserSubscription
from app.models.book import Book

logger = get_logger(__name__)


# =============================================================================
# TIER LIMITS CONFIGURATION
# =============================================================================

TIER_LIMITS = {
    "free": {
        "monthly_book_limit": 2,  # 2 books/PDFs per month
        "max_plan_days": 30,  # 1 month max
        "monthly_message_limit": 50,
        "monthly_quiz_limit": 30,  # ~1 quiz per chapter/day
    },
    "byok": {  # Bring Your Own Key - their API key, their cost
        "monthly_book_limit": -1,  # Unlimited - their key, their cost
        "max_plan_days": 60,  # 2 months max (structured output limitation)
        "monthly_message_limit": -1,  # Unlimited
        "monthly_quiz_limit": -1,  # Unlimited
    },
}

# Global maximum for plan days - structured output can't handle more
ABSOLUTE_MAX_PLAN_DAYS = 60


# =============================================================================
# FREEMIUM SERVICE
# =============================================================================

class FreemiumService:
    """Service for managing freemium limits and subscriptions."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_user_subscription(self, user_id: UUID) -> UserSubscription:
        """
        Get or create user subscription record.
        
        Returns:
            UserSubscription record for the user
        """
        from datetime import datetime
        
        result = await self.db.execute(
            select(UserSubscription).where(UserSubscription.user_id == user_id)
        )
        subscription = result.scalar_one_or_none()
        
        if not subscription:
            # Create default free tier subscription
            subscription = UserSubscription(
                user_id=user_id,
                tier="free",
                monthly_book_limit=TIER_LIMITS["free"]["monthly_book_limit"],
                max_plan_days=TIER_LIMITS["free"]["max_plan_days"],
                monthly_message_limit=TIER_LIMITS["free"]["monthly_message_limit"],
                monthly_quiz_limit=TIER_LIMITS["free"]["monthly_quiz_limit"],
            )
            self.db.add(subscription)
            await self.db.flush()
            
            logger.info(
                "created_free_subscription",
                user_id=str(user_id),
            )
        else:
            # Check if we need to reset monthly usage (new billing cycle)
            await self._reset_monthly_usage_if_needed(subscription)
        
        return subscription
    
    async def _reset_monthly_usage_if_needed(self, subscription: UserSubscription) -> None:
        """Reset monthly usage if billing cycle has rolled over."""
        from datetime import datetime
        
        now = datetime.utcnow()
        cycle_start = subscription.billing_cycle_start
        
        # Check if we're in a new month
        if now.year > cycle_start.year or (now.year == cycle_start.year and now.month > cycle_start.month):
            subscription.books_used_this_month = 0
            subscription.messages_used_this_month = 0
            subscription.quizzes_used_this_month = 0
            subscription.billing_cycle_start = now
            await self.db.flush()
            
            logger.info(
                "monthly_usage_reset",
                user_id=str(subscription.user_id),
            )
    
    async def can_upload_book(self, user_id: UUID) -> Tuple[bool, Optional[str]]:
        """
        Check if user can upload another book this month.
        
        Returns:
            Tuple of (can_upload, error_message)
        """
        subscription = await self.get_user_subscription(user_id)
        
        # -1 means unlimited (BYOK users)
        if subscription.monthly_book_limit == -1:
            return True, None
        
        if subscription.books_used_this_month >= subscription.monthly_book_limit:
            return False, (
                f"You've reached your monthly limit of {subscription.monthly_book_limit} books on the free plan. "
                f"Add your own API key (BYOK) for unlimited uploads! 📚"
            )
        
        remaining = subscription.monthly_book_limit - subscription.books_used_this_month
        logger.info(
            "book_upload_check",
            user_id=str(user_id),
            tier=subscription.tier,
            used_this_month=subscription.books_used_this_month,
            monthly_limit=subscription.monthly_book_limit,
            remaining=remaining,
        )
        
        return True, None
    
    async def increment_book_usage(self, user_id: UUID) -> None:
        """Increment the book usage counter after successful upload."""
        subscription = await self.get_user_subscription(user_id)
        subscription.books_used_this_month += 1
        await self.db.flush()
        
        logger.info(
            "book_usage_incremented",
            user_id=str(user_id),
            books_used=subscription.books_used_this_month,
        )
    
    async def get_max_plan_days(self, user_id: UUID) -> int:
        """
        Get the maximum plan days allowed for a user.
        
        Returns:
            Maximum number of days allowed in a learning plan
        """
        subscription = await self.get_user_subscription(user_id)
        return subscription.max_plan_days
    
    async def validate_plan_days(self, user_id: UUID, requested_days: int) -> Tuple[int, Optional[str]]:
        """
        Validate and potentially cap the requested plan days.
        
        Returns:
            Tuple of (actual_days, warning_message)
        """
        subscription = await self.get_user_subscription(user_id)
        tier_max_days = subscription.max_plan_days
        
        # Apply absolute maximum (structured output limitation)
        max_days = min(tier_max_days, ABSOLUTE_MAX_PLAN_DAYS)
        
        if requested_days <= max_days:
            return requested_days, None
        
        # Cap to max allowed with appropriate message
        if subscription.tier == "free":
            warning = (
                f"Your free plan allows up to {max_days} days. "
                f"I've adjusted your plan to {max_days} days. "
                f"Add your own API key (BYOK) for plans up to {ABSOLUTE_MAX_PLAN_DAYS} days! 🚀"
            )
        else:
            # For BYOK - explain it's a system limitation for step-by-step learning
            warning = (
                f"I've adjusted your plan to {max_days} days. "
                f"We recommend taking learning step by step - "
                f"longer plans can feel overwhelming! "
                f"You can always extend your plan later. 📚"
            )
        
        logger.info(
            "plan_days_capped",
            user_id=str(user_id),
            tier=subscription.tier,
            requested_days=requested_days,
            max_days=max_days,
        )
        
        return max_days, warning
    
    async def get_usage_summary(self, user_id: UUID) -> dict:
        """
        Get a summary of user's usage and limits.
        
        Returns:
            Dict with usage information
        """
        subscription = await self.get_user_subscription(user_id)
        
        return {
            "tier": subscription.tier,
            "plan_days": {
                "max": subscription.max_plan_days,
            },
            "monthly_usage": {
                "books": {
                    "used": subscription.books_used_this_month,
                    "limit": subscription.monthly_book_limit if subscription.monthly_book_limit != -1 else "unlimited",
                    "remaining": (subscription.monthly_book_limit - subscription.books_used_this_month) if subscription.monthly_book_limit != -1 else "unlimited",
                },
                "messages": {
                    "used": subscription.messages_used_this_month,
                    "limit": subscription.monthly_message_limit if subscription.monthly_message_limit != -1 else "unlimited",
                },
                "quizzes": {
                    "used": subscription.quizzes_used_this_month,
                    "limit": subscription.monthly_quiz_limit if subscription.monthly_quiz_limit != -1 else "unlimited",
                },
            },
            "billing_cycle_start": subscription.billing_cycle_start.isoformat() if subscription.billing_cycle_start else None,
        }
    
    async def upgrade_tier(self, user_id: UUID, new_tier: str) -> UserSubscription:
        """
        Upgrade user to a new tier.
        
        Args:
            user_id: User ID
            new_tier: New tier (byok only - user provides their own API key)
        
        Returns:
            Updated subscription
        """
        if new_tier not in TIER_LIMITS:
            raise ValueError(f"Invalid tier: {new_tier}. Valid tiers are: free, byok")
        
        subscription = await self.get_user_subscription(user_id)
        limits = TIER_LIMITS[new_tier]
        
        subscription.tier = new_tier
        subscription.monthly_book_limit = limits["monthly_book_limit"]
        subscription.max_plan_days = limits["max_plan_days"]
        subscription.monthly_message_limit = limits["monthly_message_limit"]
        subscription.monthly_quiz_limit = limits["monthly_quiz_limit"]
        
        await self.db.flush()
        
        logger.info(
            "tier_upgraded",
            user_id=str(user_id),
            new_tier=new_tier,
        )
        
        return subscription


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def check_book_upload_limit(db: AsyncSession, user_id: UUID) -> Tuple[bool, Optional[str]]:
    """
    Convenience function to check book upload limit.
    
    Returns:
        Tuple of (can_upload, error_message)
    """
    service = FreemiumService(db)
    return await service.can_upload_book(user_id)


async def get_max_plan_days(db: AsyncSession, user_id: UUID) -> int:
    """
    Convenience function to get max plan days.
    
    Returns:
        Maximum days allowed for learning plan
    """
    service = FreemiumService(db)
    return await service.get_max_plan_days(user_id)


async def validate_and_cap_plan_days(db: AsyncSession, user_id: UUID, requested_days: int) -> Tuple[int, Optional[str]]:
    """
    Convenience function to validate and cap plan days.
    
    Returns:
        Tuple of (actual_days, warning_message)
    """
    service = FreemiumService(db)
    return await service.validate_plan_days(user_id, requested_days)


async def increment_book_usage(db: AsyncSession, user_id: UUID) -> None:
    """
    Convenience function to increment book usage after successful upload.
    """
    service = FreemiumService(db)
    await service.increment_book_usage(user_id)
