"""
Chat API routes - Updated for Agent-Driven Architecture.

Key Changes:
1. Uses simplified state from LearningState (single source of truth)
2. Persists state after each interaction
3. Updates last_active_at for inactivity tracking
4. Works with new phase system
5. Caches learning state and book info for performance
"""

import time
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.dependencies import get_current_user_id, get_redis
from app.logs.logger import get_logger
from app.models.chat import ChatSession, ChatMessage
from app.models.learning import LearningState
from app.models.book import Book
from app.services.cache_service import get_cache_service

logger = get_logger(__name__)
router = APIRouter()
cache = get_cache_service()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

from app.services.plan_state import (
    has_real_plan as _has_real_plan,
    resolve_plan_data as _resolve_plan_data,
    extract_pending_config as _extract_pending_config,
    resolve_learning_level as _resolve_learning_level,
    resolve_config_values as _resolve_config_values,
)


def sanitize_response_text(text: str) -> str:
    """
    Sanitize LLM response text to ensure valid JSON encoding.
    
    Removes or escapes control characters that can break JSON parsing.
    Preserves newlines and tabs as they're valid in JSON strings when escaped.
    """
    if not text:
        return text
    
    # Control characters (0x00-0x1F) except tab (0x09), newline (0x0A), carriage return (0x0D)
    # These are the ones that break JSON parsing
    import re
    
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    
    return cleaned


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ChatRequest(BaseModel):
    """Chat message request."""
    message: str
    session_id: Optional[UUID] = None
    book_id: Optional[UUID] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    message: str
    session_id: UUID
    phase: str
    chapter: int
    agent_name: str
    latency_ms: int
    scope_completion_percentage: float = 0.0
    scope_remaining_topics: List[str] = []
    scope_total_topics: int = 0
    scope_covered_topics: int = 0


class MessageResponse(BaseModel):
    """Message response model."""
    id: UUID
    role: str
    content: str
    agent_name: Optional[str]
    is_quiz_question: bool
    quiz_answer_correct: Optional[bool]
    created_at: datetime

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    """Session response model."""
    id: UUID
    book_id: Optional[UUID]
    chapter_context: Optional[int]
    session_type: str
    is_active: bool
    message_count: int
    created_at: datetime
    last_message_at: Optional[datetime]

    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    """Session detail with messages."""
    messages: List[MessageResponse]


class InitSessionResponse(BaseModel):
    """Response for initializing/getting a learning session."""
    session_id: UUID
    phase: str
    current_chapter: int
    messages: List[MessageResponse]
    has_greeting: bool
    book_title: str
    total_chapters: int
    progress: dict


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_MESSAGE_LENGTH = 10000


# ============================================================================
# WORKFLOW HELPERS
# ============================================================================

