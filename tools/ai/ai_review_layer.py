#!/usr/bin/env python3
"""
OSGuide AI Review Layer
-----------------------
A read-only review helper for GitHub Actions.

Core rule:
- Never edits OSGuide source files.
- Never commits, pushes, deploys, or executes generated code.
- Reviews a supplied diff/text and returns structured JSON only.

Environment:
- GROQ_API_KEY (required)
- GROQ_MODEL (optional; defaults to openai/gpt-oss-120b)
"""

from __future__ import annotations

import json
import os
import sys
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

def fail(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)

def read_input() -> str:
    if len(sys.argv) > 1:
        path = sys.argv[1]
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = handle.read()
        except OSError as exc:
            fail(f"Cannot read input file: {exc}")
    elif not sys.stdin.isatty():
        data = sys.stdin.read()
    else:
        fail("Provide a text/diff file path or pipe text through stdin.")

    data = data.strip()
    if not data:
        fail("Review input is empty.")

    if len(data) > MAX_INPUT_CHARS:
        data = data[:MAX_INPUT_CHARS] + "\n\n[INPUT TRUNCATED SAFELY]"

    return data

def call_groq(review_input: str) -> dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        fail("GROQ_API_KEY is not configured.")

    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Review the following proposed OSGuide change. "
                    "Do not modify anything. Return JSON only.\n\n"
                    + review_input
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
            "User-Agent": "OSGuide-AI-Review-Layer/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"Groq API returned HTTP {exc.code}: {body[:500]}")
    except urllib.error.URLError as exc:
        fail(f"Groq API connection failed: {exc.reason}")
    except TimeoutError:
        fail("Groq API request timed out.")

    try:
        envelope = json.loads(raw)
        content = envelope["choices"][0]["message"]["content"]
        result = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        fail(f"Invalid API response: {exc}")

    return result

def validate_result(result: dict[str, Any]) -> dict[str, Any]:
    verdict = str(result.get("verdict", "")).upper()
    if verdict not in {"PASS", "WARN", "BLOCK"}:
        verdict = "WARN"

    clean = {
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

def main() -> None:
    review_input = read_input()
    result = validate_result(call_groq(review_input))
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
