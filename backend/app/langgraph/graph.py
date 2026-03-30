"""LangGraph workflow for Professor - TRUE Agent-Driven Architecture.

Key Design Principle:
- NO intent detection/classification layer
- Each agent decides its own next action
- Agents return BOTH response AND next_phase
- The LLM IS the router - it understands context naturally
- This is an AGENTIC platform, not a rule-based chatbot

Flow:
1. User message goes to current phase's agent
2. Agent processes with full context (including user message)
3. Agent returns response + decides next phase
4. No external routing logic needed - agents are autonomous
"""

from typing import Dict, Any, Optional
from datetime import datetime

from app.langgraph.state import (
    ProfessorState, 
    should_trigger_quiz,
    reset_chapter_state,
)
from app.logs.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# AGENT NODES - Each agent handles its phase completely
# ============================================================================

async def greeting_node(state: ProfessorState) -> Dict[str, Any]:
    """
    GreetingAgent: Welcomes user and offers to create a learning plan.
    
    This is a simple node - just displays greeting.
    The PlannerAgent will handle the user's response.
    """
    book_title = state.get("book_title", "your learning material")
    total_chapters = state.get("total_chapters", 0)
    learning_level = state.get("learning_level", "intermediate")
    
    level_note = {
        "beginner": "I'll explain concepts clearly with plenty of examples.",
        "intermediate": "I'll balance depth with clarity.",
        "advanced": "I'll dive deep into technical details.",
        "research": "I'll focus on advanced analysis.",
    }.get(learning_level, "")
    
    greeting = f"""Hello! 👋

I've analyzed **"{book_title}"** with **{total_chapters or 'several'} chapters**.

{level_note}

**Would you like me to create a personalized learning plan?**

Just say **"Yes"** when you're ready!"""
    
    return {
        "professor_response": greeting,
        "response_type": "greeting",
        "phase": "greeting",
        "active_agent": "none",
        "agent_name": "Professor",
    }


async def config_gathering_node(state: ProfessorState) -> Dict[str, Any]:
    """
    ConfigGatheringAgent: Conversationally gathers user preferences.
    
    This agent uses tools to ask the user about:
    - How many days they want to study
    - How much time per day
    - Learning level (beginner/intermediate/advanced)
    - Quiz frequency
    - Professor level
    
    The agent drives the conversation until all config is gathered,
    then generates the learning plan.
    """
    from app.agents.planner import gather_config_conversationally
    
    book_id = state.get("book_id", "")
    book_title = state.get("book_title", "")
    user_id = state.get("user_id", "")
    total_chapters = state.get("total_chapters", 12)
    user_message = state.get("user_message", "")
    # Prefer dedicated config history; fall back to general conversation
    # history (loaded from ChatMessage records) so the agent has context
    # even after a Temporal workflow restart.
    conversation_history = (
        state.get("config_conversation_history")
        or state.get("conversation_history", [])
    )
    api_key = state.get("api_key", "")
    
    logger.info(
        "config_gathering_node",
        book_id=book_id,
        book_title=book_title,
        total_chapters=total_chapters,
        has_api_key=bool(api_key),
    )
    
    # Use the conversational config gathering agent
    result = await gather_config_conversationally(
        book_id=book_id,
        book_title=book_title,
        user_id=user_id,
        total_chapters=total_chapters,
        user_message=user_message,
        conversation_history=conversation_history,
        api_key=api_key,
    )
    
    response = result.get("response", "")
    config_complete = result.get("config_complete", False)
    config = result.get("config")
    
    # Update conversation history
    new_history = list(conversation_history)
    new_history.append({"role": "user", "content": user_message})
    new_history.append({"role": "assistant", "content": response})
    
    response_data = {
        "professor_response": response,
        "response_type": "config_gathering",
        "phase": "config_gathering",
        "active_agent": "planner",
        "agent_name": "Professor",
        "config_conversation_history": new_history,
    }
    
    # If config is complete, transition to planning
    if config_complete and config:
        response_data["phase"] = "planning"
        response_data["learning_config"] = config
        response_data["learning_level"] = config.get("learning_level", "intermediate")
        response_data["professor_level"] = config.get("professor_level", "intermediate")
        response_data["target_days"] = config.get("target_days", 30)
        response_data["daily_minutes"] = config.get("daily_minutes", 30)
        response_data["quiz_frequency"] = config.get("quiz_frequency", "after_each_chapter")
        
        logger.info(
            "config_gathering_complete",
            config=config,
        )
    
    return response_data


