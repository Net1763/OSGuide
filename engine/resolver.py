"""
OSGuide Engine
Super Resolver Layer

Purpose
-------
The Super Resolver receives an AppCandidate from Discovery and tries to
resolve missing or conflicting application metadata by consulting
multiple trusted evidence providers.

This module is intentionally independent from:
- Supabase publishing
- final Decision Engine actions
- APK binary inspection
- AI content writing
- rollback execution
- Admin UI behavior

Architecture rules
------------------
1. Never fabricate Package ID, APK URL, version, license or repository.
2. Missing data is not automatically fatal.
3. A short description must never cause an application to be skipped.
4. A difficult candidate must not consume the whole engine runtime.
5. Every field has a bounded attempt budget.
6. Every provider failure is isolated.
7. Conflicts are preserved as evidence, not silently overwritten.
8. Higher-confidence evidence wins only when policy permits.
9. Admin authority will be enforced later by the Publisher/Decision
   layers; Resolver does not override manual admin fields.
10. Resolver must be usable for both new-app discovery and existing-app
    repair/update workflows.
11. Resolver stores provenance for every resolved field.
12. Resolver may return a partial result so the engine can continue.
13. No deletion is performed here.
14. No external writes are performed here.
15. Real network providers plug into provider interfaces later.

Current implementation provides:
- normalized metadata field model
- evidence model
- field-level confidence
- provider interface
- field strategies
- conflict detection
- merge logic
- bounded attempts
- timeout-budget awareness hooks
- resolution report
- deterministic diagnostic providers
- duplicate evidence suppression
- package/repository/version/license/category/icon validation
- public diagnostics

The first live providers will be added separately so this file remains a
stable orchestration layer.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Final,
    Iterable,
    Mapping,
    Protocol,
    Sequence,
)
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from discovery import (
    AppCandidate,
    CandidateEvidence,
    EvidenceKind,
    SourceType,
    is_valid_http_url,
    is_valid_package_id,
    normalize_url,
    sanitize_error,
    sanitize_text,
)


# ============================================================
# Component identity
# ============================================================

RESOLVER_COMPONENT: Final[str] = "Super Resolver"
RESOLVER_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Hard safety limits
# ============================================================

MAX_FIELD_VALUE_LENGTH: Final[int] = 10_000
MAX_FIELD_EVIDENCE_ITEMS: Final[int] = 50
MAX_CONFLICTS_PER_FIELD: Final[int] = 20
MAX_PROVIDER_ERRORS: Final[int] = 100
MAX_PROVIDER_NAME_LENGTH: Final[int] = 80

DEFAULT_FIELD_ATTEMPTS: Final[int] = 4
MAX_FIELD_ATTEMPTS: Final[int] = 10

DEFAULT_PROVIDER_TIMEOUT_SECONDS: Final[float] = 8.0
MIN_PROVIDER_TIMEOUT_SECONDS: Final[float] = 1.0
MAX_PROVIDER_TIMEOUT_SECONDS: Final[float] = 30.0

DEFAULT_MIN_ACCEPT_CONFIDENCE: Final[float] = 0.60
DEFAULT_STRONG_ACCEPT_CONFIDENCE: Final[float] = 0.85

MAX_TOTAL_RESOLUTION_SECONDS: Final[float] = 60.0
DEFAULT_TOTAL_RESOLUTION_SECONDS: Final[float] = 20.0

VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._+~:-]{0,127}$"
)

LICENSE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9 ._+()/:-]{0,199}$"
)

CATEGORY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9 &/._+-]{0,99}$"
)


# ============================================================
# Enums
# ============================================================

class MetadataField(str, Enum):
    NAME = "name"
    PACKAGE_ID = "package_id"
    VERSION = "version"
    REPOSITORY_URL = "repository_url"
    SOURCE_URL = "source_url"
    APK_URL = "apk_url"
    ICON_URL = "icon_url"
    LICENSE = "license"
    CATEGORY = "category"
    SHORT_DESCRIPTION = "short_description"
    FULL_DESCRIPTION = "full_description"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"
    SKIPPED = "skipped"
    FAILED = "failed"


class FieldState(str, Enum):
    EMPTY = "empty"
    RESOLVED = "resolved"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class ProviderStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


class ConflictSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================================
# Resolver evidence
# ============================================================

@dataclass(frozen=True, slots=True)
class FieldEvidence:
    field: MetadataField
    value: str
    provider_name: str
    source_type: SourceType
    source_url: str
    confidence: float
    observed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    note: str | None = None

    def validate(self) -> None:
        if not self.provider_name.strip():
            raise ValueError("Resolver provider name cannot be empty.")

        if len(self.provider_name) > MAX_PROVIDER_NAME_LENGTH:
            raise ValueError("Resolver provider name is too long.")

        if not self.value.strip():
            raise ValueError("Resolver evidence value cannot be empty.")

        if len(self.value) > MAX_FIELD_VALUE_LENGTH:
            raise ValueError("Resolver evidence value is too long.")

        if not is_valid_http_url(self.source_url, require_https=True):
            raise ValueError("Resolver evidence requires a valid HTTPS source URL.")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Resolver evidence confidence must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class FieldConflict:
    field: MetadataField
    current_value: str
    incoming_value: str
    current_confidence: float
    incoming_confidence: float
    severity: ConflictSeverity
    provider_name: str
    note: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ============================================================
# Resolved field model
# ============================================================

@dataclass(slots=True)
class ResolvedField:
    field: MetadataField
    value: str | None = None
    confidence: float = 0.0
    state: FieldState = FieldState.EMPTY
    selected_provider: str | None = None
    selected_source_url: str | None = None
    evidence: list[FieldEvidence] = field(default_factory=list)
    conflicts: list[FieldConflict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        message = sanitize_text(message, max_length=300)

        if message and message not in self.warnings:
            self.warnings.append(message)

    def add_evidence(self, item: FieldEvidence) -> None:
        item.validate()

        if len(self.evidence) >= MAX_FIELD_EVIDENCE_ITEMS:
            self.add_warning("Field evidence limit reached.")
            return

        fingerprint = field_evidence_fingerprint(item)

        known = {
            field_evidence_fingerprint(existing)
            for existing in self.evidence
        }

        if fingerprint not in known:
            self.evidence.append(item)

    def add_conflict(self, conflict: FieldConflict) -> None:
        if len(self.conflicts) >= MAX_CONFLICTS_PER_FIELD:
            self.add_warning("Field conflict limit reached.")
            return

        self.conflicts.append(conflict)

    @property
    def resolved(self) -> bool:
        return (
            self.value is not None
            and self.state == FieldState.RESOLVED
        )


# ============================================================
# Application resolution result
# ============================================================

@dataclass(slots=True)
class ResolvedApplication:
    candidate_identity: str
    candidate_name: str

    fields: dict[MetadataField, ResolvedField] = field(default_factory=dict)

    status: ResolutionStatus = ResolutionStatus.UNRESOLVED

    provider_errors: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    finished_at: datetime | None = None

    providers_attempted: int = 0
    providers_succeeded: int = 0
    providers_failed: int = 0
    field_attempts: int = 0

    timed_out: bool = False

    @property
    def duration_seconds(self) -> float:
        end_time = self.finished_at or datetime.now(timezone.utc)

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )

    @property
    def resolved_field_count(self) -> int:
        return sum(
            1
            for field_result in self.fields.values()
            if field_result.resolved
        )

    @property
    def conflict_count(self) -> int:
        return sum(
            len(field_result.conflicts)
            for field_result in self.fields.values()
        )

    def field_result(self, metadata_field: MetadataField) -> ResolvedField:
        existing = self.fields.get(metadata_field)

        if existing is not None:
            return existing

        created = ResolvedField(field=metadata_field)
        self.fields[metadata_field] = created

        return created

    def add_provider_error(self, message: str) -> None:
        if len(self.provider_errors) >= MAX_PROVIDER_ERRORS:
            return

        cleaned = sanitize_text(message, max_length=500)

        if cleaned:
            self.provider_errors.append(cleaned)

    def add_warning(self, message: str) -> None:
        cleaned = sanitize_text(message, max_length=500)

        if cleaned and cleaned not in self.warnings:
            self.warnings.append(cleaned)


# ============================================================
# Provider result model
# ============================================================

@dataclass(slots=True)
class ResolverProviderResult:
    provider_name: str
    status: ProviderStatus
    evidence: list[FieldEvidence] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return (
            self.status == ProviderStatus.SUCCESS
            and self.error is None
        )


# ============================================================
# Resolver settings
# ============================================================

@dataclass(frozen=True, slots=True)
class ResolverPolicy:
    max_attempts_per_field: int = DEFAULT_FIELD_ATTEMPTS
    provider_timeout_seconds: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS
    total_budget_seconds: float = DEFAULT_TOTAL_RESOLUTION_SECONDS

    minimum_accept_confidence: float = DEFAULT_MIN_ACCEPT_CONFIDENCE
    strong_accept_confidence: float = DEFAULT_STRONG_ACCEPT_CONFIDENCE

    allow_partial: bool = True
    preserve_conflicts: bool = True
    stop_field_on_strong_evidence: bool = True
    skip_difficult_candidate_on_budget_exhaustion: bool = True

    resolve_name: bool = True
    resolve_package_id: bool = True
    resolve_version: bool = True
    resolve_repository_url: bool = True
    resolve_source_url: bool = True
    resolve_apk_url: bool = True
    resolve_icon_url: bool = True
    resolve_license: bool = True
    resolve_category: bool = True
    resolve_short_description: bool = True
    resolve_full_description: bool = True

    def validate(self) -> None:
        if not 1 <= self.max_attempts_per_field <= MAX_FIELD_ATTEMPTS:
            raise ValueError("max_attempts_per_field outside allowed range.")

        if not (
            MIN_PROVIDER_TIMEOUT_SECONDS
            <= self.provider_timeout_seconds
            <= MAX_PROVIDER_TIMEOUT_SECONDS
        ):
            raise ValueError("provider_timeout_seconds outside allowed range.")

        if not 1.0 <= self.total_budget_seconds <= MAX_TOTAL_RESOLUTION_SECONDS:
            raise ValueError("total_budget_seconds outside allowed range.")

        if not 0.0 <= self.minimum_accept_confidence <= 1.0:
            raise ValueError("minimum_accept_confidence must be between 0 and 1.")

        if not 0.0 <= self.strong_accept_confidence <= 1.0:
            raise ValueError("strong_accept_confidence must be between 0 and 1.")

        if self.strong_accept_confidence < self.minimum_accept_confidence:
            raise ValueError(
                "strong_accept_confidence cannot be lower than "
                "minimum_accept_confidence."
            )


# ============================================================
# Provider protocol
# ============================================================

class ResolverProvider(Protocol):
    name: str
    source_type: SourceType

    def resolve(
        self,
        candidate: AppCandidate,
        *,
        fields: Sequence[MetadataField],
        timeout_seconds: float,
    ) -> list[FieldEvidence]:
        ...


# ============================================================
# Base provider
# ============================================================

class BaseResolverProvider:
    name: str = "unknown"
    source_type: SourceType = SourceType.OFFICIAL

    def resolve(
        self,
        candidate: AppCandidate,
        *,
        fields: Sequence[MetadataField],
        timeout_seconds: float,
    ) -> list[FieldEvidence]:
        raise NotImplementedError


# ============================================================
# Value normalization
# ============================================================

def normalize_field_value(
    metadata_field: MetadataField,
    value: str,
) -> str:
    value = sanitize_text(
        value,
        max_length=MAX_FIELD_VALUE_LENGTH,
    )

    if not value:
        raise ValueError("Resolved field value cannot be empty.")

    if metadata_field == MetadataField.PACKAGE_ID:
        if not is_valid_package_id(value):
            raise ValueError(f"Invalid package ID: {value!r}")
        return value.strip()

    if metadata_field in {
        MetadataField.REPOSITORY_URL,
        MetadataField.SOURCE_URL,
        MetadataField.APK_URL,
        MetadataField.ICON_URL,
    }:
        if not is_valid_http_url(value, require_https=True):
            raise ValueError(
                f"{metadata_field.value} requires a valid HTTPS URL."
            )
        return normalize_url(value)

    if metadata_field == MetadataField.VERSION:
        if not VERSION_PATTERN.fullmatch(value):
            raise ValueError(f"Invalid version value: {value!r}")
        return value

    if metadata_field == MetadataField.LICENSE:
        if not LICENSE_PATTERN.fullmatch(value):
            raise ValueError(f"Invalid license value: {value!r}")
        return value

    if metadata_field == MetadataField.CATEGORY:
        if not CATEGORY_PATTERN.fullmatch(value):
            raise ValueError(f"Invalid category value: {value!r}")
        return value

    return value


# ============================================================
# Evidence fingerprint
# ============================================================

def field_evidence_fingerprint(
    evidence: FieldEvidence,
) -> str:
    normalized_value = normalize_field_value(
        evidence.field,
        evidence.value,
    )

    raw = "|".join(
        (
            evidence.field.value,
            normalized_value.lower(),
            evidence.provider_name.lower(),
            evidence.source_type.value,
            normalize_url(evidence.source_url),
        )
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# Conflict logic
# ============================================================

def values_equivalent(
    metadata_field: MetadataField,
    first: str,
    second: str,
) -> bool:
    try:
        normalized_first = normalize_field_value(
            metadata_field,
            first,
        )

        normalized_second = normalize_field_value(
            metadata_field,
            second,
        )
    except ValueError:
        return False

    if metadata_field in {
        MetadataField.REPOSITORY_URL,
        MetadataField.SOURCE_URL,
        MetadataField.APK_URL,
        MetadataField.ICON_URL,
        MetadataField.PACKAGE_ID,
    }:
        return normalized_first.lower() == normalized_second.lower()

    return normalized_first == normalized_second


def conflict_severity(
    metadata_field: MetadataField,
) -> ConflictSeverity:
    if metadata_field in {
        MetadataField.PACKAGE_ID,
        MetadataField.APK_URL,
        MetadataField.REPOSITORY_URL,
    }:
        return ConflictSeverity.HIGH

    if metadata_field in {
        MetadataField.VERSION,
        MetadataField.LICENSE,
        MetadataField.SOURCE_URL,
    }:
        return ConflictSeverity.MEDIUM

    return ConflictSeverity.LOW


# ============================================================
# Field selection rules
# ============================================================

def should_replace_field(
    current: ResolvedField,
    incoming: FieldEvidence,
    *,
    policy: ResolverPolicy,
) -> bool:
    if current.value is None:
        return incoming.confidence >= policy.minimum_accept_confidence

    if values_equivalent(
        current.field,
        current.value,
        incoming.value,
    ):
        return incoming.confidence > current.confidence

    if incoming.confidence >= policy.strong_accept_confidence:
        if incoming.confidence > current.confidence:
            return True

    return False


def apply_field_evidence(
    field_result: ResolvedField,
    evidence: FieldEvidence,
    *,
    policy: ResolverPolicy,
) -> None:
    evidence.validate()

    normalized_value = normalize_field_value(
        evidence.field,
        evidence.value,
    )

    normalized_evidence = FieldEvidence(
        field=evidence.field,
        value=normalized_value,
        provider_name=evidence.provider_name,
        source_type=evidence.source_type,
        source_url=evidence.source_url,
        confidence=evidence.confidence,
        observed_at=evidence.observed_at,
        note=evidence.note,
    )

    field_result.add_evidence(normalized_evidence)

    if field_result.value is None:
        if (
            normalized_evidence.confidence
            >= policy.minimum_accept_confidence
        ):
            field_result.value = normalized_value
            field_result.confidence = normalized_evidence.confidence
            field_result.state = FieldState.RESOLVED
            field_result.selected_provider = normalized_evidence.provider_name
            field_result.selected_source_url = normalized_evidence.source_url

        return

    if values_equivalent(
        field_result.field,
        field_result.value,
        normalized_value,
    ):
        if normalized_evidence.confidence > field_result.confidence:
            field_result.confidence = normalized_evidence.confidence
            field_result.selected_provider = normalized_evidence.provider_name
            field_result.selected_source_url = normalized_evidence.source_url

        return

    conflict = FieldConflict(
        field=field_result.field,
        current_value=field_result.value,
        incoming_value=normalized_value,
        current_confidence=field_result.confidence,
        incoming_confidence=normalized_evidence.confidence,
        severity=conflict_severity(field_result.field),
        provider_name=normalized_evidence.provider_name,
        note="Conflicting field evidence observed.",
    )

    if policy.preserve_conflicts:
        field_result.add_conflict(conflict)

    if should_replace_field(
        field_result,
        normalized_evidence,
        policy=policy,
    ):
        field_result.value = normalized_value
        field_result.confidence = normalized_evidence.confidence
        field_result.selected_provider = normalized_evidence.provider_name
        field_result.selected_source_url = normalized_evidence.source_url
        field_result.state = FieldState.RESOLVED
    else:
        field_result.state = FieldState.CONFLICT


# ============================================================
# Candidate bootstrap
# ============================================================

def candidate_bootstrap_evidence(
    candidate: AppCandidate,
) -> list[FieldEvidence]:
    """
    Convert trusted Discovery hints into Resolver evidence.

    These are only hints; confidence remains bounded.
    """

    output: list[FieldEvidence] = []

    source_type = candidate.source_enum
    confidence = max(
        0.0,
        min(1.0, candidate.source_confidence),
    )

    source_url = candidate.source_url

    def add(
        metadata_field: MetadataField,
        value: str | None,
    ) -> None:
        if not value:
            return

        output.append(
            FieldEvidence(
                field=metadata_field,
                value=value,
                provider_name="discovery-bootstrap",
                source_type=source_type,
                source_url=source_url,
                confidence=confidence,
                note="Value carried forward from Discovery.",
            )
        )

    add(MetadataField.NAME, candidate.name)
    add(MetadataField.PACKAGE_ID, candidate.package_id)
    add(MetadataField.REPOSITORY_URL, candidate.repository_url)
    add(MetadataField.SOURCE_URL, candidate.source_url)

    if candidate.description:
        add(
            MetadataField.SHORT_DESCRIPTION,
            candidate.description,
        )

    return output


# ============================================================
# Field enablement
# ============================================================

def enabled_fields(
    policy: ResolverPolicy,
) -> tuple[MetadataField, ...]:
    mappings = (
        (MetadataField.NAME, policy.resolve_name),
        (MetadataField.PACKAGE_ID, policy.resolve_package_id),
        (MetadataField.VERSION, policy.resolve_version),
        (
            MetadataField.REPOSITORY_URL,
            policy.resolve_repository_url,
        ),
        (
            MetadataField.SOURCE_URL,
            policy.resolve_source_url,
        ),
        (MetadataField.APK_URL, policy.resolve_apk_url),
        (MetadataField.ICON_URL, policy.resolve_icon_url),
        (MetadataField.LICENSE, policy.resolve_license),
        (MetadataField.CATEGORY, policy.resolve_category),
        (
            MetadataField.SHORT_DESCRIPTION,
            policy.resolve_short_description,
        ),
        (
            MetadataField.FULL_DESCRIPTION,
            policy.resolve_full_description,
        ),
    )

    return tuple(
        metadata_field
        for metadata_field, enabled in mappings
        if enabled
    )


# ============================================================
# Provider validation
# ============================================================

def validate_provider(
    provider: ResolverProvider,
) -> None:
    name = getattr(provider, "name", None)
    source_type = getattr(provider, "source_type", None)
    method = getattr(provider, "resolve", None)

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Resolver provider requires a non-empty name.")

    if len(name) > MAX_PROVIDER_NAME_LENGTH:
        raise ValueError("Resolver provider name is too long.")

    if not isinstance(source_type, SourceType):
        raise TypeError("Resolver provider requires SourceType.")

    if not callable(method):
        raise TypeError("Resolver provider requires resolve().")


# ============================================================
# Provider registry
# ============================================================

class ResolverRegistry:
    def __init__(self) -> None:
        self._providers: list[ResolverProvider] = []
        self._names: set[str] = set()

    @property
    def providers(self) -> tuple[ResolverProvider, ...]:
        return tuple(self._providers)

    def register(self, provider: ResolverProvider) -> None:
        validate_provider(provider)

        normalized = provider.name.strip().lower()

        if normalized in self._names:
            raise ValueError(
                f"Duplicate Resolver provider name: {provider.name}"
            )

        self._providers.append(provider)
        self._names.add(normalized)

    def extend(self, providers: Iterable[ResolverProvider]) -> None:
        for provider in providers:
            self.register(provider)


# ============================================================
# Provider execution
# ============================================================

def run_provider(
    provider: ResolverProvider,
    candidate: AppCandidate,
    *,
    fields: Sequence[MetadataField],
    timeout_seconds: float,
) -> ResolverProviderResult:
    started = time.monotonic()

    try:
        validate_provider(provider)

        if not (
            MIN_PROVIDER_TIMEOUT_SECONDS
            <= timeout_seconds
            <= MAX_PROVIDER_TIMEOUT_SECONDS
        ):
            raise ValueError("Resolver provider timeout outside allowed range.")

        evidence = provider.resolve(
            candidate,
            fields=fields,
            timeout_seconds=timeout_seconds,
        )

        if not isinstance(evidence, list):
            raise TypeError("Resolver provider must return a list.")

        valid: list[FieldEvidence] = []

        for item in evidence:
            if not isinstance(item, FieldEvidence):
                raise TypeError(
                    "Resolver provider returned a non-FieldEvidence item."
                )

            item.validate()
            valid.append(item)

        return ResolverProviderResult(
            provider_name=provider.name,
            status=ProviderStatus.SUCCESS,
            evidence=valid,
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )

    except Exception as exc:
        return ResolverProviderResult(
            provider_name=getattr(provider, "name", "unknown"),
            status=ProviderStatus.FAILURE,
            error=sanitize_error(exc),
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )


# ============================================================
# Resolution budget
# ============================================================

class ResolutionBudget:
    def __init__(self, total_seconds: float) -> None:
        if not 1.0 <= total_seconds <= MAX_TOTAL_RESOLUTION_SECONDS:
            raise ValueError("Resolver total budget outside allowed range.")

        self._started = time.monotonic()
        self._total = total_seconds

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self._started)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self._total - self.elapsed_seconds)

    @property
    def exhausted(self) -> bool:
        return self.remaining_seconds <= 0.0

    def provider_timeout(self, requested: float) -> float:
        if self.exhausted:
            return 0.0

        return max(
            0.0,
            min(requested, self.remaining_seconds),
        )


# ============================================================
# Field attempt bookkeeping
# ============================================================

@dataclass(slots=True)
class FieldAttemptState:
    attempts: dict[MetadataField, int] = field(default_factory=dict)

    def count(self, metadata_field: MetadataField) -> int:
        return self.attempts.get(metadata_field, 0)

    def increment(self, metadata_field: MetadataField) -> int:
        new_value = self.count(metadata_field) + 1
        self.attempts[metadata_field] = new_value
        return new_value

    def exhausted(
        self,
        metadata_field: MetadataField,
        *,
        max_attempts: int,
    ) -> bool:
        return self.count(metadata_field) >= max_attempts


# ============================================================
# Resolution status evaluation
# ============================================================

IMPORTANT_FIELDS: Final[tuple[MetadataField, ...]] = (
    MetadataField.NAME,
    MetadataField.PACKAGE_ID,
    MetadataField.VERSION,
    MetadataField.SOURCE_URL,
    MetadataField.APK_URL,
)

NON_FATAL_CONTENT_FIELDS: Final[tuple[MetadataField, ...]] = (
    MetadataField.SHORT_DESCRIPTION,
    MetadataField.FULL_DESCRIPTION,
)


def evaluate_resolution_status(
    result: ResolvedApplication,
    *,
    policy: ResolverPolicy,
) -> ResolutionStatus:
    conflict_fields = [
        field_result
        for field_result in result.fields.values()
        if field_result.conflicts
        and field_result.state == FieldState.CONFLICT
    ]

    if conflict_fields:
        high_conflict = any(
            any(
                conflict.severity == ConflictSeverity.HIGH
                for conflict in field_result.conflicts
            )
            for field_result in conflict_fields
        )

        if high_conflict:
            return ResolutionStatus.CONFLICT

    resolved_important = 0

    for metadata_field in IMPORTANT_FIELDS:
        field_result = result.fields.get(metadata_field)

        if field_result and field_result.resolved:
            resolved_important += 1

    if resolved_important == len(IMPORTANT_FIELDS):
        return ResolutionStatus.RESOLVED

    if result.resolved_field_count > 0 and policy.allow_partial:
        return ResolutionStatus.PARTIAL

    if result.provider_errors and result.resolved_field_count == 0:
        return ResolutionStatus.FAILED

    return ResolutionStatus.UNRESOLVED


# ============================================================
# Super Resolver orchestration
# ============================================================

def resolve_candidate(
    candidate: AppCandidate,
    providers: Sequence[ResolverProvider],
    *,
    policy: ResolverPolicy | None = None,
) -> ResolvedApplication:
    """
    Resolve one candidate safely.

    The candidate may leave partially resolved. This is intentional:
    later Decision logic can choose repair/review/skip without making
    the entire run fail.
    """

    if policy is None:
        policy = ResolverPolicy()

    policy.validate()
    candidate.validate()

    result = ResolvedApplication(
        candidate_identity=candidate.identity,
        candidate_name=candidate.name,
    )

    budget = ResolutionBudget(
        policy.total_budget_seconds
    )

    attempts = FieldAttemptState()

    active_fields = enabled_fields(policy)

    for evidence in candidate_bootstrap_evidence(candidate):
        field_result = result.field_result(evidence.field)

        try:
            apply_field_evidence(
                field_result,
                evidence,
                policy=policy,
            )
        except Exception as exc:
            field_result.add_warning(
                f"Discovery bootstrap evidence rejected: {sanitize_error(exc)}"
            )

    for provider in providers:
        if budget.exhausted:
            result.timed_out = True
            result.add_warning(
                "Resolver time budget exhausted; moving to next candidate."
            )
            break

        unresolved_fields: list[MetadataField] = []

        for metadata_field in active_fields:
            field_result = result.field_result(metadata_field)

            if (
                field_result.resolved
                and policy.stop_field_on_strong_evidence
                and field_result.confidence >= policy.strong_accept_confidence
            ):
                continue

            if attempts.exhausted(
                metadata_field,
                max_attempts=policy.max_attempts_per_field,
            ):
                continue

            unresolved_fields.append(metadata_field)

        if not unresolved_fields:
            break

        timeout = budget.provider_timeout(
            policy.provider_timeout_seconds
        )

        if timeout < MIN_PROVIDER_TIMEOUT_SECONDS:
            result.timed_out = True
            result.add_warning(
                "Insufficient remaining budget for another provider."
            )
            break

        for metadata_field in unresolved_fields:
            attempts.increment(metadata_field)
            result.field_attempts += 1

        result.providers_attempted += 1

        provider_result = run_provider(
            provider,
            candidate,
            fields=unresolved_fields,
            timeout_seconds=timeout,
        )

        if not provider_result.succeeded:
            result.providers_failed += 1
            result.add_provider_error(
                f"{provider_result.provider_name}: "
                f"{provider_result.error or 'unknown error'}"
            )
            continue

        result.providers_succeeded += 1

        for evidence in provider_result.evidence:
            field_result = result.field_result(evidence.field)

            try:
                apply_field_evidence(
                    field_result,
                    evidence,
                    policy=policy,
                )
            except Exception as exc:
                field_result.add_warning(
                    f"Provider evidence rejected: {sanitize_error(exc)}"
                )

    result.status = evaluate_resolution_status(
        result,
        policy=policy,
    )

    result.finished_at = datetime.now(timezone.utc)

    return result


# ============================================================
# Batch resolution
# ============================================================

@dataclass(slots=True)
class BatchResolutionReport:
    started_at: datetime
    finished_at: datetime | None = None
    results: list[ResolvedApplication] = field(default_factory=list)
    failures: int = 0
    skipped: int = 0

    @property
    def duration_seconds(self) -> float:
        end_time = self.finished_at or datetime.now(timezone.utc)

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )


def resolve_candidates(
    candidates: Iterable[AppCandidate],
    providers: Sequence[ResolverProvider],
    *,
    policy: ResolverPolicy | None = None,
    max_candidates: int | None = None,
) -> BatchResolutionReport:
    report = BatchResolutionReport(
        started_at=datetime.now(timezone.utc)
    )

    if max_candidates is not None and max_candidates < 1:
        raise ValueError("max_candidates must be at least 1.")

    for index, candidate in enumerate(candidates, start=1):
        if max_candidates is not None and index > max_candidates:
            break

        try:
            result = resolve_candidate(
                candidate,
                providers,
                policy=policy,
            )

        except Exception as exc:
            report.failures += 1

            failed = ResolvedApplication(
                candidate_identity=getattr(candidate, "identity", "unknown"),
                candidate_name=getattr(candidate, "name", "unknown"),
                status=ResolutionStatus.FAILED,
                provider_errors=[sanitize_error(exc)],
                finished_at=datetime.now(timezone.utc),
            )

            report.results.append(failed)
            continue

        if result.status == ResolutionStatus.SKIPPED:
            report.skipped += 1

        if result.status == ResolutionStatus.FAILED:
            report.failures += 1

        report.results.append(result)

    report.finished_at = datetime.now(timezone.utc)

    return report


# ============================================================
# Diagnostic providers
# ============================================================

class DiagnosticResolverProvider(BaseResolverProvider):
    """
    Local deterministic provider.

    No network requests and no external writes.
    """

    name = "diagnostic-resolver"
    source_type = SourceType.GITHUB

    def resolve(
        self,
        candidate: AppCandidate,
        *,
        fields: Sequence[MetadataField],
        timeout_seconds: float,
    ) -> list[FieldEvidence]:
        del timeout_seconds

        evidence: list[FieldEvidence] = []

        requested = set(fields)

        def add(
            metadata_field: MetadataField,
            value: str,
            confidence: float,
        ) -> None:
            if metadata_field not in requested:
                return

            evidence.append(
                FieldEvidence(
                    field=metadata_field,
                    value=value,
                    provider_name=self.name,
                    source_type=self.source_type,
                    source_url="https://github.com/",
                    confidence=confidence,
                    note="Synthetic diagnostic resolver evidence.",
                )
            )

        add(
            MetadataField.NAME,
            candidate.name or "Diagnostic App",
            0.95,
        )

        add(
            MetadataField.PACKAGE_ID,
            candidate.package_id or "org.osguide.diagnostic",
            0.90,
        )

        add(
            MetadataField.VERSION,
            "1.0.0",
            0.90,
        )

        add(
            MetadataField.REPOSITORY_URL,
            candidate.repository_url or "https://github.com/",
            0.90,
        )

        add(
            MetadataField.SOURCE_URL,
            candidate.source_url,
            0.95,
        )

        add(
            MetadataField.APK_URL,
            "https://github.com/example/osguide-diagnostic/releases/download/v1.0.0/app.apk",
            0.70,
        )

        add(
            MetadataField.ICON_URL,
            "https://github.com/favicon.ico",
            0.60,
        )

        add(
            MetadataField.LICENSE,
            "GPL-3.0",
            0.90,
        )

        add(
            MetadataField.CATEGORY,
            "Development",
            0.80,
        )

        add(
            MetadataField.SHORT_DESCRIPTION,
            "Diagnostic application used to verify the OSGuide Resolver.",
            0.90,
        )

        add(
            MetadataField.FULL_DESCRIPTION,
            (
                "This is synthetic resolver content used only to test "
                "field selection, provenance, confidence, and conflict "
                "handling inside the OSGuide engine."
            ),
            0.90,
        )

        return evidence


class DiagnosticConflictProvider(BaseResolverProvider):
    """
    Produces deliberate conflicts for testing conflict preservation.
    """

    name = "diagnostic-conflict"
    source_type = SourceType.GITLAB

    def resolve(
        self,
        candidate: AppCandidate,
        *,
        fields: Sequence[MetadataField],
        timeout_seconds: float,
    ) -> list[FieldEvidence]:
        del candidate
        del timeout_seconds

        evidence: list[FieldEvidence] = []

        requested = set(fields)

        if MetadataField.VERSION in requested:
            evidence.append(
                FieldEvidence(
                    field=MetadataField.VERSION,
                    value="2.0.0",
                    provider_name=self.name,
                    source_type=self.source_type,
                    source_url="https://gitlab.com/",
                    confidence=0.65,
                    note="Intentional diagnostic version conflict.",
                )
            )

        if MetadataField.PACKAGE_ID in requested:
            evidence.append(
                FieldEvidence(
                    field=MetadataField.PACKAGE_ID,
                    value="org.osguide.conflict",
                    provider_name=self.name,
                    source_type=self.source_type,
                    source_url="https://gitlab.com/",
                    confidence=0.55,
                    note="Intentional diagnostic identity conflict.",
                )
            )

        return evidence


class DiagnosticFailingResolverProvider(BaseResolverProvider):
    """
    Deliberately fails to verify provider failure isolation.
    """

    name = "diagnostic-resolver-failure"
    source_type = SourceType.CODEBERG

    def resolve(
        self,
        candidate: AppCandidate,
        *,
        fields: Sequence[MetadataField],
        timeout_seconds: float,
    ) -> list[FieldEvidence]:
        del candidate
        del fields
        del timeout_seconds

        raise RuntimeError(
            "Intentional Resolver provider failure for diagnostics."
        )


# ============================================================
# Diagnostic registry
# ============================================================

def build_default_resolver_registry() -> ResolverRegistry:
    registry = ResolverRegistry()

    registry.register(
        DiagnosticResolverProvider()
    )

    return registry


def build_live_resolver_registry() -> ResolverRegistry:
    """
    Build the normal read-only resolver registry used by the engine.

    Diagnostic providers are intentionally excluded.
    """
    registry = ResolverRegistry()

    registry.register(
        FutureFdroidResolverProvider()
    )

    return registry


def build_extended_resolver_registry() -> ResolverRegistry:
    registry = ResolverRegistry()

    registry.extend(
        (
            DiagnosticResolverProvider(),
            DiagnosticConflictProvider(),
            DiagnosticFailingResolverProvider(),
        )
    )

    return registry


# ============================================================
# Public diagnostics
# ============================================================

def run_live_resolver(
    candidate: AppCandidate,
) -> ResolvedApplication:
    """
    Resolve one real candidate using approved read-only providers.
    """
    registry = build_live_resolver_registry()

    policy = ResolverPolicy(
        max_attempts_per_field=4,
        provider_timeout_seconds=8.0,
        total_budget_seconds=20.0,
        minimum_accept_confidence=0.60,
        strong_accept_confidence=0.85,
        allow_partial=True,
        preserve_conflicts=True,
        stop_field_on_strong_evidence=True,
        skip_difficult_candidate_on_budget_exhaustion=True,
    )

    return resolve_candidate(
        candidate,
        registry.providers,
        policy=policy,
    )


def run_resolver_diagnostic(
    candidate: AppCandidate,
) -> ResolvedApplication:
    registry = build_default_resolver_registry()

    policy = ResolverPolicy(
        max_attempts_per_field=4,
        provider_timeout_seconds=5.0,
        total_budget_seconds=15.0,
        minimum_accept_confidence=0.60,
        strong_accept_confidence=0.85,
        allow_partial=True,
        preserve_conflicts=True,
        stop_field_on_strong_evidence=True,
        skip_difficult_candidate_on_budget_exhaustion=True,
    )

    return resolve_candidate(
        candidate,
        registry.providers,
        policy=policy,
    )


def run_extended_resolver_diagnostic(
    candidate: AppCandidate,
) -> ResolvedApplication:
    registry = build_extended_resolver_registry()

    policy = ResolverPolicy(
        max_attempts_per_field=5,
        provider_timeout_seconds=5.0,
        total_budget_seconds=15.0,
        minimum_accept_confidence=0.50,
        strong_accept_confidence=0.85,
        allow_partial=True,
        preserve_conflicts=True,
        stop_field_on_strong_evidence=False,
        skip_difficult_candidate_on_budget_exhaustion=True,
    )

    return resolve_candidate(
        candidate,
        registry.providers,
        policy=policy,
    )


# ============================================================
# Output helpers
# ============================================================

def resolved_values(
    result: ResolvedApplication,
) -> dict[str, str | None]:
    return {
        metadata_field.value: field_result.value
        for metadata_field, field_result in result.fields.items()
    }


def resolution_summary(
    result: ResolvedApplication,
) -> dict[str, object]:
    return {
        "candidate_identity": result.candidate_identity,
        "candidate_name": result.candidate_name,
        "status": result.status.value,
        "duration_seconds": round(
            result.duration_seconds,
            3,
        ),
        "providers_attempted": result.providers_attempted,
        "providers_succeeded": result.providers_succeeded,
        "providers_failed": result.providers_failed,
        "field_attempts": result.field_attempts,
        "resolved_field_count": result.resolved_field_count,
        "conflict_count": result.conflict_count,
        "timed_out": result.timed_out,
        "values": resolved_values(result),
        "provider_errors": list(result.provider_errors),
        "warnings": list(result.warnings),
    }


# ============================================================
# Future live provider contracts
# ============================================================

class FutureFdroidResolverProvider(BaseResolverProvider):
    """
    Read-only resolver backed by the official F-Droid repository index.

    The provider never publishes, deletes, or mutates external data.  It
    only turns metadata that F-Droid already exposes into FieldEvidence.

    The JSON index is cached inside the provider instance so a batch of
    candidates does not download the same repository index repeatedly.
    """

    name = "fdroid-resolver"
    source_type = SourceType.FDROID

    INDEX_URL: Final[str] = "https://f-droid.org/repo/index-v1.json"
    REPO_BASE_URL: Final[str] = "https://f-droid.org/repo/"
    USER_AGENT: Final[str] = "OSGuide-Resolver/0.3 (+https://github.com/)"

    MAX_INDEX_BYTES: Final[int] = 64 * 1024 * 1024

    def __init__(self) -> None:
        self._index_cache: Mapping[str, object] | None = None
        self._apps_by_package: dict[str, Mapping[str, object]] | None = None
        self._packages_by_package: dict[str, list[Mapping[str, object]]] | None = None

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object] | None:
        if isinstance(value, Mapping):
            return value
        return None

    @staticmethod
    def _localized_text(
        app: Mapping[str, object],
        field_name: str,
    ) -> str | None:
        direct = app.get(field_name)

        if isinstance(direct, str):
            cleaned = sanitize_text(
                direct,
                max_length=MAX_FIELD_VALUE_LENGTH,
            )
            return cleaned or None

        localized = app.get("localized")

        if isinstance(localized, Mapping):
            preferred_locales = (
                "en-US",
                "en",
                "en-GB",
            )

            for locale in preferred_locales:
                locale_data = localized.get(locale)

                if isinstance(locale_data, Mapping):
                    value = locale_data.get(field_name)

                    if isinstance(value, str):
                        cleaned = sanitize_text(
                            value,
                            max_length=MAX_FIELD_VALUE_LENGTH,
                        )

                        if cleaned:
                            return cleaned

            for locale_data in localized.values():
                if not isinstance(locale_data, Mapping):
                    continue

                value = locale_data.get(field_name)

                if isinstance(value, str):
                    cleaned = sanitize_text(
                        value,
                        max_length=MAX_FIELD_VALUE_LENGTH,
                    )

                    if cleaned:
                        return cleaned

        return None

    @staticmethod
    def _safe_repo_asset_name(value: object) -> str | None:
        """Return a safe repository asset filename from F-Droid metadata."""
        if not isinstance(value, str):
            return None

        value = value.strip()

        if not value or len(value) > 255:
            return None

        if "/" in value or "\\" in value or ".." in value:
            return None

        return value

    @classmethod
    def _icon_name(
        cls,
        app: Mapping[str, object],
    ) -> str | None:
        """
        Resolve an icon filename from official F-Droid index metadata.

        Prefer the top-level icon field, then localized icon metadata.
        """
        direct = cls._safe_repo_asset_name(app.get("icon"))
        if direct:
            return direct

        localized = app.get("localized")
        if not isinstance(localized, Mapping):
            return None

        for locale in ("en-US", "en", "en-GB"):
            locale_data = localized.get(locale)
            if isinstance(locale_data, Mapping):
                icon = cls._safe_repo_asset_name(locale_data.get("icon"))
                if icon:
                    return icon

        for locale_data in localized.values():
            if not isinstance(locale_data, Mapping):
                continue

            icon = cls._safe_repo_asset_name(locale_data.get("icon"))
            if icon:
                return icon

        return None

    @staticmethod
    def _safe_apk_name(value: object) -> str | None:
        if not isinstance(value, str):
            return None

        value = value.strip()

        if not value or len(value) > 255:
            return None

        if "/" in value or "\\" in value or ".." in value:
            return None

        if not value.lower().endswith(".apk"):
            return None

        return value

    @staticmethod
    def _version_code(value: object) -> int | None:
        if isinstance(value, bool):
            return None

        if isinstance(value, int):
            return value

        if isinstance(value, str):
            stripped = value.strip()

            if stripped.isdigit():
                try:
                    return int(stripped)
                except ValueError:
                    return None

        return None

    def _load_index(
        self,
        *,
        timeout_seconds: float,
    ) -> Mapping[str, object]:
        if self._index_cache is not None:
            return self._index_cache

        request = Request(
            self.INDEX_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": self.USER_AGENT,
            },
            method="GET",
        )

        try:
            with urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                status = getattr(response, "status", 200)

                if status != 200:
                    raise RuntimeError(
                        f"F-Droid index returned HTTP {status}."
                    )

                raw = response.read(
                    self.MAX_INDEX_BYTES + 1
                )

        except HTTPError as exc:
            raise RuntimeError(
                f"F-Droid index returned HTTP {exc.code}."
            ) from exc
        except URLError as exc:
            reason = sanitize_text(
                str(getattr(exc, "reason", "network error")),
                max_length=300,
            )
            raise RuntimeError(
                f"F-Droid index network error: {reason}"
            ) from exc

        if len(raw) > self.MAX_INDEX_BYTES:
            raise RuntimeError(
                "F-Droid index exceeded the resolver size limit."
            )

        try:
            decoded = raw.decode("utf-8")
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "F-Droid index returned invalid JSON."
            ) from exc

        if not isinstance(payload, Mapping):
            raise RuntimeError(
                "F-Droid index root must be an object."
            )

        self._index_cache = payload
        self._build_lookup_tables(payload)

        return payload

    def _build_lookup_tables(
        self,
        payload: Mapping[str, object],
    ) -> None:
        apps_by_package: dict[str, Mapping[str, object]] = {}
        packages_by_package: dict[str, list[Mapping[str, object]]] = {}

        raw_apps = payload.get("apps")

        if isinstance(raw_apps, list):
            for raw_app in raw_apps:
                if not isinstance(raw_app, Mapping):
                    continue

                package_name = raw_app.get("packageName")

                if (
                    isinstance(package_name, str)
                    and is_valid_package_id(package_name)
                ):
                    apps_by_package[package_name] = raw_app

        raw_packages = payload.get("packages")

        if isinstance(raw_packages, Mapping):
            for package_name, raw_items in raw_packages.items():
                if (
                    not isinstance(package_name, str)
                    or not is_valid_package_id(package_name)
                    or not isinstance(raw_items, list)
                ):
                    continue

                items: list[Mapping[str, object]] = []

                for raw_item in raw_items:
                    if isinstance(raw_item, Mapping):
                        items.append(raw_item)

                if items:
                    packages_by_package[package_name] = items

        self._apps_by_package = apps_by_package
        self._packages_by_package = packages_by_package

    def _select_package(
        self,
        *,
        app: Mapping[str, object] | None,
        packages: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object] | None:
        if not packages:
            return None

        suggested_code = None

        if app is not None:
            suggested_code = self._version_code(
                app.get("suggestedVersionCode")
            )

        if suggested_code is not None:
            for package in packages:
                if (
                    self._version_code(
                        package.get("versionCode")
                    )
                    == suggested_code
                ):
                    return package

        def sort_key(
            package: Mapping[str, object],
        ) -> int:
            return self._version_code(
                package.get("versionCode")
            ) or -1

        return max(
            packages,
            key=sort_key,
        )

    def resolve(
        self,
        candidate: AppCandidate,
        *,
        fields: Sequence[MetadataField],
        timeout_seconds: float,
    ) -> list[FieldEvidence]:
        if candidate.source_enum != SourceType.FDROID:
            return []

        if not candidate.package_id:
            return []

        if not is_valid_package_id(candidate.package_id):
            return []

        requested = set(fields)

        if not requested:
            return []

        self._load_index(
            timeout_seconds=timeout_seconds
        )

        apps_by_package = self._apps_by_package or {}
        packages_by_package = self._packages_by_package or {}

        package_id = candidate.package_id
        app = apps_by_package.get(package_id)
        packages = packages_by_package.get(
            package_id,
            [],
        )

        selected_package = self._select_package(
            app=app,
            packages=packages,
        )

        evidence: list[FieldEvidence] = []

        def add(
            metadata_field: MetadataField,
            value: str | None,
            *,
            confidence: float,
            note: str,
        ) -> None:
            if metadata_field not in requested:
                return

            if not value:
                return

            cleaned = sanitize_text(
                value,
                max_length=MAX_FIELD_VALUE_LENGTH,
            )

            if not cleaned:
                return

            evidence.append(
                FieldEvidence(
                    field=metadata_field,
                    value=cleaned,
                    provider_name=self.name,
                    source_type=self.source_type,
                    source_url=self.INDEX_URL,
                    confidence=confidence,
                    note=note,
                )
            )

        if app is not None:
            add(
                MetadataField.NAME,
                self._localized_text(
                    app,
                    "name",
                ),
                confidence=0.98,
                note="Name read from the official F-Droid repository index.",
            )

            add(
                MetadataField.SHORT_DESCRIPTION,
                self._localized_text(
                    app,
                    "summary",
                ),
                confidence=0.97,
                note="Summary read from the official F-Droid repository index.",
            )

            add(
                MetadataField.FULL_DESCRIPTION,
                self._localized_text(
                    app,
                    "description",
                ),
                confidence=0.97,
                note="Description read from the official F-Droid repository index.",
            )

            icon_name = self._icon_name(app)

            if icon_name:
                icon_url = (
                    self.REPO_BASE_URL
                    + "icons-640/"
                    + quote(
                        icon_name,
                        safe="._+-=@",
                    )
                )

                if is_valid_http_url(
                    icon_url,
                    require_https=True,
                ):
                    add(
                        MetadataField.ICON_URL,
                        icon_url,
                        confidence=0.98,
                        note=(
                            "Icon URL derived from official F-Droid "
                            "repository index metadata."
                        ),
                    )

            license_value = app.get("license")

            if isinstance(license_value, str):
                add(
                    MetadataField.LICENSE,
                    license_value,
                    confidence=0.98,
                    note="License read from the official F-Droid repository index.",
                )

            categories = app.get("categories")

            if isinstance(categories, list):
                for category in categories:
                    if isinstance(category, str) and category.strip():
                        add(
                            MetadataField.CATEGORY,
                            category,
                            confidence=0.95,
                            note="Category read from the official F-Droid repository index.",
                        )
                        break

            source_code = app.get("sourceCode")

            if (
                isinstance(source_code, str)
                and is_valid_http_url(
                    source_code,
                    require_https=True,
                )
            ):
                add(
                    MetadataField.REPOSITORY_URL,
                    source_code,
                    confidence=0.98,
                    note="Source-code URL read from the official F-Droid repository index.",
                )

        if selected_package is not None:
            version_name = selected_package.get(
                "versionName"
            )

            if isinstance(version_name, str):
                add(
                    MetadataField.VERSION,
                    version_name,
                    confidence=0.99,
                    note="Version read from the selected F-Droid package record.",
                )

            apk_name = self._safe_apk_name(
                selected_package.get("apkName")
            )

            if apk_name:
                apk_url = (
                    self.REPO_BASE_URL
                    + quote(
                        apk_name,
                        safe="._+-",
                    )
                )

                if is_valid_http_url(
                    apk_url,
                    require_https=True,
                ):
                    add(
                        MetadataField.APK_URL,
                        apk_url,
                        confidence=0.99,
                        note="APK URL derived from the exact apkName in the official F-Droid index.",
                    )

        return evidence


class FutureGithubResolverProvider(BaseResolverProvider):
    name = "github-resolver"
    source_type = SourceType.GITHUB

    def resolve(
        self,
        candidate: AppCandidate,
        *,
        fields: Sequence[MetadataField],
        timeout_seconds: float,
    ) -> list[FieldEvidence]:
        del candidate
        del fields
        del timeout_seconds

        raise NotImplementedError(
            "Live GitHub Resolver provider is not connected yet."
        )


class FutureOfficialResolverProvider(BaseResolverProvider):
    name = "official-resolver"
    source_type = SourceType.OFFICIAL

    def resolve(
        self,
        candidate: AppCandidate,
        *,
        fields: Sequence[MetadataField],
        timeout_seconds: float,
    ) -> list[FieldEvidence]:
        del candidate
        del fields
        del timeout_seconds

        raise NotImplementedError(
            "Live official-site Resolver provider is not connected yet."
        )


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "BaseResolverProvider",
    "BatchResolutionReport",
    "ConflictSeverity",
    "DiagnosticConflictProvider",
    "DiagnosticFailingResolverProvider",
    "DiagnosticResolverProvider",
    "FieldConflict",
    "FieldEvidence",
    "FieldState",
    "FutureFdroidResolverProvider",
    "FutureGithubResolverProvider",
    "FutureOfficialResolverProvider",
    "IMPORTANT_FIELDS",
    "MetadataField",
    "NON_FATAL_CONTENT_FIELDS",
    "ProviderStatus",
    "RESOLVER_COMPONENT",
    "RESOLVER_SCHEMA_VERSION",
    "ResolvedApplication",
    "ResolvedField",
    "ResolutionBudget",
    "ResolutionStatus",
    "ResolverPolicy",
    "ResolverProvider",
    "ResolverProviderResult",
    "ResolverRegistry",
    "apply_field_evidence",
    "build_default_resolver_registry",
    "build_extended_resolver_registry",
    "build_live_resolver_registry",
    "candidate_bootstrap_evidence",
    "enabled_fields",
    "evaluate_resolution_status",
    "field_evidence_fingerprint",
    "normalize_field_value",
    "resolve_candidate",
    "resolve_candidates",
    "resolved_values",
    "resolution_summary",
    "run_extended_resolver_diagnostic",
    "run_live_resolver",
    "run_provider",
    "run_resolver_diagnostic",
    "should_replace_field",
    "validate_provider",
    "values_equivalent",
)
