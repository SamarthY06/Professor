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
    
    SYSTEM_PROMPT = """You are a Quiz Generation Specialist. Create clear, fair questions that test understanding, not just memorization. Always respond with valid JSON."""

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

    QUESTION_GENERATION_PROMPT = """Generate a quiz question for Chapter {chapter_number}: {chapter_title}

**CHAPTER CONTENT:**
{chapter_content}

**TOPICS TO TEST:**
{topics}

**QUESTION SPECIFICATIONS:**
- Type: {question_type}
- Difficulty: {difficulty}
- Question {question_number} of {total_questions}

**REQUIREMENTS:**
1. Test understanding of concepts, not just recall
2. Be clear and unambiguous
3. For MCQ: provide 4 distinct options with one clearly correct answer
4. Include a brief explanation of why the correct answer is right

Return JSON:
{{
    "question": "<the question text>",
    "type": "{question_type}",
    "difficulty": "{difficulty}",
    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
    "correct_answer": "<correct answer or letter>",
    "explanation": "<why this is correct>",
    "topic": "<main topic tested>"
}}"""

    ANSWER_EVALUATION_PROMPT = """Evaluate this quiz answer.

**QUESTION:**
{question}

**CORRECT ANSWER:**
{correct_answer}

**EXPLANATION:**
{explanation}

**STUDENT'S ANSWER:**
{user_answer}

**EVALUATION RULES:**
- For MCQ: Check if the letter/option matches
- For True/False: Check if the answer matches (accept variations like "true", "yes", "T")
- For Short Answer: Check if the key concepts are present (be fair, partial credit allowed)

Return JSON:
{{
    "correct": true/false,
    "score": 0.0-1.0,
    "feedback": "<brief, encouraging feedback>"
}}"""

    QUESTION_TYPES = ["mcq", "true_false", "short_answer"]
    QUESTION_TYPE_WEIGHTS = [0.5, 0.25, 0.25]  # 50% MCQ, 25% T/F, 25% short

    async def start_quiz(
        self,
        state: Dict[str, Any],
    ) -> QuizStartResult:
        """
        Start a new quiz by generating all questions.
        
        Args:
            state: Current state with chapter info and config
            
        Returns:
            QuizStartResult with all questions and first question display
        """
        chapter_number = state.get("current_chapter", 1)
        chapter_title = state.get("chapter_title", f"Chapter {chapter_number}")
        topics_covered = state.get("topics_covered_this_chapter", [])
        comprehension_score = state.get("comprehension_score", 0.7)
        questions_per_quiz = state.get("questions_per_quiz", settings.questions_per_quiz)
        retrieved_context = state.get("retrieved_context", [])
        
        # Format chapter content from retrieved context
        chapter_content = self._format_chapter_content(retrieved_context)
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
            first_question_display=f"📝 **Quiz Time!**\n\n{first_question_display}",
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
        
        # Build feedback message
        if evaluation["correct"]:
            feedback_msg = f"✅ **Correct!** {evaluation['feedback']}"
        else:
            correct_answer = current_question.get("correct_answer", "N/A")
            feedback_msg = f"❌ **Not quite.** {evaluation['feedback']}\n\n*Correct answer: {correct_answer}*"
        
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
            message = (
                f"🎉 **Quiz Complete!**\n\n"
                f"Your Score: **{score_percent:.0f}%**\n\n"
                f"Great job! You've demonstrated a solid understanding of this chapter. "
                f"Let's move on to the next one!"
            )
            return QuizCompletionResult(
                passed=True,
                final_score=final_score,
                message=message,
                awaiting_decision=False,
            )
        else:
            message = (
                f"📊 **Quiz Complete!**\n\n"
                f"Your Score: **{score_percent:.0f}%** (Passing: {settings.quiz_passing_score * 100:.0f}%)\n\n"
                f"You're close! Would you like to:\n"
                f"- **Retry** the quiz with new questions\n"
                f"- **Move on** to the next chapter (you can always come back)\n\n"
                f"Just say 'retry' or 'move on'."
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
        prompt = self.QUESTION_GENERATION_PROMPT.format(
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
            system_prompt=self.SYSTEM_PROMPT,
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
        prompt = self.ANSWER_EVALUATION_PROMPT.format(
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
            "feedback": "Good answer!" if correct else "Not quite right.",
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
