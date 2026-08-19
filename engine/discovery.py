"""
OSGuide Engine
Discovery Layer

This module is responsible for discovering Android application
candidates from approved open-source sources.

Architecture goals
------------------
1. Discovery only discovers candidates.
2. Discovery never publishes to Supabase.
3. Discovery never deletes applications.
4. Discovery never decides the final OSGuide action.
5. Discovery never fabricates APK URLs, package IDs, versions,
   repositories, licenses, or application metadata.
6. Failure of one source must not terminate the whole run.
7. Candidate discovery must remain bounded by explicit limits.
8. Candidate data must carry source evidence for later verification.
9. Admin decisions remain authoritative in later engine stages.
10. The Discovery layer must be replaceable and extensible without
    rewriting the main controller.

This file intentionally contains infrastructure for:
- candidate models
- source evidence
- source policies
- source ranking
- URL normalization
- candidate validation
- package-id validation
- deduplication
- source isolation
- source registry
- source execution reports
- discovery orchestration
- local diagnostics
- future real provider integration

It does not contain:
- Super Resolver
- APK Intelligence
- Supabase Publisher
- AI content generation
- Memory
- Audit / Rollback
- Admin override enforcement
- Review / Update logic

Those remain separate modules by design.
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
from urllib.request import Request, urlopen
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlparse,
    urlunparse,
)


# ============================================================
# Component identity
# ============================================================

DISCOVERY_COMPONENT: Final[str] = "Discovery"
DISCOVERY_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Safety limits
# ============================================================

DEFAULT_SOURCE_CONFIDENCE: Final[float] = 0.50
MIN_SOURCE_CONFIDENCE: Final[float] = 0.0
MAX_SOURCE_CONFIDENCE: Final[float] = 1.0

DEFAULT_SOURCE_LIMIT: Final[int] = 20
MIN_SOURCE_LIMIT: Final[int] = 1
MAX_SOURCE_LIMIT: Final[int] = 100

DEFAULT_GLOBAL_CANDIDATE_LIMIT: Final[int] = 20
MAX_GLOBAL_CANDIDATE_LIMIT: Final[int] = 100

DEFAULT_SOURCE_TIMEOUT_SECONDS: Final[float] = 8.0
MIN_SOURCE_TIMEOUT_SECONDS: Final[float] = 1.0
MAX_SOURCE_TIMEOUT_SECONDS: Final[float] = 30.0

MAX_CANDIDATE_NAME_LENGTH: Final[int] = 200
MAX_PACKAGE_ID_LENGTH: Final[int] = 255
MAX_DESCRIPTION_LENGTH: Final[int] = 5000
MAX_URL_LENGTH: Final[int] = 2048
MAX_METADATA_ITEMS: Final[int] = 100
MAX_EVIDENCE_ITEMS: Final[int] = 50

MAX_SOURCE_ERROR_LENGTH: Final[int] = 500


# ============================================================
# Validation patterns
# ============================================================

PACKAGE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$"
)

SAFE_SOURCE_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_.:-]{1,80}$"
)


# ============================================================
# Enumerations
# ============================================================

class SourceType(str, Enum):
    """
    Supported source families.

    A source type describes where the candidate was discovered,
    not whether the candidate has already been fully verified.
    """

    FDROID = "fdroid"
    GITHUB = "github"
    GITLAB = "gitlab"
    CODEBERG = "codeberg"
    OFFICIAL = "official"


class EvidenceKind(str, Enum):
    """
    Types of evidence attached to a candidate.
    """

    LISTING = "listing"
    REPOSITORY = "repository"
    PACKAGE_ID = "package-id"
    RELEASE = "release"
    WEBSITE = "website"
    LICENSE = "license"
    DESCRIPTION = "description"
    OTHER = "other"


class DiscoveryStatus(str, Enum):
    """
    Source execution status.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


class CandidateDisposition(str, Enum):
    """
    Discovery-stage disposition only.

    This is not the final Decision Engine result.
    """

    ACCEPTED = "accepted"
    INVALID = "invalid"
    DUPLICATE = "duplicate"


# ============================================================
# Trusted source policy
# ============================================================

@dataclass(frozen=True, slots=True)
class SourcePolicy:
    """
    Static policy associated with a source type.

    `base_confidence` is only a discovery confidence hint.
    Later verification stages must independently verify facts.
    """

    source_type: SourceType
    base_confidence: float
    preferred_rank: int
    requires_https: bool = True
    allow_query_parameters: bool = True
    notes: str = ""

    def validate(self) -> None:
        if not (
            MIN_SOURCE_CONFIDENCE
            <= self.base_confidence
            <= MAX_SOURCE_CONFIDENCE
        ):
            raise ValueError(
                "SourcePolicy.base_confidence must be between "
                f"{MIN_SOURCE_CONFIDENCE} and "
                f"{MAX_SOURCE_CONFIDENCE}."
            )

        if self.preferred_rank < 0:
            raise ValueError(
                "SourcePolicy.preferred_rank cannot be negative."
            )


SOURCE_POLICIES: Final[Mapping[SourceType, SourcePolicy]] = {
    SourceType.FDROID: SourcePolicy(
        source_type=SourceType.FDROID,
        base_confidence=0.95,
        preferred_rank=10,
        requires_https=True,
        notes=(
            "Trusted open-source Android catalog. "
            "Candidate metadata still requires verification."
        ),
    ),
    SourceType.GITHUB: SourcePolicy(
        source_type=SourceType.GITHUB,
        base_confidence=0.90,
        preferred_rank=20,
        requires_https=True,
        notes=(
            "Official or upstream repositories may be hosted here. "
            "Repository ownership must be verified later."
        ),
    ),
    SourceType.GITLAB: SourcePolicy(
        source_type=SourceType.GITLAB,
        base_confidence=0.85,
        preferred_rank=30,
        requires_https=True,
    ),
    SourceType.CODEBERG: SourcePolicy(
        source_type=SourceType.CODEBERG,
        base_confidence=0.85,
        preferred_rank=40,
        requires_https=True,
    ),
    SourceType.OFFICIAL: SourcePolicy(
        source_type=SourceType.OFFICIAL,
        base_confidence=0.80,
        preferred_rank=50,
        requires_https=True,
        notes=(
            "Official project websites are useful evidence, "
            "but ownership must be resolved by later stages."
        ),
    ),
}