async def _get_or_start_workflow(client, workflow_id: str, user_id: str, book_id: str):
    """Get a running workflow handle or start a new one.

    Uses Temporal's ``execute_update`` pattern, so we only need a handle —
    no signal+poll loop.
    """
    import asyncio
    from temporalio.client import WorkflowExecutionStatus
    from temporalio.common import WorkflowIDReusePolicy
    from app.temporal.workflows.chat_workflow import ChatWorkflow
    from app.config import settings

    try:
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
        if desc.status == WorkflowExecutionStatus.RUNNING:
            return handle
    except Exception:
        pass

    handle = await client.start_workflow(
        ChatWorkflow.run,
        args=[user_id, book_id],
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
        execution_timeout=timedelta(hours=24),
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
    await asyncio.sleep(0.5)
    return handle


# ============================================================================
# TEMPORAL-BASED CHAT ENDPOINT (Production)
# ============================================================================

@router.post("/v2", response_model=ChatResponse)
async def chat_v2(
    request: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
):
    """
    Send a message to Professor using Temporal workflow.
    
    This is the production-ready endpoint that uses Temporal for:
    - Durability (survives crashes)
    - Automatic retries
    - Long-running session support
    
    Security:
    - API key is NOT passed through workflow (loaded in activity)
    - Input validation prevents abuse
    - Rate limiting via Redis (TODO)
    """
    import asyncio
    from app.temporal.client import get_temporal_client
    from app.temporal.workflows.chat_workflow import ChatWorkflow
    
    start_time = time.time()
    
    # ========== INPUT VALIDATION ==========
    if request.book_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="book_id is required",
        )
    
    # Validate message length
    if len(request.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message too long. Maximum {MAX_MESSAGE_LENGTH} characters allowed.",
        )
    
    # Validate message is not empty
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty.",
        )
    
    book_id = request.book_id
    
    # ========== RATE LIMITING ==========
    from app.services.rate_limiter import check_chat_rate_limit
    
    rate_allowed, rate_error = await check_chat_rate_limit(redis, str(user_id))
    if not rate_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=rate_error,
        )
    
    # ========== CHECK API KEY EXISTS (but don't load it) ==========
    from app.services.api_key_service import APIKeyService
    api_key_service = APIKeyService(db)
    has_api_key = False
    try:
        api_key = await api_key_service.get_api_key_for_user(user_id)
        has_api_key = bool(api_key)
    except ValueError:
        pass
    
    if not has_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key not configured. Please add your OpenAI API key in settings.",
        )
    
    # ========== GET/CREATE SESSION (with transaction) ==========
    async with db.begin_nested():
        learning_state = await _get_or_create_learning_state(db, user_id, book_id)
        
        session_result = await db.execute(
            select(ChatSession)
            .where(ChatSession.book_id == book_id)
            .where(ChatSession.user_id == user_id)
            .where(ChatSession.is_active == True)
            .order_by(ChatSession.created_at.desc())
        )
        session = session_result.scalar()
        
        if session is None:
            session = ChatSession(
                user_id=user_id,
                learning_state_id=learning_state.id,
                book_id=book_id,
                chapter_context=learning_state.current_chapter,
                session_type="learning",
            )
            db.add(session)
            await db.flush()
        
        # Save user message
        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=request.message,
            chapter_at_time=session.chapter_context,
        )
        db.add(user_message)
    
    await db.commit()
    
    # ========== TEMPORAL WORKFLOW ==========
    try:
        client = await get_temporal_client()
    except Exception as e:
        logger.error("temporal_client_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service temporarily unavailable. Please try again.",
        )
    
    workflow_id = f"chat-{user_id}-{book_id}"
    handle = await _get_or_start_workflow(client, workflow_id, str(user_id), str(book_id))
    
    # ========== SEND MESSAGE AND POLL FOR RESPONSE ==========
    try:
        await handle.signal(ChatWorkflow.send_message, request.message)
    except Exception as sig_err:
        logger.error("signal_failed", error=str(sig_err))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message. Please try again.",
        )

    result = None
    poll_interval, max_wait = 1.5, 120
    elapsed = 0.0
    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        try:
            result = await handle.query(ChatWorkflow.get_response)
            if result and result.get("response"):
                break
        except Exception:
            pass

    if not result or not result.get("response"):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Response timeout. The professor is thinking... Please try again.",
        )

    response = result.get("response")
    phase = result.get("phase", "teaching")
    current_chapter = result.get("current_chapter", learning_state.current_chapter)
    current_day = result.get("current_day", learning_state.current_day)
    
    if not response:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Response timeout. The professor is thinking... Please try again.",
        )
    
    # ========== SAVE RESPONSE (with transaction) ==========
    async with db.begin_nested():
        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=response,
            agent_name="Professor",
            chapter_at_time=current_chapter,
            latency_ms=int((time.time() - start_time) * 1000),
        )
        db.add(assistant_message)
        
        # Update session
        session.message_count += 2
        session.last_message_at = datetime.utcnow()
        session.chapter_context = current_chapter
    
    await db.commit()
    
    latency_ms = int((time.time() - start_time) * 1000)
    
    logger.info(
        "chat_v2_completed",
        user_id=str(user_id),
        session_id=str(session.id),
        phase=phase,
        day=current_day,
        chapter=current_chapter,
        latency_ms=latency_ms,
    )
    
    return ChatResponse(
        message=sanitize_response_text(response),
        session_id=session.id,
        phase=phase,
        chapter=current_chapter,
        agent_name="Professor",
        latency_ms=latency_ms,
    )


# ============================================================================
# SSE STREAMING ENDPOINT (Temporal-based, non-blocking)
# ============================================================================

