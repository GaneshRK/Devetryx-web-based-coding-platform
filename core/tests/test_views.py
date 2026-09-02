import json
from django.test import TestCase, Client
from django.urls import reverse
from core.models import DevetryxEvent


class ViewsIntegrationTestCase(TestCase):
    """Integration tests for all REST API endpoints."""

    def setUp(self):
        self.client = Client()

    def test_run_python_code_endpoint_success(self):
        payload = {
            "files": {"main.py": "print('Devetryx Platform Test')"},
            "main_file": "main.py",
            "session_id": "test_session_api"
        }
        response = self.client.post(
            reverse("core:run_python"),
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Devetryx Platform Test", data["output"])
        self.assertEqual(data["exit_code"], 0)
        self.assertTrue(DevetryxEvent.objects.filter(session_id="test_session_api").exists())

    def test_run_python_code_blocked_security_endpoint(self):
        payload = {
            "files": {"main.py": "import subprocess\nsubprocess.call(['ls'])"},
            "main_file": "main.py",
            "session_id": "test_session_sec"
        }
        response = self.client.post(
            reverse("core:run_python"),
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Security Guard", data["stderr"])

    def test_ai_mentor_endpoint(self):
        payload = {
            "code": "x = [1, 2]\nprint(x[5])",
            "current_file": "main.py",
            "assistance_level": 2,
            "session_id": "test_session_mentor"
        }
        response = self.client.post(
            reverse("core:ai_mentor"),
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["feedback"]["assistance_level"], 2)

    def test_skill_graph_endpoint(self):
        response = self.client.get(
            reverse("core:skill_graph"),
            {"session_id": "test_session_graph"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("languages", data)
        self.assertIn("concepts", data)

    def test_events_feed_endpoint(self):
        response = self.client.get(
            reverse("core:events_feed"),
            {"session_id": "test_session_feed"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("events", data)
