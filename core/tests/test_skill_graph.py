from django.test import TestCase
from core.events import emit_event, EVENT_CODE_EXECUTED, EVENT_COMPILATION_FAILED
from core.skills.skill_graph import compute_skill_graph, SAMPLE_SIZE_THRESHOLD


class SkillGraphTestCase(TestCase):
    """Tests Skill Graph schema conformity and sample-size threshold gating."""

    def test_cold_start_sample_size_gating(self):
        # 0 events -> Should display 'not enough data yet'
        graph = compute_skill_graph(session_id="session_new")
        self.assertFalse(graph["has_sufficient_data"])
        self.assertEqual(graph["display_status"], "not enough data yet")
        self.assertEqual(graph["languages"]["python"]["syntax"], "not enough data yet")

    def test_below_threshold_sample_size(self):
        # Emit 3 events (< 5)
        for i in range(3):
            emit_event(
                EVENT_CODE_EXECUTED,
                {"concept_tags": ["functions", "loops"], "exit_code": 0},
                session_id="session_partial"
            )

        graph = compute_skill_graph(session_id="session_partial", sample_size_threshold=5)
        self.assertFalse(graph["has_sufficient_data"])
        self.assertEqual(graph["languages"]["python"]["syntax"], "not enough data yet")

    def test_sufficient_sample_size_computes_numerical_scores(self):
        # Emit 6 events (>= 5)
        for i in range(6):
            emit_event(
                EVENT_CODE_EXECUTED,
                {"concept_tags": ["functions", "recursion", "loops"], "exit_code": 0},
                session_id="session_active"
            )

        graph = compute_skill_graph(session_id="session_active", sample_size_threshold=5)
        self.assertTrue(graph["has_sufficient_data"])
        self.assertEqual(graph["display_status"], "active")
        self.assertIsInstance(graph["languages"]["python"]["syntax"], float)
        self.assertIsInstance(graph["languages"]["python"]["functions"], float)
        self.assertIsInstance(graph["concepts"]["recursion"], float)
        self.assertIn("software_engineering", graph)
        self.assertIn("weakest_areas", graph)
        self.assertIn("trend", graph)
