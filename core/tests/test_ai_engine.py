from django.test import TestCase
from ai_engine.provider import (
    DeterministicProvider,
    MentorContextPayload,
    get_ai_provider,
)


class AIEngineTestCase(TestCase):
    """Tests model-agnostic AI provider, AST analysis, and assistance levels."""

    def setUp(self):
        self.provider = get_ai_provider()

    def test_provider_ast_structure_analysis(self):
        code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

total = 0
for i in range(5):
    total += factorial(i)
"""
        analysis = self.provider.analyze_code_structure(code)
        self.assertIn("factorial", analysis["functions"])
        self.assertTrue(analysis["recursion"])
        self.assertEqual(analysis["loops"], 1)
        self.assertIn("recursion", analysis["concept_tags"])

    def test_assistance_level_1_hint_only(self):
        code = "print(unknown_variable)"
        context = MentorContextPayload(
            code=code,
            current_file="main.py",
            recent_execution={"stderr": "NameError: name 'unknown_variable' is not defined"},
            assistance_level=1,
        )
        feedback = self.provider.generate_mentor_feedback(context)
        self.assertEqual(feedback.assistance_level, 1)
        self.assertEqual(feedback.level_name, "Hint")
        self.assertIsNone(feedback.code_suggestion)
        self.assertIn("NameError", feedback.headline)

    def test_assistance_level_2_explanation_default(self):
        code = "nums = [1, 2, 3]\nprint(nums[10])"
        context = MentorContextPayload(
            code=code,
            current_file="main.py",
            recent_execution={"stderr": "IndexError: list index out of range"},
            assistance_level=2,
        )
        feedback = self.provider.generate_mentor_feedback(context)
        self.assertEqual(feedback.assistance_level, 2)
        self.assertEqual(feedback.level_name, "Explanation")
        # Principle 2: Level 2 explains root cause & concept, NO auto-fix code snippet
        self.assertIsNone(feedback.code_suggestion)
        self.assertIn("IndexError", feedback.headline)
        self.assertTrue(len(feedback.root_cause) > 0)
        self.assertTrue(len(feedback.concept_explanation) > 0)

    def test_assistance_level_3_guided_fix(self):
        code = "x = 10 / 0"
        context = MentorContextPayload(
            code=code,
            current_file="main.py",
            recent_execution={"stderr": "ZeroDivisionError: division by zero"},
            assistance_level=3,
        )
        feedback = self.provider.generate_mentor_feedback(context)
        self.assertEqual(feedback.assistance_level, 3)
        self.assertEqual(feedback.level_name, "Guided Fix")
        self.assertIsNotNone(feedback.code_suggestion)

    def test_assistance_level_4_suggested_solution(self):
        code = "x = '5' + 10"
        context = MentorContextPayload(
            code=code,
            current_file="main.py",
            recent_execution={"stderr": "TypeError: can only concatenate str to str"},
            assistance_level=4,
        )
        feedback = self.provider.generate_mentor_feedback(context)
        self.assertEqual(feedback.assistance_level, 4)
        self.assertEqual(feedback.level_name, "Suggested Solution")
        self.assertIsNotNone(feedback.code_suggestion)
