"""
PlannerAgent - LangGraph Agentic Config Gathering & Plan Generation.

Architecture (follows eon-langgraph patterns):
    - ConfigGathering: StateGraph agent with save_learning_config tool (per-invocation sink)
        - Agent node: LLM with tools bound → autonomous decision-making
        - Tools node: ToolNode executes when LLM decides to call tools
        - Routing: should_continue checks tool_calls → tools or END
        - The LLM drives the entire conversation. No deterministic fallbacks.
    - PlannerAgent: Structured output plan generation after config is gathered
"""

from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional, Annotated, Literal

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END, MessagesState
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from app.config import settings
from app.logs.logger import get_logger
from app.prompts.planner import (
    PLANNER_CONFIG_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    PLAN_PROMPT,
    ADAPT_PROMPT,
)
from app.utils.state_helpers import (
    safe_get, safe_get_int, safe_get_float, safe_get_list, safe_get_dict,
)

logger = get_logger(__name__)


# =============================================================================
# STRUCTURED OUTPUT MODELS
# =============================================================================

class DayItem(BaseModel):
    chapter_number: int = Field(description="Chapter number (1-indexed)")
    chapter_title: str = Field(description="Title of the chapter")
    topics: List[str] = Field(description="Key topics to cover")
    estimated_minutes: int = Field(description="Estimated minutes", ge=5, le=300)


class LearningDay(BaseModel):
    day: int = Field(description="Day number (1-indexed)")
    day_title: str = Field(description="Descriptive title for the day")
    rest: bool = Field(default=False, description="Whether this is a rest/review day")
    items: List[DayItem] = Field(default_factory=list)
    quiz_after: bool = Field(default=False)


class Milestone(BaseModel):
    day: int
    title: str
    description: str


class LearningPlanSchema(BaseModel):
    """Structured output schema for plan generation."""
    total_days: int = Field(ge=1, le=365)
    overview: str
    days: List[LearningDay]
    milestones: List[Milestone] = Field(default_factory=list)
    total_chapters: int
    estimated_total_hours: float


# =============================================================================
# TOOLS — LLM decides when to call these
#
# config_sink: per agent invocation, closed over by the tool so the async
# caller reads gathered config without module-level mutable state.
# =============================================================================


def _make_config_gathering_tools(config_sink: Dict[str, Any]):
    @tool("save_learning_config")
    def save_learning_config(
        learning_level: str,
        target_days: int,
        daily_minutes: int,
        quiz_frequency: str,
        professor_level: str = "mtech",
    ) -> str:
        """Save the student's learning preferences and create their learning plan.

        Call this tool when you have gathered ALL of the student's preferences
        through conversation. You need:
        - learning_level: their experience ("beginner", "intermediate", or "advanced")
        - target_days: how many days they want to finish in (any positive number)
        - daily_minutes: how many minutes per day they can study
        - quiz_frequency: how often to quiz ("after_each_chapter", "after_2_chapters", or "final_only")
        - professor_level: teaching depth they chose ("undergrad", "mtech", or "phd")

        Args:
            learning_level: One of 'beginner', 'intermediate', 'advanced'
            target_days: Number of days to complete (1-365)
            daily_minutes: Minutes per day for study (10-480)
            quiz_frequency: One of 'after_each_chapter', 'after_2_chapters', 'final_only'
            professor_level: One of 'undergrad', 'mtech', 'phd'

        Returns:
            Confirmation message
        """
        # Normalize learning_level
        level_map = {"new": "beginner", "basic": "beginner", "expert": "advanced"}
        learning_level = level_map.get(learning_level.lower(), learning_level.lower())
        if learning_level not in ("beginner", "intermediate", "advanced"):
            learning_level = "intermediate"

        # Normalize professor_level
        prof_map = {
            "undergraduate": "undergrad", "friendly": "undergrad", "intuitive": "undergrad",
            "balanced": "mtech", "thorough": "mtech", "master": "mtech", "masters": "mtech",
            "deep": "phd", "rigorous": "phd", "research": "phd",
            "intermediate": "mtech",
        }
        professor_level = prof_map.get(professor_level.lower(), professor_level.lower())
        if professor_level not in ("undergrad", "mtech", "phd"):
            professor_level = "mtech"

        # Normalize quiz_frequency
        freq_map = {
            "each chapter": "after_each_chapter", "every chapter": "after_each_chapter",
            "every 2 chapters": "after_2_chapters", "final only": "final_only",
            "at the end": "final_only",
        }
        quiz_frequency = freq_map.get(quiz_frequency.lower(), quiz_frequency.lower())
        if quiz_frequency not in ("after_each_chapter", "after_2_chapters", "final_only"):
            quiz_frequency = "after_each_chapter"

        target_days = max(1, min(target_days, 365))
        daily_minutes = max(10, min(daily_minutes, 480))

        config = {
            "learning_level": learning_level,
            "professor_level": professor_level,
            "target_days": target_days,
            "daily_minutes": daily_minutes,
            "quiz_frequency": quiz_frequency,
        }

        config_sink["config"] = config

        professor_display = {
            "undergrad": "Friendly & Intuitive",
            "mtech": "Balanced & Thorough",
            "phd": "Deep & Rigorous",
        }.get(professor_level, professor_level)

        logger.info("learning_config_saved_via_tool", config=config)

        return (
            f"Configuration saved!\n"
            f"- Level: {learning_level}\n"
            f"- Style: {professor_display}\n"
            f"- Timeline: {target_days} days, {daily_minutes} min/day\n"
            f"- Quizzes: {quiz_frequency.replace('_', ' ')}\n\n"
            f"Generating your personalized learning plan now..."
        )

    return [save_learning_config]


