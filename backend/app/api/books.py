"""Book management API routes.

This module handles book uploads and delegates document processing
to the external RAG service via Temporal workflows.

IMPORTANT: ProfessorOS never ingests or embeds PDFs itself.
All document intelligence is delegated to the external RAG service.
"""

import hashlib
import os
from datetime import datetime, date, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db, async_session_maker
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.models.book import Book, BookChapter
from app.models.learning_config import LearningConfig

logger = get_logger(__name__)
router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class BookResponse(BaseModel):
    """Book response model."""
    id: UUID
    title: str
    author: Optional[str]
    total_pages: Optional[int]
    total_chapters: Optional[int]
    processing_status: str
    processing_progress: int = 0
    processing_step: Optional[str] = None
    processing_error: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BookStatusResponse(BaseModel):
    """Book processing status response for polling."""
    id: UUID
    processing_status: str
    processing_progress: int
    processing_step: Optional[str]
    processing_error: Optional[str]
    total_pages: Optional[int]
    total_chapters: Optional[int]


class ChapterResponse(BaseModel):
    """Chapter response model."""
    id: UUID
    chapter_number: int
    title: Optional[str]
    start_page: Optional[int]
    end_page: Optional[int]
    summary: Optional[str]
    estimated_duration_minutes: Optional[int]

    class Config:
        from_attributes = True


class BookDetailResponse(BaseModel):
    """Book detail response with chapters."""
    id: UUID
    title: str
    author: Optional[str]
    total_pages: Optional[int]
    total_chapters: Optional[int]
    processing_status: str
    processing_progress: int = 0
    processing_step: Optional[str] = None
    processing_error: Optional[str] = None
    created_at: datetime
    chapters: List[ChapterResponse]

    class Config:
        from_attributes = True


class BookUploadResponse(BaseModel):
    """Response after uploading a book."""
    id: UUID
    title: str
    author: Optional[str]
    processing_status: str
    message: str
    
    class Config:
        from_attributes = True


class BookUpdateRequest(BaseModel):
    """Book update request."""
    title: Optional[str] = None
    author: Optional[str] = None


class LearningConfigRequest(BaseModel):
    """Learning configuration collected during upload."""
    learning_level: str = Field(
        default="intermediate",
        description="Student level: beginner, intermediate, advanced, research"
    )
    study_all_chapters: bool = Field(
        default=True,
        description="Whether to study all chapters or selected ones"
    )
    selected_chapters: Optional[List[int]] = Field(
        default=None,
        description="List of chapter numbers to study (if not all)"
    )
    deadline: Optional[date] = Field(
        default=None,
        description="Target completion date"
    )
    daily_study_minutes: int = Field(
        default=60,
        description="Preferred daily study time in minutes"
    )
    quiz_frequency: str = Field(
        default="after_each_chapter",
        description="Quiz timing: after_each_chapter, after_n_chapters, final_only"
    )
    quiz_after_n_chapters: Optional[int] = Field(
        default=None,
        description="If quiz_frequency is after_n_chapters, how many"
    )
    questions_per_quiz: int = Field(
        default=5,
        description="Number of questions per quiz"
    )
    enable_reminders: bool = Field(
        default=True,
        description="Enable inactivity reminders"
    )
    reminder_channel: str = Field(
        default="push",
        description="Reminder channel: push, email, whatsapp, all"
    )
    inactivity_threshold_hours: int = Field(
        default=24,
        description="Hours of inactivity before reminder"
    )


# =============================================================================
# Helper Functions
# =============================================================================

