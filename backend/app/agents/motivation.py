"""Motivation Agent - Provides encouragement when motivation drops."""

from typing import Any, Dict, Optional

from app.agents.base import BaseAgent
from app.config import settings
from app.logs.logger import get_logger
from app.utils.state_helpers import (
    safe_get, safe_get_int, safe_get_float, safe_get_list
)

logger = get_logger(__name__)


class MotivationAgent(BaseAgent):
    """
    Provides personalized encouragement when motivation score is low.
    
    Responsibilities:
    - Generate encouraging messages
    - Highlight progress made
    - Adjust tone based on professor_style
    - Suggest breaks or schedule adjustments
    """
    
    SYSTEM_PROMPT = """You are a supportive learning coach. Your role is to:
1. Acknowledge the learner's effort and progress
2. Provide genuine, personalized encouragement
3. Offer practical suggestions to help them continue
4. Be warm but not patronizing

Match your tone to the professor_style:
- strict: Focus on goals and discipline, brief encouragement
- balanced: Mix empathy with practical advice
- encouraging: Very warm, lots of positive reinforcement"""

    MOTIVATION_PROMPT = """The student needs encouragement. Generate a supportive message.

STUDENT CONTEXT:
- Name: {user_name}
- Current motivation score: {motivation_score}% (low)
- Chapters completed: {completed_chapters}/{total_chapters}
- Study time so far: {study_time} minutes
- Missed sessions: {missed_sessions}
- Last quiz score: {last_quiz_score}
- Professor style preference: {professor_style}

RECENT PROGRESS:
{recent_progress}

REASON FOR LOW MOTIVATION:
{motivation_reason}

Generate an encouraging message that:
1. Acknowledges their feelings/situation
2. Highlights specific progress they've made
3. Provides 1-2 actionable suggestions
4. Ends with genuine encouragement

Keep the message warm and under 150 words. Match the {professor_style} tone."""

    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate motivational message.
        
        Args:
            state: Current UserState with low motivation_score
            
        Returns:
            Updated state with motivational response
        """
        motivation_score = safe_get_float(state, "motivation_score", 0.5)
        
        # Determine reason for low motivation
        reason = self._determine_motivation_reason(state)
        
        # Format recent progress
        recent_progress = self._format_recent_progress(state)
        
        user_name = safe_get(state, "user_name", "Learner")
        completed_chapters = safe_get_list(state, "completed_chapters", [])
        total_chapters = safe_get_int(state, "total_chapters", 10)
        study_time = safe_get_int(state, "total_study_time_minutes", 0)
        missed_sessions = safe_get_int(state, "missed_sessions", 0)
        quiz_score = state.get("quiz_score")
        professor_style = safe_get(state, "professor_style", "balanced")
        
        prompt = self.MOTIVATION_PROMPT.format(
            user_name=user_name,
            motivation_score=int(motivation_score * 100),
            completed_chapters=len(completed_chapters),
            total_chapters=total_chapters,
            study_time=study_time,
            missed_sessions=missed_sessions,
            last_quiz_score=self._format_quiz_score(quiz_score),
            professor_style=professor_style,
            recent_progress=recent_progress,
            motivation_reason=reason,
        )
        
        try:
            response = await self.generate_with_retry(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=300,
                temperature=0.8,  # Higher for more natural encouragement
                fallback_response=self._get_fallback_encouragement(state),
            )
            
            logger.info(
                "motivation_message_generated",
                user_id=safe_get(state, "user_id"),
                motivation_score=motivation_score,
                reason=reason,
            )
            
            # Boost motivation slightly after intervention
            new_motivation = min(1.0, motivation_score + 0.1)
            
            return {
                "agent_response": response,
                "motivation_score": new_motivation,
                "motivation_intervention": True,
                "agent_name": "MotivationAgent",
            }
            
        except Exception as e:
            logger.exception("motivation_generation_failed", error=str(e))
            return {
                "agent_response": self._get_fallback_encouragement(state),
                "agent_name": "MotivationAgent",
            }
    
    def _determine_motivation_reason(self, state: Dict[str, Any]) -> str:
        """Determine the primary reason for low motivation."""
        reasons = []
        
        missed = safe_get_int(state, "missed_sessions", 0)
        if missed >= 3:
            reasons.append(f"Multiple missed sessions ({missed})")
        
        quiz_score = state.get("quiz_score")
        if quiz_score is not None and float(quiz_score) < 0.5:
            reasons.append(f"Struggling with quiz (score: {int(float(quiz_score)*100)}%)")
        
        attention = safe_get_float(state, "attention_score", 1.0)
        if attention < 0.5:
            reasons.append("Difficulty with attention questions")
        
        comprehension = safe_get_float(state, "comprehension_score", 1.0)
        if comprehension < 0.5:
            reasons.append("Comprehension challenges")
        
        if not reasons:
            reasons.append("General motivation dip")
        
        return "; ".join(reasons)
    
    def _format_recent_progress(self, state: Dict[str, Any]) -> str:
        """Format recent progress for the prompt."""
        progress_points = []
        
        completed = safe_get_list(state, "completed_chapters", [])
        if len(completed) > 0:
            progress_points.append(f"Completed {len(completed)} chapter(s)")
        
        topics = safe_get_list(state, "topics_covered_this_session", [])
        if topics:
            progress_points.append(f"Topics covered today: {', '.join(topics[:3])}")
        
        study_time = safe_get_int(state, "total_study_time_minutes", 0)
        if study_time > 0:
            hours = study_time // 60
            mins = study_time % 60
            if hours > 0:
                progress_points.append(f"Total study time: {hours}h {mins}m")
            else:
                progress_points.append(f"Total study time: {mins} minutes")
        
        quiz_score = state.get("quiz_score")
        if quiz_score is not None and float(quiz_score) >= 0.7:
            progress_points.append(f"Recent quiz passed ({int(float(quiz_score)*100)}%)")
        
        if not progress_points:
            progress_points.append("Just getting started - that's progress too!")
        
        return "\n".join(f"- {p}" for p in progress_points)
    
    def _format_quiz_score(self, score: Optional[float]) -> str:
        """Format quiz score for display."""
        if score is None:
            return "No quiz taken yet"
        return f"{int(float(score) * 100)}%"
    
    def _get_fallback_encouragement(self, state: Dict[str, Any]) -> str:
        """Get fallback encouragement message."""
        professor_style = safe_get(state, "professor_style", "balanced")
        completed = safe_get_list(state, "completed_chapters", [])
        completed_count = len(completed)
        
        if professor_style == "strict":
            return (
                f"You've completed {completed_count} chapter(s) so far. "
                "Let's keep the momentum going. Take a short break if needed, "
                "then let's continue with focused effort."
            )
        elif professor_style == "encouraging":
            return (
                f"Hey! I noticed things might feel a bit tough right now, and that's completely okay! "
                f"You've already made it through {completed_count} chapter(s) - that's real progress! 🌟 "
                "Remember, learning isn't a race. Take a breath, maybe grab a snack, "
                "and come back when you're ready. I believe in you!"
            )
        else:  # balanced
            return (
                f"I see you've been working hard - {completed_count} chapter(s) completed! "
                "It's natural to feel challenged sometimes. Let's take a moment to acknowledge "
                "how far you've come. If you need a break, take one. When you're ready, "
                "we'll tackle this together. You've got this!"
            )
