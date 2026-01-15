"""
TeacherAgent - The main agent that drives the teaching conversation.

This is the CORE agent of the system. It:
1. Uses the retrieval tool to get context
2. Teaches content from the chapter
3. Handles doubts/questions inline (no separate phase)
4. Includes motivation when needed (not a separate agent)
5. Asks attention questions naturally
6. Detects when chapter content is covered
7. Signals when ready for quiz

Key Design:
- Agent-driven, not intent-driven
- Orchestrator prompt makes the agent intelligent
- No explicit intent classification needed
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.agents.base import BaseAgent
from app.config import settings
from app.logs.logger import get_logger
from app.tools.retrieval import retrieve_context

logger = get_logger(__name__)


@dataclass
class TeacherResponse:
    """Response from TeacherAgent."""
    response: str                    # The teaching response
    chapter_content_covered: bool    # True if chapter content is sufficiently covered
    ready_for_quiz: bool             # True if agent signaled ready for quiz
    topics_mentioned: List[str]      # Topics covered in this response
    asked_attention_question: bool   # True if response includes attention question
    motivation_included: bool        # True if motivation message was prepended


class TeacherAgent(BaseAgent):
    """
    TeacherAgent - Drives the entire teaching conversation.
    
    This agent handles:
    - Teaching chapter content
    - Answering questions/doubts (inline, no separate phase)
    - Motivation (when motivation_score is low)
    - Attention questions (based on message count, not random)
    - Chapter completion detection
    - Quiz readiness signaling
    
    The orchestrator prompt makes the agent smart enough to handle
    all these scenarios without explicit intent classification.
    """
    
    # System prompt defines the professor's personality and capabilities
    SYSTEM_PROMPT = """You are Professor, an expert educator who DRIVES the learning experience.

**YOUR ROLE: YOU LEAD, STUDENT FOLLOWS**
- YOU decide what to teach next
- YOU move through the chapter content systematically  
- YOU check understanding with questions
- YOU decide when to move to the next topic
- YOU decide when the chapter is complete and it's quiz time

**Teaching Flow (YOU CONTROL THIS):**
1. Introduce a concept from the chapter content
2. Explain it clearly with examples
3. Ask the student a quick comprehension question
4. Based on their response, either clarify OR move to the next concept
5. When all key concepts are covered, announce quiz time

**When Student Responds:**
- If they answer correctly → Praise briefly, then teach the NEXT concept
- If they answer incorrectly → Clarify, then ask again or move on
- If they ask a question → Answer it, then continue YOUR teaching plan
- If they say "continue/yes/ok" → Teach the next concept

**IMPORTANT:**
- Don't wait for the student to ask what's next - YOU tell them
- Keep momentum - each response should teach something new OR check understanding
- After 3-4 concepts, you should be ready for quiz
- Responses: 200-400 words, focused and educational

SIGNALS (include at END of response):
- [CHAPTER_COVERED] - When you've taught all key concepts
- [READY_FOR_QUIZ] - When announcing it's quiz time (after chapter covered)
- [ATTENTION_CHECK] - After asking a comprehension question"""

    # Main orchestrator prompt - this is what makes the agent intelligent
    ORCHESTRATOR_PROMPT = """**TEACHING SESSION - YOU ARE DRIVING**

**Book:** {book_title}
**Chapter {chapter_number}:** {chapter_title}
**Student Level:** {learning_level}
**Teaching Style:** {professor_style}

---

{motivation_section}

---

**CHAPTER CONTENT TO TEACH (from the book):**
{retrieved_context}

---

**TOPICS YOU'VE ALREADY COVERED:**
{topics_covered}

**TOPICS REMAINING:** Look at the chapter content above and identify what you haven't taught yet.

---

**STUDENT'S LAST MESSAGE:**
{user_message}

---

**YOUR TASK - DRIVE THE LESSON:**

