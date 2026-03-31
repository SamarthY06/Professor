"""Voice transcription API -- Speech-to-Text via OpenAI Whisper."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.dependencies import get_current_user_id
from app.logs.logger import get_logger
from app.services.api_key_service import APIKeyService

logger = get_logger(__name__)

router = APIRouter()

MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_AUDIO_PREFIXES = (
    "audio/",
    "video/webm",  # some browsers report webm as video/webm
)


def _is_audio_content_type(content_type: str | None) -> bool:
    if not content_type:
        return True  # allow if browser didn't set it
    base = content_type.split(";")[0].strip().lower()
    return any(base.startswith(prefix) for prefix in ALLOWED_AUDIO_PREFIXES)


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Transcribe an audio recording to text using OpenAI Whisper.

    Accepts audio from the browser MediaRecorder (webm/mp4/wav).
    Returns the transcribed English text for the user to review and send.
    """
    if not _is_audio_content_type(file.content_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported format: {file.content_type}. Send an audio file.",
        )

    audio_bytes = await file.read()

    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file too large ({len(audio_bytes)} bytes). Maximum is {MAX_AUDIO_SIZE_BYTES} bytes.",
        )

    if len(audio_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is too small or empty.",
        )

    key_service = APIKeyService(db)
    api_key = await key_service.get_api_key_for_user(user_id)

    try:
        import openai

        client = openai.OpenAI(api_key=api_key)

        filename = file.filename or "recording.webm"
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_bytes),
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
            detail="Invalid OpenAI API key. Check your API key in settings.",
        )
    except openai.RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="OpenAI rate limit reached. Please try again in a moment.",
        )
    except Exception as e:
        logger.exception("voice_transcription_failed", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transcription failed. Please try again.",
        )
