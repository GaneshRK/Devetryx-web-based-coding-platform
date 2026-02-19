from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .models import ContactMessage

import re
import sys
import json
import tempfile
import subprocess
import os
import ast
import base64
import glob
import uuid
import py_compile
import platform

IS_LINUX = platform.system() == "Linux"

if IS_LINUX:
    import resource

# =========================================================
# CONFIGURATION
# =========================================================

MAX_OUTPUT_SIZE = 8000        # prevent terminal flooding
EXECUTION_TIMEOUT = 20         # seconds
MAX_MEMORY_MB = 256

# =========================================================
# SAFE MODULES
# =========================================================

SAFE_MODULES = {
    "math", "random", "datetime", "statistics",
    "functools", "itertools", "json", "re",
    "string", "time", "typing",
    "numpy", "pandas", "matplotlib",
    "scipy", "sklearn", "sympy", "seaborn",
    "requests"
}

UNSAFE_NAMES = {
    "os", "sys", "subprocess", "shutil",
    "socket", "pathlib", "threading",
    "multiprocessing", "ctypes",
    "importlib", "builtins"
}

UNSAFE_FUNCTIONS = {"eval", "exec", "__import__"}

# =========================================================
# RESOURCE LIMITS (LINUX)
# =========================================================

def limit_resources():
    if not IS_LINUX:
        return  # Windows does not support resource limits

    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(
        resource.RLIMIT_AS,
        (256 * 1024 * 1024,) * 2
    )

# =========================================================
# AST SECURITY CHECK
# =========================================================