async def planning_node(state: ProfessorState) -> Dict[str, Any]:
    """
    PlannerAgent: Generates and iterates on learning plans.
    
    This is called AFTER config gathering is complete.
    The agent:
    - Creates a plan based on gathered config
    - Presents the plan to the user
    - Handles acceptance/rejection/modification
    """
    from app.agents.planner import PlannerAgent
    
    api_key = state.get("api_key")
    book_id = state.get("book_id", "")
    user_id = state.get("user_id", "")
    book_title = state.get("book_title", "")
    total_chapters = state.get("total_chapters", 12)
    chapter_titles = state.get("chapter_titles", [])
    user_message = state.get("user_message", "")
    plan_iteration_count = state.get("plan_iteration_count", 0)
    raw_plan_data = state.get("plan_data")
    
    # Get config from state (gathered in config_gathering phase)
    # Also check learning_plan.pending_config for persisted config
    pending_config = {}
    existing_plan = None
    
    if raw_plan_data and isinstance(raw_plan_data, dict):
        pending_config = raw_plan_data.get("pending_config", {})
        # Only treat as existing plan if it has actual plan data (days array)
        if raw_plan_data.get("days") and len(raw_plan_data.get("days", [])) > 0:
            existing_plan = raw_plan_data
    
    learning_level = state.get("learning_level") or pending_config.get("learning_level", "intermediate")
    professor_level = state.get("professor_level") or pending_config.get("professor_level", "intermediate")
    target_days = state.get("target_days") or pending_config.get("target_days", 30)
    daily_minutes = state.get("daily_minutes") or pending_config.get("daily_minutes", 30)
    quiz_frequency = state.get("quiz_frequency") or pending_config.get("quiz_frequency", "after_each_chapter")
    
    logger.info(
        "planning_node_config",
        target_days=target_days,
        daily_minutes=daily_minutes,
        learning_level=learning_level,
    )
    
    planner = PlannerAgent(api_key=api_key)
    
    # PlannerAgent handles plan creation and iteration
    result = await planner.process({
        "book_id": book_id,
        "user_id": user_id,
        "book_title": book_title,
        "total_chapters": total_chapters,
        "chapter_titles": chapter_titles,
        "user_message": user_message,
        "existing_plan": existing_plan,
        "iteration_count": plan_iteration_count,
        "learning_level": learning_level,
        "professor_level": professor_level,
        "target_days": target_days,
        "preferred_study_time_minutes": daily_minutes,
        "quiz_frequency": quiz_frequency,
    })
    
    learning_plan = result.plan_data
    summary = result.summary
    
    # Check if agent decided the plan is accepted
    plan_accepted = result.plan_accepted
    
    # Check for freemium warning (plan days were capped)
    freemium_warning = pending_config.get("freemium_warning")
    
    if freemium_warning:
        summary = f"⚠️ {freemium_warning}\n\n{summary}"
    
    if plan_iteration_count > 0 and not plan_accepted:
        summary = f"I've adjusted the plan based on your feedback:\n\n{summary}"
    
    logger.info(
        "plan_generated",
        book_id=book_id,
        iteration=plan_iteration_count,
        total_days=learning_plan.get("total_days"),
        plan_accepted=plan_accepted,
    )
    
    response_data = {
        "plan_data": learning_plan,
        "professor_response": summary,
        "response_type": "plan",
        "phase": "planning",  # Stay in planning until accepted
        "active_agent": "planner",
        "agent_name": "Planner",
        "plan_iteration_count": plan_iteration_count + 1,
        "professor_level": professor_level,
        "learning_level": learning_level,
        "plan_accepted": plan_accepted,
    }
    
    # If plan accepted, transition to teaching
    if plan_accepted:
        response_data["phase"] = "teaching"
    
    return response_data