1. **If student answered a question:** Acknowledge briefly (correct/incorrect), then IMMEDIATELY teach the NEXT concept
2. **If student said "yes/ok/continue/got it":** Teach the NEXT concept from the chapter
3. **If student asked a question:** Answer it concisely, then continue teaching
4. **If you've covered all major concepts:** Announce it's quiz time!

**TEACHING STRUCTURE FOR THIS RESPONSE:**
- Start with: Brief transition from their message (1 sentence)
- Then: Teach ONE new concept from the chapter content (use the book content above)
- End with: A quick question to check understanding OR announce quiz time

{attention_instruction}

{completion_instruction}

**REMEMBER: You are the teacher. You drive. Don't ask "what would you like to learn?" - YOU decide what's next.**"""

    MOTIVATION_SECTION_TEMPLATE = """**MOTIVATION NOTE:**
The student's motivation score is low ({motivation_score:.0%}). 
Reason: {motivation_reason}

Start your response with a brief, genuine encouragement (1-2 sentences) before teaching.
Match the {professor_style} style:
- strict: Brief acknowledgment, focus on goals
- balanced: Empathetic but practical
- encouraging: Warm and supportive"""

    ATTENTION_INSTRUCTION = """
**ATTENTION CHECK:**
It's been a while since you checked understanding. Include a quick comprehension 
question at the end of your response. Something like:
"Quick check - [question about what you just explained]?"

Add [ATTENTION_CHECK] at the very end of your response."""

    COMPLETION_INSTRUCTION = """
**CHAPTER NEARLY COMPLETE:**
You've covered most of the chapter content. Time to wrap up!

1. Briefly summarize the key concepts (2-3 sentences)
2. Say: "Great progress! Now let's test your understanding with a quick quiz."
3. Add [CHAPTER_COVERED] and [READY_FOR_QUIZ] at the end

