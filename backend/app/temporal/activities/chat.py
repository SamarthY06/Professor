"""Chat Activities - Bridge between Temporal workflows and LangGraph agents.

STATE CONTRACT:
    This module serialises/deserialises the canonical ``ProfessorState``
    (defined in ``app.langgraph.state``) to/from the ``LearningState`` DB
    model. Every key name used here MUST match the ``ProfessorState``
    TypedDict so that the graph nodes can read/write state without any
    ad-hoc translation layer in between.

    Canonical keys that flow through all layers:
        topics_covered_this_chapter  – list[str]
        quiz_questions               – list[dict] | None
        quiz_current_index           – int
        quiz_scores                  – list[float]
        quiz_passed                  – bool | None
        awaiting_quiz_decision       – bool

Security Note:
    API keys are loaded from the database inside activities, NOT passed
    through the Temporal workflow, so they never appear in event history.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID

from temporalio import activity

from app.logs.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DB  ↔  ProfessorState mapping helpers
# ---------------------------------------------------------------------------

def _quiz_state_from_db(pending_quiz_questions: Optional[dict]) -> Dict[str, Any]:
    """Deserialise quiz fields stored in ``LearningState.pending_quiz_questions``."""
    if not pending_quiz_questions or not isinstance(pending_quiz_questions, dict):
        return {
            "quiz_questions": None,
            "quiz_current_index": 0,
            "quiz_scores": [],
            "quiz_passed": None,
            "awaiting_quiz_decision": False,
        }
    return {
        "quiz_questions": pending_quiz_questions.get("quiz_questions"),
        "quiz_current_index": pending_quiz_questions.get("quiz_current_index", 0),
        "quiz_scores": pending_quiz_questions.get("quiz_scores", []),
        "quiz_passed": pending_quiz_questions.get("quiz_passed"),
        "awaiting_quiz_decision": pending_quiz_questions.get("awaiting_quiz_decision", False),
    }


def _quiz_state_to_db(state: Dict[str, Any]) -> Optional[dict]:
    """Serialise canonical quiz keys into the JSONB blob for ``pending_quiz_questions``."""
    phase = state.get("phase", "")
    questions = state.get("quiz_questions")
    index = state.get("quiz_current_index", 0)
    scores = state.get("quiz_scores", [])
    passed = state.get("quiz_passed")
    awaiting = state.get("awaiting_quiz_decision", False)

    if not questions and phase not in ("quiz", "quiz_feedback"):
        return None

    blob: dict = {}
    if questions:
        blob["quiz_questions"] = questions
    if index:
        blob["quiz_current_index"] = index
    if scores:
        blob["quiz_scores"] = scores
    if passed is not None:
        blob["quiz_passed"] = passed
    if awaiting:
        blob["awaiting_quiz_decision"] = awaiting
    return blob or None


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

@activity.defn
async def load_chat_state(user_id: str, book_id: str) -> Optional[Dict[str, Any]]:
    """Load the persisted chat state and return it using canonical ``ProfessorState`` keys."""
    from app.db.database import async_session_maker
    from app.models.learning import LearningState
    from app.models.learning_config import LearningPlan, LearningConfig
    from app.models.book import Book, BookChapter
    from sqlalchemy import select

    activity.heartbeat()

    try:
        async with async_session_maker() as db:
            ls_result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            learning_state = ls_result.scalar_one_or_none()
            if not learning_state:
                logger.info("no_existing_state", user_id=user_id, book_id=book_id)
                return None

            plan_result = await db.execute(
                select(LearningPlan)
                .where(LearningPlan.book_id == UUID(book_id))
                .where(LearningPlan.status == "accepted")
                .order_by(LearningPlan.created_at.desc())
            )
            plan = plan_result.scalar_one_or_none()

            book_result = await db.execute(select(Book).where(Book.id == UUID(book_id)))
            book = book_result.scalar_one_or_none()

            from app.services.plan_state import (
                resolve_plan_data,
                extract_pending_config,
                extract_config_conversation_history,
                resolve_learning_level,
                resolve_config_values,
            )

            # Load chapter titles for plan generation
            chapter_titles: List[str] = []
            try:
                ch_result = await db.execute(
                    select(BookChapter)
                    .where(BookChapter.book_id == UUID(book_id))
                    .order_by(BookChapter.chapter_number)
                )
                chapters = ch_result.scalars().all()
                chapter_titles = [
                    c.title or f"Chapter {c.chapter_number}" for c in chapters
                ]
            except Exception as ch_err:
                logger.warning("load_chapter_titles_failed", error=str(ch_err))

            raw_plan = learning_state.learning_plan
            plan_data = resolve_plan_data(
                raw_plan,
                accepted_plan_data=plan.plan_data if plan else None,
            )
            pending_cfg = extract_pending_config(raw_plan)

            # Load config from LearningConfig table as fallback
            config_result = await db.execute(
                select(LearningConfig).where(LearningConfig.book_id == UUID(book_id))
            )
            learning_config = config_result.scalar_one_or_none()

            target_days, daily_minutes, quiz_frequency = resolve_config_values(pending_cfg)

            # ------ build state dict using CANONICAL keys ------
            state: Dict[str, Any] = {
                # Identity
                "user_id": user_id,
                "book_id": book_id,
                "book_title": book.title if book else "your textbook",
                "total_chapters": book.total_chapters if book else 12,
                # Phase & progress
                "phase": getattr(learning_state, "current_phase", None) or "config_gathering",
                "current_day": learning_state.current_day or 1,
                "current_chapter": learning_state.current_chapter or 1,
                "completed_days": learning_state.completed_days or [],
                "completed_chapters": learning_state.completed_chapters or [],
                # Plan
                "plan_data": plan_data,
                # Teaching
                "professor_level": learning_state.professor_level or "intermediate",
                "topics_covered_this_chapter": learning_state.pending_topics or [],
                # Config gathering state
                "config_conversation_history": extract_config_conversation_history(raw_plan),
                "learning_level": resolve_learning_level(
                    pending_cfg,
                    learning_config_level=learning_config.learning_level if learning_config else None,
                    professor_level=learning_state.professor_level,
                ),
                "target_days": target_days,
                "daily_minutes": daily_minutes,
                "quiz_frequency": quiz_frequency,
                # Chapter metadata
                "chapter_titles": chapter_titles,
                # Summaries
                "day_summaries": getattr(learning_state, "day_summaries", None) or {},
                "chapter_summaries": getattr(learning_state, "chapter_summaries", None) or {},
                "cumulative_summary": getattr(learning_state, "cumulative_summary", None) or "",
                # Metrics
                "total_study_time_minutes": learning_state.total_study_time_minutes or 0,
                # State management
                "state_version": getattr(learning_state, "state_version", 0) or 0,
                "last_session_date": (
                    learning_state.last_active_at.isoformat()
                    if learning_state.last_active_at
                    else None
                ),
            }

            # Quiz state (deserialised from JSONB)
            state.update(_quiz_state_from_db(learning_state.pending_quiz_questions))

            logger.info(
                "state_loaded",
                user_id=user_id,
                book_id=book_id,
                phase=state["phase"],
                day=state["current_day"],
                chapter=state["current_chapter"],
                topics_count=len(state["topics_covered_this_chapter"]),
                has_quiz=bool(state.get("quiz_questions")),
            )
            return state

    except Exception as e:
        logger.exception("load_state_failed", error=str(e))
        return None


@activity.defn
async def save_chat_state(user_id: str, book_id: str, state: Dict[str, Any]) -> bool:
    """Persist the canonical ``ProfessorState`` dict back to the DB."""
    from app.db.database import async_session_maker
    from app.models.learning import LearningState
    from sqlalchemy import select

    activity.heartbeat()

    try:
        async with async_session_maker() as db:
            async with db.begin():
                result = await db.execute(
                    select(LearningState)
                    .where(LearningState.user_id == UUID(user_id))
                    .where(LearningState.book_id == UUID(book_id))
                )
                ls = result.scalar_one_or_none()

                if not ls:
                    ls = LearningState(user_id=UUID(user_id), book_id=UUID(book_id))
                    db.add(ls)

                # ---- Map canonical keys → DB columns ----
                if hasattr(ls, "current_phase"):
                    ls.current_phase = state.get("phase", "greeting")
                ls.current_day = state.get("current_day", 1)
                ls.current_chapter = state.get("current_chapter", 1)
                ls.completed_days = state.get("completed_days", [])
                ls.completed_chapters = state.get("completed_chapters", [])
                ls.pending_topics = state.get("topics_covered_this_chapter", [])
                ls.professor_level = state.get("professor_level", "intermediate")
                ls.total_study_time_minutes = state.get("total_study_time_minutes", 0)
                ls.last_active_at = datetime.utcnow()

                # Persist gathered config and conversation history in the
                # learning_plan JSONB so they survive across workflow restarts
                # without requiring a DB migration for new columns.
                from app.services.plan_state import build_pending_plan_blob
                phase = state.get("phase", "")
                if phase in ("config_gathering", "planning") and not state.get("plan_data"):
                    ls.learning_plan = build_pending_plan_blob(state, ls.learning_plan)

                # When config gathering completes (phase -> planning), sync the
                # gathered preferences to the LearningConfig table so the plan
                # page's REST generate endpoint uses the right values.
                if phase == "planning":
                    from app.models.learning_config import LearningConfig
                    from datetime import date as date_type, timedelta
                    lc_result = await db.execute(
                        select(LearningConfig).where(
                            LearningConfig.book_id == UUID(book_id)
                        )
                    )
                    lc = lc_result.scalar_one_or_none()
                    if lc:
                        lc.learning_level = state.get("learning_level", lc.learning_level)
                        lc.daily_study_minutes = state.get("daily_minutes", lc.daily_study_minutes)
                        lc.quiz_frequency = state.get("quiz_frequency", lc.quiz_frequency)
                        target_days = state.get("target_days", 30)
                        lc.deadline = date_type.today() + timedelta(days=target_days)

                # Optimistic locking — detect concurrent writes
                if hasattr(ls, "state_version"):
                    expected_version = state.get("state_version", 0)
                    db_version = ls.state_version or 0
                    if db_version != expected_version:
                        logger.warning(
                            "state_version_conflict",
                            user_id=user_id,
                            book_id=book_id,
                            expected=expected_version,
                            actual=db_version,
                        )
                    ls.state_version = db_version + 1

                # Quiz state → JSONB
                ls.pending_quiz_questions = _quiz_state_to_db(state)

                # Summaries
                if hasattr(ls, "day_summaries"):
                    ls.day_summaries = state.get("day_summaries", {})
                if hasattr(ls, "chapter_summaries"):
                    ls.chapter_summaries = state.get("chapter_summaries", {})
                if hasattr(ls, "cumulative_summary"):
                    ls.cumulative_summary = state.get("cumulative_summary", "")

                # Plan data — only overwrite when we have a real plan (with days)
                plan_data = state.get("plan_data")
                if plan_data and isinstance(plan_data, dict) and plan_data.get("days"):
                    ls.learning_plan = plan_data

                    # Sync to LearningPlan table so the plan review page
                    # (/learn/[id]/plan) can find it via GET /api/planning/{book_id}/current
                    from app.models.learning_config import LearningPlan, LearningConfig
                    try:
                        lc_result = await db.execute(
                            select(LearningConfig).where(
                                LearningConfig.book_id == UUID(book_id)
                            )
                        )
                        lc = lc_result.scalar_one_or_none()
                        if lc:
                            existing_lp = await db.execute(
                                select(LearningPlan)
                                .where(LearningPlan.book_id == UUID(book_id))
                                .where(LearningPlan.user_id == UUID(user_id))
                                .order_by(LearningPlan.version.desc())
                            )
                            old_lp = existing_lp.scalar_one_or_none()
                            if old_lp and old_lp.status == "pending_review":
                                old_lp.plan_data = plan_data
                                old_lp.plan_summary = plan_data.get("overview", "")
                                old_lp.version += 1
                            else:
                                if old_lp and old_lp.status == "pending_review":
                                    old_lp.status = "superseded"
                                new_lp = LearningPlan(
                                    config_id=lc.id,
                                    user_id=UUID(user_id),
                                    book_id=UUID(book_id),
                                    plan_data=plan_data,
                                    plan_summary=plan_data.get("overview", ""),
                                    version=(old_lp.version + 1) if old_lp else 1,
                                    status="pending_review",
                                )
                                db.add(new_lp)
                    except Exception as lp_err:
                        logger.warning("sync_learning_plan_failed", error=str(lp_err))

                await db.commit()

        logger.info(
            "state_saved",
            user_id=user_id,
            book_id=book_id,
            phase=state.get("phase"),
            day=state.get("current_day"),
            topics=len(state.get("topics_covered_this_chapter", [])),
        )
        return True

    except Exception as e:
        logger.exception("save_state_failed", error=str(e))
        return False


@activity.defn
async def load_conversation_history(
    user_id: str,
    book_id: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Load recent conversation messages for context injection."""
    from app.db.database import async_session_maker
    from app.models.chat import ChatSession, ChatMessage
    from sqlalchemy import select

    activity.heartbeat()

    try:
        async with async_session_maker() as db:
            session_result = await db.execute(
                select(ChatSession)
                .where(ChatSession.user_id == UUID(user_id))
                .where(ChatSession.book_id == UUID(book_id))
                .where(ChatSession.is_active == True)
                .order_by(ChatSession.created_at.desc())
            )
            session = session_result.scalar_one_or_none()
            if not session:
                return []

            messages_result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            )
            messages = messages_result.scalars().all()

            return [
                {
                    "role": m.role,
                    "content": m.content,
                    "agent_name": m.agent_name,
                    "created_at": m.created_at.isoformat(),
                }
                for m in reversed(messages)
            ]

    except Exception as e:
        logger.exception("load_history_failed", error=str(e))
        return []


