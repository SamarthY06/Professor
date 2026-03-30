"""
TeacherAgent - LangGraph StateGraph Agent with @tool decorated functions.

Architecture:
1. Tools defined with @tool decorator
2. StateGraph with agent node + ToolNode
3. LLM decides when to call tools
4. Automatic tool execution via ToolNode

Enhanced Features:
- Day scope awareness and enforcement
- Previous day summary integration
- Professor level customization
- Strict chapter filtering for RAG
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import re

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from app.config import settings
from app.logs.logger import get_logger
from app.prompts.teacher import build_teacher_prompt

logger = get_logger(__name__)


# ============== TOOLS ==============
# RAG tools are built per request via make_teacher_tools(ctx) so each invocation
# closes over a context snapshot (safe under concurrent requests).


async def _fetch_next_topic_for_ctx(ctx: Dict[str, Any], topics_already_covered: str = "") -> str:
    from app.integrations.rag_client import get_rag_client
    from app.db.database import async_session_maker
    from app.models.book import Book, BookChapter
    from sqlalchemy import select
    from uuid import UUID
    
    book_id = ctx.get("book_id", "")
    chapter_number = ctx.get("chapter_number", 1)
    chapter_title = ctx.get("chapter_title", "")
    user_id = ctx.get("user_id", "")
    day_scope = ctx.get("day_scope", "")
    day_chapter_numbers = ctx.get("day_chapter_numbers", [chapter_number])
    
    if not book_id:
        return "Error: No book context available."
    
    document_id = None
    chapter_ids = []
    
    try:
        async with async_session_maker() as db:
            book_result = await db.execute(select(Book).where(Book.id == UUID(book_id)))
            book = book_result.scalar_one_or_none()
            if book and book.book_metadata:
                document_id = book.book_metadata.get("external_document_id") or book.book_metadata.get("rag_document_id")
            
            # Get chapter IDs for ALL chapters assigned to this day
            for ch_num in day_chapter_numbers:
                ch_result = await db.execute(
                    select(BookChapter)
                    .where(BookChapter.book_id == UUID(book_id))
                    .where(BookChapter.chapter_number == ch_num)
                )
                chapter = ch_result.scalar_one_or_none()
                if chapter:
                    if chapter.key_concepts:
                        cid = chapter.key_concepts.get("rag_chapter_id")
                        if cid:
                            chapter_ids.append(cid)
                    if ch_num == chapter_number and chapter.title:
                        chapter_title = chapter.title
                    
    except Exception as e:
        logger.warning("tool_db_error", error=str(e))
        return f"Error accessing book data: {str(e)}"
    
    if not document_id:
        return "Error: Book not processed yet."
    
    multi_chapter = len(day_chapter_numbers) > 1
    chapter_id = chapter_ids[0] if chapter_ids else None
    
    if multi_chapter:
        chapter_context = f"from Chapters {', '.join(str(c) for c in day_chapter_numbers)}"
    else:
        chapter_context = f"STRICTLY from Chapter {chapter_number}"
        if chapter_title:
            chapter_context += f" titled '{chapter_title}'"
    
    uncovered_topics = ctx.get("uncovered_topics", [])
    
    if topics_already_covered or uncovered_topics:
        # Prioritize uncovered scope topics for targeted retrieval
        if uncovered_topics:
            next_target = uncovered_topics[0]
            query = (
                f"{chapter_context}: "
                f"Teach about '{next_target}'. "
                f"Provide detailed content, explanations, formulas, and definitions."
            )
            if len(uncovered_topics) > 1:
                query += f" Also related: {', '.join(uncovered_topics[1:3])}"
        else:
            query = (
                f"{chapter_context}: "
                f"Topics already covered: {topics_already_covered}. "
                f"What is the NEXT topic to teach? "
                f"Provide content and explanations."
            )
        if day_scope:
            query += f" Today's scope includes: {day_scope}"
    else:
        query = (
            f"{chapter_context}: "
            f"What are the first main concepts? "
            f"Provide introductory content and key definitions."
        )
        if day_scope:
            query += f" Focus on topics within today's scope: {day_scope}"
    
    try:
        client = get_rag_client()
        
        # ALWAYS use chapter_id if available for strict filtering
        if chapter_id:
            search_chapter_ids = chapter_ids if multi_chapter and chapter_ids else ([chapter_id] if chapter_id else None)
            logger.info(
                "rag_search",
                chapter_ids=search_chapter_ids,
                chapter_numbers=day_chapter_numbers,
                multi_chapter=multi_chapter,
                query_preview=query[:100],
            )
            if search_chapter_ids:
                response = await client.search(
                    query=query,
                    document_id=document_id,
                    chapter_ids=search_chapter_ids,
                    limit=5,
                    user_id=user_id,
                )
            else:
                response = await client.search(
                    query=query,
                    document_id=document_id,
                    limit=5,
                    user_id=user_id,
                )
        else:
            logger.warning(
                "rag_search_without_chapter_filter",
                chapter_number=chapter_number,
                message="No chapter_id available, searching entire document"
            )
            response = await client.search(
                query=query,
                document_id=document_id,
                limit=5,
                user_id=user_id,
            )
        
        if not response.results:
            return f"No content found for the requested topics in the textbook."
        
        parts = []
        for i, r in enumerate(response.results[:4], 1):
            section = r.section_title or f"Section {i}"
            parts.append(f"[{section}]\n{r.content}")
        
        return "\n\n---\n\n".join(parts)
        
    except Exception as e:
        logger.exception("tool_fetch_error", error=str(e))
        return f"Error fetching content: {str(e)}"


async def _answer_from_textbook_for_ctx(ctx: Dict[str, Any], question: str) -> str:
    from app.integrations.rag_client import get_rag_client
    from app.db.database import async_session_maker
    from app.models.book import Book, BookChapter
    from sqlalchemy import select
    from uuid import UUID
    
    book_id = ctx.get("book_id", "")
    chapter_number = ctx.get("chapter_number", 1)
    chapter_title = ctx.get("chapter_title", "")
    user_id = ctx.get("user_id", "")
    
    if not book_id:
        return "Error: No book context available."
    
    document_id = None
    chapter_id = None
    
    try:
        async with async_session_maker() as db:
            book_result = await db.execute(select(Book).where(Book.id == UUID(book_id)))
            book = book_result.scalar_one_or_none()
            if book and book.book_metadata:
                # Try both keys for compatibility
                document_id = book.book_metadata.get("external_document_id") or book.book_metadata.get("rag_document_id")
            
            # CRITICAL: Always get chapter_id for proper filtering
            ch_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
                .where(BookChapter.chapter_number == chapter_number)
            )
            chapter = ch_result.scalar_one_or_none()
            if chapter and chapter.key_concepts:
                chapter_id = chapter.key_concepts.get("rag_chapter_id")
    except Exception as e:
        logger.warning("tool_db_error", error=str(e))
        return f"Error accessing book data: {str(e)}"
    
    if not document_id:
        return "Error: Book not processed yet."
    
    query = f"Chapter {chapter_number} ({chapter_title}): {question}"

    try:
        client = get_rag_client()

        # Search current chapter first
        if chapter_id:
            logger.info(
                "rag_answer_with_chapter_filter",
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                question_preview=question[:50],
            )
            response = await client.search(
                query=query,
                document_id=document_id,
                chapter_ids=[chapter_id],
                limit=3,
                user_id=user_id,
            )
        else:
            response = await client.search(
                query=query,
                document_id=document_id,
                limit=3,
                user_id=user_id,
            )

        # Cross-chapter fallback: if < 2 results, retry document-wide
        if chapter_id and len(response.results or []) < 2:
            logger.info(
                "rag_answer_cross_chapter_fallback",
                chapter_number=chapter_number,
                chapter_results=len(response.results or []),
                question_preview=question[:50],
            )
            fallback = await client.search(
                query=question,
                document_id=document_id,
                limit=3,
                user_id=user_id,
            )
            if len(fallback.results or []) > len(response.results or []):
                response = fallback

        if not response.results:
            return f"No relevant content found for this question."

        parts = [r.content for r in response.results[:3]]
        return "\n\n".join(parts)
        
    except Exception as e:
        logger.exception("tool_answer_error", error=str(e))
        return f"Error searching: {str(e)}"


def make_teacher_tools(tool_ctx: Dict[str, Any]) -> List[Any]:
    """Build LangChain tools that close over a snapshot of request context."""
    ctx = dict(tool_ctx)

    @tool
    async def fetch_next_topic(topics_already_covered: str = "") -> str:
        """
        Fetch the NEXT topic to teach from the textbook.

        Call this when:
        - Student says "proceed", "next", "continue", "move on"
        - You need NEW content to teach
        - Starting a new concept

        Args:
            topics_already_covered: Summary of topics already taught. Empty if starting fresh.

        Returns:
            Content from the textbook for the next topic.
        """
        return await _fetch_next_topic_for_ctx(ctx, topics_already_covered)

    @tool
    async def answer_from_textbook(question: str) -> str:
        """
        Search the textbook to answer a specific question.

        Call this when:
        - Student asks a specific question like "what is X?" or "explain Y"
        - You need to look up a definition or concept
        - Student asks for clarification on something from the book

        Args:
            question: The specific question to answer from the textbook.

        Returns:
            Relevant content from the textbook to answer the question.
        """
        return await _answer_from_textbook_for_ctx(ctx, question)

    return [fetch_next_topic, answer_from_textbook]


# ============== STATE ==============

class TeacherState(MessagesState):
    """State for teacher agent."""
    book_title: str = ""
    chapter_number: int = 1
    chapter_title: str = ""
    current_day: int = 1
    topics_covered: List[str] = []
    learning_level: str = "intermediate"
    day_scope: str = ""
    previous_day_summary: str = ""
    professor_level: str = "intermediate"
    scope_section: str = ""  # Built from plan_data at runtime


# ============== CREATE AGENT ==============

def create_teacher_agent(tools: List[Any]):
    """Create the Teacher Agent using StateGraph pattern."""
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.7,
        streaming=True,
    )
    
    llm_with_tools = llm.bind_tools(tools)
    
    def agent_node(state: TeacherState) -> dict:
        """Main agent reasoning node."""
        # Build the comprehensive system prompt
        # scope_section is built from plan_data at runtime
        system_prompt = build_teacher_prompt(
            book_title=state.get("book_title", "the textbook"),
            current_day=state.get("current_day", 1),
            chapter_number=state.get("chapter_number", 1),
            chapter_title=state.get("chapter_title", ""),
            topics_covered=", ".join(state.get("topics_covered", [])) or "None yet",
            learning_level=state.get("learning_level", "intermediate"),
            day_scope=state.get("day_scope", ""),
            previous_day_summary=state.get("previous_day_summary", ""),
            professor_level=state.get("professor_level", "intermediate"),
            scope_section=state.get("scope_section", ""),  # From plan_data
        )
        
        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        
        return {"messages": [response]}
    
    def should_continue(state: TeacherState) -> str:
        """Determine if we should call tools or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        
        return END
    
    workflow = StateGraph(TeacherState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))
    
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()


