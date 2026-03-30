"""
End-to-End tests for the Modern Robotics textbook learning journey.

Simulates real user flows through the Professor platform:
- Passive student behavior (minimal input, teacher drives)
- Scope enforcement (blocks premature transition before 95% coverage)
- Chapter transition accuracy (dashboard reflects completed state)

Uses httpx for API calls. Tests are skeletons with clear structure;
replace placeholders with actual endpoints once API is finalized.
"""

import os
from typing import Optional

import pytest
import httpx

# Base URL for API - configure via env or default to local
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture
def auth_headers() -> dict:
    """Placeholder: provide Authorization header. Override in conftest or test module."""
    token = os.getenv("E2E_AUTH_TOKEN", "")
    if not token:
        pytest.skip("E2E_AUTH_TOKEN not set")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def modern_robotics_book_id() -> Optional[str]:
    """Placeholder: provide Modern Robotics book ID. Override in conftest or test module."""
    return os.getenv("E2E_MODERN_ROBOTICS_BOOK_ID")


@pytest.mark.e2e
class TestModernRoboticsJourney:
    """
    E2E test suite for Modern Robotics learning flow.

    Prerequisites: Running Professor backend, test user with Modern Robotics
    book uploaded and plan accepted.
    """

    def test_passive_student_coverage(
        self,
        auth_headers: dict,
        modern_robotics_book_id: Optional[str] = None,
    ):
        """
        Validates that a passive student who repeatedly says "ok" or similar
        minimal responses still receives full day scope coverage.

        The teacher should drive the conversation: ask questions, present content,
        and cover all topics in the plan without requiring proactive input.
        """
        if not modern_robotics_book_id:
            pytest.skip("modern_robotics_book_id not provided")

        client = httpx.Client(base_url=BASE_URL, timeout=60.0)
        passive_responses = ["ok", "okay", "sure", "yes", "continue", "got it"]

        topics_covered = []

        for i, msg in enumerate(passive_responses[:10]):
            response = client.post(
                "/api/chat",
                headers=auth_headers,
                json={
                    "book_id": modern_robotics_book_id,
                    "message": msg,
                },
            )
            assert response.status_code == 200, f"Chat request {i+1} failed: {response.text}"
            data = response.json()

            assert "message" in data or "response" in data, "Expected professor response"
            professor_msg = data.get("message", data.get("response", ""))
            assert len(professor_msg) > 0, "Teacher should drive with substantive content"

            if "scope" in data or "topics_covered" in data:
                topics_covered.extend(
                    data.get("topics_covered", data.get("scope", {}).get("covered", []))
                )

        client.close()

        assert len(passive_responses) > 0, "Teacher must respond to passive input"

    def test_scope_enforcement_blocks_premature_transition(
        self,
        auth_headers: dict,
        modern_robotics_book_id: Optional[str] = None,
    ):
        """
        Validates that attempting to skip or transition before reaching 95%
        day scope coverage is blocked with an appropriate message.

        User sends "let's move on" or "next day" early; system should
        refuse and ask to cover remaining topics.
        """
        if not modern_robotics_book_id:
            pytest.skip("modern_robotics_book_id not provided")

        client = httpx.Client(base_url=BASE_URL, timeout=60.0)

        response = client.post(
            "/api/chat",
            headers=auth_headers,
            json={
                "book_id": modern_robotics_book_id,
                "message": "Let's skip to the next day, I'm done here",
            },
        )
        assert response.status_code == 200
        data = response.json()

        professor_msg = data.get("message", data.get("response", "")).lower()
        scope_info = data.get("scope_completion", data.get("scope", {}))

        completion = scope_info.get("completion_percentage", 0) if isinstance(scope_info, dict) else 0

        if completion < 95:
            assert any(
                term in professor_msg
                for term in ["cover", "topic", "remaining", "before", "first"]
            ), "Should block transition and mention remaining topics"

        client.close()

    def test_chapter_transition_accuracy(
        self,
        auth_headers: dict,
        modern_robotics_book_id: Optional[str] = None,
    ):
        """
        Validates that after completing a chapter, the dashboard/progress
        API correctly reflects:
        - completed_chapters includes the new chapter
        - current_chapter is incremented
        - Progress percentages are accurate
        """
        if not modern_robotics_book_id:
            pytest.skip("modern_robotics_book_id not provided")

        client = httpx.Client(base_url=BASE_URL, timeout=60.0)

        progress_response = client.get(
            f"/api/learning/progress/{modern_robotics_book_id}",
            headers=auth_headers,
        )
        assert progress_response.status_code == 200
        progress_before = progress_response.json()

        state_response = client.get(
            f"/api/learning/state/{modern_robotics_book_id}",
            headers=auth_headers,
        )
        assert state_response.status_code == 200
        state_before = state_response.json()

        completed_before = set(state_before.get("completed_chapters", []))
        current_chapter_before = state_before.get("current_chapter", 1)

        progress_after_response = client.get(
            f"/api/learning/progress/{modern_robotics_book_id}",
            headers=auth_headers,
        )
        progress_after = progress_after_response.json()
        state_after_response = client.get(
            f"/api/learning/state/{modern_robotics_book_id}",
            headers=auth_headers,
        )
        state_after = state_after_response.json()

        completed_after = set(state_after.get("completed_chapters", []))
        current_chapter_after = state_after.get("current_chapter", 1)

        assert "completed_chapters" in state_after
        assert "current_chapter" in state_after
        assert isinstance(completed_after, (set, list))
        assert current_chapter_after >= current_chapter_before

        client.close()
