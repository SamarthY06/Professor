"""SQLAlchemy models package."""

from app.models.user import User, UserAuth, UserSession, UserSettings, EncryptedAPIKey
from app.models.book import Book, BookChapter, Goal, GoalChapter
from app.models.learning import (
    LearningState,
    ProgressSnapshot,
    DocumentChunk,
    ChapterSummary,
    TopicRelationship,
)
from app.models.learning_config import (
    LearningConfig,
    LearningPlan,
    ConversationState,
)
from app.models.chat import ChatSession, ChatMessage, AgentLog
from app.models.quiz import (
    Quiz,
    QuizQuestion,
    QuizAttempt,
    QuestionResponse,
    AttentionQuestion,
)
from app.models.admin import AdminLog, SystemMetric, FeatureFlag
from app.models.note import UserNote, Reminder

__all__ = [
    # User models
    "User",
    "UserAuth",
    "UserSession",
    "UserSettings",
    "EncryptedAPIKey",
    # Book models
    "Book",
    "BookChapter",
    "Goal",
    "GoalChapter",
    # Learning models
    "LearningState",
    "ProgressSnapshot",
    "DocumentChunk",
    "ChapterSummary",
    "TopicRelationship",
    # Learning config models
    "LearningConfig",
    "LearningPlan",
    "ConversationState",
    # Chat models
    "ChatSession",
    "ChatMessage",
    "AgentLog",
    # Quiz models
    "Quiz",
    "QuizQuestion",
    "QuizAttempt",
    "QuestionResponse",
    "AttentionQuestion",
    # Admin models
    "AdminLog",
    "SystemMetric",
    "FeatureFlag",
    # Note models
    "UserNote",
    "Reminder",
]
