"""Teaching Agent - Delivers personalized instruction."""

import random
from typing import Any, Dict, List, Optional

from app.agents.base import BaseAgent
from app.config import settings
from app.logs.logger import get_logger
from app.utils.state_helpers import (
    safe_get, safe_get_int, safe_get_list, safe_get_bool, safe_get_dict
)

logger = get_logger(__name__)


class TeachingAgent(BaseAgent):
    """
    Delivers personalized instruction using retrieved context.
    
    Responsibilities:
    - Build comprehensive context from multiple sources
    - Generate clear, educational responses
    - Determine when to trigger attention questions
    - Track topic coverage and chapter progress
    """
    
    SYSTEM_PROMPT = """You are Professor, an expert educator with years of experience 
teaching complex subjects in an accessible way. Your teaching style is:

- Clear and structured, with logical progressions
- Rich in examples and analogies that connect to real life
- Patient and encouraging, adjusting to the student's level
- Focused on building deep understanding, not just memorization

You MUST:
1. Only teach content from the current chapter (no future chapters)
2. Reference previous chapters only when relevant and already completed
3. Keep responses focused (200-400 words)
4. Include examples when helpful
5. End with a thought-provoking point or natural transition

Match your style to the professor_level:
- beginner: More basic explanations, simpler analogies, more encouragement
- intermediate: Balanced depth, some technical terms with explanations
- advanced: More technical, deeper insights, expects prior knowledge"""

    TEACHING_PROMPT = """TEACHING CONTEXT

**Book/Course:** {book_title}
**Current Chapter:** {chapter_number} - {chapter_title}
**Current Section:** {current_section}
**Student Level:** {professor_level}
**Teaching Style:** {professor_style}

---

**WHAT THE STUDENT ALREADY KNOWS (Compressed Memory):**
{summarized_past_context}

---

**CURRENT CHAPTER CONTENT (Retrieved Chunks):**
{retrieved_chunks}

---

{cross_reference_section}

---

**TOPICS COVERED THIS SESSION:**
{topics_covered}

---

**STUDENT'S QUESTION:**
{user_query}

---

Respond as Professor. Teach this concept clearly, using the chapter content provided.
If the question relates to previous chapters, briefly reference what they learned before."""

    CROSS_REFERENCE_TEMPLATE = """**RELATED CONCEPTS FROM PREVIOUS CHAPTERS:**
{references}

Note: The student has already learned these concepts. Reference them naturally if relevant."""

    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate teaching response.
        
        Args:
            state: Current UserState with query and context
            
        Returns:
            Updated state with teaching response
        """
        # Build context sections using safe_get helpers
        cross_ref_section = self._build_cross_reference_section(state)
        
        retrieved_chunks_list = safe_get_list(state, "retrieved_chunks", [])
        retrieved_chunks = self._format_retrieved_chunks(retrieved_chunks_list)
        
        topics_list = safe_get_list(state, "topics_covered_this_session", [])
        topics_covered = ", ".join(topics_list) if topics_list else "None yet"
        
        # Safe get all state values
        book_title = safe_get(state, "book_title", "Learning Material")
        chapter_number = safe_get_int(state, "current_chapter", 1)
        chapter_title = safe_get(state, "current_chapter_title", "")
        current_section = safe_get(state, "current_section", "")
        professor_level = safe_get(state, "professor_level", "intermediate")
        professor_style = safe_get(state, "professor_style", "balanced")
        summarized_context = safe_get(state, "summarized_past_context", "This is the first chapter.")
        user_query = safe_get(state, "user_query", "")
        
        prompt = self.TEACHING_PROMPT.format(
            book_title=book_title,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            current_section=current_section,
            professor_level=professor_level,
            professor_style=professor_style,
            summarized_past_context=summarized_context,
            retrieved_chunks=retrieved_chunks or "No specific content retrieved.",
            cross_reference_section=cross_ref_section,
            topics_covered=topics_covered,
            user_query=user_query,
        )
        
        try:
            response = await self.generate_with_retry(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=settings.max_response_tokens,
                temperature=settings.default_temperature,
                fallback_response=self._get_fallback_response(state),
            )
            
            # Determine if we should ask an attention question
            should_ask_attention = self._should_ask_attention_question(state)
            
            # Check if chapter content is complete
            chapter_complete = self._check_chapter_completion(state, response)
            
            # Extract topic from response
            topic = self._extract_topic_from_response(response, state)
            
            logger.info(
                "teaching_response_generated",
                user_id=safe_get(state, "user_id"),
                chapter=chapter_number,
                should_ask_attention=should_ask_attention,
                chapter_complete=chapter_complete,
            )
            
            return {
                "agent_response": response,
                "trigger_attention_question": should_ask_attention,
                "chapter_complete": chapter_complete,
                "last_topic_discussed": topic,
                "agent_name": "TeachingAgent",
            }
            
        except Exception as e:
            logger.exception("teaching_generation_failed", error=str(e))
            return {
                "agent_response": self._get_fallback_response(state),
                "trigger_attention_question": False,
                "chapter_complete": False,
                "agent_name": "TeachingAgent",
            }
    
    def _build_cross_reference_section(self, state: Dict[str, Any]) -> str:
        """Build cross-reference section if applicable."""
        cross_refs = safe_get_dict(state, "cross_references", {})
        if not cross_refs or not cross_refs.get("references"):
            return ""
        
        references = cross_refs["references"]
        formatted_refs = []
        
        for ref in references[:3]:  # Limit to 3 references
            topic = ref.get('topic', 'Unknown topic')
            source_ch = ref.get('source_chapter', '?')
            summary = ref.get('summary', '')
            formatted_refs.append(
                f"- **{topic}** (Chapter {source_ch}): {summary}"
            )
        
        if not formatted_refs:
            return ""
        
        return self.CROSS_REFERENCE_TEMPLATE.format(
            references="\n".join(formatted_refs)
        )
    
    def _format_retrieved_chunks(self, chunks: List[Dict[str, Any]]) -> str:
        """Format retrieved chunks for the prompt."""
        if not chunks:
            return ""
        
        formatted = []
        for i, chunk in enumerate(chunks[:8], 1):
            section = chunk.get("section", "")
            section_header = f" ({section})" if section else ""
            content = chunk.get('content', '')
            formatted.append(
                f"[{i}]{section_header}:\n{content}\n"
            )
        
        return "\n---\n".join(formatted)
    
    def _should_ask_attention_question(self, state: Dict[str, Any]) -> bool:
        """
        Determine if we should ask an attention question.
        
        Uses configurable intervals and probability.
        """
        message_count = safe_get_int(state, "session_message_count", 0)
        
        # Don't ask too early in the session
        min_interval = settings.attention_question_min_interval
        max_interval = settings.attention_question_max_interval
        probability = settings.attention_question_probability
        
        if message_count < min_interval:
            return False
        
        # Check if we're in the attention window
        if message_count >= min_interval and message_count <= max_interval:
            # Random chance based on configured probability
            if random.random() < probability:
                return True
        
        # Force ask if we've gone too long without one
        if message_count >= max_interval:
            return True
        
        return False
    
    def _check_chapter_completion(
        self, 
        state: Dict[str, Any], 
        response: str
    ) -> bool:
        """
        Check if the chapter content has been fully covered.
        
        Uses retrieved chunks coverage and topic tracking - NO HARDCODING.
        """
        pending_topics = safe_get_list(state, "pending_topics", [])
        topics_covered = safe_get_list(state, "topics_covered_this_session", [])
        retrieved_chunks = safe_get_list(state, "retrieved_chunks", [])
        
        # If we have topics, use coverage ratio
        if pending_topics:
            covered_count = len(topics_covered)
            total_count = len(pending_topics)
            
            if total_count > 0:
                coverage_ratio = covered_count / total_count
                return coverage_ratio >= 0.8  # 80% coverage
        
        # If we have retrieved chunks, check if we've processed most
        if retrieved_chunks:
            chunk_count = len(retrieved_chunks)
            topics_count = len(topics_covered)
            
            # If topics covered >= chunks retrieved, likely covered chapter
            if topics_count >= chunk_count and topics_count > 0:
                return True
        
        # Check if the response indicates chapter completion
        # Look for completion signals in the teaching content
        completion_signals = [
            "we've covered all",
            "that concludes",
            "we've now completed",
            "those are the key concepts",
            "that's everything for this chapter",
            "we've explored all the main",
        ]
        
        response_lower = response.lower()
        for signal in completion_signals:
            if signal in response_lower:
                return True
        
        # Default: not complete - continue teaching
        return False
    
    def _extract_topic_from_response(
        self, 
        response: str, 
        state: Dict[str, Any]
    ) -> Optional[str]:
        """Extract the main topic discussed in the response."""
        # Use first sentence or section of response as topic indicator
        sentences = response.split(". ")
        if sentences:
            first_sentence = sentences[0]
            # Extract key words (simplified approach)
            words = first_sentence.split()
            if len(words) >= 3:
                return " ".join(words[:5])
        
        return safe_get(state, "current_section")
    
    def _get_fallback_response(self, state: Dict[str, Any]) -> str:
        """Get a fallback response when generation fails."""
        chapter = safe_get_int(state, "current_chapter", 1)
        query = safe_get(state, "user_query", "")
        query_preview = query[:50] if query else "this topic"
        
        return (
            f"That's a great question about Chapter {chapter}! Let me think about "
            f"the best way to explain this. {query_preview}... is an interesting topic. "
            f"The key thing to understand here is that this concept builds on what "
            f"we've covered before. Would you like me to start from the fundamentals, "
            f"or shall we dive into the specifics?"
        )
    
    async def generate_teaching_for_topic(
        self,
        topic: str,
        state: Dict[str, Any],
    ) -> str:
        """
        Generate proactive teaching for a specific topic.
        
        Used when Professor introduces a new topic.
        """
        chapter = safe_get_int(state, "current_chapter", 1)
        level = safe_get(state, "professor_level", "intermediate")
        
        prompt = f"""You are Professor. Introduce this topic to the student:

Topic: {topic}
Chapter: {chapter}
Student Level: {level}

Provide a clear, engaging introduction to this topic. Start with why it's important,
then explain the key concepts. Use examples to make it concrete. Keep it under 300 words."""

        try:
            return await self.generate_with_retry(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                max_tokens=500,
                temperature=0.7,
                fallback_response=f"Let's learn about {topic}. This is an important concept in our chapter.",
            )
        except Exception:
            return f"Let's explore {topic}. This is a key concept we'll be working with."
