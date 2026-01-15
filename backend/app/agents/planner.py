"""Planner Agent - Creates and updates personalized learning plans."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent
from app.config import settings
from app.logs.logger import get_logger
from app.utils.state_helpers import (
    safe_get, safe_get_int, safe_get_float, safe_get_list, safe_get_dict
)

logger = get_logger(__name__)


class PlannerAgent(BaseAgent):
    """
    Creates and updates personalized learning plans.
    
    Responsibilities:
    - Analyze book structure and chapter dependencies
    - Create timeline based on user's study schedule
    - Adapt plan when user misses sessions or excels
    - Estimate completion dates
    """
    
    SYSTEM_PROMPT = """You are a Learning Plan Specialist. Create a day-by-day plan that strictly fits the target days and study time. Always return valid JSON only."""

    PLAN_PROMPT = """Create a learning plan for the following:

BOOK/GOAL INFORMATION:
- Title: {title}
- Total Chapters: {total_chapters}
- Chapter Details:
{chapter_details}

USER INFORMATION:
- Available study time per day: {study_time_minutes} minutes
- Learning level: {professor_level}
- Target total days: {target_days}
- Previous performance: {performance_summary}
- Additional instructions: {additional_instructions}

Create a day-by-day plan that uses exactly {target_days} days.
Include topics for each day and place quizzes per the schedule implied by the chapters.
Include review or rest days if needed, but still fill all days.

Return JSON in this format:
{{
    "total_days": <number>,
    "overview": "<summary>",
    "days": [
        {{
            "day": <number>,
            "rest": <true|false>,
            "items": [
                {{
                    "chapter_number": <number>,
                    "chapter_title": "<string>",
                    "topics": ["<topic1>", "<topic2>"],
                    "estimated_minutes": <number>,
                    "quiz_after": <true|false>
                }}
            ]
        }}
    ],
    "milestones": [
        {{
            "name": "<string>",
            "day": <number>,
            "type": "checkpoint|quiz|completion"
        }}
    ]
}}"""

    ADAPT_PROMPT = """Adapt the existing learning plan based on user performance:

CURRENT PLAN:
{current_plan}

USER PERFORMANCE:
- Completed chapters: {completed_chapters}
- Average quiz score: {avg_quiz_score}
- Total study time: {total_study_time} minutes
- Missed sessions: {missed_sessions}
- Days since start: {days_elapsed}
- Original estimated days: {original_estimated_days}

REASON FOR ADAPTATION: {adaptation_reason}

Return updated JSON plan with adjusted:
1. Remaining chapter estimates
2. New completion date
3. Any necessary review sessions
4. Updated milestones

