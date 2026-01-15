"""Context engine for managing learning context."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.models.book import Book, BookChapter
from app.models.learning import LearningState, ChapterSummary

logger = get_logger(__name__)


class ContextEngine:
    """
    Manages context assembly for LLM prompts.
    Implements hierarchical context layers.
    """
    
    def __init__(self, db: AsyncSession, cache=None):
        self.db = db
        self.cache = cache
    
    async def build_context(
        self,
        user_id: UUID,
        book_id: UUID,
        current_chapter: int,
        user_query: str,
    ) -> Dict[str, Any]:
        """
        Build complete context for a teaching response.
        
        Returns:
            Dict with all context layers
        """
        context = {
            "system_context": await self._build_system_context(),
            "user_state": await self._build_user_state_context(user_id, book_id),
            "compressed_memory": await self._build_compressed_memory(user_id, book_id),
            "chapter_context": await self._build_chapter_context(book_id, current_chapter),
            "conversation_context": await self._get_recent_conversation(user_id, book_id),
        }
        
        # Calculate total tokens
        total_tokens = sum(
            self._estimate_tokens(str(v))
            for v in context.values()
        )
        
        logger.info(
            "context_built",
            user_id=str(user_id),
            total_tokens=total_tokens,
        )
        
        return context
    
    async def _build_system_context(self) -> str:
        """Layer 1: System context (always present)."""
        return """You are Professor, an AI-powered personalized learning assistant.

Your teaching principles:
1. Explain concepts clearly with relevant examples
2. Adapt to the student's level (beginner/intermediate/advanced)
3. Build on prior knowledge from previous chapters
4. Encourage questions and critical thinking
5. Provide constructive feedback on quiz answers

Rules:
- Stay focused on the current chapter's material
- Do not reveal answers to quiz questions prematurely
- Be encouraging but maintain academic rigor
- Use analogies appropriate for the student's level"""
    
    async def _build_user_state_context(
        self,
        user_id: UUID,
        book_id: UUID,
    ) -> str:
        """Layer 2: User state context."""
        result = await self.db.execute(
            select(LearningState).where(
                LearningState.user_id == user_id,
                LearningState.book_id == book_id,
            )
        )
        state = result.scalar_one_or_none()
        
        if not state:
            return "New student, no prior learning history."
        
        completed = state.completed_chapters or []
        
        return f"""Student Progress:
- Current Chapter: {state.current_chapter}
- Completed Chapters: {', '.join(map(str, completed)) or 'None yet'}
- Learning Level: {state.professor_level}
- Strict Mode: {'Yes' if state.strict_mode else 'No'}
- Motivation Score: {state.motivation_score:.0%}
- Comprehension Score: {state.comprehension_score:.0%}
- Total Study Time: {state.total_study_time_minutes} minutes"""
    
    async def _build_compressed_memory(
        self,
        user_id: UUID,
        book_id: UUID,
    ) -> str:
        """Layer 3: Compressed memory of previous chapters."""
        result = await self.db.execute(
            select(ChapterSummary)
            .where(
                ChapterSummary.user_id == user_id,
                ChapterSummary.book_id == book_id,
                ChapterSummary.summary_type == "completion",
            )
            .order_by(ChapterSummary.created_at)
        )
        summaries = result.scalars().all()
        
        if not summaries:
            return "This is the beginning of the learning journey."
        
        memory_parts = []
        for summary in summaries:
            memory_parts.append(f"Chapter {summary.chapter_id}: {summary.summary_text[:200]}")
        
        return "Previous Learning Summary:\n" + "\n".join(memory_parts)
    
    async def _build_chapter_context(
        self,
        book_id: UUID,
        chapter_number: int,
    ) -> str:
        """Layer 4: Current chapter context."""
        # Get chapter info
        result = await self.db.execute(
            select(BookChapter).where(
                BookChapter.book_id == book_id,
                BookChapter.chapter_number == chapter_number,
            )
        )
        chapter = result.scalar_one_or_none()
        
        if not chapter:
            return "Chapter information not available."
        
        context = f"""Current Chapter: {chapter.chapter_number} - {chapter.title or 'Untitled'}

Overview: {chapter.summary or 'No summary available.'}

Key Concepts: {', '.join(chapter.key_concepts.get('concepts', [])) if chapter.key_concepts else 'Not extracted yet.'}"""
        
        return context
    
    async def _get_recent_conversation(
        self,
        user_id: UUID,
        book_id: UUID,
        limit: int = 10,
    ) -> str:
        """Layer 5: Recent conversation context."""
        # Check cache first
        if self.cache:
            cached = await self.cache.get(f"convo:{user_id}:{book_id}")
            if cached:
                return cached
        
        # Would fetch from chat_messages table
        return "Starting a new conversation."
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        # Rough estimate: ~4 characters per token
        return len(text) // 4
    
    async def update_chapter_summary(
        self,
        user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        summary: str,
        key_concepts: List[str],
    ) -> None:
        """Update chapter summary after completion."""
        existing = await self.db.execute(
            select(ChapterSummary).where(
                ChapterSummary.user_id == user_id,
                ChapterSummary.chapter_id == chapter_id,
                ChapterSummary.summary_type == "completion",
            )
        )
        summary_record = existing.scalar_one_or_none()
        
        if summary_record:
            summary_record.summary_text = summary
            summary_record.key_concepts = {"concepts": key_concepts}
        else:
            summary_record = ChapterSummary(
                user_id=user_id,
                book_id=book_id,
                chapter_id=chapter_id,
                summary_type="completion",
                summary_text=summary,
                key_concepts={"concepts": key_concepts},
                token_count=self._estimate_tokens(summary),
            )
            self.db.add(summary_record)
        
        await self.db.flush()
        
        logger.info(
            "chapter_summary_updated",
            user_id=str(user_id),
            chapter_id=str(chapter_id),
        )