async def teaching_node(state: ProfessorState) -> Dict[str, Any]:
    """
    TeacherAgent: Handles ALL teaching interactions.
    
    The agent understands:
    - Questions about content
    - Requests to continue/proceed
    - Requests for examples
    - Requests to move to next day
    - Requests for quizzes
    - Requests for breaks
    
    The agent decides the next phase based on its understanding.
    NO external intent classification needed.
    
    SCOPE ENFORCEMENT: Before allowing day/quiz transitions, verifies
    that the day's scope is complete.
    """
    from app.agents.teacher import teach_with_context, get_chapter_for_day, get_all_chapters_for_day
    from app.services.scope_service import (
        extract_scope_from_plan,
        update_scope_coverage,
        verify_scope_completion,
        get_scope_status_for_response,
        ScopeStatus,
    )
    import time
    
    start_time = time.time()
    api_key = state.get("api_key")
    user_message = state.get("user_message", "")
    current_day = state.get("current_day", 1)
    plan_data = state.get("plan_data", {})
    
    # Get ALL chapters for the current day (a day can span multiple chapters)
    day_chapters = get_all_chapters_for_day(plan_data, current_day)
    plan_chapter, plan_chapter_title = get_chapter_for_day(plan_data, current_day)
    if plan_chapter > 0:
        actual_chapter = plan_chapter
        actual_chapter_title = plan_chapter_title
    else:
        actual_chapter = state.get("current_chapter", 1)
        actual_chapter_title = state.get("chapter_title", f"Chapter {actual_chapter}")
    
    # Build full context for the teacher
    teacher_state = dict(state)
    teacher_state["current_chapter"] = actual_chapter
    teacher_state["chapter_title"] = actual_chapter_title
    
    # Tell the teacher about ALL chapters assigned to this day
    if len(day_chapters) > 1:
        all_ch_desc = ", ".join([f"Ch {cn}: {ct}" for cn, ct in day_chapters if cn > 0])
        teacher_state["day_chapters_description"] = all_ch_desc
        teacher_state["day_chapter_numbers"] = [cn for cn, _ in day_chapters if cn > 0]
    
    # Add summaries if available
    if state.get("previous_day_summary"):
        teacher_state["previous_day_summary"] = state["previous_day_summary"]
    if state.get("cumulative_summary"):
        teacher_state["cumulative_summary"] = state["cumulative_summary"]
    if state.get("conversation_history"):
        teacher_state["conversation_history"] = state["conversation_history"]
    
    # Inject hint about uncovered topics so teacher prioritizes them
    scope_for_hint = extract_scope_from_plan(plan_data, current_day)
    existing_topics = teacher_state.get("topics_covered_this_chapter", [])
    scope_for_hint = update_scope_coverage(scope_for_hint, existing_topics)
    uncovered = [t for t in scope_for_hint.remaining_items if t.status != ScopeStatus.COMPLETE]
    if uncovered:
        uncovered_names = ', '.join(t.topic_name for t in uncovered)
        teacher_state["system_hint"] = (
            f"PRIORITY: {len(uncovered)} topics still uncovered today: {uncovered_names}. "
            f"Call fetch_next_topic NOW for the first uncovered topic. "
            f"Do NOT re-explain already covered topics. Move forward."
        )
    elif scope_for_hint.total_items > 0:
        teacher_state["system_hint"] = (
            f"ALL {scope_for_hint.total_items} topics are covered (100%). "
            f"You MUST offer a quiz NOW. Do not continue teaching."
        )
    
    # TeacherAgent processes and decides everything
    result = await teach_with_context(
        user_message=user_message,
        state=teacher_state,
        api_key=api_key,
    )
    
    elapsed_seconds = time.time() - start_time
    study_minutes = max(2, int(elapsed_seconds / 60) + 2)
    
    # Track topics covered
    new_topics = list(state.get("topics_covered_this_chapter", []))
    for topic in result.topics_mentioned:
        if topic not in new_topics:
            new_topics.append(topic)
    
    total_study_time = state.get("total_study_time_minutes", 0) + study_minutes
    
    # SCOPE VERIFICATION: Check scope completion before transitions
    scope = extract_scope_from_plan(plan_data, current_day)
    scope = update_scope_coverage(scope, new_topics)
    scope_verification = verify_scope_completion(scope, allow_partial=True, minimum_completion=0.95)
    scope_status = get_scope_status_for_response(scope)
    
    # SYSTEM OVERRIDE: Force quiz when scope is sufficiently complete but
    # the agent chose to keep teaching.  The LLM sometimes ignores the
    # "offer_quiz" instruction; this hard gate guarantees forward progress.
    # We use `can_proceed` (≥95%) rather than `is_complete` (strict 100%)
    # because fuzzy topic matching may leave minor gaps that shouldn't
    # block quiz transitions.  As a secondary safety net, if we've been
    # teaching for many messages (≥12) and scope is ≥80%, also force quiz
    # to prevent infinite teaching loops.
    effective_next_phase = result.next_phase
    msg_count = state.get("session_message_count", 0)
    scope_pct = scope_verification.completion_percentage

    has_real_scope = scope.total_items > 0
    should_force_quiz = (
        effective_next_phase == "teaching"
        and has_real_scope
        and should_trigger_quiz(state)
        and (
            scope_verification.is_complete
            or scope_verification.can_proceed
            or (msg_count >= 10 and scope_pct >= 80)
            or msg_count >= 18  # absolute cap: prevent infinite teaching regardless of scope
        )
    )
    if should_force_quiz:
        effective_next_phase = "quiz"
        logger.info(
            "scope_override_to_quiz",
            day=current_day,
            completion=scope_pct,
            message_count=msg_count,
            agent_decision=result.next_phase,
        )

    # Build response using agent's decision (or system override)
    response_data = {
        "professor_response": result.response,
        "response_type": "teaching",
        "phase": effective_next_phase,
        "active_agent": "teacher",
        "agent_name": "Professor",
        "topics_covered_this_chapter": new_topics,
        "session_message_count": state.get("session_message_count", 0) + 1,
        "total_study_time_minutes": total_study_time,
        "current_chapter": actual_chapter,
        "chapter_title": actual_chapter_title,
        "scope_status": scope_status,
    }
    
    # Handle day transition if agent decided
    if effective_next_phase == "day_transition" or result.day_completed:
        if not scope_verification.can_proceed:
            response_data["phase"] = "teaching"
            response_data["professor_response"] = (
                result.response + "\n\n" + scope_verification.warning_message
            )
            logger.info(
                "day_transition_blocked_by_scope",
                day=current_day,
                completion=scope_verification.completion_percentage,
                remaining=scope_verification.remaining_topics,
            )
        else:
            if scope_verification.warning_message and not scope_verification.is_complete:
                response_data["professor_response"] = (
                    result.response + "\n\n" + scope_verification.warning_message
                )
            adv = _advance_day(
                plan_data, current_day, actual_chapter,
                state.get("completed_days", []),
                state.get("completed_chapters", []),
            )
            response_data.update(adv)
        
        logger.info(
            "day_transition_by_agent",
            from_day=current_day,
            to_day=response_data.get("current_day", current_day),
            scope_complete=scope_verification.is_complete,
            scope_completion=scope_verification.completion_percentage,
        )
    
    # Handle quiz if agent or system override decided
    if effective_next_phase == "quiz":
        if not scope_verification.can_proceed:
            response_data["phase"] = "teaching"
            response_data["professor_response"] = (
                result.response + "\n\n" + scope_verification.warning_message
            )
            logger.info(
                "quiz_blocked_by_scope",
                day=current_day,
                completion=scope_verification.completion_percentage,
            )
        elif should_trigger_quiz(state):
            response_data["phase"] = "quiz"
            response_data["active_agent"] = "quiz"
    
    # Handle break if agent decided
    if effective_next_phase == "break":
        response_data["phase"] = "break"
    
    logger.info(
        "teaching_node_complete",
        agent_decision=result.next_phase,
        effective_phase=effective_next_phase,
        rag_used=result.rag_was_used,
        topics_count=len(result.topics_mentioned),
        scope_completion=scope_verification.completion_percentage,
    )
    
    return response_data


