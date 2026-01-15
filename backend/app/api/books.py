"""Book management API routes."""

import asyncio
import hashlib
import os
from datetime import datetime, date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db, async_session_maker
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.models.book import Book, BookChapter
from app.models.learning_config import LearningConfig, ConversationState

logger = get_logger(__name__)
router = APIRouter()


async def process_book_task(book_id: UUID):
    """
    Background task to process a book through RAG pipeline.
    
    Per Goals.md:
    - Step 2: Chunking happens
    - Step 3: When complete, Professor auto-triggers with greeting
    """
    from app.rag.ingestion import PDFIngestionService
    
    async with async_session_maker() as db:
        try:
            result = await db.execute(select(Book).where(Book.id == book_id))
            book = result.scalar_one_or_none()
            
            if not book:
                logger.error("book_not_found_for_processing", book_id=str(book_id))
                return
            
            # Get user's API key or use default
            from app.services.api_key_service import APIKeyService
            api_key_service = APIKeyService(db)
            api_key = await api_key_service.get_api_key_for_user(book.user_id)
            
            # Process book (Step 2: Chunking & Embeddings)
            ingestion_service = PDFIngestionService(db, api_key=api_key)
            success = await ingestion_service.process_book(book)
            
            if success:
                # Update status to ready_for_planning (not just completed)
                # This indicates chunking is done but professor hasn't greeted yet
                book.processing_status = "ready_for_planning"
                await db.commit()
                
                logger.info(
                    "book_processing_completed_ready_for_professor",
                    book_id=str(book_id),
                    user_id=str(book.user_id),
                )
                
                # Step 3: Trigger Professor Auto-Greeting
                # This creates the initial conversation state and sends greeting
                await trigger_professor_greeting(db, book)
                
            else:
                logger.error("book_processing_failed", book_id=str(book_id))
                
        except Exception as e:
            logger.exception("book_processing_error", book_id=str(book_id), error=str(e))
            # Update book status to failed
            result = await db.execute(select(Book).where(Book.id == book_id))
            book = result.scalar_one_or_none()
            if book:
                book.processing_status = "failed"
                book.processing_error = str(e)
                await db.commit()


async def trigger_professor_greeting(db: AsyncSession, book: Book):
    """
    Trigger professor's auto-greeting after book processing completes.
    
    Per Goals.md Step 3:
    > "Once chunking completes, the Professor Agent automatically triggers"
    
    This is a simple template greeting with dynamic book info.
    The REAL agents (PlannerAgent, TeachingAgent, QuizAgent) do the actual work.
    """
    from app.models.chat import ChatSession, ChatMessage
    from app.models.learning import LearningState
    
    try:
        # Create or get learning state
        result = await db.execute(
            select(LearningState)
            .where(LearningState.user_id == book.user_id)
            .where(LearningState.book_id == book.id)
        )
        learning_state = result.scalar_one_or_none()
        
        if not learning_state:
            learning_state = LearningState(
                user_id=book.user_id,
                book_id=book.id,
                current_chapter=1,
            )
            db.add(learning_state)
            await db.flush()
        
        # Create conversation state to track where we are
        conversation_state = ConversationState(
            user_id=book.user_id,
            book_id=book.id,
            phase="greeting",
            last_professor_action="greeting_sent",
        )
        db.add(conversation_state)
        
        # Create a chat session for this interaction
        session = ChatSession(
            user_id=book.user_id,
            learning_state_id=learning_state.id,
            book_id=book.id,
            chapter_context=1,
            session_type="onboarding",
        )
        db.add(session)
        await db.flush()
        
        # Get learning config for personalization
        config_result = await db.execute(
            select(LearningConfig).where(LearningConfig.book_id == book.id)
        )
        config = config_result.scalar_one_or_none()
        
        # Simple template greeting with dynamic data
        # The REAL work happens in PlannerAgent, TeachingAgent, QuizAgent
        level_note = {
            "beginner": "I'll explain concepts clearly with plenty of examples.",
            "intermediate": "I'll balance depth with clarity as we explore the material.",
            "advanced": "I'll dive deep into technical details and nuances.",
            "research": "I'll focus on advanced analysis and research implications.",
        }.get(config.learning_level if config else "intermediate", "")
        
        greeting = f"""Hello! 👋

I've finished analyzing **"{book.title}"**. I found **{book.total_chapters or 'several'} chapters** of material to explore together.

{level_note}

**Would you like me to create a personalized learning plan for you?**

The plan will include:
• A day-by-day schedule based on your timeline
• Estimated time for each chapter
• Quiz checkpoints to reinforce your learning

Just say **"Yes"** or **"Let's plan"** when you're ready!"""

        # Store the greeting message
        greeting_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=greeting,
            agent_name="Professor",
            chapter_at_time=1,
        )
        db.add(greeting_message)
        
        # Mark book as greeted
        book.professor_greeted = True
        book.professor_greeting_at = datetime.utcnow()
        book.processing_status = "completed"
        
        await db.commit()
        
        logger.info(
            "professor_greeting_triggered",
            book_id=str(book.id),
            user_id=str(book.user_id),
            session_id=str(session.id),
        )
        
    except Exception as e:
        logger.exception("professor_greeting_failed", book_id=str(book.id), error=str(e))
        await db.rollback()


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
    chapters: List["ChapterResponse"]

    class Config:
        from_attributes = True


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


