"""Planning API - Human-in-the-loop learning plan generation.

Per Goals.md Step 4:
- Planner Agent generates detailed plan based on user config
- User reviews and can request changes
- User must explicitly ACCEPT before teaching starts
- No teaching until plan acceptance
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies import get_current_user_id, get_redis
from app.logs.logger import get_logger
from app.models.book import Book
from app.models.learning_config import LearningConfig, LearningPlan
from app.models.learning import LearningState
from app.models.chat import ChatSession, ChatMessage

logger = get_logger(__name__)
router = APIRouter()


class GeneratePlanRequest(BaseModel):
    """Request to generate a learning plan."""
    book_id: UUID
    additional_instructions: Optional[str] = Field(
        default=None,
        description="Any additional preferences for the plan"
    )


class PlanResponse(BaseModel):
    """Learning plan response."""
    id: UUID
    book_id: UUID
    summary: Optional[str] = None  # Maps to plan_summary in DB
    plan_data: dict
    status: str
    version: int
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewPlanRequest(BaseModel):
    """Request to provide feedback on a plan."""
    plan_id: UUID
    feedback: str = Field(
        ...,
        description="User's feedback or change requests for the plan"
    )
    action: str = Field(
        ...,
        description="Action: 'request_changes' or 'accept'"
    )


class AcceptPlanResponse(BaseModel):
    """Response after accepting a plan."""
    success: bool
    message: str
    can_start_learning: bool
    session_id: Optional[UUID] = None


@router.post("/generate", response_model=PlanResponse)
async def generate_learning_plan(
    request: GeneratePlanRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a personalized learning plan.
    
    Per Goals.md Step 4:
    - Uses user's learning config (level, timeline, quiz prefs)
    - Generates chapter-wise schedule
    - Returns plan for user review
    """
    from app.services.api_key_service import APIKeyService
    from app.agents.planner import PlannerAgent
    from datetime import date
    
    # Get book and config
    book_result = await db.execute(
        select(Book)
        .where(Book.id == request.book_id)
        .where(Book.user_id == user_id)
    )
    book = book_result.scalar_one_or_none()
    
    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found"
        )
    
    if book.processing_status not in ["completed", "ready_for_planning"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Book is not ready for planning. Status: {book.processing_status}"
        )
    
    # Get learning config
    config_result = await db.execute(
        select(LearningConfig).where(LearningConfig.book_id == request.book_id)
    )
    config = config_result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Learning configuration not found. Please re-upload the book."
        )
    
    # Get chapters
    from app.models.book import BookChapter
    chapters_result = await db.execute(
        select(BookChapter)
        .where(BookChapter.book_id == request.book_id)
        .order_by(BookChapter.chapter_number)
    )
    chapters = chapters_result.scalars().all()
    
    if not chapters:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No chapters found. Book may still be processing."
        )
    
    # Filter chapters if not studying all
    if not config.study_all_chapters and config.selected_chapters:
        chapters = [c for c in chapters if c.chapter_number in config.selected_chapters]
    
    # Get user's API key
    api_key_service = APIKeyService(db)
    api_key = await api_key_service.get_api_key_for_user(user_id)
    
    target_days = 0
    if config.deadline:
        target_days = (config.deadline - date.today()).days
    if target_days <= 0:
        target_days = len(chapters)

    chapter_list = [
        {
            "number": c.chapter_number,
            "title": c.title or f"Chapter {c.chapter_number}",
            "estimated_minutes": c.estimated_duration_minutes or 45,
            "summary": c.summary or "",
        }
        for c in chapters
    ]

    planner = PlannerAgent(api_key=api_key)
    planner_state = {
        "user_id": str(user_id),
        "active_book_id": str(request.book_id),
        "book_title": book.title,
        "total_chapters": len(chapters),
        "professor_level": config.learning_level,
        "preferred_study_time_minutes": config.daily_study_minutes,
        "target_days": target_days,
        "chapters": chapter_list,
        "additional_instructions": request.additional_instructions or "",
    }

    plan_data = {}
    for attempt in range(2):
        plan_result = await planner.process(planner_state)
        plan_data = plan_result.plan_data if hasattr(plan_result, 'plan_data') else plan_result.get("learning_plan", {})
        days = plan_data.get("days", [])
        day_numbers = [d.get("day") for d in days if isinstance(d, dict)]
        
        if days and len(days) > 0:
            actual_days = len(days)
            if sorted(day_numbers) == list(range(1, actual_days + 1)):
                target_days = actual_days
                break
    else:
        raise HTTPException(status_code=500, detail="Plan generation failed - invalid plan structure")
    
    plan_data["total_days"] = target_days
    plan_data["daily_minutes"] = config.daily_study_minutes
    plan_data["learning_level"] = config.learning_level
    plan_data["quiz_frequency"] = config.quiz_frequency
    
    # Generate human-readable summary
    summary = f"""📚 **Learning Plan for {book.title}**

**Duration:** {plan_data.get('total_days', target_days)} days
**Chapters:** {len(chapters)}
**Daily Study Time:** {config.daily_study_minutes} minutes

{plan_data.get('overview', '')}

**Schedule:**
"""
    for day in plan_data.get("days", [])[:5]:
        if day.get("rest"):
            summary += f"\n• Day {day.get('day')}: Review or rest"
            continue
        items = day.get("items", [])
        titles = ", ".join([i.get("chapter_title", "") for i in items])
        summary += f"\n• Day {day.get('day')}: {titles}"

    if len(plan_data.get("days", [])) > 5:
        summary += f"\n• ... and {len(plan_data['days']) - 5} more days"

    summary += "\n\n**Would you like to proceed with this plan, or would you like any changes?**"
    
    # Check for existing plan and increment version
    existing_plan_result = await db.execute(
        select(LearningPlan)
        .where(LearningPlan.book_id == request.book_id)
        .where(LearningPlan.user_id == user_id)
        .order_by(LearningPlan.version.desc())
    )
    existing_plan = existing_plan_result.scalar_one_or_none()
    version = (existing_plan.version + 1) if existing_plan else 1
    
    # Mark old plans as superseded
    if existing_plan and existing_plan.status == "pending_review":
        existing_plan.status = "superseded"
    
    # Create new plan
    plan = LearningPlan(
        config_id=config.id,
        user_id=user_id,
        book_id=request.book_id,
        plan_data=plan_data,
        plan_summary=summary,  # DB column is plan_summary
        version=version,
        status="pending_review",
    )
    db.add(plan)
    
    # Update phase on LearningState
    ls_result = await db.execute(
        select(LearningState)
        .where(LearningState.user_id == user_id)
        .where(LearningState.book_id == request.book_id)
    )
    ls = ls_result.scalar_one_or_none()
    if ls:
        ls.current_phase = "plan_review"

    # Update config
    config.plan_generated = True
    
    await db.commit()
    await db.refresh(plan)
    
    logger.info(
        "learning_plan_generated",
        user_id=str(user_id),
        book_id=str(request.book_id),
        plan_id=str(plan.id),
        version=version,
    )
    
    return PlanResponse(
        id=plan.id,
        book_id=request.book_id,
        summary=summary,
        plan_data=plan_data,
        status=plan.status,
        version=plan.version,
        created_at=plan.created_at,
    )