async def quiz_node(state: ProfessorState) -> Dict[str, Any]:
    """
    QuizAgent: Handles ALL quiz interactions.
    
    The agent understands:
    - Quiz answers (A, B, C, D or free text)
    - Requests for hints
    - Requests to skip
    - Requests to retry
    - Requests to move on
    
    The agent decides the next phase based on its understanding.
    NO external intent classification needed.
    """
    from app.agents.quiz import QuizAgent
    from app.agents.teacher import get_chapter_for_day
    
    api_key = state.get("api_key")
    quiz_questions = state.get("quiz_questions", [])
    quiz_index = state.get("quiz_current_index", 0)
    quiz_scores = state.get("quiz_scores", [])
    user_message = state.get("user_message", "")
    awaiting_decision = state.get("awaiting_quiz_decision", False)
    current_day = state.get("current_day", 1)
    plan_data = state.get("plan_data", {})
    
    # Get correct chapter for current day
    plan_chapter, plan_chapter_title = get_chapter_for_day(plan_data, current_day)
    current_chapter = plan_chapter if plan_chapter > 0 else state.get("current_chapter", 1)
    
    quiz_agent = QuizAgent(api_key=api_key)
    
    # If awaiting decision after quiz completion
    if awaiting_decision:
        # QuizAgent understands retry/skip intent
        decision = await quiz_agent.understand_post_quiz_decision(user_message)
        
        if decision.get("wants_retry", False):
            quiz_result = await quiz_agent.start_quiz(state)
            return {
                "professor_response": quiz_result.first_question_display,
                "response_type": "quiz_question",
                "phase": "quiz",
                "active_agent": "quiz",
                "agent_name": "Quiz Master",
                "quiz_questions": quiz_result.questions,
                "quiz_current_index": 0,
                "quiz_scores": [],
                "quiz_passed": None,
                "awaiting_quiz_decision": False,
                "current_chapter": current_chapter,  # Always include for tracking
            }
        else:
            adv = _advance_day(
                plan_data, current_day, current_chapter,
                state.get("completed_days", []),
                state.get("completed_chapters", []),
            )
            result_data = {
                "professor_response": "No problem! Let's move on to the next day. You can always come back to review.",
                "response_type": "day_transition",
                "active_agent": "teacher",
                "agent_name": "Professor",
                "awaiting_quiz_decision": False,
                "quiz_questions": [],
                "quiz_scores": [],
                "quiz_current_index": 0,
                "quiz_passed": False,
            }
            result_data.update(adv)
            return result_data
    
    # Start new quiz if no questions yet
    if not quiz_questions:
        quiz_result = await quiz_agent.start_quiz(state)
        return {
            "professor_response": quiz_result.first_question_display,
            "response_type": "quiz_question",
            "phase": "quiz",
            "active_agent": "quiz",
            "agent_name": "Quiz Master",
            "quiz_questions": quiz_result.questions,
            "quiz_current_index": 0,
            "quiz_scores": [],
            "quiz_passed": None,
            "current_chapter": current_chapter,  # Always include for tracking
        }
    
    # Evaluate answer - QuizAgent handles everything
    evaluation = await quiz_agent.evaluate_answer(user_message, state)
    new_scores = list(quiz_scores) + [evaluation.score]
    new_index = quiz_index + 1
    
    if evaluation.is_quiz_complete:
        completion = quiz_agent.format_completion_message(
            evaluation.final_score,
            evaluation.passed,
        )
        
        response_data = {
            "professor_response": f"{evaluation.feedback}\n\n{completion.message}",
            "response_type": "quiz_result",
            "agent_name": "Quiz Master",
            "quiz_scores": new_scores,
            "quiz_current_index": new_index,
            "quiz_passed": evaluation.passed,
            "current_chapter": current_chapter,  # Always include for tracking
        }
        
        if evaluation.passed:
            response_data["active_agent"] = "none"
            response_data["awaiting_quiz_decision"] = False
            response_data["quiz_questions"] = []
            
            adv = _advance_day(
                plan_data, current_day, current_chapter,
                state.get("completed_days", []),
                state.get("completed_chapters", []),
            )
            response_data.update(adv)
            # If not completed, go through chapter transition
            if response_data.get("phase") != "completed":
                response_data["phase"] = "chapter_transition"
        else:
            response_data["phase"] = "quiz_feedback"
            response_data["active_agent"] = "quiz"
            response_data["awaiting_quiz_decision"] = True
        
        return response_data
    else:
        return {
            "professor_response": f"{evaluation.feedback}\n\n{evaluation.next_question_display}",
            "response_type": "quiz_question",
            "phase": "quiz",
            "active_agent": "quiz",
            "agent_name": "Quiz Master",
            "quiz_scores": new_scores,
            "quiz_current_index": new_index,
            "current_chapter": current_chapter,  # Always include for tracking
        }