# ============== RESPONSE ==============

@dataclass
class TeacherResponse:
    """
    Response from TeacherAgent.
    
    The agent decides what happens next - no external routing needed.
    This is the TRUE AGENTIC approach.
    """
    response: str
    topic_completed: bool
    day_completed: bool
    ready_for_quiz: bool
    topics_mentioned: List[str]
    needs_next_content: bool
    rag_was_used: bool
    continue_to_next_day: bool = False  # Agent decided to move to next day
    
    # AGENTIC DECISION: What should happen next?
    # The agent decides this based on context, not external routing
    next_phase: str = "teaching"  # teaching, quiz, chapter_transition, break
    agent_reasoning: str = ""  # Why the agent made this decision


# ============== HELPER FUNCTIONS ==============

# Words to skip when extracting topics from bold text
_TOPIC_SKIP_WORDS = frozenset([
    "note", "important", "example", "check", "task", "question", 
    "answer", "current", "student", "session", "recap", "summary",
    "key", "remember", "tip", "warning", "hint", "exercise"
])


def _extract_topics_from_response(response_text: str) -> List[str]:
    """
    Extract topic names from bold text in the response.
    
    This looks for **bold text** patterns which typically indicate
    topic names or key concepts being discussed.
    
    Args:
        response_text: The teacher's response
    
    Returns:
        List of extracted topic names (max 5)
    """
    topics = []
    bold_matches = re.findall(r'\*\*([^*]+)\*\*', response_text)
    
    for match in bold_matches:
        topic = match.strip().rstrip(':')
        # Filter by length
        if not (3 < len(topic) < 80):
            continue
        # Filter out common non-topic words
        topic_lower = topic.lower()
        if any(skip_word in topic_lower for skip_word in _TOPIC_SKIP_WORDS):
            continue
        topics.append(topic)
    
    return topics[:5]  # Limit to 5 topics


