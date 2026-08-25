"""
OSGuide Engine
AI Review Bridge

Purpose
-------
Thin, non-destructive bridge between the deterministic OSGuide core engine
and tools/ai/ai_review_layer.py.

Safety rules
------------
- Never replaces Decision Engine.
- Never publishes or writes to Supabase.
- Never mutates DecisionResult.
- AI can tighten an automatic decision, never loosen a safe core decision.
- If AI is unavailable, default behavior is BYPASS so the existing core
  continues unchanged.
"""

from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any, Final, Mapping


AI_BRIDGE_COMPONENT: Final[str] = "AI Review Bridge"
AI_BRIDGE_SCHEMA_VERSION: Final[str] = "1"
AI_BRIDGE_VERSION: Final[str] = "0.1.0"

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_STANDALONE_LAYER_PATH: Final[Path] = (
    _REPO_ROOT / "tools" / "ai" / "ai_review_layer.py"
)

_TRUE_VALUES: Final[frozenset[str]] = frozenset(
    {"1", "true", "yes", "on", "enabled"}
)
_FALSE_VALUES: Final[frozenset[str]] = frozenset(
    {"0", "false", "no", "off", "disabled"}
)
_PUBLISHABLE_ACTIONS: Final[frozenset[str]] = frozenset(
    {"insert", "update", "repair"}
)
_NON_PUBLISHABLE_ACTIONS: Final[frozenset[str]] = frozenset(
    {"review", "skip"}
)


class AIAdvisoryDecision(str, Enum):
    BYPASS = "bypass"
    ACCEPT = "accept"
    MANUAL_REVIEW = "manual_review"
    REJECT = "reject"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AIReviewBridgeResult:
    decision: AIAdvisoryDecision
    attempted: bool
    available: bool
    should_hold_for_review: bool
    reason: str
    model: str | None = None
    cached: bool = False
    quality_score: int | None = None
    osguide_fit_score: int | None = None
    description_quality_score: int | None = None
    confidence: float | None = None
    description_action: str | None = None
    suggested_category: str | None = None
    content_flags: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    facts_not_verified: tuple[str, ...] = ()
    safe_to_auto_apply_text_only: bool = False
    raw_review: Mapping[str, Any] = field(default_factory=dict)

    @property
    def blocks_automatic_publish(self) -> bool:
        return self.should_hold_for_review

    @property
    def accepted(self) -> bool:
        return self.decision == AIAdvisoryDecision.ACCEPT

    @property
    def bypassed(self) -> bool:
        return self.decision == AIAdvisoryDecision.BYPASS


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return default


def _bounded_text(value: object, *, max_length: int) -> str:
    text = str(value or "")
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_length:
        text = text[:max_length] + "…"
    return text


def _safe_list(
    value: object,
    *,
    max_items: int = 20,
    max_item_length: int = 240,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[str] = []
    for item in value[:max_items]:
        text = _bounded_text(item, max_length=max_item_length)
        if text:
            result.append(text)
    return tuple(result)


def _safe_int_0_100(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, number))


def _safe_confidence(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _action_value(decision_result: object) -> str:
    action = getattr(decision_result, "action", None)
    if action is None:
        return ""
    value = getattr(action, "value", action)
    return str(value or "").strip().lower()


def _decision_kind_value(decision_result: object) -> str:
    kind = getattr(decision_result, "kind", None)
    if kind is None:
        return ""
    value = getattr(kind, "value", kind)
    return str(value or "").strip().lower()


def _decision_reason_text(decision_result: object) -> str:
    return _bounded_text(
        getattr(decision_result, "reason_text", ""),
        max_length=1800,
    )


def _decision_confidence(decision_result: object) -> float | None:
    return _safe_confidence(
        getattr(decision_result, "confidence", None)
    )


def _payload_value(
    decision_result: object,
    field_name: str,
) -> object | None:
    payload = getattr(decision_result, "payload", None)
    if payload is None:
        return None
    return getattr(payload, field_name, None)


def _candidate_value(
    candidate: object,
    field_name: str,
) -> object | None:
    return getattr(candidate, field_name, None)


def ai_bridge_enabled() -> bool:
    if not _env_bool("OSGUIDE_AI_ENABLED", False):
        return False
    return _env_bool("OSGUIDE_AI_BRIDGE_ENABLED", True)


def ai_use_cache() -> bool:
    return _env_bool("OSGUIDE_AI_USE_CACHE", True)


def ai_fail_mode() -> str:
    value = os.getenv(
        "OSGUIDE_AI_FAIL_MODE",
        "bypass",
    ).strip().lower()
    if value not in {"bypass", "review"}:
        return "bypass"
    return value


def groq_key_available() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip())


