"""
Scope Service - Manages and enforces learning scope for each day/chapter.

The scope system ensures:
1. All planned topics for a day are covered before moving on
2. Teacher stays within the defined scope
3. User is warned if topics are skipped
4. Scope is verified before quiz/transition

This is CRITICAL for ensuring comprehensive content coverage.
"""

from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from app.logs.logger import get_logger

logger = get_logger(__name__)


class ScopeStatus(Enum):
    """Status of scope completion."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    SKIPPED = "skipped"


@dataclass
class ScopeItem:
    """A single item in the scope (topic to cover)."""
    topic_name: str
    chapter_number: int
    chapter_title: str
    status: ScopeStatus = ScopeStatus.NOT_STARTED
    covered_at_message: Optional[int] = None
    key_formulas: Optional[List[str]] = None
    key_definitions: Optional[List[str]] = None
    priority: str = "core"


@dataclass
class DayScope:
    """Complete scope for a single day."""
    day: int
    day_title: str
    items: List[ScopeItem]
    is_rest_day: bool = False
    
    @property
    def total_items(self) -> int:
        return len(self.items)
    
    @property
    def covered_items(self) -> int:
        return len([i for i in self.items if i.status == ScopeStatus.COMPLETE])
    
    @property
    def completion_percentage(self) -> float:
        if self.total_items == 0:
            return 100.0
        return (self.covered_items / self.total_items) * 100
    
    @property
    def is_complete(self) -> bool:
        if self.is_rest_day:
            return True
        return self.covered_items >= self.total_items
    
    @property
    def remaining_items(self) -> List[ScopeItem]:
        return [i for i in self.items if i.status != ScopeStatus.COMPLETE]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "day_title": self.day_title,
            "is_rest_day": self.is_rest_day,
            "total_items": self.total_items,
            "covered_items": self.covered_items,
            "completion_percentage": self.completion_percentage,
            "is_complete": self.is_complete,
            "items": [
                {
                    "topic_name": i.topic_name,
                    "chapter_number": i.chapter_number,
                    "chapter_title": i.chapter_title,
                    "status": i.status.value,
                    "covered_at_message": i.covered_at_message,
                    "key_formulas": i.key_formulas,
                    "key_definitions": i.key_definitions,
                    "priority": i.priority,
                }
                for i in self.items
            ],
        }


@dataclass
class ScopeVerificationResult:
    """Result of scope verification."""
    is_complete: bool
    completion_percentage: float
    covered_topics: List[str]
    remaining_topics: List[str]
    warning_message: Optional[str] = None
    can_proceed: bool = True  # True if user can proceed even if incomplete


def extract_scope_from_plan(plan_data: Dict[str, Any], day: int) -> DayScope:
    """
    Extract the scope for a specific day from the learning plan.
    
    Args:
        plan_data: The learning plan data
        day: Day number to extract scope for
    
    Returns:
        DayScope object with all items for that day
    """
    if not plan_data:
        return DayScope(day=day, day_title=f"Day {day}", items=[], is_rest_day=False)
    
    days = plan_data.get("days", [])
    
    for day_data in days:
        if day_data.get("day") == day:
            day_title = day_data.get("day_title", f"Day {day}")
            is_rest = day_data.get("rest", False)
            
            if is_rest:
                return DayScope(
                    day=day,
                    day_title=day_title,
                    items=[],
                    is_rest_day=True,
                )
            
            items = []
            for item in day_data.get("items", []):
                chapter_number = item.get("chapter_number", 1)
                chapter_title = item.get("chapter_title", f"Chapter {chapter_number}")
                topics = item.get("topics", [])
                
                for topic in topics:
                    if isinstance(topic, dict):
                        items.append(ScopeItem(
                            topic_name=topic.get("name", ""),
                            chapter_number=chapter_number,
                            chapter_title=chapter_title,
                            key_formulas=topic.get("key_formulas"),
                            key_definitions=topic.get("key_definitions"),
                            priority=topic.get("priority", "core"),
                        ))
                    else:
                        items.append(ScopeItem(
                            topic_name=topic,
                            chapter_number=chapter_number,
                            chapter_title=chapter_title,
                        ))
            
            return DayScope(
                day=day,
                day_title=day_title,
                items=items,
                is_rest_day=False,
            )
    
    # Day not found in plan
    return DayScope(day=day, day_title=f"Day {day}", items=[], is_rest_day=False)


def update_scope_coverage(
    scope: DayScope,
    topics_covered: List[str],
    message_index: int = 0,
) -> DayScope:
    """
    Update scope items based on topics that have been covered.
    
    Uses fuzzy matching to determine if a topic has been covered.
    
    Args:
        scope: The current day scope
        topics_covered: List of topic names that have been covered
        message_index: Current message index for tracking
    
    Returns:
        Updated DayScope with coverage status
    """
    if not topics_covered:
        return scope
    
    # Normalize topics for matching
    covered_normalized = {_normalize_topic(t) for t in topics_covered}
    
    for item in scope.items:
        if item.status == ScopeStatus.COMPLETE:
            continue
        
        item_normalized = _normalize_topic(item.topic_name)
        
        # Check for match
        if _topics_match(item_normalized, covered_normalized):
            item.status = ScopeStatus.COMPLETE
            item.covered_at_message = message_index
            logger.info(
                "scope_item_covered",
                topic=item.topic_name,
                day=scope.day,
                message_index=message_index,
            )
    
    return scope


def _normalize_topic(topic: str) -> str:
    """Normalize a topic name for matching."""
    return topic.lower().strip()


def _topics_match(item_topic: str, covered_topics: set) -> bool:
    """
    Check if a scope item topic matches any covered topic.
    
    Uses multiple matching strategies:
    1. Exact match
    2. Substring match (item in covered or covered in item) with minimum length
    3. Key word overlap (>= 70% of significant words)
    """
    # Exact match
    if item_topic in covered_topics:
        return True
    
    # Substring match - require minimum length to avoid spurious matches
    for covered in covered_topics:
        if len(item_topic) >= 8 and item_topic in covered:
            return True
        if len(covered) >= 8 and covered in item_topic:
            return True
    
    # Key word overlap - require 70% match to avoid confusion
    # between related but distinct topics (e.g. "forward kinematics" vs "inverse kinematics")
    item_words = {w for w in item_topic.split() if len(w) >= 4}
    if not item_words or len(item_words) < 2:
        return False
    
    for covered in covered_topics:
        covered_words = {w for w in covered.split() if len(w) >= 4}
        if not covered_words:
            continue
        
        overlap = len(item_words & covered_words)
        if overlap >= max(2, len(item_words) * 0.7):
            return True
    
    return False


def verify_scope_completion(
    scope: DayScope,
    allow_partial: bool = False,
    minimum_completion: float = 0.8,
) -> ScopeVerificationResult:
    """
    Verify if the day's scope is complete enough to proceed.
    
    Args:
        scope: The day scope to verify
        allow_partial: If True, allows proceeding with partial completion
        minimum_completion: Minimum completion percentage required (0-1)
    
    Returns:
        ScopeVerificationResult with status and warnings
    """
    if scope.is_rest_day:
        return ScopeVerificationResult(
            is_complete=True,
            completion_percentage=100.0,
            covered_topics=[],
            remaining_topics=[],
            can_proceed=True,
        )
    
    covered = [i.topic_name for i in scope.items if i.status == ScopeStatus.COMPLETE]
    remaining = [i.topic_name for i in scope.items if i.status != ScopeStatus.COMPLETE]
    completion_pct = scope.completion_percentage
    
    is_complete = completion_pct >= 100.0
    can_proceed = is_complete or (allow_partial and completion_pct >= minimum_completion * 100)
    
    warning_message = None
    if not is_complete:
        remaining_str = ", ".join(remaining[:3])
        if len(remaining) > 3:
            remaining_str += f" and {len(remaining) - 3} more"
        
        if can_proceed:
            warning_message = (
                f"⚠️ **Note:** We haven't covered all topics yet. "
                f"Remaining: {remaining_str}. "
                f"Would you like to continue with these topics, or proceed anyway?"
            )
        else:
            warning_message = (
                f"📚 **Hold on!** We still need to cover: {remaining_str}. "
                f"Let's make sure you understand these before moving on."
            )
    
    return ScopeVerificationResult(
        is_complete=is_complete,
        completion_percentage=completion_pct,
        covered_topics=covered,
        remaining_topics=remaining,
        warning_message=warning_message,
        can_proceed=can_proceed,
    )


def build_scope_prompt_section(
    scope: DayScope,
    topics_covered: List[str],
) -> str:
    """
    Build a prompt section describing the current scope status.
    
    This is injected into the teacher's system prompt to ensure
    scope awareness.
    
    Args:
        scope: The current day scope
        topics_covered: Topics already covered in this session
    
    Returns:
        Formatted string for the prompt
    """
    if scope.is_rest_day:
        return """
