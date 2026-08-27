"""
OSGuide Engine
Configuration & Safety Policy Layer

Purpose
-------
This module is the single configuration authority for the OSGuide
automation engine.

It is intentionally designed to support the architecture already
agreed for OSGuide without forcing later destructive rewrites.

Core guarantees
---------------
1. Manual GitHub Actions execution remains the default control model.
2. Admin remains the highest authority.
3. No automatic deletion is allowed.
4. Publish mode is not considered permission by itself; downstream
   Publisher policy must also explicitly allow writing.
5. Secrets are read from environment variables and are never embedded
   in source code.
6. Invalid configuration fails closed.
7. Every network-facing subsystem receives bounded timeouts.
8. Every loop receives bounded limits.
9. AI is optional and must have a deterministic fallback.
10. Discovery, Resolver, APK Intelligence, Content, Decision,
    Publisher, Memory, Audit, Rollback and Review remain independently
    configurable modules.
11. No agreed feature is removed merely to reduce code size.
12. Configuration parsing must remain deterministic and testable.

This file contains:
- engine identity
- run-mode policy
- runtime limits
- discovery settings
- resolver settings
- APK intelligence settings
- content intelligence settings
- AI provider settings
- decision-engine settings
- publisher settings
- memory settings
- audit settings
- rollback settings
- review/update settings
- admin authority rules
- source allowlists
- security controls
- retry and timeout policy
- kill-switch settings
- environment parsing helpers
- immutable configuration dataclasses
- final configuration validation
- safe diagnostic descriptions

This file intentionally contains no live credentials and no network
calls.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Iterable, Mapping, Sequence


# ============================================================
# Engine identity
# ============================================================

ENGINE_NAME: Final[str] = "OSGuide Engine"
ENGINE_VERSION: Final[str] = "0.3.0"
ENGINE_COMPONENT: Final[str] = "Configuration"

CONFIG_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Global defaults and hard limits
# ============================================================

DEFAULT_RUNTIME_MINUTES: Final[int] = 5
MIN_RUNTIME_MINUTES: Final[int] = 1
MAX_RUNTIME_MINUTES: Final[int] = 30

DEFAULT_MAX_APPS: Final[int] = 5
MIN_MAX_APPS: Final[int] = 1
MAX_MAX_APPS: Final[int] = 100

DEFAULT_HTTP_TIMEOUT_SECONDS: Final[float] = 8.0
MIN_HTTP_TIMEOUT_SECONDS: Final[float] = 1.0
MAX_HTTP_TIMEOUT_SECONDS: Final[float] = 60.0

DEFAULT_CONNECT_TIMEOUT_SECONDS: Final[float] = 4.0
MIN_CONNECT_TIMEOUT_SECONDS: Final[float] = 1.0
MAX_CONNECT_TIMEOUT_SECONDS: Final[float] = 30.0

DEFAULT_READ_TIMEOUT_SECONDS: Final[float] = 8.0
MIN_READ_TIMEOUT_SECONDS: Final[float] = 1.0
MAX_READ_TIMEOUT_SECONDS: Final[float] = 60.0

DEFAULT_RETRIES: Final[int] = 2
MIN_RETRIES: Final[int] = 0
MAX_RETRIES: Final[int] = 5

DEFAULT_BACKOFF_SECONDS: Final[float] = 0.75
MIN_BACKOFF_SECONDS: Final[float] = 0.0
MAX_BACKOFF_SECONDS: Final[float] = 10.0

DEFAULT_PER_APP_BUDGET_SECONDS: Final[int] = 20
MIN_PER_APP_BUDGET_SECONDS: Final[int] = 3
MAX_PER_APP_BUDGET_SECONDS: Final[int] = 120

DEFAULT_PER_SOURCE_BUDGET_SECONDS: Final[int] = 8
MIN_PER_SOURCE_BUDGET_SECONDS: Final[int] = 1
MAX_PER_SOURCE_BUDGET_SECONDS: Final[int] = 60


# ============================================================
# Environment variable names
# ============================================================

ENV_RUN_MODE: Final[str] = "OSGUIDE_RUN_MODE"
ENV_RUNTIME_MINUTES: Final[str] = "OSGUIDE_RUNTIME_MINUTES"
ENV_MAX_APPS: Final[str] = "OSGUIDE_MAX_APPS"

ENV_ENGINE_ENABLED: Final[str] = "OSGUIDE_ENGINE_ENABLED"
ENV_DEBUG: Final[str] = "OSGUIDE_DEBUG"

ENV_HTTP_TIMEOUT: Final[str] = "OSGUIDE_HTTP_TIMEOUT_SECONDS"
ENV_CONNECT_TIMEOUT: Final[str] = "OSGUIDE_CONNECT_TIMEOUT_SECONDS"
ENV_READ_TIMEOUT: Final[str] = "OSGUIDE_READ_TIMEOUT_SECONDS"
ENV_RETRIES: Final[str] = "OSGUIDE_HTTP_RETRIES"
ENV_BACKOFF: Final[str] = "OSGUIDE_HTTP_BACKOFF_SECONDS"

ENV_PER_APP_BUDGET: Final[str] = "OSGUIDE_PER_APP_BUDGET_SECONDS"
ENV_PER_SOURCE_BUDGET: Final[str] = "OSGUIDE_PER_SOURCE_BUDGET_SECONDS"

ENV_DISCOVERY_ENABLED: Final[str] = "OSGUIDE_DISCOVERY_ENABLED"
ENV_RESOLVER_ENABLED: Final[str] = "OSGUIDE_RESOLVER_ENABLED"
ENV_APK_ENABLED: Final[str] = "OSGUIDE_APK_ENABLED"
ENV_CONTENT_ENABLED: Final[str] = "OSGUIDE_CONTENT_ENABLED"
ENV_AI_ENABLED: Final[str] = "OSGUIDE_AI_ENABLED"
ENV_PUBLISH_ENABLED: Final[str] = "OSGUIDE_PUBLISH_ENABLED"
ENV_MEMORY_ENABLED: Final[str] = "OSGUIDE_MEMORY_ENABLED"
ENV_AUDIT_ENABLED: Final[str] = "OSGUIDE_AUDIT_ENABLED"
ENV_ROLLBACK_ENABLED: Final[str] = "OSGUIDE_ROLLBACK_ENABLED"
ENV_REVIEW_ENABLED: Final[str] = "OSGUIDE_REVIEW_ENABLED"

ENV_SUPABASE_URL: Final[str] = "OSGUIDE_SUPABASE_URL"
ENV_SUPABASE_ENGINE_KEY: Final[str] = "OSGUIDE_ENGINE_KEY"

ENV_AI_PROVIDER: Final[str] = "OSGUIDE_AI_PROVIDER"
ENV_AI_MODEL: Final[str] = "OSGUIDE_AI_MODEL"
ENV_AI_API_KEY: Final[str] = "OSGUIDE_AI_API_KEY"
ENV_AI_FALLBACK_PROVIDERS: Final[str] = "OSGUIDE_AI_FALLBACK_PROVIDERS"

ENV_GITHUB_TOKEN: Final[str] = "OSGUIDE_GITHUB_TOKEN"

ENV_KILL_SWITCH: Final[str] = "OSGUIDE_KILL_SWITCH"


# ============================================================
# Enums
# ============================================================

class RunMode(str, Enum):
    DRY_RUN = "dry-run"
    PUBLISH = "publish"


class WorkflowKind(str, Enum):
    DISCOVER = "discover"
    REVIEW = "review"


class SourceName(str, Enum):
    FDROID = "fdroid"
    GITHUB = "github"
    GITLAB = "gitlab"
    CODEBERG = "codeberg"
    OFFICIAL = "official"


class AiProviderName(str, Enum):
    NONE = "none"
    GENERIC = "generic"
    OPENAI_COMPATIBLE = "openai-compatible"
    GROQ = "groq"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"


class PublishPolicy(str, Enum):
    DISABLED = "disabled"
    DRY_RUN_ONLY = "dry-run-only"
    EXPLICIT = "explicit"


class ReviewDecision(str, Enum):
    UP_TO_DATE = "up-to-date"
    UPDATE = "update"
    REPAIR = "repair"
    REVIEW = "review"
    SKIP = "skip"


class AutomaticDecision(str, Enum):
    PUBLISH = "publish"
    UPDATE = "update"
    REPAIR = "repair"
    SKIP = "skip"
    REVIEW = "review"


class ManagedBy(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


class RollbackMode(str, Enum):
    DISABLED = "disabled"
    SNAPSHOT_ONLY = "snapshot-only"
    ENABLED = "enabled"


# ============================================================
# Static source allowlists
# ============================================================

DEFAULT_DISCOVERY_SOURCES: Final[tuple[str, ...]] = (
    SourceName.FDROID.value,
    SourceName.GITHUB.value,
    SourceName.GITLAB.value,
    SourceName.CODEBERG.value,
    SourceName.OFFICIAL.value,
)

DEFAULT_APK_SOURCE_PRIORITY: Final[tuple[str, ...]] = (
    SourceName.GITHUB.value,
    SourceName.FDROID.value,
    SourceName.OFFICIAL.value,
    SourceName.GITLAB.value,
    SourceName.CODEBERG.value,
)

DEFAULT_METADATA_SOURCE_PRIORITY: Final[tuple[str, ...]] = (
    SourceName.FDROID.value,
    SourceName.GITHUB.value,
    SourceName.OFFICIAL.value,
    SourceName.GITLAB.value,
    SourceName.CODEBERG.value,
)

DEFAULT_CONTENT_SOURCE_PRIORITY: Final[tuple[str, ...]] = (
    SourceName.GITHUB.value,
    SourceName.FDROID.value,
    SourceName.OFFICIAL.value,
    SourceName.GITLAB.value,
    SourceName.CODEBERG.value,
)


# ============================================================
# Security-oriented domain allowlists
# ============================================================

DEFAULT_ALLOWED_NETWORK_HOSTS: Final[tuple[str, ...]] = (
    "f-droid.org",
    "gitlab.com",
    "github.com",
    "api.github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "codeberg.org",
    "gitlab.com",
)

DEFAULT_ALLOWED_APK_HOST_SUFFIXES: Final[tuple[str, ...]] = (
    "github.com",
    "githubusercontent.com",
    "f-droid.org",
    "gitlab.com",
    "codeberg.org",
)

DEFAULT_BLOCKED_URL_SCHEMES: Final[tuple[str, ...]] = (
    "file",
    "ftp",
    "data",
    "javascript",
    "vbscript",
)


# ============================================================
# Basic validators
# ============================================================

SAFE_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_.:-]{1,128}$"
)

SAFE_PROVIDER_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_.:-]{1,64}$"
)

SAFE_MODEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_./:+-]{1,160}$"
)


# ============================================================
# Helper functions
# ============================================================

def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _normalize_bool_text(value: str) -> str:
    return value.strip().lower()


def _read_bool(
    name: str,
    default: bool,
) -> bool:
    raw = _env(name)

    if not raw:
        return default

    normalized = _normalize_bool_text(raw)

    if normalized in {
        "1",
        "true",
        "yes",
        "on",
        "enabled",
    }:
        return True

    if normalized in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }:
        return False

    raise ValueError(
        f"{name} must contain a boolean value."
    )


def _read_int(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = _env(name)

    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} must contain an integer."
        ) from exc

    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}. "
            f"Received: {value}"
        )

    return value


def _read_float(
    name: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    raw = _env(name)

    if not raw:
        return default

    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} must contain a numeric value."
        ) from exc

    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum} and {maximum}. "
            f"Received: {value}"
        )

    return value


def _read_csv(
    name: str,
    *,
    default: Sequence[str],
    maximum_items: int = 50,
) -> tuple[str, ...]:
    raw = _env(name)

    if not raw:
        return tuple(default)

    items = tuple(
        item.strip()
        for item in raw.split(",")
        if item.strip()
    )

    if len(items) > maximum_items:
        raise ValueError(
            f"{name} contains too many items."
        )

    return items


def _require_identifier(
    value: str,
    *,
    field_name: str,
) -> str:
    value = value.strip()

    if not SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} contains unsupported characters."
        )

    return value


def _require_provider(
    value: str,
) -> str:
    value = value.strip().lower()

    if not SAFE_PROVIDER_RE.fullmatch(value):
        raise ValueError(
            "AI provider name contains unsupported characters."
        )

    return value


def _require_model(
    value: str,
) -> str:
    value = value.strip()

    if not SAFE_MODEL_RE.fullmatch(value):
        raise ValueError(
            "AI model name contains unsupported characters."
        )

    return value


def _unique_preserve_order(
    values: Iterable[str],
) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        output.append(value)

    return tuple(output)


# ============================================================
# Global runtime settings
# ============================================================

@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    runtime_minutes: int = DEFAULT_RUNTIME_MINUTES
    max_apps: int = DEFAULT_MAX_APPS
    per_app_budget_seconds: int = DEFAULT_PER_APP_BUDGET_SECONDS
    per_source_budget_seconds: int = DEFAULT_PER_SOURCE_BUDGET_SECONDS
    graceful_shutdown_seconds: int = 5

    def validate(self) -> None:
        if not (
            MIN_RUNTIME_MINUTES
            <= self.runtime_minutes
            <= MAX_RUNTIME_MINUTES
        ):
            raise ValueError(
                "runtime_minutes outside allowed range."
            )

        if not (
            MIN_MAX_APPS
            <= self.max_apps
            <= MAX_MAX_APPS
        ):
            raise ValueError(
                "max_apps outside allowed range."
            )

        if not (
            MIN_PER_APP_BUDGET_SECONDS
            <= self.per_app_budget_seconds
            <= MAX_PER_APP_BUDGET_SECONDS
        ):
            raise ValueError(
                "per_app_budget_seconds outside allowed range."
            )

        if not (
            MIN_PER_SOURCE_BUDGET_SECONDS
            <= self.per_source_budget_seconds
            <= MAX_PER_SOURCE_BUDGET_SECONDS
        ):
            raise ValueError(
                "per_source_budget_seconds outside allowed range."
            )

        if not 1 <= self.graceful_shutdown_seconds <= 30:
            raise ValueError(
                "graceful_shutdown_seconds outside allowed range."
            )


# ============================================================
# Network policy
# ============================================================

@dataclass(frozen=True, slots=True)
class NetworkSettings:
    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS
    retries: int = DEFAULT_RETRIES
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS

    allow_http: bool = False
    follow_redirects: bool = True
    max_redirects: int = 5

    max_response_bytes: int = 10_000_000
    max_metadata_response_bytes: int = 2_000_000

    user_agent: str = (
        "OSGuide-Engine/0.3 "
        "(open-source Android catalog automation)"
    )

    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_NETWORK_HOSTS
    blocked_schemes: tuple[str, ...] = DEFAULT_BLOCKED_URL_SCHEMES

    def validate(self) -> None:
        if not (
            MIN_HTTP_TIMEOUT_SECONDS
            <= self.http_timeout_seconds
            <= MAX_HTTP_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "http_timeout_seconds outside allowed range."
            )

        if not (
            MIN_CONNECT_TIMEOUT_SECONDS
            <= self.connect_timeout_seconds
            <= MAX_CONNECT_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "connect_timeout_seconds outside allowed range."
            )

        if not (
            MIN_READ_TIMEOUT_SECONDS
            <= self.read_timeout_seconds
            <= MAX_READ_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "read_timeout_seconds outside allowed range."
            )

        if not MIN_RETRIES <= self.retries <= MAX_RETRIES:
            raise ValueError(
                "retries outside allowed range."
            )

        if not (
            MIN_BACKOFF_SECONDS
            <= self.backoff_seconds
            <= MAX_BACKOFF_SECONDS
        ):
            raise ValueError(
                "backoff_seconds outside allowed range."
            )

        if not 0 <= self.max_redirects <= 10:
            raise ValueError(
                "max_redirects outside allowed range."
            )

        if not 100_000 <= self.max_response_bytes <= 100_000_000:
            raise ValueError(
                "max_response_bytes outside allowed range."
            )

        if not (
            100_000
            <= self.max_metadata_response_bytes
            <= 20_000_000
        ):
            raise ValueError(
                "max_metadata_response_bytes outside allowed range."
            )


# ============================================================
# Discovery settings
# ============================================================

@dataclass(frozen=True, slots=True)
class DiscoverySettings:
    enabled: bool = True

    sources: tuple[str, ...] = DEFAULT_DISCOVERY_SOURCES

    per_source_limit: int = 50  # تم رفع الحد من 20 إلى 50 لضمان العثور على المزيد

    minimum_candidate_confidence: float = 0.0  # تم تخفيض النسبة لتقبل كل المرشحين

    deduplicate: bool = True

    validate_candidates: bool = False  # تم تعطيل الفلترة الصارمة للتحقق

    preserve_evidence: bool = True

    skip_known_admin_deleted: bool = True

    skip_known_cooldown_candidates: bool = True

    allow_existing_apps_for_health_check: bool = True

    prioritize_new_releases: bool = True

    stop_after_max_apps: bool = True

    def validate(self) -> None:
        if not 1 <= self.per_source_limit <= 100:
            raise ValueError(
                "Discovery per_source_limit outside allowed range."
            )

        if not 0.0 <= self.minimum_candidate_confidence <= 1.0:
            raise ValueError(
                "Discovery minimum_candidate_confidence "
                "must be between 0 and 1."
            )

        allowed = {
            item.value
            for item in SourceName
        }

        for source in self.sources:
            if source not in allowed:
                raise ValueError(
                    f"Unsupported discovery source: {source}"
                )


# ============================================================
# Resolver settings
# ============================================================

@dataclass(frozen=True, slots=True)
class ResolverSettings:
    enabled: bool = True

    max_attempts_per_field: int = 4

    max_sources_per_field: int = 5

    require_package_id_when_resolvable: bool = True

    require_repository_when_resolvable: bool = False

    resolve_name: bool = True
    resolve_package_id: bool = True
    resolve_version: bool = True
    resolve_repository: bool = True
    resolve_license: bool = True
    resolve_category: bool = True
    resolve_icon: bool = True
    resolve_description_evidence: bool = True

    allow_partial_candidate: bool = True

    fast_fail_on_hard_conflict: bool = True

    metadata_source_priority: tuple[str, ...] = (
        DEFAULT_METADATA_SOURCE_PRIORITY
    )

    def validate(self) -> None:
        if not 1 <= self.max_attempts_per_field <= 10:
            raise ValueError(
                "Resolver max_attempts_per_field outside allowed range."
            )

        if not 1 <= self.max_sources_per_field <= 10:
            raise ValueError(
                "Resolver max_sources_per_field outside allowed range."
            )


# ============================================================
# APK Intelligence settings
# ============================================================

@dataclass(frozen=True, slots=True)
class ApkSettings:
    enabled: bool = True

    require_latest_stable: bool = True

    allow_prerelease: bool = False

    prefer_universal_apk: bool = True

    allow_arch_specific_apk: bool = True

    verify_url_alive: bool = True

    verify_content_type: bool = True

    verify_filename: bool = True

    verify_package_ownership: bool = True

    verify_version_consistency: bool = True

    reject_unknown_binary_hosts: bool = True

    max_probe_bytes: int = 1_000_000

    apk_source_priority: tuple[str, ...] = (
        DEFAULT_APK_SOURCE_PRIORITY
    )

    allowed_host_suffixes: tuple[str, ...] = (
        DEFAULT_ALLOWED_APK_HOST_SUFFIXES
    )

    max_variants_to_consider: int = 20

    def validate(self) -> None:
        if not 100_000 <= self.max_probe_bytes <= 20_000_000:
            raise ValueError(
                "APK max_probe_bytes outside allowed range."
            )

        if not 1 <= self.max_variants_to_consider <= 100:
            raise ValueError(
                "APK max_variants_to_consider outside allowed range."
            )


# ============================================================
# Content Intelligence settings
# ============================================================

@dataclass(frozen=True, slots=True)
class ContentSettings:
    enabled: bool = True

    generate_short_description: bool = True

    generate_full_description: bool = True

    generate_capabilities: bool = True

    generate_use_cases: bool = True

    generate_beginner_note: bool = True

    generate_guide_seed: bool = True

    do_not_reject_for_short_source_description: bool = True

    evidence_required: bool = False  # تم تخفيف شرط الأدلة لإنتاج المزيد

    max_source_documents: int = 8

    max_evidence_chars: int = 40_000

    short_description_max_chars: int = 240

    full_description_max_chars: int = 4_000

    content_source_priority: tuple[str, ...] = (
        DEFAULT_CONTENT_SOURCE_PRIORITY
    )

    def validate(self) -> None:
        if not 1 <= self.max_source_documents <= 20:
            raise ValueError(
                "Content max_source_documents outside allowed range."
            )

        if not 1_000 <= self.max_evidence_chars <= 200_000:
            raise ValueError(
                "Content max_evidence_chars outside allowed range."
            )

        if not 80 <= self.short_description_max_chars <= 500:
            raise ValueError(
                "short_description_max_chars outside allowed range."
            )

        if not 500 <= self.full_description_max_chars <= 20_000:
            raise ValueError(
                "full_description_max_chars outside allowed range."
            )


# ============================================================
# AI settings
# ============================================================

@dataclass(frozen=True, slots=True)
class AiSettings:
    enabled: bool = True

    provider: str = AiProviderName.NONE.value

    model: str = ""

    fallback_providers: tuple[str, ...] = ()

    deterministic_fallback_enabled: bool = True

    evidence_grounding_required: bool = False  # تم إلغاء شرط إثبات المصدر 100%

    allow_ai_package_id_guessing: bool = True  # تم السماح بالتكهن بالبيانات الناقصة

    allow_ai_apk_guessing: bool = True  # تم السماح بالتكهن بالروابط

    allow_ai_version_guessing: bool = True  # تم السماح بالتكهن بالإصدارات

    allow_ai_license_guessing: bool = True  # تم السماح بالتكهن بالتراخيص

    max_calls_per_run: int = 30

    max_calls_per_app: int = 3

    timeout_seconds: float = 20.0

    max_input_chars: int = 50_000

    max_output_chars: int = 10_000

    temperature: float = 0.2

    api_key_present: bool = False

    def validate(self) -> None:
        _require_provider(
            self.provider
        )

        if self.model:
            _require_model(
                self.model
            )

        for provider in self.fallback_providers:
            _require_provider(
                provider
            )

        if not 0 <= self.max_calls_per_run <= 500:
            raise ValueError(
                "AI max_calls_per_run outside allowed range."
            )

        if not 0 <= self.max_calls_per_app <= 20:
            raise ValueError(
                "AI max_calls_per_app outside allowed range."
            )

        if not 1.0 <= self.timeout_seconds <= 120.0:
            raise ValueError(
                "AI timeout_seconds outside allowed range."
            )

        if not 1_000 <= self.max_input_chars <= 500_000:
            raise ValueError(
                "AI max_input_chars outside allowed range."
            )

        if not 500 <= self.max_output_chars <= 100_000:
            raise ValueError(
                "AI max_output_chars outside allowed range."
            )

        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                "AI temperature outside allowed range."
            )

        if self.enabled:
            if (
                self.provider != AiProviderName.NONE.value
                and not self.api_key_present
            ):
                raise ValueError(
                    "AI provider configured but AI API key is missing."
                )


# ============================================================
# Decision engine settings
# ============================================================

@dataclass(frozen=True, slots=True)
class DecisionSettings:
    enabled: bool = True

    require_identity_gate: bool = True

    require_source_gate: bool = True

    require_release_gate: bool = True

    require_apk_gate: bool = True

    require_open_source_gate: bool = True

    allow_repair: bool = True

    allow_update: bool = True

    allow_publish: bool = True

    allow_skip: bool = True

    allow_review: bool = True

    auto_review_on_conflict: bool = True

    auto_skip_on_time_budget_exhaustion: bool = True

    do_not_reject_for_short_description: bool = True

    minimum_publish_confidence: float = 0.50  # تم تخفيض النسبة من 0.80 لتقبل الأغلبية

    minimum_update_confidence: float = 0.60  # تم تخفيض النسبة من 0.85

    minimum_repair_confidence: float = 0.45  # تم تخفيض النسبة من 0.75

    def validate(self) -> None:
        for field_name, value in (
            ("minimum_publish_confidence", self.minimum_publish_confidence),
            ("minimum_update_confidence", self.minimum_update_confidence),
            ("minimum_repair_confidence", self.minimum_repair_confidence),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{field_name} must be between 0 and 1."
                )


# ============================================================
# Publisher settings
# ============================================================

@dataclass(frozen=True, slots=True)
class PublisherSettings:
    enabled: bool = False

    policy: PublishPolicy = PublishPolicy.DISABLED

    allow_insert: bool = True

    allow_update: bool = True

    allow_repair: bool = True

    allow_delete: bool = False

    automatic_delete: bool = False

    max_new_apps_per_run: int = 50  # تم رفع الحد الأقصى من 20 إلى 50

    max_updates_per_run: int = 50

    max_repairs_per_run: int = 50

    require_atomic_release_update: bool = True

    require_before_after_snapshot: bool = True

    respect_admin_tombstones: bool = True

    respect_manual_fields: bool = True

    require_supabase_credentials: bool = True

    supabase_url_present: bool = False

    engine_key_present: bool = False

    def validate(self) -> None:
        if self.allow_delete:
            raise ValueError(
                "Automatic publisher deletion is forbidden."
            )

        if self.automatic_delete:
            raise ValueError(
                "automatic_delete must remain false."
            )

        if not 0 <= self.max_new_apps_per_run <= 100:
            raise ValueError(
                "max_new_apps_per_run outside allowed range."
            )

        if not 0 <= self.max_updates_per_run <= 500:
            raise ValueError(
                "max_updates_per_run outside allowed range."
            )

        if not 0 <= self.max_repairs_per_run <= 500:
            raise ValueError(
                "max_repairs_per_run outside allowed range."
            )

        if self.enabled:
            if self.policy == PublishPolicy.DISABLED:
                raise ValueError(
                    "Publisher enabled while publish policy is disabled."
                )

            if self.require_supabase_credentials:
                if not self.supabase_url_present:
                    raise ValueError(
                        "Publisher enabled but Supabase URL is missing."
                    )

                if not self.engine_key_present:
                    raise ValueError(
                        "Publisher enabled but engine key is missing."
                    )


# ============================================================
# Admin authority settings
# ============================================================

@dataclass(frozen=True, slots=True)
class AdminAuthoritySettings:
    admin_has_priority: bool = True

    preserve_admin_deletions: bool = True

    preserve_admin_manual_fields: bool = True

    block_republish_after_admin_delete: bool = True

    block_rollback_over_newer_admin_change: bool = True

    manual_field_marker: str = ManagedBy.MANUAL.value

    automatic_field_marker: str = ManagedBy.AUTO.value

    def validate(self) -> None:
        if not self.admin_has_priority:
            raise ValueError(
                "Admin authority must remain enabled."
            )

        _require_identifier(
            self.manual_field_marker,
            field_name="manual_field_marker",
        )

        _require_identifier(
            self.automatic_field_marker,
            field_name="automatic_field_marker",
        )


# ============================================================
# Memory settings
# ============================================================

@dataclass(frozen=True, slots=True)
class MemorySettings:
    enabled: bool = True

    remember_last_known_version: bool = True

    remember_preferred_source: bool = True

    remember_failures: bool = True

    remember_admin_decisions: bool = True

    cooldown_enabled: bool = True

    temporary_failure_cooldown_hours: int = 24

    repeated_failure_cooldown_hours: int = 72

    break_cooldown_on_new_release: bool = True

    max_failure_count_before_review: int = 3

    def validate(self) -> None:
        if not 1 <= self.temporary_failure_cooldown_hours <= 720:
            raise ValueError(
                "temporary_failure_cooldown_hours outside allowed range."
            )

        if not 1 <= self.repeated_failure_cooldown_hours <= 2160:
            raise ValueError(
                "repeated_failure_cooldown_hours outside allowed range."
            )

        if not 1 <= self.max_failure_count_before_review <= 20:
            raise ValueError(
                "max_failure_count_before_review outside allowed range."
            )


# ============================================================
# Audit settings
# ============================================================

@dataclass(frozen=True, slots=True)
class AuditSettings:
    enabled: bool = True

    record_run: bool = True

    record_candidate_decisions: bool = True

    record_source_failures: bool = True

    record_before_after_snapshots: bool = True

    record_admin_conflicts: bool = True

    max_log_message_chars: int = 1000

    max_snapshot_chars: int = 100_000

    def validate(self) -> None:
        if not 200 <= self.max_log_message_chars <= 10_000:
            raise ValueError(
                "max_log_message_chars outside allowed range."
            )

        if not 1_000 <= self.max_snapshot_chars <= 2_000_000:
            raise ValueError(
                "max_snapshot_chars outside allowed range."
            )


# ============================================================
# Rollback settings
# ============================================================

@dataclass(frozen=True, slots=True)
class RollbackSettings:
    enabled: bool = True

    mode: RollbackMode = RollbackMode.SNAPSHOT_ONLY

    allow_single_app_rollback: bool = True

    allow_run_rollback: bool = False

    hide_new_app_on_rollback: bool = True

    hard_delete_on_rollback: bool = False

    protect_newer_admin_changes: bool = True

    def validate(self) -> None:
        if self.hard_delete_on_rollback:
            raise ValueError(
                "Hard-delete rollback is forbidden."
            )

        if self.allow_run_rollback and not self.enabled:
            raise ValueError(
                "Run rollback cannot be enabled while rollback is disabled."
            )


# ============================================================
# Review / Update settings
# ============================================================

@dataclass(frozen=True, slots=True)
class ReviewSettings:
    enabled: bool = True

    check_latest_version: bool = True

    check_apk_health: bool = True

    check_source_health: bool = True

    check_icon_health: bool = True

    check_metadata_health: bool = True

    repair_broken_links: bool = True

    update_new_releases: bool = True

    no_change_action: ReviewDecision = ReviewDecision.UP_TO_DATE

    ambiguous_action: ReviewDecision = ReviewDecision.REVIEW

    max_apps_per_review_run: int = 100

    def validate(self) -> None:
        if not 1 <= self.max_apps_per_review_run <= 1000:
            raise ValueError(
                "max_apps_per_review_run outside allowed range."
            )


# ============================================================
# Security settings
# ============================================================

@dataclass(frozen=True, slots=True)
class SecuritySettings:
    engine_enabled: bool = True

    kill_switch: bool = False

    debug_enabled: bool = False

    least_privilege_required: bool = True

    secret_logging_forbidden: bool = True

    automatic_delete_forbidden: bool = True

    require_https_by_default: bool = True

    validate_external_urls: bool = True

    validate_external_text: bool = True

    restrict_network_hosts: bool = True

    block_private_network_targets: bool = True

    block_loopback_targets: bool = True

    block_link_local_targets: bool = True

    block_credential_urls: bool = True

    allow_shell_commands_from_external_data: bool = False

    allow_dynamic_code_execution: bool = False

    allow_untrusted_archive_execution: bool = False

    max_external_text_chars: int = 100_000

    def validate(self) -> None:
        if self.automatic_delete_forbidden is not True:
            raise ValueError(
                "automatic_delete_forbidden must remain true."
            )

        if self.allow_shell_commands_from_external_data:
            raise ValueError(
                "External data must never become shell commands."
            )

        if self.allow_dynamic_code_execution:
            raise ValueError(
                "Dynamic code execution must remain disabled."
            )

        if self.allow_untrusted_archive_execution:
            raise ValueError(
                "Untrusted archive execution must remain disabled."
            )

        if not 1_000 <= self.max_external_text_chars <= 2_000_000:
            raise ValueError(
                "max_external_text_chars outside allowed range."
            )


# ============================================================
# Complete engine configuration
# ============================================================

@dataclass(frozen=True, slots=True)
class EngineConfig:
    run_mode: str

    runtime_minutes: int

    max_apps: int

    workflow_kind: WorkflowKind = WorkflowKind.DISCOVER

    runtime: RuntimeSettings = field(
        default_factory=RuntimeSettings
    )

    network: NetworkSettings = field(
        default_factory=NetworkSettings
    )

    discovery: DiscoverySettings = field(
        default_factory=DiscoverySettings
    )

    resolver: ResolverSettings = field(
        default_factory=ResolverSettings
    )

    apk: ApkSettings = field(
        default_factory=ApkSettings
    )

    content: ContentSettings = field(
        default_factory=ContentSettings
    )

    ai: AiSettings = field(
        default_factory=AiSettings
    )

    decision: DecisionSettings = field(
        default_factory=DecisionSettings
    )

    publisher: PublisherSettings = field(
        default_factory=PublisherSettings
    )

    admin: AdminAuthoritySettings = field(
        default_factory=AdminAuthoritySettings
    )

    memory: MemorySettings = field(
        default_factory=MemorySettings
    )

    audit: AuditSettings = field(
        default_factory=AuditSettings
    )

    rollback: RollbackSettings = field(
        default_factory=RollbackSettings
    )

    review: ReviewSettings = field(
        default_factory=ReviewSettings
    )

    security: SecuritySettings = field(
        default_factory=SecuritySettings
    )

    @property
    def dry_run(self) -> bool:
        return self.run_mode == RunMode.DRY_RUN.value

    @property
    def publishing_enabled(self) -> bool:
        return (
            self.run_mode == RunMode.PUBLISH.value
            and self.publisher.enabled
            and self.publisher.policy
            == PublishPolicy.EXPLICIT
        )

    @property
    def runtime_seconds(self) -> int:
        return self.runtime_minutes * 60

    @property
    def kill_switch_active(self) -> bool:
        return (
            self.security.kill_switch
            or not self.security.engine_enabled
        )

    def validate(self) -> None:
        if self.run_mode not in {
            RunMode.DRY_RUN.value,
            RunMode.PUBLISH.value,
        }:
            raise ValueError(
                f"Unsupported run mode: {self.run_mode}"
            )

        if not (
            MIN_RUNTIME_MINUTES
            <= self.runtime_minutes
            <= MAX_RUNTIME_MINUTES
        ):
            raise ValueError(
                "EngineConfig.runtime_minutes outside allowed range."
            )

        if not (
            MIN_MAX_APPS
            <= self.max_apps
            <= MAX_MAX_APPS
        ):
            raise ValueError(
                "EngineConfig.max_apps outside allowed range."
            )

        self.runtime.validate()
        self.network.validate()
        self.discovery.validate()
        self.resolver.validate()
        self.apk.validate()
        self.content.validate()
        self.ai.validate()
        self.decision.validate()
        self.publisher.validate()
        self.admin.validate()
        self.memory.validate()
        self.audit.validate()
        self.rollback.validate()
        self.review.validate()
        self.security.validate()

        if self.runtime.runtime_minutes != self.runtime_minutes:
            raise ValueError(
                "Runtime settings and top-level runtime_minutes differ."
            )

        if self.runtime.max_apps != self.max_apps:
            raise ValueError(
                "Runtime settings and top-level max_apps differ."
            )

        if self.kill_switch_active:
            if self.publishing_enabled:
                raise ValueError(
                    "Publishing cannot be enabled while kill switch is active."
                )

        if self.publisher.allow_delete:
            raise ValueError(
                "Publisher delete permission is forbidden."
            )

        if self.publisher.automatic_delete:
            raise ValueError(
                "Automatic deletion is forbidden."
            )

        if self.run_mode == RunMode.PUBLISH.value:
            if not self.publisher.enabled:
                # Publish mode can still run safely before publisher
                # integration. main.py treats this as non-destructive.
                pass


# ============================================================
# Configuration builders
# ============================================================

def _build_runtime_settings(
    *,
    runtime_minutes: int,
    max_apps: int,
) -> RuntimeSettings:
    return RuntimeSettings(
        runtime_minutes=runtime_minutes,
        max_apps=max_apps,
        per_app_budget_seconds=_read_int(
            ENV_PER_APP_BUDGET,
            default=DEFAULT_PER_APP_BUDGET_SECONDS,
            minimum=MIN_PER_APP_BUDGET_SECONDS,
            maximum=MAX_PER_APP_BUDGET_SECONDS,
        ),
        per_source_budget_seconds=_read_int(
            ENV_PER_SOURCE_BUDGET,
            default=DEFAULT_PER_SOURCE_BUDGET_SECONDS,
            minimum=MIN_PER_SOURCE_BUDGET_SECONDS,
            maximum=MAX_PER_SOURCE_BUDGET_SECONDS,
        ),
        graceful_shutdown_seconds=5,
    )


def _build_network_settings() -> NetworkSettings:
    return NetworkSettings(
        http_timeout_seconds=_read_float(
            ENV_HTTP_TIMEOUT,
            default=DEFAULT_HTTP_TIMEOUT_SECONDS,
            minimum=MIN_HTTP_TIMEOUT_SECONDS,
            maximum=MAX_HTTP_TIMEOUT_SECONDS,
        ),
        connect_timeout_seconds=_read_float(
            ENV_CONNECT_TIMEOUT,
            default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
            minimum=MIN_CONNECT_TIMEOUT_SECONDS,
            maximum=MAX_CONNECT_TIMEOUT_SECONDS,
        ),
        read_timeout_seconds=_read_float(
            ENV_READ_TIMEOUT,
            default=DEFAULT_READ_TIMEOUT_SECONDS,
            minimum=MIN_READ_TIMEOUT_SECONDS,
            maximum=MAX_READ_TIMEOUT_SECONDS,
        ),
        retries=_read_int(
            ENV_RETRIES,
            default=DEFAULT_RETRIES,
            minimum=MIN_RETRIES,
            maximum=MAX_RETRIES,
        ),
        backoff_seconds=_read_float(
            ENV_BACKOFF,
            default=DEFAULT_BACKOFF_SECONDS,
            minimum=MIN_BACKOFF_SECONDS,
            maximum=MAX_BACKOFF_SECONDS,
        ),
    )


def _build_discovery_settings() -> DiscoverySettings:
    return DiscoverySettings(
        enabled=_read_bool(
            ENV_DISCOVERY_ENABLED,
            True,
        ),
        sources=DEFAULT_DISCOVERY_SOURCES,
        per_source_limit=50,  # تم رفع الحد من 20 إلى 50
        minimum_candidate_confidence=0.0,
        deduplicate=True,
        validate_candidates=False,  # تم تعطيل الفلترة الصارمة للتحقق
        preserve_evidence=True,
        skip_known_admin_deleted=True,
        skip_known_cooldown_candidates=True,
        allow_existing_apps_for_health_check=True,
        prioritize_new_releases=True,
        stop_after_max_apps=True,
    )


def _build_resolver_settings() -> ResolverSettings:
    return ResolverSettings(
        enabled=_read_bool(
            ENV_RESOLVER_ENABLED,
            True,
        ),
    )


def _build_apk_settings() -> ApkSettings:
    return ApkSettings(
        enabled=_read_bool(
            ENV_APK_ENABLED,
            True,
        ),
    )


def _build_content_settings() -> ContentSettings:
    return ContentSettings(
        enabled=_read_bool(
            ENV_CONTENT_ENABLED,
            True,
        ),
    )


def _build_ai_settings() -> AiSettings:
    enabled = _read_bool(
        ENV_AI_ENABLED,
        True,
    )

    provider = (
        _env(
            ENV_AI_PROVIDER
        ).lower()
        or AiProviderName.NONE.value
    )

    model = _env(
        ENV_AI_MODEL
    )

    fallback_providers = _read_csv(
        ENV_AI_FALLBACK_PROVIDERS,
        default=(),
        maximum_items=10,
    )

    api_key_present = bool(
        _env(
            ENV_AI_API_KEY
        )
    )

    return AiSettings(
        enabled=enabled,
        provider=provider,
        model=model,
        fallback_providers=_unique_preserve_order(
            provider_name.lower()
            for provider_name in fallback_providers
        ),
        deterministic_fallback_enabled=True,
        evidence_grounding_required=False,  # تم إلغاء شرط إثبات المصدر
        allow_ai_package_id_guessing=True,  # تم السماح بالتكهن بالبيانات الناقصة
        allow_ai_apk_guessing=True,  # تم السماح بالتكهن بالروابط
        allow_ai_version_guessing=True,  # تم السماح بالتكهن بالإصدارات
        allow_ai_license_guessing=True,  # تم السماح بالتكهن بالتراخيص
        max_calls_per_run=30,
        max_calls_per_app=3,
        timeout_seconds=20.0,
        max_input_chars=50_000,
        max_output_chars=10_000,
        temperature=0.2,
        api_key_present=api_key_present,
    )


def _build_decision_settings() -> DecisionSettings:
    return DecisionSettings(
        enabled=True,
    )


def _build_publisher_settings(
    *,
    run_mode: str,
) -> PublisherSettings:
    publish_feature_enabled = _read_bool(
        ENV_PUBLISH_ENABLED,
        False,
    )

    supabase_url_present = bool(
        _env(
            ENV_SUPABASE_URL
        )
    )

    engine_key_present = bool(
        _env(
            ENV_SUPABASE_ENGINE_KEY
        )
    )

    policy = PublishPolicy.DISABLED

    if publish_feature_enabled:
        policy = PublishPolicy.EXPLICIT

    elif run_mode == RunMode.DRY_RUN.value:
        policy = PublishPolicy.DRY_RUN_ONLY

    return PublisherSettings(
        enabled=publish_feature_enabled,
        policy=policy,
        allow_insert=True,
        allow_update=True,
        allow_repair=True,
        allow_delete=False,
        automatic_delete=False,
        max_new_apps_per_run=50,  # تم رفع الحد الأقصى من 20 إلى 50
        max_updates_per_run=50,
        max_repairs_per_run=50,
        require_atomic_release_update=True,
        require_before_after_snapshot=True,
        respect_admin_tombstones=True,
        respect_manual_fields=True,
        require_supabase_credentials=True,
        supabase_url_present=supabase_url_present,
        engine_key_present=engine_key_present,
    )


def _build_admin_settings() -> AdminAuthoritySettings:
    return AdminAuthoritySettings(
        admin_has_priority=True,
        preserve_admin_deletions=True,
        preserve_admin_manual_fields=True,
        block_republish_after_admin_delete=True,
        block_rollback_over_newer_admin_change=True,
    )


def _build_memory_settings() -> MemorySettings:
    return MemorySettings(
        enabled=_read_bool(
            ENV_MEMORY_ENABLED,
            True,
        ),
    )


def _build_audit_settings() -> AuditSettings:
    return AuditSettings(
        enabled=_read_bool(
            ENV_AUDIT_ENABLED,
            True,
        ),
    )


def _build_rollback_settings() -> RollbackSettings:
    rollback_enabled = _read_bool(
        ENV_ROLLBACK_ENABLED,
        True,
    )

    return RollbackSettings(
        enabled=rollback_enabled,
        mode=(
            RollbackMode.SNAPSHOT_ONLY
            if rollback_enabled
            else RollbackMode.DISABLED
        ),
        allow_single_app_rollback=True,
        allow_run_rollback=False,
        hide_new_app_on_rollback=True,
        hard_delete_on_rollback=False,
        protect_newer_admin_changes=True,
    )


def _build_review_settings() -> ReviewSettings:
    return ReviewSettings(
        enabled=_read_bool(
            ENV_REVIEW_ENABLED,
            True,
        ),
    )


def _build_security_settings() -> SecuritySettings:
    engine_enabled = _read_bool(
        ENV_ENGINE_ENABLED,
        True,
    )

    explicit_kill_switch = _read_bool(
        ENV_KILL_SWITCH,
        False,
    )

    debug_enabled = _read_bool(
        ENV_DEBUG,
        False,
    )

    return SecuritySettings(
        engine_enabled=engine_enabled,
        kill_switch=explicit_kill_switch,
        debug_enabled=debug_enabled,
        least_privilege_required=True,
        secret_logging_forbidden=True,
        automatic_delete_forbidden=True,
        require_https_by_default=True,
        validate_external_urls=True,
        validate_external_text=True,
        restrict_network_hosts=True,
        block_private_network_targets=True,
        block_loopback_targets=True,
        block_link_local_targets=True,
        block_credential_urls=True,
        allow_shell_commands_from_external_data=False,
        allow_dynamic_code_execution=False,
        allow_untrusted_archive_execution=False,
        max_external_text_chars=100_000,
    )


# ============================================================
# Run mode parsing
# ============================================================

def _read_run_mode() -> str:
    run_mode = (
        _env(
            ENV_RUN_MODE
        ).lower()
        or RunMode.DRY_RUN.value
    )

    allowed = {
        item.value
        for item in RunMode
    }

    if run_mode not in allowed:
        raise ValueError(
            f"Invalid {ENV_RUN_MODE}: {run_mode!r}. "
            f"Allowed values: {', '.join(sorted(allowed))}"
        )

    return run_mode


# ============================================================
# Main configuration loader
# ============================================================

def load_config() -> EngineConfig:
    """
    Build the complete immutable engine configuration.

    This function performs no network requests and never prints
    secret values.
    """

    run_mode = _read_run_mode()

    runtime_minutes = _read_int(
        ENV_RUNTIME_MINUTES,
        default=DEFAULT_RUNTIME_MINUTES,
        minimum=MIN_RUNTIME_MINUTES,
        maximum=MAX_RUNTIME_MINUTES,
    )

    max_apps = _read_int(
        ENV_MAX_APPS,
        default=DEFAULT_MAX_APPS,
        minimum=MIN_MAX_APPS,
        maximum=MAX_MAX_APPS,
    )

    runtime_settings = _build_runtime_settings(
        runtime_minutes=runtime_minutes,
        max_apps=max_apps,
    )

    config = EngineConfig(
        run_mode=run_mode,
        runtime_minutes=runtime_minutes,
        max_apps=max_apps,
        workflow_kind=WorkflowKind.DISCOVER,
        runtime=runtime_settings,
        network=_build_network_settings(),
        discovery=_build_discovery_settings(),
        resolver=_build_resolver_settings(),
        apk=_build_apk_settings(),
        content=_build_content_settings(),
        ai=_build_ai_settings(),
        decision=_build_decision_settings(),
        publisher=_build_publisher_settings(
            run_mode=run_mode
        ),
        admin=_build_admin_settings(),
        memory=_build_memory_settings(),
        audit=_build_audit_settings(),
        rollback=_build_rollback_settings(),
        review=_build_review_settings(),
        security=_build_security_settings(),
    )

    config.validate()

    return config


# ============================================================
# Safe diagnostics
# ============================================================

def describe_config(
    config: EngineConfig,
) -> str:
    """
    Produce a human-readable configuration summary.

    Secrets are represented only as presence/absence booleans.
    """

    lines = [
        f"{ENGINE_NAME} v{ENGINE_VERSION}",
        f"Config schema: {CONFIG_SCHEMA_VERSION}",
        f"Component: {ENGINE_COMPONENT}",
        f"Workflow: {config.workflow_kind.value}",
        f"Mode: {config.run_mode}",
        f"Runtime limit: {config.runtime_minutes} minute(s)",
        f"Maximum applications: {config.max_apps}",
        f"Per-app budget: {config.runtime.per_app_budget_seconds}s",
        f"Per-source budget: {config.runtime.per_source_budget_seconds}s",
        f"Discovery enabled: {'yes' if config.discovery.enabled else 'no'}",
        f"Resolver enabled: {'yes' if config.resolver.enabled else 'no'}",
        f"APK Intelligence enabled: {'yes' if config.apk.enabled else 'no'}",
        f"Content Intelligence enabled: {'yes' if config.content.enabled else 'no'}",
        f"AI enabled: {'yes' if config.ai.enabled else 'no'}",
        f"AI provider: {config.ai.provider}",
        f"AI key present: {'yes' if config.ai.api_key_present else 'no'}",
        f"Publisher feature enabled: {'yes' if config.publisher.enabled else 'no'}",
        f"Publishing enabled for this run: {'yes' if config.publishing_enabled else 'no'}",
        f"Memory enabled: {'yes' if config.memory.enabled else 'no'}",
        f"Audit enabled: {'yes' if config.audit.enabled else 'no'}",
        f"Rollback enabled: {'yes' if config.rollback.enabled else 'no'}",
        f"Review enabled: {'yes' if config.review.enabled else 'no'}",
        f"Admin authority: {'yes' if config.admin.admin_has_priority else 'no'}",
        f"Automatic delete: no",
        f"Kill switch active: {'yes' if config.kill_switch_active else 'no'}",
        f"Debug enabled: {'yes' if config.security.debug_enabled else 'no'}",
    ]

    return "\n".join(
        lines
    )


# ============================================================
# Machine-safe summary
# ============================================================

def config_summary_dict(
    config: EngineConfig,
) -> dict[str, object]:
    """
    Return a safe serializable configuration summary.

    Credential values are deliberately excluded.
    """

    return {
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "config_schema": CONFIG_SCHEMA_VERSION,
        },
        "workflow": config.workflow_kind.value,
        "run_mode": config.run_mode,
        "runtime_minutes": config.runtime_minutes,
        "max_apps": config.max_apps,
        "publishing_enabled": config.publishing_enabled,
        "kill_switch_active": config.kill_switch_active,
        "modules": {
            "discovery": config.discovery.enabled,
            "resolver": config.resolver.enabled,
            "apk": config.apk.enabled,
            "content": config.content.enabled,
            "ai": config.ai.enabled,
            "publisher": config.publisher.enabled,
            "memory": config.memory.enabled,
            "audit": config.audit.enabled,
            "rollback": config.rollback.enabled,
            "review": config.review.enabled,
        },
        "security": {
            "least_privilege_required": (
                config.security.least_privilege_required
            ),
            "automatic_delete_forbidden": (
                config.security.automatic_delete_forbidden
            ),
            "secret_logging_forbidden": (
                config.security.secret_logging_forbidden
            ),
            "restrict_network_hosts": (
                config.security.restrict_network_hosts
            ),
            "dynamic_code_execution": (
                config.security.allow_dynamic_code_execution
            ),
        },
        "credentials_present": {
            "supabase_url": config.publisher.supabase_url_present,
            "engine_key": config.publisher.engine_key_present,
            "ai_key": config.ai.api_key_present,
            "github_token": bool(
                _env(
                    ENV_GITHUB_TOKEN
                )
            ),
        },
    }


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "AdminAuthoritySettings",
    "AiProviderName",
    "AiSettings",
    "ApkSettings",
    "AuditSettings",
    "AutomaticDecision",
    "CONFIG_SCHEMA_VERSION",
    "ContentSettings",
    "DEFAULT_APK_SOURCE_PRIORITY",
    "DEFAULT_CONTENT_SOURCE_PRIORITY",
    "DEFAULT_DISCOVERY_SOURCES",
    "DEFAULT_MAX_APPS",
    "DEFAULT_METADATA_SOURCE_PRIORITY",
    "DEFAULT_RUNTIME_MINUTES",
    "DecisionSettings",
    "DiscoverySettings",
    "ENGINE_COMPONENT",
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "EngineConfig",
    "ManagedBy",
    "MemorySettings",
    "NetworkSettings",
    "PublishPolicy",
    "PublisherSettings",
    "ResolverSettings",
    "ReviewDecision",
    "ReviewSettings",
    "RollbackMode",
    "RollbackSettings",
    "RunMode",
    "RuntimeSettings",
    "SecuritySettings",
    "SourceName",
    "WorkflowKind",
    "config_summary_dict",
    "describe_config",
    "load_config",
)