async def chapter_transition_node(state: ProfessorState) -> Dict[str, Any]:
    """
    ChapterTransitionNode: Handles transitions between chapters.
    
    Provides summary of completed chapter and introduces next chapter.
    """
    from app.services.chapter_transition import (
        generate_chapter_summary,
        prepare_new_chapter_context,
        format_chapter_transition_message,
    )
    
    api_key = state.get("api_key")
    current_chapter = state.get("current_chapter", 1)
    book_id = state.get("book_id", "")
    user_id = state.get("user_id", "")
    topics_covered = state.get("topics_covered_this_chapter", [])
    
    try:
        # Generate summary for completed chapter
        summary_result = await generate_chapter_summary(
            book_id=book_id,
            chapter_number=current_chapter,
            user_id=user_id,
            topics_covered=topics_covered,
            api_key=api_key,
        )
        
        # Prepare context for new chapter
        new_chapter = current_chapter + 1
        new_context = await prepare_new_chapter_context(
            book_id=book_id,
            new_chapter_number=new_chapter,
            user_id=user_id,
            api_key=api_key,
        )
        
        # Format transition message
        message = format_chapter_transition_message(
            previous_chapter=current_chapter,
            previous_summary=summary_result.get("summary_text"),
            new_chapter=new_chapter,
            new_chapter_title=new_context.get("new_chapter_title", f"Chapter {new_chapter}"),
            new_chapter_overview=new_context.get("new_chapter_overview"),
        )
        
        return {
            "professor_response": message,
            "response_type": "chapter_transition",
            "phase": "awaiting_chapter_start",
            "active_agent": "none",
            "agent_name": "Professor",
            "current_chapter": new_chapter,
            "chapter_title": new_context.get("new_chapter_title", f"Chapter {new_chapter}"),
            "topics_covered_this_chapter": [],
        }
    except Exception as e:
        logger.error("chapter_transition_error", error=str(e))
        return {
            "professor_response": f"Great work on Chapter {current_chapter}! Ready for Chapter {current_chapter + 1}?",
            "response_type": "chapter_transition",
            "phase": "awaiting_chapter_start",
            "active_agent": "none",
            "agent_name": "Professor",
            "current_chapter": current_chapter + 1,
        }