## TODAY'S FOCUS: Review Day

Today is a consolidation day. Help the student:
- Review challenging concepts from previous days
- Answer any lingering questions
- Reinforce key takeaways

No new content today - focus on solidifying understanding.
"""
    
    if not scope.items:
        return ""
    
    # Group items by chapter
    chapters: Dict[int, List[ScopeItem]] = {}
    for item in scope.items:
        if item.chapter_number not in chapters:
            chapters[item.chapter_number] = []
        chapters[item.chapter_number].append(item)
    
    # Build scope description
    lines = [f"## TODAY'S SCOPE - Day {scope.day}: {scope.day_title}\n"]
    
    for chapter_num, items in sorted(chapters.items()):
        chapter_title = items[0].chapter_title if items else f"Chapter {chapter_num}"
        lines.append(f"### Chapter {chapter_num}: {chapter_title}\n")
        
        for item in items:
            status_icon = "✅" if item.status == ScopeStatus.COMPLETE else "⬜"
            priority_tag = f" [{item.priority}]" if item.priority != "core" else ""
            lines.append(f"  {status_icon} {item.topic_name}{priority_tag}")
            if item.key_formulas and item.status != ScopeStatus.COMPLETE:
                for formula in item.key_formulas:
                    lines.append(f"      📐 Formula: {formula}")
            if item.key_definitions and item.status != ScopeStatus.COMPLETE:
                for defn in item.key_definitions:
                    lines.append(f"      📖 Definition: {defn}")
        
        lines.append("")
    
    # Progress summary
    lines.append(f"**Progress:** {scope.covered_items}/{scope.total_items} topics ({scope.completion_percentage:.0f}%)\n")
    
    # Remaining topics
    remaining = scope.remaining_items
    if remaining:
        lines.append("**Still to cover:**")
        for item in remaining[:5]:
            lines.append(f"  - {item.topic_name}")
        if len(remaining) > 5:
            lines.append(f"  - ... and {len(remaining) - 5} more")
        lines.append("")
    
    # Instructions
    lines.append("""