@router.post("/review", response_model=AcceptPlanResponse)
async def review_plan(
    request: ReviewPlanRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Review and provide feedback on a learning plan.
    
    Per Goals.md Step 4:
    - User can request changes (iterate with planner)
    - User must explicitly ACCEPT before teaching starts
    """
    # Get the plan
    plan_result = await db.execute(
        select(LearningPlan)
        .where(LearningPlan.id == request.plan_id)
        .where(LearningPlan.user_id == user_id)
    )
    plan = plan_result.scalar_one_or_none()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )
    
    if plan.status not in ["pending_review", "draft"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan cannot be reviewed. Status: {plan.status}"
        )
    
    # Store feedback
    plan.user_feedback = request.feedback
    
    if request.action == "accept":
        # User accepts the plan - teaching can now begin!
        plan.status = "accepted"
        plan.accepted_at = datetime.utcnow()
        
        # Update config
        config_result = await db.execute(
            select(LearningConfig).where(LearningConfig.id == plan.config_id)
        )
        config = config_result.scalar_one_or_none()
        if config:
            config.plan_accepted = True
            config.plan_accepted_at = datetime.utcnow()
        
        # Update LearningState phase and plan
        session_id = None
        state_result = await db.execute(
            select(LearningState)
            .where(LearningState.user_id == user_id)
            .where(LearningState.book_id == plan.book_id)
        )
        learning_state = state_result.scalar_one_or_none()

        if learning_state:
            learning_state.current_phase = "teaching"
            learning_state.learning_plan = plan.plan_data
            from datetime import date
            learning_state.plan_start_date = date.today()

            session = ChatSession(
                user_id=user_id,
                learning_state_id=learning_state.id,
                book_id=plan.book_id,
                chapter_context=1,
                session_type="teaching",
            )
            db.add(session)
            await db.flush()
            session_id = session.id

            from app.models.chat import ChatMessage
            from app.models.book import Book

            book_result = await db.execute(
                select(Book).where(Book.id == plan.book_id)
            )
            book = book_result.scalar_one_or_none()
            book_title = book.title if book else "your book"

            days = plan.plan_data.get("days", [])
            day1 = days[0] if days else {}
            day1_title = day1.get("day_title", "Getting Started")
            day1_items = day1.get("items", [])
            chapters_today = ", ".join([f"Chapter {item.get('chapter_number')}: {item.get('chapter_title', '')}" for item in day1_items])

            greeting = f"""🎉 **Your learning plan is confirmed!**

Welcome to Day 1 of your journey through **{book_title}**!

**Today's Focus:** {day1_title}
{f"**Chapters:** {chapters_today}" if chapters_today else ""}

I'll guide you through today's material step by step. When you're ready, just say **"Let's start"** or **"Begin"** and we'll dive in!

Remember: You can ask questions anytime, and I'll check your understanding as we go. Let's make this a great learning experience! 📚"""

            initial_message = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=greeting,
                agent_name="Professor",
                chapter_at_time=1,
            )
            db.add(initial_message)
        
        await db.commit()

        # Terminate any stale Temporal chat workflow so the next message
        # starts a fresh one that reads the updated DB state (phase=teaching).
        try:
            from app.temporal.client import get_temporal_client
            client = await get_temporal_client()
            wf_id = f"chat-{user_id}-{plan.book_id}"
            handle = client.get_workflow_handle(wf_id)
            await handle.terminate("Plan accepted via REST — restarting for teaching phase")
            logger.info("terminated_stale_workflow", workflow_id=wf_id)
        except Exception:
            pass  # No running workflow — that's fine
        
        logger.info(
            "learning_plan_accepted",
            user_id=str(user_id),
            plan_id=str(plan.id),
        )
        
        return AcceptPlanResponse(
            success=True,
            message="Excellent! Your learning plan is confirmed. Professor is ready to begin Day 1!",
            can_start_learning=True,
            session_id=session_id,
        )
    
    elif request.action == "request_changes":
        # User wants changes - trigger plan regeneration with feedback
        plan.status = "superseded"
        
        await db.commit()
        
        logger.info(
            "learning_plan_changes_requested",
            user_id=str(user_id),
            plan_id=str(plan.id),
            feedback=request.feedback[:100],
        )
        
        return AcceptPlanResponse(
            success=True,
            message="I understand. Let me revise the plan based on your feedback. "
                    "Please call the generate endpoint again with your additional instructions.",
            can_start_learning=False,
        )
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Use 'accept' or 'request_changes'"
        )


@router.get("/{book_id}/current", response_model=Optional[PlanResponse])
async def get_current_plan(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the current active plan for a book."""
    result = await db.execute(
        select(LearningPlan)
        .where(LearningPlan.book_id == book_id)
        .where(LearningPlan.user_id == user_id)
        .where(LearningPlan.status.in_(["pending_review", "accepted"]))
        .order_by(LearningPlan.version.desc())
    )
    plan = result.scalar_one_or_none()
    
    if not plan:
        return None
    
    return PlanResponse(
        id=plan.id,
        book_id=plan.book_id,
        summary=plan.plan_summary,  # DB column is plan_summary
        plan_data=plan.plan_data,
        status=plan.status,
        version=plan.version,
        created_at=plan.created_at,
    )


@router.get("/{book_id}/can-start-teaching")
async def can_start_teaching(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if teaching can begin for a book.
    
    Per Goals.md: "No teaching starts until plan acceptance"
    """
    # Check if plan is accepted
    config_result = await db.execute(
        select(LearningConfig)
        .where(LearningConfig.book_id == book_id)
        .where(LearningConfig.user_id == user_id)
    )
    config = config_result.scalar_one_or_none()
    
    if not config:
        return {
            "can_start": False,
            "reason": "no_config",
            "message": "Learning configuration not found.",
        }
    
    if not config.plan_generated:
        return {
            "can_start": False,
            "reason": "no_plan",
            "message": "Learning plan has not been generated yet.",
        }
    
    if not config.plan_accepted:
        return {
            "can_start": False,
            "reason": "plan_not_accepted",
            "message": "Please review and accept your learning plan before starting.",
        }
    
    return {
        "can_start": True,
        "reason": "ready",
        "message": "You're all set! Teaching can begin.",
    }
