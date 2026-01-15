"""Goal management API routes."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.models.book import Goal, GoalChapter

logger = get_logger(__name__)
router = APIRouter()


class GoalCreateRequest(BaseModel):
    """Goal creation request."""
    title: str
    description: Optional[str] = None
    duration_days: int
    difficulty_level: str = "intermediate"  # beginner, intermediate, advanced


class GoalResponse(BaseModel):
    """Goal response model."""
    id: UUID
    title: str
    description: Optional[str]
    duration_days: int
    difficulty_level: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class GoalDetailResponse(GoalResponse):
    """Goal detail response with chapters."""
    chapters: List["GoalChapterResponse"]
    ai_generated_curriculum: Optional[dict]


class GoalChapterResponse(BaseModel):
    """Goal chapter response model."""
    id: UUID
    week_number: int
    title: str
    topics: dict
    learning_objectives: Optional[List[str]]
    summary: Optional[str]

    class Config:
        from_attributes = True


class GoalUpdateRequest(BaseModel):
    """Goal update request."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # active, paused, completed, abandoned


@router.get("/", response_model=List[GoalResponse])
async def list_goals(
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all goals for the current user."""
    result = await db.execute(
        select(Goal)
        .where(Goal.user_id == user_id)
        .order_by(Goal.created_at.desc())
    )
    goals = result.scalars().all()
    return goals


@router.get("/{goal_id}", response_model=GoalDetailResponse)
async def get_goal(
    goal_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get goal details with chapters."""
    result = await db.execute(
        select(Goal)
        .where(Goal.id == goal_id, Goal.user_id == user_id)
        .options(selectinload(Goal.chapters))
    )
    goal = result.scalar_one_or_none()
    
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    
    return GoalDetailResponse(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        duration_days=goal.duration_days,
        difficulty_level=goal.difficulty_level,
        status=goal.status,
        created_at=goal.created_at,
        ai_generated_curriculum=goal.ai_generated_curriculum,
        chapters=[
            GoalChapterResponse(
                id=ch.id,
                week_number=ch.week_number,
                title=ch.title,
                topics=ch.topics,
                learning_objectives=ch.learning_objectives,
                summary=ch.summary,
            )
            for ch in sorted(goal.chapters, key=lambda x: x.week_number)
        ],
    )


@router.post("/", response_model=GoalResponse)
async def create_goal(
    request: GoalCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new learning goal.
    The AI will generate a curriculum based on the goal.
    """
    goal = Goal(
        user_id=user_id,
        title=request.title,
        description=request.description,
        duration_days=request.duration_days,
        difficulty_level=request.difficulty_level,
        status="active",
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    
    logger.info(
        "goal_created",
        user_id=str(user_id),
        goal_id=str(goal.id),
        duration_days=request.duration_days,
    )
    
    # Trigger async curriculum generation
    # await trigger_curriculum_generation(goal.id)
    
    return goal


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: UUID,
    updates: GoalUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update goal metadata or status."""
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    goal = result.scalar_one_or_none()
    
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(goal, field, value)
    
    await db.commit()
    await db.refresh(goal)
    
    logger.info(
        "goal_updated",
        user_id=str(user_id),
        goal_id=str(goal_id),
        fields=list(update_data.keys()),
    )
    
    return goal


@router.delete("/{goal_id}")
async def delete_goal(
    goal_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a goal and all associated data."""
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    goal = result.scalar_one_or_none()
    
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    
    await db.delete(goal)
    await db.commit()
    
    logger.info("goal_deleted", user_id=str(user_id), goal_id=str(goal_id))
    
    return {"message": "Goal deleted successfully"}


@router.post("/{goal_id}/regenerate-curriculum")
async def regenerate_curriculum(
    goal_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate AI curriculum for a goal."""
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    goal = result.scalar_one_or_none()
    
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    
    # Clear existing chapters
    await db.execute(
        GoalChapter.__table__.delete().where(GoalChapter.goal_id == goal_id)
    )
    
    # Trigger async curriculum generation
    # await trigger_curriculum_generation(goal.id)
    
    logger.info("curriculum_regeneration_triggered", goal_id=str(goal_id))
    
    return {"message": "Curriculum regeneration started"}