DO NOT ask if they want a quiz - YOU decide it's quiz time. Just announce it."""

    QUIZ_REQUEST_INSTRUCTION = """
**QUIZ TIME:**
Either the student asked for a quiz OR you've covered enough content.

1. Brief summary of what was covered (2-3 sentences)
2. Say: "Let's start the quiz!"
3. Add [READY_FOR_QUIZ] at the end

Move directly to quiz - no more teaching needed."""

    async def process(self, state: Dict[str, Any]) -> TeacherResponse:
        """
        Process a teaching interaction.
        
        This is the main entry point. It:
        1. Retrieves context using the retrieval tool
        2. Builds the orchestrator prompt
        3. Generates the response
        4. Parses signals from the response
        
        Args:
            state: Current ProfessorState
            
        Returns:
            TeacherResponse with response and state updates
        """
        # Extract state values
        user_message = state.get("user_message", "")
        book_id = state.get("book_id", "")
        book_title = state.get("book_title", "Learning Material")
        current_chapter = state.get("current_chapter", 1)
        chapter_title = state.get("chapter_title", f"Chapter {current_chapter}")
        learning_level = state.get("learning_level", "intermediate")
        professor_style = state.get("professor_style", "balanced")
        topics_covered = state.get("topics_covered_this_chapter", [])
        motivation_score = state.get("motivation_score", 1.0)
        session_message_count = state.get("session_message_count", 0)
        last_attention_check = state.get("last_attention_check_at", 0)
        api_key = state.get("api_key")
        user_id = state.get("user_id", "")
        
        # Step 1: Retrieve context using the retrieval tool
        retrieval_result = await retrieve_context(
            query=user_message or f"teach chapter {current_chapter}",
            book_id=book_id,
            current_chapter=current_chapter,
            user_id=user_id,
            api_key=api_key,
        )
        
        # Step 2: Build motivation section if needed
        motivation_section = ""
        motivation_included = False
        if motivation_score < 0.5:
            motivation_reason = self._determine_motivation_reason(state)
            motivation_section = self.MOTIVATION_SECTION_TEMPLATE.format(
                motivation_score=motivation_score,
                motivation_reason=motivation_reason,
                professor_style=professor_style,
            )
            motivation_included = True
        
        # Step 3: Determine if attention check should be included
        attention_instruction = ""
        messages_since_check = session_message_count - last_attention_check
        should_check_attention = (
            messages_since_check >= settings.attention_question_min_interval
        )
        if should_check_attention:
            attention_instruction = self.ATTENTION_INSTRUCTION
        
        # Step 4: Check if user is explicitly asking for quiz
        quiz_request_instruction = ""
        user_lower = user_message.lower()
        quiz_keywords = ["quiz", "test me", "ready for quiz", "take the quiz", "start quiz", "do the quiz"]
        if any(kw in user_lower for kw in quiz_keywords):
            quiz_request_instruction = self.QUIZ_REQUEST_INSTRUCTION
        
        # Step 5: Determine if chapter might be complete
        completion_instruction = ""
        topic_coverage = self._estimate_topic_coverage(
            topics_covered, 
            retrieval_result.chunks,
            session_message_count,
        )
        if topic_coverage >= 0.6 and not quiz_request_instruction:  # 60% coverage = near completion
            completion_instruction = self.COMPLETION_INSTRUCTION
        
        # Step 6: Build the orchestrator prompt
        # If quiz requested, use that instruction instead of completion
        final_instruction = quiz_request_instruction or completion_instruction
        
        prompt = self.ORCHESTRATOR_PROMPT.format(
            book_title=book_title,
            chapter_number=current_chapter,
            chapter_title=chapter_title,
            learning_level=learning_level,
            professor_style=professor_style,
            motivation_section=motivation_section or "Student motivation is good.",
            retrieved_context=retrieval_result.formatted_context,
            topics_covered=", ".join(topics_covered) if topics_covered else "None yet - starting fresh",
            user_message=user_message,
            attention_instruction=attention_instruction,
            completion_instruction=final_instruction,
        )
        
        # Step 7: Generate response
        try:
            response = await self.generate_with_retry(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=settings.max_response_tokens,
                temperature=settings.default_temperature,
                fallback_response=self._get_fallback_response(state),
            )
        except Exception as e:
            logger.exception("teaching_generation_failed", error=str(e))
            response = self._get_fallback_response(state)
        
        # Step 8: Parse signals from response
        chapter_covered, ready_for_quiz, asked_attention = self._parse_signals(response)
        
        # Step 9: Clean response (remove signals for display)
        clean_response = self._clean_response(response)
        
        # Step 10: Extract topics mentioned
        topics_mentioned = self._extract_topics(response, state)
        
        logger.info(
            "teacher_response_generated",
            user_id=user_id,
            chapter=current_chapter,
            chapter_covered=chapter_covered,
            ready_for_quiz=ready_for_quiz,
            asked_attention=asked_attention,
            motivation_included=motivation_included,
            topics_count=len(topics_mentioned),
        )
        
        return TeacherResponse(
            response=clean_response,
            chapter_content_covered=chapter_covered,
            ready_for_quiz=ready_for_quiz,
            topics_mentioned=topics_mentioned,
            asked_attention_question=asked_attention,
            motivation_included=motivation_included,
        )
    
    def _determine_motivation_reason(self, state: Dict[str, Any]) -> str:
        """Determine why motivation might be low."""
        missed_sessions = state.get("missed_sessions", 0)
        last_quiz_score = state.get("quiz_score", 1.0)
        attention_score = state.get("attention_score", 1.0)
        
        if missed_sessions >= 2:
            return "returning after a break"
        elif last_quiz_score and last_quiz_score < 0.5:
            return "challenging quiz results"
        elif attention_score < 0.5:
            return "difficulty staying focused"
        else:
            return "general motivation dip"
    
    def _estimate_topic_coverage(
        self, 
        topics_covered: List[str], 
        chunks: List[Dict[str, Any]],
        message_count: int = 0,
    ) -> float:
        """
        Estimate how much of the chapter has been covered.
        
        Uses combination of:
        - Topics covered vs chunks
        - Message count (after ~4-5 teaching exchanges, chapter should be done)
        """
        if not chunks:
            # No chunks = use message count
            return min(1.0, message_count / 5)
        
        chunk_count = len(chunks)
        topic_count = len(topics_covered)
        
        # Topic-based coverage
        topic_coverage = min(1.0, topic_count / max(chunk_count, 1))
        
        # Message-based coverage (after 4-5 exchanges, should be near complete)
        message_coverage = min(1.0, message_count / 5)
        
        # Use the higher of the two (be aggressive about completing)
        return max(topic_coverage, message_coverage)
    
    def _parse_signals(self, response: str) -> Tuple[bool, bool, bool]:
        """
        Parse signals from the response.
        
        Returns:
            Tuple of (chapter_covered, ready_for_quiz, asked_attention)
        """
        chapter_covered = "[CHAPTER_COVERED]" in response
        ready_for_quiz = "[READY_FOR_QUIZ]" in response
        asked_attention = "[ATTENTION_CHECK]" in response
        
        return chapter_covered, ready_for_quiz, asked_attention
    
    def _clean_response(self, response: str) -> str:
        """Remove signal markers from response for display."""
        signals = ["[CHAPTER_COVERED]", "[READY_FOR_QUIZ]", "[ATTENTION_CHECK]"]
        clean = response
        for signal in signals:
            clean = clean.replace(signal, "").strip()
        return clean
    
    def _extract_topics(self, response: str, state: Dict[str, Any]) -> List[str]:
        """
        Extract topics mentioned in the response.
        
        Looks for:
        1. Bold headers (** text **)
        2. Section titles from chunks
        3. Key ML terms
        """
        topics = []
        
        # Extract bold headers from response (these are usually topic names)
        import re
        bold_pattern = r'\*\*([^*]+)\*\*'
        bold_matches = re.findall(bold_pattern, response)
        for match in bold_matches:
            # Clean up the match
            topic = match.strip().rstrip(':')
            if len(topic) > 3 and len(topic) < 100 and topic not in topics:
                topics.append(topic)
        
        # Key ML terms to track
        ml_terms = [
            "machine learning", "supervised learning", "unsupervised learning",
            "reinforcement learning", "classification", "regression",
            "neural network", "deep learning", "training", "model",
            "data preprocessing", "feature engineering", "evaluation",
            "overfitting", "underfitting", "cross-validation"
        ]
        
        response_lower = response.lower()
        for term in ml_terms:
            if term in response_lower and term not in [t.lower() for t in topics]:
                topics.append(term.title())
        
        return topics[:8]  # Limit to 8 topics
    
    def _get_fallback_response(self, state: Dict[str, Any]) -> str:
        """Get a fallback response when generation fails."""
        chapter = state.get("current_chapter", 1)
        chapter_title = state.get("chapter_title", f"Chapter {chapter}")
        
        return (
            f"Let's continue with {chapter_title}. "
            f"I want to make sure you understand the key concepts here. "
            f"What would you like to explore? I can explain the main ideas, "
            f"go deeper into a specific topic, or answer any questions you have."
        )


# Convenience function for direct usage
async def teach(
    user_message: str,
    state: Dict[str, Any],
    api_key: Optional[str] = None,
) -> TeacherResponse:
    """
    Convenience function to get a teaching response.
    
    Args:
        user_message: The student's message
        state: Current state dict
        api_key: OpenAI API key
        
    Returns:
        TeacherResponse
    """
    state["user_message"] = user_message
    if api_key:
        state["api_key"] = api_key
    
    agent = TeacherAgent(api_key=api_key)
    return await agent.process(state)
