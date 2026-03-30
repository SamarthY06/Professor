"""
LangGraph state definition - Simplified Agent-Driven Architecture.

Key Changes from Original:
1. Removed doubt_resolution phase (handled inline by TeacherAgent)
2. Removed plan_iteration phase (handled by PlannerAgent)
3. Added active_agent field to track which agent is in control
4. Added paused phase for session breaks
5. Simplified quiz state management
"""

from typing import Any, Dict, List, Literal, Optional, TypedDict


# Simplified phases - agents drive the conversation, not phases
Phase = Literal[
    "greeting",              # Initial greeting, waiting for user to accept
    "config_gathering",      # PlannerAgent gathering user preferences
    "planning",              # PlannerAgent generating/iterating plan
    "teaching",              # TeacherAgent driving the conversation
    "quiz",                  # QuizAgent running quiz loop
    "quiz_feedback",         # Quiz complete, waiting for retry/proceed decision
    "chapter_transition",    # Moving to next chapter
    "awaiting_chapter_start",# Ready to begin the next chapter
    "completed",             # All chapters done
    "paused",                # User paused the session
    "error"                  # Error state
]

# Which agent is currently in control
ActiveAgent = Literal[
    "planner",   # PlannerAgent - plan generation/iteration
    "teacher",   # TeacherAgent - teaching, doubts, attention questions
    "quiz",      # QuizAgent - quiz questions and evaluation
    "none"       # No agent active (greeting, transitions)
]


class ProfessorState(TypedDict, total=False):
    """
    State for the Professor learning system.
    
    Design Principles:
    1. Single source of truth - this state maps to LearningState in DB
    2. Agent-driven - active_agent determines who handles the message
    3. Minimal phases - agents handle complexity via orchestrator prompts
    """
    
    # ==================== IDENTITY ====================
    user_id: str
    session_id: str
    book_id: str
    book_title: str
    
    # ==================== PHASE & AGENT ====================
    phase: Phase
    active_agent: ActiveAgent  # Which agent is in control
    
    # ==================== USER INPUT ====================
    user_message: str
    
    # ==================== PROFESSOR OUTPUT ====================
    professor_response: str
    response_type: Literal["greeting", "teaching", "quiz_question", "quiz_result", "plan", "transition", "completion"]
    agent_name: str  # For display: "Professor", "Planner", "Quiz Master"
    
    # ==================== CHAPTER & DAY STATE ====================
    current_chapter: int
    total_chapters: int
    completed_chapters: List[int]
    chapter_title: str
    # Day-based tracking
    current_day: int
    total_days: int
    completed_days: List[int]
    day_title: str
    
    # ==================== TEACHING STATE ====================
    # Topics covered in current chapter (for chapter completion detection)
    topics_covered_this_chapter: List[str]
    # Summary from previous chapter (for continuity)
    previous_chapter_summary: Optional[str]
    # Retrieved context from RAG (populated by retrieval tool)
    retrieved_context: List[Dict[str, Any]]
    # Flag set by TeacherAgent when chapter content is covered
    chapter_content_covered: bool
    
    # ==================== QUIZ STATE ====================
    quiz_questions: List[Dict[str, Any]]  # All questions for current quiz
    quiz_current_index: int               # Current question index (0-based)
    quiz_scores: List[float]              # Score for each answered question
    quiz_passed: Optional[bool]           # None = in progress, True/False = complete
    awaiting_quiz_decision: bool          # True when asking retry/proceed after failure
    
    # ==================== PLAN STATE ====================
    plan_accepted: bool
    plan_data: Optional[Dict[str, Any]]
    plan_iteration_count: int  # Track how many times plan was modified
    
    # ==================== CONFIG (from LearningConfig) ====================
    learning_level: str          # beginner, intermediate, advanced, research
    professor_level: str         # undergrad, mtech, phd - teaching style/depth
    daily_study_minutes: int
    quiz_frequency: str          # after_each_chapter, after_n_chapters, final_only
    questions_per_quiz: int
    professor_style: str         # strict, balanced, encouraging (deprecated, use professor_level)
    
    # ==================== METRICS ====================
    comprehension_score: float   # 0-1, updated after quizzes
    attention_score: float       # 0-1, updated after attention questions
    motivation_score: float      # 0-1, updated based on engagement
    total_study_time_minutes: int
    
    # ==================== SESSION STATE ====================
    session_message_count: int
    last_attention_check_at: int  # Message count when last attention question was asked
    
    # ==================== INTERNAL ====================
    api_key: Optional[str]
    error_message: Optional[str]


