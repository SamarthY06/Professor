"""Quiz API routes."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.models.quiz import Quiz, QuizQuestion, QuizAttempt, QuestionResponse

logger = get_logger(__name__)
router = APIRouter()


class QuizResponse(BaseModel):
    """Quiz response model."""
    id: UUID
    book_id: UUID
    chapter_id: UUID
    quiz_type: str
    title: Optional[str]
    total_questions: Optional[int]
    passing_score: float
    time_limit_minutes: Optional[int]

    class Config:
        from_attributes = True


class QuestionResponseSchema(BaseModel):
    """Question response model."""
    id: UUID
    question_text: str
    question_type: str  # mcq, true_false, short_answer, explain
    options: Optional[dict]
    difficulty: str
    topic: Optional[str]

    class Config:
        from_attributes = True


class AnswerRequest(BaseModel):
    """Answer submission request."""
    question_id: UUID
    answer: str


class AnswerFeedback(BaseModel):
    """Feedback for an answer."""
    is_correct: bool
    correct_answer: str
    explanation: Optional[str]
    next_question: Optional[QuestionResponseSchema]
    quiz_complete: bool
    score: Optional[float]
    passed: Optional[bool]


class AttemptResponse(BaseModel):
    """Quiz attempt response."""
    id: UUID
    quiz_id: UUID
    started_at: datetime
    completed_at: Optional[datetime]
    score: Optional[float]
    passed: Optional[bool]
    time_taken_seconds: Optional[int]

    class Config:
        from_attributes = True


class AttemptDetailResponse(AttemptResponse):
    """Detailed attempt with answers."""
    answers: Optional[dict]
    feedback: Optional[dict]


@router.get("/chapter/{chapter_id}", response_model=List[QuizResponse])
async def get_chapter_quizzes(
    chapter_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get available quizzes for a chapter."""
    result = await db.execute(
        select(Quiz).where(Quiz.chapter_id == chapter_id)
    )
    quizzes = result.scalars().all()
    return quizzes


