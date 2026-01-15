"""
LangGraph workflow for Professor - Simplified Agent-Driven Architecture.

KEY DESIGN PRINCIPLES:
1. Agent-Driven, Not Intent-Driven
   - Agents drive the conversation through their orchestrator prompts
   - No explicit intent classification for most interactions
   
2. Only 3 Active Agents:
   - PlannerAgent: Plan generation and iteration
   - TeacherAgent: All teaching, doubts, motivation, attention questions
   - QuizAgent: Quiz generation and evaluation
   
3. Retrieval is a Tool, Not an Agent
   - TeacherAgent calls retrieve_context() tool
   
4. Simplified Flow:
   greeting → planning → teaching ←→ quiz → chapter_transition → (repeat or complete)

5. Background Processing:
   - Summarization happens async after chapter completion
   - Motivation messages triggered by Temporal for inactivity
"""

from typing import Dict, Any, Optional
from datetime import datetime

from app.langgraph.state import (
    ProfessorState, 
    Phase, 
    should_trigger_quiz,
    reset_chapter_state,
)
from app.logs.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# NODE FUNCTIONS
# ============================================================================

async def greeting_node(state: ProfessorState) -> Dict[str, Any]:
    """
    Display greeting and wait for user to accept.
    
    Simple template - the greeting was already generated during PDF processing.
    This node just handles the response when user is ready.
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


async def planning_node(state: ProfessorState) -> Dict[str, Any]:
    """
    Generate or iterate learning plan using PlannerAgent.
    
    PlannerAgent handles both initial generation and modifications.
    """
    from app.agents.planner import PlannerAgent
    from app.db.database import async_session_maker
    from sqlalchemy import select
    from app.models.book import Book, BookChapter
    from app.models.learning_config import LearningConfig
    from datetime import date
    from uuid import UUID
    
    api_key = state.get("api_key")
    book_id = state.get("book_id")
    user_message = state.get("user_message", "")
    existing_plan = state.get("plan_data")
    plan_iteration_count = state.get("plan_iteration_count", 0)
    
    # Gather book info from database
    chapter_list = []
    target_days = 30
    daily_minutes = state.get("daily_study_minutes", 60)
    learning_level = state.get("learning_level", "intermediate")
    book_title = state.get("book_title", "Your Book")
    total_chapters = state.get("total_chapters", 5)
    
    if book_id:
        async with async_session_maker() as db:
            # Get book
            book_result = await db.execute(
                select(Book).where(Book.id == UUID(book_id))
            )
            book = book_result.scalar_one_or_none()
            if book:
                book_title = book.title
                total_chapters = book.total_chapters or total_chapters
            
            # Get chapters
            chapters_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
                .order_by(BookChapter.chapter_number)
            )
            chapters = chapters_result.scalars().all()
            chapter_list = [
                {
                    "number": c.chapter_number,
                    "title": c.title or f"Chapter {c.chapter_number}",
                    "estimated_minutes": c.estimated_duration_minutes or 45,
                }
                for c in chapters
            ]
            
            # Get config
            config_result = await db.execute(
                select(LearningConfig).where(LearningConfig.book_id == UUID(book_id))
            )
            config = config_result.scalar_one_or_none()
            if config:
                daily_minutes = config.daily_study_minutes or daily_minutes
                learning_level = config.learning_level or learning_level
                if config.deadline:
                    target_days = max(1, (config.deadline - date.today()).days)
    
    if target_days <= 0:
        target_days = max(total_chapters, 7)
    
    # Build agent state
    agent_state = {
        "user_id": state.get("user_id"),
        "active_book_id": book_id,
        "book_title": book_title,
        "total_chapters": total_chapters,
        "professor_level": learning_level,
        "preferred_study_time_minutes": daily_minutes,
        "target_days": target_days,
        "chapters": chapter_list,
        "api_key": api_key,
        "learning_plan": existing_plan,
        "additional_instructions": user_message if plan_iteration_count > 0 else "",
    }
    
    # Generate/iterate plan
    planner = PlannerAgent(api_key=api_key)
    plan_result = await planner.process(agent_state)
    learning_plan = plan_result.get("learning_plan", {})
    
    # Format plan summary
    summary = _format_plan_summary(learning_plan, {
        "book_title": book_title,
        "daily_study_minutes": daily_minutes,
        "total_chapters": total_chapters,
    })
    
    # Add iteration context if this is a modification
    if plan_iteration_count > 0:
        summary = f"I've adjusted the plan based on your feedback:\n\n{summary}"
    
    logger.info(
        "plan_generated",
        book_id=book_id,
        iteration=plan_iteration_count,
        total_days=learning_plan.get("total_days"),
    )
    
    return {
        "plan_data": learning_plan,
        "professor_response": summary,
        "response_type": "plan",
        "phase": "planning",
        "active_agent": "planner",
        "agent_name": "Planner",
        "plan_iteration_count": plan_iteration_count + 1,
    }


async def teaching_node(state: ProfessorState) -> Dict[str, Any]:
    """
    TeacherAgent drives the teaching conversation.
    
    This is the main node where most interaction happens.
    TeacherAgent handles:
    - Teaching content
    - Answering questions/doubts
    - Motivation (when needed)
    - Attention questions
    - Chapter completion detection
    """
    from app.agents.teacher import TeacherAgent
    from app.services.progress import update_study_time, add_topic_covered
    import time
    
    start_time = time.time()
    api_key = state.get("api_key")
    
    # Create TeacherAgent and process
    teacher = TeacherAgent(api_key=api_key)
    result = await teacher.process(state)
    
    # Calculate time spent on this interaction (estimate ~2 min per exchange)
    elapsed_seconds = time.time() - start_time
    study_minutes = max(2, int(elapsed_seconds / 60) + 2)  # At least 2 min per interaction
    
    # Update progress
    # Note: These are utility functions, not agent calls
    new_topics = list(state.get("topics_covered_this_chapter", []))
    for topic in result.topics_mentioned:
        if topic not in new_topics:
            new_topics.append(topic)
    
    # Track cumulative study time
    total_study_time = state.get("total_study_time_minutes", 0) + study_minutes
    
    # Build response
    response_data = {
        "professor_response": result.response,
        "response_type": "teaching",
        "phase": "teaching",
        "active_agent": "teacher",
        "agent_name": "Professor",
        "topics_covered_this_chapter": new_topics,
        "session_message_count": state.get("session_message_count", 0) + 1,
        "total_study_time_minutes": total_study_time,
    }
    
    # Handle attention question tracking
    if result.asked_attention_question:
        response_data["last_attention_check_at"] = state.get("session_message_count", 0) + 1
    
    # Handle chapter completion
    if result.chapter_content_covered:
        response_data["chapter_content_covered"] = True
    
    # Handle quiz readiness
    if result.ready_for_quiz:
        # Check if quiz should trigger based on config
        if should_trigger_quiz(state):
            response_data["phase"] = "quiz"
            response_data["active_agent"] = "quiz"
        else:
            # No quiz configured, go to chapter transition
            response_data["phase"] = "chapter_transition"
    
    return response_data


async def quiz_node(state: ProfessorState) -> Dict[str, Any]:
    """
    QuizAgent handles the quiz flow.
    
    Flow:
    1. First entry: Generate questions, show first
    2. Subsequent: Evaluate answer, show next or complete
    3. On completion: Show result, handle retry/proceed
    """
    from app.agents.quiz import QuizAgent
    from app.services.progress import update_comprehension_score, update_motivation_score
    
    api_key = state.get("api_key")
    quiz_questions = state.get("quiz_questions", [])
    quiz_index = state.get("quiz_current_index", 0)
    quiz_scores = state.get("quiz_scores", [])
    user_message = state.get("user_message", "")
    awaiting_decision = state.get("awaiting_quiz_decision", False)
    
    quiz_agent = QuizAgent(api_key=api_key)
    
    # Handle retry/proceed decision after failure
    if awaiting_decision:
        user_lower = user_message.lower()
        if any(word in user_lower for word in ["retry", "again", "try"]) and "move" not in user_lower:
            # Retry - reset quiz and regenerate
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
            }
        else:
            # Move on - proceed to chapter transition
            # Clear quiz state completely
            return {
                "professor_response": "No problem! Let's move on to the next chapter. You can always come back to review.",
                "response_type": "transition",
                "phase": "chapter_transition",
                "active_agent": "none",
                "agent_name": "Professor",
                "awaiting_quiz_decision": False,
                "quiz_questions": [],  # Clear quiz questions
                "quiz_scores": [],
                "quiz_current_index": 0,
                "quiz_passed": False,
            }
    
    # First entry - generate quiz
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
        }
    
    # Evaluate answer
    evaluation = await quiz_agent.evaluate_answer(user_message, state)
    
    # Update scores
    new_scores = list(quiz_scores) + [evaluation.score]
    new_index = quiz_index + 1
    
    if evaluation.is_quiz_complete:
        # Quiz complete
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
        }
        
        if evaluation.passed:
            response_data["phase"] = "chapter_transition"
            response_data["active_agent"] = "none"
            response_data["awaiting_quiz_decision"] = False
            # Clear quiz state on pass
            response_data["quiz_questions"] = []
        else:
            response_data["phase"] = "quiz_feedback"
            response_data["active_agent"] = "quiz"
            response_data["awaiting_quiz_decision"] = True
        
        return response_data
    else:
        # More questions
        return {
            "professor_response": f"{evaluation.feedback}\n\n{evaluation.next_question_display}",
            "response_type": "quiz_question",
            "phase": "quiz",
            "active_agent": "quiz",
            "agent_name": "Quiz Master",
            "quiz_scores": new_scores,
            "quiz_current_index": new_index,
        }


async def chapter_transition_node(state: ProfessorState) -> Dict[str, Any]:
    """
    Handle chapter completion and transition to next chapter.
    
    This node:
    1. Marks chapter as complete
    2. Triggers background summarization
    3. Prepares for next chapter or course completion
    """
    from app.services.progress import (
        mark_chapter_complete,
        update_motivation_score,
        create_progress_snapshot,
    )
    from app.services.summarization import trigger_chapter_summarization
    from app.db.database import async_session_maker
    from sqlalchemy import select
    from app.models.book import BookChapter
    from uuid import UUID
    
    current_chapter = state.get("current_chapter", 1)
    total_chapters = state.get("total_chapters", 1)
    chapters_completed = list(state.get("chapters_completed", []))
    book_id = state.get("book_id")
    user_id = state.get("user_id")
    session_id = state.get("session_id")
    quiz_passed = state.get("quiz_passed")
    
    # Mark chapter complete
    if current_chapter not in chapters_completed:
        chapters_completed.append(current_chapter)
    
    # Trigger background summarization (fire-and-forget)
    try:
        await trigger_chapter_summarization(
            user_id=user_id,
            book_id=book_id,
            chapter_number=current_chapter,
            session_id=session_id,
        )
    except Exception as e:
        logger.warning(f"Summarization trigger failed: {e}")
    
    # Check if course is complete
    if current_chapter >= total_chapters:
        return {
            "professor_response": (
                f"🎓 **Congratulations!**\n\n"
                f"You've completed all {total_chapters} chapters! "
                f"This is a fantastic achievement. "
                f"Would you like to review any chapter or take a final assessment?"
            ),
            "response_type": "completion",
            "phase": "completed",
            "active_agent": "none",
            "agent_name": "Professor",
            "chapters_completed": chapters_completed,
        }
    
    # Get next chapter info
    next_chapter = current_chapter + 1
    next_chapter_title = f"Chapter {next_chapter}"
    
    if book_id:
        try:
            async with async_session_maker() as db:
                ch_result = await db.execute(
                    select(BookChapter.title)
                    .where(BookChapter.book_id == UUID(book_id))
                    .where(BookChapter.chapter_number == next_chapter)
                )
                ch_row = ch_result.first()
                if ch_row and ch_row[0]:
                    next_chapter_title = ch_row[0]
        except Exception as e:
            logger.warning(f"Failed to get next chapter title: {e}")
    
    # Reset chapter state
    chapter_reset = reset_chapter_state(state)
    
    # Build transition message
    if quiz_passed:
        transition_msg = (
            f"✨ **Great work on Chapter {current_chapter}!**\n\n"
            f"You've demonstrated solid understanding. "
            f"Ready for **{next_chapter_title}**?\n\n"
            f"Say 'yes' when you're ready to continue!"
        )
    else:
        transition_msg = (
            f"📚 **Moving on from Chapter {current_chapter}**\n\n"
            f"Let's continue with **{next_chapter_title}**. "
            f"You can always come back to review.\n\n"
            f"Say 'yes' when you're ready!"
        )
    
    return {
        **chapter_reset,
        "professor_response": transition_msg,
        "response_type": "transition",
        "phase": "teaching",  # Ready for next chapter
        "active_agent": "teacher",
        "agent_name": "Professor",
        "chapters_completed": chapters_completed,
        "current_chapter": next_chapter,
        "chapter_title": next_chapter_title,
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _format_plan_summary(plan: Dict[str, Any], context: Dict[str, Any]) -> str:
    """Format learning plan for display."""
    days = plan.get("days", [])
    total_days = plan.get("total_days", len(days))
    overview = plan.get("overview", "")
    milestones = plan.get("milestones", [])
    book_title = context.get("book_title", "Your Book")
    daily_minutes = context.get("daily_study_minutes", 60)
    total_chapters = context.get("total_chapters", len(days))
    
    parts = [f"📚 **Learning Plan for \"{book_title}\"**\n"]
    
    if overview:
        parts.append(f"{overview}\n")
    
    parts.append(f"**Duration:** {total_days} days")
    parts.append(f"**Study Time:** {daily_minutes} min/day")
    parts.append(f"**Chapters:** {total_chapters}\n")
    
    if days:
        parts.append("**Schedule Preview:**")
        for day in days[:7]:
            day_num = day.get("day", "?")
            items = day.get("items", [])
            if day.get("rest"):
                parts.append(f"• Day {day_num}: Review & rest")
                continue
            if not items:
                parts.append(f"• Day {day_num}: Catch up")
                continue
            
            chapter_info = []
            for item in items:
                ch_title = item.get("chapter_title", "Chapter")
                ch_num = item.get("chapter_number", "")
                if ch_num:
                    chapter_info.append(f"Ch.{ch_num}: {ch_title}")
                else:
                    chapter_info.append(ch_title)
            
            parts.append(f"• Day {day_num}: {', '.join(chapter_info)}")
        
        if len(days) > 7:
            parts.append(f"• ... and {len(days) - 7} more days")
    
    if milestones:
        parts.append("\n**Key Milestones:**")
        for milestone in milestones[:3]:
            name = milestone.get("name", "Milestone")
            day = milestone.get("day", "?")
            m_type = milestone.get("type", "checkpoint")
            emoji = {"checkpoint": "🎯", "quiz": "📝", "completion": "🎓"}.get(m_type, "✓")
            parts.append(f"• {emoji} Day {day}: {name}")
    
    parts.append("\n**Ready to begin?** Just say 'yes' or 'let's start'!")
    parts.append("Want changes? Tell me what you'd like to adjust.")
    
    return "\n".join(parts)


def _is_acceptance(message: str) -> bool:
    """Check if message indicates acceptance."""
    accept_words = [
        "yes", "yeah", "yep", "sure", "ok", "okay", "let's", "lets", 
        "start", "begin", "ready", "go", "continue", "sounds good",
        "looks good", "perfect", "great", "fine", "accepted"
    ]
    message_lower = message.lower().strip()
    return any(word in message_lower for word in accept_words)


def _is_modification_request(message: str) -> bool:
    """Check if message requests plan modification."""
    modify_words = [
        "change", "modify", "adjust", "different", "more time", "less time",
        "fewer days", "more days", "slower", "faster", "skip", "focus on",
        "can we", "could we", "what if", "instead"
    ]
    message_lower = message.lower().strip()
    return any(word in message_lower for word in modify_words)


# ============================================================================
# MAIN MESSAGE PROCESSOR
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
    
    This is the main entry point. It routes to the appropriate
    agent based on the current phase.
    
    Key Design:
    - Agents drive the conversation
    - Minimal intent classification (only for phase transitions)
    - State updates come from agent responses
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
    
    try:
        # ==================== GREETING PHASE ====================
        if phase == "greeting":
            if _is_acceptance(message):
                # User accepted, generate plan
                result = await planning_node(state)
            else:
                # User has question or needs more info
                result = await greeting_node(state)
        
        # ==================== PLANNING PHASE ====================
        elif phase == "planning":
            if _is_acceptance(message):
                # User accepted plan, start teaching
                state["plan_accepted"] = True
                state["current_chapter"] = 1
                result = await teaching_node(state)
                result["plan_accepted"] = True
                result["professor_response"] = (
                    "🎓 **Let's begin your learning journey!**\n\n---\n\n" 
                    + result.get("professor_response", "")
                )
            elif _is_modification_request(message):
                # User wants to modify plan
                result = await planning_node(state)
            else:
                # Unclear - show plan again or answer question
                result = await planning_node(state)
        
        # ==================== TEACHING PHASE ====================
        elif phase == "teaching":
            result = await teaching_node(state)
        
        # ==================== QUIZ PHASE ====================
        elif phase in ["quiz", "quiz_feedback"]:
            result = await quiz_node(state)
        
        # ==================== CHAPTER TRANSITION ====================
        elif phase == "chapter_transition":
            # Always proceed with transition - teacher drives
            result = await chapter_transition_node(state)
        
        # ==================== COMPLETED ====================
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
        
        # ==================== DEFAULT ====================
        else:
            result = await teaching_node(state)
            result["phase"] = "teaching"
        
        # Build final response
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
            "response": (
                f"I'm having trouble processing that. "
                f"Could you try rephrasing? We were working on {phase}."
            ),
            "response_type": "error",
            "phase": phase,
            "state": state,
            "error": str(e),
        }