def create_initial_state(
    user_id: str,
    book_id: str,
    book_title: str,
    total_chapters: int,
    learning_level: str = "intermediate",
    daily_study_minutes: int = 60,
    quiz_frequency: str = "after_each_chapter",
    questions_per_quiz: int = 5,
    professor_style: str = "balanced",
    api_key: Optional[str] = None,
) -> ProfessorState:
    """Create initial state for a new learning session."""
    return ProfessorState(
        # Identity
        user_id=user_id,
        book_id=book_id,
        book_title=book_title,
        session_id="",
        
        # Phase & Agent
        phase="greeting",
        active_agent="none",
        
        # User input
        user_message="",
        
        # Output
        professor_response="",
        response_type="greeting",
        agent_name="Professor",
        
        # Chapter & Day
        current_chapter=1,
        total_chapters=total_chapters,
        completed_chapters=[],
        chapter_title="",
        current_day=1,
        total_days=1,
        completed_days=[],
        day_title="",
        
        # Teaching
        topics_covered_this_chapter=[],
        previous_chapter_summary=None,
        retrieved_context=[],
        chapter_content_covered=False,
        
        # Quiz
        quiz_questions=[],
        quiz_current_index=0,
        quiz_scores=[],
        quiz_passed=None,
        awaiting_quiz_decision=False,
        
        # Plan
        plan_accepted=False,
        plan_data=None,
        plan_iteration_count=0,
        
        # Config
        learning_level=learning_level,
        professor_level="intermediate",  # Default, will be set from config
        daily_study_minutes=daily_study_minutes,
        quiz_frequency=quiz_frequency,
        questions_per_quiz=questions_per_quiz,
        professor_style=professor_style,
        
        # Metrics
        comprehension_score=1.0,
        attention_score=1.0,
        motivation_score=1.0,
        total_study_time_minutes=0,
        
        # Session
        session_message_count=0,
        last_attention_check_at=0,
        
        # Internal
        api_key=api_key,
        error_message=None,
    )


def should_trigger_quiz(state: ProfessorState) -> bool:
    """
    Determine if a quiz should be triggered based on quiz_frequency setting.
    
    Called when chapter content is covered and user has no more doubts.
    """
    quiz_frequency = state.get("quiz_frequency", "after_each_chapter")
    current_chapter = state.get("current_chapter", 1)
    total_chapters = state.get("total_chapters", 1)
    chapters_completed = state.get("completed_chapters", [])
    
    if quiz_frequency == "after_each_chapter":
        return True
    
    elif quiz_frequency == "after_n_chapters":
        # Quiz every N chapters (default N=3)
        n = 3  # Could be made configurable
        completed_count = len(chapters_completed) + 1  # +1 for current
        return completed_count % n == 0
    
    elif quiz_frequency == "final_only":
        return current_chapter >= total_chapters
    
    return True  # Default to quiz after each chapter


def reset_chapter_state(state: ProfessorState) -> Dict[str, Any]:
    """
    Reset state fields when transitioning to a new chapter.
    
    Returns dict of fields to update.
    """
    return {
        "topics_covered_this_chapter": [],
        "chapter_content_covered": False,
        "quiz_questions": [],
        "quiz_current_index": 0,
        "quiz_scores": [],
        "quiz_passed": None,
        "awaiting_quiz_decision": False,
        "session_message_count": 0,
        "last_attention_check_at": 0,
    }
