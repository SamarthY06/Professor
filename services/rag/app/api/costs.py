"""Cost tracking API endpoints."""
import uuid
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func, and_

from app.config.logging import get_logger
from app.storage.postgres import get_db_session
from app.models.cost import CostTransaction, CostSummary, CostType, OPENAI_PRICING

logger = get_logger(__name__)
router = APIRouter(prefix="/costs", tags=["costs"])


# Response models
class CostBreakdown(BaseModel):
    """Cost breakdown by type."""
    embedding: str
    toc_detection: str
    image_summary: str
    rag_query: str
    total: str


class TokenUsage(BaseModel):
    """Token usage statistics."""
    input_tokens: int
    output_tokens: int
    total_tokens: int


class DailyCost(BaseModel):
    """Daily cost entry."""
    date: str
    cost: str
    transaction_count: int


class CostOverview(BaseModel):
    """Overall cost overview for admin dashboard."""
    total_cost_usd: str
    cost_breakdown: CostBreakdown
    token_usage: TokenUsage
    transaction_count: int
    period_start: str
    period_end: str
    daily_costs: list[DailyCost]


class DocumentCost(BaseModel):
    """Cost for a specific document."""
    document_id: str
    filename: str
    total_cost_usd: str
    cost_breakdown: CostBreakdown
    token_usage: TokenUsage
    transaction_count: int


class UserCostSummary(BaseModel):
    """Cost summary for a specific user."""
    user_id: str
    total_cost_usd: str
    cost_breakdown: CostBreakdown
    token_usage: TokenUsage
    transaction_count: int
    recent_transactions: list[dict]


class PricingInfo(BaseModel):
    """Model pricing information."""
    model: str
    input_per_1m_tokens: str
    output_per_1m_tokens: str


