"""
Agents module - Simplified Agent-Driven Architecture.

Only 3 active agents:
1. PlannerAgent - Plan generation and iteration
2. TeacherAgent - All teaching, doubts, motivation, attention questions
3. QuizAgent - Quiz generation and evaluation

Retrieval is now a TOOL (in app.tools.retrieval), not an agent.
Progress tracking is now utility functions (in app.services.progress).
Motivation is handled inline by TeacherAgent.
"""

from app.agents.base import BaseAgent
from app.agents.planner import PlannerAgent
from app.agents.teacher import TeacherAgent
from app.agents.quiz import QuizAgent

# Keep old imports for backward compatibility but mark as deprecated
# These will be removed in a future version
from app.agents.teaching import TeachingAgent  # Deprecated - use TeacherAgent

__all__ = [
    "BaseAgent",
    "PlannerAgent",
    "TeacherAgent",
    "QuizAgent",
    # Deprecated
    "TeachingAgent",
]
