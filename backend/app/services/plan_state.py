"""Shared utilities for resolving plan and config state.

Every code path that needs to determine the current learning plan, pending
config, or conversation history should use these functions instead of
reimplementing the resolution logic.  This avoids the DRY violation that
previously existed across:

    - ``load_chat_state``  (Temporal activity)
    - ``_build_state_from_learning_state``  (legacy chat API)
    - ``init_or_get_session``  (session initialisation)
"""

from typing import Any, Dict, List, Optional, Tuple

from app.logs.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Plan resolution
# ---------------------------------------------------------------------------

def has_real_plan(learning_plan: Any) -> bool:
    """Return True only when *learning_plan* contains a generated plan with days.

    The ``LearningState.learning_plan`` JSONB column is overloaded:
    it may hold ``{"pending_config": {...}}`` during config gathering,
    or a full plan dict with a ``"days"`` key after plan generation.
    A simple truthiness check is **not** sufficient.
    """
    if not learning_plan or not isinstance(learning_plan, dict):
        return False
    days = learning_plan.get("days")
    return bool(days and len(days) > 0)


def resolve_plan_data(
    learning_plan_json: Any,
    accepted_plan_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Return the best available plan data dict, or ``None``.

    Resolution order:
        1. An explicitly accepted plan (from ``LearningPlan`` table).
        2. The ``learning_plan`` JSONB on ``LearningState``, but only if
           it contains real plan data (has a ``"days"`` key).
        3. ``None`` — no usable plan exists.
    """
    if accepted_plan_data and isinstance(accepted_plan_data, dict):
        return accepted_plan_data
    if has_real_plan(learning_plan_json):
        return learning_plan_json
    return None


# ---------------------------------------------------------------------------
# Pending config resolution
# ---------------------------------------------------------------------------

def extract_pending_config(learning_plan_json: Any) -> Dict[str, Any]:
    """Extract the ``pending_config`` sub-dict from the overloaded JSONB.

    Returns an empty dict when no pending config is stored.
    """
    if not learning_plan_json or not isinstance(learning_plan_json, dict):
        return {}
    return learning_plan_json.get("pending_config", {})


def extract_config_conversation_history(learning_plan_json: Any) -> List[Dict[str, str]]:
    """Extract the config conversation history from the overloaded JSONB.

    During config gathering, the multi-turn conversation with the planner
    agent is persisted here so it survives Temporal workflow restarts
    without requiring a dedicated DB column.
    """
    if not learning_plan_json or not isinstance(learning_plan_json, dict):
        return []
    return learning_plan_json.get("config_conversation_history", [])


def build_pending_plan_blob(
    state: Dict[str, Any],
    existing_blob: Any = None,
) -> Dict[str, Any]:
    """Build the ``learning_plan`` JSONB blob for the config-gathering phase.

    Merges pending config and conversation history into the existing blob
    (if any) so that previously stored data is not lost.
    """
    blob: Dict[str, Any] = existing_blob.copy() if isinstance(existing_blob, dict) else {}

    blob["pending_config"] = {
        "learning_level": state.get("learning_level", "intermediate"),
        "target_days": state.get("target_days", 30),
        "daily_minutes": state.get("daily_minutes", 30),
        "quiz_frequency": state.get("quiz_frequency", "after_each_chapter"),
    }

    cfg_history = state.get("config_conversation_history", [])
    if cfg_history:
        blob["config_conversation_history"] = cfg_history

    return blob


# ---------------------------------------------------------------------------
# Resolved config values (with fallback chain)
# ---------------------------------------------------------------------------

def resolve_learning_level(
    pending_cfg: Dict[str, Any],
    learning_config_level: Optional[str] = None,
    professor_level: Optional[str] = None,
) -> str:
    """Return the best available learning level string."""
    return (
        pending_cfg.get("learning_level")
        or learning_config_level
        or professor_level
        or "intermediate"
    )


def resolve_config_values(
    pending_cfg: Dict[str, Any],
) -> Tuple[int, int, str]:
    """Return ``(target_days, daily_minutes, quiz_frequency)``."""
    return (
        pending_cfg.get("target_days", 30),
        pending_cfg.get("daily_minutes", 30),
        pending_cfg.get("quiz_frequency", "after_each_chapter"),
    )
