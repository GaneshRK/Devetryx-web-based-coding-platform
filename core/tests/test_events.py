from django.test import TestCase
from core.models import DevetryxEvent
from core.events import (
    emit_event,
    get_recent_events,
    EVENT_CODE_EXECUTED,
    EVENT_AI_HINT_REQUESTED,
)


class EventTelemetryTestCase(TestCase):
    """Tests event logging and telemetry queries."""

    def test_emit_event_persists_to_database(self):
        payload = {
            "language": "python",
            "concept_tags": ["recursion", "base_case"],
            "file": "solution.py",
            "attempt_number": 1
        }
        event = emit_event(
            event_type=EVENT_CODE_EXECUTED,
            payload=payload,
            session_id="test_session_123",
        )
        self.assertIsNotNone(event)
        self.assertEqual(DevetryxEvent.objects.count(), 1)
        self.assertEqual(event.event_type, EVENT_CODE_EXECUTED)
        self.assertEqual(event.payload["file"], "solution.py")

    def test_get_recent_events_filter_by_session(self):
        emit_event(EVENT_CODE_EXECUTED, {"run": 1}, session_id="session_A")
        emit_event(EVENT_AI_HINT_REQUESTED, {"hint": 1}, session_id="session_A")
        emit_event(EVENT_CODE_EXECUTED, {"run": 2}, session_id="session_B")

        events_a = get_recent_events(session_id="session_A")
        self.assertEqual(len(events_a), 2)
        events_b = get_recent_events(session_id="session_B")
        self.assertEqual(len(events_b), 1)
