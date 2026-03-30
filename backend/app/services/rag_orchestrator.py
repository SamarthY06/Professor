"""RAG Orchestrator - Smart query generation and RAG decision layer."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)


class RAGIntent(str, Enum):
    """What kind of RAG content is needed."""
    NONE = "none"
    CHAPTER_OVERVIEW = "chapter_overview"
    CONCEPT_EXPLANATION = "concept"
    CLARIFICATION = "clarification"
    DEEPER_DIVE = "deeper_dive"
    EXAMPLE = "example"
    SUMMARY = "summary"
    ANSWER_QUESTION = "answer"


@dataclass
class RAGDecision:
    """Result of the RAG decision layer."""
    should_call_rag: bool
    intent: RAGIntent
    generated_query: Optional[str]
    reasoning: str


@dataclass
class RAGContent:
    """Content retrieved from RAG service."""
    content: str
    chunks: List[Dict[str, Any]]
    query_used: str
    success: bool
    error_message: Optional[str] = None


@dataclass 
class TeachingContext:
    """Full context passed to TeacherAgent."""
    user_message: str
    rag_content: Optional[RAGContent]
    rag_decision: RAGDecision
    teaching_state: Dict[str, Any]


class RAGOrchestrator:
    """Orchestrates RAG decisions and query generation."""
    
    DECISION_PROMPT = """You are a teaching assistant helping decide if we need to look up content from the textbook.

CURRENT TEACHING STATE:
- Chapter: {chapter_number} - {chapter_title}
- Teaching Phase: {teaching_phase}
- Topics Already Covered: {topics_covered}
- Last Thing Taught: {last_topic}

STUDENT'S MESSAGE:
"{user_message}"

DECIDE: Does the teacher need content from the textbook to respond?

**IMPORTANT: When teaching, we should ALMOST ALWAYS use the textbook content.**
The teacher should teach FROM THE BOOK, not make up content.

ANSWER "NO" ONLY if:
- Student is asking about the learning process itself (not content)
- Student is asking to skip, pause, or change settings
- Student is giving personal feedback unrelated to content

ANSWER "YES" if (DEFAULT - when in doubt, say YES):
- Teacher needs to teach ANY concept (always use book content!)
- Student says "yes", "ok", "continue", "got it" (teacher should continue teaching from book)
- Student asks ANY question about the material
- Teacher is explaining, teaching, or continuing the lesson
- Student asks for examples, clarification, or deeper explanation
- ANY teaching activity is happening

Respond in this exact format:
DECISION: YES or NO
INTENT: chapter_overview | concept | clarification | deeper_dive | example | summary | answer | none
REASONING: One sentence explaining why"""

    QUERY_GENERATION_PROMPT = """Generate a search query to find relevant content from a textbook.

CONTEXT:
- Book: {book_title}
- Chapter: {chapter_number} - {chapter_title}
- Teaching Phase: {teaching_phase}
- Intent: {intent}
- Topics Already Covered: {topics_covered}

STUDENT'S MESSAGE (if relevant):
"{user_message}"

INTENT DESCRIPTIONS:
- chapter_overview: Find what topics/concepts this chapter covers
- concept: Find explanation of a specific concept
- clarification: Find simpler explanation or different angle
- deeper_dive: Find more detailed information
- example: Find examples or applications
- summary: Find key points for summarization
- answer: Find answer to student's specific question

Generate a FOCUSED search query (1-2 sentences) that will retrieve the most relevant content.
The query should be specific to the chapter and intent.

