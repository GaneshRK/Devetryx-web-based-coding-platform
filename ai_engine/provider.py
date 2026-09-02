"""
Devetryx AI Engine Provider.

Internal model-agnostic interface for AI mentor, error explanations, and code intelligence.
Feature code ONLY interacts with this interface, never with external vendor SDKs directly.
"""

from __future__ import annotations
import abc
import ast
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "v1"


@dataclass
class MentorContextPayload:
    """
    Context payload matching Part 2.2 schema.
    """
    user_question: str = ""
    current_file: str = "main.py"
    code: str = ""
    project_structure: List[str] = field(default_factory=list)
    recent_execution: Dict[str, Any] = field(default_factory=dict)
    recent_errors: List[str] = field(default_factory=list)
    skill_context: Dict[str, Any] = field(default_factory=dict)
    assistance_level: int = 2  # Level 1 to 5, default to 2 (Explanation)


@dataclass
class MentorFeedbackResponse:
    """
    Structured feedback response returned by the AI provider.
    """
    assistance_level: int
    level_name: str
    headline: str
    root_cause: str
    concept_explanation: str
    actionable_guidance: str
    code_suggestion: Optional[str] = None
    suggested_exercise: Optional[str] = None
    concept_tags: List[str] = field(default_factory=list)
    raw_markdown: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assistance_level": self.assistance_level,
            "level_name": self.level_name,
            "headline": self.headline,
            "root_cause": self.root_cause,
            "concept_explanation": self.concept_explanation,
            "actionable_guidance": self.actionable_guidance,
            "code_suggestion": self.code_suggestion,
            "suggested_exercise": self.suggested_exercise,
            "concept_tags": self.concept_tags,
            "raw_markdown": self.raw_markdown,
        }


ASSISTANCE_LEVEL_NAMES = {
    1: "Hint",
    2: "Explanation",
    3: "Guided Fix",
    4: "Suggested Solution",
    5: "Autonomous",
}


def load_prompt_template(filename: str) -> str:
    """Load versioned prompt template from disk."""
    prompt_path = PROMPTS_DIR / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return ""


class AIProvider(abc.ABC):
    """
    Abstract internal AI Provider interface.
    """

    @abc.abstractmethod
    def generate_mentor_feedback(self, context: MentorContextPayload) -> MentorFeedbackResponse:
        """Generate structured mentor feedback for a given context payload."""
        pass

    @abc.abstractmethod
    def analyze_code_structure(self, code: str) -> Dict[str, Any]:
        """Perform AST and code structural analysis."""
        pass


