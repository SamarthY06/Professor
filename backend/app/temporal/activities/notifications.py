"""Notification activities with real service integrations."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from temporalio import activity

from app.config import settings
from app.logs.logger import get_logger
from app.models.note import Reminder
from app.models.user import User, UserSettings

logger = get_logger(__name__)

# Database setup (shared with learning activities)
_engine = None
_session_factory = None


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


@activity.defn
async def send_email_notification(
    user_id: str,
    subject: str,
    message: str,
    notification_type: str = "reminder",
) -> dict:
    """
    Send an email notification to a user.
    
    In production, this would integrate with an email service like:
    - SendGrid
    - AWS SES
    - Mailgun
    
    Args:
        user_id: The user's ID
        subject: Email subject
        message: Email body
        notification_type: Type of notification
        
    Returns:
        Dict with send status
    """
    activity.logger.info(f"Sending email notification to user {user_id}")
    
    async with await get_db_session() as db:
        try:
            # Get user's email
            result = await db.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return {"success": False, "error": "User not found"}
            
            # Check user's notification preferences
            settings_result = await db.execute(
                select(UserSettings).where(UserSettings.user_id == UUID(user_id))
            )
            user_settings = settings_result.scalar_one_or_none()
            
            # Check if email notifications are enabled
            if user_settings:
                prefs = user_settings.notification_preferences or {}
                if not prefs.get("email", True):
                    logger.info(
                        "email_notification_disabled",
                        user_id=user_id,
                    )
                    return {
                        "success": False,
                        "error": "Email notifications disabled by user",
                    }
            
            # In production, send via email service
            # For now, log the notification
            logger.info(
                "email_notification_sent",
                user_id=user_id,
                email=user.email,
                subject=subject,
                notification_type=notification_type,
            )
            
            # Record the notification
            reminder = Reminder(
                user_id=UUID(user_id),
                reminder_type=notification_type,
                channel="email",
                message_template=subject,
                message_data={"body": message[:500]},  # Truncate for storage
                scheduled_at=datetime.utcnow(),
                sent_at=datetime.utcnow(),
                status="sent",
            )
            db.add(reminder)
            await db.commit()
            
            # TODO: Production integration
            # Example with SendGrid:
            # from sendgrid import SendGridAPIClient
            # from sendgrid.helpers.mail import Mail
            # 
            # sg = SendGridAPIClient(api_key=settings.sendgrid_api_key)
            # mail = Mail(
            #     from_email='professor@yourdomain.com',
            #     to_emails=user.email,
            #     subject=subject,
            #     html_content=message,
            # )
            # sg.send(mail)
            
            return {
                "success": True,
                "email": user.email,
                "notification_type": notification_type,
                "sent_at": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("email_notification_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def send_push_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "reminder",
    data: Optional[dict] = None,
) -> dict:
    """
    Send a push notification to a user.
    
    In production, this would integrate with:
    - Firebase Cloud Messaging (FCM)
    - Apple Push Notification Service (APNS)
    - Web Push
    
    Args:
        user_id: The user's ID
        title: Notification title
        message: Notification body
        notification_type: Type of notification
        data: Optional additional data
        
    Returns:
        Dict with send status
    """
    activity.logger.info(f"Sending push notification to user {user_id}")
    
    async with await get_db_session() as db:
        try:
            # Get user
            result = await db.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return {"success": False, "error": "User not found"}
            
            # Check push notification preferences
            settings_result = await db.execute(
                select(UserSettings).where(UserSettings.user_id == UUID(user_id))
            )
            user_settings = settings_result.scalar_one_or_none()
            
            if user_settings:
                prefs = user_settings.notification_preferences or {}
                if not prefs.get("push", True):
                    logger.info(
                        "push_notification_disabled",
                        user_id=user_id,
                    )
                    return {
                        "success": False,
                        "error": "Push notifications disabled by user",
                    }
            
            # Log the notification
            logger.info(
                "push_notification_sent",
                user_id=user_id,
                title=title,
                notification_type=notification_type,
            )
            
            # Record the notification
            reminder = Reminder(
                user_id=UUID(user_id),
                reminder_type=notification_type,
                channel="push",
                message_template=title,
                message_data={"body": message, "data": data or {}},
                scheduled_at=datetime.utcnow(),
                sent_at=datetime.utcnow(),
                status="sent",
            )
            db.add(reminder)
            await db.commit()
            
            # TODO: Production integration
            # Example with Firebase:
            # import firebase_admin
            # from firebase_admin import messaging
            # 
            # message = messaging.Message(
            #     notification=messaging.Notification(
            #         title=title,
            #         body=message,
            #     ),
            #     data=data or {},
            #     token=user_fcm_token,
            # )
            # messaging.send(message)
            
            return {
                "success": True,
                "user_id": user_id,
                "title": title,
                "notification_type": notification_type,
                "sent_at": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            await db.rollback()
            logger.exception("push_notification_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def send_quiz_reminder(
    user_id: str,
    quiz_id: str,
    attempt_number: int,
) -> dict:
    """
    Send a quiz reminder to a user.
    
    Args:
        user_id: The user's ID
        quiz_id: The quiz ID
        attempt_number: Which reminder attempt this is (1, 2, 3)
        
    Returns:
        Dict with send status
    """
    activity.logger.info(
        f"Sending quiz reminder to user {user_id}, attempt {attempt_number}"
    )
    
    # Customize message based on attempt
    if attempt_number == 1:
        title = "Quiz Ready! 📝"
        message = "Your chapter quiz is ready to take. Let's see how much you've learned!"
    elif attempt_number == 2:
        title = "Don't forget your quiz! ⏰"
        message = "You still have a quiz waiting. Complete it to unlock the next chapter!"
    else:
        title = "Last reminder! 🔔"
        message = "Your quiz is still pending. Take it now to continue your learning journey!"
    
    # Send both push and email
    push_result = await send_push_notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type="quiz_reminder",
        data={"quiz_id": quiz_id},
    )
    
    email_result = await send_email_notification(
        user_id=user_id,
        subject=title,
        message=message,
        notification_type="quiz_reminder",
    )
    
    return {
        "success": push_result["success"] or email_result["success"],
        "push_sent": push_result["success"],
        "email_sent": email_result["success"],
        "attempt_number": attempt_number,
    }


@activity.defn
async def send_whatsapp_notification(
    user_id: str,
    message: str,
    notification_type: str = "reminder",
) -> dict:
    """
    Send a WhatsApp notification via Twilio.
    
    Args:
        user_id: The user's ID
        message: Message to send
        notification_type: Type of notification
        
    Returns:
        Dict with send status
    """
    activity.logger.info(f"Sending WhatsApp notification to user {user_id}")
    
    async with await get_db_session() as db:
        try:
            # Get user's phone number
            settings_result = await db.execute(
                select(UserSettings).where(UserSettings.user_id == UUID(user_id))
            )
            user_settings = settings_result.scalar_one_or_none()
            
            if not user_settings or not user_settings.whatsapp_number:
                return {"success": False, "error": "No WhatsApp number configured"}
            
            phone_number = user_settings.whatsapp_number
            
            # Check if WhatsApp notifications are enabled
            prefs = user_settings.notification_preferences or {}
            if not prefs.get("whatsapp", True):
                return {"success": False, "error": "WhatsApp notifications disabled"}
            
            # Send via Twilio
            try:
                from twilio.rest import Client
                
                twilio_sid = settings.twilio_account_sid
                twilio_token = settings.twilio_auth_token
                twilio_whatsapp = settings.twilio_whatsapp_number
                
                if not twilio_sid or not twilio_token:
                    logger.warning("Twilio credentials not configured")
                    return {"success": False, "error": "Twilio not configured"}
                
                client = Client(twilio_sid, twilio_token)
                
                twilio_message = client.messages.create(
                    body=message,
                    from_=twilio_whatsapp,
                    to=f"whatsapp:{phone_number}"
                )
                
                logger.info(
                    "whatsapp_notification_sent",
                    user_id=user_id,
                    phone=phone_number,
                    message_sid=twilio_message.sid,
                )
                
                # Record the notification
                reminder = Reminder(
                    user_id=UUID(user_id),
                    reminder_type=notification_type,
                    channel="whatsapp",
                    message_template=message[:100],
                    message_data={"body": message, "sid": twilio_message.sid},
                    scheduled_at=datetime.utcnow(),
                    sent_at=datetime.utcnow(),
                    status="sent",
                )
                db.add(reminder)
                await db.commit()
                
                return {
                    "success": True,
                    "phone": phone_number,
                    "message_sid": twilio_message.sid,
                    "sent_at": datetime.utcnow().isoformat(),
                }
                
            except ImportError:
                logger.error("Twilio package not installed")
                return {"success": False, "error": "Twilio package not installed"}
            except Exception as e:
                logger.exception("twilio_send_failed", error=str(e))
                return {"success": False, "error": str(e)}
                
        except Exception as e:
            await db.rollback()
            logger.exception("whatsapp_notification_failed", error=str(e))
            return {"success": False, "error": str(e)}


@activity.defn
async def send_missed_session_reminder(
    user_id: str,
    book_id: str,
    days_inactive: int,
) -> dict:
    """
    Send a reminder about missed study sessions.
    
    Args:
        user_id: The user's ID
        book_id: The book ID
        days_inactive: Number of days since last activity
        
    Returns:
        Dict with send status
    """
    activity.logger.info(
        f"Sending missed session reminder to user {user_id}, "
        f"inactive for {days_inactive} days"
    )
    
    # Customize based on inactivity duration
    if days_inactive == 1:
        title = "We missed you yesterday! 💙"
        message = "Just a quick check-in. Ready to continue learning today?"
    elif days_inactive <= 3:
        title = "Your learning journey awaits! 🌟"
        message = f"It's been {days_inactive} days since your last session. Let's pick up where you left off!"
    elif days_inactive <= 7:
        title = "Let's get back on track! 💪"
        message = f"You've been away for {days_inactive} days. Your progress is waiting for you!"
    else:
        title = "We're here when you're ready 🙏"
        message = "Life gets busy sometimes. Whenever you're ready, your learning materials are here waiting."
    
    push_result = await send_push_notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type="missed_session",
        data={"book_id": book_id, "days_inactive": days_inactive},
    )
    
    return {
        "success": push_result["success"],
        "days_inactive": days_inactive,
        "sent_at": datetime.utcnow().isoformat(),
    }