@router.get("/overview", response_model=CostOverview)
async def get_cost_overview(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to include"),
) -> CostOverview:
    """
    Get overall cost overview for admin dashboard.
    
    Shows total costs, breakdown by type, and daily trends.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    async with get_db_session() as session:
        # Get aggregated costs by type
        result = await session.execute(
            select(
                CostTransaction.cost_type,
                func.sum(CostTransaction.cost_usd).label("total_cost"),
                func.sum(CostTransaction.input_tokens).label("input_tokens"),
                func.sum(CostTransaction.output_tokens).label("output_tokens"),
                func.count(CostTransaction.id).label("count"),
            )
            .where(CostTransaction.created_at >= start_date)
            .group_by(CostTransaction.cost_type)
        )
        
        type_costs = {row.cost_type: row for row in result.fetchall()}
        
        # Calculate totals
        embedding_cost = type_costs.get(CostType.EMBEDDING)
        toc_cost = type_costs.get(CostType.TOC_DETECTION)
        image_cost = type_costs.get(CostType.IMAGE_SUMMARY)
        rag_cost = type_costs.get(CostType.RAG_QUERY)
        
        total_cost = sum(
            (row.total_cost or Decimal("0")) for row in type_costs.values()
        )
        total_input = sum(
            (row.input_tokens or 0) for row in type_costs.values()
        )
        total_output = sum(
            (row.output_tokens or 0) for row in type_costs.values()
        )
        total_count = sum(
            (row.count or 0) for row in type_costs.values()
        )
        
        # Get daily costs
        daily_result = await session.execute(
            select(
                func.date(CostTransaction.created_at).label("date"),
                func.sum(CostTransaction.cost_usd).label("cost"),
                func.count(CostTransaction.id).label("count"),
            )
            .where(CostTransaction.created_at >= start_date)
            .group_by(func.date(CostTransaction.created_at))
            .order_by(func.date(CostTransaction.created_at))
        )
        
        daily_costs = [
            DailyCost(
                date=str(row.date),
                cost=f"{row.cost:.8f}",
                transaction_count=row.count,
            )
            for row in daily_result.fetchall()
        ]
        
        return CostOverview(
            total_cost_usd=f"{total_cost:.8f}",
            cost_breakdown=CostBreakdown(
                embedding=f"{embedding_cost.total_cost:.8f}" if embedding_cost else "0.00000000",
                toc_detection=f"{toc_cost.total_cost:.8f}" if toc_cost else "0.00000000",
                image_summary=f"{image_cost.total_cost:.8f}" if image_cost else "0.00000000",
                rag_query=f"{rag_cost.total_cost:.8f}" if rag_cost else "0.00000000",
                total=f"{total_cost:.8f}",
            ),
            token_usage=TokenUsage(
                input_tokens=total_input,
                output_tokens=total_output,
                total_tokens=total_input + total_output,
            ),
            transaction_count=total_count,
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            daily_costs=daily_costs,
        )


@router.get("/documents", response_model=list[DocumentCost])
async def get_document_costs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[DocumentCost]:
    """
    Get cost breakdown by document.
    
    Returns top documents by cost.
    """
    async with get_db_session() as session:
        from app.models.document import Document
        
        # Get costs grouped by document
        result = await session.execute(
            select(
                CostTransaction.document_id,
                Document.original_filename,
                CostTransaction.cost_type,
                func.sum(CostTransaction.cost_usd).label("total_cost"),
                func.sum(CostTransaction.input_tokens).label("input_tokens"),
                func.sum(CostTransaction.output_tokens).label("output_tokens"),
                func.count(CostTransaction.id).label("count"),
            )
            .join(Document, CostTransaction.document_id == Document.id, isouter=True)
            .where(CostTransaction.document_id.isnot(None))
            .group_by(CostTransaction.document_id, Document.original_filename, CostTransaction.cost_type)
        )
        
        # Aggregate by document
        doc_costs: dict[str, dict] = {}
        for row in result.fetchall():
            doc_id = str(row.document_id)
            if doc_id not in doc_costs:
                doc_costs[doc_id] = {
                    "document_id": doc_id,
                    "filename": row.original_filename or "Unknown",
                    "embedding": Decimal("0"),
                    "toc_detection": Decimal("0"),
                    "image_summary": Decimal("0"),
                    "rag_query": Decimal("0"),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "count": 0,
                }
            
            cost_type_key = row.cost_type.value.lower()
            doc_costs[doc_id][cost_type_key] = row.total_cost or Decimal("0")
            doc_costs[doc_id]["input_tokens"] += row.input_tokens or 0
            doc_costs[doc_id]["output_tokens"] += row.output_tokens or 0
            doc_costs[doc_id]["count"] += row.count or 0
        
        # Convert to response format
        documents = []
        for doc_id, data in doc_costs.items():
            total = data["embedding"] + data["toc_detection"] + data["image_summary"] + data["rag_query"]
            documents.append(
                DocumentCost(
                    document_id=data["document_id"],
                    filename=data["filename"],
                    total_cost_usd=f"{total:.8f}",
                    cost_breakdown=CostBreakdown(
                        embedding=f"{data['embedding']:.8f}",
                        toc_detection=f"{data['toc_detection']:.8f}",
                        image_summary=f"{data['image_summary']:.8f}",
                        rag_query=f"{data['rag_query']:.8f}",
                        total=f"{total:.8f}",
                    ),
                    token_usage=TokenUsage(
                        input_tokens=data["input_tokens"],
                        output_tokens=data["output_tokens"],
                        total_tokens=data["input_tokens"] + data["output_tokens"],
                    ),
                    transaction_count=data["count"],
                )
            )
        
        # Sort by total cost descending
        documents.sort(key=lambda x: float(x.total_cost_usd), reverse=True)
        return documents[:limit]


@router.get("/users/{user_id}", response_model=UserCostSummary)
async def get_user_costs(
    user_id: str,
    days: int = Query(default=30, ge=1, le=365),
) -> UserCostSummary:
    """
    Get cost summary for a specific user.
    
    Shows user's total costs and recent transactions.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    async with get_db_session() as session:
        # Get aggregated costs by type for user
        result = await session.execute(
            select(
                CostTransaction.cost_type,
                func.sum(CostTransaction.cost_usd).label("total_cost"),
                func.sum(CostTransaction.input_tokens).label("input_tokens"),
                func.sum(CostTransaction.output_tokens).label("output_tokens"),
                func.count(CostTransaction.id).label("count"),
            )
            .where(
                and_(
                    CostTransaction.user_id == user_id,
                    CostTransaction.created_at >= start_date,
                )
            )
            .group_by(CostTransaction.cost_type)
        )
        
        type_costs = {row.cost_type: row for row in result.fetchall()}
        
        # Calculate totals
        embedding_cost = type_costs.get(CostType.EMBEDDING)
        toc_cost = type_costs.get(CostType.TOC_DETECTION)
        image_cost = type_costs.get(CostType.IMAGE_SUMMARY)
        rag_cost = type_costs.get(CostType.RAG_QUERY)
        
        total_cost = sum(
            (row.total_cost or Decimal("0")) for row in type_costs.values()
        )
        total_input = sum(
            (row.input_tokens or 0) for row in type_costs.values()
        )
        total_output = sum(
            (row.output_tokens or 0) for row in type_costs.values()
        )
        total_count = sum(
            (row.count or 0) for row in type_costs.values()
        )
        
        # Get recent transactions
        recent_result = await session.execute(
            select(CostTransaction)
            .where(CostTransaction.user_id == user_id)
            .order_by(CostTransaction.created_at.desc())
            .limit(10)
        )
        
        recent_transactions = [
            {
                "id": str(tx.id),
                "cost_type": tx.cost_type.value,
                "model": tx.model,
                "cost_usd": f"{tx.cost_usd:.8f}",
                "input_tokens": tx.input_tokens,
                "output_tokens": tx.output_tokens,
                "created_at": tx.created_at.isoformat(),
            }
            for tx in recent_result.scalars().all()
        ]
        
        return UserCostSummary(
            user_id=user_id,
            total_cost_usd=f"{total_cost:.8f}",
            cost_breakdown=CostBreakdown(
                embedding=f"{embedding_cost.total_cost:.8f}" if embedding_cost else "0.00000000",
                toc_detection=f"{toc_cost.total_cost:.8f}" if toc_cost else "0.00000000",
                image_summary=f"{image_cost.total_cost:.8f}" if image_cost else "0.00000000",
                rag_query=f"{rag_cost.total_cost:.8f}" if rag_cost else "0.00000000",
                total=f"{total_cost:.8f}",
            ),
            token_usage=TokenUsage(
                input_tokens=total_input,
                output_tokens=total_output,
                total_tokens=total_input + total_output,
            ),
            transaction_count=total_count,
            recent_transactions=recent_transactions,
        )