async def _verify_topics_covered_llm(
    response_text: str,
    planned_topics: List[str],
    api_key: str,
) -> List[str]:
    """Use a lightweight LLM call to verify which planned topics were actually taught.
    
    A topic counts as "covered" only if the response contains substantive teaching
    (definitions, explanations, examples, or formulas), not just passing mentions.
    """
    from openai import AsyncOpenAI
    import json

    client = AsyncOpenAI(api_key=api_key)

    topics_list = "\n".join(f"- {t}" for t in planned_topics)
    prompt = (
        "Given this teaching response and a list of planned topics, identify which "
        "topics were ACTUALLY EXPLAINED (not just mentioned in passing).\n\n"
        "A topic counts as 'covered' only if the response contains substantive "
        "teaching about it (definitions, explanations, examples, or formulas).\n\n"
        f"TEACHING RESPONSE:\n{response_text[:3000]}\n\n"
        f"PLANNED TOPICS:\n{topics_list}\n\n"
        "Return ONLY a JSON array of topic names that were substantively covered. "
        'Example: ["Topic A", "Topic C"]\n'
        "If none were covered, return: []"
    )

    try:
        result = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=500,
        )
        content = result.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(content)
    except Exception as e:
        logger.warning("llm_topic_verification_failed", error=str(e))
        return []


