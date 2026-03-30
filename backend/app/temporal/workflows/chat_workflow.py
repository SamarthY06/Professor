"""Chat Workflow - Durable chat session management.

Architecture:
    User → FastAPI → Temporal Workflow → Activities → DB
                          ↓
                    LangGraph (as activity)

STATE CONTRACT:
    The ``ChatState`` dataclass in this module MUST use the same key names
    as the canonical ``ProfessorState`` TypedDict (defined in
    ``app.langgraph.state``) and as the serialisation layer in
    ``app.temporal.activities.chat``.  Every field that needs to survive
    across messages must be present here — otherwise the ``to_dict()`` /
    ``from_dict()`` round-trip will silently drop it.

Security:
    API keys are loaded inside activities, never passed through workflow
    signals/queries so they never appear in Temporal event history.
"""

from datetime import timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.chat import (
        load_chat_state,
        process_chat_message,
        save_chat_state,
        get_initial_greeting,
        generate_day_summary,
        load_conversation_history,
    )
    from app.temporal.activities.teaching import generate_chapter_summary


@dataclass
class ChatState:
    """Workflow-local mirror of the persisted learning state.

    Every field here maps 1:1 to a canonical ``ProfessorState`` key and to a
    column (or JSONB sub-key) in the ``LearningState`` DB model.  Adding a
    new persistent field requires updating:
        1. This dataclass (field + to_dict + from_dict)
        2. ``load_chat_state`` / ``save_chat_state`` in activities
        3. ``ProfessorState`` TypedDict in ``app.langgraph.state``
    """

    # Identity & book metadata (not persisted, but needed by graph nodes)
    user_id: str = ""
    book_id: str = ""
    book_title: str = ""
    total_chapters: int = 0

    # Phase & progress
    phase: str = "greeting"
    current_day: int = 1
    current_chapter: int = 1
    completed_days: List[int] = field(default_factory=list)
    completed_chapters: List[int] = field(default_factory=list)

    # Plan & teaching
    plan_data: Optional[Dict[str, Any]] = None
    professor_level: str = "intermediate"
    topics_covered_this_chapter: List[str] = field(default_factory=list)

    # Config gathering — must survive across messages for multi-turn flow
    config_conversation_history: List[Dict[str, str]] = field(default_factory=list)
    learning_level: str = "intermediate"
    target_days: int = 30
    daily_minutes: int = 30
    quiz_frequency: str = "after_each_chapter"

    # Chapter metadata for plan generation
    chapter_titles: List[str] = field(default_factory=list)

    # Quiz — must survive across messages for multi-turn quiz flow
    quiz_questions: Optional[List[Dict[str, Any]]] = None
    quiz_current_index: int = 0
    quiz_scores: List[float] = field(default_factory=list)
    quiz_passed: Optional[bool] = None
    awaiting_quiz_decision: bool = False

    # Summaries
    day_summaries: Dict[str, Any] = field(default_factory=dict)
    chapter_summaries: Dict[str, Any] = field(default_factory=dict)
    cumulative_summary: str = ""

    # Metrics
    last_session_date: Optional[str] = None
    total_study_time_minutes: int = 0
    plan_iteration_count: int = 0

    # Optimistic locking
    state_version: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "book_id": self.book_id,
            "book_title": self.book_title,
            "total_chapters": self.total_chapters,
            "phase": self.phase,
            "current_day": self.current_day,
            "current_chapter": self.current_chapter,
            "completed_days": self.completed_days,
            "completed_chapters": self.completed_chapters,
            "plan_data": self.plan_data,
            "professor_level": self.professor_level,
            "topics_covered_this_chapter": self.topics_covered_this_chapter,
            "config_conversation_history": self.config_conversation_history,
            "learning_level": self.learning_level,
            "target_days": self.target_days,
            "daily_minutes": self.daily_minutes,
            "quiz_frequency": self.quiz_frequency,
            "chapter_titles": self.chapter_titles,
            "quiz_questions": self.quiz_questions,
            "quiz_current_index": self.quiz_current_index,
            "quiz_scores": self.quiz_scores,
            "quiz_passed": self.quiz_passed,
            "awaiting_quiz_decision": self.awaiting_quiz_decision,
            "day_summaries": self.day_summaries,
            "chapter_summaries": self.chapter_summaries,
            "cumulative_summary": self.cumulative_summary,
            "last_session_date": self.last_session_date,
            "total_study_time_minutes": self.total_study_time_minutes,
            "plan_iteration_count": self.plan_iteration_count,
            "state_version": self.state_version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatState":
        return cls(
            user_id=data.get("user_id", ""),
            book_id=data.get("book_id", ""),
            book_title=data.get("book_title", ""),
            total_chapters=data.get("total_chapters", 0),
            phase=data.get("phase", "greeting"),
            current_day=data.get("current_day", 1),
            current_chapter=data.get("current_chapter", 1),
            completed_days=data.get("completed_days") or [],
            completed_chapters=data.get("completed_chapters") or [],
            plan_data=data.get("plan_data"),
            professor_level=data.get("professor_level", "intermediate"),
            topics_covered_this_chapter=data.get("topics_covered_this_chapter") or [],
            config_conversation_history=data.get("config_conversation_history") or [],
            learning_level=data.get("learning_level", "intermediate"),
            target_days=data.get("target_days", 30),
            daily_minutes=data.get("daily_minutes", 30),
            quiz_frequency=data.get("quiz_frequency", "after_each_chapter"),
            chapter_titles=data.get("chapter_titles") or [],
            quiz_questions=data.get("quiz_questions"),
            quiz_current_index=data.get("quiz_current_index", 0),
            quiz_scores=data.get("quiz_scores") or [],
            quiz_passed=data.get("quiz_passed"),
            awaiting_quiz_decision=data.get("awaiting_quiz_decision", False),
            day_summaries=data.get("day_summaries") or {},
            chapter_summaries=data.get("chapter_summaries") or {},
            cumulative_summary=data.get("cumulative_summary", ""),
            last_session_date=data.get("last_session_date"),
            total_study_time_minutes=data.get("total_study_time_minutes", 0),
            plan_iteration_count=data.get("plan_iteration_count", 0),
            state_version=data.get("state_version", 0),
        )