QUERY:"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self._decision_llm: Optional[ChatOpenAI] = None
        self._query_llm: Optional[ChatOpenAI] = None
    
    def _get_decision_llm(self) -> ChatOpenAI:
        if self._decision_llm is None:
            self._decision_llm = ChatOpenAI(
                model=settings.openai_model_mini,
                api_key=self.api_key,
                temperature=0.1,
                max_tokens=150,
            )
        return self._decision_llm
    
    def _get_query_llm(self) -> ChatOpenAI:
        if self._query_llm is None:
            self._query_llm = ChatOpenAI(
                model=settings.openai_model_mini,
                api_key=self.api_key,
                temperature=0.3,
                max_tokens=100,
            )
        return self._query_llm
    
    async def decide_and_fetch(
        self,
        user_message: str,
        book_id: str,
        chapter_number: int,
        chapter_title: str,
        teaching_phase: str,
        topics_covered: List[str],
        last_topic: Optional[str],
        user_id: str,
        book_title: str = "the textbook",
        force_rag: bool = True,  # Default to always use RAG when teaching
    ) -> TeachingContext:
        """Main entry point: Decide if RAG is needed and fetch content if so."""
        decision = await self._make_rag_decision(
            user_message=user_message,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            teaching_phase=teaching_phase,
            topics_covered=topics_covered,
            last_topic=last_topic,
        )
        
        # Override: When teaching, ALWAYS use RAG to get book content
        # Only skip RAG for explicit skip/settings requests
        skip_keywords = ["skip", "pause", "stop", "settings", "change", "quit", "exit"]
        user_lower = user_message.lower()
        is_skip_request = any(kw in user_lower for kw in skip_keywords)
        
        if force_rag and teaching_phase == "teaching" and not is_skip_request:
            decision.should_call_rag = True
            if decision.intent == RAGIntent.NONE:
                decision.intent = RAGIntent.CONCEPT_EXPLANATION
            decision.reasoning = f"Force RAG enabled for teaching phase. Original: {decision.reasoning}"
        
        logger.info(
            "rag_decision_made",
            should_call=decision.should_call_rag,
            intent=decision.intent.value,
            reasoning=decision.reasoning,
            user_id=user_id,
            chapter=chapter_number,
            force_rag=force_rag,
        )
        
        rag_content = None
        if decision.should_call_rag and decision.intent != RAGIntent.NONE:
            query = await self._generate_query(
                user_message=user_message,
                book_title=book_title,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                teaching_phase=teaching_phase,
                intent=decision.intent,
                topics_covered=topics_covered,
            )
            
            decision.generated_query = query
            
            rag_content = await self._fetch_from_rag(
                query=query,
                book_id=book_id,
                chapter_number=chapter_number,
                user_id=user_id,
            )
            
            logger.info(
                "rag_content_fetched",
                query=query,
                success=rag_content.success,
                chunks_count=len(rag_content.chunks),
                user_id=user_id,
            )
        
        return TeachingContext(
            user_message=user_message,
            rag_content=rag_content,
            rag_decision=decision,
            teaching_state={
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "teaching_phase": teaching_phase,
                "topics_covered": topics_covered,
                "last_topic": last_topic,
            },
        )
    
    async def _make_rag_decision(
        self,
        user_message: str,
        chapter_number: int,
        chapter_title: str,
        teaching_phase: str,
        topics_covered: List[str],
        last_topic: Optional[str],
    ) -> RAGDecision:
        llm = self._get_decision_llm()
        
        prompt = self.DECISION_PROMPT.format(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            teaching_phase=teaching_phase,
            topics_covered=", ".join(topics_covered) if topics_covered else "None yet",
            last_topic=last_topic or "Just starting",
            user_message=user_message,
        )
        
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            result = response.content.strip()
            
            should_call = "DECISION: YES" in result.upper()
            
            intent = RAGIntent.NONE
            for i in RAGIntent:
                if i.value in result.lower():
                    intent = i
                    break
            
            reasoning = "Unknown"
            if "REASONING:" in result:
                reasoning = result.split("REASONING:")[-1].strip()
            
            return RAGDecision(
                should_call_rag=should_call,
                intent=intent if should_call else RAGIntent.NONE,
                generated_query=None,
                reasoning=reasoning,
            )
            
        except Exception as e:
            logger.warning("rag_decision_failed", error=str(e))
            return RAGDecision(
                should_call_rag=True,
                intent=RAGIntent.CONCEPT_EXPLANATION,
                generated_query=None,
                reasoning=f"Decision failed, defaulting to RAG: {str(e)}",
            )
    
    async def _generate_query(
        self,
        user_message: str,
        book_title: str,
        chapter_number: int,
        chapter_title: str,
        teaching_phase: str,
        intent: RAGIntent,
        topics_covered: List[str],
    ) -> str:
        if intent == RAGIntent.CHAPTER_OVERVIEW:
            return f"What are the main topics, concepts, and sections covered in chapter {chapter_number}: {chapter_title}?"
        
        if intent == RAGIntent.SUMMARY:
            return f"What are the key takeaways, main points, and important concepts from chapter {chapter_number}: {chapter_title}?"
        
        llm = self._get_query_llm()
        
        prompt = self.QUERY_GENERATION_PROMPT.format(
            book_title=book_title,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            teaching_phase=teaching_phase,
            intent=intent.value,
            topics_covered=", ".join(topics_covered) if topics_covered else "None yet",
            user_message=user_message,
        )
        
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            query = response.content.strip()
            
            if query.startswith("QUERY:"):
                query = query[6:].strip()
            
            return query
            
        except Exception as e:
            logger.warning("query_generation_failed", error=str(e))
            return f"Explain the concepts in chapter {chapter_number}: {chapter_title}"
    
    async def _fetch_from_rag(
        self,
        query: str,
        book_id: str,
        chapter_number: int,
        user_id: str,
    ) -> RAGContent:
        from app.db.database import async_session_maker
        from app.models.book import Book, BookChapter
        from app.integrations.rag_client import get_rag_client, RAGClientError
        from sqlalchemy import select
        
        try:
            async with async_session_maker() as db:
                book_result = await db.execute(
                    select(Book).where(Book.id == UUID(book_id))
                )
                book = book_result.scalar_one_or_none()
                
                if not book or not book.book_metadata:
                    return RAGContent(
                        content="",
                        chunks=[],
                        query_used=query,
                        success=False,
                        error_message="Book not found or not processed",
                    )
                
                document_id = book.book_metadata.get("rag_document_id")
                if not document_id:
                    return RAGContent(
                        content="",
                        chunks=[],
                        query_used=query,
                        success=False,
                        error_message="Document not yet processed by RAG service",
                    )
                
                chapter_result = await db.execute(
                    select(BookChapter)
                    .where(BookChapter.book_id == book.id)
                    .where(BookChapter.chapter_number == chapter_number)
                )
                chapter = chapter_result.scalar_one_or_none()
                
                chapter_id = None
                if chapter and chapter.key_concepts:
                    chapter_id = chapter.key_concepts.get("rag_chapter_id")
            
            client = get_rag_client()
            
            if chapter_id:
                response = await client.search(
                    query=query,
                    document_id=document_id,
                    chapter_ids=[chapter_id],
                    limit=6,
                    user_id=user_id,
                )
            else:
                response = await client.search(
                    query=query,
                    document_id=document_id,
                    limit=6,
                    user_id=user_id,
                )
            
            chunks = [
                {
                    "content": r.content,
                    "section_title": r.section_title,
                    "similarity": r.similarity_score,
                    "chapter_number": r.chapter_number,
                }
                for r in response.results
            ]
            
            formatted_parts = []
            for i, chunk in enumerate(chunks, 1):
                section = f" ({chunk['section_title']})" if chunk.get('section_title') else ""
                formatted_parts.append(f"[Source {i}]{section}:\n{chunk['content']}")
            
            formatted_content = "\n\n---\n\n".join(formatted_parts) if formatted_parts else ""
            
            return RAGContent(
                content=formatted_content,
                chunks=chunks,
                query_used=query,
                success=True,
            )
            
        except RAGClientError as e:
            logger.warning("rag_fetch_failed", query=query, error=str(e))
            return RAGContent(
                content="",
                chunks=[],
                query_used=query,
                success=False,
                error_message=str(e),
            )
        except Exception as e:
            logger.exception("rag_fetch_error", query=query, error=str(e))
            return RAGContent(
                content="",
                chunks=[],
                query_used=query,
                success=False,
                error_message=str(e),
            )


async def get_teaching_context(
    user_message: str,
    state: Dict[str, Any],
    api_key: Optional[str] = None,
) -> TeachingContext:
    """Convenience function to get teaching context with RAG content."""
    orchestrator = RAGOrchestrator(api_key=api_key)
    
    return await orchestrator.decide_and_fetch(
        user_message=user_message,
        book_id=state.get("book_id", ""),
        chapter_number=state.get("current_chapter", 1),
        chapter_title=state.get("chapter_title", ""),
        teaching_phase=state.get("teaching_phase", "teaching"),
        topics_covered=state.get("topics_covered_this_chapter", []),
        last_topic=state.get("last_topic_discussed"),
        user_id=state.get("user_id", ""),
        book_title=state.get("book_title", "the textbook"),
    )