def _get_all_topics_for_day(plan_data: Dict[str, Any], current_day: int) -> List[str]:
    """Extract all planned topic names for a given day."""
    if not plan_data:
        return []
    for day_data in plan_data.get("days", []):
        if day_data.get("day") == current_day:
            topics = []
            for item in day_data.get("items", []):
                for topic in item.get("topics", []):
                    if isinstance(topic, dict):
                        topics.append(topic.get("name", ""))
                    else:
                        topics.append(topic)
            return topics
    return []


def _build_scope_section_from_plan(
    plan_data: Dict[str, Any],
    current_day: int,
    topics_covered: List[str],
) -> str:
    """
    Build the scope section for the teacher prompt from plan_data.
    
    Uses the scope service for comprehensive scope tracking.
    
    Args:
        plan_data: The learning plan
        current_day: Current day number
        topics_covered: Topics already covered today
    
    Returns:
        Formatted string for the prompt
    """
    from app.services.scope_service import (
        extract_scope_from_plan,
        update_scope_coverage,
        build_scope_prompt_section,
    )
    
    if not plan_data:
        return ""
    
    # Extract scope using the scope service
    scope = extract_scope_from_plan(plan_data, current_day)
    
    # Update with covered topics
    scope = update_scope_coverage(scope, topics_covered)
    
    # Build the prompt section
    return build_scope_prompt_section(scope, topics_covered)


def get_chapter_for_day(plan_data: Dict[str, Any], current_day: int) -> tuple[int, str]:
    """
    Get the primary chapter number and title assigned to a specific day.

    Returns the first chapter item. Use get_all_chapters_for_day() when a
    day spans multiple chapters.
    """
    if not plan_data:
        return (1, "")
    
    days = plan_data.get("days", [])
    for day in days:
        if day.get("day") == current_day:
            items = day.get("items", [])
            if items:
                first_item = items[0]
                chapter_number = first_item.get("chapter_number", 1)
                chapter_title = first_item.get("chapter_title", f"Chapter {chapter_number}")
                return (chapter_number, chapter_title)
            return (0, "Review Day")
    
    return (1, "")


def get_all_chapters_for_day(plan_data: Dict[str, Any], current_day: int) -> list[tuple[int, str]]:
    """
    Get ALL chapter numbers and titles assigned to a specific day.

    Many days cover multiple chapters (e.g. Day 1 might include both
    Ch 1: Preview and Ch 2: Configuration Space). The teacher must be
    allowed to teach content from ALL of them.
    """
    if not plan_data:
        return [(1, "")]
    
    days = plan_data.get("days", [])
    for day in days:
        if day.get("day") == current_day:
            items = day.get("items", [])
            if items:
                return [
                    (item.get("chapter_number", 1), item.get("chapter_title", f"Chapter {item.get('chapter_number', 1)}"))
                    for item in items
                ]
            return [(0, "Review Day")]
    
    return [(1, "")]


def get_day_scope_from_plan(plan_data: Dict[str, Any], current_day: int) -> str:
    """
    Extract the scope (topics to cover) for a specific day from the learning plan.
    
    Args:
        plan_data: The learning plan data
        current_day: The current day number
    
    Returns:
        String describing what should be covered today
    """
    if not plan_data:
        return ""
    
    days = plan_data.get("days", [])
    for day in days:
        if day.get("day") == current_day:
            items = day.get("items", [])
            if not items:
                if day.get("rest"):
                    return "Review and rest day - consolidate previous learning"
                return ""
            
            # Build scope description
            scope_parts = []
            for item in items:
                chapter_title = item.get("chapter_title", "")
                topics = item.get("topics", [])
                if topics:
                    scope_parts.append(f"{chapter_title}: {', '.join(topics[:3])}")
                elif chapter_title:
                    scope_parts.append(chapter_title)
            
            return "; ".join(scope_parts) if scope_parts else ""
    
    return ""