@activity.defn
async def get_initial_greeting(user_id: str, book_id: str) -> str:
    """Return the initial greeting for a new session."""
    from app.db.database import async_session_maker
    from app.models.book import Book
    from sqlalchemy import select

    activity.heartbeat()

    try:
        async with async_session_maker() as db:
            result = await db.execute(select(Book).where(Book.id == UUID(book_id)))
            book = result.scalar_one_or_none()
            book_title = book.title if book else "your textbook"
            total_chapters = book.total_chapters if book else "several"

        return (
            f"👋 Welcome! I'm your Professor, and I'm excited to guide you through **{book_title}**.\n\n"
            f"This book has **{total_chapters} chapters**, and I'll create a personalized learning plan "
            f"tailored to your goals and schedule.\n\n"
            f"Before we begin, I'd like to understand:\n"
            f"- How much time you can dedicate daily\n"
            f"- Your target completion timeframe\n"
            f"- Your current knowledge level\n\n"
            f"Ready to get started? Just say **yes** and we'll begin planning your learning journey!"
        )

    except Exception as e:
        logger.exception("greeting_failed", error=str(e))
        return (
            "👋 Welcome! I'm your Professor, ready to guide you through your learning journey.\n\n"
            "Say **yes** when you're ready to begin!"
        )


