"""Session management activities for learning workflows."""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from temporalio import activity
import redis.asyncio as redis

from app.config import settings
from app.logs.logger import get_logger
from app.models.chat import ChatSession, ChatMessage
from app.models.learning import LearningState

logger = get_logger(__name__)

# Database setup
_engine = None
_session_factory = None
_redis_client = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncSession:
    """Get a database session for activities."""
    factory = get_session_factory()
    return factory()


async def get_redis_client():
    """Get Redis client for message queue."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url)
    return _redis_client


@activity.defn
async def send_professor_message(
    session_id: str,
    content: str,
    message_type: str = "teaching",
) -> Dict[str, Any]:
    """
    Send a message from the professor to the student.
    
    This stores the message in the database and publishes to Redis
    for real-time delivery.
    
    Args:
        session_id: The chat session ID
        content: The message content
        message_type: Type of message (teaching, question, feedback, etc.)
        
    Returns:
        Dict with message details
    """
    activity.logger.info(f"Sending professor message to session {session_id}")
    
    async with await get_db_session() as db:
        try:
            # Get session
            result = await db.execute(
                select(ChatSession).where(ChatSession.id == UUID(session_id))
            )
            session = result.scalar_one_or_none()
            
            if not session:
                return {"success": False, "error": "Session not found"}
            
            # Create message record
            message = ChatMessage(
                session_id=UUID(session_id),
                role="assistant",
                content=content,
                agent_name="Professor",
                chapter_at_time=session.chapter_context,
                is_quiz_question=message_type in ["quiz_question", "question"],
                latency_ms=0,
            )
            db.add(message)
            
            # Update session
            session.message_count += 1
            session.last_message_at = datetime.utcnow()
            
            await db.commit()
            
            # Publish to Redis for real-time delivery
            redis_client = await get_redis_client()
            await redis_client.publish(
                f"session:{session_id}:messages",
                json.dumps({
                    "id": str(message.id),
                    "role": "assistant",
                    "content": content,
                    "message_type": message_type,
                    "timestamp": datetime.utcnow().isoformat(),
                })
            )
            
            # Also store in a list for polling
            await redis_client.lpush(
                f"session:{session_id}:pending",
                json.dumps({
                    "id": str(message.id),
                    "role": "assistant",
                    "content": content,
                    "message_type": message_type,
                    "timestamp": datetime.utcnow().isoformat(),
                })
            )
            await redis_client.expire(f"session:{session_id}:pending", 3600)  # 1 hour TTL
            
            logger.info(
                "professor_message_sent",
                session_id=session_id,
                message_type=message_type,
                content_length=len(content),
            )
            
            return {
                "success": True,
                "message_id": str(message.id),
                "session_id": session_id,
                "message_type": message_type,
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("send_professor_message_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def get_pending_student_response(
    session_id: str,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """
    Get any pending student response for a session.
    
    This checks Redis for student responses that were submitted
    while the workflow was waiting.
    
    Args:
        session_id: The chat session ID
        timeout_seconds: How long to wait (not used - blocking done in workflow)
        
    Returns:
        Dict with response if available, or None
    """
    activity.logger.info(f"Checking for student response in session {session_id}")
    
    try:
        redis_client = await get_redis_client()
        
        # Check for pending response
        response = await redis_client.rpop(f"session:{session_id}:student_responses")
        
        if response:
            data = json.loads(response)
            return {
                "success": True,
                "has_response": True,
                "response": data.get("content"),
                "timestamp": data.get("timestamp"),
            }
        
        return {
            "success": True,
            "has_response": False,
            "response": None,
        }
        
    except Exception as e:
        logger.exception("get_student_response_failed", error=str(e))
        return {"success": False, "has_response": False, "error": str(e)}


@activity.defn
async def save_session_state(
    user_id: str,
    book_id: str,
    session_id: str,
    current_chapter: int,
    additional_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Save the current session state for later resume.
    
    Args:
        user_id: The student's ID
        book_id: The book's ID
        session_id: The session ID
        current_chapter: Current chapter number
        additional_state: Any additional state to preserve
        
    Returns:
        Dict with save status
    """
    activity.logger.info(f"Saving session state for user {user_id}")
    
    async with await get_db_session() as db:
        try:
            # Update learning state
            result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            learning_state = result.scalar_one_or_none()
            
            if learning_state:
                await db.execute(
                    update(LearningState)
                    .where(LearningState.id == learning_state.id)
                    .values(
                        current_chapter=current_chapter,
                        last_active_at=datetime.utcnow(),
                        last_session_summary=f"Paused during Chapter {current_chapter}",
                        updated_at=datetime.utcnow(),
                    )
                )
            
            # Store additional state in Redis
            if additional_state:
                redis_client = await get_redis_client()
                await redis_client.setex(
                    f"session:{session_id}:state",
                    86400,  # 24 hour TTL
                    json.dumps(additional_state),
                )
            
            await db.commit()
            
            logger.info(
                "session_state_saved",
                user_id=user_id,
                session_id=session_id,
                chapter=current_chapter,
            )
            
            return {
                "success": True,
                "user_id": user_id,
                "session_id": session_id,
                "chapter": current_chapter,
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("save_session_state_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def load_session_state(
    user_id: str,
    book_id: str,
) -> Dict[str, Any]:
    """
    Load saved session state for resuming.
    
    Args:
        user_id: The student's ID
        book_id: The book's ID
        
    Returns:
        Dict with saved state
    """
    activity.logger.info(f"Loading session state for user {user_id}")
    
    async with await get_db_session() as db:
        try:
            # Get learning state
            result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            learning_state = result.scalar_one_or_none()
            
            if not learning_state:
                return {
                    "success": True,
                    "has_state": False,
                    "current_chapter": 1,
                    "completed_chapters": [],
                }
            
            return {
                "success": True,
                "has_state": True,
                "current_chapter": learning_state.current_chapter,
                "completed_chapters": list(learning_state.completed_chapters or []),
                "motivation_score": learning_state.motivation_score,
                "last_active_at": learning_state.last_active_at.isoformat() if learning_state.last_active_at else None,
            }
            
        except Exception as e:
            logger.exception("load_session_state_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def create_learning_session(
    user_id: str,
    book_id: str,
) -> Dict[str, Any]:
    """
    Create a new learning session.
    
    Args:
        user_id: The student's ID
        book_id: The book's ID
        
    Returns:
        Dict with session details
    """
    activity.logger.info(f"Creating learning session for user {user_id}")
    
    async with await get_db_session() as db:
        try:
            # Get or create learning state
            result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            learning_state = result.scalar_one_or_none()
            
            if not learning_state:
                learning_state = LearningState(
                    user_id=UUID(user_id),
                    book_id=UUID(book_id),
                    current_chapter=1,
                    completed_chapters=[],
                )
                db.add(learning_state)
                await db.flush()
            
            # Create chat session
            session = ChatSession(
                user_id=UUID(user_id),
                learning_state_id=learning_state.id,
                book_id=UUID(book_id),
                chapter_context=learning_state.current_chapter,
                session_type="learning",
            )
            db.add(session)
            await db.commit()
            
            logger.info(
                "learning_session_created",
                user_id=user_id,
                session_id=str(session.id),
                chapter=learning_state.current_chapter,
            )
            
            return {
                "success": True,
                "session_id": str(session.id),
                "user_id": user_id,
                "book_id": book_id,
                "current_chapter": learning_state.current_chapter,
                "completed_chapters": list(learning_state.completed_chapters or []),
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("create_learning_session_failed", error=str(e))
            return {"success": False, "error": str(e)}