Use the same JSON format as the original plan."""

    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create or update learning plan based on state.
        
        Args:
            state: Current UserState
            
        Returns:
            Updated state with learning_plan
        """
        # Check if we need to create or adapt plan
        existing_plan = safe_get_dict(state, "learning_plan", {})
        
        if not existing_plan:
            # Create new plan
            plan = await self._create_plan(state)
        else:
            # Check if adaptation is needed
            adaptation_reason = self._check_adaptation_needed(state)
            if adaptation_reason:
                plan = await self._adapt_plan(state, adaptation_reason)
            else:
                plan = existing_plan
        
        return {
            "learning_plan": plan,
            "estimated_completion_date": plan.get("estimated_completion_date"),
            "agent_name": "PlannerAgent",
        }
    
    async def _create_plan(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new learning plan."""
        # Get chapter details
        chapter_details = await self._format_chapter_details(state)
        
        study_time = safe_get_int(state, "preferred_study_time_minutes", 30)
        target_days = safe_get_int(state, "target_days", 0)
        if target_days <= 0:
            target_days = safe_get_int(state, "total_days", 30)
        
        # Format performance summary
        performance = self._format_performance_summary(state)
        
        # Safe get all state values
        book_title = safe_get(state, "book_title", "Learning Material")
        total_chapters = safe_get_int(state, "total_chapters", 10)
        professor_level = safe_get(state, "professor_level", "intermediate")
        
        additional_instructions = safe_get(state, "additional_instructions", "")
        prompt = self.PLAN_PROMPT.format(
            title=book_title,
            total_chapters=total_chapters,
            chapter_details=chapter_details,
            study_time_minutes=study_time,
            professor_level=professor_level,
            target_days=target_days,
            performance_summary=performance,
            additional_instructions=additional_instructions,
        )
        
        try:
            plan = await self.generate_json(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=1500,
                temperature=0.3,
            )
            
            plan["created_at"] = datetime.utcnow().isoformat()
            plan["version"] = 1
            
            logger.info(
                "learning_plan_created",
                user_id=safe_get(state, "user_id"),
                book_id=safe_get(state, "active_book_id"),
                estimated_days=plan.get("total_estimated_days"),
            )
            
            return plan
            
        except Exception as e:
            logger.exception("plan_creation_failed", error=str(e))
            raise
    
    async def _adapt_plan(
        self, 
        state: Dict[str, Any], 
        adaptation_reason: str
    ) -> Dict[str, Any]:
        """Adapt existing plan based on performance."""
        current_plan = safe_get_dict(state, "learning_plan", {})
        
        # Safe get all values
        completed_chapters = safe_get_list(state, "completed_chapters", [])
        quiz_score = safe_get_float(state, "quiz_score", 0.7)
        total_study_time = safe_get_int(state, "total_study_time_minutes", 0)
        missed_sessions = safe_get_int(state, "missed_sessions", 0)
        days_elapsed = self._calculate_days_elapsed(current_plan)
        original_days = current_plan.get("total_estimated_days", 30)
        
        prompt = self.ADAPT_PROMPT.format(
            current_plan=str(current_plan),
            completed_chapters=completed_chapters,
            avg_quiz_score=quiz_score,
            total_study_time=total_study_time,
            missed_sessions=missed_sessions,
            days_elapsed=days_elapsed,
            original_estimated_days=original_days,
            adaptation_reason=adaptation_reason,
        )
        
        try:
            adapted_plan = await self.generate_json(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=1500,
                temperature=0.3,
            )
            
            # Update metadata
            adapted_plan["adapted_at"] = datetime.utcnow().isoformat()
            adapted_plan["version"] = current_plan.get("version", 1) + 1
            adapted_plan["adaptation_reason"] = adaptation_reason
            
            logger.info(
                "learning_plan_adapted",
                user_id=safe_get(state, "user_id"),
                reason=adaptation_reason,
                new_estimated_days=adapted_plan.get("total_estimated_days"),
            )
            
            return adapted_plan
            
        except Exception as e:
            logger.exception("plan_adaptation_failed", error=str(e))
            return current_plan
    
    def _check_adaptation_needed(self, state: Dict[str, Any]) -> Optional[str]:
        """Check if plan needs adaptation and return reason."""
        plan = safe_get_dict(state, "learning_plan", {})
        triggers = plan.get("adaptation_triggers", {})
        
        # Check quiz performance
        quiz_score = safe_get_float(state, "quiz_score", 0.7)
        
        speed_up = triggers.get("speed_up_threshold", 0.9)
        slow_down = triggers.get("slow_down_threshold", 0.5)
        
        if quiz_score >= speed_up:
            return "User excelling - can speed up"
        
        if quiz_score <= slow_down:
            return "User struggling - need to slow down"
        
        # Check for missed sessions
        missed = safe_get_int(state, "missed_sessions", 0)
        if missed >= 3:
            return f"Multiple missed sessions ({missed}) - need reschedule"
        
        # Check if behind schedule
        if self._is_behind_schedule(state, plan):
            return "Behind schedule - need to adjust timeline"
        
        return None
    
    def _is_behind_schedule(
        self, 
        state: Dict[str, Any], 
        plan: Dict[str, Any]
    ) -> bool:
        """Check if user is significantly behind schedule."""
        created_at = plan.get("created_at")
        if not created_at:
            return False
        
        try:
            start_date = datetime.fromisoformat(created_at)
            days_elapsed = (datetime.utcnow() - start_date).days
            
            total_chapters = safe_get_int(state, "total_chapters", 10)
            completed_list = safe_get_list(state, "completed_chapters", [])
            completed = len(completed_list)
            
            estimated_days = plan.get("total_estimated_days", 30)
            
            # Prevent division by zero
            if estimated_days == 0 or total_chapters == 0:
                return False
                
            expected_progress = days_elapsed / estimated_days
            actual_progress = completed / total_chapters
            
            # Behind if actual progress is less than 70% of expected
            return actual_progress < (expected_progress * 0.7)
            
        except (ValueError, ZeroDivisionError, TypeError):
            return False
    
    def _calculate_days_elapsed(self, plan: Dict[str, Any]) -> int:
        """Calculate days since plan creation."""
        created_at = plan.get("created_at")
        if not created_at:
            return 0
        
        try:
            start_date = datetime.fromisoformat(created_at)
            return (datetime.utcnow() - start_date).days
        except ValueError:
            return 0
    
    async def _format_chapter_details(self, state: Dict[str, Any]) -> str:
        chapters = safe_get_list(state, "chapters", [])
        if not chapters:
            raise ValueError("Chapters are required to build a plan")
        return "\n".join([
            f"- Chapter {c.get('number', i+1)}: {c.get('title', 'Untitled')} "
            f"(~{c.get('estimated_minutes', 30)} min) "
            f"{c.get('summary', '')}".strip()
            for i, c in enumerate(chapters)
        ])
    
    def _format_performance_summary(self, state: Dict[str, Any]) -> str:
        """Format user's past performance for the prompt."""
        quiz_score = state.get("quiz_score")
        comprehension = state.get("comprehension_score")
        
        if quiz_score is None and comprehension is None:
            return "New learner - no previous performance data"
        
        parts = []
        if quiz_score is not None:
            parts.append(f"Average quiz score: {quiz_score*100:.0f}%")
        if comprehension is not None:
            parts.append(f"Comprehension score: {comprehension*100:.0f}%")
        
        return ", ".join(parts) if parts else "New learner"
