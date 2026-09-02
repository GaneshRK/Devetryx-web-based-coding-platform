"""
Devetryx Sandboxed Subprocess Executor.

Executes user code strictly inside an isolated worker subprocess with
time caps, output buffer limits, and temporary isolated workspaces.
"""

from __future__ import annotations
import ast
import dataclasses
import os
import platform
import subprocess
import sys
import tempfile
import uuid
from typing import Any, Dict, Optional, Set

from .ast_security import validate_code_safety, syntax_check

IS_LINUX = platform.system() == "Linux"

if IS_LINUX:
    import resource


def limit_resources():
    """Apply OS-level CPU & Memory resource bounds (Linux)."""
    if not IS_LINUX:
        return
    # 5 seconds of CPU time
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    # 256 MB of address space
    resource.setrlimit(
        resource.RLIMIT_AS,
        (256 * 1024 * 1024, 256 * 1024 * 1024)
    )


MAX_OUTPUT_SIZE = 8000
EXECUTION_TIMEOUT = 10  # seconds


@dataclasses.dataclass
class ExecutionResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    security_error: Optional[str] = None
    waiting_for_input: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "security_error": self.security_error,
            "waiting_for_input": self.waiting_for_input,
        }


def execute_sandboxed_code(
    files: Dict[str, str],
    main_file: str = "main.py",
    user_input: str = "",
    timeout: int = EXECUTION_TIMEOUT,
) -> ExecutionResult:
    """
    Execute user Python code in an isolated temporary directory via subprocess.

    Args:
        files: Dictionary of filename -> file content.
        main_file: Entry point file name.
        user_input: Interactive standard input stream string.
        timeout: Execution timeout limit in seconds.

    Returns:
        ExecutionResult object.
    """
    if not files or main_file not in files:
        return ExecutionResult(
            stderr=f"Entry point '{main_file}' not found in submitted files.",
            exit_code=1
        )

    # Compute allowed custom modules from other local project files
    custom_modules: Set[str] = set()
    for name in files.keys():
        if name.endswith(".py"):
            base = name[:-3]
            custom_modules.add(base)

    # 1. AST Security Inspection on all files
    for fname, content in files.items():
        if fname.endswith(".py"):
            is_safe, error_reason = validate_code_safety(content, allow_custom_modules=custom_modules)
            if not is_safe:
                return ExecutionResult(
                    stderr=f"🛡️ Security Guard: {error_reason}",
                    exit_code=1,
                    security_error=error_reason
                )

    # 2. Setup isolated ephemeral workspace
    with tempfile.TemporaryDirectory() as root_temp:
        workspace_dir = os.path.join(root_temp, f"workspace_{uuid.uuid4().hex}")
        os.makedirs(workspace_dir, exist_ok=True)

        file_paths = {}
        for fname, content in files.items():
            # Prevent path traversal in filenames
            safe_basename = os.path.basename(fname)
            fpath = os.path.join(workspace_dir, safe_basename)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            file_paths[safe_basename] = fpath

            # Syntax pre-check
            if safe_basename.endswith(".py"):
                syntax_err = syntax_check(fpath)
                if syntax_err:
                    return ExecutionResult(
                        stderr=syntax_err,
                        exit_code=1
                    )

        target_file_path = file_paths.get(main_file)
        if not target_file_path or not os.path.exists(target_file_path):
            return ExecutionResult(
                stderr=f"Main entry point '{main_file}' could not be resolved.",
                exit_code=1
            )

        # 3. Subprocess execution in sandbox
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", target_file_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workspace_dir,
                text=True,
                preexec_fn=limit_resources if IS_LINUX else None
            )

            stdin_data = user_input + ("\n" if user_input and not user_input.endswith("\n") else "")
            
            try:
                stdout_data, stderr_data = process.communicate(
                    input=stdin_data if user_input else None,
                    timeout=timeout
                )
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_data, stderr_data = process.communicate()
                return ExecutionResult(
                    stdout=stdout_data[:MAX_OUTPUT_SIZE] if stdout_data else "",
                    stderr="⏱️ Execution timed out (exceeded limit).",
                    exit_code=124,
                    timed_out=True
                )

            # Check if execution paused waiting for interactive input (EOFError on empty stdin with input() call)
            waiting_input = False
            if "EOFError: EOF when reading a line" in (stderr_data or ""):
                waiting_input = True
                # Clean up the EOFError from stderr so prompt appears natural
                stderr_data = ""

            return ExecutionResult(
                stdout=(stdout_data or "")[:MAX_OUTPUT_SIZE],
                stderr=(stderr_data or "")[:MAX_OUTPUT_SIZE],
                exit_code=process.returncode,
                waiting_for_input=waiting_input
            )

        except Exception as e:
            return ExecutionResult(
                stderr=f"Execution worker failure: {str(e)}",
                exit_code=1
            )