### SCOPE ENFORCEMENT RULES

1. **Cover ALL topics** listed above before offering quiz or day transition
2. **Stay within scope** - If student asks about topics from other days, redirect politely
3. **Track progress** - After teaching a topic, mentally check it off
4. **Verify before transition** - Before saying "we've covered everything", check the list above

### MANDATORY TOOL USAGE

You MUST call `fetch_next_topic` or `answer_from_textbook` for EVERY uncovered topic in today's scope.
Do NOT teach from memory alone. The textbook is your ONLY source of content.
If you explain a concept without first retrieving it from the textbook, the system will flag it as uncovered.

For each uncovered topic marked with ⬜:
1. Call fetch_next_topic with the specific topic name in the `topics_already_covered` parameter
2. Teach from the retrieved content
3. Include formulas, equations, and definitions exactly as they appear in the textbook

NEVER say "we've covered this" unless you retrieved content for it via tools.

### KEEP MOVING FORWARD

When the student acknowledges understanding (says "ok", "got it", "next", "continue", "I see", etc.):
- Immediately call fetch_next_topic for the next ⬜ topic
- Do NOT re-explain, re-summarize, or re-elaborate on the ✅ topic
- Do NOT ask if they want to review — move to new material
- Each response should teach NEW content from an uncovered ⬜ topic