# =============================================================================
# CONFIG GATHERING AGENT — LangGraph StateGraph (eon-langgraph pattern)
# =============================================================================

def _create_config_agent(api_key: str, system_prompt: str, config_sink: Dict[str, Any]):
    """Create a LangGraph agent for config gathering.

    Pattern: agent → should_continue → (tools → agent) | END
    The LLM autonomously decides when to call save_learning_config.
    """
    tools = _make_config_gathering_tools(config_sink)
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=api_key,
        temperature=0.6,
        streaming=False,
    )
    llm_with_tools = llm.bind_tools(tools)

    async def agent_node(state: MessagesState):
        """Agent node — LLM reasons over messages and decides action."""
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "end"]:
        """Route to tools if LLM made tool calls, else end turn."""
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "end"

    workflow = StateGraph(MessagesState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(tools))
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# =============================================================================
# PUBLIC INTERFACE — called by graph.py config_gathering_node
# =============================================================================

async def gather_config_conversationally(
    book_id: str,
    book_title: str,
    user_id: str,
    total_chapters: int,
    user_message: str,
    conversation_history: List[Dict[str, str]] = None,
    api_key: str = None,
) -> Dict[str, Any]:
    """Run one turn of the config-gathering conversation.

    The LangGraph agent handles the entire conversation autonomously:
    - It asks questions naturally
    - It decides when enough info has been gathered
    - It calls save_learning_config tool on its own

    Returns:
        {"response": str, "config_complete": bool, "config": dict | None}
    """
    config_sink: Dict[str, Any] = {}

    effective_key = api_key or settings.openai_api_key

    # Build system prompt
    system_prompt = PLANNER_CONFIG_SYSTEM_PROMPT.format(
        book_title=book_title,
        total_chapters=total_chapters,
    )

    # Build message history for the agent
    messages: list = [SystemMessage(content=system_prompt)]
    for msg in (conversation_history or []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=user_message))

    # Create and invoke the agent
    agent = _create_config_agent(effective_key, system_prompt, config_sink)

    logger.info(
        "config_agent_invoked",
        book_id=book_id,
        message_count=len(messages),
        user_message=user_message[:100],
    )

    result = await agent.ainvoke({"messages": messages})

    # Extract the final AI response (skip tool-call-only messages)
    response_text = ""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
            response_text = msg.content
            break

    if not response_text:
        response_text = "Let me set up your learning plan!"

    # Check if the tool was called (agent decided config is complete)
    config = config_sink.get("config")

    logger.info(
        "config_agent_result",
        config_complete=config is not None,
        response_length=len(response_text),
    )

    return {
        "response": response_text,
        "config_complete": config is not None,
        "config": config,
    }