@router.get("/transactions")
async def get_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    cost_type: Optional[str] = Query(default=None),
    document_id: Optional[uuid.UUID] = Query(default=None),
) -> dict:
    """
    Get cost transactions with pagination and filtering.
    """
    async with get_db_session() as session:
        query = select(CostTransaction).order_by(CostTransaction.created_at.desc())
        
        if cost_type:
            query = query.where(CostTransaction.cost_type == CostType(cost_type))
        if document_id:
            query = query.where(CostTransaction.document_id == document_id)
        
        # Get total count
        count_query = select(func.count(CostTransaction.id))
        if cost_type:
            count_query = count_query.where(CostTransaction.cost_type == CostType(cost_type))
        if document_id:
            count_query = count_query.where(CostTransaction.document_id == document_id)
        
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0
        
        # Get paginated results
        result = await session.execute(query.offset(offset).limit(limit))
        
        transactions = [
            {
                "id": str(tx.id),
                "document_id": str(tx.document_id) if tx.document_id else None,
                "user_id": tx.user_id,
                "cost_type": tx.cost_type.value,
                "model": tx.model,
                "input_tokens": tx.input_tokens,
                "output_tokens": tx.output_tokens,
                "cost_usd": f"{tx.cost_usd:.8f}",
                "description": tx.description,
                "created_at": tx.created_at.isoformat(),
            }
            for tx in result.scalars().all()
        ]
        
        return {
            "transactions": transactions,
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/pricing", response_model=list[PricingInfo])
async def get_pricing() -> list[PricingInfo]:
    """
    Get current OpenAI pricing information.
    """
    return [
        PricingInfo(
            model=model,
            input_per_1m_tokens=str(pricing.get("input", Decimal("0"))),
            output_per_1m_tokens=str(pricing.get("output", Decimal("0"))),
        )
        for model, pricing in OPENAI_PRICING.items()
    ]
