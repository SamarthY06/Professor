"""
Prompts module - Centralized prompt management for all agents.

This module contains all system prompts and task prompts used by agents.
Keeping prompts in one place makes them easier to maintain and update.
"""

from app.prompts.teacher import TEACHER_SYSTEM_PROMPT
from app.prompts.planner import (
    PLANNER_CONFIG_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    PLAN_PROMPT,
    ADAPT_PROMPT,
    PLAN_PRESENTATION_PROMPT,
)
from app.prompts.quiz import (
    QUIZ_SYSTEM_PROMPT,
    QUESTION_GENERATION_PROMPT,
    ANSWER_EVALUATION_PROMPT,
)

__all__ = [
    # Teacher
    "TEACHER_SYSTEM_PROMPT",
    # Planner - Config Gathering
    "PLANNER_CONFIG_SYSTEM_PROMPT",
    # Planner - Plan Generation
    "PLANNER_SYSTEM_PROMPT",
    "PLAN_PROMPT",
    "ADAPT_PROMPT",
    "PLAN_PRESENTATION_PROMPT",
    # Quiz
    "QUIZ_SYSTEM_PROMPT",
    "QUESTION_GENERATION_PROMPT",
    "ANSWER_EVALUATION_PROMPT",
]