_STANDALONE_MODULE: ModuleType | None = None


def _load_standalone_ai_layer() -> ModuleType:
    global _STANDALONE_MODULE

    if _STANDALONE_MODULE is not None:
        return _STANDALONE_MODULE

    if not _STANDALONE_LAYER_PATH.is_file():
        raise RuntimeError(
            "Standalone AI Review Layer file is missing."
        )

    spec = importlib.util.spec_from_file_location(
        "osguide_standalone_ai_review_layer",
        _STANDALONE_LAYER_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Standalone AI Review Layer could not be loaded."
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not callable(getattr(module, "review_candidate", None)):
        raise RuntimeError(
            "Standalone AI Review Layer does not expose review_candidate()."
        )

    _STANDALONE_MODULE = module
    return module


def build_ai_candidate_payload(
    *,
    candidate: object,
    decision_result: object,
) -> dict[str, Any]:
    name = (
        _payload_value(decision_result, "name")
        or _candidate_value(candidate, "name")
        or ""
    )

    package_id = (
        _payload_value(decision_result, "package_id")
        or _candidate_value(candidate, "package_id")
    )

    source = (
        _payload_value(decision_result, "source")
        or _candidate_value(candidate, "source_type")
    )

    source_type = _candidate_value(
        candidate,
        "source_type",
    )

    short_description = _payload_value(
        decision_result,
        "short_description",
    )
    full_description = _payload_value(
        decision_result,
        "full_description",
    )
    candidate_description = _candidate_value(
        candidate,
        "description",
    )

    metadata = {
        "core_decision_action": _action_value(decision_result),
        "core_decision_kind": _decision_kind_value(decision_result),
        "core_decision_confidence": _decision_confidence(
            decision_result
        ),
        "core_requires_review": bool(
            getattr(decision_result, "requires_review", False)
        ),
        "core_blocked": bool(
            getattr(decision_result, "blocked", False)
        ),
    }

    evidence = [
        item
        for item in (_decision_reason_text(decision_result),)
        if item
    ]

    return {
        "name": _bounded_text(name, max_length=240),
        "package_id": (
            _bounded_text(package_id, max_length=240)
            if package_id
            else None
        ),
        "version": _payload_value(decision_result, "version"),
        "source": (
            _bounded_text(source, max_length=120)
            if source
            else None
        ),
        "source_type": (
            _bounded_text(source_type, max_length=120)
            if source_type
            else None
        ),
        "source_url": _payload_value(
            decision_result,
            "source_url",
        ),
        "repository_url": _payload_value(
            decision_result,
            "repository_url",
        ),
        "apk_url": _payload_value(
            decision_result,
            "apk_url",
        ),
        "license": _payload_value(
            decision_result,
            "license",
        ),
        "category": _payload_value(
            decision_result,
            "category",
        ),
        "description": (
            candidate_description
            if candidate_description
            else short_description
        ),
        "short_description": short_description,
        "full_description": full_description,
        "icon_url": _payload_value(
            decision_result,
            "icon_url",
        ),
        "metadata": metadata,
        "evidence": evidence,
    }


def _bypass_result(reason: str) -> AIReviewBridgeResult:
    return AIReviewBridgeResult(
        decision=AIAdvisoryDecision.BYPASS,
        attempted=False,
        available=False,
        should_hold_for_review=False,
        reason=_bounded_text(reason, max_length=500),
    )


def _unavailable_result(
    reason: str,
    *,
    attempted: bool,
) -> AIReviewBridgeResult:
    hold = ai_fail_mode() == "review"

    return AIReviewBridgeResult(
        decision=(
            AIAdvisoryDecision.MANUAL_REVIEW
            if hold
            else AIAdvisoryDecision.UNAVAILABLE
        ),
        attempted=attempted,
        available=False,
        should_hold_for_review=hold,
        reason=_bounded_text(reason, max_length=700),
    )


def _normalize_envelope(
    envelope: object,
) -> AIReviewBridgeResult:
    ok = bool(getattr(envelope, "ok", False))

    model = _bounded_text(
        getattr(envelope, "model", ""),
        max_length=160,
    ) or None

    cached = bool(getattr(envelope, "cached", False))
    review = getattr(envelope, "review", None)

    if not isinstance(review, Mapping):
        return _unavailable_result(
            "AI Review Layer returned an invalid review envelope.",
            attempted=True,
        )

    raw_decision = str(
        review.get("decision", "") or ""
    ).strip().lower()

    reason = _bounded_text(
        review.get(
            "reason",
            "AI Review Layer returned no reason.",
        ),
        max_length=1800,
    )

    if not ok:
        return _unavailable_result(
            reason or "AI Review Layer failed safely.",
            attempted=True,
        )

    if raw_decision == "accept":
        normalized_decision = AIAdvisoryDecision.ACCEPT
        hold_for_review = False
    elif raw_decision == "manual_review":
        normalized_decision = AIAdvisoryDecision.MANUAL_REVIEW
        hold_for_review = True
    elif raw_decision == "reject":
        normalized_decision = AIAdvisoryDecision.REJECT
        hold_for_review = True
    else:
        return _unavailable_result(
            "AI Review Layer returned an unknown decision.",
            attempted=True,
        )

    return AIReviewBridgeResult(
        decision=normalized_decision,
        attempted=True,
        available=True,
        should_hold_for_review=hold_for_review,
        reason=reason,
        model=model,
        cached=cached,
        quality_score=_safe_int_0_100(
            review.get("quality_score")
        ),
        osguide_fit_score=_safe_int_0_100(
            review.get("osguide_fit_score")
        ),
        description_quality_score=_safe_int_0_100(
            review.get("description_quality_score")
        ),
        confidence=_safe_confidence(
            review.get("confidence")
        ),
        description_action=(
            _bounded_text(
                review.get("description_action"),
                max_length=40,
            )
            or None
        ),
        suggested_category=(
            _bounded_text(
                review.get("suggested_category"),
                max_length=120,
            )
            or None
        ),
        content_flags=_safe_list(
            review.get("content_flags")
        ),
        quality_flags=_safe_list(
            review.get("quality_flags")
        ),
        facts_not_verified=_safe_list(
            review.get("facts_not_verified"),
            max_items=30,
        ),
        safe_to_auto_apply_text_only=bool(
            review.get(
                "safe_to_auto_apply_text_only",
                False,
            )
        ),
        raw_review=dict(review),
    )


def should_attempt_ai_review(
    decision_result: object,
) -> bool:
    if not ai_bridge_enabled():
        return False

    if bool(getattr(decision_result, "blocked", False)):
        return False

    if bool(
        getattr(
            decision_result,
            "requires_review",
            False,
        )
    ):
        return False

    return _action_value(decision_result) in _PUBLISHABLE_ACTIONS


def review_decision(
    *,
    candidate: object,
    decision_result: object,
) -> AIReviewBridgeResult:
    """
    Non-destructive advisory gate.

    The caller may inspect .blocks_automatic_publish before Publisher.
    This function itself never mutates DecisionResult and never writes.
    """

    if not ai_bridge_enabled():
        return _bypass_result(
            "AI Review Bridge is disabled."
        )

    action = _action_value(decision_result)

    if bool(getattr(decision_result, "blocked", False)):
        return _bypass_result(
            "Decision Engine already blocked this candidate."
        )

    if bool(
        getattr(
            decision_result,
            "requires_review",
            False,
        )
    ):
        return _bypass_result(
            "Decision Engine already requires manual review."
        )

    if action in _NON_PUBLISHABLE_ACTIONS:
        return _bypass_result(
            "Decision Engine returned a non-publishable action."
        )

    if action not in _PUBLISHABLE_ACTIONS:
        return _bypass_result(
            "Decision Engine action is not eligible for AI review."
        )

    if not groq_key_available():
        return _unavailable_result(
            "GROQ_API_KEY is unavailable. Core behavior is preserved.",
            attempted=False,
        )

    try:
        module = _load_standalone_ai_layer()
        review_function = getattr(module, "review_candidate")

        payload = build_ai_candidate_payload(
            candidate=candidate,
            decision_result=decision_result,
        )

        envelope = review_function(
            payload,
            use_cache=ai_use_cache(),
        )

        return _normalize_envelope(envelope)

    except Exception as exc:
        safe_error = (
            f"{type(exc).__name__}: "
            f"{_bounded_text(exc, max_length=500)}"
        )
        return _unavailable_result(
            "AI Review Bridge failed safely: " + safe_error,
            attempted=True,
        )


def ai_review_log_summary(
    result: AIReviewBridgeResult,
) -> str:
    parts = [
        f"decision={result.decision.value}",
        f"attempted={'yes' if result.attempted else 'no'}",
        f"available={'yes' if result.available else 'no'}",
        f"hold={'yes' if result.should_hold_for_review else 'no'}",
    ]

    if result.model:
        parts.append(
            "model="
            + _bounded_text(
                result.model,
                max_length=120,
            )
        )

    if result.confidence is not None:
        parts.append(
            f"confidence={result.confidence:.3f}"
        )

    if result.quality_score is not None:
        parts.append(
            f"quality={result.quality_score}"
        )

    if result.osguide_fit_score is not None:
        parts.append(
            f"osguide_fit={result.osguide_fit_score}"
        )

    if result.cached:
        parts.append("cached=yes")

    return "; ".join(parts)


def ai_review_report_payload(
    result: AIReviewBridgeResult,
) -> dict[str, Any]:
    return {
        "component": AI_BRIDGE_COMPONENT,
        "schema_version": AI_BRIDGE_SCHEMA_VERSION,
        "version": AI_BRIDGE_VERSION,
        "decision": result.decision.value,
        "attempted": result.attempted,
        "available": result.available,
        "hold_for_review": result.should_hold_for_review,
        "model": result.model,
        "cached": result.cached,
        "quality_score": result.quality_score,
        "osguide_fit_score": result.osguide_fit_score,
        "description_quality_score": (
            result.description_quality_score
        ),
        "confidence": result.confidence,
        "description_action": result.description_action,
        "suggested_category": result.suggested_category,
        "content_flags": list(result.content_flags),
        "quality_flags": list(result.quality_flags),
        "facts_not_verified": list(
            result.facts_not_verified
        ),
        "safe_to_auto_apply_text_only": (
            result.safe_to_auto_apply_text_only
        ),
        "reason": _bounded_text(
            result.reason,
            max_length=1800,
        ),
    }


def bridge_diagnostic() -> dict[str, Any]:
    """
    Structural diagnostic only. Does not call Groq.
    """
    return {
        "component": AI_BRIDGE_COMPONENT,
        "version": AI_BRIDGE_VERSION,
        "schema_version": AI_BRIDGE_SCHEMA_VERSION,
        "enabled": ai_bridge_enabled(),
        "fail_mode": ai_fail_mode(),
        "use_cache": ai_use_cache(),
        "groq_key_present": groq_key_available(),
        "standalone_layer_present": (
            _STANDALONE_LAYER_PATH.is_file()
        ),
        "standalone_layer_path": str(
            _STANDALONE_LAYER_PATH.relative_to(
                _REPO_ROOT
            )
        ),
    }


__all__: Final[tuple[str, ...]] = (
    "AIAdvisoryDecision",
    "AIReviewBridgeResult",
    "AI_BRIDGE_COMPONENT",
    "AI_BRIDGE_SCHEMA_VERSION",
    "AI_BRIDGE_VERSION",
    "ai_bridge_enabled",
    "ai_fail_mode",
    "ai_review_log_summary",
    "ai_review_report_payload",
    "ai_use_cache",
    "bridge_diagnostic",
    "build_ai_candidate_payload",
    "groq_key_available",
    "review_decision",
    "should_attempt_ai_review",
)
