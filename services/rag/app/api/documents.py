"""Document API endpoints."""
import os
import uuid
from pathlib import Path
from typing import List, Optional
from decimal import Decimal

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select, func
from temporalio.client import Client

from app.config.settings import settings
from app.config.logging import get_logger
from app.models.document import Document, DocumentStatus, DocumentPhase
from app.models.cost import CostTransaction, CostType
from app.schemas.document import DocumentUploadResponse, DocumentCostBreakdown
from app.storage.postgres import get_db_session, PostgresStorage
from app.workflows.document_ingestion import (
    DocumentIngestionWorkflow,
    DocumentIngestionInput,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
async def list_documents() -> List[dict]:
    """List all documents, ordered by creation date (newest first)."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Document).order_by(Document.created_at.desc())
        )
        documents = result.scalars().all()
        
        return [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "original_filename": doc.original_filename,
                "status": doc.status.value,
                "current_phase": doc.current_phase.value,
                "total_pages": doc.total_pages,
                "total_chapters": doc.total_chapters,
                "completed_chapters": doc.completed_chapters,
                "error_reason": doc.error_reason,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "started_at": doc.started_at.isoformat() if doc.started_at else None,
                "completed_at": doc.completed_at.isoformat() if doc.completed_at else None,
            }
            for doc in documents
        ]


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    openai_key: Optional[str] = Form(
        default=None,
        description="Optional OpenAI API key. If provided, uses this key for processing instead of the default."
    ),
) -> DocumentUploadResponse:
    """
    Upload a PDF document for processing.

    - Accepts PDF file
    - openai_key: Optional OpenAI API key (uses default if not provided)
    - Persists document metadata
    - Starts Temporal DocumentIngestionWorkflow
    - Returns immediately with document_id
    
    The processing cost can be retrieved via GET /documents/{document_id}/cost
    after processing is complete.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    # Create document record first to get the ID
    async with get_db_session() as session:
        storage = PostgresStorage(session)

        # Generate unique filename using a temp UUID
        temp_id = uuid.uuid4()
        safe_filename = f"{temp_id}.pdf"
        file_path = settings.upload_dir / safe_filename

        # Ensure upload directory exists
        settings.upload_dir.mkdir(parents=True, exist_ok=True)

        # Save file
        try:
            async with aiofiles.open(file_path, "wb") as f:
                content = await file.read()
                await f.write(content)
                file_size = len(content)
        except Exception as e:
            logger.error(f"Failed to save uploaded file: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save uploaded file",
            )

        document = await storage.create_document(
            filename=safe_filename,
            original_filename=file.filename,
            file_path=str(file_path),
            file_size=file_size,
        )

        # Use the database-generated document ID
        document_id = document.id

        # Update status to INGESTING
        await storage.update_document_status(
            document_id=document_id,
            status=DocumentStatus.INGESTING,
            phase=DocumentPhase.UPLOAD,
        )

    # Start Temporal workflow
    try:
        client = await Client.connect(settings.temporal_address)

        workflow_input = DocumentIngestionInput(
            document_id=str(document_id),
            pdf_path=str(file_path),
            filename=file.filename,
        )

        await client.start_workflow(
            DocumentIngestionWorkflow.run,
            workflow_input,
            id=f"document-{document_id}",
            task_queue=settings.temporal_task_queue,
        )

        logger.info(
            "Started document ingestion workflow",
            document_id=str(document_id),
            filename=file.filename,
        )

    except Exception as e:
        logger.error(f"Failed to start workflow: {e}")
        # Update document status to failed
        async with get_db_session() as session:
            storage = PostgresStorage(session)
            await storage.update_document_status(
                document_id=document_id,
                status=DocumentStatus.FAILED,
                error_reason=f"Failed to start ingestion workflow: {str(e)}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start document processing",
        )

    return DocumentUploadResponse(
        document_id=document_id,
        status=DocumentStatus.INGESTING,
    )


@router.get("/{document_id}")
async def get_document(document_id: uuid.UUID) -> dict:
    """Get document details."""
    async with get_db_session() as session:
        storage = PostgresStorage(session)
        document = await storage.get_document(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        return {
            "id": str(document.id),
            "filename": document.filename,
            "original_filename": document.original_filename,
            "status": document.status.value,
            "current_phase": document.current_phase.value,
            "total_pages": document.total_pages,
            "total_chapters": document.total_chapters,
            "completed_chapters": document.completed_chapters,
            "error_reason": document.error_reason,
            "created_at": document.created_at.isoformat() if document.created_at else None,
            "started_at": document.started_at.isoformat() if document.started_at else None,
            "completed_at": document.completed_at.isoformat() if document.completed_at else None,
        }


@router.get("/{document_id}/toc")
async def get_document_toc(document_id: uuid.UUID) -> dict:
    """
    Get the Table of Contents (TOC) for a document.
    
    Returns the TOC data that was extracted during document processing,
    including chapters, sections, and page ranges.
    """
    async with get_db_session() as session:
        storage = PostgresStorage(session)
        document = await storage.get_document(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        if not document.toc_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="TOC not yet available. Document may still be processing.",
            )

        return {
            "document_id": str(document.id),
            "filename": document.original_filename,
            "total_pages": document.total_pages,
            "toc": document.toc_data,
        }


@router.get("/{document_id}/cost")
async def get_document_cost(document_id: uuid.UUID) -> dict:
    """
    Get the processing cost breakdown for a document.
    
    Returns cost information including:
    - Embedding costs
    - TOC detection costs
    - Image summarization costs
    - Total cost and tokens
    """
    async with get_db_session() as session:
        storage = PostgresStorage(session)
        document = await storage.get_document(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Get cost breakdown from cost_transactions table
        result = await session.execute(
            select(
                CostTransaction.cost_type,
                func.sum(CostTransaction.cost_usd).label("total_cost"),
                func.sum(CostTransaction.input_tokens).label("input_tokens"),
                func.sum(CostTransaction.output_tokens).label("output_tokens"),
            )
            .where(CostTransaction.document_id == document_id)
            .group_by(CostTransaction.cost_type)
        )
        
        type_costs = {row.cost_type: row for row in result.fetchall()}
        
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

        return {
            "document_id": str(document_id),
            "filename": document.original_filename,
            "status": document.status.value,
            "cost": {
                "embedding_cost": f"{embedding_cost.total_cost:.8f}" if embedding_cost else "0.00000000",
                "toc_detection_cost": f"{toc_cost.total_cost:.8f}" if toc_cost else "0.00000000",
                "image_summary_cost": f"{image_cost.total_cost:.8f}" if image_cost else "0.00000000",
                "rag_query_cost": f"{rag_cost.total_cost:.8f}" if rag_cost else "0.00000000",
                "total_cost": f"{total_cost:.8f}",
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
            },
        }


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID) -> None:
    """Delete a document and all associated data."""
    async with get_db_session() as session:
        storage = PostgresStorage(session)
        document = await storage.get_document(document_id)

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Delete file if exists
        if document.file_path and os.path.exists(document.file_path):
            try:
                os.remove(document.file_path)
            except Exception as e:
                logger.warning(f"Failed to delete file: {e}")

        # Delete from database (cascades to chapters and chunks)
        await session.delete(document)

        # TODO: Delete vectors from Qdrant

        logger.info("Deleted document", document_id=str(document_id))
