"""Cost tracking activities for Temporal workers."""
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from temporalio import activity

from app.config.settings import settings
from app.config.logging import get_logger
from app.models.cost import CostType, calculate_cost, OPENAI_PRICING

logger = get_logger(__name__)


@activity.defn
async def record_cost_transaction(
    cost_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
    document_id: Optional[str] = None,
    user_id: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Record a cost transaction to the database.
    
    Args:
        cost_type: Type of cost (EMBEDDING, TOC_DETECTION, IMAGE_SUMMARY, RAG_QUERY)
        model: OpenAI model used
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        document_id: Optional document ID
        user_id: Optional user ID
        description: Optional description
        metadata: Optional additional metadata
        
    Returns:
        Transaction details including calculated cost
    """
    from app.storage.postgres import get_db_session
    from app.models.cost import CostTransaction, CostType as CostTypeEnum
    
    # Calculate cost
    cost_usd = calculate_cost(model, input_tokens, output_tokens)
    
    activity.logger.info(
        f"Recording cost: type={cost_type}, model={model}, "
        f"tokens={input_tokens}+{output_tokens}, cost=${cost_usd:.8f}"
    )
    
    async with get_db_session() as session:
        transaction = CostTransaction(
            document_id=uuid.UUID(document_id) if document_id else None,
            user_id=user_id,
            cost_type=CostTypeEnum(cost_type),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            description=description,
            cost_metadata=metadata,
        )
        session.add(transaction)
        await session.flush()
        
        return {
            "transaction_id": str(transaction.id),
            "cost_type": cost_type,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": str(cost_usd),
        }


async def record_cost_sync(
    cost_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
    document_id: Optional[str] = None,
    user_id: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Synchronous version for use outside of Temporal activities.
    
    This can be called directly from API endpoints.
    """
    from app.storage.postgres import get_db_session
    from app.models.cost import CostTransaction, CostType as CostTypeEnum
    
    # Calculate cost
    cost_usd = calculate_cost(model, input_tokens, output_tokens)
    
    logger.info(
        f"Recording cost: type={cost_type}, model={model}, "
        f"tokens={input_tokens}+{output_tokens}, cost=${cost_usd:.8f}"
    )
    
    async with get_db_session() as session:
        transaction = CostTransaction(
            document_id=uuid.UUID(document_id) if document_id else None,
            user_id=user_id,
            cost_type=CostTypeEnum(cost_type),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            description=description,
            cost_metadata=metadata,
        )
        session.add(transaction)
        await session.flush()
        
        return {
            "transaction_id": str(transaction.id),
            "cost_type": cost_type,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": str(cost_usd),
        }


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.
    
    Uses a simple heuristic: ~4 characters per token for English text.
    For more accurate counting, use tiktoken library.
    """
    # Simple estimation: ~4 chars per token
    return max(1, len(text) // 4)


def get_model_pricing(model: str) -> dict:
    """Get pricing info for a model."""
    pricing = OPENAI_PRICING.get(model, OPENAI_PRICING["gpt-4o"])
    return {
        "model": model,
        "input_per_1m": str(pricing.get("input", Decimal("0"))),
        "output_per_1m": str(pricing.get("output", Decimal("0"))),
    }
