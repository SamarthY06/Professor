"""RAG Tool for TeacherAgent - Fetches content from textbook via RAG service.

This tool is designed to be called by the TeacherAgent when it needs to:
1. Get the NEXT topic to teach (incremental progression)
2. Answer a specific question from the book
3. Get examples or deeper explanations

The tool generates smart queries that:
- Include context of what's already been covered
- Ask for the NEXT topic (not random content)
- Are scoped to the current chapter only
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)


class RAGToolInput(BaseModel):
    """Input schema for RAG tool."""
    topics_covered_summary: str = Field(
        description="Brief summary of topics already covered in this session (e.g., 'We covered configuration space basics, degrees of freedom')"
    )
    query_type: str = Field(
        default="next_topic",
        description="Type of query: 'next_topic' (get next content to teach), 'clarify' (explain current topic differently), 'example' (get examples), 'answer' (answer specific question)"
    )
    specific_question: Optional[str] = Field(
        default=None,
        description="If query_type is 'answer' or 'clarify', the specific question or topic to address"
    )


@dataclass
class RAGToolResult:
    """Result from RAG tool."""
    content: str
    source_sections: List[str]
    query_used: str
    success: bool
    error_message: Optional[str] = None


class RAGTool:
    """
    RAG Tool for fetching textbook content.
    
    This tool is called by TeacherAgent to get content from the book.
    It generates smart queries based on what's been covered and what's needed next.
    """
    
    def __init__(
        self,
        book_id: str,
        document_id: str,
        chapter_number: int,
        chapter_title: str,
        chapter_id: Optional[str] = None,
        user_id: str = "",
        openai_key: Optional[str] = None,
    ):
        self.book_id = book_id
        self.document_id = document_id
        self.chapter_number = chapter_number
        self.chapter_title = chapter_title
        self.chapter_id = chapter_id
        self.user_id = user_id
        self.openai_key = openai_key  # For BYOK users
    
    def _generate_query(
        self,
        topics_covered_summary: str,
        query_type: str,
        specific_question: Optional[str] = None,
    ) -> str:
        """Generate a smart query for RAG service."""
        
        if query_type == "next_topic":
            # Core query: Get the NEXT topic after what's been covered
            if topics_covered_summary and topics_covered_summary.strip():
                query = (
                    f"In Chapter {self.chapter_number} ({self.chapter_title}), "
                    f"the following topics have already been covered: {topics_covered_summary}. "
                    f"What is the NEXT topic or concept that should be taught? "
                    f"Provide the content, explanations, and key points for this next topic."
                )
            else:
                # Starting fresh - get the first topic
                query = (
                    f"What are the first main concepts and topics covered in Chapter {self.chapter_number} ({self.chapter_title})? "
                    f"Provide the introductory content, key definitions, and foundational concepts."
                )
        
        elif query_type == "clarify":
            topic = specific_question or "the current topic"
            query = (
                f"In Chapter {self.chapter_number} ({self.chapter_title}), "
                f"provide a clearer explanation of: {topic}. "
                f"Use simpler terms, analogies, or different perspectives."
            )
        
        elif query_type == "example":
            topic = specific_question or "the concepts discussed"
            query = (
                f"In Chapter {self.chapter_number} ({self.chapter_title}), "
                f"provide examples and applications for: {topic}. "
                f"Include practical examples, worked problems, or real-world applications."
            )
        
        elif query_type == "answer":
            if specific_question:
                query = (
                    f"In Chapter {self.chapter_number} ({self.chapter_title}), "
                    f"answer this question: {specific_question}"
                )
            else:
                query = f"Explain the main concepts in Chapter {self.chapter_number} ({self.chapter_title})"
        
        else:
            # Default: get next content
            query = (
                f"What are the key concepts and content in Chapter {self.chapter_number} ({self.chapter_title})?"
            )
        
        return query
    
    async def fetch_content(
        self,
        topics_covered_summary: str,
        query_type: str = "next_topic",
        specific_question: Optional[str] = None,
    ) -> RAGToolResult:
        """
        Fetch content from RAG service.
        
        Args:
            topics_covered_summary: What's been covered so far
            query_type: Type of content needed
            specific_question: Specific question if applicable
        
        Returns:
            RAGToolResult with content from the book
        """
        from app.integrations.rag_client import get_rag_client, RAGClientError
        
        query = self._generate_query(topics_covered_summary, query_type, specific_question)
        
        logger.info(
            "rag_tool_query",
            query=query,
            query_type=query_type,
            chapter=self.chapter_number,
            user_id=self.user_id,
        )
        
        try:
            client = get_rag_client()

            # First try chapter-scoped search
            if self.chapter_id:
                response = await client.search(
                    query=query,
                    document_id=self.document_id,
                    chapter_ids=[self.chapter_id],
                    limit=5,
                    user_id=self.user_id,
                    openai_key=self.openai_key,
                )

                # Fallback: if chapter-scoped returned < 2 results, retry document-wide
                if len(response.results or []) < 2:
                    logger.info(
                        "rag_tool_cross_chapter_fallback",
                        chapter=self.chapter_number,
                        chapter_results=len(response.results or []),
                        query_type=query_type,
                    )
                    fallback = await client.search(
                        query=query,
                        document_id=self.document_id,
                        limit=5,
                        user_id=self.user_id,
                        openai_key=self.openai_key,
                    )
                    if len(fallback.results or []) > len(response.results or []):
                        response = fallback
            else:
                response = await client.search(
                    query=query,
                    document_id=self.document_id,
                    limit=5,
                    user_id=self.user_id,
                    openai_key=self.openai_key,
                )

            if response.cost and self.user_id:
                await self._log_search_cost(response.cost, query_type)

            if not response.results:
                return RAGToolResult(
                    content="",
                    source_sections=[],
                    query_used=query,
                    success=False,
                    error_message="No relevant content found in this chapter",
                )
            
            # Format the content for the teacher
            content_parts = []
            source_sections = []
            
            for i, result in enumerate(response.results, 1):
                section = result.section_title or f"Section {i}"
                source_sections.append(section)
                
                content_parts.append(
                    f"**[From: {section}]**\n{result.content}"
                )
            
            formatted_content = "\n\n---\n\n".join(content_parts)
            
            logger.info(
                "rag_tool_success",
                chunks_retrieved=len(response.results),
                query_type=query_type,
                chapter=self.chapter_number,
                cost=response.cost.cost_usd if response.cost else None,
            )
            
            return RAGToolResult(
                content=formatted_content,
                source_sections=source_sections,
                query_used=query,
                success=True,
            )
            
        except RAGClientError as e:
            logger.warning("rag_tool_error", error=str(e), query=query)
            return RAGToolResult(
                content="",
                source_sections=[],
                query_used=query,
                success=False,
                error_message=f"RAG service error: {str(e)}",
            )
        except Exception as e:
            logger.exception("rag_tool_unexpected_error", error=str(e))
            return RAGToolResult(
                content="",
                source_sections=[],
                query_used=query,
                success=False,
                error_message=f"Unexpected error: {str(e)}",
            )
    
    async def _log_search_cost(self, cost_info: Any, query_type: str) -> None:
        """Log RAG search cost to usage tracking."""
        from app.db.database import async_session_maker
        from app.services.usage_service import UsageService
        
        try:
            async with async_session_maker() as db:
                usage_service = UsageService(db)
                await usage_service.log_rag_usage(
                    user_id=UUID(self.user_id),
                    usage_type=f"rag_search_{query_type}",
                    model_used=cost_info.model,
                    input_tokens=cost_info.input_tokens,
                    output_tokens=cost_info.output_tokens,
                    cost_usd=cost_info.cost_usd,
                    book_id=UUID(self.book_id) if self.book_id else None,
                    document_id=self.document_id,
                )
        except Exception as e:
            # Don't fail the search if cost logging fails
            logger.warning("failed_to_log_rag_search_cost", error=str(e))


class RAGToolError(Exception):
    """Custom exception for RAG tool errors."""
    pass


async def get_rag_tool_for_session(
    book_id: str,
    chapter_number: int,
    user_id: str,
    openai_key: Optional[str] = None,
) -> Optional[RAGTool]:
    """
    Create a RAGTool instance for the current teaching session.
    
    Fetches necessary IDs from database and user's BYOK key if available.
    
    Args:
        book_id: Book ID
        chapter_number: Chapter number
        user_id: User ID
        openai_key: Optional pre-fetched OpenAI key (for BYOK users)
    """
    from app.db.database import async_session_maker
    from app.models.book import Book, BookChapter
    from app.services.api_key_service import APIKeyService
    from sqlalchemy import select
    
    try:
        async with async_session_maker() as db:
            # Get book with RAG document ID
            book_result = await db.execute(
                select(Book).where(Book.id == UUID(book_id))
            )
            book = book_result.scalar_one_or_none()
            
            if not book or not book.book_metadata:
                logger.warning("rag_tool_no_book", book_id=book_id)
                return None
            
            document_id = book.book_metadata.get("rag_document_id")
            if not document_id:
                logger.warning("rag_tool_no_document_id", book_id=book_id)
                return None
            
            # Get chapter info
            chapter_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == book.id)
                .where(BookChapter.chapter_number == chapter_number)
            )
            chapter = chapter_result.scalar_one_or_none()
            
            chapter_title = chapter.title if chapter else f"Chapter {chapter_number}"
            chapter_id = None
            if chapter and chapter.key_concepts:
                chapter_id = chapter.key_concepts.get("rag_chapter_id")
            
            # Get user's BYOK key if not provided
            user_openai_key = openai_key
            if not user_openai_key and user_id:
                key_service = APIKeyService(db)
                user_openai_key = await key_service.get_stored_user_api_key(
                    UUID(user_id)
                )
            
            return RAGTool(
                book_id=book_id,
                document_id=document_id,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                chapter_id=chapter_id,
                user_id=user_id,
                openai_key=user_openai_key,
            )
            
    except Exception as e:
        logger.exception("rag_tool_creation_failed", error=str(e))
        return None


# Convenience functions for direct use

async def get_next_topic_content(
    book_id: str,
    chapter_number: int,
    user_id: str,
    topics_covered_summary: str,
) -> RAGToolResult:
    """
    Get the next topic content to teach.
    
    This is the main function for incremental teaching progression.
    """
    tool = await get_rag_tool_for_session(book_id, chapter_number, user_id)
    
    if not tool:
        return RAGToolResult(
            content="",
            source_sections=[],
            query_used="",
            success=False,
            error_message="Could not initialize RAG tool",
        )
    
    return await tool.fetch_content(
        topics_covered_summary=topics_covered_summary,
        query_type="next_topic",
    )


async def search_chapter_content(
    book_id: str,
    chapter_number: int,
    user_id: str,
    query: str,
    query_type: str = "answer",
) -> RAGToolResult:
    """
    Search for specific content in the chapter.
    
    Use this for answering questions or getting clarifications.
    """
    tool = await get_rag_tool_for_session(book_id, chapter_number, user_id)
    
    if not tool:
        return RAGToolResult(
            content="",
            source_sections=[],
            query_used="",
            success=False,
            error_message="Could not initialize RAG tool",
        )
    
    return await tool.fetch_content(
        topics_covered_summary="",
        query_type=query_type,
        specific_question=query,
    )
