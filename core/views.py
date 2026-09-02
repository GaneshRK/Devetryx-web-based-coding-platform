"""
Devetryx Core Views & API Endpoints.

Implements clean, decoupled controllers delegating to:
- Sandboxed Execution Engine (core.sandbox)
- Model-Agnostic AI Provider (ai_engine)
- Event Telemetry Stream (core.events)
- Skill Graph Engine (core.skills)
"""

import json
import logging
from django.shortcuts import render
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import ContactMessage
from .serializers import RunCodeSerializer, AIMentorRequestSerializer
from .events import (
    emit_event,
    get_recent_events,
    EVENT_CODE_EXECUTED,
    EVENT_COMPILATION_FAILED,
    EVENT_AI_HINT_REQUESTED,
)
from .sandbox.executor import execute_sandboxed_code
from .sandbox.ast_security import validate_code_safety
from .skills.skill_graph import compute_skill_graph, update_skill_snapshot
from ai_engine.provider import (
    get_ai_provider,
    MentorContextPayload,
    MentorFeedbackResponse,
)

logger = logging.getLogger(__name__)


# =========================================================
# TEMPLATE PAGES
# =========================================================

def home(request):
    """Devetryx Landing Page."""
    return render(request, "core/home.html")


def contact(request):
    """Devetryx Contact Page."""
    return render(request, "core/contact.html")


def python_compiler(request):
    """Devetryx Python IDE & Intelligence Studio."""
    return render(request, "compilers/python.html")


@require_POST
def contact_submit(request):
    """Handle contact form submissions."""
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    message = request.POST.get("message", "").strip()

    if not name or not email:
        return JsonResponse({"status": "error", "message": "Name and email are required."}, status=400)

    ContactMessage.objects.create(name=name, email=email, message=message)
    return JsonResponse({"status": "success", "message": "Message sent successfully."})


# =========================================================
# CODE EXECUTION API
# =========================================================