# =============================================================================
# CONFIG CONVERSATION STARTER — called by init endpoint for first greeting
# =============================================================================

async def start_config_conversation(
    book_id: str,
    book_title: str,
    user_id: str,
    total_chapters: int,
) -> str:
    """Generate the initial greeting that kicks off config gathering.

    Called by the init endpoint when a brand-new session is created.
    Uses the same LangGraph agent to produce the first message.
    """
    effective_key = settings.openai_api_key
    system_prompt = PLANNER_CONFIG_SYSTEM_PROMPT.format(
        book_title=book_title,
        total_chapters=total_chapters,
    )

    agent = _create_config_agent(effective_key, system_prompt, {})

    try:
        result = await agent.ainvoke({
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content="Hi, I just uploaded a book and want to start learning."),
            ]
        })

        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                return msg.content

    except Exception as e:
        logger.warning("start_config_conversation_failed", error=str(e))

    return (
        f"Welcome! I'm excited to help you learn **{book_title}**! 📚\n\n"
        f"Before we create your plan, a few quick questions:\n\n"
        f"1. **Your background** — Is this subject new to you, or do you have some experience?\n"
        f"2. **Teaching style** — Would you prefer:\n"
        f"   - 📚 Friendly & Intuitive (relaxed, lots of examples)\n"
        f"   - 🎓 Balanced & Thorough (depth with clarity)\n"
        f"   - 🔬 Deep & Rigorous (full technical detail)\n"
        f"3. **Timeline** — How many days to complete, and how much time per day?\n\n"
        f"Feel free to answer everything at once or one at a time!"
    )


# =============================================================================
# PLAN GENERATION — PlannerAgent (after config is gathered)
# =============================================================================

