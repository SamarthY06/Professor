"""
QuizAgent - Handles chapter quizzes and evaluations.

This agent:
1. Generates quiz questions for a chapter
2. Evaluates user answers
3. Handles quiz completion (pass/fail)
4. Provides retry/proceed options on failure

The quiz loop continues until all questions are answered.
"""

import random
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.agents.base import BaseAgent
from app.config import settings
from app.logs.logger import get_logger
from app.prompts.quiz import (
    QUIZ_SYSTEM_PROMPT,
    QUESTION_GENERATION_PROMPT,
    ANSWER_EVALUATION_PROMPT,
)

logger = get_logger(__name__)


@dataclass
class QuizQuestion:
    """A single quiz question."""
    question: str
    question_type: str  # mcq, true_false, short_answer
    difficulty: str     # easy, medium, hard
    options: Optional[List[str]]  # For MCQ
    correct_answer: str
    explanation: str
    topic: str


@dataclass 
class QuizStartResult:
    """Result when starting a new quiz."""
    questions: List[Dict[str, Any]]
    first_question_display: str
    total_questions: int


@dataclass
class AnswerEvaluation:
    """Result of evaluating an answer."""
    correct: bool
    score: float  # 0-1
    feedback: str
    is_quiz_complete: bool
    final_score: Optional[float]  # Set when quiz is complete
    passed: Optional[bool]        # Set when quiz is complete
    next_question_display: Optional[str]  # Next question if not complete


@dataclass
class QuizCompletionResult:
    """Result when quiz is complete."""
    passed: bool
    final_score: float
    message: str
    awaiting_decision: bool  # True if failed and waiting for retry/proceed


