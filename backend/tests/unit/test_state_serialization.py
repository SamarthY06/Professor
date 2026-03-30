"""
Unit tests for ChatState serialization round-trip and key consistency.

ChatState is defined in app.temporal.workflows.chat_workflow.
"""

import pytest

from app.temporal.workflows.chat_workflow import ChatState


def test_chat_state_roundtrip():
    """
    ChatState.from_dict(state.to_dict()) preserves all fields.
    Ensures serialization does not lose or corrupt data.
    """
    state = ChatState(
        user_id="user-123",
        book_id="book-456",
        phase="teaching",
        current_day=2,
        current_chapter=3,
        completed_days=[1],
        completed_chapters=[1, 2],
        plan_data={"total_days": 10, "days": [{"day": 1}]},
        professor_level="advanced",
        topics_covered_this_chapter=["Topic A", "Topic B"],
        day_summaries={"day_1": {"summary": "Day 1 summary"}},
        chapter_summaries={"chapter_1": {"summary": "Ch1 summary"}},
        cumulative_summary="Cumulative context",
        last_session_date="2024-01-15",
        total_study_time_minutes=120,
    )

    serialized = state.to_dict()
    restored = ChatState.from_dict(serialized)

    assert restored.user_id == state.user_id
    assert restored.book_id == state.book_id
    assert restored.phase == state.phase
    assert restored.current_day == state.current_day
    assert restored.current_chapter == state.current_chapter
    assert restored.completed_days == state.completed_days
    assert restored.completed_chapters == state.completed_chapters
    assert restored.plan_data == state.plan_data
    assert restored.professor_level == state.professor_level
    assert restored.topics_covered_this_chapter == state.topics_covered_this_chapter
    assert restored.day_summaries == state.day_summaries
    assert restored.chapter_summaries == state.chapter_summaries
    assert restored.cumulative_summary == state.cumulative_summary
    assert restored.last_session_date == state.last_session_date
    assert restored.total_study_time_minutes == state.total_study_time_minutes


def test_chat_state_roundtrip_minimal():
    """Round-trip with minimal/default fields."""
    state = ChatState(user_id="u", book_id="b")
    restored = ChatState.from_dict(state.to_dict())

    assert restored.user_id == "u"
    assert restored.book_id == "b"
    assert restored.phase == "greeting"
    assert restored.current_day == 1
    assert restored.current_chapter == 1
    assert restored.completed_days == []
    assert restored.completed_chapters == []
    assert restored.plan_data is None


def test_completed_chapters_key_consistency():
    """
    Verify the key is `completed_chapters` everywhere:
    - ChatState field name
    - to_dict() output
    - from_dict() input

    Prevents drift between workflow, activities, and DB mapping.
    """
    state = ChatState(
        user_id="u",
        book_id="b",
        completed_chapters=[1, 2, 3],
    )

    d = state.to_dict()
    assert "completed_chapters" in d
    assert d["completed_chapters"] == [1, 2, 3]
    assert "completed_chapter" not in d
    assert "completedChapter" not in d

    restored = ChatState.from_dict(d)
    assert restored.completed_chapters == [1, 2, 3]
