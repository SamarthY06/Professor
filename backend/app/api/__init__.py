"""API routers package."""

from app.api import auth, users, books, goals, chat, learning, planning, quiz, notes, admin

__all__ = [
    "auth",
    "users",
    "books",
    "goals",
    "chat",
    "learning",
    "planning",
    "quiz",
    "notes",
    "admin",
]
