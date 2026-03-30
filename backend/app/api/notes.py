"""Notes API routes."""

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
from app.models.note import UserNote

logger = get_logger(__name__)
router = APIRouter()


class NoteCreateRequest(BaseModel):
    """Note creation request."""
    title: Optional[str] = None
    content: str
    book_id: Optional[UUID] = None
    goal_id: Optional[UUID] = None
    chapter_id: Optional[UUID] = None
    source_message_id: Optional[UUID] = None
    tags: Optional[List[str]] = None


class NoteUpdateRequest(BaseModel):
    """Note update request."""
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    is_pinned: Optional[bool] = None


class NoteResponse(BaseModel):
    """Note response model."""
    id: UUID
    title: Optional[str]
    content: str
    book_id: Optional[UUID]
    goal_id: Optional[UUID]
    chapter_id: Optional[UUID]
    source_message_id: Optional[UUID]
    tags: Optional[List[str]]
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=List[NoteResponse])
async def list_notes(
    book_id: Optional[UUID] = None,
    goal_id: Optional[UUID] = None,
    chapter_id: Optional[UUID] = None,
    tag: Optional[str] = None,
    pinned_only: bool = False,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List user's notes with optional filters."""
    conditions = [UserNote.user_id == user_id]
    
    if book_id:
        conditions.append(UserNote.book_id == book_id)
    if goal_id:
        conditions.append(UserNote.goal_id == goal_id)
    if chapter_id:
        conditions.append(UserNote.chapter_id == chapter_id)
    if tag:
        conditions.append(UserNote.tags.contains([tag]))
    if pinned_only:
        conditions.append(UserNote.is_pinned == True)
    
    result = await db.execute(
        select(UserNote)
        .where(and_(*conditions))
        .order_by(UserNote.is_pinned.desc(), UserNote.updated_at.desc())
    )
    notes = result.scalars().all()
    return notes


@router.get("/export/{format}")
async def export_notes(
    format: str,
    book_id: Optional[UUID] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Export notes in various formats (json, markdown, txt)."""
    from fastapi.responses import Response
    import json

    conditions = [UserNote.user_id == user_id]
    if book_id:
        conditions.append(UserNote.book_id == book_id)

    result = await db.execute(
        select(UserNote)
        .where(and_(*conditions))
        .order_by(UserNote.created_at.desc())
    )
    notes = result.scalars().all()

    if format == "json":
        export_data = [
            {
                "title": note.title,
                "content": note.content,
                "tags": note.tags or [],
                "created_at": note.created_at.isoformat(),
                "is_pinned": note.is_pinned,
            }
            for note in notes
        ]
        return Response(
            content=json.dumps(export_data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=notes.json"},
        )

    elif format == "markdown":
        md_content = "# My Learning Notes\n\n"
        for note in notes:
            md_content += f"## {note.title or 'Untitled'}\n\n"
            md_content += f"{note.content}\n\n"
            if note.tags:
                md_content += f"Tags: {', '.join(note.tags)}\n\n"
            md_content += f"*Created: {note.created_at.strftime('%Y-%m-%d %H:%M')}*\n\n---\n\n"

        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=notes.md"},
        )

    elif format == "txt":
        txt_content = "MY LEARNING NOTES\n" + "=" * 50 + "\n\n"
        for note in notes:
            txt_content += f"TITLE: {note.title or 'Untitled'}\n"
            txt_content += f"DATE: {note.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            txt_content += "-" * 30 + "\n"
            txt_content += f"{note.content}\n"
            txt_content += "\n" + "=" * 50 + "\n\n"

        return Response(
            content=txt_content,
            media_type="text/plain",
            headers={"Content-Disposition": "attachment; filename=notes.txt"},
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid format. Use: json, markdown, or txt",
        )


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific note."""
    result = await db.execute(
        select(UserNote).where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
        )
    )
    note = result.scalar_one_or_none()
    
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
    
    return note


@router.post("/", response_model=NoteResponse)
async def create_note(
    request: NoteCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new note."""
    note = UserNote(
        user_id=user_id,
        title=request.title,
        content=request.content,
        book_id=request.book_id,
        goal_id=request.goal_id,
        chapter_id=request.chapter_id,
        source_message_id=request.source_message_id,
        tags=request.tags,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    
    logger.info("note_created", user_id=str(user_id), note_id=str(note.id))
    
    return note


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: UUID,
    updates: NoteUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update a note."""
    result = await db.execute(
        select(UserNote).where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
        )
    )
    note = result.scalar_one_or_none()
    
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
    
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)
    
    await db.commit()
    await db.refresh(note)
    
    return note


@router.delete("/{note_id}")
async def delete_note(
    note_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a note."""
    result = await db.execute(
        select(UserNote).where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
        )
    )
    note = result.scalar_one_or_none()
    
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
    
    await db.delete(note)
    await db.commit()
    
    logger.info("note_deleted", note_id=str(note_id))
    
    return {"message": "Note deleted"}


@router.post("/{note_id}/pin")
async def toggle_pin(
    note_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Toggle pin status of a note."""
    result = await db.execute(
        select(UserNote).where(
            UserNote.id == note_id,
            UserNote.user_id == user_id,
        )
    )
    note = result.scalar_one_or_none()
    
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
    
    note.is_pinned = not note.is_pinned
    await db.commit()
    
    return {"is_pinned": note.is_pinned}
