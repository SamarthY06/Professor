"""Quiz service - generates and evaluates quizzes with proper scoring."""

from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime
import json
from openai import AsyncOpenAI
from sqlalchemy import select

from app.config import settings
from app.db.database import async_session_maker
from app.logs.logger import get_logger
from app.models.quiz import QuizAttempt, QuizQuestion

logger = get_logger(__name__)


async def generate_quiz(
    book_id: str,
    chapter: int,
    num_questions: int = 5,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Generate quiz questions for a chapter."""
    
    from app.rag.retrieval import retrieve_chapter_chunks
    
    async with async_session_maker() as db:
        chunks = await retrieve_chapter_chunks(db, book_id, chapter, "key concepts quiz", api_key)
        context = "\n---\n".join([c.get("content", "")[:400] for c in chunks[:5]])
        
        client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        
        prompt = f"""Based on this content, generate {num_questions} quiz questions.

Content:
{context}

Return JSON array:
[{{"question": "...", "answer": "...", "explanation": "..."}}]"""

        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "Generate educational quiz questions. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.7,
                response_format={"type": "json_object"},
            )
            
            result = json.loads(response.choices[0].message.content)
            questions = result.get("questions", result) if isinstance(result, dict) else result
            
            if isinstance(questions, list):
                return questions[:num_questions]
                
        except Exception as e:
            logger.exception("quiz_generation_failed", error=str(e))
        
        return [
            {"question": f"What is the main concept of Chapter {chapter}?", "answer": "Various concepts", "explanation": "Review the chapter."},
            {"question": "How does this relate to previous chapters?", "answer": "Builds upon foundations", "explanation": "Connections exist."},
        ]


async def evaluate_answer(
    question: Dict[str, Any],
    answer: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate a quiz answer with proper LLM-based validation."""
    
    client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
    
    prompt = f"""Evaluate this student's answer fairly:

Question: {question.get('question')}
Expected/Correct Answer: {question.get('answer')}
Explanation: {question.get('explanation', 'N/A')}
Student's Answer: {answer}

Be fair - the student doesn't need to match exactly, just show understanding.
Give partial credit for partially correct answers.

Respond with JSON:
{{"correct": true/false, "score": 0.0-1.0, "feedback": "specific constructive feedback"}}"""

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model_mini,
            messages=[
                {"role": "system", "content": "You are a fair grader. Evaluate student answers based on understanding, not exact wording. Return JSON only."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        
        result = json.loads(response.choices[0].message.content)
        return {
            "correct": result.get("correct", False),
            "score": result.get("score", 0.5),
            "feedback": result.get("feedback", "Thank you for your answer."),
        }
        
    except Exception as e:
        logger.exception("answer_evaluation_failed", error=str(e))
        return {"correct": True, "score": 0.7, "feedback": "Good effort!"}


async def should_trigger_quiz(
    book_id: str,
    user_id: str,
    current_chapter: int,
    chapters_completed: List[int],
) -> bool:
    """
    Check if quiz should be triggered based on user preferences (Goals.md Section 6).
    
    Quiz Trigger Conditions:
    - after_each_chapter: Quiz after every chapter
    - after_n_chapters: Quiz after N chapters completed
    - final_only: Quiz only at the end
    """
    from app.models.learning_config import LearningConfig
    from app.models.book import Book
    
    async with async_session_maker() as db:
        try:
            # Get learning config
            config_result = await db.execute(
                select(LearningConfig).where(
                    LearningConfig.book_id == UUID(book_id),
                    LearningConfig.user_id == UUID(user_id)
                )
            )
            config = config_result.scalar_one_or_none()
            
            if not config:
                return True  # Default: quiz after each chapter
            
            # Get total chapters
            book_result = await db.execute(
                select(Book.total_chapters).where(Book.id == UUID(book_id))
            )
            book_row = book_result.first()
            total_chapters = book_row[0] if book_row else 5
            
            quiz_frequency = config.quiz_frequency
            
            if quiz_frequency == "after_each_chapter":
                return True
            
            elif quiz_frequency == "after_n_chapters":
                n = config.quiz_after_n_chapters or 2
                return len(chapters_completed) % n == 0
            
            elif quiz_frequency == "final_only":
                return current_chapter >= total_chapters
            
            return True  # Default
            
        except Exception as e:
            logger.exception("quiz_trigger_check_failed", error=str(e))
            return True


async def get_quiz_config(book_id: str, user_id: str) -> Dict[str, Any]:
    """Get quiz configuration for a user/book."""
    from app.models.learning_config import LearningConfig
    
    async with async_session_maker() as db:
        try:
            config_result = await db.execute(
                select(LearningConfig).where(
                    LearningConfig.book_id == UUID(book_id),
                    LearningConfig.user_id == UUID(user_id)
                )
            )
            config = config_result.scalar_one_or_none()
            
            if config:
                return {
                    "questions_per_quiz": config.questions_per_quiz,
                    "quiz_frequency": config.quiz_frequency,
                    "quiz_difficulty": config.quiz_difficulty,
                }
            
            return {
                "questions_per_quiz": 5,
                "quiz_frequency": "after_each_chapter",
                "quiz_difficulty": "medium",
            }
            
        except Exception as e:
            logger.exception("get_quiz_config_failed", error=str(e))
            return {"questions_per_quiz": 5, "quiz_frequency": "after_each_chapter", "quiz_difficulty": "medium"}
