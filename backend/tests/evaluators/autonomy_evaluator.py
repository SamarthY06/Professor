"""Autonomy evaluator for teaching quality.

Evaluates whether the teacher proactively drives the learning
conversation vs. waiting for student prompts.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class AutonomyReport:
    """Report summarizing teacher autonomy from a transcript."""

    autonomy_score: float
    metrics: Dict[str, Any]
    passed: bool


def evaluate_teacher_autonomy(messages: List[dict]) -> AutonomyReport:
    """
    Analyze transcript for teacher autonomy indicators.

    Metrics:
    - teacher_initiated_topics: teacher introduced new topics without student asking
    - student_requested_topics: student explicitly asked to cover something
    - teacher_asked_what_next: teacher asked "what next?" or similar
    - teacher_checked_understanding: teacher asked comprehension questions

    autonomy_score: higher when teacher drives the flow, lower when waiting for student.

    Returns:
        AutonomyReport with autonomy_score and passed=True if score >= 0.7
    """
    transcript_parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            transcript_parts.append(content)
        else:
            transcript_parts.append(str(content))

    transcript = "\n".join(transcript_parts).lower()

    # Patterns for teacher-driven behavior
    teacher_initiated = [
        r"let['\s]?s (?:talk|cover|discuss|look at|explore)",
        r"today we['\s]?(?:ll|will) (?:cover|learn|discuss)",
        r"next[,.]? (?:we|i)['\s]?(?:ll|will) (?:cover|look at)",
        r"moving (?:on|forward) (?:to|with)",
        r"now let['\s]?s (?:move|turn) (?:to|to the)",
        r"i['\s]?(?:d like to|want to) (?:introduce|cover|explain)",
    ]
    teacher_initiated_topics = sum(
        1 for p in teacher_initiated if re.search(p, transcript)
    )

    # Patterns for student-driven behavior (reduces autonomy)
    student_requested = [
        r"student[:\s].*(?:explain|tell me|teach me|what is|how does)",
        r"user[:\s].*(?:explain|tell me|teach me|what is|how does)",
        r"human[:\s].*(?:explain|tell me|teach me|what is|how does)",
        r"can you (?:explain|teach|go over)",
        r"i (?:want|would like) to (?:learn|know) (?:about|more)",
    ]
    student_requested_topics = sum(
        1 for p in student_requested if re.search(p, transcript)
    )

    # Teacher asking what next (bad for autonomy)
    teacher_asked_what_next = [
        r"what (?:would you like|do you want) (?:to (?:do|learn)|next)",
        r"what next\??",
        r"where (?:would you like|do you want) to (?:go|proceed)",
        r"anything else you['\s]?d like",
    ]
    teacher_asked_what_next_count = sum(
        1 for p in teacher_asked_what_next if re.search(p, transcript)
    )

    # Teacher checking understanding (good for autonomy - active teaching)
    teacher_checked_understanding = [
        r"do you (?:understand|follow|see)",
        r"does that (?:make sense|help)",
        r"any questions\??",
        r"clear so far\??",
        r"ready to (?:move on|continue)",
        r"would you like (?:me to|a ) (?:clarify|explain)",
    ]
    teacher_checked_understanding_count = sum(
        1 for p in teacher_checked_understanding if re.search(p, transcript)
    )

    metrics = {
        "teacher_initiated_topics": teacher_initiated_topics,
        "student_requested_topics": student_requested_topics,
        "teacher_asked_what_next": teacher_asked_what_next_count,
        "teacher_checked_understanding": teacher_checked_understanding_count,
    }

    # Score: positive for teacher-driven, negative for student-driven
    # Base 0.5, +0.1 per teacher-initiated, +0.05 per understanding check
    # -0.15 per student-requested, -0.2 per "what next"
    autonomy_score = 0.5
    autonomy_score += min(teacher_initiated_topics * 0.15, 0.3)
    autonomy_score += min(teacher_checked_understanding_count * 0.05, 0.15)
    autonomy_score -= min(student_requested_topics * 0.15, 0.3)
    autonomy_score -= min(teacher_asked_what_next_count * 0.2, 0.3)
    autonomy_score = max(0.0, min(1.0, autonomy_score))

    passed = autonomy_score >= 0.7

    return AutonomyReport(
        autonomy_score=autonomy_score,
        metrics=metrics,
        passed=passed,
    )