@workflow.defn
class ChatWorkflow:
    """Durable chat workflow for learning sessions.

    Flow: Planning → Teaching → Quiz → Day transition → repeat
    """

    def __init__(self):
        self._state: Optional[ChatState] = None
        self._pending_message: Optional[str] = None
        self._latest_response: Optional[str] = None
        self._response_ready = False
        self._session_ended = False
        self._conversation_history: List[Dict[str, Any]] = []

    @workflow.run
    async def run(self, user_id: str, book_id: str) -> Dict[str, Any]:
        workflow.logger.info(f"Starting chat workflow for user {user_id}, book {book_id}")

        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(minutes=1),
            backoff_coefficient=2.0,
        )

        # Backward-compatible versioning: any running workflow that was started
        # before this deployment will skip the patched block and keep its old
        # behaviour; new workflows take the new path.
        if workflow.patched("v2-state-version"):
            pass  # new-path marker — no extra logic yet, just a compatibility fence

        state_data = await workflow.execute_activity(
            load_chat_state,
            args=[user_id, book_id],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        self._state = (
            ChatState.from_dict(state_data) if state_data
            else ChatState(user_id=user_id, book_id=book_id)
        )

        self._conversation_history = await workflow.execute_activity(
            load_conversation_history,
            args=[user_id, book_id, 20],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        if self._state.phase == "greeting" and not self._conversation_history:
            greeting = await workflow.execute_activity(
                get_initial_greeting,
                args=[user_id, book_id],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            self._latest_response = greeting
            self._response_ready = True

        event_count = 0

        while not self._session_ended and self._state.phase != "completed":
            try:
                await workflow.wait_condition(
                    lambda: self._pending_message is not None or self._session_ended,
                    timeout=timedelta(hours=24),
                )
            except TimeoutError:
                workflow.logger.info("Session timed out due to inactivity")
                break

            if self._session_ended:
                break

            if self._pending_message:
                message = self._pending_message
                self._pending_message = None
                self._response_ready = False

                context = self._build_context()

                result = await workflow.execute_activity(
                    process_chat_message,
                    args=[message, self._state.to_dict(), context],
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=retry_policy,
                    heartbeat_timeout=timedelta(seconds=60),
                )

                if result.get("new_state"):
                    old_day = self._state.current_day
                    old_chapter = self._state.current_chapter
                    new_state_data = result["new_state"]
                    self._state = ChatState.from_dict(new_state_data)

                    if self._state.current_day > old_day:
                        await self._handle_day_transition(old_day, retry_policy)

                    if self._state.current_chapter > old_chapter:
                        await self._handle_chapter_transition(old_chapter, retry_policy)

                response_text = result.get("response", "")
                self._latest_response = response_text
                self._response_ready = True

                # Keep conversation history in sync so subsequent messages
                # have full context (prevents the teacher from repeating itself)
                self._conversation_history.append({"role": "user", "content": message})
                self._conversation_history.append({"role": "assistant", "content": response_text})
                # Trim to prevent unbounded growth
                if len(self._conversation_history) > 30:
                    self._conversation_history = self._conversation_history[-20:]

                await workflow.execute_activity(
                    save_chat_state,
                    args=[user_id, book_id, self._state.to_dict()],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry_policy,
                )

                event_count += 1
                workflow.logger.info(
                    f"Message processed, phase: {self._state.phase}, "
                    f"day: {self._state.current_day}, chapter: {self._state.current_chapter}"
                )

                if event_count >= 500:
                    workflow.logger.info("Event limit reached, continuing as new workflow")
                    await workflow.execute_activity(
                        save_chat_state,
                        args=[user_id, book_id, self._state.to_dict()],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=retry_policy,
                    )
                    workflow.continue_as_new(user_id, book_id)

        await workflow.execute_activity(
            save_chat_state,
            args=[user_id, book_id, self._state.to_dict()],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry_policy,
        )

        return {
            "status": "completed" if self._state.phase == "completed" else "ended",
            "user_id": user_id,
            "book_id": book_id,
            "final_day": self._state.current_day,
            "completed_days": self._state.completed_days,
            "completed_chapters": self._state.completed_chapters,
        }

    def _build_context(self) -> Dict[str, Any]:
        """Build context including summaries, config history, and recent chat."""
        context: Dict[str, Any] = {
            "conversation_history": self._conversation_history[-10:],
            "cumulative_summary": self._state.cumulative_summary,
            "day_summaries": self._state.day_summaries,
            "chapter_summaries": self._state.chapter_summaries,
            "config_conversation_history": self._state.config_conversation_history,
        }

        if self._state.current_day > 1:
            prev_day_key = f"day_{self._state.current_day - 1}"
            if prev_day_key in self._state.day_summaries:
                context["previous_day_summary"] = self._state.day_summaries[prev_day_key]

        if self._state.current_chapter > 1:
            prev_ch_key = f"chapter_{self._state.current_chapter - 1}"
            if prev_ch_key in self._state.chapter_summaries:
                context["previous_chapter_summary"] = self._state.chapter_summaries[prev_ch_key]

        return context

    async def _handle_day_transition(self, completed_day: int, retry_policy: RetryPolicy):
        """Generate and store a summary when a day is completed."""
        workflow.logger.info(f"Day {completed_day} completed, generating summary")

        summary = await workflow.execute_activity(
            generate_day_summary,
            args=[
                self._state.user_id,
                self._state.book_id,
                completed_day,
                self._state.topics_covered_this_chapter,
            ],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )

        day_key = f"day_{completed_day}"
        self._state.day_summaries[day_key] = {
            "summary": summary,
            "topics": self._state.topics_covered_this_chapter.copy(),
            "date": workflow.now().isoformat(),
        }

        self._state.topics_covered_this_chapter = []
        self._state.cumulative_summary = self._build_cumulative_summary()

    async def _handle_chapter_transition(self, completed_chapter: int, retry_policy: RetryPolicy):
        """Generate and store a summary when a chapter is completed."""
        workflow.logger.info(f"Chapter {completed_chapter} completed, generating summary")

        summary = await workflow.execute_activity(
            generate_chapter_summary,
            args=[
                self._state.user_id,
                self._state.book_id,
                completed_chapter,
            ],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )

        chapter_key = f"chapter_{completed_chapter}"
        self._state.chapter_summaries[chapter_key] = {
            "summary": summary,
            "completed_at": workflow.now().isoformat(),
        }

        self._state.cumulative_summary = self._build_cumulative_summary()

    _MAX_CUMULATIVE_SUMMARY_CHARS = 2000

    def _build_cumulative_summary(self) -> str:
        """Build a cumulative summary from the most recent day and chapter summaries.

        Keeps only the last 3 chapter + last 3 day summaries and truncates
        the combined output to _MAX_CUMULATIVE_SUMMARY_CHARS to prevent
        unbounded growth that eats into LLM context windows.
        """
        parts = []

        chapter_keys = sorted(self._state.chapter_summaries.keys())[-3:]
        for chapter_key in chapter_keys:
            chapter_data = self._state.chapter_summaries[chapter_key]
            parts.append(f"**{chapter_key.replace('_', ' ').title()}**: {chapter_data.get('summary', '')}")

        day_keys = sorted(self._state.day_summaries.keys(), reverse=True)[:3]
        for day_key in reversed(day_keys):
            day_data = self._state.day_summaries[day_key]
            parts.append(f"**{day_key.replace('_', ' ').title()}**: {day_data.get('summary', '')}")

        combined = "\n\n".join(parts) if parts else ""
        if len(combined) > self._MAX_CUMULATIVE_SUMMARY_CHARS:
            combined = combined[: self._MAX_CUMULATIVE_SUMMARY_CHARS - 3] + "..."
        return combined

    @workflow.update
    async def send_and_wait(self, message: str) -> Dict[str, Any]:
        """Accept a user message, wait for it to be processed, return the response.

        This replaces the old signal+poll pattern.  The API calls
        ``handle.execute_update(ChatWorkflow.send_and_wait, msg)`` and
        blocks only for the actual LLM processing time (~5-15 s) instead
        of polling for up to 90 s.
        """
        self._pending_message = message
        self._response_ready = False

        await workflow.wait_condition(
            lambda: self._response_ready,
            timeout=timedelta(minutes=3),
        )

        return {
            "response": self._latest_response,
            "ready": self._response_ready,
            "phase": self._state.phase if self._state else "unknown",
            "current_day": self._state.current_day if self._state else 1,
            "current_chapter": self._state.current_chapter if self._state else 1,
        }

    @workflow.signal
    def send_message(self, message: str):
        """Receive a message from the user (kept for backward-compat)."""
        self._pending_message = message

    @workflow.signal
    def end_session(self):
        """End the chat session."""
        self._session_ended = True

    @workflow.query
    def get_response(self) -> Dict[str, Any]:
        """Query the latest response (kept for backward-compat)."""
        return {
            "response": self._latest_response if self._response_ready else None,
            "ready": self._response_ready,
            "phase": self._state.phase if self._state else "unknown",
            "current_day": self._state.current_day if self._state else 1,
            "current_chapter": self._state.current_chapter if self._state else 1,
        }

    @workflow.query
    def get_state(self) -> Dict[str, Any]:
        """Query the current state."""
        if self._state:
            return self._state.to_dict()
        return {}

    @workflow.query
    def get_summaries(self) -> Dict[str, Any]:
        """Query the day and chapter summaries."""
        if self._state:
            return {
                "day_summaries": self._state.day_summaries,
                "chapter_summaries": self._state.chapter_summaries,
                "cumulative_summary": self._state.cumulative_summary,
            }
        return {}