@router.post("/start/{quiz_id}", response_model=QuestionResponseSchema)
async def start_quiz(
    quiz_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Start a quiz attempt and get the first question."""
    # Get quiz
    result = await db.execute(select(Quiz).where(Quiz.id == quiz_id))
    quiz = result.scalar_one_or_none()
    
    if quiz is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )
    
    # Check for existing incomplete attempt
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.completed_at.is_(None),
        )
    )
    existing_attempt = result.scalar_one_or_none()
    
    if existing_attempt:
        # Resume existing attempt
        attempt = existing_attempt
    else:
        # Create new attempt
        attempt = QuizAttempt(
            user_id=user_id,
            quiz_id=quiz_id,
            answers={},
        )
        db.add(attempt)
        await db.flush()
    
    # Get first unanswered question
    answered_ids = list(attempt.answers.keys()) if attempt.answers else []
    
    result = await db.execute(
        select(QuizQuestion).where(
            QuizQuestion.quiz_id == quiz_id,
            ~QuizQuestion.id.in_([UUID(qid) for qid in answered_ids]) if answered_ids else True,
        ).limit(1)
    )
    question = result.scalar_one_or_none()
    
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No questions available",
        )
    
    await db.commit()
    
    logger.info(
        "quiz_started",
        user_id=str(user_id),
        quiz_id=str(quiz_id),
        attempt_id=str(attempt.id),
    )
    
    return QuestionResponseSchema(
        id=question.id,
        question_text=question.question_text,
        question_type=question.question_type,
        options=question.options,
        difficulty=question.difficulty,
        topic=question.topic,
    )


@router.post("/answer", response_model=AnswerFeedback)
async def submit_answer(
    request: AnswerRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer and get feedback."""
    # Get question
    result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.id == request.question_id)
    )
    question = result.scalar_one_or_none()
    
    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )
    
    # Get user's current attempt
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.user_id == user_id,
            QuizAttempt.quiz_id == question.quiz_id,
            QuizAttempt.completed_at.is_(None),
        )
    )
    attempt = result.scalar_one_or_none()
    
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active quiz attempt",
        )
    
    # Check answer
    is_correct = _check_answer(question, request.answer)
    
    # Save response
    response = QuestionResponse(
        attempt_id=attempt.id,
        question_id=question.id,
        user_answer=request.answer,
        is_correct=is_correct,
    )
    db.add(response)
    
    # Update attempt answers
    answers = dict(attempt.answers) if attempt.answers else {}
    answers[str(question.id)] = request.answer
    attempt.answers = answers
    
    # Get total questions answered
    result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.quiz_id == question.quiz_id)
    )
    all_questions = result.scalars().all()
    total_questions = len(all_questions)
    answered_count = len(answers)
    
    # Check if quiz is complete
    quiz_complete = answered_count >= total_questions
    
    score = None
    passed = None
    next_question = None
    
    if quiz_complete:
        # Calculate score
        correct_count = sum(
            1 for q in all_questions
            if _check_answer(q, answers.get(str(q.id), ""))
        )
        score = correct_count / total_questions
        
        # Check pass/fail
        result = await db.execute(
            select(Quiz).where(Quiz.id == question.quiz_id)
        )
        quiz = result.scalar_one()
        passed = score >= quiz.passing_score
        
        # Complete attempt
        attempt.completed_at = datetime.utcnow()
        attempt.score = score
        attempt.passed = passed
        attempt.time_taken_seconds = int(
            (datetime.utcnow() - attempt.started_at).total_seconds()
        )
        
        logger.info(
            "quiz_completed",
            user_id=str(user_id),
            quiz_id=str(question.quiz_id),
            score=score,
            passed=passed,
        )
    else:
        # Get next question
        result = await db.execute(
            select(QuizQuestion).where(
                QuizQuestion.quiz_id == question.quiz_id,
                ~QuizQuestion.id.in_([UUID(qid) for qid in answers.keys()]),
            ).limit(1)
        )
        next_q = result.scalar_one_or_none()
        
        if next_q:
            next_question = QuestionResponseSchema(
                id=next_q.id,
                question_text=next_q.question_text,
                question_type=next_q.question_type,
                options=next_q.options,
                difficulty=next_q.difficulty,
                topic=next_q.topic,
            )
    
    await db.commit()
    
    return AnswerFeedback(
        is_correct=is_correct,
        correct_answer=question.correct_answer,
        explanation=question.explanation,
        next_question=next_question,
        quiz_complete=quiz_complete,
        score=round(score * 100, 1) if score else None,
        passed=passed,
    )


def _check_answer(question: QuizQuestion, user_answer: str) -> bool:
    """Check if user's answer is correct."""
    if not user_answer:
        return False
    
    correct = question.correct_answer.lower().strip()
    answer = user_answer.lower().strip()
    
    if question.question_type == "mcq":
        return answer == correct
    elif question.question_type == "true_false":
        return answer == correct
    else:
        # For short answer, check for similarity
        # This is a simple check; in production, use LLM for evaluation
        return correct in answer or answer in correct


@router.get("/attempts", response_model=List[AttemptResponse])
async def list_attempts(
    quiz_id: Optional[UUID] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List user's quiz attempts."""
    conditions = [QuizAttempt.user_id == user_id]
    
    if quiz_id:
        conditions.append(QuizAttempt.quiz_id == quiz_id)
    
    result = await db.execute(
        select(QuizAttempt)
        .where(and_(*conditions))
        .order_by(QuizAttempt.started_at.desc())
    )
    attempts = result.scalars().all()
    return attempts


@router.get("/attempts/{attempt_id}", response_model=AttemptDetailResponse)
async def get_attempt(
    attempt_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed attempt information."""
    result = await db.execute(
        select(QuizAttempt).where(
            QuizAttempt.id == attempt_id,
            QuizAttempt.user_id == user_id,
        )
    )
    attempt = result.scalar_one_or_none()
    
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found",
        )
    
    return attempt
