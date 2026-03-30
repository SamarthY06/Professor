"""Progress API endpoints."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, func
from temporalio.client import Client

from app.config.settings import settings
from app.config.logging import get_logger
from app.models.document import DocumentPhase, DocumentStatus
from app.models.cost import CostTransaction, CostType
from app.schemas.document import DocumentProgressResponse, DocumentCostBreakdown
from app.storage.postgres import get_db_session, PostgresStorage
from app.workflows.document_ingestion import DocumentIngestionWorkflow

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["progress"])


@router.get("/{document_id}/progress", response_model=DocumentProgressResponse)
async def get_document_progress(document_id: uuid.UUID) -> DocumentProgressResponse:
    """
    Get document processing progress.

    Returns:
    - document_id
    - status: INGESTING | COMPLETED | FAILED | PARTIAL_READY
    - total_chapters
    - completed_chapters
    - percentage: 0-100
    - current_phase: TOC | CHAPTER_INGESTION | EMBEDDING | COMPLETED
    """
    async with get_db_session() as session:
        storage = PostgresStorage(session)
        document = await storage.get_document(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Try to get real-time progress from Temporal workflow
        workflow_progress = None
        if document.status == DocumentStatus.INGESTING:
            try:
                client = await Client.connect(settings.temporal_address)
                handle = client.get_workflow_handle(f"document-{document_id}")
                workflow_progress = await handle.query(
                    DocumentIngestionWorkflow.get_progress
                )
            except Exception as e:
                logger.warning(f"Could not query workflow progress: {e}")

        # Use workflow progress if available, otherwise use database values
        if workflow_progress:
            total_chapters = workflow_progress.get("total_chapters", document.total_chapters)
            completed_chapters = workflow_progress.get("completed_chapters", document.completed_chapters)
            current_phase_str = workflow_progress.get("current_phase", document.current_phase.value)

            # Map string to enum
            try:
                current_phase = DocumentPhase(current_phase_str)
            except ValueError:
                current_phase = document.current_phase

            error_reason = workflow_progress.get("error") or document.error_reason
        else:
            total_chapters = document.total_chapters
            completed_chapters = document.completed_chapters
            current_phase = document.current_phase
            error_reason = document.error_reason

        # Calculate percentage
        if total_chapters > 0:
            percentage = round((completed_chapters / total_chapters) * 100, 2)
        else:
            percentage = 0.0

        # Get cost information
        cost_breakdown = None
        cost_result = await session.execute(
            select(
                CostTransaction.cost_type,
                func.sum(CostTransaction.cost_usd).label("total_cost"),
                func.sum(CostTransaction.input_tokens).label("input_tokens"),
                func.sum(CostTransaction.output_tokens).label("output_tokens"),
            )
            .where(CostTransaction.document_id == document_id)
            .group_by(CostTransaction.cost_type)
        )
        
        type_costs = {row.cost_type: row for row in cost_result.fetchall()}
        
        if type_costs:
            embedding_cost = type_costs.get(CostType.EMBEDDING)
            toc_cost = type_costs.get(CostType.TOC_DETECTION)
            image_cost = type_costs.get(CostType.IMAGE_SUMMARY)
            
            total_cost = sum(
                (row.total_cost or Decimal("0")) for row in type_costs.values()
            )
            total_tokens = sum(
                (row.input_tokens or 0) + (row.output_tokens or 0) for row in type_costs.values()
            )
            
            cost_breakdown = DocumentCostBreakdown(
                embedding_cost=f"{embedding_cost.total_cost:.8f}" if embedding_cost else "0.00000000",
                toc_detection_cost=f"{toc_cost.total_cost:.8f}" if toc_cost else "0.00000000",
                image_summary_cost=f"{image_cost.total_cost:.8f}" if image_cost else "0.00000000",
                total_cost=f"{total_cost:.8f}",
                total_tokens=total_tokens,
            )

        return DocumentProgressResponse(
            document_id=document.id,
            status=document.status,
            total_chapters=total_chapters,
            completed_chapters=completed_chapters,
            percentage=percentage,
            current_phase=current_phase,
            error_reason=error_reason,
            started_at=document.started_at,
            completed_at=document.completed_at,
            cost=cost_breakdown,
        )
