"""Temporal activities for document ingestion tracking.

These activities handle communication with the external RAG service
and update ProfessorOS database with ingestion progress.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from temporalio import activity

from app.logs.logger import get_logger

logger = get_logger(__name__)


@activity.defn
async def upload_document_to_rag(
    file_path: str,
    filename: str,
    user_id: str,
    book_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Upload a document to the external RAG service.
    
    Args:
        file_path: Path to the PDF file
        filename: Original filename
        user_id: User ID
        book_id: Book ID in Professor DB
        metadata: Optional metadata
    
    Returns:
        Dict with document_id and status
    """
    from app.integrations.rag_client import get_rag_client
    from fastapi import UploadFile
    import aiofiles
    
    client = get_rag_client()
    
    # Read file and create UploadFile-like object
    async with aiofiles.open(file_path, 'rb') as f:
        content = await f.read()
    
    # Create a file-like object for upload
    from io import BytesIO
    file_obj = BytesIO(content)
    
    # Create mock UploadFile
    class MockUploadFile:
        def __init__(self, filename: str, content: bytes):
            self.filename = filename
            self._content = content
            self.content_type = "application/pdf"
        
        async def read(self):
            return self._content
        
        async def seek(self, pos):
            pass
    
    mock_file = MockUploadFile(filename, content)
    
    try:
        response = await client.upload_document(
            file=mock_file,
            user_id=user_id,
            metadata={
                "professor_book_id": book_id,
                "user_id": user_id,
                **(metadata or {}),
            },
        )
        
        logger.info(
            "document_uploaded_to_rag",
            document_id=response.document_id,
            book_id=book_id,
            user_id=user_id,
        )
        
        return {
            "document_id": response.document_id,
            "status": response.status,
            "filename": response.filename,
        }
        
    except Exception as e:
        logger.exception(
            "document_upload_failed",
            book_id=book_id,
            user_id=user_id,
            error=str(e),
        )
        raise