class QuizAgent(BaseAgent):
    """
    QuizAgent - Generates and evaluates chapter quizzes.
    
    Flow:
    1. start_quiz() - Generate all questions, return first
    2. evaluate_answer() - Evaluate answer, return next question or completion
    3. If failed: User chooses retry or proceed
    """

    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process quiz state - required by BaseAgent.
        
        This method is called by the graph but we use start_quiz() and evaluate_answer()
        directly for more control. This is a fallback.
        """
        quiz_questions = state.get("quiz_questions", [])
        
        if not quiz_questions:
            # Start new quiz
            result = await self.start_quiz(state)
            return {
                "quiz_questions": result.questions,
                "quiz_display": result.first_question_display,
            }
        else:
            # Evaluate answer
            user_message = state.get("user_message", "")
            result = await self.evaluate_answer(user_message, state)
            return {
                "evaluation": result,
            }

    QUESTION_TYPES = ["mcq", "true_false", "short_answer"]
    QUESTION_TYPE_WEIGHTS = [0.5, 0.25, 0.25]  # 50% MCQ, 25% T/F, 25% short

    async def start_quiz(
        self,
        state: Dict[str, Any],
    ) -> QuizStartResult:
        """
        Start a new quiz by generating all questions.
        
        IMPORTANT: Questions MUST be grounded in textbook content.
        We fetch fresh content from RAG to ensure questions are based
        on what's actually in the book, not LLM's general knowledge.
        
        Args:
            state: Current state with chapter info and config
            
        Returns:
            QuizStartResult with all questions and first question display
        """
        chapter_number = state.get("current_chapter", 1)
        chapter_title = state.get("chapter_title", f"Chapter {chapter_number}")
        topics_covered = state.get("topics_covered_this_chapter", [])
        comprehension_score = state.get("comprehension_score", 0.7)
        questions_per_quiz = state.get("questions_per_quiz", settings.quiz_questions_per_quiz)
        book_id = state.get("book_id", "")
        user_id = state.get("user_id", "")
        
        # CRITICAL: Fetch fresh content from RAG for quiz grounding
        # This ensures questions are based on textbook content, not LLM knowledge
        chapter_content = await self._fetch_chapter_content_for_quiz(
            book_id=book_id,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            topics_covered=topics_covered,
            user_id=user_id,
        )
        
        if not chapter_content or chapter_content == "No content available":
            logger.warning(
                "quiz_no_rag_content",
                chapter_number=chapter_number,
                book_id=book_id,
                message="No RAG content available for quiz - using fallback"
            )
            chapter_content = f"Chapter {chapter_number}: {chapter_title}. Topics covered: {', '.join(topics_covered) if topics_covered else 'General content'}"
        
        topics = ", ".join(topics_covered) if topics_covered else "General chapter content"
        
        # Generate all questions
        questions = []
        for i in range(questions_per_quiz):
            question_type = self._select_question_type()
            difficulty = self._select_difficulty(comprehension_score, i, questions_per_quiz)
            
            try:
                question_data = await self._generate_question(
                    chapter_number=chapter_number,
                    chapter_title=chapter_title,
                    chapter_content=chapter_content,
                    topics=topics,
                    question_type=question_type,
                    difficulty=difficulty,
                    question_number=i + 1,
                    total_questions=questions_per_quiz,
                )
                questions.append(question_data)
            except Exception as e:
                logger.warning(f"Question generation failed: {e}, using fallback")
                questions.append(self._get_fallback_question(
                    chapter_number, question_type, difficulty
                ))
        
        # Format first question for display
        first_question_display = self._format_question_display(
            questions[0], 1, len(questions)
        )
        
        logger.info(
            "quiz_started",
            chapter=chapter_number,
            questions_count=len(questions),
        )
        
        return QuizStartResult(
            questions=questions,
            first_question_display=f"📝 **Let's check your understanding!**\n\nNo pressure - this is just to see what's clicking and what might need another look.\n\n{first_question_display}",
            total_questions=len(questions),
        )
    
    async def evaluate_answer(
        self,
        user_answer: str,
        state: Dict[str, Any],
    ) -> AnswerEvaluation:
        """
        Evaluate the user's answer to the current question.
        
        Args:
            user_answer: The user's answer
            state: Current state with quiz questions and index
            
        Returns:
            AnswerEvaluation with feedback and next question or completion
        """
        quiz_questions = state.get("quiz_questions", [])
        quiz_index = state.get("quiz_current_index", 0)
        quiz_scores = state.get("quiz_scores", [])
        questions_per_quiz = len(quiz_questions)
        
        if not quiz_questions or quiz_index >= len(quiz_questions):
            # Quiz is already complete
            return self._create_completion_evaluation(quiz_scores)
        
        # Get current question
        current_question = quiz_questions[quiz_index]
        
        # Evaluate the answer
        evaluation = await self._evaluate_answer(
            question=current_question,
            user_answer=user_answer,
        )
        
        # Add score to list
        new_scores = list(quiz_scores) + [evaluation["score"]]
        
        # Check if quiz is complete
        next_index = quiz_index + 1
        is_complete = next_index >= questions_per_quiz
        
        # Build feedback message - warm and encouraging
        if evaluation["correct"]:
            feedback_msg = f"✅ **Nice work!** {evaluation['feedback']}"
        else:
            correct_answer = current_question.get("correct_answer", "N/A")
            feedback_msg = f"💭 **Almost there!** {evaluation['feedback']}\n\n*The answer was: {correct_answer}*"
        
        if is_complete:
            # Quiz complete - calculate final score
            final_score = sum(new_scores) / len(new_scores) if new_scores else 0
            passed = final_score >= settings.quiz_passing_score
            
            return AnswerEvaluation(
                correct=evaluation["correct"],
                score=evaluation["score"],
                feedback=feedback_msg,
                is_quiz_complete=True,
                final_score=final_score,
                passed=passed,
                next_question_display=None,
            )
        else:
            # More questions - format next question
            next_question = quiz_questions[next_index]
            next_display = self._format_question_display(
                next_question, next_index + 1, questions_per_quiz
            )
            
            return AnswerEvaluation(
                correct=evaluation["correct"],
                score=evaluation["score"],
                feedback=feedback_msg,
                is_quiz_complete=False,
                final_score=None,
                passed=None,
                next_question_display=next_display,
            )
    
    def format_completion_message(
        self,
        final_score: float,
        passed: bool,
    ) -> QuizCompletionResult:
        """
        Format the quiz completion message.
        
        Args:
            final_score: Final quiz score (0-1)
            passed: Whether the quiz was passed
            
        Returns:
            QuizCompletionResult with message and decision status
        """
        score_percent = final_score * 100
        
        if passed:
            if score_percent >= 90:
                message = (
                    f"🌟 **Fantastic work!**\n\n"
                    f"You scored **{score_percent:.0f}%** - that's excellent!\n\n"
                    f"You've really grasped the material. I'm impressed! "
                    f"Ready to explore what's next?"
                )
            elif score_percent >= 80:
                message = (
                    f"🎉 **Great job!**\n\n"
                    f"You scored **{score_percent:.0f}%** - solid understanding!\n\n"
                    f"You've got a good handle on this chapter. "
                    f"Let's keep the momentum going!"
                )
            else:
                message = (
                    f"✅ **You passed!**\n\n"
                    f"You scored **{score_percent:.0f}%** - nice work!\n\n"
                    f"You've shown you understand the key concepts. "
                    f"Ready to continue?"
                )
            return QuizCompletionResult(
                passed=True,
                final_score=final_score,
                message=message,
                awaiting_decision=False,
            )
        else:
            message = (
                f"📚 **Quiz finished!**\n\n"
                f"You scored **{score_percent:.0f}%** (we're looking for {settings.quiz_passing_score * 100:.0f}%)\n\n"
                f"No worries - this material takes time to sink in! You have two options:\n\n"
                f"🔄 **Try again** - I'll give you fresh questions to practice with\n"
                f"➡️ **Move forward** - Continue learning and come back to review later\n\n"
                f"What feels right to you? Just say 'try again' or 'move on'."
            )
            return QuizCompletionResult(
                passed=False,
                final_score=final_score,
                message=message,
                awaiting_decision=True,
            )
    
    async def _generate_question(
        self,
        chapter_number: int,
        chapter_title: str,
        chapter_content: str,
        topics: str,
        question_type: str,
        difficulty: str,
        question_number: int,
        total_questions: int,
    ) -> Dict[str, Any]:
        """Generate a single quiz question."""
        prompt = QUESTION_GENERATION_PROMPT.format(
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            chapter_content=chapter_content[:2000],  # Limit content length
            topics=topics,
            question_type=question_type,
            difficulty=difficulty,
            question_number=question_number,
            total_questions=total_questions,
        )
        
        question_data = await self.generate_json(
            prompt=prompt,
            system_prompt=QUIZ_SYSTEM_PROMPT,
            max_tokens=500,
            temperature=0.7,
        )
        
        return question_data
    
    async def _evaluate_answer(
        self,
        question: Dict[str, Any],
        user_answer: str,
    ) -> Dict[str, Any]:
        """Evaluate a user's answer using LLM."""
        prompt = ANSWER_EVALUATION_PROMPT.format(
            question=question.get("question", ""),
            correct_answer=question.get("correct_answer", ""),
            explanation=question.get("explanation", ""),
            user_answer=user_answer,
        )
        
        try:
            result = await self.generate_json(
                prompt=prompt,
                system_prompt="You are a fair quiz evaluator. Return valid JSON.",
                max_tokens=200,
                temperature=0.3,
            )
            return {
                "correct": result.get("correct", False),
                "score": result.get("score", 0.0),
                "feedback": result.get("feedback", ""),
            }
        except Exception as e:
            logger.warning(f"Answer evaluation failed: {e}")
            # Simple fallback evaluation
            return self._simple_evaluate(question, user_answer)
    
    def _simple_evaluate(
        self,
        question: Dict[str, Any],
        user_answer: str,
    ) -> Dict[str, Any]:
        """Simple fallback evaluation without LLM."""
        correct_answer = question.get("correct_answer", "").lower().strip()
        user_answer_clean = user_answer.lower().strip()
        
        q_type = question.get("type", "short_answer")
        
        if q_type == "mcq":
            # Check if first letter matches
            correct = user_answer_clean.startswith(correct_answer[0].lower())
        elif q_type == "true_false":
            # Check for true/false variations
            true_variants = ["true", "t", "yes", "y", "1"]
            false_variants = ["false", "f", "no", "n", "0"]
            
            user_is_true = any(v in user_answer_clean for v in true_variants)
            user_is_false = any(v in user_answer_clean for v in false_variants)
            correct_is_true = any(v in correct_answer for v in true_variants)
            
            correct = (user_is_true and correct_is_true) or (user_is_false and not correct_is_true)
        else:
            # Short answer - check for keyword overlap
            correct_words = set(correct_answer.split())
            user_words = set(user_answer_clean.split())
            overlap = len(correct_words & user_words)
            correct = overlap >= len(correct_words) * 0.5
        
        return {
            "correct": correct,
            "score": 1.0 if correct else 0.0,
            "feedback": "You've got it!" if correct else "That's not quite it, but you're thinking in the right direction.",
        }
    
    def _select_question_type(self) -> str:
        """Select question type with weighted probability."""
        return random.choices(
            self.QUESTION_TYPES,
            weights=self.QUESTION_TYPE_WEIGHTS,
            k=1
        )[0]
    
    def _select_difficulty(
        self,
        comprehension_score: float,
        question_index: int,
        total_questions: int,
    ) -> str:
        """
        Select difficulty based on comprehension score and question position.
        
        Earlier questions are easier, later questions are harder.
        Comprehension score also affects distribution.
        """
        # Base weights based on comprehension
        if comprehension_score >= 0.8:
            weights = [0.1, 0.3, 0.6]  # More hard
        elif comprehension_score >= 0.6:
            weights = [0.2, 0.5, 0.3]  # Balanced
        else:
            weights = [0.4, 0.4, 0.2]  # More easy
        
        # Adjust based on position (later questions slightly harder)
        position_factor = question_index / max(total_questions - 1, 1)
        weights[2] += position_factor * 0.2  # Increase hard probability
        weights[0] -= position_factor * 0.1  # Decrease easy probability
        
        # Normalize
        total = sum(weights)
        weights = [w / total for w in weights]
        
        return random.choices(["easy", "medium", "hard"], weights=weights, k=1)[0]
    
    def _format_chapter_content(self, retrieved_context: List[Dict[str, Any]]) -> str:
        """Format retrieved context for question generation."""
        if not retrieved_context:
            return "General chapter content"
        
        parts = []
        for chunk in retrieved_context[:5]:  # Limit to 5 chunks
            content = chunk.get("content", "")
            section = chunk.get("section_title", "")
            if section:
                parts.append(f"[{section}]\n{content}")
            else:
                parts.append(content)
        
        return "\n\n".join(parts)
    
    async def _fetch_chapter_content_for_quiz(
        self,
        book_id: str,
        chapter_number: int,
        chapter_title: str,
        topics_covered: List[str],
        user_id: str,
    ) -> str:
        """
        Fetch chapter content from RAG for quiz question generation.
        
        CRITICAL: This ensures quiz questions are grounded in the actual
        textbook content, not the LLM's general knowledge.
        
        Args:
            book_id: Book ID
            chapter_number: Chapter number
            chapter_title: Chapter title
            topics_covered: Topics that were covered (to focus questions)
            user_id: User ID for RAG auth
        
        Returns:
            Formatted chapter content string
        """
        from app.integrations.rag_client import get_rag_client
        from app.db.database import async_session_maker
        from app.models.book import Book, BookChapter
        from sqlalchemy import select
        from uuid import UUID
        
        if not book_id:
            return "No content available"
        
        document_id = None
        chapter_id = None
        
        try:
            async with async_session_maker() as db:
                book_result = await db.execute(select(Book).where(Book.id == UUID(book_id)))
                book = book_result.scalar_one_or_none()
                if book and book.book_metadata:
                    document_id = book.book_metadata.get("external_document_id") or book.book_metadata.get("rag_document_id")
                
                # Get chapter_id for filtering
                ch_result = await db.execute(
                    select(BookChapter)
                    .where(BookChapter.book_id == UUID(book_id))
                    .where(BookChapter.chapter_number == chapter_number)
                )
                chapter = ch_result.scalar_one_or_none()
                if chapter and chapter.key_concepts:
                    chapter_id = chapter.key_concepts.get("rag_chapter_id")
                if chapter and chapter.title:
                    chapter_title = chapter.title
        except Exception as e:
            logger.warning("quiz_db_error", error=str(e))
            return "No content available"
        
        if not document_id:
            return "No content available"
        
        # Build query focused on covered topics
        topics_str = ", ".join(topics_covered[:5]) if topics_covered else "main concepts"
        query = (
            f"STRICTLY from Chapter {chapter_number} titled '{chapter_title}': "
            f"Provide detailed content about: {topics_str}. "
            f"Include definitions, formulas, examples, and key concepts from this chapter ONLY."
        )
        
        try:
            client = get_rag_client()
            
            if chapter_id:
                logger.info(
                    "quiz_rag_fetch_with_chapter_filter",
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                )
                response = await client.search(
                    query=query,
                    document_id=document_id,
                    chapter_ids=[chapter_id],
                    limit=8,  # Get more content for quiz
                    user_id=user_id,
                )
            else:
                logger.warning(
                    "quiz_rag_fetch_without_chapter_filter",
                    chapter_number=chapter_number,
                    message="No chapter_id - quiz may use wrong chapter content"
                )
                response = await client.search(
                    query=query,
                    document_id=document_id,
                    limit=8,
                    user_id=user_id,
                )
            
            if not response.results:
                return "No content available"
            
            # Format content with chapter verification
            parts = []
            for r in response.results[:6]:
                section = r.section_title or "Content"
                parts.append(f"[Chapter {chapter_number} - {section}]\n{r.content}")
            
            content = "\n\n---\n\n".join(parts)
            
            logger.info(
                "quiz_content_fetched",
                chapter_number=chapter_number,
                content_length=len(content),
                chunks_used=len(parts),
            )
            
            return content
            
        except Exception as e:
            logger.exception("quiz_rag_fetch_error", error=str(e))
            return "No content available"
    
    def _format_question_display(
        self,
        question: Dict[str, Any],
        question_number: int,
        total_questions: int,
    ) -> str:
        """Format a question for display to the user."""
        q_type = question.get("type", "short_answer")
        q_text = question.get("question", "")
        difficulty = question.get("difficulty", "medium")
        
        header = f"**Question {question_number}/{total_questions}** ({difficulty.capitalize()})\n\n"
        output = header + q_text + "\n\n"
        
        if q_type == "mcq" and question.get("options"):
            options = question["options"]
            output += "\n".join(options) + "\n\n"
            output += "_Reply with the letter of your answer (A, B, C, or D)_"
        elif q_type == "true_false":
            output += "_Reply with True or False_"
        else:
            output += "_Please type your answer_"
        
        return output
    
    def _get_fallback_question(
        self,
        chapter_number: int,
        question_type: str,
        difficulty: str,
    ) -> Dict[str, Any]:
        """Get a fallback question when generation fails."""
        if question_type == "mcq":
            return {
                "question": f"Which concept is most central to Chapter {chapter_number}?",
                "type": "mcq",
                "difficulty": difficulty,
                "options": [
                    "A) The main theme discussed throughout",
                    "B) A minor detail mentioned briefly",
                    "C) Something from a different chapter",
                    "D) An unrelated concept",
                ],
                "correct_answer": "A",
                "explanation": "The main theme is the central focus of any chapter.",
                "topic": "Chapter comprehension",
            }
        elif question_type == "true_false":
            return {
                "question": f"Chapter {chapter_number} builds upon concepts from earlier chapters.",
                "type": "true_false",
                "difficulty": difficulty,
                "options": None,
                "correct_answer": "True",
                "explanation": "Learning is cumulative and chapters typically build on each other.",
                "topic": "Learning progression",
            }
        else:
            return {
                "question": f"In your own words, explain one key concept from Chapter {chapter_number}.",
                "type": "short_answer",
                "difficulty": difficulty,
                "options": None,
                "correct_answer": "A clear explanation of any main concept",
                "explanation": "Tests understanding through explanation.",
                "topic": "Chapter comprehension",
            }
    
    def _create_completion_evaluation(
        self,
        quiz_scores: List[float],
    ) -> AnswerEvaluation:
        """Create an evaluation result for an already-complete quiz."""
        final_score = sum(quiz_scores) / len(quiz_scores) if quiz_scores else 0
        passed = final_score >= settings.quiz_passing_score
        
        return AnswerEvaluation(
            correct=True,
            score=1.0,
            feedback="Quiz already complete.",
            is_quiz_complete=True,
            final_score=final_score,
            passed=passed,
            next_question_display=None,
        )
    
    async def understand_post_quiz_decision(self, user_message: str) -> Dict[str, Any]:
        """
        Use LLM to understand user's decision after quiz completion.
        
        The agent understands natural language like:
        - "I want to try again" → retry
        - "Let me retake it" → retry
        - "Move on" → skip
        - "Continue to next chapter" → skip
        - "I'll review later" → skip
        
        Returns:
            Dict with 'wants_retry' and 'wants_skip' booleans
        """
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are analyzing a student's response after completing a quiz.
Determine if they want to:
1. RETRY the quiz (try again, retake, redo, another attempt)
2. SKIP/MOVE ON (continue, next chapter, move on, skip, proceed)

Respond with ONLY one word: RETRY or SKIP"""),
            ("human", "{message}")
        ])
        
        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=self.api_key,
            )
            
            chain = prompt | llm
            result = await chain.ainvoke({"message": user_message})
            
            decision = result.content.strip().upper()
            
            return {
                "wants_retry": "RETRY" in decision,
                "wants_skip": "SKIP" in decision or "RETRY" not in decision,
            }
        except Exception as e:
            logger.error("quiz_decision_understanding_error", error=str(e))
            # Default to skip on error
            return {"wants_retry": False, "wants_skip": True}
