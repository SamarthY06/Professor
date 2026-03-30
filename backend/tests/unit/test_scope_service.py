"""
Unit tests for scope_service.

Tests cover:
- extract_scope_from_plan (basic and structured topics)
- update_scope_coverage (exact match, no false positive)
- verify_scope_completion (95% threshold, rest day)
- check_scope_before_transition (blocks below 95%, allows 100%)
"""

import pytest

from app.services.scope_service import (
    DayScope,
    ScopeItem,
    ScopeStatus,
    extract_scope_from_plan,
    update_scope_coverage,
    verify_scope_completion,
    check_scope_before_transition,
    build_scope_prompt_section,
)


# ---------------------------------------------------------------------------
# test_extract_scope_from_plan
# ---------------------------------------------------------------------------


def test_extract_scope_from_plan_basic_extraction():
    """Basic extraction with string topics."""
    plan_data = {
        "days": [
            {
                "day": 1,
                "day_title": "Introduction to Calculus",
                "rest": False,
                "items": [
                    {
                        "chapter_number": 1,
                        "chapter_title": "Limits",
                        "topics": ["Limits at Infinity", "Continuity", "Derivatives"],
                    }
                ],
            }
        ]
    }
    scope = extract_scope_from_plan(plan_data, 1)

    assert scope.day == 1
    assert scope.day_title == "Introduction to Calculus"
    assert scope.is_rest_day is False
    assert scope.total_items == 3

    assert scope.items[0].topic_name == "Limits at Infinity"
    assert scope.items[0].chapter_number == 1
    assert scope.items[0].chapter_title == "Limits"
    assert scope.items[0].status == ScopeStatus.NOT_STARTED
    assert scope.items[0].priority == "core"

    assert scope.items[1].topic_name == "Continuity"
    assert scope.items[2].topic_name == "Derivatives"


def test_extract_scope_from_plan_empty_plan():
    """Empty or missing plan returns empty scope."""
    scope = extract_scope_from_plan({}, 1)
    assert scope.day == 1
    assert scope.day_title == "Day 1"
    assert scope.items == []
    assert scope.is_rest_day is False

    scope = extract_scope_from_plan(None, 2)
    assert scope.day == 2
    assert scope.items == []


def test_extract_scope_from_plan_day_not_found():
    """When day is not in plan, returns empty scope."""
    plan_data = {"days": [{"day": 1, "day_title": "Day 1", "items": []}]}
    scope = extract_scope_from_plan(plan_data, 99)
    assert scope.day == 99
    assert scope.items == []


# ---------------------------------------------------------------------------
# test_extract_scope_structured_topics
# ---------------------------------------------------------------------------


def test_extract_scope_structured_topics():
    """Extraction with dict-format topics (name, key_formulas, key_definitions, priority)."""
    plan_data = {
        "days": [
            {
                "day": 2,
                "day_title": "Differentiation",
                "rest": False,
                "items": [
                    {
                        "chapter_number": 2,
                        "chapter_title": "Rules of Differentiation",
                        "topics": [
                            {
                                "name": "Product Rule",
                                "key_formulas": ["(fg)' = f'g + fg'"],
                                "key_definitions": ["Derivative of product of two functions"],
                                "priority": "core",
                            },
                            {
                                "name": "Chain Rule",
                                "key_formulas": ["(f∘g)' = f'(g)·g'"],
                                "key_definitions": ["Derivative of composite functions"],
                                "priority": "core",
                            },
                            {"name": "Supplementary Topic", "priority": "supplementary"},
                        ],
                    }
                ],
            }
        ]
    }
    scope = extract_scope_from_plan(plan_data, 2)

    assert scope.day == 2
    assert scope.total_items == 3

    product_rule = scope.items[0]
    assert product_rule.topic_name == "Product Rule"
    assert product_rule.chapter_number == 2
    assert product_rule.key_formulas == ["(fg)' = f'g + fg'"]
    assert product_rule.key_definitions == ["Derivative of product of two functions"]
    assert product_rule.priority == "core"

    chain_rule = scope.items[1]
    assert chain_rule.topic_name == "Chain Rule"
    assert chain_rule.key_formulas == ["(f∘g)' = f'(g)·g'"]
    assert chain_rule.priority == "core"

    supp = scope.items[2]
    assert supp.topic_name == "Supplementary Topic"
    assert supp.priority == "supplementary"
    assert supp.key_formulas is None
    assert supp.key_definitions is None