def validate_source_policies() -> None:
    """
    Validate built-in source policies at import/runtime boundaries.
    """

    for policy in SOURCE_POLICIES.values():
        policy.validate()


# ============================================================
# Evidence model
# ============================================================

@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    """
    One piece of source evidence associated with a candidate.
    """

    kind: EvidenceKind
    source_type: SourceType
    source_name: str
    url: str
    confidence: float
    note: str | None = None
    captured_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def validate(self) -> None:
        if not SAFE_SOURCE_NAME_PATTERN.fullmatch(
            self.source_name.strip()
        ):
            raise ValueError(
                f"Invalid evidence source name: {self.source_name!r}"
            )

        validate_url(
            self.url,
            require_https=True,
        )

        if not (
            MIN_SOURCE_CONFIDENCE
            <= self.confidence
            <= MAX_SOURCE_CONFIDENCE
        ):
            raise ValueError(
                "Evidence confidence must be between 0 and 1."
            )

        if self.note is not None and len(self.note) > 1000:
            raise ValueError(
                "Evidence note is too long."
            )


# ============================================================
# Candidate model
# ============================================================

@dataclass(slots=True)
class AppCandidate:
    """
    Raw candidate discovered by the engine.

    A candidate is not approved for publication merely because
    Discovery found it. Resolver + Verification + Decision stages
    must process it later.
    """

    name: str
    source_type: str
    source_url: str

    package_id: str | None = None
    repository_url: str | None = None
    description: str | None = None

    source_confidence: float = DEFAULT_SOURCE_CONFIDENCE

    discovered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    evidence: list[CandidateEvidence] = field(
        default_factory=list
    )

    source_names: list[str] = field(
        default_factory=list
    )

    warnings: list[str] = field(
        default_factory=list
    )

    @property
    def source_enum(self) -> SourceType:
        try:
            return SourceType(
                self.source_type.strip().lower()
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported source type: {self.source_type!r}"
            ) from exc

    @property
    def normalized_package_id(self) -> str | None:
        if self.package_id is None:
            return None

        normalized = self.package_id.strip()

        return normalized or None

    @property
    def normalized_source_url(self) -> str:
        return normalize_url(
            self.source_url
        )

    @property
    def normalized_repository_url(self) -> str | None:
        if not self.repository_url:
            return None

        return normalize_url(
            self.repository_url
        )

    @property
    def identity(self) -> str:
        """
        Stable candidate identity.

        Package ID is preferred because it maps to Android app
        identity. When unavailable, use normalized repository URL,
        then normalized source URL.
        """

        if self.normalized_package_id:
            return (
                "package:"
                + self.normalized_package_id.lower()
            )

        if self.normalized_repository_url:
            digest = hashlib.sha256(
                self.normalized_repository_url.encode(
                    "utf-8"
                )
            ).hexdigest()

            return f"repo:{digest}"

        digest = hashlib.sha256(
            self.normalized_source_url.encode(
                "utf-8"
            )
        ).hexdigest()

        return f"url:{digest}"

    @property
    def evidence_count(self) -> int:
        return len(self.evidence)

    def add_warning(
        self,
        message: str,
    ) -> None:
        message = sanitize_text(
            message,
            max_length=300,
        )

        if message and message not in self.warnings:
            self.warnings.append(
                message
            )

    def add_source_name(
        self,
        source_name: str,
    ) -> None:
        source_name = sanitize_text(
            source_name,
            max_length=80,
        )

        if not source_name:
            return

        if source_name not in self.source_names:
            self.source_names.append(
                source_name
            )

    def add_evidence(
        self,
        evidence: CandidateEvidence,
    ) -> None:
        evidence.validate()

        if len(self.evidence) >= MAX_EVIDENCE_ITEMS:
            self.add_warning(
                "Evidence limit reached; additional evidence ignored."
            )

            return

        fingerprint = evidence_fingerprint(
            evidence
        )

        existing_fingerprints = {
            evidence_fingerprint(item)
            for item in self.evidence
        }

        if fingerprint in existing_fingerprints:
            return

        self.evidence.append(
            evidence
        )

    def validate(self) -> None:
        """
        Validate only the discovery-stage structure.

        Missing version, APK, license, or icon are NOT errors here.
        Those belong to later resolver stages.
        """

        self.name = sanitize_text(
            self.name,
            max_length=MAX_CANDIDATE_NAME_LENGTH,
        )

        if not self.name:
            raise ValueError(
                "Candidate name cannot be empty."
            )

        source_enum = self.source_enum

        validate_url(
            self.source_url,
            require_https=SOURCE_POLICIES[
                source_enum
            ].requires_https,
        )

        if self.repository_url:
            validate_url(
                self.repository_url,
                require_https=True,
            )

        if self.package_id is not None:
            normalized_package = self.package_id.strip()

            if normalized_package:
                validate_package_id(
                    normalized_package
                )

                self.package_id = normalized_package
            else:
                self.package_id = None

        if self.description is not None:
            self.description = sanitize_text(
                self.description,
                max_length=MAX_DESCRIPTION_LENGTH,
            )

            if not self.description:
                self.description = None

        if not (
            MIN_SOURCE_CONFIDENCE
            <= self.source_confidence
            <= MAX_SOURCE_CONFIDENCE
        ):
            raise ValueError(
                "source_confidence must be between "
                f"{MIN_SOURCE_CONFIDENCE} and "
                f"{MAX_SOURCE_CONFIDENCE}."
            )

        if len(self.metadata) > MAX_METADATA_ITEMS:
            raise ValueError(
                "Candidate metadata contains too many items."
            )

        if len(self.evidence) > MAX_EVIDENCE_ITEMS:
            raise ValueError(
                "Candidate contains too many evidence items."
            )

        for evidence in self.evidence:
            evidence.validate()


# ============================================================
# Discovery source result model
# ============================================================

