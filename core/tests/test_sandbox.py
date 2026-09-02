from django.test import TestCase
from core.sandbox.ast_security import validate_code_safety
from core.sandbox.executor import execute_sandboxed_code


class SandboxSecurityTestCase(TestCase):
    """Tests AST-level security filtering and isolation."""

    def test_safe_code_passes_ast_check(self):
        code = "import math\nx = math.sqrt(16)\nprint(x)"
        is_safe, err = validate_code_safety(code)
        self.assertTrue(is_safe)
        self.assertIsNone(err)

    def test_blocked_os_import(self):
        code = "import os\nos.system('dir')"
        is_safe, err = validate_code_safety(code)
        self.assertFalse(is_safe)
        self.assertIn("Disallowed import detected: `os`", err)

    def test_blocked_subprocess_import(self):
        code = "from subprocess import Popen"
        is_safe, err = validate_code_safety(code)
        self.assertFalse(is_safe)
        self.assertIn("Disallowed import detected", err)

    def test_blocked_eval_call(self):
        code = "user_input = '1+1'\nres = eval(user_input)"
        is_safe, err = validate_code_safety(code)
        self.assertFalse(is_safe)
        self.assertIn("Disallowed function call detected: `eval()`", err)

    def test_blocked_open_call(self):
        code = "with open('/etc/passwd', 'r') as f:\n    print(f.read())"
        is_safe, err = validate_code_safety(code)
        self.assertFalse(is_safe)
        self.assertIn("Disallowed function call detected: `open()`", err)

    def test_blocked_dunder_subclasses_access(self):
        code = "x = ().__class__.__subclasses__()"
        is_safe, err = validate_code_safety(code)
        self.assertFalse(is_safe)
        self.assertIn("Disallowed attribute access", err)


class SandboxExecutionTestCase(TestCase):
    """Tests subprocess execution, multi-file workspaces, timeouts, and stdin."""

    def test_execute_simple_python_code(self):
        files = {"main.py": "print('Hello Devetryx Sandbox!')"}
        result = execute_sandboxed_code(files=files, main_file="main.py")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Hello Devetryx Sandbox!", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_execute_multi_file_project(self):
        files = {
            "helper.py": "def add(a, b):\n    return a + b",
            "main.py": "from helper import add\nprint('Result:', add(10, 25))"
        }
        result = execute_sandboxed_code(files=files, main_file="main.py")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Result: 35", result.stdout)

    def test_blocked_execution_for_unsafe_code(self):
        files = {"main.py": "import os\nprint(os.name)"}
        result = execute_sandboxed_code(files=files, main_file="main.py")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Security Guard", result.stderr)

    def test_timeout_protection(self):
        files = {"main.py": "import time\nwhile True:\n    time.sleep(0.1)"}
        result = execute_sandboxed_code(files=files, main_file="main.py", timeout=1)
        self.assertTrue(result.timed_out)
        self.assertIn("timed out", result.stderr)

    def test_interactive_stdin_execution(self):
        files = {"main.py": "name = input('Name: ')\nprint('Greetings, ' + name)"}
        result = execute_sandboxed_code(files=files, main_file="main.py", user_input="Alice")
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Greetings, Alice", result.stdout)