async def start_document_ingestion_workflow(
    book_id: UUID,
    user_id: UUID,
    file_path: str,
    filename: str,
) -> str:
    """
    Start the Temporal workflow to track document ingestion.
    
    Args:
        book_id: Book ID in Professor DB
        user_id: User ID
        file_path: Path to the uploaded PDF
        filename: Original filename
    
    Returns:
        Workflow ID
    """
    from app.temporal.client import get_temporal_client
    from app.temporal.workflows.document_ingestion import TrackDocumentIngestionWorkflow
    from app.config.rag import get_rag_config
    
    rag_config = get_rag_config()
    client = await get_temporal_client()
    
    workflow_id = f"doc-ingestion-{book_id}"
    
    await client.start_workflow(
        TrackDocumentIngestionWorkflow.run,
        args=[
            str(book_id),
            str(user_id),
            file_path,
            filename,
            rag_config.rag_poll_interval_seconds,
            1800,  # 30 minutes max
        ],
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    
    logger.info(
        "document_ingestion_workflow_started",
        workflow_id=workflow_id,
        book_id=str(book_id),
        user_id=str(user_id),
    )
    
    return workflow_id


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/", response_model=List[BookResponse])
async def list_books(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all books for the current user."""
    db.expire_all()
    
    result = await db.execute(
        select(Book)
        .where(Book.user_id == user_id)
        .order_by(Book.created_at.desc())
    )
    books = result.scalars().all()
    return books


@router.get("/{book_id}/status", response_model=BookStatusResponse)
async def get_book_status(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get book processing status for polling."""
    db.expire_all()
    
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    return BookStatusResponse(
        id=book.id,
        processing_status=book.processing_status,
        processing_progress=book.processing_progress or 0,
        processing_step=book.processing_step,
        processing_error=book.processing_error,
        total_pages=book.total_pages,
        total_chapters=book.total_chapters,
    )


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get book details with chapters."""
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id, Book.user_id == user_id)
        .options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    return BookDetailResponse(
        id=book.id,
        title=book.title,
        author=book.author,
        total_pages=book.total_pages,
        total_chapters=book.total_chapters,
        processing_status=book.processing_status,
        processing_progress=book.processing_progress or 0,
        processing_step=book.processing_step,
        processing_error=book.processing_error,
        created_at=book.created_at,
        chapters=[
            ChapterResponse(
                id=ch.id,
                chapter_number=ch.chapter_number,
                title=ch.title,
                start_page=ch.start_page,
                end_page=ch.end_page,
                summary=ch.summary,
                estimated_duration_minutes=ch.estimated_duration_minutes,
            )
            for ch in sorted(book.chapters, key=lambda x: x.chapter_number)
        ],
    )


@router.post("/upload", response_model=BookUploadResponse)
async def upload_book(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    learning_level: str = Form("intermediate"),
    study_all_chapters: bool = Form(True),
    selected_chapters: Optional[str] = Form(None),
    deadline: Optional[str] = Form(None),
    daily_study_minutes: int = Form(60),
    quiz_frequency: str = Form("after_each_chapter"),
    quiz_after_n_chapters: Optional[int] = Form(None),
    questions_per_quiz: int = Form(5),
    enable_reminders: bool = Form(True),
    reminder_channel: str = Form("push"),
    inactivity_threshold_hours: int = Form(24),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF book with learning configuration.
    
    The document is forwarded to the external RAG service for processing.
    A Temporal workflow tracks the ingestion progress and updates the UI.
    
    ProfessorOS NEVER processes PDFs internally - all document intelligence
    is delegated to the external RAG service.
    
    FREEMIUM LIMITS:
    - Free tier: Max 3 books
    - BYOK tier: Max 10 books
    - Pro tier: Unlimited books
    """
    import json
    from app.services.freemium_service import check_book_upload_limit
    
    # Check freemium book upload limit
    can_upload, limit_error = await check_book_upload_limit(db, user_id)
    if not can_upload:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=limit_error,
        )
    
    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )
    
    # Check file size
    contents = await file.read()
    file_size_mb = len(contents) / (1024 * 1024)
    
    if file_size_mb > settings.max_file_size_mb:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum of {settings.max_file_size_mb}MB",
        )
    
    # Calculate file hash for deduplication
    file_hash = hashlib.sha256(contents).hexdigest()
    
    # Check for duplicate
    result = await db.execute(
        select(Book).where(Book.user_id == user_id, Book.file_hash == file_hash)
    )
    existing_book = result.scalar_one_or_none()
    
    if existing_book:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This book has already been uploaded",
        )
    
    # Save file locally (for Temporal workflow to access)
    file_path = os.path.join(
        settings.pdf_storage_path,
        str(user_id),
        f"{file_hash}.pdf",
    )
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Create book record with INGESTING_EXTERNAL status
    book = Book(
        user_id=user_id,
        title=title or file.filename.replace(".pdf", ""),
        author=author,
        file_path=file_path,
        file_hash=file_hash,
        processing_status="ingesting_external",  # New status for external RAG
        processing_step="Uploading to document service...",
    )
    db.add(book)
    await db.flush()
    
    # Parse and create learning configuration
    parsed_chapters = None
    if selected_chapters:
        try:
            parsed_chapters = json.loads(selected_chapters)
        except json.JSONDecodeError:
            pass
    
    parsed_deadline = None
    if deadline:
        try:
            parsed_deadline = date.fromisoformat(deadline)
        except ValueError:
            pass
    
    learning_config = LearningConfig(
        user_id=user_id,
        book_id=book.id,
        learning_level=learning_level,
        study_all_chapters=study_all_chapters,
        selected_chapters=parsed_chapters,
        deadline=parsed_deadline,
        daily_study_minutes=daily_study_minutes,
        quiz_frequency=quiz_frequency,
        quiz_after_n_chapters=quiz_after_n_chapters,
        questions_per_quiz=questions_per_quiz,
        enable_reminders=enable_reminders,
        reminder_channel=reminder_channel,
        inactivity_threshold_hours=inactivity_threshold_hours,
    )
    db.add(learning_config)
    
    await db.commit()
    await db.refresh(book)
    
    logger.info(
        "book_uploaded",
        user_id=str(user_id),
        book_id=str(book.id),
        file_size_mb=round(file_size_mb, 2),
        learning_level=learning_level,
    )
    
    # Start Temporal workflow to track ingestion
    try:
        await start_document_ingestion_workflow(
            book_id=book.id,
            user_id=user_id,
            file_path=file_path,
            filename=file.filename,
        )
    except Exception as e:
        logger.exception(
            "workflow_start_failed",
            book_id=str(book.id),
            error=str(e),
        )
        # Update status to indicate workflow failure
        book.processing_status = "pending"
        book.processing_step = "Waiting for processing..."
        await db.commit()
    
    # Increment monthly book usage for freemium tracking
    from app.services.freemium_service import increment_book_usage
    await increment_book_usage(db, user_id)
    
    return BookUploadResponse(
        id=book.id,
        title=book.title,
        author=book.author,
        processing_status=book.processing_status,
        message="Book uploaded successfully! Processing will begin shortly. "
                "Professor will greet you once the analysis is complete.",
    )


