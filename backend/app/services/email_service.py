"""Email verification service using Resend + Redis for OTP storage."""

import random
import string

import resend
from redis.asyncio import Redis

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)

VERIFY_CODE_PREFIX = "email_verify:"
DAILY_SEND_COUNT_PREFIX = "email_send_count:"
CODE_LENGTH = 6
CODE_TTL_SECONDS = 600  # 10 minutes
DAILY_SEND_LIMIT = 90  # keep buffer below Resend's 100/day free tier


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=CODE_LENGTH))


async def check_daily_limit(redis: Redis) -> tuple[bool, int]:
    """Return (within_limit, remaining_count)."""
    key = f"{DAILY_SEND_COUNT_PREFIX}global"
    count = await redis.get(key)
    current = int(count) if count else 0
    remaining = max(DAILY_SEND_LIMIT - current, 0)
    return current < DAILY_SEND_LIMIT, remaining


async def _increment_daily_count(redis: Redis) -> None:
    key = f"{DAILY_SEND_COUNT_PREFIX}global"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 86400)  # reset after 24 h
    await pipe.execute()


async def send_verification_code(email: str, redis: Redis) -> tuple[bool, str]:
    """
    Generate a 6-digit code, store in Redis, and email it via Resend.
    Returns (success, message).
    """
    if not settings.resend_api_key:
        logger.warning("resend_api_key_not_set")
        return False, "Email verification is not configured."

    within_limit, remaining = await check_daily_limit(redis)
    if not within_limit:
        return False, (
            "We've reached the daily email verification limit. "
            "Please try again tomorrow or sign up with Google instead."
        )

    code = _generate_code()
    key = f"{VERIFY_CODE_PREFIX}{email.lower()}"
    await redis.setex(key, CODE_TTL_SECONDS, code)

    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send({
            "from": settings.verification_from_email,
            "to": [email],
            "subject": "Professor – Verify your email",
            "html": (
                "<div style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,"
                "Helvetica,Arial,sans-serif;max-width:480px;margin:0 auto;padding:40px 24px'>"
                "<div style='text-align:center;margin-bottom:32px'>"
                "<span style='font-size:36px'>🎓</span>"
                "<h1 style='color:#1e293b;font-size:24px;margin:12px 0 4px'>Welcome to Professor</h1>"
                "<p style='color:#64748b;font-size:15px;margin:0'>Your AI-powered learning companion</p>"
                "</div>"
                "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:16px;padding:32px;text-align:center'>"
                "<p style='color:#475569;font-size:15px;margin:0 0 20px'>Your verification code is:</p>"
                f"<div style='font-size:36px;font-weight:700;letter-spacing:10px;"
                f"color:#1e40af;padding:12px 0'>{code}</div>"
                "<p style='color:#94a3b8;font-size:13px;margin:20px 0 0'>This code expires in 10 minutes</p>"
                "</div>"
                "<p style='color:#94a3b8;font-size:12px;text-align:center;margin-top:24px'>"
                "If you didn't request this, you can safely ignore this email.</p>"
                "</div>"
            ),
        })
        await _increment_daily_count(redis)
        logger.info("verification_email_sent", email=email, remaining=remaining - 1)
        return True, "Verification code sent."
    except Exception as e:
        logger.error("verification_email_failed", email=email, error=str(e))
        error_msg = str(e).lower()
        if "rate" in error_msg or "limit" in error_msg or "429" in error_msg:
            return False, (
                "Email sending limit reached. "
                "Please try again later or sign up with Google instead."
            )
        return False, "Failed to send verification email. Please try again."


async def verify_code(email: str, code: str, redis: Redis) -> bool:
    """Check the submitted code against the stored one and consume it."""
    key = f"{VERIFY_CODE_PREFIX}{email.lower()}"
    stored = await redis.get(key)

    if stored is None:
        return False

    if stored.decode() == code.strip():
        await redis.delete(key)
        return True

    return False