def get_previous_day_summary(
    plan_data: Dict[str, Any],
    current_day: int,
    completed_days: List[int],
    last_session_date: str = "",
) -> str:
    """
    Generate a warm, time-aware summary of what was covered in previous day(s).
    
    Args:
        plan_data: The learning plan data
        current_day: The current day number
        completed_days: List of completed day numbers
        last_session_date: ISO date string of last session for time-aware summaries
    
    Returns:
        Summary string for the teacher to use
    """
    from datetime import datetime, timedelta
    
    if current_day <= 1 or not plan_data:
        return ""
    
    days = plan_data.get("days", [])
    previous_day = current_day - 1
    
    # Determine time context
    time_phrase = "Last time"
    if last_session_date:
        try:
            last_date = datetime.fromisoformat(last_session_date.replace('Z', '+00:00'))
            now = datetime.now(last_date.tzinfo) if last_date.tzinfo else datetime.now()
            days_ago = (now - last_date).days
            
            if days_ago == 0:
                time_phrase = "Earlier today"
            elif days_ago == 1:
                time_phrase = "Yesterday"
            elif days_ago == 2:
                time_phrase = "A couple days ago"
            elif days_ago <= 7:
                time_phrase = f"A few days ago ({last_date.strftime('%A')})"
            elif days_ago <= 14:
                time_phrase = f"Last week ({last_date.strftime('%A')})"
            else:
                time_phrase = f"On {last_date.strftime('%B %d')}"
        except (ValueError, TypeError):
            time_phrase = "In our last session"
    
    # Find the previous day's content
    for day in days:
        if day.get("day") == previous_day:
            items = day.get("items", [])
            if not items:
                return ""
            
            # Build summary
            summary_parts = []
            for item in items:
                chapter_title = item.get("chapter_title", "")
                topics = item.get("topics", [])
                if chapter_title:
                    if topics:
                        summary_parts.append(f"**{chapter_title}**: {', '.join(topics[:3])}")
                    else:
                        summary_parts.append(f"**{chapter_title}**")
            
            if summary_parts:
                intro = f"📚 **Quick recap**: {time_phrase}, we explored:\n"
                content = "\n".join(f"- {s}" for s in summary_parts)
                outro = "\n\nLet's build on that foundation today!"
                return intro + content + outro
    
    return ""


# ============== AUTOMATIC DAY COMPLETION DETECTION ==============

def get_all_topics_for_day(plan_data: Dict[str, Any], current_day: int) -> List[str]:
    """
    Get all topics planned for a specific day.
    
    Args:
        plan_data: The learning plan data
        current_day: The current day number
    
    Returns:
        List of all topic strings for the day
    """
    if not plan_data:
        return []
    
    days = plan_data.get("days", [])
    for day in days:
        if day.get("day") == current_day:
            if day.get("rest"):
                return []  # Rest days have no specific topics
            
            all_topics = []
            for item in day.get("items", []):
                topics = item.get("topics", [])
                all_topics.extend(topics)
            return all_topics
    
    return []


def _topics_match(planned: str, covered: str) -> bool:
    """
    Strict match two topic names to determine if they're the same topic.
    
    This is intentionally strict to avoid false positives from casual mentions.
    
    Args:
        planned: The planned topic name from the learning plan
        covered: The topic name extracted from teaching response
    
    Returns:
        True if the topics match
    """
    planned_lower = planned.lower().strip()
    covered_lower = covered.lower().strip()
    
    # Exact match only
    if planned_lower == covered_lower:
        return True
    
    # Very close substring match (planned must be mostly in covered)
    if len(planned_lower) >= 5 and planned_lower in covered_lower:
        return True
    
    # For short topics, require exact match
    if len(planned_lower) < 10:
        return False
    
    # Key word overlap - extract significant words (4+ chars)
    planned_words = {w for w in planned_lower.split() if len(w) >= 4}
    covered_words = {w for w in covered_lower.split() if len(w) >= 4}
    
    # Remove common words
    common_words = {"the", "and", "for", "with", "from", "into", "about", "what", "how", "this", "that", "these", "those"}
    planned_words -= common_words
    covered_words -= common_words
    
    if not planned_words or len(planned_words) < 2:
        return False
    
    # Require 80% of planned words to be in covered (stricter)
    overlap = len(planned_words & covered_words)
    if overlap >= len(planned_words) * 0.8:
        return True
    
    return False