@router.post("/v2/stream")
async def chat_v2_stream(
    request: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
):
    """SSE streaming chat endpoint using Temporal workflow.update (no polling)."""
    import asyncio
    import json as json_lib
    from fastapi.responses import StreamingResponse
    from app.temporal.client import get_temporal_client
    from app.temporal.workflows.chat_workflow import ChatWorkflow
    from app.config import settings

    start_time = time.time()

    if not request.book_id:
        raise HTTPException(status_code=400, detail="book_id is required for v2/stream")

    book_id = request.book_id

    from app.services.api_key_service import APIKeyService
    api_key_service = APIKeyService(db)
    try:
        _key = await api_key_service.get_api_key_for_user(user_id)
        if not _key:
            raise ValueError("No key")
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key not configured. Please add your OpenAI API key in settings.",
        )

    result = await db.execute(
        select(LearningState)
        .where(LearningState.user_id == user_id, LearningState.book_id == book_id)
        .order_by(LearningState.created_at.desc())
        .limit(1)
    )
    learning_state = result.scalars().first()
    if not learning_state:
        raise HTTPException(status_code=404, detail="No learning state found")

    session_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id, ChatSession.book_id == book_id)
        .order_by(ChatSession.created_at.desc())
        .limit(1)
    )
    session = session_result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="No chat session found")

    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.message,
        chapter_at_time=learning_state.current_chapter,
    )
    db.add(user_msg)
    await db.commit()

    client = await get_temporal_client()
    workflow_id = f"chat-{user_id}-{book_id}"
    handle = await _get_or_start_workflow(client, workflow_id, str(user_id), str(book_id))

    async def event_generator():
        yield f"data: {json_lib.dumps({'status': 'processing'})}\n\n"

        await handle.signal(ChatWorkflow.send_message, request.message)

        poll_interval = 2
        max_wait = 120
        elapsed = 0
        query_result = None
        while elapsed < max_wait:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            try:
                query_result = await handle.query(ChatWorkflow.get_response)
                if query_result and query_result.get("response"):
                    break
            except Exception:
                pass
            if not query_result or not query_result.get("response"):
                yield f"data: {json_lib.dumps({'status': 'processing'})}\n\n"

        if query_result and query_result.get("response"):
            response_text = sanitize_response_text(query_result.get("response", ""))

            # CRITICAL: Save the assistant response to the DB so conversations persist
            try:
                assistant_msg = ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=response_text,
                    agent_name="Professor",
                    chapter_at_time=query_result.get("current_chapter", learning_state.current_chapter),
                    latency_ms=int((time.time() - start_time) * 1000),
                )
                db.add(assistant_msg)
                session.message_count = (session.message_count or 0) + 2
                session.last_message_at = datetime.utcnow()
                session.chapter_context = query_result.get("current_chapter", session.chapter_context)
                await db.commit()
            except Exception as save_err:
                logger.error("v2_stream_save_failed", error=str(save_err))

            payload = {
                "status": "complete",
                "message": response_text,
                "phase": query_result.get("phase", "teaching"),
                "current_chapter": query_result.get("current_chapter", 1),
                "current_day": query_result.get("current_day", 1),
                "latency_ms": int((time.time() - start_time) * 1000),
                "session_id": str(session.id),
            }
            yield f"data: {json_lib.dumps(payload)}\n\n"
        else:
            yield f"data: {json_lib.dumps({'status': 'error', 'error': 'timeout'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ============================================================================
# LEGACY CHAT ENDPOINT (Direct LangGraph - DEPRECATED, use /v2 or /v2/stream)
# ============================================================================