class BookUpdateRequest(BaseModel):
    """Book update request."""
    title: Optional[str] = None
    author: Optional[str] = None


@router.get("/", response_model=List[BookResponse])
async def list_books(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all books for the current user."""
    # Expire all to ensure we get fresh data (for polling during processing)
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


class LearningConfigRequest(BaseModel):
    """Learning configuration collected during upload (per Goals.md Step 1)."""
    
    # Learning Level
    learning_level: str = Field(
        default="intermediate",
        description="Student level: beginner, intermediate, advanced, research"
    )
    
    # Chapter Selection
    study_all_chapters: bool = Field(
        default=True,
        description="Whether to study all chapters or selected ones"
    )
    selected_chapters: Optional[List[int]] = Field(
        default=None,
        description="List of chapter numbers to study (if not all)"
    )
    
    # Timeline
    deadline: Optional[date] = Field(
        default=None,
        description="Target completion date"
    )
    daily_study_minutes: int = Field(
        default=60,
        description="Preferred daily study time in minutes"
    )
    
    # Quiz Preferences
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
    
    # Reminders
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


class BookUploadResponse(BaseModel):
    """Response after uploading a book."""
    id: UUID
    title: str
    author: Optional[str]
    processing_status: str
    message: str
    
    class Config:
        from_attributes = True


@router.post("/upload", response_model=BookUploadResponse)
async def upload_book(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    # Learning Configuration (as JSON string in form data)
    learning_level: str = Form("intermediate"),
    study_all_chapters: bool = Form(True),
    selected_chapters: Optional[str] = Form(None),  # JSON array string
    deadline: Optional[str] = Form(None),  # ISO date string
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
    
    Per Goals.md Step 1, this collects:
    - Learning level (BTech / MTech / Research)
    - Chapters to study (full book or selected chapters)
    - Deadline / timeline
    - Quiz preferences
    - Reminder & inactivity preferences
    
    After upload, the book is processed asynchronously.
    When processing completes, Professor auto-triggers with greeting (Step 3).
    """
    import json
    
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
    
    # Save file
    file_path = os.path.join(
        settings.pdf_storage_path,
        str(user_id),
        f"{file_hash}.pdf",
    )
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Create book record
    book = Book(
        user_id=user_id,
        title=title or file.filename.replace(".pdf", ""),
        author=author,
        file_path=file_path,
        file_hash=file_hash,
        processing_status="pending",
    )
    db.add(book)
    await db.flush()  # Get book.id
    
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
        "book_uploaded_with_config",
        user_id=str(user_id),
        book_id=str(book.id),
        file_size_mb=round(file_size_mb, 2),
        learning_level=learning_level,
        quiz_frequency=quiz_frequency,
    )
    
    # Trigger async processing in background
    # When complete, professor will auto-greet (Step 3)
    background_tasks.add_task(process_book_task, book.id)
    
    return BookUploadResponse(
        id=book.id,
        title=book.title,
        author=book.author,
        processing_status=book.processing_status,
        message="Book uploaded successfully! Processing will begin shortly. "
                "Professor will greet you once the analysis is complete.",
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
    
    # Delete file
    if os.path.exists(book.file_path):
        os.remove(book.file_path)
    
    # Delete from database (cascades to chunks, chapters, etc.)
    await db.delete(book)
    await db.commit()
    
    logger.info("book_deleted", user_id=str(user_id), book_id=str(book_id))
    
    return {"message": "Book deleted successfully"}


@router.post("/{book_id}/reprocess")
async def reprocess_book(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger reprocessing of a book (admin or owner only)."""
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    # Update status
    book.processing_status = "pending"
    book.processing_error = None
    await db.commit()
    
    # Trigger async processing
    # await trigger_book_processing(book.id)
    
    logger.info("book_reprocessing_triggered", book_id=str(book_id))
    
    return {"message": "Book reprocessing started"}


class ChapterListResponse(BaseModel):
    """Chapter list response for configuration page."""
    id: UUID
    chapter_number: int
    title: str
    estimated_duration_minutes: int
    
    class Config:
        from_attributes = True


@router.get("/{book_id}/chapters", response_model=List[ChapterListResponse])
async def get_book_chapters(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get chapters for a book (for configuration page)."""
    from app.models.book import BookChapter
    
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
        ChapterListResponse(
            id=ch.id,
            chapter_number=ch.chapter_number,
            # Ensure meaningful title
            title=ch.title if ch.title and len(ch.title) > 2 and not ch.title.isdigit() else f"Chapter {ch.chapter_number}",
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
    from app.models.learning_config import LearningConfig
    from datetime import datetime
    
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
        # Update existing
        existing_config.deadline = target_date
        existing_config.daily_study_minutes = config.daily_study_minutes
        existing_config.learning_level = config.learning_level
        existing_config.quiz_frequency = config.quiz_frequency
        existing_config.selected_chapters = config.selected_chapters
        existing_config.study_all_chapters = len(config.selected_chapters) == book.total_chapters
    else:
        # Create new
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
        daily_minutes=config.daily_study_minutes,
        level=config.learning_level,
    )
    
    return {"success": True, "message": "Configuration saved"}


# ============================================================================
# UPLOAD WITH CONFIG ENDPOINT (for new UI flow)
# ============================================================================

@router.post("/upload-with-config", response_model=BookUploadResponse)
async def upload_book_with_config(
    background_tasks: BackgroundTasks,
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
    
    Per Goals.md Step 1:
    - Learning level
    - Days to complete (total_days)
    - Daily study time (daily_minutes)
    - Quiz frequency
    
    After processing, generates a day-by-day learning plan.
    """
    from datetime import timedelta
    
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
    
    # Save file
    file_path = os.path.join(
        settings.pdf_storage_path,
        str(user_id),
        f"{file_hash}.pdf",
    )
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Calculate deadline from total_days
    deadline = date.today() + timedelta(days=total_days)
    
    # Create book record
    book = Book(
        user_id=user_id,
        title=title,
        author=author,
        file_path=file_path,
        file_hash=file_hash,
        processing_status="pending",
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
        learning_level=learning_level,
    )
    
    # Trigger async processing
    background_tasks.add_task(process_book_task, book.id)
    
    return BookUploadResponse(
        id=book.id,
        title=book.title,
        author=book.author,
        processing_status=book.processing_status,
        message="Book uploaded! Professor will create your learning plan.",
    )


# ============================================================================
# LEARNING PLAN ENDPOINT
# ============================================================================

