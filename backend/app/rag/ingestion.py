"""High-performance PDF ingestion service with parallel processing."""

import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Tuple, Union
from uuid import UUID

import pdfplumber
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.models.book import Book, BookChapter
from app.models.learning import DocumentChunk
from app.rag.chapter_detection import ChapterDetector, DetectedChapter
from app.rag.chunking import SmartChunker, Chunk
from app.rag.embeddings import EmbeddingService

logger = get_logger(__name__)

# Thread pool for CPU-bound PDF operations
_executor = ThreadPoolExecutor(max_workers=4)


class PDFIngestionService:
    """
    High-performance PDF ingestion pipeline with parallel processing.
    
    Optimizations:
    - Async PDF extraction using thread pool
    - Parallel chapter processing
    - Batched embeddings (all chunks at once)
    - Minimal database commits
    """
    
    def __init__(
        self,
        db: AsyncSession,
        api_key: Optional[str] = None,
        cache=None,
    ):
        self.db = db
        self.chapter_detector = ChapterDetector()
        self.chunker = SmartChunker()
        self.embedding_service = EmbeddingService(api_key=api_key)
        self.cache = cache
    
    async def _update_progress(self, book: Book, progress: int, step: str):
        """Update book processing progress."""
        book.processing_progress = progress
        book.processing_step = step
        await self.db.commit()
    
    async def process_book(self, book: Book) -> bool:
        """
        Process a book with optimized parallel pipeline.
        
        Pipeline:
        1. Extract PDF text (async in thread pool)
        2. Detect chapters
        3. Chunk all chapters in parallel
        4. Batch embed ALL chunks at once
        5. Bulk insert to database
        """
        try:
            logger.info("book_processing_started", book_id=str(book.id))
            
            book.processing_status = "processing"
            await self._update_progress(book, 5, "Initializing...")
            
            # Phase 1: Extract text (5% - 20%)
            await self._update_progress(book, 10, "Extracting text...")
            pages = await self._extract_text_async(book.file_path)
            book.total_pages = len(pages)
            await self._update_progress(book, 20, f"Extracted {len(pages)} pages")
            
            # Phase 2: Detect chapters (20% - 30%)
            await self._update_progress(book, 25, "Detecting chapters...")
            chapters = await self.chapter_detector.detect_chapters(pages)
            book.total_chapters = len(chapters)
            await self._update_progress(book, 30, f"Found {len(chapters)} chapters")
            
            if not chapters:
                # No chapters found - create single chapter from all content
                chapters = [DetectedChapter(
                    chapter_number=1,
                    title=book.title,
                    start_page=0,
                    end_page=len(pages) - 1
                )]
                book.total_chapters = 1
            
            # Phase 3: Chunk all chapters in parallel (30% - 50%)
            await self._update_progress(book, 35, "Chunking content...")
            all_chunks, chapter_records = await self._chunk_all_chapters_parallel(
                book, chapters, pages
            )
            await self._update_progress(book, 50, f"Created {len(all_chunks)} chunks")
            
            # Phase 4: Batch embed ALL chunks at once (50% - 85%)
            await self._update_progress(book, 55, "Generating embeddings...")
            if all_chunks:
                all_chunks = await self._batch_embed_all(all_chunks)
            await self._update_progress(book, 85, "Embeddings complete")
            
            # Phase 5: Bulk insert (85% - 95%)
            await self._update_progress(book, 90, "Saving to database...")
            await self._bulk_insert_chunks(all_chunks)
            
            # Finalize
            book.processing_status = "completed"
            book.processing_progress = 100
            book.processing_step = "Complete"
            await self.db.commit()
            
            logger.info(
                "book_processing_completed",
                book_id=str(book.id),
                chapters=book.total_chapters,
                chunks=len(all_chunks),
            )
            
            return True
            
        except Exception as e:
            logger.exception("book_processing_failed", book_id=str(book.id), error=str(e))
            book.processing_status = "failed"
            book.processing_error = str(e)
            book.processing_step = "Failed"
            await self.db.commit()
            return False
    
    async def _extract_text_async(self, file_path: str) -> List[Tuple[int, str]]:
        """Extract PDF text asynchronously using thread pool."""
        loop = asyncio.get_event_loop()
        pages = await loop.run_in_executor(_executor, self._extract_text_sync, file_path)
        logger.info("pdf_extracted", pages=len(pages))
        return pages
    
    def _extract_text_sync(self, file_path: str) -> List[Tuple[int, str]]:
        """Synchronous PDF extraction (runs in thread pool)."""
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append((i, text))
        return pages
    
    async def _chunk_all_chapters_parallel(
        self,
        book: Book,
        chapters: List[DetectedChapter],
        pages: List[Tuple[int, str]],
    ) -> Tuple[List[Chunk], List[BookChapter]]:
        """
        Process all chapters in parallel and collect all chunks.
        """
        from sqlalchemy import select
        
        all_chunks = []
        chapter_records = []
        
        # Create all chapter records first
        for chapter_data in chapters:
            # Check if exists
            result = await self.db.execute(
                select(BookChapter).where(
                    BookChapter.book_id == book.id,
                    BookChapter.chapter_number == chapter_data.chapter_number,
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                chapter_records.append(existing)
                continue
            
            # Calculate duration
            start_page = chapter_data.start_page
            end_page = chapter_data.end_page or len(pages) - 1
            page_count = max(1, end_page - start_page + 1)
            duration = self.chapter_detector.estimate_duration(page_count)
            
            chapter = BookChapter(
                book_id=book.id,
                chapter_number=chapter_data.chapter_number,
                title=chapter_data.title or f"Chapter {chapter_data.chapter_number}",
                start_page=start_page,
                end_page=end_page,
                estimated_duration_minutes=duration,
            )
            self.db.add(chapter)
            chapter_records.append(chapter)
        
        await self.db.flush()  # Get IDs for all chapters
        
        # Now chunk all chapters (can be parallelized with thread pool)
        loop = asyncio.get_event_loop()
        chunk_tasks = []
        
        for i, (chapter_data, chapter_record) in enumerate(zip(chapters, chapter_records)):
            task = loop.run_in_executor(
                _executor,
                self._chunk_chapter_sync,
                chapter_data,
                chapter_record,
                pages,
                book.id,
            )
            chunk_tasks.append(task)
        
        # Gather all chunks from parallel processing
        chunk_results = await asyncio.gather(*chunk_tasks)
        for chunks in chunk_results:
            all_chunks.extend(chunks)
        
        return all_chunks, chapter_records
    
    def _chunk_chapter_sync(
        self,
        chapter_data: DetectedChapter,
        chapter_record: BookChapter,
        pages: List[Tuple[int, str]],
        book_id: UUID,
    ) -> List[Chunk]:
        """Synchronous chunking for a single chapter (runs in thread pool)."""
        start_page = chapter_data.start_page
        end_page = chapter_data.end_page or len(pages) - 1
        
        chapter_text = "\n\n".join(
            text for page_num, text in pages
            if start_page <= page_num <= end_page
        )
        
        chunks = self.chunker.chunk_chapter(
            chapter_text=chapter_text,
            chapter_id=chapter_record.id,
            book_id=book_id,
            page_offset=start_page,
        )
        
        return chunks
    
    async def _batch_embed_all(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        Embed ALL chunks in optimized batches.
        Uses larger batch size and parallel API calls.
        """
        return await self.embedding_service.embed_chunks(chunks, cache=self.cache)
    
    async def _bulk_insert_chunks(self, chunks: List[Chunk]) -> None:
        """Bulk insert all chunks efficiently."""
        for chunk in chunks:
            doc_chunk = DocumentChunk(
                book_id=chunk.book_id,
                chapter_id=chunk.chapter_id,
                section_title=chunk.section_title,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                token_count=chunk.token_count,
                embedding=chunk.embedding,
                chunk_metadata=chunk.metadata,
            )
            self.db.add(doc_chunk)
        
        await self.db.flush()
        logger.info("chunks_inserted", count=len(chunks))
    
    async def _process_chapter(
        self,
        book: Book,
        chapter_data: DetectedChapter,
        pages: List[Tuple[int, str]],
    ) -> Optional[BookChapter]:
        """
        Process a single chapter: create record, chunk, embed, store.
        """
        from sqlalchemy import select
        
        # Check if chapter already exists
        result = await self.db.execute(
            select(BookChapter).where(
                BookChapter.book_id == book.id,
                BookChapter.chapter_number == chapter_data.chapter_number,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.info(
                "chapter_already_exists",
                book_id=str(book.id),
                chapter_number=chapter_data.chapter_number,
            )
            return existing
        
        # Extract chapter text
        start_page = chapter_data.start_page
        end_page = chapter_data.end_page or len(pages) - 1
        
        chapter_text = "\n\n".join(
            text for page_num, text in pages
            if start_page <= page_num <= end_page
        )
        
        # Estimate duration
        page_count = max(1, end_page - start_page + 1)
        duration = self.chapter_detector.estimate_duration(page_count)
        
        # Create chapter record
        chapter = BookChapter(
            book_id=book.id,
            chapter_number=chapter_data.chapter_number,
            title=chapter_data.title or f"Chapter {chapter_data.chapter_number}",
            start_page=start_page,
            end_page=end_page,
            estimated_duration_minutes=duration,
        )
        self.db.add(chapter)
        await self.db.flush()
        
        # Chunk the chapter
        chunks = self.chunker.chunk_chapter(
            chapter_text=chapter_text,
            chapter_id=chapter.id,
            book_id=book.id,
            page_offset=start_page,
        )
        
        # Generate embeddings
        chunks = await self.embedding_service.embed_chunks(
            chunks,
            cache=self.cache,
        )
        
        # Store chunks
        for chunk in chunks:
            doc_chunk = DocumentChunk(
                book_id=book.id,
                chapter_id=chapter.id,
                section_title=chunk.section_title,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                token_count=chunk.token_count,
                embedding=chunk.embedding,
                chunk_metadata=chunk.metadata,
            )
            self.db.add(doc_chunk)
        
        await self.db.flush()
        
        return chapter
    
    async def reprocess_chapter(
        self,
        chapter: BookChapter,
        pages: List[Tuple[int, str]],
    ) -> None:
        """
        Reprocess a single chapter (e.g., after updates).
        """
        from sqlalchemy import delete
        
        # Delete existing chunks
        await self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.chapter_id == chapter.id)
        )
        
        # Extract chapter text
        start_page = chapter.start_page or 0
        end_page = chapter.end_page or len(pages) - 1
        
        chapter_text = "\n\n".join(
            text for page_num, text in pages
            if start_page <= page_num <= end_page
        )
        
        # Chunk and embed
        chunks = self.chunker.chunk_chapter(
            chapter_text=chapter_text,
            chapter_id=chapter.id,
            book_id=chapter.book_id,
            page_offset=start_page,
        )
        
        chunks = await self.embedding_service.embed_chunks(
            chunks,
            cache=self.cache,
        )
        
        # Store new chunks
        for chunk in chunks:
            doc_chunk = DocumentChunk(
                book_id=chapter.book_id,
                chapter_id=chapter.id,
                section_title=chunk.section_title,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                content_hash=chunk.content_hash,
                token_count=chunk.token_count,
                embedding=chunk.embedding,
                chunk_metadata=chunk.metadata,
            )
            self.db.add(doc_chunk)
        
        await self.db.flush()
        
        logger.info(
            "chapter_reprocessed",
            chapter_id=str(chapter.id),
            chunks=len(chunks),
        )
