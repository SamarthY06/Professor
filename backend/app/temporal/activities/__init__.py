"""Temporal activities for Professor workflows."""

from app.temporal.activities.notifications import (
    send_email_notification,
    send_push_notification,
    send_quiz_reminder,
    send_missed_session_reminder,
)

from app.temporal.activities.quiz import (
    generate_chapter_quiz,
    process_quiz_results,
    create_quiz_attempt,
    get_quiz_questions,
)

from app.temporal.activities.learning import (
    unlock_next_chapter,
    schedule_review_session,
    update_motivation_score,
    record_missed_session,
    get_user_learning_state,
)

from app.temporal.activities.teaching import (
    get_chapter_topics,
    generate_chapter_introduction,
    generate_teaching_segment,
    generate_comprehension_question,
    evaluate_student_response,
    generate_chapter_summary,
)

from app.temporal.activities.session import (
    send_professor_message,
    get_pending_student_response,
    save_session_state,
    load_session_state,
    create_learning_session,
)

__all__ = [
    # Notifications
    "send_email_notification",
    "send_push_notification",
    "send_quiz_reminder",
    "send_missed_session_reminder",
    
    # Quiz
    "generate_chapter_quiz",
    "process_quiz_results",
    "create_quiz_attempt",
    "get_quiz_questions",
    
    # Learning
    "unlock_next_chapter",
    "schedule_review_session",
    "update_motivation_score",
    "record_missed_session",
    "get_user_learning_state",
    
    # Teaching
    "get_chapter_topics",
    "generate_chapter_introduction",
    "generate_teaching_segment",
    "generate_comprehension_question",
    "evaluate_student_response",
    "generate_chapter_summary",
    
    # Session
    "send_professor_message",
    "get_pending_student_response",
    "save_session_state",
    "load_session_state",
    "create_learning_session",
]