@dataclass(slots=True)
class DiscoverySourceResult:
    """
    Result produced by exactly one source execution.
    """

    source_name: str
    source_type: SourceType | None = None

    status: DiscoveryStatus = (
        DiscoveryStatus.SUCCESS
    )

    candidates: list[AppCandidate] = field(
        default_factory=list
    )

    error: str | None = None

    duration_seconds: float = 0.0

    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    finished_at: datetime | None = None

    raw_candidates_count: int = 0

    invalid_candidates_count: int = 0

    @property
    def succeeded(self) -> bool:
        return (
            self.status
            == DiscoveryStatus.SUCCESS
            and self.error is None
        )

    @property
    def failed(self) -> bool:
        return (
            self.status
            == DiscoveryStatus.FAILURE
        )

    @property
    def skipped(self) -> bool:
        return (
            self.status
            == DiscoveryStatus.SKIPPED
        )


# ============================================================
# Discovery report
# ============================================================

@dataclass(slots=True)
class DiscoveryReport:
    """
    Aggregated output from all configured discovery sources.
    """

    started_at: datetime

    finished_at: datetime | None = None

    source_results: list[
        DiscoverySourceResult
    ] = field(
        default_factory=list
    )

    candidates: list[
        AppCandidate
    ] = field(
        default_factory=list
    )

    duplicates_removed: int = 0

    invalid_candidates_removed: int = 0

    raw_candidates_seen: int = 0

    accepted_candidates: int = 0

    warnings: list[str] = field(
        default_factory=list
    )

    @property
    def duration_seconds(self) -> float:
        end_time = (
            self.finished_at
            or datetime.now(timezone.utc)
        )

        return max(
            0.0,
            (
                end_time
                - self.started_at
            ).total_seconds(),
        )

    @property
    def sources_succeeded(self) -> int:
        return sum(
            1
            for result in self.source_results
            if result.succeeded
        )

    @property
    def sources_failed(self) -> int:
        return sum(
            1
            for result in self.source_results
            if result.failed
        )

    @property
    def sources_skipped(self) -> int:
        return sum(
            1
            for result in self.source_results
            if result.skipped
        )


# ============================================================
# Discovery configuration model
# ============================================================

@dataclass(frozen=True, slots=True)
class DiscoverySettings:
    """
    Runtime configuration dedicated to Discovery.
    """

    max_apps: int = DEFAULT_GLOBAL_CANDIDATE_LIMIT

    per_source_limit: int = DEFAULT_SOURCE_LIMIT

    per_source_timeout_seconds: float = (
        DEFAULT_SOURCE_TIMEOUT_SECONDS
    )

    min_candidate_confidence: float = 0.0

    deduplicate: bool = True

    validate_candidates: bool = True

    prefer_package_identity: bool = True

    def validate(self) -> None:
        if not (
            1
            <= self.max_apps
            <= MAX_GLOBAL_CANDIDATE_LIMIT
        ):
            raise ValueError(
                "DiscoverySettings.max_apps is out of range."
            )

        if not (
            MIN_SOURCE_LIMIT
            <= self.per_source_limit
            <= MAX_SOURCE_LIMIT
        ):
            raise ValueError(
                "DiscoverySettings.per_source_limit is out of range."
            )

        if not (
            MIN_SOURCE_TIMEOUT_SECONDS
            <= self.per_source_timeout_seconds
            <= MAX_SOURCE_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "DiscoverySettings.per_source_timeout_seconds "
                "is out of range."
            )

        if not (
            MIN_SOURCE_CONFIDENCE
            <= self.min_candidate_confidence
            <= MAX_SOURCE_CONFIDENCE
        ):
            raise ValueError(
                "DiscoverySettings.min_candidate_confidence "
                "must be between 0 and 1."
            )


# ============================================================
# Source protocol
# ============================================================