async def start_new_chapter_node(state: ProfessorState) -> Dict[str, Any]:
    """
    StartNewChapterNode: Begins teaching a new chapter.
    
    IMPORTANT: This node must fetch actual content from the textbook
    and start teaching immediately - not just say "let's dive in".
    """
    from app.agents.teacher import teach_with_context
    
    current_chapter = state.get("current_chapter", 1)
    chapter_title = state.get("chapter_title", f"Chapter {current_chapter}")
    
    # Build a teaching state and immediately start teaching
    # This ensures the first response has actual content
    teacher_state = dict(state)
    teacher_state["user_message"] = f"Let's start learning Chapter {current_chapter}: {chapter_title}"
    
    # Call the teacher agent to get actual content
    result = await teach_with_context(
        user_message=teacher_state["user_message"],
        state=teacher_state,
        api_key=state.get("api_key"),
    )
    
    # Prepend a chapter start header to the teaching response
    chapter_intro = f"**Now, let's dive into Chapter {current_chapter}: {chapter_title}**\n\nI'm excited to explore this with you!\n\n---\n\n"
    
    return {
        "professor_response": chapter_intro + result.response,
        "response_type": "chapter_start",
        "phase": "teaching",
        "active_agent": "teacher",
        "agent_name": "Professor",
        "topics_covered_this_chapter": result.topics_mentioned,
    }