# ---------------------------------------------------------------------------
# test_update_scope_coverage_exact_match
# ---------------------------------------------------------------------------


def test_update_scope_coverage_exact_match():
    """Topics covered with exact match marks scope items complete."""
    scope = DayScope(
        day=1,
        day_title="Day 1",
        items=[
            ScopeItem("Limits at Infinity", 1, "Limits"),
            ScopeItem("Continuity", 1, "Limits"),
            ScopeItem("Derivatives", 1, "Limits"),
        ],
    )
    topics_covered = ["Limits at Infinity", "Continuity", "Derivatives"]

    updated = update_scope_coverage(scope, topics_covered)

    assert updated.items[0].status == ScopeStatus.COMPLETE
    assert updated.items[1].status == ScopeStatus.COMPLETE
    assert updated.items[2].status == ScopeStatus.COMPLETE
    assert updated.completion_percentage == 100.0


def test_update_scope_coverage_partial_match():
    """Partial topics covered marks only those items complete."""
    scope = DayScope(
        day=1,
        day_title="Day 1",
        items=[
            ScopeItem("Derivatives", 1, "Ch1"),
            ScopeItem("Integration", 1, "Ch1"),
            ScopeItem("Limits", 1, "Ch1"),
        ],
    )
    # Only Derivatives and Limits covered - Integration should remain uncovered
    topics_covered = ["Derivatives", "Limits"]

    updated = update_scope_coverage(scope, topics_covered)

    assert updated.items[0].status == ScopeStatus.COMPLETE
    assert updated.items[1].status == ScopeStatus.NOT_STARTED
    assert updated.items[2].status == ScopeStatus.COMPLETE
    assert updated.completion_percentage == pytest.approx(66.67, rel=0.01)


# ---------------------------------------------------------------------------
# test_update_scope_coverage_no_false_positive
# ---------------------------------------------------------------------------


def test_update_scope_coverage_no_false_positive():
    """Unrelated topics in topics_covered do not mark scope items complete."""
    scope = DayScope(
        day=1,
        day_title="Day 1",
        items=[
            ScopeItem("Derivatives", 1, "Calculus"),
            ScopeItem("Integration by Parts", 1, "Calculus"),
        ],
    )
    # Completely unrelated topics - should not match
    topics_covered = ["Limits", "Continuity", "Sequences", "Series"]

    updated = update_scope_coverage(scope, topics_covered)

    assert updated.items[0].status == ScopeStatus.NOT_STARTED
    assert updated.items[1].status == ScopeStatus.NOT_STARTED
    assert updated.completion_percentage == 0.0


def test_update_scope_coverage_empty_topics_returns_unchanged():
    """Empty topics_covered leaves scope unchanged."""
    scope = DayScope(
        day=1,
        day_title="Day 1",
        items=[ScopeItem("Topic A", 1, "Ch1")],
    )
    updated = update_scope_coverage(scope, [])
    assert updated.items[0].status == ScopeStatus.NOT_STARTED


# ---------------------------------------------------------------------------
# test_verify_scope_95_threshold
# ---------------------------------------------------------------------------


def test_verify_scope_95_threshold_4_of_5_blocks():
    """4 of 5 topics (80%) should NOT allow proceed when minimum is 95%."""
    items = [
        ScopeItem("T1", 1, "Ch1", status=ScopeStatus.COMPLETE),
        ScopeItem("T2", 1, "Ch1", status=ScopeStatus.COMPLETE),
        ScopeItem("T3", 1, "Ch1", status=ScopeStatus.COMPLETE),
        ScopeItem("T4", 1, "Ch1", status=ScopeStatus.COMPLETE),
        ScopeItem("T5", 1, "Ch1", status=ScopeStatus.NOT_STARTED),
    ]
    scope = DayScope(day=1, day_title="Day 1", items=items)

    result = verify_scope_completion(
        scope, allow_partial=True, minimum_completion=0.95
    )

    assert result.completion_percentage == 80.0
    assert result.can_proceed is False
    assert result.is_complete is False
    assert "T5" in result.remaining_topics