@activity.defn
async def process_chat_message(
    message: str,
    state: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Process a chat message through LangGraph.

    Because ``load_chat_state`` already returns canonical ``ProfessorState``
    keys and the graph reads/writes those same keys, this function does NOT
    perform any key translation.  It merges ephemeral context (conversation
    history, API key) into the state, calls the graph, and extracts the
    resulting state back out — all using the same key names.
    """
    from app.langgraph.graph import process_message
    from app.db.database import async_session_maker
    from app.services.api_key_service import APIKeyService

    activity.heartbeat()

    try:
        # Securely load the API key (never passed through workflow history)
        api_key = None
        async with async_session_maker() as db:
            api_key_service = APIKeyService(db)
            try:
                api_key = await api_key_service.get_api_key_for_user(UUID(state["user_id"]))
            except ValueError:
                logger.warning("no_api_key", user_id=state["user_id"])

        if not api_key:
            return {
                "response": (
                    "I notice you haven't set up your API key yet. "
                    "Please add your OpenAI API key in settings to continue."
                ),
                "new_state": state,
                "phase": state.get("phase", "greeting"),
                "error": "no_api_key",
            }

        activity.heartbeat()

        # Build graph input — state already uses canonical keys, just add
        # the ephemeral per-message fields.
        langgraph_state = {
            **state,
            "user_message": message,
            "api_key": api_key,
            "conversation_history": context.get("conversation_history", []),
            "config_conversation_history": context.get("config_conversation_history") or state.get("config_conversation_history", []),
            "cumulative_summary": context.get("cumulative_summary", ""),
            "previous_day_summary": context.get("previous_day_summary", {}),
            "previous_chapter_summary": context.get("previous_chapter_summary", {}),
        }

        result = await process_message(
            user_id=state.get("user_id", ""),
            session_id=state.get("session_id", ""),
            book_id=state.get("book_id", ""),
            message=message,
            current_state=langgraph_state,
        )

        activity.heartbeat()

        response = result.get("response", "") or result.get("professor_response", "")
        result_state = result.get("state", {})

        # Extract the new state from the merged graph output.
        # ``result_state`` is ``{**input_state, **node_output}`` so it
        # already contains the canonical keys.  We pick out the ones we
        # need to persist and fall back to the input state for anything
        # the graph didn't touch.
        def _pick(key: str, default=None):
            """Prefer result_state, fall back to input state."""
            return result_state.get(key, state.get(key, default))

        new_state: Dict[str, Any] = {
            # Identity (immutable)
            "user_id": state["user_id"],
            "book_id": state["book_id"],
            # Phase & progress
            "phase": result.get("phase", state.get("phase", "greeting")),
            "current_day": _pick("current_day", 1),
            "current_chapter": _pick("current_chapter", 1),
            "completed_days": _pick("completed_days", []),
            "completed_chapters": _pick("completed_chapters", []),
            # Plan
            "plan_data": _pick("plan_data"),
            # Teaching — canonical key, no aliases
            "professor_level": _pick("professor_level", "intermediate"),
            "topics_covered_this_chapter": _pick("topics_covered_this_chapter", []),
            # Config gathering — must survive across multi-turn config flow
            "config_conversation_history": _pick("config_conversation_history", []),
            "learning_level": _pick("learning_level", "intermediate"),
            "target_days": _pick("target_days", 30),
            "daily_minutes": _pick("daily_minutes", 30),
            "quiz_frequency": _pick("quiz_frequency", "after_each_chapter"),
            # Chapter metadata
            "chapter_titles": _pick("chapter_titles", []),
            # Quiz — canonical keys
            "quiz_questions": _pick("quiz_questions"),
            "quiz_current_index": _pick("quiz_current_index", 0),
            "quiz_scores": _pick("quiz_scores", []),
            "quiz_passed": _pick("quiz_passed"),
            "awaiting_quiz_decision": _pick("awaiting_quiz_decision", False),
            # Summaries
            "day_summaries": _pick("day_summaries", {}),
            "chapter_summaries": _pick("chapter_summaries", {}),
            "cumulative_summary": _pick("cumulative_summary", ""),
            # Metrics
            "total_study_time_minutes": _pick("total_study_time_minutes", 0),
            "plan_iteration_count": _pick("plan_iteration_count", 0),
        }

        logger.info(
            "message_processed",
            phase=new_state["phase"],
            day=new_state["current_day"],
            chapter=new_state["current_chapter"],
            topics=len(new_state["topics_covered_this_chapter"]),
            quiz_index=new_state["quiz_current_index"],
            response_length=len(response),
        )

        return {
            "response": response,
            "new_state": new_state,
            "phase": new_state["phase"],
        }

    except Exception as e:
        logger.exception("process_message_failed", error=str(e))
        return {
            "response": (
                "I apologize, but I encountered an issue processing your message. "
                "Could you please try again?"
            ),
            "new_state": state,
            "phase": state.get("phase", "greeting"),
            "error": str(e),
        }


@activity.defn
async def generate_day_summary(
    user_id: str,
    book_id: str,
    day_number: int,
    topics_covered: List[str],
) -> str:
    """Generate a short LLM summary for a completed day."""
    from app.db.database import async_session_maker
    from app.services.api_key_service import APIKeyService
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    activity.heartbeat()

    fallback = f"Day {day_number}: Covered {', '.join(topics_covered) if topics_covered else 'various topics'}."

    try:
        api_key = None
        async with async_session_maker() as db:
            api_key_service = APIKeyService(db)
            try:
                api_key = await api_key_service.get_api_key_for_user(UUID(user_id))
            except ValueError:
                pass

        if not api_key or not topics_covered:
            return fallback

        activity.heartbeat()

        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.3)
        prompt = (
            f"Summarize what was learned on Day {day_number} in 2-3 sentences.\n\n"
            f"Topics covered:\n" + "\n".join(f"- {t}" for t in topics_covered) +
            f"\n\nWrite a concise summary. Start with \"On Day {day_number}...\""
        )

        response = await llm.ainvoke([
            SystemMessage(content="You are a helpful teaching assistant summarizing learning progress."),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()

    except Exception as e:
        logger.exception("generate_day_summary_failed", error=str(e))
        return fallback