@activity.defn
async def poll_ingestion_progress(
    document_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Poll the RAG service for ingestion progress.
    
    Args:
        document_id: RAG document ID
        user_id: User ID for logging
    
    Returns:
        Dict with progress information including cost
    """
    from app.integrations.rag_client import get_rag_client
    
    client = get_rag_client()
    
    try:
        progress = await client.get_document_progress(document_id, user_id)
        
        result = {
            "document_id": progress.document_id,
            "status": progress.status,
            "progress_percentage": progress.percentage,
            "current_step": progress.current_phase,
            "total_chapters": progress.total_chapters,
            "completed_chapters": progress.completed_chapters,
            "error_message": progress.error_reason,
            "is_complete": progress.is_complete,
            "is_failed": progress.is_failed,
        }
        
        # Include cost information if available
        if progress.cost:
            result["cost"] = {
                "embedding_cost": progress.cost.embedding_cost,
                "toc_detection_cost": progress.cost.toc_detection_cost,
                "image_summary_cost": progress.cost.image_summary_cost,
                "total_cost": progress.cost.total_cost,
                "total_tokens": progress.cost.total_tokens,
            }
        
        return result
        
    except Exception as e:
        logger.exception(
            "ingestion_progress_poll_failed",
            document_id=document_id,
            error=str(e),
        )
        raise


@activity.defn
async def update_book_progress(
    book_id: str,
    progress_data: Dict[str, Any],
) -> None:
    """
    Update book processing progress in Professor DB.
    
    Args:
        book_id: Book ID in Professor DB
        progress_data: Progress data from RAG service
    """
    from app.db.database import async_session_maker
    from app.models.book import Book
    from sqlalchemy import select
    
    async with async_session_maker() as db:
        result = await db.execute(
            select(Book).where(Book.id == UUID(book_id))
        )
        book = result.scalar_one_or_none()
        
        if not book:
            logger.warning("book_not_found_for_progress_update", book_id=book_id)
            return
        
        # Map RAG status to Professor status
        rag_status = progress_data.get("status", "INGESTING")
        if rag_status == "COMPLETED":
            book.processing_status = "ready_for_planning"
        elif rag_status == "FAILED":
            book.processing_status = "failed"
            book.processing_error = progress_data.get("error_message")
        else:
            book.processing_status = "ingesting_external"
        
        book.processing_progress = int(progress_data.get("progress_percentage", 0))
        book.processing_step = progress_data.get("current_step", "Processing...")
        
        if progress_data.get("total_chapters"):
            book.total_chapters = progress_data["total_chapters"]
        
        await db.commit()
        
        logger.info(
            "book_progress_updated",
            book_id=book_id,
            status=book.processing_status,
            progress=book.processing_progress,
        )


@activity.defn
async def log_rag_processing_cost(
    book_id: str,
    user_id: str,
    document_id: str,
    cost_data: Dict[str, Any],
) -> None:
    """
    Log RAG document processing cost to usage tracking.
    
    Called when document ingestion completes with final cost breakdown.
    
    Args:
        book_id: Book ID in Professor DB
        user_id: User who uploaded the document
        document_id: RAG service document ID
        cost_data: Cost breakdown from RAG service
    """
    from app.db.database import async_session_maker
    from app.services.usage_service import UsageService
    
    async with async_session_maker() as db:
        usage_service = UsageService(db)
        
        try:
            await usage_service.log_rag_document_processing(
                user_id=UUID(user_id),
                book_id=UUID(book_id),
                document_id=document_id,
                embedding_cost=cost_data.get("embedding_cost", "0.00000000"),
                toc_detection_cost=cost_data.get("toc_detection_cost", "0.00000000"),
                image_summary_cost=cost_data.get("image_summary_cost", "0.00000000"),
                total_cost=cost_data.get("total_cost", "0.00000000"),
                total_tokens=cost_data.get("total_tokens", 0),
            )
            
            logger.info(
                "rag_processing_cost_logged",
                book_id=book_id,
                user_id=user_id,
                document_id=document_id,
                total_cost=cost_data.get("total_cost"),
            )
        except Exception as e:
            logger.exception(
                "failed_to_log_rag_cost",
                book_id=book_id,
                user_id=user_id,
                error=str(e),
            )
            # Don't raise - cost logging failure shouldn't fail the workflow


@activity.defn
async def fetch_and_store_toc(
    document_id: str,
    book_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Fetch chapters from RAG service and store in Professor DB.
    
    Args:
        document_id: RAG document ID
        book_id: Book ID in Professor DB
        user_id: User ID
    
    Returns:
        Dict with chapter information
    """
    from app.integrations.rag_client import get_rag_client
    from app.db.database import async_session_maker
    from app.models.book import Book, BookChapter
    from sqlalchemy import select
    
    client = get_rag_client()
    
    try:
        # Use list_chapters which returns ChapterInfo objects
        chapters = await client.list_chapters(document_id, user_id)
        
        async with async_session_maker() as db:
            # Update book
            result = await db.execute(
                select(Book).where(Book.id == UUID(book_id))
            )
            book = result.scalar_one_or_none()
            
            if not book:
                raise ValueError(f"Book not found: {book_id}")
            
            book.total_chapters = len(chapters)
            
            # Store external document ID for future reference
            if not book.book_metadata:
                book.book_metadata = {}
            book.book_metadata["rag_document_id"] = document_id
            
            # Create chapter records
            chapters_created = []
            for chapter in chapters:
                # Check if chapter exists
                existing = await db.execute(
                    select(BookChapter).where(
                        BookChapter.book_id == book.id,
                        BookChapter.chapter_number == chapter.chapter_number,
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                
                # Calculate estimated duration based on page count
                page_count = chapter.end_page - chapter.start_page + 1
                estimated_minutes = max(15, page_count * 2)  # ~2 min per page
                
                book_chapter = BookChapter(
                    book_id=book.id,
                    chapter_number=chapter.chapter_number,
                    title=chapter.title,
                    start_page=chapter.start_page,
                    end_page=chapter.end_page,
                    estimated_duration_minutes=estimated_minutes,
                )
                
                # Store RAG chapter ID in key_concepts for reference
                book_chapter.key_concepts = {"rag_chapter_id": chapter.id}
                
                db.add(book_chapter)
                chapters_created.append({
                    "chapter_number": chapter.chapter_number,
                    "title": chapter.title,
                    "rag_chapter_id": chapter.id,
                })
            
            await db.commit()
            
            logger.info(
                "toc_stored",
                book_id=book_id,
                document_id=document_id,
                chapters_created=len(chapters_created),
            )
            
            return {
                "document_id": document_id,
                "book_id": book_id,
                "total_chapters": len(chapters),
                "chapters": chapters_created,
            }
            
    except Exception as e:
        logger.exception(
            "toc_fetch_failed",
            document_id=document_id,
            book_id=book_id,
            error=str(e),
        )
        raise


@activity.defn
async def fetch_chapter_summaries(
    document_id: str,
    book_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Fetch summaries for all chapters from RAG service in parallel batches.
    
    This queries the RAG service for each chapter to get a summary of topics
    that will be covered, enabling better plan generation.
    
    Args:
        document_id: RAG document ID
        book_id: Book ID in Professor DB
        user_id: User ID
    
    Returns:
        Dict with chapter summaries
    """
    import asyncio
    from app.integrations.rag_client import get_rag_client
    from app.db.database import async_session_maker
    from app.models.book import Book, BookChapter
    from sqlalchemy import select
    
    client = get_rag_client()
    
    async with async_session_maker() as db:
        # Get all chapters for this book
        result = await db.execute(
            select(BookChapter)
            .where(BookChapter.book_id == UUID(book_id))
            .order_by(BookChapter.chapter_number)
        )
        chapters = result.scalars().all()
        
        if not chapters:
            logger.warning("no_chapters_found", book_id=book_id)
            return {"book_id": book_id, "summaries": []}
        
        async def fetch_chapter_summary(chapter: BookChapter) -> Dict[str, Any]:
            """Fetch summary for a single chapter."""
            try:
                # Get RAG chapter ID from key_concepts
                rag_chapter_id = None
                if chapter.key_concepts:
                    rag_chapter_id = chapter.key_concepts.get("rag_chapter_id")
                
                if not rag_chapter_id:
                    logger.warning(
                        "no_rag_chapter_id",
                        chapter_number=chapter.chapter_number,
                        book_id=book_id,
                    )
                    return {
                        "chapter_number": chapter.chapter_number,
                        "summary": None,
                        "topics": [],
                    }
                
                # Query RAG for chapter summary
                # Use a summary-focused query
                summary_query = f"Summarize the main topics and key concepts covered in chapter {chapter.chapter_number}: {chapter.title}"
                
                search_result = await client.search_chapter(
                    query=summary_query,
                    document_id=document_id,
                    chapter_id=rag_chapter_id,
                    limit=5,
                    user_id=user_id,
                )
                
                # Combine results into a summary
                if search_result.results:
                    content_parts = [r.content for r in search_result.results[:3]]
                    summary = " ".join(content_parts)[:1000]  # Limit summary length
                    
                    # Extract topics from the content
                    topics = []
                    for r in search_result.results:
                        if hasattr(r, 'metadata') and r.metadata:
                            if 'topic' in r.metadata:
                                topics.append(r.metadata['topic'])
                    
                    return {
                        "chapter_number": chapter.chapter_number,
                        "summary": summary,
                        "topics": topics[:5],  # Limit to 5 topics
                    }
                else:
                    return {
                        "chapter_number": chapter.chapter_number,
                        "summary": f"Chapter {chapter.chapter_number}: {chapter.title}",
                        "topics": [],
                    }
                    
            except Exception as e:
                logger.warning(
                    "chapter_summary_fetch_failed",
                    chapter_number=chapter.chapter_number,
                    error=str(e),
                )
                return {
                    "chapter_number": chapter.chapter_number,
                    "summary": f"Chapter {chapter.chapter_number}: {chapter.title}",
                    "topics": [],
                }
        
        # Fetch summaries in parallel batches of 5
        batch_size = 5
        all_summaries = []
        
        for i in range(0, len(chapters), batch_size):
            batch = chapters[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[fetch_chapter_summary(ch) for ch in batch],
                return_exceptions=True
            )
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.warning("batch_summary_error", error=str(result))
                else:
                    all_summaries.append(result)
        
        # Update chapters with summaries
        for summary_data in all_summaries:
            chapter_num = summary_data["chapter_number"]
            summary_text = summary_data.get("summary")
            
            if summary_text:
                # Find and update the chapter
                for chapter in chapters:
                    if chapter.chapter_number == chapter_num:
                        chapter.summary = summary_text
                        break
        
        await db.commit()
        
        logger.info(
            "chapter_summaries_fetched",
            book_id=book_id,
            total_chapters=len(chapters),
            summaries_fetched=len(all_summaries),
        )
        
        return {
            "book_id": book_id,
            "document_id": document_id,
            "summaries": all_summaries,
        }


@activity.defn
async def mark_book_ready_for_planning(
    book_id: str,
    document_id: str,
) -> None:
    """
    Mark book as ready for planning after successful ingestion.
    
    Args:
        book_id: Book ID in Professor DB
        document_id: RAG document ID
    """
    from app.db.database import async_session_maker
    from app.models.book import Book
    from sqlalchemy import select
    
    async with async_session_maker() as db:
        result = await db.execute(
            select(Book).where(Book.id == UUID(book_id))
        )
        book = result.scalar_one_or_none()
        
        if not book:
            logger.warning("book_not_found", book_id=book_id)
            return
        
        book.processing_status = "ready_for_planning"
        book.processing_progress = 100
        book.processing_step = "Ready for planning"
        
        # Ensure document ID is stored
        if not book.book_metadata:
            book.book_metadata = {}
        book.book_metadata["rag_document_id"] = document_id
        
        await db.commit()
        
        logger.info(
            "book_ready_for_planning",
            book_id=book_id,
            document_id=document_id,
        )


@activity.defn
async def mark_book_ingestion_failed(
    book_id: str,
    error_message: str,
) -> None:
    """
    Mark book ingestion as failed.
    
    Args:
        book_id: Book ID in Professor DB
        error_message: Error message
    """
    from app.db.database import async_session_maker
    from app.models.book import Book
    from sqlalchemy import select
    
    async with async_session_maker() as db:
        result = await db.execute(
            select(Book).where(Book.id == UUID(book_id))
        )
        book = result.scalar_one_or_none()
        
        if not book:
            return
        
        book.processing_status = "failed"
        book.processing_error = error_message
        book.processing_step = "Failed"
        
        await db.commit()
        
        logger.error(
            "book_ingestion_failed",
            book_id=book_id,
            error=error_message,
        )


@activity.defn
async def trigger_professor_greeting(
    book_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Trigger professor greeting after successful ingestion.
    
    Args:
        book_id: Book ID
        user_id: User ID
    
    Returns:
        Dict with session info
    """
    from app.db.database import async_session_maker
    from app.models.book import Book
    from app.models.chat import ChatSession, ChatMessage
    from app.models.learning import LearningState
    from app.models.learning_config import LearningConfig
    from sqlalchemy import select
    
    async with async_session_maker() as db:
        # Get book
        result = await db.execute(
            select(Book).where(Book.id == UUID(book_id))
        )
        book = result.scalar_one_or_none()
        
        if not book:
            raise ValueError(f"Book not found: {book_id}")
        
        # Create or get learning state (use first() to tolerate duplicates)
        result = await db.execute(
            select(LearningState)
            .where(LearningState.user_id == UUID(user_id))
            .where(LearningState.book_id == book.id)
            .order_by(LearningState.created_at.desc())
            .limit(1)
        )
        learning_state = result.scalars().first()
        
        if not learning_state:
            learning_state = LearningState(
                user_id=UUID(user_id),
                book_id=book.id,
                current_chapter=1,
            )
            db.add(learning_state)
            await db.flush()
        
        # Set phase on learning state — start in config_gathering so the
        # planner agent drives the first conversation turn.
        learning_state.current_phase = "config_gathering"

        # Create chat session
        session = ChatSession(
            user_id=UUID(user_id),
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
        
        # Generate greeting
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

        # Store greeting message — use PlannerAgent so init_or_get_session
        # recognises this as the planner greeting and doesn't create a duplicate.
        greeting_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=greeting,
            agent_name="PlannerAgent",
            chapter_at_time=1,
        )
        db.add(greeting_message)
        
        # Mark book as greeted
        book.professor_greeted = True
        book.professor_greeting_at = datetime.utcnow()
        book.processing_status = "completed"
        
        await db.commit()
        
        logger.info(
            "professor_greeting_sent",
            book_id=book_id,
            user_id=user_id,
            session_id=str(session.id),
        )
        
        return {
            "session_id": str(session.id),
            "learning_state_id": str(learning_state.id),
            "greeting_sent": True,
        }