def check_day_completion(
    plan_data: Dict[str, Any],
    current_day: int,
    topics_covered: List[str],
    message_count: int = 0,
) -> tuple:
    """
    Check if the day's scope is complete based on topics covered.
    
    This provides automatic day completion detection without relying
    on the LLM to include [DAY_COMPLETED] signals.
    
    Args:
        plan_data: The learning plan data
        current_day: The current day number
        topics_covered: List of topics that have been covered
        message_count: Number of messages in the current session (for minimum threshold)
    
    Returns:
        Tuple of (is_complete: bool, completion_percentage: float, matched_topics: list)
    """
    planned_topics = get_all_topics_for_day(plan_data, current_day)
    
    if not planned_topics:
        # No specific topics planned (rest day or empty) = always complete
        return True, 1.0, []
    
    # SAFEGUARD: Require minimum 10 messages before auto-completing a day
    # This prevents premature completion from topic word matching
    # The LLM should signal [DAY_COMPLETED] for normal completion
    # Auto-detection is only a fallback for when LLM forgets to signal
    if message_count < 10:
        logger.info(
            "day_completion_check_skipped",
            current_day=current_day,
            message_count=message_count,
            reason="minimum_messages_not_met",
        )
        return False, 0.0, []
    
    # Match covered topics against planned topics
    matched_topics = []
    for planned_topic in planned_topics:
        for covered_topic in topics_covered:
            if _topics_match(planned_topic, covered_topic):
                matched_topics.append(planned_topic)
                break
    
    completion_pct = len(matched_topics) / len(planned_topics)
    
    # Consider day complete if 90% or more topics are covered (stricter threshold)
    is_complete = completion_pct >= 0.9
    
    logger.info(
        "day_completion_check",
        current_day=current_day,
        planned_topics=len(planned_topics),
        matched_topics=len(matched_topics),
        completion_pct=round(completion_pct, 2),
        is_complete=is_complete,
        message_count=message_count,
    )
    
    return is_complete, completion_pct, matched_topics


def extract_topics_from_response_enhanced(response: str, day_scope: str) -> List[str]:
    """
    Enhanced topic extraction that looks for topics from the day's scope
    mentioned in the response.
    
    Args:
        response: The teaching response text
        day_scope: The day's scope string (topics planned for today)
    
    Returns:
        List of topics that were covered in the response
    """
    topics_found = []
    response_lower = response.lower()
    
    # Extract topics from day_scope
    # Format: "Chapter Title: topic1, topic2, topic3; Chapter Title: topic4"
    scope_parts = day_scope.split(";")
    for part in scope_parts:
        if ":" in part:
            _, topics_str = part.split(":", 1)
            topics = [t.strip() for t in topics_str.split(",")]
            for topic in topics:
                topic_lower = topic.lower()
                # Check if topic is mentioned in response
                if topic_lower in response_lower:
                    topics_found.append(topic)
                else:
                    # Check for key words
                    topic_words = {w for w in topic_lower.split() if len(w) >= 4}
                    if topic_words:
                        words_found = sum(1 for w in topic_words if w in response_lower)
                        if words_found >= len(topic_words) * 0.5:
                            topics_found.append(topic)
    
    return topics_found


# ============== ENTRY POINTS ==============