@router.post("/", response_model=ChatResponse, deprecated=True)
async def chat(
    request: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
):
    """
    DEPRECATED: Use POST /api/chat/v2 or POST /api/chat/v2/stream instead.
    
    This legacy endpoint routes directly through LangGraph without Temporal.
    It will be removed in a future release.
    """
    start_time = time.time()
    
    # Validate input
    if request.session_id is None and request.book_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either session_id or book_id must be provided",
        )
    
    # Get or create session
    if request.session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == request.session_id,
                ChatSession.user_id == user_id,
            )
        )
        session = result.scalar_one_or_none()
        
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        book_id = session.book_id
    else:
        book_id = request.book_id
        # Get or create learning state and session
        learning_state = await _get_or_create_learning_state(db, user_id, book_id)
        
        # Find existing session or create new
        session_result = await db.execute(
            select(ChatSession)
            .where(ChatSession.book_id == book_id)
            .where(ChatSession.user_id == user_id)
            .where(ChatSession.is_active == True)
            .order_by(ChatSession.created_at.desc())
        )
        session = session_result.scalar()
        
        if session is None:
            session = ChatSession(
                user_id=user_id,
                learning_state_id=learning_state.id,
                book_id=book_id,
                chapter_context=learning_state.current_chapter,
                session_type="learning",
            )
            db.add(session)
            await db.flush()
    
    # Save user message
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.message,
        chapter_at_time=session.chapter_context,
    )
    db.add(user_message)
    
    # Get learning state
    result = await db.execute(
        select(LearningState).where(LearningState.id == session.learning_state_id)
    )
    learning_state = result.scalar_one()
    
    # Get API key
    from app.services.api_key_service import APIKeyService
    api_key_service = APIKeyService(db)
    api_key = None
    try:
        api_key = await api_key_service.get_api_key_for_user(user_id)
    except ValueError:
        pass
    
    # Build current state from LearningState
    current_state = await _build_state_from_learning_state(learning_state, api_key, db)
    
    # CRITICAL: Load conversation history from chat messages for context
    # This allows the teacher to know what was already taught
    messages_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at)
    )
    history_messages = messages_result.scalars().all()
    conversation_history = [
        {"role": m.role, "content": m.content}
        for m in history_messages
    ]
    current_state["conversation_history"] = conversation_history
    
    # Use actual message count from the session (not study time)
    current_state["session_message_count"] = session.message_count or 0
    
    # Check if we're in config gathering phase
    phase = _determine_phase_from_state(learning_state)
    
    if phase == "config_gathering":
        # Use the planner agent for config gathering
        from app.agents.planner import gather_config_conversationally, PlannerAgent
        from app.models.book import Book
        
        # Get book info
        book_result = await db.execute(select(Book).where(Book.id == book_id))
        book = book_result.scalar_one_or_none()
        
        # Get conversation history
        messages_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
        )
        history_messages = messages_result.scalars().all()
        conversation_history = [
            {"role": m.role, "content": m.content}
            for m in history_messages
        ]
        
        # Process through planner agent
        result = await gather_config_conversationally(
            book_id=str(book_id),
            book_title=book.title if book else "Learning Material",
            user_id=str(user_id),
            total_chapters=book.total_chapters if book else 0,
            user_message=request.message,
            conversation_history=conversation_history,
        )
        
        response_data = {
            "response": result["response"],
            "phase": "config_gathering",
            "agent_name": "PlannerAgent",
            "state": current_state,
        }
        
        # If config is complete, generate the plan and transition to teaching
        if result.get("config_complete") and result.get("config"):
            config = result["config"]
            
            # Update learning state with config
            learning_state.professor_level = config["learning_level"]
            
            # Create the learning plan
            planner = PlannerAgent(api_key=api_key)
            plan_state = {
                **current_state,
                "target_days": config["target_days"],
                "preferred_study_time_minutes": config["daily_minutes"],
                "professor_level": config["learning_level"],
                "quiz_frequency": config["quiz_frequency"],
            }
            
            plan_result = await planner.process(plan_state)
            # PlanResult is a dataclass with plan_data, summary, plan_accepted
            plan = plan_result.plan_data if hasattr(plan_result, 'plan_data') else plan_result.get("learning_plan", {})
            
            # Save the plan
            learning_state.learning_plan = plan
            learning_state.quiz_mode = "none"  # Ready for teaching
            
            # Set current_chapter based on Day 1's content
            days = plan.get("days", [])
            if days:
                day_1 = days[0]
                items = day_1.get("items", [])
                if items:
                    # Get the first chapter from Day 1
                    first_chapter = items[0].get("chapter_number", 1)
                    learning_state.current_chapter = first_chapter
            
            # Also sync to LearningPlan table
            await _sync_learning_plan_record(db, learning_state, plan)
            
            # Add plan presentation to response
            plan_overview = plan.get("overview", "Your personalized learning plan is ready!")
            total_days = plan.get("total_days", config["target_days"])
            
            response_data["response"] += f"\n\n🎉 **Your Learning Plan is Ready!**\n\n{plan_overview}\n\n📅 **{total_days} days** to complete\n⏱️ **{config['daily_minutes']} minutes** per day\n📚 **{config['learning_level'].capitalize()}** level content\n\nReady to start learning? Just say 'let's begin' or ask me anything!"
            response_data["phase"] = "teaching"
            response_data["state"]["phase"] = "teaching"  # Ensure phase is in state for _update_learning_state
            response_data["state"]["plan_data"] = plan
            response_data["state"]["plan_accepted"] = True
    else:
        # Process through agent-driven system
        from app.langgraph.graph import process_message
        
        response_data = await process_message(
            user_id=str(user_id),
            session_id=str(session.id),
            book_id=str(book_id),
            message=request.message,
            current_state=current_state,
        )
    
    # Update learning state from response
    new_state = response_data.get("state", {})
    await _update_learning_state(db, learning_state, new_state)
    
    # Update last_active_at (critical for inactivity detection)
    learning_state.last_active_at = datetime.utcnow()
    
    # Save assistant message
    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=response_data.get("response", ""),
        agent_name=response_data.get("agent_name", "Professor"),
        chapter_at_time=new_state.get("current_chapter", learning_state.current_chapter),
        is_quiz_question=response_data.get("response_type") == "quiz_question",
        latency_ms=int((time.time() - start_time) * 1000),
    )
    db.add(assistant_message)
    
    # Update session
    session.message_count += 2
    session.last_message_at = datetime.utcnow()
    session.chapter_context = new_state.get("current_chapter", session.chapter_context)
    
    await db.commit()
    
    latency_ms = int((time.time() - start_time) * 1000)
    
    logger.info(
        "chat_completed",
        user_id=str(user_id),
        session_id=str(session.id),
        phase=response_data.get("phase"),
        latency_ms=latency_ms,
    )
    
    return ChatResponse(
        message=sanitize_response_text(response_data.get("response", "")),
        session_id=session.id,
        phase=response_data.get("phase", "teaching"),
        chapter=new_state.get("current_chapter", learning_state.current_chapter),
        agent_name=response_data.get("agent_name", "Professor"),
        latency_ms=latency_ms,
    )


# ============================================================================
# SESSION INITIALIZATION
# ============================================================================

