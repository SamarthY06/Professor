"""Context compression for managing long-term memory."""

from typing import List, Optional
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.logs.logger import get_logger
from app.models.chat import ChatMessage
from app.models.learning import ChapterSummary

logger = get_logger(__name__)


class ContextCompressor:
    """
    Maintains compressed summaries of learning progress.
    Updates after each chapter completion.
    """
    
    CHAPTER_SUMMARY_PROMPT = """Summarize the student's learning journey through this chapter.

Recent Teaching Interactions:
{messages}

Key Concepts Covered:
{concepts}

Quiz Performance:
- Score: {quiz_score}%
- Weak Areas: {weak_areas}

Create a concise summary (100-150 words) that captures:
1. What the student learned
2. Key concepts they mastered
3. Areas that may need review
4. Their engagement and understanding level

Summary:"""
    
    META_COMPRESSION_PROMPT = """You have summaries from multiple chapters. Create a unified compressed memory.

Chapter Summaries:
{summaries}

Create a meta-summary (200-300 words) that:
1. Highlights the student's learning progression
2. Notes recurring strengths and weaknesses
3. Identifies patterns in understanding
4. Provides context for teaching future chapters

Compressed Memory:"""
    
    def __init__(
        self,
        db: AsyncSession,
        api_key: Optional[str] = None,
    ):
        self.db = db
        self._client: Optional[AsyncOpenAI] = None
        self._api_key = api_key
    
    def _get_client(self) -> AsyncOpenAI:
        """Get OpenAI client."""
        if self._client is None:
            api_key = self._api_key or settings.openai_api_key
            self._client = AsyncOpenAI(api_key=api_key)
        return self._client
    
    async def compress_chapter(
        self,
        user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        quiz_score: float = 0.0,
        weak_areas: List[str] = None,
    ) -> str:
        """
        Generate compressed summary when chapter is completed.
        
        Args:
            user_id: The user's ID
            book_id: The book's ID
            chapter_id: The completed chapter's ID
            quiz_score: Quiz score (0-1)
            weak_areas: List of weak topics
            
        Returns:
            The compressed summary
        """
        # Get recent messages from this chapter
        messages = await self._get_chapter_messages(user_id, chapter_id)
        
        # Extract concepts
        concepts = await self._extract_concepts(messages)
        
        # Generate summary
        prompt = self.CHAPTER_SUMMARY_PROMPT.format(
            messages=self._format_messages(messages[-20:]),
            concepts=", ".join(concepts) or "Various topics",
            quiz_score=int(quiz_score * 100),
            weak_areas=", ".join(weak_areas) if weak_areas else "None identified",
        )
        
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=settings.openai_model_mini,  # Use lighter model for compression
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.5,
            )
            summary = response.choices[0].message.content
        except Exception as e:
            logger.error("compression_failed", error=str(e))
            summary = f"Chapter completed with {int(quiz_score * 100)}% quiz score."
        
        # Store summary
        await self._store_summary(
            user_id=user_id,
            book_id=book_id,
            chapter_id=chapter_id,
            summary=summary,
            concepts=concepts,
        )
        
        logger.info(
            "chapter_compressed",
            user_id=str(user_id),
            chapter_id=str(chapter_id),
        )
        
        return summary
    
    async def build_cumulative_memory(
        self,
        user_id: UUID,
        book_id: UUID,
    ) -> str:
        """
        Build compressed memory of all completed chapters.
        
        Returns:
            Combined memory string
        """
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
            return "Beginning of learning journey - no prior chapters completed."
        
        if len(summaries) <= 5:
            # Just combine summaries
            return "\n\n".join(
                f"Chapter: {s.summary_text}"
                for s in summaries
            )
        
        # Need to further compress
        return await self._meta_compress([s.summary_text for s in summaries])
    
    async def _get_chapter_messages(
        self,
        user_id: UUID,
        chapter_id: UUID,
        limit: int = 50,
    ) -> List[ChatMessage]:
        """Get messages from a specific chapter."""
        from app.models.chat import ChatSession
        
        result = await self.db.execute(
            select(ChatMessage)
            .join(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatMessage.chapter_at_time == chapter_id,
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        
        return list(reversed(result.scalars().all()))
    
    async def _extract_concepts(
        self,
        messages: List[ChatMessage],
    ) -> List[str]:
        """Extract key concepts from messages."""
        # Simple extraction - in production would use NLP/LLM
        concepts = set()
        
        for msg in messages:
            if msg.role == "assistant":
                # Look for concept indicators
                content = msg.content.lower()
                if "key point" in content:
                    concepts.add("Key concepts discussed")
                if "example" in content:
                    concepts.add("Examples provided")
                if "practice" in content:
                    concepts.add("Practice exercises")
        
        return list(concepts)
    
    def _format_messages(
        self,
        messages: List[ChatMessage],
    ) -> str:
        """Format messages for the prompt."""
        formatted = []
        for msg in messages[-10:]:  # Last 10 messages
            role = "Student" if msg.role == "user" else "Professor"
            formatted.append(f"{role}: {msg.content[:200]}...")
        
        return "\n".join(formatted)
    
    async def _store_summary(
        self,
        user_id: UUID,
        book_id: UUID,
        chapter_id: UUID,
        summary: str,
        concepts: List[str],
    ) -> None:
        """Store chapter summary."""
        existing = await self.db.execute(
            select(ChapterSummary).where(
                ChapterSummary.user_id == user_id,
                ChapterSummary.chapter_id == chapter_id,
                ChapterSummary.summary_type == "completion",
            )
        )
        record = existing.scalar_one_or_none()
        
        if record:
            record.summary_text = summary
            record.key_concepts = {"concepts": concepts}
        else:
            record = ChapterSummary(
                user_id=user_id,
                book_id=book_id,
                chapter_id=chapter_id,
                summary_type="completion",
                summary_text=summary,
                key_concepts={"concepts": concepts},
            )
            self.db.add(record)
        
        await self.db.flush()
    
    async def _meta_compress(
        self,
        summaries: List[str],
    ) -> str:
        """Further compress multiple summaries into one."""
        prompt = self.META_COMPRESSION_PROMPT.format(
            summaries="\n\n".join(f"- {s}" for s in summaries)
        )
        
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.5,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("meta_compression_failed", error=str(e))
            # Fallback: truncate and combine
            return "\n".join(s[:100] for s in summaries[-5:])
