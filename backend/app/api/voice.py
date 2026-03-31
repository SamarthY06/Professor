"""Voice transcription API -- Speech-to-Text via OpenAI Whisper."""

from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.services.api_key_service import APIKeyService

logger = get_logger(__name__)

router = APIRouter()

MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
READ_CHUNK_SIZE = 64 * 1024  # 64 KB chunks for streaming read
RATE_LIMIT_MAX = 10  # max transcriptions per window
RATE_LIMIT_WINDOW_SECONDS = 60

ALLOWED_AUDIO_PREFIXES = (
    "audio/",
    "video/webm",
)


def _is_audio_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    base = content_type.split(";")[0].strip().lower()
    return any(base.startswith(prefix) for prefix in ALLOWED_AUDIO_PREFIXES)


async def _check_voice_rate_limit(user_id: UUID, request: Request) -> None:
    """Redis-based per-user rate limit for voice transcription."""
    try:
        pool = request.app.state.redis_pool if hasattr(request.app.state, "redis_pool") else None
        if not pool:
            pool = redis.from_url(settings.redis_url, decode_responses=True)
        r = redis.Redis(connection_pool=pool)
        key = f"voice_rate:{user_id}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        if count > RATE_LIMIT_MAX:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Voice transcription rate limit exceeded. Please wait a minute.",
            )
    except HTTPException:
        raise
    except Exception:
        pass


async def _read_audio_with_limit(file: UploadFile) -> bytes:
    """Read uploaded audio in chunks, aborting early if over size limit."""
    total = 0
    chunks: list[bytes] = []
    while True:
        chunk = await file.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_AUDIO_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Audio file too large. Maximum is 10 MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/transcribe")
async def transcribe_audio(
    request: Request,
    file: UploadFile = File(...),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Transcribe an audio recording to text using OpenAI Whisper.

    Accepts audio from the browser MediaRecorder (webm/mp4/wav).
    Returns the transcribed English text for the user to review and send.
    """
    await _check_voice_rate_limit(user_id, request)

    if not _is_audio_content_type(file.content_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported format. Send an audio file (webm, mp4, wav, ogg).",
        )

    audio_bytes = await _read_audio_with_limit(file)

    if len(audio_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is too small or empty.",
        )

    key_service = APIKeyService(db)
    api_key = await key_service.get_api_key_for_user(user_id)

    try:
        import openai

        client = openai.OpenAI(api_key=api_key, timeout=30.0)

        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=("recording.webm", audio_bytes),
            language="en",
        )

        text = transcription.text.strip()

        logger.info(
            "voice_transcription_success",
            user_id=str(user_id),
            audio_size_bytes=len(audio_bytes),
            text_length=len(text),
        )

        return {"text": text}

    except openai.AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key. Check your API key in settings.",
        )
    except openai.RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit reached. Please try again in a moment.",
        )
    except Exception as e:
        logger.exception("voice_transcription_failed", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transcription failed. Please try again.",
        )