def is_safe_import(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return True

    for node in ast.walk(tree):

        # Block dangerous calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in UNSAFE_FUNCTIONS:
                    return False

        # Block unsafe imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in UNSAFE_NAMES or root not in SAFE_MODULES:
                    return False

        if isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in UNSAFE_NAMES or root not in SAFE_MODULES:
                    return False

    return True

# =========================================================
# SYNTAX CHECK
# =========================================================

def syntax_check(path):
    try:
        py_compile.compile(path, doraise=True)
        return None
    except py_compile.PyCompileError as e:
        return str(e)

# =========================================================
# ERROR EXPLANATION
# =========================================================

INJECTED_LINES = 2  # lines added before user code

def explain_error(stderr: str, user_code: str | None = None) -> str:
    if not stderr:
        return ""

    stderr = stderr.strip()

    # --------------------------------------------------
    # Extract traceback line number
    # --------------------------------------------------
    line_no = None
    matches = re.findall(r'File ".*?", line (\d+)', stderr)
    if matches:
        raw_line = int(matches[-1])
        line_no = max(1, raw_line - INJECTED_LINES)

    # --------------------------------------------------
    # Extract error type & message
    # --------------------------------------------------
    lines = [l for l in stderr.splitlines() if l.strip()]
    last_line = lines[-1] if lines else stderr

    if ":" in last_line:
        error_type, error_msg = last_line.split(":", 1)
        error_type = error_type.strip()
        error_msg = error_msg.strip()
    else:
        error_type = last_line.strip()
        error_msg = ""

    # --------------------------------------------------
    # Agent-style explanations
    # --------------------------------------------------
    AGENT_EXPLANATIONS = {
        "NameError": {
            "what": lambda m: f"You tried to use `{extract_name(m)}` but Python does not know what it is.",
            "why": "Python reads code from top to bottom. If a variable is used before being created, this error happens.",
            "fix": "Define the variable before using it, or check for spelling mistakes.",
            "try": "Can you find where this variable should be created?"
        },
        "ZeroDivisionError": {
            "what": lambda _: "Your code tried to divide a number by zero.",
            "why": "Division by zero is mathematically undefined.",
            "fix": "Check the divisor before dividing.",
            "try": "What value is becoming zero here?"
        },
        "IndexError": {
            "what": lambda _: "You accessed a list position that does not exist.",
            "why": "Lists have a fixed size. Indexing beyond it causes this error.",
            "fix": "Check the list length or loop bounds.",
            "try": "How many elements does your list actually have?"
        },
        "TypeError": {
            "what": lambda _: "An operation was applied to incompatible data types.",
            "why": "Some operations only work with specific data types.",
            "fix": "Print the variable types using `type()`.",
            "try": "What data types are involved here?"
        },
        "SyntaxError": {
            "what": lambda _: "Python could not understand this line of code.",
            "why": "There is a syntax rule violation.",
            "fix": "Look for missing colons, brackets, or typos.",
            "try": "Does this line follow Python’s syntax rules?"
        },
        "IndentationError": {
            "what": lambda _: "Your code indentation is inconsistent.",
            "why": "Python uses indentation to define blocks.",
            "fix": "Align spaces consistently.",
            "try": "Are all lines under this block aligned?"
        },
        "KeyError": {
            "what": lambda m: f"You tried to access a dictionary key `{extract_name(m)}` that does not exist.",
            "why": "Dictionaries raise an error when a key is missing.",
            "fix": "Check if the key exists before accessing it.",
            "try": "What keys does this dictionary contain?"
        },
    }

    # --------------------------------------------------
    # Build response
    # --------------------------------------------------
    header = f"❌ {error_type}"
    if line_no:
        header += f" at line {line_no}"

    if error_type in AGENT_EXPLANATIONS:
        info = AGENT_EXPLANATIONS[error_type]

        response = (
            f"{header}\n\n"
            f"🧠 What happened:\n{info['what'](error_msg)}\n\n"
            f"❓ Why this happened:\n{info['why']}\n\n"
            f"🛠 How to fix it:\n{info['fix']}\n\n"
            f"💡 Try this yourself:\n{info['try']}"
        )
        return response

    # --------------------------------------------------
    # Fallback
    # --------------------------------------------------

    return f"{header}\n\nDetails:\n{last_line}"
def extract_name(msg: str) -> str:
    match = re.search(r"'(.*?)'", msg)
    return match.group(1) if match else "this"

# =========================================================
# VIEWS
# =========================================================

def home(request):
    return render(request, "core/home.html")

def contact(request):
    return render(request, "core/contact.html")

@require_POST
def contact_submit(request):
    ContactMessage.objects.create(
        name=request.POST.get("name"),
        email=request.POST.get("email"),
        message=request.POST.get("message")
    )
    return JsonResponse({"status": "success"})

def python_compiler(request):
    return render(request, "compilers/python.html")

# =========================================================
# PYTHON EXECUTOR
# =========================================================
@csrf_exempt
def run_python_code(request):

    if request.method != "POST":
        return JsonResponse({"output": "Invalid request"}, status=405)

    try:
        payload = json.loads(request.body)
        files = payload.get("files", {})
        main_file = payload.get("main_file")
        mode = payload.get("mode", "compiler")
        user_input = payload.get("user_input", "")

        if main_file not in files:
            return JsonResponse({"output": "Main file missing"})

        # ---------------- SECURITY CHECK ----------------
        for code in files.values():
            if not is_safe_import(code):
                return JsonResponse({"output": "❌ Unsafe code detected"})

        # ---------------- EXECUTION ENGINE ----------------
        execution_result = execute_python(files, main_file, user_input)

        stdout = execution_result["stdout"]
        stderr = execution_result["stderr"]

        # Attach user input into output (so it looks natural)
        if user_input:
            stdout = stdout.replace(
                "Enter the maximum number:",
                f"Enter the maximum number: {user_input}"
            )
        # ---------------- CHECK IF WAITING FOR INPUT ----------------
        if "EOFError" in stderr:
            return JsonResponse({
                "output": stdout,
                "waiting_for_input": True
            })

        # ---------------- NORMAL EXECUTION ----------------
        if mode == "compiler":
            output = stderr if stderr else stdout
        else:
            # Learning / Mentor / Analyzer modes
            output = intelligence_router(
                mode=mode,
                code=files[main_file],
                stdout=stdout,
                stderr=stderr
            )

        return JsonResponse({
            "output": output,
            "waiting_for_input": False
        })

    except subprocess.TimeoutExpired:
        return JsonResponse({
            "output": "⏱ Execution timed out",
            "waiting_for_input": False
        })

    except Exception as e:
        return JsonResponse({
            "output": f"Internal error: {str(e)}",
            "waiting_for_input": False
        })

def execute_python(files: dict, main_file: str, user_input=""):

    with tempfile.TemporaryDirectory() as root:
        workspace = os.path.join(root, str(uuid.uuid4()))
        os.mkdir(workspace)

        file_paths = {}

        # Write files
        for name, content in files.items():
            path = os.path.join(workspace, name)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            file_paths[name] = path

            err = syntax_check(path)
            if err:
                return {"stdout": "", "stderr": err}

        # Run main file
        try:
            process = subprocess.Popen(
                [sys.executable, file_paths[main_file]],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workspace,
                text=True,
                preexec_fn=limit_resources if IS_LINUX else None
            )

            if user_input:
                process.stdin.write(user_input + "\n")
                process.stdin.flush()

            try:
                stdout, stderr = process.communicate(timeout=EXECUTION_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
                return {
                    "stdout": "",
                    "stderr": "⏱ Execution timed out"
                }
        except Exception as e:
            return {"stdout": "", "stderr": str(e)}

        return {
            "stdout": stdout[:MAX_OUTPUT_SIZE],
            "stderr": stderr
        }

def intelligence_router(mode, code, stdout, stderr):

    if mode == "compiler":
        return stderr if stderr else stdout

    if stderr:
        return explain_error(stderr, code)

    analysis = advanced_code_analysis(code) or {}

    if mode == "mentor":
        return generate_personalized_feedback(analysis, stdout)

    if mode == "analyzer":
        return generate_personalized_feedback(analysis, stdout)

    if mode == "challenge":
        return generate_challenge(analysis)

    if mode == "explain":
        return explain_logic(code)

    return stdout

def explain_logic(code):
    try:
        tree = ast.parse(code)
    except:
        return "Could not analyze code."

    explanation = ["🧠 Code Explanation:\n"]

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            explanation.append(f"Function defined: {node.name}")
        if isinstance(node, ast.For):
            explanation.append("Loop detected (for-loop).")
        if isinstance(node, ast.While):
            explanation.append("Loop detected (while-loop).")
        if isinstance(node, ast.If):
            explanation.append("Conditional statement detected.")

    return "\n".join(explanation)
def mentor_mode(code, stdout, stderr):

    if stderr:
        return explain_error(stderr, code)

    tree = ast.parse(code)

    loops = sum(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
    functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

    response = ["🎓 Mentor Feedback:\n"]

    if not functions:
        response.append("Try using functions to organize your logic.")

    if loops > 0:
        response.append(f"You used {loops} loop(s). Great for iteration practice!")

    if "input(" not in code:
        response.append("Try making your program interactive using input().")

    response.append("\nProgram Output:")
    response.append(stdout)

    return "\n".join(response)
def analyzer_mode(code, stdout, stderr):

    if stderr:
        return explain_error(stderr, code)

    tree = ast.parse(code)

    loops = sum(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
    conditions = sum(isinstance(n, ast.If) for n in ast.walk(tree))

    response = ["🔬 Code Analysis Report:\n"]

    # Complexity
    if loops >= 2:
        response.append("Estimated Time Complexity: O(n²)")
    elif loops == 1:
        response.append("Estimated Time Complexity: O(n)")
    else:
        response.append("Estimated Time Complexity: O(1)")

    # Code smell
    if len(code.splitlines()) > 40:
        response.append("Code is long. Consider splitting into functions.")

    if conditions > 3:
        response.append("Too many conditionals. Consider refactoring.")

    response.append("\nProgram Output:")
    response.append(stdout)

    return "\n".join(response)

def generate_challenge(analysis):

    response = ["🎯 Adaptive Challenge Mode\n"]

    if analysis["loops"] == 0:
        response.append("Rewrite this program using at least one loop.")
    elif analysis["loops"] == 1:
        response.append("Convert your solution into a recursive approach.")
    else:
        response.append("Optimize nested loops to reduce time complexity.")

    if not analysis["functions"]:
        response.append("Refactor your solution into reusable functions.")

    return "\n".join(response)

def challenge_mode(code, stdout, stderr):

    if stderr:
        return explain_error(stderr, code)

    tree = ast.parse(code)

    loops = sum(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
    recursion = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in [f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)]
        for n in ast.walk(tree)
    )

    response = ["🎯 Personalized Challenge:\n"]

    if loops == 0:
        response.append("Rewrite this program using a loop.")
    elif loops == 1:
        response.append("Can you optimize this to avoid nested loops?")
    else:
        response.append("Try solving the same problem using recursion.")

    if not recursion:
        response.append("Bonus: Implement a recursive version.")

    return "\n".join(response)

# =========================================================
# INTELLIGENCE ENGINE
# =========================================================
def advanced_code_analysis(code: str):
    analysis = {
        "functions": [],
        "loops": 0,
        "nested_loop_depth": 0,
        "conditions": 0,
        "recursion": False,
        "list_comp": 0,
        "variables": set(),
        "used_variables": set(),
        "cyclomatic_complexity": 1,
        "unused_variables": []
    }

    try:
        tree = ast.parse(code)
    except Exception:
        return {
            "functions": [],
            "loops": 0,
            "nested_loop_depth": 0,
            "conditions": 0,
            "recursion": False,
            "list_comp": 0,
            "variables": set(),
            "used_variables": set(),
            "cyclomatic_complexity": 1,
            "unused_variables": []
        }
    loop_stack = 0
    max_loop_depth = 0

    for node in ast.walk(tree):

        # Functions
        if isinstance(node, ast.FunctionDef):
            analysis["functions"].append(node.name)

        # Loops
        if isinstance(node, (ast.For, ast.While)):
            analysis["loops"] += 1
            loop_stack += 1
            max_loop_depth = max(max_loop_depth, loop_stack)

        # Conditions
        if isinstance(node, ast.If):
            analysis["conditions"] += 1
            analysis["cyclomatic_complexity"] += 1

        # List Comprehension
        if isinstance(node, ast.ListComp):
            analysis["list_comp"] += 1

        # Variables declared
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            analysis["variables"].add(node.id)

        # Variables used
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            analysis["used_variables"].add(node.id)

    analysis["nested_loop_depth"] = max_loop_depth

    # Recursion detection
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in analysis["functions"]:
                analysis["recursion"] = True

    # Unused variables
    analysis["unused_variables"] = list(
        analysis["variables"] - analysis["used_variables"]
    )

    return analysis
def calculate_skill_score(analysis: dict):
    score = 0

    score += len(analysis["functions"]) * 10
    score += analysis["loops"] * 5
    score += analysis["conditions"] * 3
    score += analysis["list_comp"] * 7

    if analysis["recursion"]:
        score += 15

    if analysis["nested_loop_depth"] >= 2:
        score += 10

    score += analysis["cyclomatic_complexity"] * 2

    return min(score, 100)

def generate_personalized_feedback(analysis, stdout):
    if not analysis:
        return stdout

    response = []
    score = calculate_skill_score(analysis)

    response.append("🧠 Devetryx Intelligence Report\n")
    response.append(f"🎯 Skill Score: {score}/100\n")

    # Level Detection
    if score < 25:
        level = "Beginner"
    elif score < 60:
        level = "Intermediate"
    else:
        level = "Advanced"

    response.append(f"📊 Level Detected: {level}\n")

    # Structure feedback
    if not analysis["functions"]:
        response.append("💡 Tip: Use functions to modularize your logic.")

    if analysis["unused_variables"]:
        response.append(
            f"⚠️ Unused variables detected: {', '.join(analysis['unused_variables'])}"
        )

    if analysis["nested_loop_depth"] >= 2:
        response.append("⚠️ Deep nested loops detected. Consider optimization.")

    if analysis["cyclomatic_complexity"] > 10:
        response.append("⚠️ High cyclomatic complexity. Refactor for readability.")

    if analysis["recursion"]:
        response.append("🧠 Good job using recursion.")

    if analysis["list_comp"] > 0:
        response.append("⚡ Nice use of list comprehension.")

    # Learning Roadmap
    response.append("\n🚀 Improvement Roadmap:")

    if level == "Beginner":
        response.append("- Practice loops and conditional statements.")
        response.append("- Learn to write reusable functions.")
    elif level == "Intermediate":
        response.append("- Study algorithm optimization.")
        response.append("- Practice recursion and data structures.")
    else:
        response.append("- Focus on clean architecture.")
        response.append("- Improve time and space complexity awareness.")

    response.append("\n📤 Program Output:")
    response.append(stdout[:3000])

    return "\n".join(response)
