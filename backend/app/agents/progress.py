"""Progress Agent - Updates learning state after each interaction."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.config import settings
from app.logs.logger import get_logger
from app.utils.state_helpers import (
    safe_get, safe_get_int, safe_get_float, safe_get_list, safe_get_bool
)

logger = get_logger(__name__)


class ProgressAgent(BaseAgent):
    """
    Updates learning state after each interaction.
    
    Responsibilities:
    - Update current chapter/section progress
    - Track topics covered in session
    - Calculate engagement metrics
    - Determine if motivation intervention needed
    """
    
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update progress based on current interaction.
        
        Args:
            state: Current UserState
            
        Returns:
            Updated state with progress metrics
        """
        # Note: We create our own db session if needed for persistence
        
        # Update session metrics using safe_get
        session_message_count = safe_get_int(state, "session_message_count", 0) + 1
        
        # Track topics covered this session
        topics_covered = list(safe_get_list(state, "topics_covered_this_session", []))
        new_topic = self._extract_topic_from_interaction(state)
        if new_topic and new_topic not in topics_covered:
            topics_covered.append(new_topic)
        
        # Update study time (assuming ~2 minutes per interaction)
        total_study_time = safe_get_int(state, "total_study_time_minutes", 0) + 2
        
        # Calculate engagement metrics
        attention_score = self._calculate_attention_score(state)
        comprehension_score = self._calculate_comprehension_score(state)
        motivation_score = self._calculate_motivation_score(state)
        
        # Check for chapter completion
        chapter_complete = safe_get_bool(state, "chapter_complete", False)
        completed_chapters = list(safe_get_list(state, "completed_chapters", []))
        current_chapter = safe_get_int(state, "current_chapter", 1)
        
        if chapter_complete and current_chapter not in completed_chapters:
            completed_chapters.append(current_chapter)
            logger.info(
                "chapter_completed",
                user_id=safe_get(state, "user_id"),
                chapter=current_chapter,
            )
        
        # Note: Progress persistence is handled by the chat endpoint, not here
        # This avoids async db session context issues in LangGraph
        
        # Determine if motivation check is needed
        needs_motivation = motivation_score < 0.5
        
        return {
            "session_message_count": session_message_count,
            "topics_covered_this_session": topics_covered,
            "total_study_time_minutes": total_study_time,
            "attention_score": attention_score,
            "comprehension_score": comprehension_score,
            "motivation_score": motivation_score,
            "completed_chapters": completed_chapters,
            "motivation_check": needs_motivation,
            "last_interaction_at": datetime.utcnow().isoformat(),
            "agent_name": "ProgressAgent",
        }
    
    def _extract_topic_from_interaction(self, state: Dict[str, Any]) -> Optional[str]:
        """Extract the main topic from current interaction."""
        # Use the last topic discussed or extract from response
        agent_response = safe_get(state, "agent_response", "")
        
        # Simple extraction - get first sentence topic
        if "about" in agent_response.lower():
            # Try to extract topic after "about"
            idx = agent_response.lower().find("about")
            snippet = agent_response[idx:idx+100]
            words = snippet.split()
            if len(words) > 1:
                return " ".join(words[1:4])  # Get 3 words after "about"
        
        return safe_get(state, "last_topic_discussed")
    
    def _calculate_attention_score(self, state: Dict[str, Any]) -> float:
        """
        Calculate attention score based on attention question performance.
        
        Score range: 0.0 to 1.0
        """
        current_score = safe_get_float(state, "attention_score", 1.0)
        
        # Check recent attention question results
        attention_correct = state.get("attention_correct")
        
        if attention_correct is not None:
            if attention_correct:
                # Increase score slightly for correct answers
                current_score = min(1.0, current_score + 0.1)
            else:
                # Decrease score for incorrect answers
                current_score = max(0.0, current_score - 0.15)
        
        return current_score
    
    def _calculate_comprehension_score(self, state: Dict[str, Any]) -> float:
        """
        Calculate comprehension score based on quiz and attention performance.
        
        Score range: 0.0 to 1.0
        """
        current_score = safe_get_float(state, "comprehension_score", 1.0)
        quiz_score = state.get("quiz_score")
        attention_correct = state.get("attention_correct")
        
        # Weight quiz scores more heavily
        if quiz_score is not None:
            # Blend current score with quiz score
            current_score = (current_score * 0.3) + (float(quiz_score) * 0.7)
        
        # Attention questions have smaller impact
        if attention_correct is not None:
            adjustment = 0.05 if attention_correct else -0.05
            current_score = max(0.0, min(1.0, current_score + adjustment))
        
        return current_score
    
    def _calculate_motivation_score(self, state: Dict[str, Any]) -> float:
        """
        Calculate motivation score based on engagement patterns.
        
        Score range: 0.0 to 1.0
        """
        current_score = safe_get_float(state, "motivation_score", 1.0)
        
        # Factors that decrease motivation
        missed_sessions = safe_get_int(state, "missed_sessions", 0)
        if missed_sessions > 0:
            current_score -= missed_sessions * 0.1
        
        # Low quiz scores decrease motivation
        quiz_score = state.get("quiz_score")
        if quiz_score is not None and float(quiz_score) < 0.5:
            current_score -= 0.1
        
        # Factors that increase motivation
        # Recent activity is good
        session_count = safe_get_int(state, "session_message_count", 0)
        if session_count > 5:
            current_score += 0.05
        
        # Completing topics increases motivation
        topics_list = safe_get_list(state, "topics_covered_this_session", [])
        topics_covered = len(topics_list)
        if topics_covered > 3:
            current_score += 0.05
        
        # Chapter completion is a big boost
        if safe_get_bool(state, "chapter_complete", False):
            current_score += 0.2
        
        return max(0.0, min(1.0, current_score))
    
    async def _persist_progress(
        self,
        db: AsyncSession,
        user_id: str,
        book_id: Optional[str],
        updates: Dict[str, Any],
    ) -> None:
        """Persist progress updates to database."""
        if not user_id:
            return
        
        try:
            from app.models.learning import LearningState
            
            stmt = (
                update(LearningState)
                .where(LearningState.user_id == user_id)
                .where(LearningState.book_id == book_id)
                .values(**updates)
            )
            
            await db.execute(stmt)
            await db.commit()
            
            logger.debug(
                "progress_persisted",
                user_id=user_id,
                book_id=book_id,
            )
            
        except Exception as e:
            logger.exception("progress_persist_failed", error=str(e))
            await db.rollback()