@router.get("/init/{book_id}", response_model=InitSessionResponse)
async def init_or_get_session(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Initialize or get existing learning session for a book.
    
    Returns the session with messages and current state.
    If no config exists, starts the agentic config gathering conversation.
    """
    from app.models.book import Book
    from app.services.progress import get_progress_summary
    
    # Get book
    book_result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = book_result.scalar_one_or_none()
    
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )
    
    # Check if book processing is complete
    if book.processing_status not in ["completed", "ready_for_planning", "ready"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Book is still processing: {book.processing_status}",
        )
    
    # Get or create learning state
    learning_state = await _get_or_create_learning_state(db, user_id, book_id)
    
    # Get or create session
    sessions_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.book_id == book_id, ChatSession.user_id == user_id)
        .options(selectinload(ChatSession.messages))
        .order_by(ChatSession.created_at.desc())
    )
    session = sessions_result.scalar()
    
    is_new_session = False
    if session is None:
        is_new_session = True
        # Create new session
        session = ChatSession(
            user_id=user_id,
            learning_state_id=learning_state.id,
            book_id=book_id,
            chapter_context=learning_state.current_chapter,
            session_type="learning",
        )
        db.add(session)
        await db.flush()
        
        # Reload with messages
        sessions_result = await db.execute(
            select(ChatSession)
            .where(ChatSession.id == session.id)
            .options(selectinload(ChatSession.messages))
        )
        session = sessions_result.scalar()
    
    # Check if a real plan (with days) exists — pending_config alone doesn't count
    has_config = _has_real_plan(learning_state.learning_plan)
    
    # Determine phase - if no real plan, we MUST be in config_gathering
    if not has_config:
        phase = "config_gathering"
        
        # Check if we need to generate a new config gathering greeting
        # (only if no PlannerAgent messages exist yet)
        has_planner_greeting = any(
            m.role == "assistant" and m.agent_name in ("PlannerAgent", "Professor")
            for m in session.messages
        )
        
        if not has_planner_greeting:
            # Generate planner greeting for config gathering
            from app.agents.planner import start_config_conversation
            
            greeting = await start_config_conversation(
                book_id=str(book_id),
                book_title=book.title,
                user_id=str(user_id),
                total_chapters=book.total_chapters or 0,
            )
            
            # Save greeting message
            greeting_message = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=greeting,
                agent_name="PlannerAgent",
                chapter_at_time=1,
            )
            db.add(greeting_message)
            await db.flush()
        
        # Mark as config gathering phase
        learning_state.quiz_mode = "config"
        if hasattr(learning_state, 'current_phase'):
            learning_state.current_phase = "config_gathering"
        
        # Commit to ensure message is saved
        await db.commit()
    else:
        phase = _determine_phase(learning_state, session)
    
    # Build progress summary
    state_dict = await _build_state_from_learning_state(learning_state, None, db)
    progress = get_progress_summary(state_dict)
    
    # Final reload of session to ensure we have all messages (force fresh load)
    sessions_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session.id)
        .options(selectinload(ChatSession.messages))
        .execution_options(populate_existing=True)
    )
    session = sessions_result.scalar()
    
    # Check for greeting
    has_greeting = any(
        m.role == "assistant" and m.agent_name in ["Professor", "GreetingAgent", "PlannerAgent"]
        for m in session.messages
    )
    
    return InitSessionResponse(
        session_id=session.id,
        phase=phase,
        current_chapter=learning_state.current_chapter,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                agent_name=m.agent_name,
                is_quiz_question=m.is_quiz_question,
                quiz_answer_correct=m.quiz_answer_correct,
                created_at=m.created_at,
            )
            for m in sorted(session.messages, key=lambda x: x.created_at)
        ],
        has_greeting=has_greeting,
        book_title=book.title,
        total_chapters=book.total_chapters or 0,
        progress=progress,
    )


# ============================================================================
# OTHER ENDPOINTS
# ============================================================================

@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    book_id: Optional[UUID] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List chat sessions for the user."""
    conditions = [ChatSession.user_id == user_id]
    
    if book_id:
        conditions.append(ChatSession.book_id == book_id)
    
    result = await db.execute(
        select(ChatSession)
        .where(and_(*conditions))
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    
    return sessions


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get session details with messages."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .options(selectinload(ChatSession.messages))
    )
    session = result.scalar_one_or_none()
    
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    return SessionDetailResponse(
        id=session.id,
        book_id=session.book_id,
        chapter_context=session.chapter_context,
        session_type=session.session_type,
        is_active=session.is_active,
        message_count=session.message_count,
        created_at=session.created_at,
        last_message_at=session.last_message_at,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                agent_name=m.agent_name,
                is_quiz_question=m.is_quiz_question,
                quiz_answer_correct=m.quiz_answer_correct,
                created_at=m.created_at,
            )
            for m in sorted(session.messages, key=lambda x: x.created_at)
        ],
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    
    await db.delete(session)
    await db.commit()
    
    return {"message": "Session deleted"}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def _get_or_create_learning_state(
    db: AsyncSession,
    user_id: UUID,
    book_id: UUID,
) -> LearningState:
    """Get or create a learning state for the user's book."""
    # Try cache first
    cache_key = f"learning_state:{user_id}:{book_id}"
    
    result = await db.execute(
        select(LearningState)
        .where(LearningState.user_id == user_id)
        .where(LearningState.book_id == book_id)
        .order_by(LearningState.created_at.desc())
        .limit(1)
    )
    learning_state = result.scalars().first()
    
    if learning_state is None:
        # Get book info for defaults
        from app.models.book import Book
        from app.models.learning_config import LearningConfig
        
        book_result = await db.execute(select(Book).where(Book.id == book_id))
        book = book_result.scalar_one_or_none()
        
        config_result = await db.execute(
            select(LearningConfig).where(LearningConfig.book_id == book_id)
        )
        config = config_result.scalar_one_or_none()
        
        learning_state = LearningState(
            user_id=user_id,
            book_id=book_id,
            current_chapter=1,
            completed_chapters=[],
            professor_level=config.learning_level if config else "intermediate",
            motivation_score=1.0,
            attention_score=1.0,
            comprehension_score=1.0,
            total_study_time_minutes=0,
        )
        db.add(learning_state)
        await db.flush()
        
        # Invalidate cache since we created new state
        await cache.delete(cache_key)
    
    return learning_state