class DiscoverySource(Protocol):
    """
    Interface implemented by discovery providers.
    """

    name: str
    source_type: SourceType

    def discover(
        self,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> list[AppCandidate]:
        ...


# ============================================================
# Base source helper
# ============================================================

class BaseDiscoverySource:
    """
    Optional convenience base class for future providers.
    """

    name: str = "unknown"
    source_type: SourceType = SourceType.OFFICIAL

    def validate_identity(self) -> None:
        if not SAFE_SOURCE_NAME_PATTERN.fullmatch(
            self.name.strip()
        ):
            raise ValueError(
                f"Invalid discovery source name: {self.name!r}"
            )

        if not isinstance(
            self.source_type,
            SourceType,
        ):
            raise ValueError(
                "source_type must be a SourceType."
            )

    def discover(
        self,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> list[AppCandidate]:
        raise NotImplementedError


# ============================================================
# Text safety helpers
# ============================================================

def sanitize_text(
    value: object,
    *,
    max_length: int,
) -> str:
    """
    Produce bounded single-line text.

    Discovery providers may return external data. This helper keeps
    later logging and metadata handling predictable.
    """

    text = str(
        value
    ).replace(
        "\x00",
        ""
    )

    text = (
        text.replace(
            "\r",
            " ",
        )
        .replace(
            "\n",
            " ",
        )
        .strip()
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    if len(text) > max_length:
        text = (
            text[:max_length]
            + "…"
        )

    return text


def sanitize_error(
    exc: BaseException,
) -> str:
    """
    Create a bounded error string without stack traces or secrets.
    """

    message = sanitize_text(
        exc,
        max_length=MAX_SOURCE_ERROR_LENGTH,
    )

    return (
        f"{type(exc).__name__}: "
        f"{message}"
    )


# ============================================================
# URL validation
# ============================================================

def validate_url(
    value: str,
    *,
    require_https: bool,
) -> None:
    if not isinstance(
        value,
        str,
    ):
        raise TypeError(
            "URL must be a string."
        )

    value = value.strip()

    if not value:
        raise ValueError(
            "URL cannot be empty."
        )

    if len(value) > MAX_URL_LENGTH:
        raise ValueError(
            "URL is too long."
        )

    try:
        parsed = urlparse(
            value
        )
    except ValueError as exc:
        raise ValueError(
            "Malformed URL."
        ) from exc

    if parsed.scheme not in {
        "http",
        "https",
    }:
        raise ValueError(
            "Only HTTP(S) URLs are allowed."
        )

    if require_https and parsed.scheme != "https":
        raise ValueError(
            "HTTPS is required for this source."
        )

    if not parsed.netloc:
        raise ValueError(
            "URL must contain a hostname."
        )

    if parsed.username or parsed.password:
        raise ValueError(
            "Credential-bearing URLs are not allowed."
        )


def is_valid_http_url(
    value: str,
    *,
    require_https: bool = False,
) -> bool:
    try:
        validate_url(
            value,
            require_https=require_https,
        )

    except (
        TypeError,
        ValueError,
    ):
        return False

    return True


# ============================================================
# URL normalization
# ============================================================

def normalize_url(
    value: str,
) -> str:
    """
    Normalize URL identity without following redirects.

    Query parameters are sorted to make duplicate detection stable.
    Fragments are dropped because they do not identify resources.
    """

    validate_url(
        value,
        require_https=False,
    )

    parsed = urlparse(
        value.strip()
    )

    scheme = parsed.scheme.lower()

    hostname = (
        parsed.hostname
        or ""
    ).lower()

    port = parsed.port

    if port is not None:
        default_http = (
            scheme == "http"
            and port == 80
        )

        default_https = (
            scheme == "https"
            and port == 443
        )

        if not (
            default_http
            or default_https
        ):
            hostname = (
                f"{hostname}:{port}"
            )

    path = (
        parsed.path
        or "/"
    )

    if path != "/":
        path = path.rstrip(
            "/"
        )

    query_pairs = parse_qsl(
        parsed.query,
        keep_blank_values=True,
    )

    query_pairs.sort()

    normalized_query = urlencode(
        query_pairs,
        doseq=True,
    )

    normalized = urlunparse(
        (
            scheme,
            hostname,
            path,
            "",
            normalized_query,
            "",
        )
    )

    return normalized


# ============================================================
# Android package ID validation
# ============================================================

def validate_package_id(
    package_id: str,
) -> None:
    if not isinstance(
        package_id,
        str,
    ):
        raise TypeError(
            "Package ID must be a string."
        )

    package_id = package_id.strip()

    if not package_id:
        raise ValueError(
            "Package ID cannot be empty."
        )

    if len(package_id) > MAX_PACKAGE_ID_LENGTH:
        raise ValueError(
            "Package ID is too long."
        )

    if not PACKAGE_ID_PATTERN.fullmatch(
        package_id
    ):
        raise ValueError(
            f"Invalid Android package ID: {package_id!r}"
        )


def is_valid_package_id(
    package_id: str | None,
) -> bool:
    if package_id is None:
        return False

    try:
        validate_package_id(
            package_id
        )

    except (
        TypeError,
        ValueError,
    ):
        return False

    return True


# ============================================================
# Evidence helpers
# ============================================================

def evidence_fingerprint(
    evidence: CandidateEvidence,
) -> str:
    raw = "|".join(
        (
            evidence.kind.value,
            evidence.source_type.value,
            evidence.source_name,
            normalize_url(
                evidence.url
            ),
        )
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()


def create_listing_evidence(
    *,
    source_type: SourceType,
    source_name: str,
    url: str,
    confidence: float,
    note: str | None = None,
) -> CandidateEvidence:
    evidence = CandidateEvidence(
        kind=EvidenceKind.LISTING,
        source_type=source_type,
        source_name=source_name,
        url=url,
        confidence=confidence,
        note=note,
    )

    evidence.validate()

    return evidence


# ============================================================
# Candidate confidence helpers
# ============================================================

def clamp_confidence(
    value: float,
) -> float:
    return max(
        MIN_SOURCE_CONFIDENCE,
        min(
            MAX_SOURCE_CONFIDENCE,
            float(value),
        ),
    )


def source_base_confidence(
    source_type: SourceType,
) -> float:
    return SOURCE_POLICIES[
        source_type
    ].base_confidence


def compute_candidate_confidence(
    candidate: AppCandidate,
) -> float:
    """
    Conservative discovery confidence.

    This score is only for prioritization. It is not enough to
    publish an application.
    """

    score = clamp_confidence(
        candidate.source_confidence
    )

    if candidate.package_id:
        score += 0.02

    if candidate.repository_url:
        score += 0.02

    if candidate.evidence_count >= 2:
        score += 0.02

    if candidate.evidence_count >= 3:
        score += 0.01

    return clamp_confidence(
        score
    )


# ============================================================
# Candidate validation pipeline
# ============================================================

@dataclass(slots=True)
class CandidateValidationResult:
    candidate: AppCandidate
    disposition: CandidateDisposition
    error: str | None = None


def validate_candidate(
    candidate: AppCandidate,
) -> CandidateValidationResult:
    try:
        candidate.validate()

    except (
        TypeError,
        ValueError,
    ) as exc:
        return CandidateValidationResult(
            candidate=candidate,
            disposition=CandidateDisposition.INVALID,
            error=sanitize_error(
                exc
            ),
        )

    return CandidateValidationResult(
        candidate=candidate,
        disposition=CandidateDisposition.ACCEPTED,
    )


def validate_candidates(
    candidates: Iterable[
        AppCandidate
    ],
) -> tuple[
    list[AppCandidate],
    int,
]:
    valid: list[
        AppCandidate
    ] = []

    invalid_count = 0

    for candidate in candidates:
        result = validate_candidate(
            candidate
        )

        if (
            result.disposition
            == CandidateDisposition.ACCEPTED
        ):
            valid.append(
                candidate
            )

            continue

        invalid_count += 1

    return (
        valid,
        invalid_count,
    )


# ============================================================
# Candidate merge helpers
# ============================================================

def _prefer_non_empty(
    first: str | None,
    second: str | None,
) -> str | None:
    if first and first.strip():
        return first

    if second and second.strip():
        return second

    return None


def _merge_metadata(
    target: dict[str, object],
    incoming: Mapping[str, object],
) -> None:
    """
    Conservative metadata merge.

    Existing values are not overwritten automatically. Later
    resolver stages will decide which source wins field-by-field.
    """

    for key, value in incoming.items():
        if len(target) >= MAX_METADATA_ITEMS:
            break

        if key not in target:
            target[key] = value


def merge_candidates(
    existing: AppCandidate,
    incoming: AppCandidate,
) -> AppCandidate:
    """
    Merge two candidates representing the same app.

    Discovery only enriches hints. It does not resolve conflicts
    authoritatively.
    """

    if (
        incoming.source_confidence
        > existing.source_confidence
    ):
        existing.name = _prefer_non_empty(
            incoming.name,
            existing.name,
        ) or existing.name

        existing.source_type = (
            incoming.source_type
        )

        existing.source_url = (
            incoming.source_url
        )

        existing.source_confidence = (
            incoming.source_confidence
        )

    existing.package_id = _prefer_non_empty(
        existing.package_id,
        incoming.package_id,
    )

    existing.repository_url = _prefer_non_empty(
        existing.repository_url,
        incoming.repository_url,
    )

    existing.description = _prefer_non_empty(
        existing.description,
        incoming.description,
    )

    for source_name in incoming.source_names:
        existing.add_source_name(
            source_name
        )

    for warning in incoming.warnings:
        existing.add_warning(
            warning
        )

    for evidence in incoming.evidence:
        try:
            existing.add_evidence(
                evidence
            )
        except ValueError:
            existing.add_warning(
                "Invalid duplicate evidence ignored."
            )

    _merge_metadata(
        existing.metadata,
        incoming.metadata,
    )

    existing.source_confidence = max(
        existing.source_confidence,
        incoming.source_confidence,
    )

    return existing


# ============================================================
# Deduplication
# ============================================================

def deduplicate_candidates(
    candidates: Iterable[
        AppCandidate
    ],
) -> tuple[
    list[AppCandidate],
    int,
]:
    selected: dict[
        str,
        AppCandidate,
    ] = {}

    duplicate_count = 0

    for candidate in candidates:
        identity = candidate.identity

        existing = selected.get(
            identity
        )

        if existing is None:
            selected[
                identity
            ] = candidate

            continue

        duplicate_count += 1

        selected[
            identity
        ] = merge_candidates(
            existing,
            candidate,
        )

    return (
        list(
            selected.values()
        ),
        duplicate_count,
    )


# ============================================================
# Source execution guards
# ============================================================

def validate_source_limit(
    limit: int,
) -> None:
    if not isinstance(
        limit,
        int,
    ):
        raise TypeError(
            "Source limit must be an integer."
        )

    if not (
        MIN_SOURCE_LIMIT
        <= limit
        <= MAX_SOURCE_LIMIT
    ):
        raise ValueError(
            "Source limit is outside the allowed range."
        )


def validate_source_timeout(
    timeout_seconds: float,
) -> None:
    timeout_seconds = float(
        timeout_seconds
    )

    if not (
        MIN_SOURCE_TIMEOUT_SECONDS
        <= timeout_seconds
        <= MAX_SOURCE_TIMEOUT_SECONDS
    ):
        raise ValueError(
            "Source timeout is outside the allowed range."
        )


def validate_source_object(
    source: DiscoverySource,
) -> None:
    source_name = getattr(
        source,
        "name",
        None,
    )

    source_type = getattr(
        source,
        "source_type",
        None,
    )

    if not isinstance(
        source_name,
        str,
    ):
        raise TypeError(
            "Discovery source requires a string name."
        )

    if not SAFE_SOURCE_NAME_PATTERN.fullmatch(
        source_name.strip()
    ):
        raise ValueError(
            f"Invalid source name: {source_name!r}"
        )

    if not isinstance(
        source_type,
        SourceType,
    ):
        raise TypeError(
            "Discovery source requires SourceType."
        )

    discover_method = getattr(
        source,
        "discover",
        None,
    )

    if not callable(
        discover_method
    ):
        raise TypeError(
            "Discovery source requires a discover() method."
        )


# ============================================================
# Safe source execution
# ============================================================

def run_source(
    source: DiscoverySource,
    *,
    limit: int,
    timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS,
) -> DiscoverySourceResult:
    """
    Execute one discovery source in an isolated failure boundary.

    NOTE:
    The provider receives the timeout value and is responsible for
    applying it to network operations. A process-level timeout will
    be added at the provider/network layer later.
    """

    started_monotonic = time.monotonic()

    started_at = datetime.now(
        timezone.utc
    )

    source_name = getattr(
        source,
        "name",
        "unknown",
    )

    source_type = getattr(
        source,
        "source_type",
        None,
    )

    try:
        validate_source_limit(
            limit
        )

        validate_source_timeout(
            timeout_seconds
        )

        validate_source_object(
            source
        )

        raw_candidates = source.discover(
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

        if not isinstance(
            raw_candidates,
            list,
        ):
            raise TypeError(
                "Discovery source must return a list."
            )

        if len(raw_candidates) > limit:
            raw_candidates = raw_candidates[
                :limit
            ]

        valid_candidates, invalid_count = (
            validate_candidates(
                raw_candidates
            )
        )

        finished_at = datetime.now(
            timezone.utc
        )

        return DiscoverySourceResult(
            source_name=source_name,
            source_type=source_type,
            status=DiscoveryStatus.SUCCESS,
            candidates=valid_candidates,
            duration_seconds=max(
                0.0,
                time.monotonic()
                - started_monotonic,
            ),
            started_at=started_at,
            finished_at=finished_at,
            raw_candidates_count=len(
                raw_candidates
            ),
            invalid_candidates_count=invalid_count,
        )

    except Exception as exc:
        finished_at = datetime.now(
            timezone.utc
        )

        return DiscoverySourceResult(
            source_name=sanitize_text(
                source_name,
                max_length=80,
            )
            or "unknown",
            source_type=(
                source_type
                if isinstance(
                    source_type,
                    SourceType,
                )
                else None
            ),
            status=DiscoveryStatus.FAILURE,
            error=sanitize_error(
                exc
            ),
            duration_seconds=max(
                0.0,
                time.monotonic()
                - started_monotonic,
            ),
            started_at=started_at,
            finished_at=finished_at,
        )


# ============================================================
# Source ranking
# ============================================================

def source_rank(
    source_type: SourceType,
) -> int:
    return SOURCE_POLICIES[
        source_type
    ].preferred_rank


def candidate_sort_key(
    candidate: AppCandidate,
) -> tuple[
    float,
    int,
    str,
]:
    """
    Sort by:
    1. higher discovery confidence
    2. preferred source family
    3. application name
    """

    confidence = (
        compute_candidate_confidence(
            candidate
        )
    )

    rank = source_rank(
        candidate.source_enum
    )

    return (
        -confidence,
        rank,
        candidate.name.lower(),
    )


# ============================================================
# Discovery registry
# ============================================================

class DiscoveryRegistry:
    """
    Ordered collection of discovery providers.

    Duplicate provider names are rejected to prevent ambiguous logs.
    """

    def __init__(
        self,
    ) -> None:
        self._sources: list[
            DiscoverySource
        ] = []

        self._source_names: set[
            str
        ] = set()

    @property
    def sources(
        self,
    ) -> tuple[
        DiscoverySource,
        ...,
    ]:
        return tuple(
            self._sources
        )

    def register(
        self,
        source: DiscoverySource,
    ) -> None:
        validate_source_object(
            source
        )

        normalized_name = source.name.strip()

        if normalized_name in self._source_names:
            raise ValueError(
                "Duplicate discovery source name: "
                f"{normalized_name}"
            )

        self._sources.append(
            source
        )

        self._source_names.add(
            normalized_name
        )

    def extend(
        self,
        sources: Iterable[
            DiscoverySource
        ],
    ) -> None:
        for source in sources:
            self.register(
                source
            )


# ============================================================
# Discovery orchestration
# ============================================================

def discover_candidates(
    sources: Iterable[
        DiscoverySource
    ],
    *,
    max_apps: int,
    settings: DiscoverySettings | None = None,
) -> DiscoveryReport:
    """
    Run configured sources and return a validated, deduplicated,
    prioritized candidate report.

    Source failures are recorded and ignored so other sources
    continue running.
    """

    if settings is None:
        settings = DiscoverySettings(
            max_apps=max_apps,
            per_source_limit=max_apps,
        )

    settings.validate()

    if max_apps != settings.max_apps:
        settings = DiscoverySettings(
            max_apps=max_apps,
            per_source_limit=settings.per_source_limit,
            per_source_timeout_seconds=(
                settings.per_source_timeout_seconds
            ),
            min_candidate_confidence=(
                settings.min_candidate_confidence
            ),
            deduplicate=settings.deduplicate,
            validate_candidates=(
                settings.validate_candidates
            ),
            prefer_package_identity=(
                settings.prefer_package_identity
            ),
        )

        settings.validate()

    report = DiscoveryReport(
        started_at=datetime.now(
            timezone.utc
        )
    )

    collected: list[
        AppCandidate
    ] = []

    source_list = list(
        sources
    )

    if not source_list:
        report.warnings.append(
            "No discovery sources were configured."
        )

    for source in source_list:
        result = run_source(
            source,
            limit=min(
                settings.per_source_limit,
                settings.max_apps,
            ),
            timeout_seconds=(
                settings.per_source_timeout_seconds
            ),
        )

        report.source_results.append(
            result
        )

        report.raw_candidates_seen += (
            result.raw_candidates_count
        )

        report.invalid_candidates_removed += (
            result.invalid_candidates_count
        )

        if result.succeeded:
            collected.extend(
                result.candidates
            )

    if settings.validate_candidates:
        validated, invalid_count = (
            validate_candidates(
                collected
            )
        )

        report.invalid_candidates_removed += (
            invalid_count
        )

    else:
        validated = list(
            collected
        )

    if settings.deduplicate:
        unique_candidates, duplicate_count = (
            deduplicate_candidates(
                validated
            )
        )

        report.duplicates_removed = (
            duplicate_count
        )

    else:
        unique_candidates = (
            validated
        )

    filtered_candidates: list[
        AppCandidate
    ] = []

    for candidate in unique_candidates:
        confidence = (
            compute_candidate_confidence(
                candidate
            )
        )

        if (
            confidence
            < settings.min_candidate_confidence
        ):
            candidate.add_warning(
                "Candidate confidence below discovery threshold."
            )

            continue

        candidate.source_confidence = (
            confidence
        )

        filtered_candidates.append(
            candidate
        )

    filtered_candidates.sort(
        key=candidate_sort_key
    )

    report.candidates = (
        filtered_candidates[
            :settings.max_apps
        ]
    )

    report.accepted_candidates = len(
        report.candidates
    )

    report.finished_at = datetime.now(
        timezone.utc
    )

    return report


# ============================================================
# Diagnostic provider
# ============================================================

class DiagnosticDiscoverySource(
    BaseDiscoverySource
):
    """
    Harmless local provider used to verify the Discovery pipeline.

    It performs zero network requests and never writes external data.
    """

    name = "diagnostic"

    source_type = (
        SourceType.GITHUB
    )

    def discover(
        self,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> list[
        AppCandidate
    ]:
        validate_source_limit(
            limit
        )

        validate_source_timeout(
            timeout_seconds
        )

        if limit < 1:
            return []

        confidence = source_base_confidence(
            self.source_type
        )

        candidate = AppCandidate(
            name="OSGuide Diagnostic Candidate",
            source_type=self.source_type.value,
            source_url="https://github.com/",
            repository_url="https://github.com/",
            description=(
                "Internal candidate used only to verify "
                "the OSGuide Discovery pipeline."
            ),
            source_confidence=confidence,
            metadata={
                "diagnostic": True,
                "network_request": False,
                "publish_allowed": False,
            },
        )

        candidate.add_source_name(
            self.name
        )

        candidate.add_evidence(
            create_listing_evidence(
                source_type=self.source_type,
                source_name=self.name,
                url="https://github.com/",
                confidence=confidence,
                note=(
                    "Synthetic evidence for internal diagnostic use."
                ),
            )
        )

        return [
            candidate
        ]


# ============================================================
# Failure-isolation diagnostic provider
# ============================================================

class DiagnosticFailingSource(
    BaseDiscoverySource
):
    """
    Optional internal provider used to test source failure isolation.

    It is not included in the default diagnostic run.
    """

    name = "diagnostic-failure"

    source_type = (
        SourceType.GITHUB
    )

    def discover(
        self,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> list[
        AppCandidate
    ]:
        del limit
        del timeout_seconds

        raise RuntimeError(
            "Intentional discovery failure for diagnostics."
        )


# ============================================================
# Duplicate diagnostic provider
# ============================================================

class DiagnosticDuplicateSource(
    BaseDiscoverySource
):
    """
    Optional provider for testing deduplication.
    """

    name = "diagnostic-duplicate"

    source_type = (
        SourceType.GITHUB
    )

    def discover(
        self,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> list[
        AppCandidate
    ]:
        validate_source_limit(
            limit
        )

        validate_source_timeout(
            timeout_seconds
        )

        if limit < 1:
            return []

        candidate = AppCandidate(
            name="OSGuide Diagnostic Candidate Duplicate",
            source_type=self.source_type.value,
            source_url="https://github.com/",
            repository_url="https://github.com/",
            source_confidence=0.70,
            metadata={
                "diagnostic": True,
                "duplicate_test": True,
            },
        )

        candidate.add_source_name(
            self.name
        )

        return [
            candidate
        ]


# ============================================================
# Invalid candidate diagnostic provider
# ============================================================

class DiagnosticInvalidSource(
    BaseDiscoverySource
):
    """
    Optional provider for validating malformed-candidate isolation.
    """

    name = "diagnostic-invalid"

    source_type = (
        SourceType.GITHUB
    )

    def discover(
        self,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> list[
        AppCandidate
    ]:
        validate_source_limit(
            limit
        )

        validate_source_timeout(
            timeout_seconds
        )

        if limit < 1:
            return []

        return [
            AppCandidate(
                name="",
                source_type=self.source_type.value,
                source_url="javascript:alert(1)",
                source_confidence=1.0,
            )
        ]


# ============================================================
# Public diagnostic entry points
# ============================================================

def build_default_diagnostic_registry(
) -> DiscoveryRegistry:
    registry = DiscoveryRegistry()

    registry.register(
        DiagnosticDiscoverySource()
    )

    return registry


def build_default_discovery_registry(
) -> DiscoveryRegistry:
    """
    Build the normal read-only discovery registry.

    Diagnostic providers are deliberately excluded from this registry.
    """
    registry = DiscoveryRegistry()

    registry.register(
        FutureFdroidSource()
    )

    return registry


def run_default_discovery(
    *,
    max_apps: int = 5,
) -> DiscoveryReport:
    """
    Run normal read-only discovery against approved real providers.
    """
    validate_source_policies()

    registry = build_default_discovery_registry()

    settings = DiscoverySettings(
        max_apps=max_apps,
        per_source_limit=max_apps,
        per_source_timeout_seconds=8.0,
        min_candidate_confidence=0.0,
        deduplicate=True,
        validate_candidates=True,
        prefer_package_identity=True,
    )

    return discover_candidates(
        registry.sources,
        max_apps=max_apps,
        settings=settings,
    )


def build_extended_diagnostic_registry(
) -> DiscoveryRegistry:
    """
    Includes deliberate duplicate/failure/invalid providers.

    Useful for future engine tests, not normal workflow runs.
    """

    registry = DiscoveryRegistry()

    registry.extend(
        (
            DiagnosticDiscoverySource(),
            DiagnosticDuplicateSource(),
            DiagnosticInvalidSource(),
            DiagnosticFailingSource(),
        )
    )

    return registry


def run_discovery_diagnostic(
    *,
    max_apps: int = 5,
) -> DiscoveryReport:
    """
    Run the safe default local diagnostic.

    No external API calls.
    No Supabase access.
    No APK downloads.
    No writes.
    """

    validate_source_policies()

    registry = (
        build_default_diagnostic_registry()
    )

    settings = DiscoverySettings(
        max_apps=max_apps,
        per_source_limit=max_apps,
        per_source_timeout_seconds=5.0,
        min_candidate_confidence=0.0,
        deduplicate=True,
        validate_candidates=True,
        prefer_package_identity=True,
    )

    return discover_candidates(
        registry.sources,
        max_apps=max_apps,
        settings=settings,
    )


def run_extended_discovery_diagnostic(
    *,
    max_apps: int = 5,
) -> DiscoveryReport:
    """
    Test:
    - success path
    - duplicate path
    - invalid candidate isolation
    - source failure isolation

    Still performs no network or external writes.
    """

    validate_source_policies()

    registry = (
        build_extended_diagnostic_registry()
    )

    settings = DiscoverySettings(
        max_apps=max_apps,
        per_source_limit=max_apps,
        per_source_timeout_seconds=5.0,
        min_candidate_confidence=0.0,
        deduplicate=True,
        validate_candidates=True,
        prefer_package_identity=True,
    )

    return discover_candidates(
        registry.sources,
        max_apps=max_apps,
        settings=settings,
    )


# ============================================================
# Future provider contract helpers
# ============================================================

@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """
    Declares which hints a discovery provider may emit.

    Later providers can use this for introspection and testing.
    """

    provides_package_id_hint: bool = False
    provides_repository_hint: bool = False
    provides_description_hint: bool = False
    provides_release_hint: bool = False
    performs_network_requests: bool = True


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """
    Static provider metadata.

    This is intentionally separate from provider implementation.
    """

    name: str
    source_type: SourceType
    capabilities: ProviderCapabilities
    enabled_by_default: bool = True

    def validate(self) -> None:
        if not SAFE_SOURCE_NAME_PATTERN.fullmatch(
            self.name.strip()
        ):
            raise ValueError(
                f"Invalid provider descriptor name: {self.name!r}"
            )

        if not isinstance(
            self.source_type,
            SourceType,
        ):
            raise TypeError(
                "ProviderDescriptor.source_type must be SourceType."
            )


# ============================================================
# Future real providers
# ============================================================

class FutureFdroidSource(
    BaseDiscoverySource
):
    """
    Real, read-only F-Droid discovery provider.

    Discovery reads the official F-Droid v1 repository index and emits
    candidates only. It performs no writes, does not publish, and does
    not fabricate missing metadata. Later engine stages remain
    responsible for verification and publication decisions.
    """

    name = "fdroid"

    source_type = (
        SourceType.FDROID
    )

    INDEX_URL: Final[str] = "https://f-droid.org/repo/index-v1.json"
    APP_URL_PREFIX: Final[str] = "https://f-droid.org/packages/"
    USER_AGENT: Final[str] = "OSGuide-Discovery/0.3 (+https://github.com/)"

    descriptor = ProviderDescriptor(
        name=name,
        source_type=source_type,
        capabilities=ProviderCapabilities(
            provides_package_id_hint=True,
            provides_repository_hint=True,
            provides_description_hint=True,
            provides_release_hint=True,
            performs_network_requests=True,
        ),
        enabled_by_default=True,
    )

    @staticmethod
    def _localized_text(value: object) -> str | None:
        if isinstance(value, str):
            cleaned = sanitize_text(
                value,
                max_length=MAX_DESCRIPTION_LENGTH,
            )
            return cleaned or None

        if isinstance(value, Mapping):
            for locale in ("en-US", "en", "en-GB"):
                candidate = value.get(locale)
                if isinstance(candidate, str):
                    cleaned = sanitize_text(
                        candidate,
                        max_length=MAX_DESCRIPTION_LENGTH,
                    )
                    if cleaned:
                        return cleaned

            for candidate in value.values():
                if isinstance(candidate, str):
                    cleaned = sanitize_text(
                        candidate,
                        max_length=MAX_DESCRIPTION_LENGTH,
                    )
                    if cleaned:
                        return cleaned

        return None

    @staticmethod
    def _repository_hint(app: Mapping[str, object]) -> str | None:
        for key in (
            "sourceCode",
            "SourceCode",
            "sourceCodeUrl",
            "repository",
            "repo",
        ):
            value = app.get(key)
            if (
                isinstance(value, str)
                and is_valid_http_url(value, require_https=True)
            ):
                return value.strip()

        return None

    def discover(
        self,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> list[
        AppCandidate
    ]:
        validate_source_limit(limit)
        validate_source_timeout(timeout_seconds)

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

                payload = json.load(response)

        except HTTPError as exc:
            raise RuntimeError(
                f"F-Droid index returned HTTP {exc.code}."
            ) from exc
        except URLError as exc:
            reason = sanitize_text(
                getattr(exc, "reason", "network error"),
                max_length=200,
            )
            raise RuntimeError(
                f"F-Droid index network error: {reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "F-Droid index returned invalid JSON."
            ) from exc

        if not isinstance(payload, Mapping):
            raise RuntimeError(
                "F-Droid index root must be an object."
            )

        raw_apps = payload.get("apps")
        if not isinstance(raw_apps, list):
            raise RuntimeError(
                "F-Droid index does not contain an apps list."
            )

        confidence = source_base_confidence(
            self.source_type
        )

        candidates: list[AppCandidate] = []

        # The repository index is ordered by F-Droid. Discovery remains
        # bounded and stops as soon as enough structurally valid hints
        # have been collected.
        for raw_app in raw_apps:
            if len(candidates) >= limit:
                break

            if not isinstance(raw_app, Mapping):
                continue

            package_id = raw_app.get("packageName")
            if not isinstance(package_id, str):
                continue

            package_id = package_id.strip()
            if not is_valid_package_id(package_id):
                continue

            name = self._localized_text(
                raw_app.get("name")
            ) or package_id

            description = (
                self._localized_text(raw_app.get("summary"))
                or self._localized_text(raw_app.get("description"))
            )

            repository_url = self._repository_hint(
                raw_app
            )

            source_url = (
                f"{self.APP_URL_PREFIX}{package_id}/"
            )

            metadata: dict[str, object] = {
                "fdroid_package_id": package_id,
                "fdroid_index": self.INDEX_URL,
                "network_request": True,
                "publish_allowed": False,
            }

            suggested_version_code = raw_app.get(
                "suggestedVersionCode"
            )
            if isinstance(
                suggested_version_code,
                (int, str),
            ):
                metadata["suggested_version_code"] = (
                    suggested_version_code
                )

            suggested_version_name = raw_app.get(
                "suggestedVersionName"
            )
            if isinstance(
                suggested_version_name,
                str,
            ):
                metadata["suggested_version_name"] = (
                    sanitize_text(
                        suggested_version_name,
                        max_length=100,
                    )
                )

            candidate = AppCandidate(
                name=name,
                source_type=self.source_type.value,
                source_url=source_url,
                package_id=package_id,
                repository_url=repository_url,
                description=description,
                source_confidence=confidence,
                metadata=metadata,
            )

            candidate.add_source_name(
                self.name
            )

            candidate.add_evidence(
                create_listing_evidence(
                    source_type=self.source_type,
                    source_name=self.name,
                    url=source_url,
                    confidence=confidence,
                    note=(
                        "Candidate discovered from the official "
                        "F-Droid repository index."
                    ),
                )
            )

            candidates.append(candidate)

        return candidates


class FutureGithubSource(
    BaseDiscoverySource
):
    """
    Placeholder contract for the real GitHub discovery provider.
    """

    name = "github"

    source_type = (
        SourceType.GITHUB
    )

    descriptor = ProviderDescriptor(
        name=name,
        source_type=source_type,
        capabilities=ProviderCapabilities(
            provides_package_id_hint=False,
            provides_repository_hint=True,
            provides_description_hint=True,
            provides_release_hint=True,
            performs_network_requests=True,
        ),
        enabled_by_default=False,
    )

    def discover(
        self,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> list[
        AppCandidate
    ]:
        del limit
        del timeout_seconds

        raise NotImplementedError(
            "Real GitHub discovery is not connected yet."
        )


# ============================================================
# Public exports
# ============================================================

__all__: Final[
    tuple[str, ...]
] = (
    "AppCandidate",
    "BaseDiscoverySource",
    "CandidateDisposition",
    "CandidateEvidence",
    "CandidateValidationResult",
    "DiagnosticDiscoverySource",
    "DiagnosticDuplicateSource",
    "DiagnosticFailingSource",
    "DiagnosticInvalidSource",
    "DiscoveryRegistry",
    "DiscoveryReport",
    "DiscoverySettings",
    "DiscoverySource",
    "DiscoverySourceResult",
    "DiscoveryStatus",
    "EvidenceKind",
    "FutureFdroidSource",
    "FutureGithubSource",
    "ProviderCapabilities",
    "ProviderDescriptor",
    "SourcePolicy",
    "SourceType",
    "build_default_diagnostic_registry",
    "build_default_discovery_registry",
    "build_extended_diagnostic_registry",
    "candidate_sort_key",
    "clamp_confidence",
    "compute_candidate_confidence",
    "create_listing_evidence",
    "deduplicate_candidates",
    "discover_candidates",
    "evidence_fingerprint",
    "is_valid_http_url",
    "is_valid_package_id",
    "merge_candidates",
    "normalize_url",
    "run_default_discovery",
    "run_discovery_diagnostic",
    "run_extended_discovery_diagnostic",
    "run_source",
    "sanitize_error",
    "sanitize_text",
    "source_base_confidence",
    "validate_candidate",
    "validate_candidates",
    "validate_package_id",
    "validate_source_policies",
    "validate_url",
)