# ============================================================================
# SCOPE HELPERS - Extract scope from plan_data at runtime
# ============================================================================

def get_day_scope_from_plan(plan_data: Dict[str, Any], current_day: int) -> Dict[str, Any]:
    """Extract scope for a specific day from the learning plan."""
    if not plan_data:
        return {}
    
    days = plan_data.get("days", [])
    for day in days:
        if day.get("day") == current_day:
            return {
                "day": current_day,
                "day_title": day.get("day_title", f"Day {current_day}"),
                "is_rest": day.get("rest", False),
                "items": day.get("items", []),
            }
    
    return {}


def _is_rest_day(plan_data: Dict[str, Any], day_number: int) -> bool:
    """Return True if ``day_number`` is a rest/review day (no teaching items)."""
    for day in plan_data.get("days", []):
        if day.get("day") == day_number:
            return bool(day.get("rest", False)) or not day.get("items")
    return False


def _advance_day(
    plan_data: Dict[str, Any],
    current_day: int,
    current_chapter: int,
    completed_days: list,
    completed_chapters: list,
) -> Dict[str, Any]:
    """Compute the state updates when the current day is finished.

    Handles:
    * marking the current day as completed
    * skipping rest/review days
    * detecting course completion (``next_day > total_days``)
    * tracking chapter changes

    Returns a dict of state keys to merge into the node's ``response_data``.
    """
    from app.agents.teacher import get_chapter_for_day

    updates: Dict[str, Any] = {}
    new_completed_days = list(completed_days)
    new_completed_chapters = list(completed_chapters)

    if current_day not in new_completed_days:
        new_completed_days.append(current_day)
    updates["completed_days"] = new_completed_days
    updates["topics_covered_this_chapter"] = []

    next_day = current_day + 1
    total_days = plan_data.get("total_days", 0)

    # Skip consecutive rest days
    while next_day <= total_days and _is_rest_day(plan_data, next_day):
        if next_day not in new_completed_days:
            new_completed_days.append(next_day)
        next_day += 1

    if next_day > total_days:
        # Course finished
        updates["current_day"] = next_day
        updates["phase"] = "completed"
        # Mark the final chapter as completed
        if current_chapter not in new_completed_chapters:
            new_completed_chapters.append(current_chapter)
            updates["completed_chapters"] = new_completed_chapters
        return updates

    updates["current_day"] = next_day

    next_chapter, next_chapter_title = get_chapter_for_day(plan_data, next_day)
    if next_chapter > 0:
        updates["current_chapter"] = next_chapter
        updates["chapter_title"] = next_chapter_title

        if next_chapter != current_chapter and current_chapter not in new_completed_chapters:
            new_completed_chapters.append(current_chapter)
            updates["completed_chapters"] = new_completed_chapters

    updates.setdefault("phase", "teaching")
    return updates


# ============================================================================
# MAIN ENTRY POINT - Simple dispatch to agents
# ============================================================================