async def _get_cached_book_info(
    db: AsyncSession,
    book_id: UUID,
) -> Optional[dict]:
    """Get book info with caching."""
    from app.models.book import Book
    
    cache_key = f"book_info:{book_id}"
    cached = await cache.get(cache_key)
    if cached:
        return cached
    
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    
    if book:
        book_info = {
            "id": str(book.id),
            "title": book.title,
            "total_chapters": book.total_chapters,
            "processing_status": book.processing_status,
        }
        await cache.set(cache_key, book_info, 3600)  # Cache for 1 hour
        return book_info
    
    return None


async def _build_state_from_learning_state(
    learning_state: LearningState,
    api_key: Optional[str],
    db: AsyncSession,
) -> dict:
    """Build ProfessorState dict from LearningState model."""
    from app.models.book import Book, BookChapter
    
    # Get book info for total_chapters
    book_result = await db.execute(
        select(Book).where(Book.id == learning_state.book_id)
    )
    book = book_result.scalar_one_or_none()
    total_chapters = book.total_chapters if book else 1
    book_title = book.title if book else "Learning Material"
    
    # Load chapter titles for plan generation
    chapter_titles: list = []
    try:
        ch_result = await db.execute(
            select(BookChapter)
            .where(BookChapter.book_id == learning_state.book_id)
            .order_by(BookChapter.chapter_number)
        )
        chapters_rows = ch_result.scalars().all()
        chapter_titles = [
            c.title or f"Chapter {c.chapter_number}" for c in chapters_rows
        ]
    except Exception as ch_err:
        logger.warning("load_chapter_titles_failed", error=str(ch_err))
    
    raw_plan = learning_state.learning_plan
    plan_data = _resolve_plan_data(raw_plan) or {}
    pending_cfg = _extract_pending_config(raw_plan)
    target_days, daily_minutes, quiz_frequency = _resolve_config_values(pending_cfg)

    total_days = plan_data.get("total_days", 1) if plan_data else 1
    current_day = getattr(learning_state, 'current_day', 1) or 1
    day_title = ""
    if plan_data and "days" in plan_data:
        for day_data in plan_data["days"]:
            if day_data.get("day") == current_day:
                day_title = day_data.get("day_title", f"Day {current_day}")
                break
    
    return {
        "user_id": str(learning_state.user_id),
        "book_id": str(learning_state.book_id),
        "book_title": book_title,
        "total_chapters": total_chapters,
        "chapter_titles": chapter_titles,
        "current_chapter": learning_state.current_chapter,
        "completed_chapters": list(learning_state.completed_chapters or []),
        "current_day": current_day,
        "total_days": total_days,
        "completed_days": list(getattr(learning_state, 'completed_days', []) or []),
        "day_title": day_title,
        "learning_level": _resolve_learning_level(
            pending_cfg, professor_level=learning_state.professor_level,
        ),
        "target_days": target_days,
        "daily_minutes": daily_minutes,
        "quiz_frequency": quiz_frequency,
        "motivation_score": learning_state.motivation_score or 1.0,
        "attention_score": learning_state.attention_score or 1.0,
        "comprehension_score": learning_state.comprehension_score or 1.0,
        "total_study_time_minutes": learning_state.total_study_time_minutes or 0,
        "topics_covered_this_chapter": list(learning_state.pending_topics or []),
        "day_topics_covered": list(getattr(learning_state, 'day_topics_covered', []) or []),
        "session_message_count": 0,
        "quiz_questions": learning_state.pending_quiz_questions.get("quiz_questions", []) if learning_state.pending_quiz_questions else [],
        "quiz_current_index": learning_state.pending_quiz_questions.get("quiz_current_index", 0) if learning_state.pending_quiz_questions else 0,
        "quiz_scores": learning_state.pending_quiz_questions.get("quiz_scores", []) if learning_state.pending_quiz_questions else [],
        "quiz_passed": learning_state.pending_quiz_questions.get("quiz_passed") if learning_state.pending_quiz_questions else None,
        "awaiting_quiz_decision": learning_state.pending_quiz_questions.get("awaiting_quiz_decision", False) if learning_state.pending_quiz_questions else False,
        "plan_data": plan_data or None,
        "plan_accepted": _has_real_plan(raw_plan),
        "api_key": api_key,
        "phase": _determine_phase_from_state(learning_state),
    }