### WHEN STUDENT WANTS TO MOVE ON

If student says "let's move on" or "next day" but scope is incomplete:
- Acknowledge their request
- Point out remaining topics: "Before we move on, we still need to cover [topics]"
- Explain that core content must be covered for the plan to be effective
- Offer to cover remaining topics quickly in summary mode rather than skipping entirely
- Do NOT allow skipping core syllabus items - only supplementary/review topics can be skipped

### WHEN SCOPE IS COMPLETE (ALL ✅, 0 ⬜)

When ALL topics above show ✅ (100% coverage):
1. Briefly summarize what was learned (2-3 sentences max)
2. Immediately offer a quiz — this is **MANDATORY**, not optional
3. Your [DECISION] block MUST say: next_action: offer_quiz

**DO NOT continue teaching once all topics are covered.**
**DO NOT add extra review, examples, or tangents after 100% scope.**
**DO NOT ask the student "what would you like to do?" — go to quiz.**
""")
    
    return "\n".join(lines)


def get_scope_status_for_response(
    scope: DayScope,
) -> Dict[str, Any]:
    """
    Get scope status for including in API response.
    
    Args:
        scope: The current day scope
    
    Returns:
        Dict with scope status information
    """
    return {
        "day": scope.day,
        "day_title": scope.day_title,
        "is_rest_day": scope.is_rest_day,
        "total_topics": scope.total_items,
        "covered_topics": scope.covered_items,
        "completion_percentage": scope.completion_percentage,
        "is_complete": scope.is_complete,
        "remaining_topics": [i.topic_name for i in scope.remaining_items],
    }


# ============================================================================
# SCOPE TRACKING IN STATE
# ============================================================================

def initialize_scope_in_state(
    state: Dict[str, Any],
    plan_data: Dict[str, Any],
    current_day: int,
) -> Dict[str, Any]:
    """
    Initialize or update scope tracking in state.
    
    Args:
        state: Current state dict
        plan_data: Learning plan data
        current_day: Current day number
    
    Returns:
        Updated state with scope information
    """
    scope = extract_scope_from_plan(plan_data, current_day)
    
    # Get existing covered topics
    topics_covered = state.get("topics_covered_this_chapter", [])
    
    # Update scope with covered topics
    scope = update_scope_coverage(scope, topics_covered)
    
    # Store scope in state
    state["current_scope"] = scope.to_dict()
    state["scope_completion"] = scope.completion_percentage
    state["scope_is_complete"] = scope.is_complete
    
    return state


def check_scope_before_transition(
    state: Dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    """
    Check if scope is complete before allowing day/quiz transition.
    
    Args:
        state: Current state dict
    
    Returns:
        Tuple of (can_proceed, warning_message)
    """
    scope_data = state.get("current_scope", {})
    
    if not scope_data:
        return True, None
    
    if scope_data.get("is_rest_day", False):
        return True, None
    
    completion = scope_data.get("completion_percentage", 0)
    remaining = scope_data.get("remaining_topics", [])
    
    if completion >= 100:
        return True, None
    
    if completion >= 95:
        remaining_str = ", ".join(remaining[:3])
        warning = (
            f"⚠️ We've covered most topics ({completion:.0f}%), but these remain: {remaining_str}. "
            f"Would you like to quickly cover them before moving on?"
        )
        return True, warning
    
    # Don't allow - too much remaining
    remaining_str = ", ".join(remaining[:3])
    if len(remaining) > 3:
        remaining_str += f" and {len(remaining) - 3} more"
    
    warning = (
        f"📚 We still need to cover: {remaining_str}. "
        f"Let's make sure you understand these before moving on."
    )
    return False, warning