def test_verify_scope_95_threshold_19_of_20_allows():
    """19 of 20 topics (95%) should allow proceed when minimum is 95%."""
    items = [
        ScopeItem(f"T{i}", 1, "Ch1", status=ScopeStatus.COMPLETE)
        for i in range(19)
    ] + [ScopeItem("T20", 1, "Ch1", status=ScopeStatus.NOT_STARTED)]
    scope = DayScope(day=1, day_title="Day 1", items=items)

    result = verify_scope_completion(
        scope, allow_partial=True, minimum_completion=0.95
    )

    assert result.completion_percentage == 95.0
    assert result.can_proceed is True
    assert result.is_complete is False
    assert result.remaining_topics == ["T20"]


# ---------------------------------------------------------------------------
# test_verify_scope_rest_day
# ---------------------------------------------------------------------------


def test_verify_scope_rest_day():
    """Rest day scope is always complete and allows proceed."""
    scope = DayScope(day=2, day_title="Review Day", items=[], is_rest_day=True)

    result = verify_scope_completion(scope)

    assert result.is_complete is True
    assert result.completion_percentage == 100.0
    assert result.can_proceed is True
    assert result.covered_topics == []
    assert result.remaining_topics == []


# ---------------------------------------------------------------------------
# test_check_scope_before_transition
# ---------------------------------------------------------------------------


def test_check_scope_before_transition_blocks_below_95():
    """Completion below 95% should block transition."""
    state = {
        "current_scope": {
            "completion_percentage": 80.0,
            "is_rest_day": False,
            "remaining_topics": ["Topic A", "Topic B"],
        }
    }

    can_proceed, warning = check_scope_before_transition(state)

    assert can_proceed is False
    assert warning is not None
    assert "Topic A" in warning or "Topic B" in warning
    assert "cover" in warning.lower()


def test_check_scope_before_transition_allows_100():
    """100% completion should allow transition with no warning."""
    state = {
        "current_scope": {
            "completion_percentage": 100.0,
            "is_rest_day": False,
            "remaining_topics": [],
        }
    }

    can_proceed, warning = check_scope_before_transition(state)

    assert can_proceed is True
    assert warning is None


def test_check_scope_before_transition_allows_95():
    """95% completion should allow transition (with optional warning)."""
    state = {
        "current_scope": {
            "completion_percentage": 95.0,
            "is_rest_day": False,
            "remaining_topics": ["Last Topic"],
        }
    }

    can_proceed, warning = check_scope_before_transition(state)

    assert can_proceed is True
    assert warning is not None
    assert "most topics" in warning.lower() or "95" in warning


def test_check_scope_before_transition_rest_day():
    """Rest day should always allow transition."""
    state = {
        "current_scope": {
            "completion_percentage": 0,
            "is_rest_day": True,
            "remaining_topics": [],
        }
    }

    can_proceed, warning = check_scope_before_transition(state)

    assert can_proceed is True
    assert warning is None


def test_check_scope_before_transition_no_scope():
    """Missing scope in state allows transition (no scope to enforce)."""
    state = {}
    can_proceed, warning = check_scope_before_transition(state)
    assert can_proceed is True
    assert warning is None

    state = {"current_scope": {}}
    can_proceed, warning = check_scope_before_transition(state)
    assert can_proceed is True


# ---------------------------------------------------------------------------
# test_build_scope_prompt_section (bonus coverage)
# ---------------------------------------------------------------------------


def test_build_scope_prompt_section_rest_day():
    """Rest day produces review-day prompt."""
    scope = DayScope(day=1, day_title="Review", items=[], is_rest_day=True)
    text = build_scope_prompt_section(scope, [])
    assert "Review Day" in text
    assert "consolidation" in text or "review" in text.lower()


def test_build_scope_prompt_section_with_items():
    """Regular day produces scope list and enforcement rules."""
    items = [
        ScopeItem("Topic A", 1, "Ch1", status=ScopeStatus.COMPLETE),
        ScopeItem("Topic B", 1, "Ch1", status=ScopeStatus.NOT_STARTED),
    ]
    scope = DayScope(day=1, day_title="Day 1", items=items)
    text = build_scope_prompt_section(scope, ["Topic A"])

    assert "TODAY'S SCOPE" in text
    assert "Topic A" in text
    assert "Topic B" in text
    assert "SCOPE ENFORCEMENT" in text or "SCOPE" in text
    assert "1/2" in text or "50" in text