def _determine_phase(learning_state: LearningState, session: ChatSession) -> str:
    """Determine current phase based on state."""
    # Check if we have messages
    if not session.messages:
        return "config_gathering"
    
    # Check if a real plan (with days) exists
    if not _has_real_plan(learning_state.learning_plan):
        return "config_gathering" if len(session.messages) <= 1 else "planning"
    
    # Check if in quiz
    if learning_state.pending_quiz_questions:
        return "quiz"
    
    return "teaching"


def _determine_phase_from_state(learning_state: LearningState) -> str:
    """Determine phase from learning state alone."""
    # Use current_phase field if available (new field)
    if hasattr(learning_state, 'current_phase') and learning_state.current_phase:
        return learning_state.current_phase
    
    # Fallback to quiz_mode for backward compatibility
    quiz_mode = learning_state.quiz_mode
    
    if quiz_mode == "config":
        return "config_gathering"
    
    if quiz_mode == "ch_transition":
        return "chapter_transition"
    
    if quiz_mode == "await_chapter":
        return "awaiting_chapter_start"
    
    if quiz_mode == "quiz_feedback":
        return "quiz_feedback"
    
    if quiz_mode in ["chapter_quiz", "attention_quiz"]:
        return "quiz"
    
    # Check if we're in planning phase (plan exists but not accepted)
    if quiz_mode == "planning":
        return "planning"
    
    # Only consider it "has a plan" if there are actual days in the plan,
    # not just pending_config stored during config gathering.
    if not _has_real_plan(learning_state.learning_plan):
        return "config_gathering"
    
    if learning_state.pending_quiz_questions:
        return "quiz"
    
    return "teaching"


async def _update_learning_state(
    db: AsyncSession,
    learning_state: LearningState,
    new_state: dict,
) -> None:
    """Update learning state from response state."""
    # Store learning config if provided (from config_gathering phase)
    if "learning_config" in new_state or "target_days" in new_state:
        from app.services.freemium_service import validate_and_cap_plan_days
        
        # Get requested days
        requested_days = new_state.get("target_days", 30)
        
        # Validate and cap based on user's subscription tier
        # Free tier: max 30 days, BYOK/Pro: max 90 days
        actual_days, freemium_warning = await validate_and_cap_plan_days(
            db, learning_state.user_id, requested_days
        )
        
        if freemium_warning:
            logger.info(
                "plan_days_capped_by_freemium",
                user_id=str(learning_state.user_id),
                requested_days=requested_days,
                actual_days=actual_days,
            )
        
        # Store config in learning_plan for persistence
        config_data = {
            "target_days": actual_days,  # Use capped value
            "daily_minutes": new_state.get("daily_minutes", 30),
            "learning_level": new_state.get("learning_level", "intermediate"),
            "professor_level": new_state.get("professor_level", "intermediate"),
            "quiz_frequency": new_state.get("quiz_frequency", "after_each_chapter"),
            "freemium_warning": freemium_warning,  # Store warning to show user
        }
        # Store in learning_plan as pending_config until plan is generated
        if not learning_state.learning_plan:
            learning_state.learning_plan = {"pending_config": config_data}
        elif isinstance(learning_state.learning_plan, dict):
            learning_state.learning_plan["pending_config"] = config_data
    
    # Update basic fields
    if "current_chapter" in new_state:
        learning_state.current_chapter = new_state["current_chapter"]
    
    if "completed_chapters" in new_state:
        learning_state.completed_chapters = new_state["completed_chapters"]
    
    # Day tracking
    if "current_day" in new_state:
        learning_state.current_day = new_state["current_day"]
    
    if "completed_days" in new_state:
        learning_state.completed_days = new_state["completed_days"]
    
    if "day_topics_covered" in new_state:
        learning_state.day_topics_covered = new_state["day_topics_covered"]
    
    if "motivation_score" in new_state:
        learning_state.motivation_score = new_state["motivation_score"]
    
    if "attention_score" in new_state:
        learning_state.attention_score = new_state["attention_score"]
    
    if "comprehension_score" in new_state:
        learning_state.comprehension_score = new_state["comprehension_score"]
    
    if "total_study_time_minutes" in new_state:
        learning_state.total_study_time_minutes = new_state["total_study_time_minutes"]
    
    phase = new_state.get("phase", "teaching")
    plan_data = new_state.get("plan_data")
    if plan_data and _has_real_plan(plan_data):
        learning_state.learning_plan = plan_data
        await _sync_learning_plan_record(db, learning_state, plan_data)
    elif phase in ("config_gathering", "planning") and not _has_real_plan(plan_data):
        from app.services.plan_state import build_pending_plan_blob
        learning_state.learning_plan = build_pending_plan_blob(
            new_state, learning_state.learning_plan,
        )
    
    # Update topics covered
    if "topics_covered_this_chapter" in new_state:
        learning_state.pending_topics = new_state["topics_covered_this_chapter"]
    
    # Update phase tracking
    # Update current_phase field (new field)
    if hasattr(learning_state, 'current_phase'):
        learning_state.current_phase = phase
    
    # Also update quiz_mode for backward compatibility
    if new_state.get("quiz_questions"):
        learning_state.pending_quiz_questions = {
            "quiz_questions": new_state.get("quiz_questions", []),
            "quiz_current_index": new_state.get("quiz_current_index", 0),
            "quiz_scores": new_state.get("quiz_scores", []),
            "quiz_passed": new_state.get("quiz_passed"),
            "awaiting_quiz_decision": new_state.get("awaiting_quiz_decision", False),
        }
        learning_state.quiz_mode = "chapter_quiz"
    elif phase == "quiz_feedback":
        learning_state.quiz_mode = "quiz_feedback"
    elif phase == "chapter_transition":
        learning_state.quiz_mode = "ch_transition"  # Shortened to fit VARCHAR(20)
        learning_state.pending_quiz_questions = None
    elif phase == "awaiting_chapter_start":
        learning_state.quiz_mode = "await_chapter"  # Shortened to fit VARCHAR(20)
        learning_state.pending_quiz_questions = None
    elif phase == "config_gathering":
        learning_state.quiz_mode = "config"
        learning_state.pending_quiz_questions = None
    elif phase == "planning":
        learning_state.quiz_mode = "planning"
        learning_state.pending_quiz_questions = None
    elif phase in ["quiz"]:
        # Phase is quiz but no questions yet - mark as pending quiz
        learning_state.quiz_mode = "chapter_quiz"
    else:
        # Clear quiz state when not in quiz/planning
        learning_state.pending_quiz_questions = None
        learning_state.quiz_mode = "none"


