"""
Devetryx Event Telemetry Module.

Every meaningful user action becomes an event written here per Principle 4 and Part 2.4.
Skill scoring and analytics are built upon this clean event feed.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from django.utils import timezone

logger = logging.getLogger(__name__)

# Standard Event Types
EVENT_CODE_WRITTEN = "CODE_WRITTEN"
EVENT_CODE_EXECUTED = "CODE_EXECUTED"
EVENT_COMPILATION_FAILED = "COMPILATION_FAILED"
EVENT_TEST_FAILED = "TEST_FAILED"
EVENT_TEST_PASSED = "TEST_PASSED"
EVENT_BUG_FIXED = "BUG_FIXED"
EVENT_AI_HINT_REQUESTED = "AI_HINT_REQUESTED"
EVENT_CHALLENGE_COMPLETED = "CHALLENGE_COMPLETED"

CORE_EVENT_TYPES = {
    EVENT_CODE_WRITTEN,
    EVENT_CODE_EXECUTED,
    EVENT_COMPILATION_FAILED,
    EVENT_TEST_FAILED,
    EVENT_TEST_PASSED,
    EVENT_BUG_FIXED,
    EVENT_AI_HINT_REQUESTED,
    EVENT_CHALLENGE_COMPLETED,
}


def emit_event(
    event_type: str,
    payload: Dict[str, Any],
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Optional[Any]:
    """
    Emit and persist a telemetry event.

    Args:
        event_type: One of standard event constants (e.g. CODE_EXECUTED).
        payload: Metadata dictionary (file, concept_tags, attempt_number, exit_code, etc.).
        user_id: Optional authenticated user UUID.
        session_id: Optional anonymous or active session ID.

    Returns:
        The created DevetryxEvent instance or None if database write failed.
    """
    from core.models import DevetryxEvent

    clean_payload = dict(payload) if payload else {}

    try:
        event = DevetryxEvent.objects.create(
            event_type=event_type,
            user_id=str(user_id) if user_id else None,
            session_id=str(session_id) if session_id else None,
            payload=clean_payload,
        )
        logger.info(f"Emitted Devetryx event [{event_type}] for session={session_id} user={user_id}")
        return event
    except Exception as e:
        logger.error(f"Failed to record Devetryx event [{event_type}]: {e}", exc_info=True)
        return None


def get_recent_events(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Retrieve recent events for a given session or user."""
    from core.models import DevetryxEvent

    qs = DevetryxEvent.objects.all()
    if user_id:
        qs = qs.filter(user_id=str(user_id))
    elif session_id:
        qs = qs.filter(session_id=str(session_id))
    else:
        # Default latest events
        pass

    return [e.to_dict() for e in qs.order_by("-timestamp")[:limit]]