async def process_message(
    user_id: str,
    session_id: str,
    book_id: str,
    message: str,
    current_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Process a message using agent-driven orchestration.
    
    This is the main entry point. It simply:
    1. Determines current phase
    2. Dispatches to the appropriate agent
    3. Returns the agent's response
    
    NO intent classification - agents handle everything.
    """
    state: ProfessorState = {
        "user_id": user_id,
        "session_id": session_id,
        "book_id": book_id,
        "user_message": message,
        **current_state,
    }
    
    phase = current_state.get("phase", "greeting")
    logger.info("processing_message", phase=phase, user_id=user_id)
    
    # Track conversation history
    conversation_history = list(state.get("conversation_history", []))
    conversation_history.append({
        "role": "user",
        "content": message,
        "timestamp": datetime.utcnow().isoformat(),
    })
    state["conversation_history"] = conversation_history
    
    try:
        # Simple dispatch to the appropriate agent based on phase
        # Each agent handles its own decision-making
        
        if phase == "greeting":
            # First message - go to config gathering
            result = await config_gathering_node(state)
        
        elif phase == "config_gathering":
            # ConfigGatheringAgent handles conversational config collection
            result = await config_gathering_node(state)
        
        elif phase == "planning":
            # PlannerAgent handles plan creation/modification.
            # Plan acceptance is handled by the dedicated plan review page
            # (POST /api/planning/review) — NOT in the chat flow.
            # The frontend redirects to /learn/[id]/plan when it sees
            # phase == "planning", so the user reviews visually there.
            result = await planning_node(state)
        
        elif phase == "teaching":
            # Auto-advance past rest days before dispatching to teacher
            plan_data = current_state.get("plan_data", {})
            cur_day = current_state.get("current_day", 1)
            if plan_data and _is_rest_day(plan_data, cur_day):
                adv = _advance_day(
                    plan_data, cur_day,
                    current_state.get("current_chapter", 1),
                    current_state.get("completed_days", []),
                    current_state.get("completed_chapters", []),
                )
                state.update(adv)
                if adv.get("phase") == "completed":
                    result = {
                        "professor_response": (
                            "🎓 Congratulations! You've completed the entire course! "
                            "Would you like to review any chapter or discuss what you've learned?"
                        ),
                        "response_type": "completion",
                        "phase": "completed",
                        "active_agent": "none",
                        "agent_name": "Professor",
                        **adv,
                    }
                else:
                    result = await teaching_node(state)
            else:
                result = await teaching_node(state)
        
        elif phase in ["quiz", "quiz_feedback"]:
            # QuizAgent handles ALL quiz interactions
            result = await quiz_node(state)
        
        elif phase == "chapter_transition":
            result = await chapter_transition_node(state)
        
        elif phase == "awaiting_chapter_start":
            result = await start_new_chapter_node(state)
        
        elif phase == "break":
            result = {
                "professor_response": (
                    "Take your time! When you're ready to continue, just let me know "
                    "and we'll pick up where we left off. 📚"
                ),
                "response_type": "break",
                "phase": "teaching",
                "active_agent": "none",
                "agent_name": "Professor",
            }
        
        elif phase == "completed":
            result = {
                "professor_response": (
                    "🎓 You've completed the course! "
                    "Would you like to review any chapter or discuss what you've learned?"
                ),
                "response_type": "completion",
                "phase": "completed",
                "active_agent": "none",
                "agent_name": "Professor",
            }
        
        else:
            # Default: TeacherAgent handles it
            result = await teaching_node(state)
        
        # Add response to conversation history
        conversation_history.append({
            "role": "assistant",
            "content": result.get("professor_response", ""),
            "timestamp": datetime.utcnow().isoformat(),
        })
        result["conversation_history"] = conversation_history
        
        return {
            "response": result.get("professor_response", ""),
            "response_type": result.get("response_type", "teaching"),
            "phase": result.get("phase", phase),
            "state": {**state, **result},
            "agent_name": result.get("agent_name", "Professor"),
        }
        
    except Exception as e:
        logger.exception("message_processing_failed", error=str(e), phase=phase)
        
        return {
            "response": "I hit a small snag there. Could you try saying that differently?",
            "response_type": "error",
            "phase": phase,
            "state": state,
            "error": str(e),
        }