async def _sync_learning_plan_record(
    db: AsyncSession,
    learning_state: LearningState,
    plan_data: dict,
) -> None:
    """
    Sync the plan data to the LearningPlan table for the plan page.
    
    This ensures the plan generated through the chat flow is also
    available via the /api/planning/{book_id}/current endpoint.
    """
    from app.models.learning_config import LearningConfig, LearningPlan
    from app.models.book import Book
    
    try:
        # Get learning config
        config_result = await db.execute(
            select(LearningConfig).where(LearningConfig.book_id == learning_state.book_id)
        )
        config = config_result.scalar_one_or_none()
        
        if not config:
            logger.warning("no_config_for_plan_sync", book_id=str(learning_state.book_id))
            return
        
        # Get book for title
        book_result = await db.execute(
            select(Book).where(Book.id == learning_state.book_id)
        )
        book = book_result.scalar_one_or_none()
        book_title = book.title if book else "Learning Material"
        
        # Check for existing plan
        existing_plan_result = await db.execute(
            select(LearningPlan)
            .where(LearningPlan.book_id == learning_state.book_id)
            .where(LearningPlan.user_id == learning_state.user_id)
            .order_by(LearningPlan.version.desc())
        )
        existing_plan = existing_plan_result.scalar_one_or_none()
        
        # Generate summary
        total_days = plan_data.get("total_days", len(plan_data.get("days", [])))
        daily_minutes = plan_data.get("daily_minutes", 30)
        overview = plan_data.get("overview", "")
        
        summary = f"""📚 **Learning Plan for {book_title}**

**Duration:** {total_days} days
**Daily Study Time:** {daily_minutes} minutes

{overview}
"""
        
        if existing_plan:
            # Update existing plan
            existing_plan.plan_data = plan_data
            existing_plan.plan_summary = summary  # DB column is plan_summary
            existing_plan.status = "accepted"  # Chat flow means user accepted
            existing_plan.accepted_at = datetime.utcnow()
            existing_plan.version += 1
        else:
            # Create new plan
            new_plan = LearningPlan(
                config_id=config.id,
                user_id=learning_state.user_id,
                book_id=learning_state.book_id,
                plan_data=plan_data,
                plan_summary=summary,  # DB column is plan_summary
                version=1,
                status="accepted",
                accepted_at=datetime.utcnow(),
            )
            db.add(new_plan)
        
        # Update config flags
        config.plan_generated = True
        config.plan_accepted = True
        config.plan_accepted_at = datetime.utcnow()
        
        logger.info(
            "learning_plan_synced",
            book_id=str(learning_state.book_id),
            user_id=str(learning_state.user_id),
        )
        
    except Exception as e:
        logger.warning("plan_sync_failed", error=str(e))