class PlannerAgent:
    """Creates and iterates on structured learning plans."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = settings.openai_model

    def _get_llm(self, max_tokens: int = 8000) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            temperature=0.3,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # Understand user's response to a presented plan
    # ------------------------------------------------------------------

    async def understand_plan_response(self, user_message: str, has_plan: bool) -> Dict[str, Any]:
        if not has_plan:
            return {"accepts": False, "rejects": False, "wants_modification": False}

        llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0, api_key=self.api_key)
        prompt = (
            "You are analyzing a student's response to a learning plan.\n"
            "Determine if they:\n"
            "1. ACCEPT (yes, looks good, perfect, let's start, ok)\n"
            "2. MODIFY (change something, more/less days)\n"
            "3. REJECT (no, start over)\n\n"
            "Respond ONLY: ACCEPT, MODIFY, or REJECT\n\n"
            f"Student said: \"{user_message}\""
        )
        try:
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            word = resp.content.strip().upper()
            return {
                "accepts": "ACCEPT" in word,
                "rejects": "REJECT" in word,
                "wants_modification": "MODIFY" in word,
            }
        except Exception:
            return {"accepts": True, "rejects": False, "wants_modification": False}

    # ------------------------------------------------------------------
    # Main process entry — called from graph.py planning_node
    # ------------------------------------------------------------------

    async def process(self, state: Dict[str, Any]):
        from dataclasses import dataclass

        @dataclass
        class PlanResult:
            plan_data: Dict[str, Any]
            summary: str
            plan_accepted: bool

        existing_plan = safe_get_dict(state, "existing_plan", {}) or safe_get_dict(state, "learning_plan", {})
        user_message = safe_get(state, "user_message", "")

        intent = await self.understand_plan_response(user_message, bool(existing_plan))

        if not existing_plan:
            plan = await self._create_plan(state)
            summary = await self._format_plan_summary(plan, state)
            return PlanResult(plan_data=plan, summary=summary, plan_accepted=False)

        if intent["accepts"]:
            return PlanResult(plan_data=existing_plan, summary="Great! Let's begin!", plan_accepted=True)

        if intent["wants_modification"]:
            plan = await self._adapt_plan(state, user_message)
            summary = await self._format_plan_summary(plan, state)
            return PlanResult(plan_data=plan, summary=summary, plan_accepted=False)

        if intent["rejects"]:
            plan = await self._create_plan(state)
            summary = await self._format_plan_summary(plan, state)
            return PlanResult(plan_data=plan, summary=summary, plan_accepted=False)

        plan = await self._adapt_plan(state, user_message)
        summary = await self._format_plan_summary(plan, state)
        return PlanResult(plan_data=plan, summary=summary, plan_accepted=False)

    # ------------------------------------------------------------------
    # Plan creation with structured output
    # ------------------------------------------------------------------

    async def _create_plan(self, state: Dict[str, Any]) -> Dict[str, Any]:
        book_id = safe_get(state, "active_book_id") or safe_get(state, "book_id")
        chapters = safe_get_list(state, "chapters", [])
        if not chapters and book_id:
            chapters = await self._fetch_chapters_from_db(book_id)
        if not chapters:
            raise ValueError("No chapters available")

        chapter_details = self._format_chapter_details(chapters)
        target_days = max(1, safe_get_int(state, "target_days", 30))
        study_time = safe_get_int(state, "preferred_study_time_minutes", 30)
        book_title = safe_get(state, "book_title", "Learning Material")

        prompt = PLAN_PROMPT.format(
            title=book_title,
            total_chapters=len(chapters),
            chapter_details=chapter_details,
            study_time_minutes=study_time,
            learning_level=safe_get(state, "learning_level", "intermediate"),
            professor_level=safe_get(state, "professor_level", "mtech"),
            target_days=target_days,
            quiz_frequency=safe_get(state, "quiz_frequency", "after_each_chapter"),
            additional_instructions=safe_get(state, "additional_instructions", "None"),
        )

        llm = self._get_llm()
        try:
            structured_llm = llm.with_structured_output(LearningPlanSchema)
            plan_obj: LearningPlanSchema = await structured_llm.ainvoke([
                SystemMessage(content=PLANNER_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ])
            plan = plan_obj.model_dump()
        except Exception as e:
            logger.exception("structured_plan_failed", error=str(e))
            plan = await self._create_plan_fallback(prompt)

        plan["created_at"] = datetime.utcnow().isoformat()
        plan["version"] = 1
        plan["book_id"] = book_id
        plan["estimated_completion_date"] = (date.today() + timedelta(days=plan.get("total_days", target_days))).isoformat()
        return plan

    async def _create_plan_fallback(self, prompt: str) -> Dict[str, Any]:
        import json, re
        llm = self._get_llm()
        resp = await llm.ainvoke([
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        text = resp.content.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        start, end = text.find('{'), text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {"total_days": 30, "overview": "Plan generation failed", "days": [], "milestones": []}

    # ------------------------------------------------------------------
    # Plan adaptation
    # ------------------------------------------------------------------

    async def _adapt_plan(self, state: Dict[str, Any], reason: str) -> Dict[str, Any]:
        current_plan = safe_get_dict(state, "existing_plan", {}) or safe_get_dict(state, "learning_plan", {})
        prompt = ADAPT_PROMPT.format(
            current_plan=self._format_plan_for_prompt(current_plan),
            completed_chapters=len(safe_get_list(state, "completed_chapters", [])),
            avg_quiz_score=int(safe_get_float(state, "quiz_score", 0.7) * 100),
            total_study_time=safe_get_int(state, "total_study_time_minutes", 0),
            missed_sessions=safe_get_int(state, "missed_sessions", 0),
            days_elapsed=self._days_elapsed(current_plan),
            original_days=current_plan.get("total_days", 30),
            adaptation_reason=reason,
        )
        try:
            llm = self._get_llm()
            resp = await llm.ainvoke([SystemMessage(content=PLANNER_SYSTEM_PROMPT), HumanMessage(content=prompt)])
            import json, re
            text = re.sub(r'^```json\s*', '', resp.content.strip())
            text = re.sub(r'\s*```$', '', text)
            s, e = text.find('{'), text.rfind('}')
            adapted = json.loads(text[s:e + 1]) if s != -1 and e != -1 else current_plan
            adapted["adapted_at"] = datetime.utcnow().isoformat()
            adapted["version"] = current_plan.get("version", 1) + 1
            return adapted
        except Exception:
            return current_plan

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _format_plan_summary(self, plan: Dict[str, Any], state: Dict[str, Any]) -> str:
        title = safe_get(state, "book_title", "your book")
        days = plan.get("days", [])
        parts = [f"📚 **Your Learning Plan for \"{title}\"**\n", f"**Duration:** {plan.get('total_days', '?')} days\n"]
        if days:
            parts.append("\n**Schedule:**\n")
            for d in days[:5]:
                dn = d.get("day", 0)
                dt = d.get("day_title", f"Day {dn}")
                if d.get("rest"):
                    parts.append(f"- Day {dn}: 📖 {dt} (Review)\n")
                else:
                    topics = []
                    for item in d.get("items", []):
                        topics.extend(item.get("topics", []))
                    parts.append(f"- Day {dn}: {dt} — {', '.join(topics[:3]) or 'Study'}\n")
            if len(days) > 5:
                parts.append(f"- … and {len(days) - 5} more days\n")
        parts.append("\n**Does this plan work for you?** Say **yes** to start, or tell me what to change!")
        return "".join(parts)

    async def _fetch_chapters_from_db(self, book_id: str) -> List[Dict[str, Any]]:
        from app.db.database import async_session_maker
        from app.models.book import BookChapter, Book
        from sqlalchemy import select
        from uuid import UUID

        try:
            async with async_session_maker() as db:
                book = (await db.execute(select(Book).where(Book.id == UUID(book_id)))).scalar_one_or_none()
                rag_doc_id = book.book_metadata.get("rag_document_id") if book and book.book_metadata else None

                chapters = (await db.execute(
                    select(BookChapter).where(BookChapter.book_id == UUID(book_id)).order_by(BookChapter.chapter_number)
                )).scalars().all()

                if chapters:
                    return [{
                        "number": c.chapter_number,
                        "title": c.title or f"Chapter {c.chapter_number}",
                        "estimated_minutes": c.estimated_duration_minutes or 45,
                        "summary": c.summary or "",
                    } for c in chapters]

            if rag_doc_id:
                from app.integrations.rag_client.client import get_rag_client
                rag_chs = await get_rag_client().list_chapters(rag_doc_id)
                return [{
                    "number": i + 1,
                    "title": c.title or f"Chapter {i + 1}",
                    "estimated_minutes": 45,
                    "summary": c.summary or "",
                } for i, c in enumerate(rag_chs)]
        except Exception as e:
            logger.warning("fetch_chapters_failed", error=str(e))
        return []

    def _format_chapter_details(self, chapters: List[Dict[str, Any]]) -> str:
        lines = []
        for ch in chapters:
            n = ch.get("number", "?")
            t = ch.get("title", f"Chapter {n}")
            m = ch.get("estimated_minutes", 45)
            s = ch.get("summary", "")
            line = f"- Chapter {n}: {t} (~{m} min)"
            if s:
                line += f"\n  Topics: {s[:200]}"
            lines.append(line)
        return "\n".join(lines)

    def _format_plan_for_prompt(self, plan: Dict[str, Any]) -> str:
        days = plan.get("days", [])
        if not days:
            return "No plan yet"
        lines = [f"Total days: {plan.get('total_days', len(days))}"]
        for d in days[:10]:
            dn = d.get("day", "?")
            lines.append(f"Day {dn}: {'Rest' if d.get('rest') else ', '.join('Ch.' + str(i.get('chapter_number')) for i in d.get('items', []))}")
        if len(days) > 10:
            lines.append(f"… and {len(days) - 10} more")
        return "\n".join(lines)

    def _days_elapsed(self, plan: Dict[str, Any]) -> int:
        created = plan.get("created_at")
        if not created:
            return 0
        try:
            return (datetime.utcnow() - datetime.fromisoformat(created)).days
        except (ValueError, TypeError):
            return 0