class DeterministicProvider(AIProvider):
    """
    Deterministic/Heuristic provider.
    Runs locally with zero external API dependencies using AST parsing,
    traceback inspection, and pedagogical rule trees.
    """

    def analyze_code_structure(self, code: str) -> Dict[str, Any]:
        result = {
            "functions": [],
            "classes": [],
            "loops": 0,
            "nested_loop_depth": 0,
            "conditions": 0,
            "recursion": False,
            "list_comp": 0,
            "variables": set(),
            "used_variables": set(),
            "cyclomatic_complexity": 1,
            "unused_variables": [],
            "concept_tags": [],
            "syntax_valid": True,
            "syntax_error": None,
        }

        if not code or not code.strip():
            return result

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            result["syntax_valid"] = False
            result["syntax_error"] = str(e)
            result["concept_tags"].append("syntax")
            return result
        except Exception as e:
            result["syntax_valid"] = False
            result["syntax_error"] = str(e)
            return result

        loop_stack = 0
        max_loop_depth = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result["functions"].append(node.name)
                result["concept_tags"].append("functions")

            elif isinstance(node, ast.ClassDef):
                result["classes"].append(node.name)
                result["concept_tags"].append("oop")

            elif isinstance(node, (ast.For, ast.While)):
                result["loops"] += 1
                loop_stack += 1
                max_loop_depth = max(max_loop_depth, loop_stack)
                result["concept_tags"].append("loops")

            elif isinstance(node, ast.If):
                result["conditions"] += 1
                result["cyclomatic_complexity"] += 1
                result["concept_tags"].append("conditionals")

            elif isinstance(node, ast.ListComp):
                result["list_comp"] += 1
                result["concept_tags"].append("list_comprehension")

            elif isinstance(node, ast.Try):
                result["concept_tags"].append("error_handling")

            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                result["variables"].add(node.id)

            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                result["used_variables"].add(node.id)

        result["nested_loop_depth"] = max_loop_depth
        if max_loop_depth >= 2:
            result["concept_tags"].append("nested_loops")

        # Detect recursion
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in result["functions"]:
                    result["recursion"] = True
                    result["concept_tags"].append("recursion")
                    break

        result["unused_variables"] = list(result["variables"] - result["used_variables"])
        result["variables"] = list(result["variables"])
        result["used_variables"] = list(result["used_variables"])
        result["concept_tags"] = list(set(result["concept_tags"]))

        return result

    def _extract_traceback_details(self, stderr: str) -> Dict[str, Any]:
        """Extract line number, exception type, and message from traceback."""
        if not stderr:
            return {"error_type": "", "error_msg": "", "line_no": None}

        stderr_clean = stderr.strip()
        line_no = None
        matches = re.findall(r'File ".*?", line (\d+)', stderr_clean)
        if matches:
            line_no = int(matches[-1])

        lines = [l for l in stderr_clean.splitlines() if l.strip()]
        last_line = lines[-1] if lines else stderr_clean

        if ":" in last_line:
            parts = last_line.split(":", 1)
            error_type = parts[0].strip()
            error_msg = parts[1].strip()
        else:
            error_type = last_line.strip()
            error_msg = ""

        return {"error_type": error_type, "error_msg": error_msg, "line_no": line_no}

    def generate_mentor_feedback(self, context: MentorContextPayload) -> MentorFeedbackResponse:
        level = max(1, min(5, context.assistance_level or 2))
        level_name = ASSISTANCE_LEVEL_NAMES.get(level, "Explanation")

        stderr = context.recent_execution.get("stderr", "") or ""
        stdout = context.recent_execution.get("stdout", "") or ""
        code = context.code or ""
        ast_info = self.analyze_code_structure(code)

        tb = self._extract_traceback_details(stderr)
        error_type = tb["error_type"]
        error_msg = tb["error_msg"]
        line_no = tb["line_no"]

        concept_tags = list(ast_info.get("concept_tags", []))

        # Handle runtime / syntax error cases
        if error_type:
            if error_type not in concept_tags:
                concept_tags.append(error_type.lower())

            return self._build_error_feedback(
                level=level,
                level_name=level_name,
                error_type=error_type,
                error_msg=error_msg,
                line_no=line_no,
                code=code,
                context=context,
                concept_tags=concept_tags,
            )

        # Handle successful run (clean output or code coaching)
        return self._build_growth_feedback(
            level=level,
            level_name=level_name,
            ast_info=ast_info,
            stdout=stdout,
            code=code,
            context=context,
            concept_tags=concept_tags,
        )

    def _build_error_feedback(
        self,
        level: int,
        level_name: str,
        error_type: str,
        error_msg: str,
        line_no: Optional[int],
        code: str,
        context: MentorContextPayload,
        concept_tags: List[str],
    ) -> MentorFeedbackResponse:
        line_str = f" at line {line_no}" if line_no else ""
        headline = f"🔍 {error_type}{line_str}"

        # Pedagogical database of error explanations
        error_catalog = {
            "NameError": {
                "concept": "Variable Scope & Lifecycle",
                "root_cause": f"Python encountered an identifier `{error_msg}` that has not been defined in current scope.",
                "explanation": "Python executes code sequentially. Before a name is referenced, it must be assigned a value or imported.",
                "hint": f"Look at line {line_no or 'above'}. Check if the variable name is spelled correctly or defined before this line.",
                "guided_fix": "1. Verify variable spelling.\n2. Ensure initialization occurs prior to usage.\n3. Check indentation if declared inside a block.",
                "solution_template": "# Ensure declaration precedes usage:\nmy_var = ...\n# Then call or use my_var",
            },
            "TypeError": {
                "concept": "Type System & Operations",
                "root_cause": f"Incompatible types were combined or passed to a function: {error_msg}",
                "explanation": "Different data types support different operations (e.g. adding string to integer requires explicit conversion via `int()` or `str()`).",
                "hint": "Check the types of the variables involved using `type(x)` or ensure explicit type casting.",
                "guided_fix": "1. Inspect operands.\n2. Use `str()` or `int()` to convert variables to compatible types before operating.",
                "solution_template": "# Example type conversion:\nresult = str(val1) + str(val2)",
            },
            "IndexError": {
                "concept": "Zero-Indexed Sequences & Bounds",
                "root_cause": f"Attempted to access an index outside the boundaries of a sequence: {error_msg}",
                "explanation": "Sequences in Python are 0-indexed (valid indices from 0 to len-1). Accessing an index >= len raises an IndexError.",
                "hint": "Check the length of your list with `len(...)` and ensure your index is strictly less than the length.",
                "guided_fix": "1. Check `len(my_list)` before indexing.\n2. In loops, prefer `for item in my_list:` over manual index tracking.",
                "solution_template": "if index < len(my_list):\n    item = my_list[index]",
            },
            "ZeroDivisionError": {
                "concept": "Arithmetic Domain Guard",
                "root_cause": "The divisor in a division or modulo operation evaluated to 0.",
                "explanation": "Division by zero is mathematically undefined and cannot produce a numeric result.",
                "hint": "Check the denominator expression and verify what causes it to become 0.",
                "guided_fix": "Add a conditional check before dividing:\n`if divisor != 0: ... else: ...`",
                "solution_template": "if divisor != 0:\n    result = numerator / divisor\nelse:\n    result = 0",
            },
            "SyntaxError": {
                "concept": "Python Grammar Rules",
                "root_cause": f"Invalid syntax encountered by Python parser: {error_msg}",
                "explanation": "Python expects specific structural grammar such as colons after `if`/`for`/`def`, matching parenthesis, and valid tokens.",
                "hint": f"Inspect line {line_no}. Check for missing colons `:`, unclosed quotes `\"`, or unclosed brackets `)`.",
                "guided_fix": "1. Look at the end of the line for a colon `:`.\n2. Match all opening and closing parentheses `()` and brackets `[]`.",
                "solution_template": "# Ensure proper colons and bracket matching:\ndef example():\n    if True:\n        pass",
            },
            "IndentationError": {
                "concept": "Block Scoping via Whitespace",
                "root_cause": "Inconsistent or missing indentation level.",
                "explanation": "Python does not use curly braces `{}` for code blocks; it uses consistent indentation (standard is 4 spaces).",
                "hint": f"Check line {line_no} and the preceding lines to make sure whitespace levels match consistently.",
                "guided_fix": "Ensure all lines within the same function or loop block use exactly 4 spaces indentation.",
                "solution_template": "def my_func():\n    # 4 spaces indentation\n    statement_1\n    statement_2",
            },
            "KeyError": {
                "concept": "Dictionary Key Lookup",
                "root_cause": f"Dictionary lookup failed for key: {error_msg}",
                "explanation": "Accessing `dict[key]` directly raises a KeyError if the key does not exist.",
                "hint": "Use `.get(key, default)` or verify membership with `if key in dict:`.",
                "guided_fix": "Replace direct bracket access with `my_dict.get(key)` or guard with `if key in my_dict:`.",
                "solution_template": "value = my_dict.get(key, 'default_value')",
            },
        }

        entry = error_catalog.get(error_type, {
            "concept": "Python Error Handling",
            "root_cause": f"Exception raised: {error_msg or error_type}",
            "explanation": "An unhandled exception occurred during execution.",
            "hint": f"Examine the traceback at line {line_no or 'the highlighted section'}.",
            "guided_fix": "Review the variables and function calls near the line where the error occurred.",
            "solution_template": "# Review and guard against unexpected state",
        })

        # Apply Assistance Levels (Principle 2: AI explains before it replaces)
        if level == 1:
            # Level 1: Hint only
            root_cause = "Issue detected during execution."
            concept_exp = f"Concept: {entry['concept']}"
            guidance = entry["hint"]
            code_sugg = None
            exercise = f"Can you fix the issue at line {line_no or 'in your code'} without looking up the answer?"

        elif level == 2:
            # Level 2 (Default): Full root cause + concept explanation, NO direct code replacement
            root_cause = entry["root_cause"]
            concept_exp = entry["explanation"]
            guidance = f"{entry['hint']}\n\n💡 Next step: {entry['guided_fix']}"
            code_sugg = None
            exercise = f"Refactor your logic to guard against {error_type} in future edge cases."

        elif level == 3:
            # Level 3: Guided fix
            root_cause = entry["root_cause"]
            concept_exp = entry["explanation"]
            guidance = entry["guided_fix"]
            code_sugg = entry["solution_template"]
            exercise = "Apply the guided changes to your file and run again."

        elif level >= 4:
            # Level 4/5: Full solution (explicit opt-in)
            root_cause = entry["root_cause"]
            concept_exp = entry["explanation"]
            guidance = "⚠️ Full solution provided below. Relying on auto-solutions reduces long-term skill retention."
            code_sugg = entry["solution_template"]
            exercise = "Study the solution, then try rewriting it without referring to this suggestion."

        raw_md = (
            f"### {headline}\n\n"
            f"**Assistance Level {level}: {level_name}**\n\n"
            f"**🧠 Root Cause:** {root_cause}\n\n"
            f"**📚 Concept ({entry['concept']}):** {concept_exp}\n\n"
            f"**🛠 Guidance:**\n{guidance}\n\n"
        )
        if code_sugg:
            raw_md += f"**💻 Suggested Pattern:**\n```python\n{code_sugg}\n```\n\n"
        if exercise:
            raw_md += f"**🎯 Active Practice:** {exercise}"

        return MentorFeedbackResponse(
            assistance_level=level,
            level_name=level_name,
            headline=headline,
            root_cause=root_cause,
            concept_explanation=concept_exp,
            actionable_guidance=guidance,
            code_suggestion=code_sugg,
            suggested_exercise=exercise,
            concept_tags=concept_tags,
            raw_markdown=raw_md,
        )

    def _build_growth_feedback(
        self,
        level: int,
        level_name: str,
        ast_info: Dict[str, Any],
        stdout: str,
        code: str,
        context: MentorContextPayload,
        concept_tags: List[str],
    ) -> MentorFeedbackResponse:
        headline = "✨ Clean Execution & Code Intelligence Analysis"
        insights = []

        if not ast_info.get("functions"):
            insights.append("• Consider modularizing your code into reusable functions (`def`).")
        else:
            insights.append(f"• Great job using functions ({', '.join(ast_info['functions'])}).")

        if ast_info.get("recursion"):
            insights.append("• Recursion detected! Good use of self-referential algorithmic logic.")

        if ast_info.get("nested_loop_depth", 0) >= 2:
            insights.append("• ⚠️ Nested loop depth >= 2 detected (O(n²) time complexity). Consider hash maps or sets.")

        if ast_info.get("unused_variables"):
            insights.append(f"• 💡 Unused variables detected: {', '.join(ast_info['unused_variables'])}.")

        if not insights:
            insights.append("• Code structure looks clean and well formatted.")

        root_cause = "Code ran successfully with no uncaught exceptions."
        concept_exp = "Code modularity, clean variable lifecycle, and algorithmic efficiency."
        guidance = "\n".join(insights)
        exercise = "Can you add unit tests or edge case handling to verify your algorithm under boundary conditions?"

        raw_md = (
            f"### {headline}\n\n"
            f"**Assistance Level {level}: {level_name}**\n\n"
            f"**🧠 Performance & Structure:**\n{guidance}\n\n"
            f"**🎯 Next Challenge:** {exercise}"
        )

        return MentorFeedbackResponse(
            assistance_level=level,
            level_name=level_name,
            headline=headline,
            root_cause=root_cause,
            concept_explanation=concept_exp,
            actionable_guidance=guidance,
            code_suggestion=None,
            suggested_exercise=exercise,
            concept_tags=concept_tags,
            raw_markdown=raw_md,
        )