async def teach_with_context(
    user_message: str,
    state: Dict[str, Any],
    api_key: Optional[str] = None,
) -> TeacherResponse:
    """Main entry point - runs the TeacherAgent."""
    from uuid import UUID
    
    book_id = state.get("book_id", "")
    user_id = state.get("user_id", "")
    topics_covered = state.get("topics_covered_this_chapter", []) or state.get("day_topics_covered", [])
    current_day = state.get("current_day", 1)
    
    plan_data = state.get("plan_data", {})
    day_scope = get_day_scope_from_plan(plan_data, current_day)
    
    # Get ALL chapters for this day (a day can span multiple chapters)
    all_day_chapters = get_all_chapters_for_day(plan_data, current_day)
    plan_chapter_number, plan_chapter_title = get_chapter_for_day(plan_data, current_day)
    
    if plan_chapter_number > 0:
        chapter_number = plan_chapter_number
        chapter_title = plan_chapter_title
        logger.info(
            "using_chapter_from_plan",
            day=current_day,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            all_day_chapters=[cn for cn, _ in all_day_chapters],
        )
    else:
        chapter_number = state.get("current_chapter", 1)
        chapter_title = state.get("chapter_title", f"Chapter {chapter_number}")
    
    # Get previous day summary
    completed_days = state.get("completed_days", [])
    previous_day_summary = state.get("previous_day_summary", "")
    
    # If we have a cumulative summary from the workflow, use it
    cumulative_summary = state.get("cumulative_summary", "")
    if cumulative_summary and not previous_day_summary:
        previous_day_summary = cumulative_summary
    elif not previous_day_summary and current_day > 1:
        previous_day_summary = get_previous_day_summary(
            plan_data, current_day, completed_days
        )
    
    # Get professor level
    professor_level = state.get("professor_level", state.get("learning_level", "intermediate"))
    
    # Build scope section from plan_data (no DB call needed)
    scope_section = _build_scope_section_from_plan(plan_data, current_day, topics_covered)
    
    day_chapter_numbers = [cn for cn, _ in all_day_chapters if cn > 0]
    
    # Compute uncovered topics from plan scope for targeted RAG queries
    planned_topics = _get_all_topics_for_day(plan_data, current_day)
    uncovered_topics = [t for t in planned_topics if t not in topics_covered]
    
    tool_ctx = {
        "book_id": book_id,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "user_id": user_id,
        "topics_covered": topics_covered,
        "day_scope": day_scope,
        "current_day": current_day,
        "day_chapter_numbers": day_chapter_numbers or [chapter_number],
        "uncovered_topics": uncovered_topics or [],
    }
    teacher_tools = make_teacher_tools(tool_ctx)
    agent = create_teacher_agent(teacher_tools)
    
    # Build multi-chapter context for days that span multiple chapters
    multi_chapter_note = ""
    day_chapter_numbers = [cn for cn, _ in all_day_chapters if cn > 0]
    if len(day_chapter_numbers) > 1:
        ch_descriptions = [f"Chapter {cn}: {ct}" for cn, ct in all_day_chapters if cn > 0]
        multi_chapter_note = (
            f"\n\nIMPORTANT: Today's session covers MULTIPLE chapters: {', '.join(ch_descriptions)}. "
            f"You MUST teach content from ALL of these chapters, not just the first one. "
            f"After covering the first chapter's topics, move on to the next chapter's topics. "
            f"You can search for content from any of these chapters."
        )
    
    messages = []
    conversation_history = state.get("conversation_history", [])
    
    recent_history = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history
    for msg in recent_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    
    # Inject system hint as context alongside the user message
    system_hint = state.get("system_hint", "")
    effective_user_message = user_message
    if system_hint:
        effective_user_message = f"{user_message}\n\n[SYSTEM INSTRUCTION: {system_hint}]"
    
    messages.append(HumanMessage(content=effective_user_message))
    
    input_state = {
        "messages": messages,
        "book_title": state.get("book_title", "the textbook"),
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "current_day": current_day,
        "topics_covered": topics_covered,
        "learning_level": state.get("learning_level", "intermediate"),
        "day_scope": day_scope + multi_chapter_note,
        "previous_day_summary": previous_day_summary,
        "professor_level": professor_level,
        "scope_section": scope_section,
        "day_chapter_numbers": day_chapter_numbers,
    }
    
    rag_was_used = False
    response_text = ""
    
    try:
        result = await agent.ainvoke(input_state)
        messages = result.get("messages", [])
        
        for msg in messages:
            if isinstance(msg, ToolMessage):
                rag_was_used = True
        
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                if not (hasattr(msg, 'tool_calls') and msg.tool_calls):
                    response_text = msg.content
                    break
                elif msg.content:
                    response_text = msg.content
        
        if not response_text:
            response_text = "Let me continue teaching. What would you like to explore?"
            
    except Exception as e:
        logger.exception("teacher_agent_error", error=str(e))
        response_text = f"Let's continue with {chapter_title}. What would you like to explore?"
    
    # AGENTIC APPROACH: Parse the agent's decision from the response
    # The agent decides what happens next - no external routing needed
    next_phase = "teaching"  # Default
    agent_reasoning = ""
    
    # Extract decision block from response
    if "[DECISION]" in response_text and "[/DECISION]" in response_text:
        decision_start = response_text.find("[DECISION]")
        decision_end = response_text.find("[/DECISION]") + len("[/DECISION]")
        decision_block = response_text[decision_start:decision_end]
        
        # Parse next_action
        if "next_action:" in decision_block:
            action_line = [l for l in decision_block.split("\n") if "next_action:" in l]
            if action_line:
                action = action_line[0].split("next_action:")[1].strip()
                if "move_to_next_day" in action:
                    next_phase = "day_transition"
                elif "offer_quiz" in action:
                    next_phase = "quiz"
                elif "take_break" in action:
                    next_phase = "break"
                else:
                    next_phase = "teaching"
        
        # Parse reasoning
        if "reasoning:" in decision_block:
            reason_line = [l for l in decision_block.split("\n") if "reasoning:" in l]
            if reason_line:
                agent_reasoning = reason_line[0].split("reasoning:")[1].strip()
        
        # Remove decision block from response
        response_text = response_text[:decision_start] + response_text[decision_end:]
    
    # Fallback: Check for legacy signals (backward compatibility)
    topic_done = "[TOPIC_DONE]" in response_text or "[TOPIC_COMPLETE]" in response_text
    day_completed_signal = "[DAY_COMPLETED]" in response_text or "[DAY_COMPLETE]" in response_text
    ready_for_quiz = "[READY_FOR_QUIZ]" in response_text
    continue_to_next_day = "[CONTINUE_TO_NEXT_DAY]" in response_text or next_phase == "day_transition"
    
    # If legacy signals present, update next_phase
    if day_completed_signal and next_phase == "teaching":
        next_phase = "day_transition"
    if ready_for_quiz and next_phase == "teaching":
        next_phase = "quiz"
    
    # Clean the response (remove all markers)
    clean_response = response_text
    for marker in ["[TOPIC_DONE]", "[TOPIC_COMPLETE]", "[DAY_COMPLETED]", "[DAY_COMPLETE]", 
                   "[READY_FOR_QUIZ]", "[CONTINUE_TO_NEXT_DAY]", "[DECISION]", "[/DECISION]"]:
        clean_response = clean_response.replace(marker, "").strip()
    
    # Also clean any remaining decision content
    clean_response = re.sub(r'next_action:.*?\n', '', clean_response)
    clean_response = re.sub(r'reasoning:.*?\n', '', clean_response)
    clean_response = clean_response.strip()
    
    # LLM-based topic verification with regex fallback
    planned_topics = _get_all_topics_for_day(plan_data, current_day)
    effective_api_key = api_key or settings.openai_api_key
    topics_mentioned = []
    if planned_topics and effective_api_key:
        topics_mentioned = await _verify_topics_covered_llm(
            response_text, planned_topics, effective_api_key
        )
    if not topics_mentioned:
        topics_mentioned = _extract_topics_from_response(response_text)
        if day_scope:
            scope_topics = extract_topics_from_response_enhanced(response_text, day_scope)
            for topic in scope_topics:
                if topic not in topics_mentioned:
                    topics_mentioned.append(topic)
    
    # Combine existing topics with newly mentioned ones (for tracking purposes)
    all_topics_covered = list(topics_covered) + [t for t in topics_mentioned if t not in topics_covered]
    
    # Get message count from state for logging
    message_count = state.get("session_message_count", 0)
    
    # Day completed if agent decided to transition
    day_completed = next_phase == "day_transition" or day_completed_signal
    
    logger.info(
        "agent_decision",
        next_phase=next_phase,
        agent_reasoning=agent_reasoning[:100] if agent_reasoning else "none",
        day_completed=day_completed,
        current_day=current_day,
        message_count=message_count,
    )
    
    logger.info(
        "teacher_response",
        day=current_day,
        chapter=chapter_number,
        topic_done=topic_done,
        day_completed=day_completed,
        next_phase=next_phase,
        rag_used=rag_was_used,
        day_scope=day_scope[:50] if day_scope else "none",
        topics_mentioned=len(topics_mentioned),
    )
    
    return TeacherResponse(
        response=clean_response,
        next_phase=next_phase,
        agent_reasoning=agent_reasoning,
        topic_completed=topic_done,
        day_completed=day_completed,
        ready_for_quiz=ready_for_quiz,
        topics_mentioned=topics_mentioned[:10],  # Increased limit
        needs_next_content=False,
        rag_was_used=rag_was_used,
        continue_to_next_day=continue_to_next_day,
    )


async def teach(
    user_message: str,
    state: Dict[str, Any],
    api_key: Optional[str] = None,
) -> TeacherResponse:
    """Alias for teach_with_context."""
    return await teach_with_context(user_message, state, api_key)


# ============== BACKWARD COMPATIBILITY ==============

class TeacherAgent:
    """TeacherAgent class for backward compatibility."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
    
    async def process(self, state: Dict[str, Any]) -> TeacherResponse:
        """Process using the StateGraph agent."""
        user_message = state.get("user_message", "")
        return await teach_with_context(user_message, state, self.api_key)