@csrf_exempt
def run_python_code(request):
    """
    Execute user Python code in an isolated sandbox and emit telemetry events.
    Supports both legacy compiler POST requests and JSON API calls.
    """
    if request.method != "POST":
        return JsonResponse({"output": "Method not allowed", "error": "Invalid request method"}, status=405)

    try:
        if request.content_type == "application/json" or request.body:
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except Exception:
                payload = request.POST.dict()
        else:
            payload = request.POST.dict()

        serializer = RunCodeSerializer(data=payload)
        if not serializer.is_valid():
            return JsonResponse({
                "output": "Invalid payload parameters.",
                "errors": serializer.errors,
                "waiting_for_input": False,
            }, status=400)

        data = serializer.validated_data
        files = data["files"]
        main_file = data.get("main_file", "main.py")
        user_input = data.get("user_input", "")
        session_id = data.get("session_id") or request.session.session_key or request.COOKIES.get("sessionid", "anon")
        mode = data.get("mode", "compiler")
        user_id = str(request.user.id) if request.user.is_authenticated else None

        # Execute sandboxed code
        result = execute_sandboxed_code(files=files, main_file=main_file, user_input=user_input)

        ai_provider = get_ai_provider()
        main_code = files.get(main_file, "")
        ast_info = ai_provider.analyze_code_structure(main_code)
        concept_tags = ast_info.get("concept_tags", [])

        # Emit Telemetry Event
        is_failure = result.exit_code != 0 or bool(result.stderr)
        event_type = EVENT_COMPILATION_FAILED if is_failure else EVENT_CODE_EXECUTED
        event_payload = {
            "language": "python",
            "file": main_file,
            "concept_tags": concept_tags,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "has_stderr": bool(result.stderr),
            "functions_count": len(ast_info.get("functions", [])),
            "cyclomatic_complexity": ast_info.get("cyclomatic_complexity", 1),
            "nested_loop_depth": ast_info.get("nested_loop_depth", 0),
        }
        emitted_event = emit_event(
            event_type=event_type,
            payload=event_payload,
            user_id=user_id,
            session_id=session_id,
        )

        # Update Skill snapshot cache
        update_skill_snapshot(session_id=session_id, user_id=user_id)

        # Handle interactive input pauses
        if result.waiting_for_input:
            return JsonResponse({
                "output": result.stdout,
                "stdout": result.stdout,
                "stderr": "",
                "waiting_for_input": True,
                "exit_code": 0,
            })

        # Learning / Mentor Mode augmentation
        mentor_data = None
        if mode in ("mentor", "learning", "analyzer"):
            context = MentorContextPayload(
                user_question="",
                current_file=main_file,
                code=main_code,
                project_structure=list(files.keys()),
                recent_execution={"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.exit_code},
                recent_errors=[result.stderr] if result.stderr else [],
                skill_context={"concept_tags": concept_tags},
                assistance_level=2,  # Default Level 2 Explanation
            )
            feedback = ai_provider.generate_mentor_feedback(context)
            mentor_data = feedback.to_dict()

            output_text = f"{feedback.raw_markdown}\n\n{'='*40}\n📤 Program Output:\n{result.stdout if result.stdout else '(no stdout)'}"
        else:
            output_text = result.stderr if result.stderr else result.stdout

        return JsonResponse({
            "output": output_text,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "waiting_for_input": False,
            "mentor_feedback": mentor_data,
            "event_id": str(emitted_event.id) if emitted_event else None,
        })

    except Exception as e:
        logger.error(f"Error in run_python_code view: {e}", exc_info=True)
        return JsonResponse({
            "output": f"Internal execution worker error: {str(e)}",
            "stdout": "",
            "stderr": str(e),
            "waiting_for_input": False,
        }, status=500)


# =========================================================
# AI MENTOR API (Levels 1 to 5)
# =========================================================

@csrf_exempt
def ai_mentor_view(request):
    """
    Direct endpoint for AI Mentor intelligence queries.
    Respects Assistance Levels 1 (Hint) to 5 (Autonomous), defaulting to Level 2.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        serializer = AIMentorRequestSerializer(data=payload)
        if not serializer.is_valid():
            return JsonResponse({"error": "Invalid request", "details": serializer.errors}, status=400)

        data = serializer.validated_data
        session_id = data.get("session_id") or request.session.session_key or request.COOKIES.get("sessionid", "anon")
        user_id = str(request.user.id) if request.user.is_authenticated else None
        asst_level = data.get("assistance_level", 2)
        current_file = data.get("current_file", "main.py")
        files = data.get("files", {})
        code = data.get("code") or files.get(current_file, "")

        ai_provider = get_ai_provider()
        ast_info = ai_provider.analyze_code_structure(code)

        context = MentorContextPayload(
            user_question=data.get("user_question", ""),
            current_file=current_file,
            code=code,
            project_structure=list(files.keys()) if files else [current_file],
            recent_execution=data.get("recent_execution", {}),
            recent_errors=[data.get("recent_execution", {}).get("stderr", "")] if data.get("recent_execution", {}).get("stderr") else [],
            skill_context={"concept_tags": ast_info.get("concept_tags", [])},
            assistance_level=asst_level,
        )

        feedback = ai_provider.generate_mentor_feedback(context)

        # Emit telemetry event
        emit_event(
            event_type=EVENT_AI_HINT_REQUESTED,
            payload={
                "language": "python",
                "file": current_file,
                "assistance_level": asst_level,
                "user_question": data.get("user_question", ""),
                "concept_tags": feedback.concept_tags,
                "has_solution": bool(feedback.code_suggestion),
            },
            user_id=user_id,
            session_id=session_id,
        )

        update_skill_snapshot(session_id=session_id, user_id=user_id)

        return JsonResponse({
            "status": "success",
            "feedback": feedback.to_dict(),
        })

    except Exception as e:
        logger.error(f"Error in ai_mentor_view: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


# =========================================================
# SKILL GRAPH & TELEMETRY API
# =========================================================

@require_GET
def skill_graph_view(request):
    """
    Retrieve computed Skill Graph matching Part 2.1 schema.
    Gated by sample_size threshold (< 5 -> 'not enough data yet').
    """
    session_id = request.GET.get("session_id") or request.session.session_key or request.COOKIES.get("sessionid", "anon")
    user_id = str(request.user.id) if request.user.is_authenticated else None

    graph_data = compute_skill_graph(session_id=session_id, user_id=user_id)
    return JsonResponse(graph_data)


@require_GET
def events_feed_view(request):
    """Retrieve recent event telemetry feed."""
    session_id = request.GET.get("session_id") or request.session.session_key or request.COOKIES.get("sessionid", "anon")
    user_id = str(request.user.id) if request.user.is_authenticated else None
    limit = int(request.GET.get("limit", 20))

    events = get_recent_events(session_id=session_id, user_id=user_id, limit=limit)
    return JsonResponse({"events": events, "count": len(events)})