@router.post("/upload-with-config", response_model=BookUploadResponse)
async def upload_book_with_config(
    file: UploadFile = File(...),
    title: str = Form(...),
    author: Optional[str] = Form(None),
    learning_level: str = Form("intermediate"),
    total_days: int = Form(30),
    daily_minutes: int = Form(30),
    quiz_frequency: str = Form("after_each_chapter"),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a PDF book with learning configuration and generate plan.
    
    Simplified upload endpoint with key configuration options.
    
    FREEMIUM LIMITS:
    - Free tier: Max 3 books
    - BYOK/Pro tier: Unlimited (their API key, their cost)
    """
    from app.services.freemium_service import check_book_upload_limit
    
    # Check freemium book upload limit
    can_upload, limit_error = await check_book_upload_limit(db, user_id)
    if not can_upload:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=limit_error,
        )
    
    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )
    
    # Check file size
    contents = await file.read()
    file_size_mb = len(contents) / (1024 * 1024)
    
    if file_size_mb > settings.max_file_size_mb:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum of {settings.max_file_size_mb}MB",
        )
    
    # Calculate file hash
    file_hash = hashlib.sha256(contents).hexdigest()
    
    # Check for duplicate
    result = await db.execute(
        select(Book).where(Book.user_id == user_id, Book.file_hash == file_hash)
    )
    existing_book = result.scalar_one_or_none()
    
    if existing_book:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This book has already been uploaded",
        )
    
    # Save file
    file_path = os.path.join(
        settings.pdf_storage_path,
        str(user_id),
        f"{file_hash}.pdf",
    )
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Calculate deadline
    deadline = date.today() + timedelta(days=total_days)
    
    # Create book record
    book = Book(
        user_id=user_id,
        title=title,
        author=author,
        file_path=file_path,
        file_hash=file_hash,
        processing_status="ingesting_external",
        processing_step="Uploading to document service...",
    )
    db.add(book)
    await db.flush()
    
    # Create learning configuration
    learning_config = LearningConfig(
        user_id=user_id,
        book_id=book.id,
        learning_level=learning_level,
        study_all_chapters=True,
        deadline=deadline,
        daily_study_minutes=daily_minutes,
        quiz_frequency=quiz_frequency,
        questions_per_quiz=5,
        enable_reminders=True,
    )
    db.add(learning_config)
    
    await db.commit()
    await db.refresh(book)
    
    logger.info(
        "book_uploaded_with_config",
        user_id=str(user_id),
        book_id=str(book.id),
        total_days=total_days,
        daily_minutes=daily_minutes,
    )
    
    # Start Temporal workflow
    try:
        await start_document_ingestion_workflow(
            book_id=book.id,
            user_id=user_id,
            file_path=file_path,
            filename=file.filename,
        )
    except Exception as e:
        logger.exception("workflow_start_failed", book_id=str(book.id), error=str(e))
        book.processing_status = "pending"
        await db.commit()
    
    return BookUploadResponse(
        id=book.id,
        title=book.title,
        author=book.author,
        processing_status=book.processing_status,
        message="Book uploaded! Professor will create your learning plan.",
    )


@router.patch("/{book_id}", response_model=BookResponse)
async def update_book(
    book_id: UUID,
    updates: BookUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update book metadata."""
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(book, field, value)
    
    await db.commit()
    await db.refresh(book)
    
    return book


@router.delete("/{book_id}")
async def delete_book(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a book and all associated data."""
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    # Delete local file
    if os.path.exists(book.file_path):
        os.remove(book.file_path)
    
    # Delete from database (cascades to chapters, etc.)
    await db.delete(book)
    await db.commit()
    
    logger.info("book_deleted", user_id=str(user_id), book_id=str(book_id))
    
    return {"message": "Book deleted successfully"}


@router.get("/{book_id}/chapters", response_model=List[ChapterResponse])
async def get_book_chapters(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get chapters for a book."""
    # Verify book ownership
    book_result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = book_result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    # Get chapters
    chapters_result = await db.execute(
        select(BookChapter)
        .where(BookChapter.book_id == book_id)
        .order_by(BookChapter.chapter_number)
    )
    chapters = chapters_result.scalars().all()
    
    return [
        ChapterResponse(
            id=ch.id,
            chapter_number=ch.chapter_number,
            title=ch.title if ch.title and len(ch.title) > 2 else f"Chapter {ch.chapter_number}",
            start_page=ch.start_page,
            end_page=ch.end_page,
            summary=ch.summary,
            estimated_duration_minutes=ch.estimated_duration_minutes or 45,
        )
        for ch in chapters
    ]


class BookConfigRequest(BaseModel):
    """Book learning configuration request."""
    target_completion_date: str
    daily_study_minutes: int = Field(ge=15, le=480)
    learning_level: str
    quiz_frequency: str
    selected_chapters: List[int]


@router.post("/{book_id}/config")
async def save_book_config(
    book_id: UUID,
    config: BookConfigRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Save learning configuration for a book."""
    # Verify book ownership
    book_result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = book_result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    # Parse target date
    try:
        target_date = datetime.strptime(config.target_completion_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format",
        )
    
    # Check for existing config
    existing_result = await db.execute(
        select(LearningConfig).where(
            LearningConfig.book_id == book_id,
            LearningConfig.user_id == user_id
        )
    )
    existing_config = existing_result.scalar_one_or_none()
    
    if existing_config:
        existing_config.deadline = target_date
        existing_config.daily_study_minutes = config.daily_study_minutes
        existing_config.learning_level = config.learning_level
        existing_config.quiz_frequency = config.quiz_frequency
        existing_config.selected_chapters = config.selected_chapters
        existing_config.study_all_chapters = len(config.selected_chapters) == book.total_chapters
    else:
        new_config = LearningConfig(
            user_id=user_id,
            book_id=book_id,
            deadline=target_date,
            daily_study_minutes=config.daily_study_minutes,
            learning_level=config.learning_level,
            quiz_frequency=config.quiz_frequency,
            selected_chapters=config.selected_chapters,
            study_all_chapters=len(config.selected_chapters) == book.total_chapters,
        )
        db.add(new_config)
    
    await db.commit()
    
    logger.info(
        "book_config_saved",
        book_id=str(book_id),
        user_id=str(user_id),
    )
    
    return {"success": True, "message": "Configuration saved"}


@router.post("/{book_id}/reprocess")
async def reprocess_book(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger reprocessing of a book via external RAG service."""
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    # Reset status
    book.processing_status = "ingesting_external"
    book.processing_error = None
    book.processing_step = "Re-uploading to document service..."
    await db.commit()
    
    # Start new workflow
    try:
        await start_document_ingestion_workflow(
            book_id=book.id,
            user_id=user_id,
            file_path=book.file_path,
            filename=os.path.basename(book.file_path),
        )
    except Exception as e:
        logger.exception("reprocess_workflow_failed", book_id=str(book_id), error=str(e))
        book.processing_status = "failed"
        book.processing_error = str(e)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start reprocessing",
        )
    
    logger.info("book_reprocessing_triggered", book_id=str(book_id))
    
    return {"message": "Book reprocessing started"}
