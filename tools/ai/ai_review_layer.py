#!/usr/bin/env python3
"""
OSGuide AI Review Layer
-----------------------
Read-only Groq review helper used by the OSGuide AI Review Bridge.

Core rules:
- Never edits OSGuide source files.
- Never commits, pushes, deploys, or executes generated code.
- Reviews supplied candidate data and returns a structured result.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_INPUT_CHARS = 60_000

SYSTEM_PROMPT = """You are the OSGuide AI review layer.

NON-NEGOTIABLE RULES:
1. You are review-only. Never claim to edit, commit, push, deploy, or execute code.
2. Preserve OSGuide's existing architecture, IDs, classes, behavior, and security boundaries.
3. Prefer small, isolated changes. Do not recommend full-file rewrites unless strictly necessary.
4. Treat existing functionality as the baseline. Flag changes that could break it.
5. Never expose, request, reproduce, or infer secrets, API keys, tokens, passwords, or credentials.
6. Do not suggest moving server-side secrets into browser/client code.
7. Separate blocking problems from optional improvements.
8. Optional features are welcome only when they do not alter the project's core foundation.
9. If evidence is insufficient, say so instead of guessing.

Return ONLY valid JSON using this schema:
{
  "verdict": "PASS" | "WARN" | "BLOCK",
  "summary": "short review summary",
  "blocking_issues": [
    {
      "title": "issue title",
      "reason": "why it matters",
      "suggested_fix": "smallest safe fix"
    }
  ],
  "warnings": [
    {
      "title": "warning title",
      "reason": "why it matters",
      "suggested_fix": "smallest safe fix"
    }
  ],
  "optional_improvements": [
    {
      "title": "improvement title",
      "benefit": "benefit",
      "core_safe": true
    }
  ]
}
"""


def _call_groq(review_input: str) -> dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    text = review_input.strip()
    if not text:
        raise ValueError("Review input is empty.")
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS] + "\n\n[INPUT TRUNCATED SAFELY]"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Review the following proposed OSGuide candidate/change. "
                    "Do not modify anything. Return JSON only.\n\n" + text
                ),
            },
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    request = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "OSGuide-AI-Review-Layer/2.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Groq API returned HTTP {exc.code}: {body[:500]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Groq API connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Groq API request timed out.") from exc

    try:
        envelope = json.loads(raw)
        content = envelope["choices"][0]["message"]["content"]
        result = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid Groq API response: {exc}") from exc

    if not isinstance(result, dict):
        raise RuntimeError("Groq API review result is not a JSON object.")

    return result


def _validate_result(result: dict[str, Any]) -> dict[str, Any]:
    verdict = str(result.get("verdict", "")).upper()
    if verdict not in {"PASS", "WARN", "BLOCK"}:
        verdict = "WARN"

    clean: dict[str, Any] = {
        "verdict": verdict,
        "summary": str(result.get("summary", "")).strip(),
        "blocking_issues": result.get("blocking_issues", []),
        "warnings": result.get("warnings", []),
        "optional_improvements": result.get("optional_improvements", []),
    }

    for key in ("blocking_issues", "warnings", "optional_improvements"):
        if not isinstance(clean[key], list):
            clean[key] = []

    if clean["blocking_issues"]:
        clean["verdict"] = "BLOCK"

    return clean


def _candidate_to_text(candidate: Any) -> str:
    if isinstance(candidate, str):
        return candidate

    if isinstance(candidate, bytes):
        return candidate.decode("utf-8", errors="replace")

    if isinstance(candidate, dict):
        return json.dumps(candidate, ensure_ascii=False, indent=2, default=str)

    if hasattr(candidate, "__dict__"):
        try:
            return json.dumps(
                vars(candidate),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        except Exception:
            pass

    return str(candidate)


def review_candidate(candidate: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """
    Bridge-compatible entry point.

    ai_review.py imports this function and calls it for a candidate.
    Extra positional/keyword arguments are accepted deliberately so the
    review layer remains compatible with bridge metadata/context arguments.
    """
    review_input = _candidate_to_text(candidate)

    if args or kwargs:
        context: dict[str, Any] = {}
        if args:
            context["args"] = args
        if kwargs:
            context["kwargs"] = kwargs

        review_input += (
            "\n\nOSGuide review context:\n"
            + json.dumps(context, ensure_ascii=False, indent=2, default=str)
        )

    return _validate_result(_call_groq(review_input))