class LLMProvider(AIProvider):
    """
    Pluggable external LLM Provider (e.g. OpenAI / Anthropic / Gemini).
    Falls back gracefully to DeterministicProvider if API keys are missing or calls fail.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("DEVETRYX_AI_API_KEY")
        self.model = model
        self.fallback = DeterministicProvider()

    def analyze_code_structure(self, code: str) -> Dict[str, Any]:
        return self.fallback.analyze_code_structure(code)

    def generate_mentor_feedback(self, context: MentorContextPayload) -> MentorFeedbackResponse:
        if not self.api_key:
            # Fall back directly to deterministic provider if no key configured
            return self.fallback.generate_mentor_feedback(context)

        try:
            # When vendor keys are configured, construct model-agnostic request
            # For now, deterministic fallback ensures 100% offline reliability in Phase 1
            return self.fallback.generate_mentor_feedback(context)
        except Exception as e:
            logger.warning(f"LLM call failed, falling back to deterministic provider: {e}")
            return self.fallback.generate_mentor_feedback(context)


_GLOBAL_PROVIDER: Optional[AIProvider] = None


def get_ai_provider() -> AIProvider:
    """
    Internal factory for getting the active AI Provider.
    Swapping providers touches this file only.
    """
    global _GLOBAL_PROVIDER
    if _GLOBAL_PROVIDER is None:
        api_key = os.environ.get("DEVETRYX_AI_API_KEY")
        if api_key:
            _GLOBAL_PROVIDER = LLMProvider(api_key=api_key)
        else:
            _GLOBAL_PROVIDER = DeterministicProvider()
    return _GLOBAL_PROVIDER
