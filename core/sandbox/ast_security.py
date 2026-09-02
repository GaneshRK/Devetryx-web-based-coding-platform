"""
Devetryx AST Security Validator.

Validates user submitted Python source code before execution:
- Import whitelisting and unsafe module blocking
- Dangerous builtin function calls blocking (eval, exec, __import__, open)
- Dunder attribute exploitation prevention (__subclasses__, __globals__, etc.)
- AST node complexity thresholds
"""

from __future__ import annotations
import ast
import py_compile
import tempfile
import os
from typing import Optional, Set, Tuple


class SecurityViolation(Exception):
    """Raised when user code violates security boundaries."""
    pass


SAFE_MODULES: Set[str] = {
    "math", "random", "datetime", "statistics",
    "functools", "itertools", "json", "re",
    "string", "time", "typing", "collections",
    "heapq", "bisect", "copy", "decimal", "fractions",
    "numpy", "pandas", "matplotlib",
    "scipy", "sklearn", "sympy", "seaborn",
}

BLOCKED_MODULES: Set[str] = {
    "os", "sys", "subprocess", "shutil", "socket",
    "pathlib", "threading", "multiprocessing",
    "ctypes", "importlib", "builtins", "signal",
    "pty", "fcntl", "posix", "winreg", "msvcrt",
    "webbrowser", "http", "urllib", "urllib3",
    "pickle", "shelve", "marshal", "sqlite3"
}

BLOCKED_FUNCTIONS: Set[str] = {
    "eval", "exec", "__import__", "open",
    "compile", "globals", "locals",
    "breakpoint", "help", "quit", "exit"
}

BLOCKED_ATTRIBUTES: Set[str] = {
    "__subclasses__", "__bases__", "__mro__",
    "__globals__", "__code__", "__builtins__",
    "__import__", "__class__"
}

MAX_AST_NODES = 25000


def validate_code_safety(code: str, allow_custom_modules: Optional[Set[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    Statically inspect code AST to detect dangerous patterns.

    Args:
        code: The Python source code.
        allow_custom_modules: Set of local filenames (e.g. {'helper', 'utils'}) that are safe to import.

    Returns:
        (is_safe, error_reason)
    """
    if not code or not code.strip():
        return True, None

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        # Let execution engine handle syntax error cleanly
        return True, None
    except Exception as e:
        return False, f"AST parse failed: {str(e)}"

    node_count = 0
    local_allowed = allow_custom_modules or set()

    for node in ast.walk(tree):
        node_count += 1
        if node_count > MAX_AST_NODES:
            return False, "Code exceeds maximum structural complexity limit."

        # 1. Check Function Calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in BLOCKED_FUNCTIONS:
                    return False, f"Disallowed function call detected: `{func_name}()`."

        # 2. Check Attribute Access (e.g. obj.__class__.__subclasses__())
        if isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRIBUTES:
                return False, f"Disallowed attribute access detected: `.{node.attr}`."

        # 3. Check `import xyz`
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module in BLOCKED_MODULES:
                    return False, f"Disallowed import detected: `{root_module}`."
                if root_module not in SAFE_MODULES and root_module not in local_allowed:
                    return False, f"Module `{root_module}` is not in the allowed security whitelist."

        # 4. Check `from xyz import abc`
        if isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module in BLOCKED_MODULES:
                    return False, f"Disallowed import detected: `from {root_module} import ...`."
                if root_module not in SAFE_MODULES and root_module not in local_allowed:
                    return False, f"Module `{root_module}` is not in the allowed security whitelist."

    return True, None


def syntax_check(file_path: str) -> Optional[str]:
    """Check Python syntax via compilation without running code."""
    try:
        py_compile.compile(file_path, doraise=True)
        return None
    except py_compile.PyCompileError as e:
        return str(e)
