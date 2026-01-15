"""Intent detection service using LLM - NO hardcoded keyword matching."""

from typing import Literal, Optional
from openai import AsyncOpenAI
import json

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)

Intent = Literal[
    "accept",      # User agrees/accepts (plan, answer, etc.)
    "reject",      # User disagrees/rejects
    "question",    # User is asking a question
    "doubt",       # User has a doubt about the content
    "no_doubt",    # User has no doubts
    "continue",    # User wants to continue
    "pause",       # User wants to pause
    "unclear"      # Intent is unclear
]


async def detect_intent(
    message: str,
    context: str,
    api_key: Optional[str] = None,
) -> dict:
    """
    Use LLM to detect user intent - NO keyword matching.
    
    Args:
        message: User's message
        context: Current conversation context (e.g., "professor asked about plan")
        api_key: OpenAI API key
        
    Returns:
        Dict with intent and confidence
    """
    client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
    
    prompt = f"""Analyze the user's message and determine their intent.

Context: {context}
User message: "{message}"

Possible intents:
- "accept": User agrees, accepts, or says yes to something
- "reject": User disagrees, declines, or says no
- "question": User is asking a question about the content
- "doubt": User expresses confusion or needs clarification
- "no_doubt": User confirms they have no questions/doubts
- "continue": User wants to proceed/continue learning
- "pause": User wants to stop or take a break
- "unclear": Cannot determine intent

Respond with JSON only:
{{"intent": "<intent>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>"}}"""

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model_mini,
            messages=[
                {"role": "system", "content": "You analyze user intent. Return JSON only."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        
        result = json.loads(response.choices[0].message.content)
        logger.info("intent_detected", intent=result.get("intent"), confidence=result.get("confidence"))
        return result
        
    except Exception as e:
        logger.exception("intent_detection_failed", error=str(e))
        return {"intent": "unclear", "confidence": 0.0, "reasoning": "Error in detection"}


async def is_positive_response(message: str, context: str, api_key: Optional[str] = None) -> bool:
    """Check if user response is positive/accepting."""
    result = await detect_intent(message, context, api_key)
    return result.get("intent") in ["accept", "continue", "no_doubt"]


async def is_question(message: str, api_key: Optional[str] = None) -> bool:
    """Check if user is asking a question."""
    result = await detect_intent(message, "User is in a learning session", api_key)
    return result.get("intent") in ["question", "doubt"]
