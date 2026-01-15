"""
LangGraph module for Professor workflow.

Agent-Driven Architecture:
- ProfessorState: Simplified state with active_agent tracking
- process_message: Main entry point for message processing
- Nodes route to appropriate agents based on phase
"""

from app.langgraph.state import (
    ProfessorState, 
    Phase, 
    ActiveAgent,
    create_initial_state,
    should_trigger_quiz,
    reset_chapter_state,
)
from app.langgraph.graph import process_message

__all__ = [
    # State
    "ProfessorState", 
    "Phase", 
    "ActiveAgent",
    "create_initial_state",
    "should_trigger_quiz",
    "reset_chapter_state",
    # Processing
    "process_message",
]
