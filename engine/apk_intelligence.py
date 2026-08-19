"""
OSGuide Engine
APK Intelligence Layer

Purpose
-------
This module evaluates APK release candidates after Discovery and the
Super Resolver have identified an application and possible release
artifacts.

It is responsible for:
- APK candidate modeling
- release / version normalization
- source provenance
- architecture classification
- APK filename heuristics
- content-type validation
- trusted-host policy checks
- duplicate artifact suppression
- release ranking
- latest-stable selection
- package/version consistency hooks
- URL-health result modeling
- bounded probing policy
- diagnostic APK providers
- failure isolation
- structured APK intelligence reports

This module does NOT:
- publish to Supabase
- delete applications
- execute APK files
- install APK files
- run untrusted shell commands
- fabricate APK URLs
- fabricate versions
- bypass package identity conflicts
- download entire APKs during ordinary selection
- replace Admin decisions
- make the final publish/skip/review decision

Architecture rules
------------------
1. Prefer the latest stable release.
2. Prefer direct APK artifacts from trusted sources.
3. Missing APK data must trigger further resolution or review, not
   invention.
4. A difficult APK candidate must not block the whole engine run.
5. All network probing must be bounded.
6. Redirects and hosts must be validated.
7. APK links must be treated as untrusted external input.
8. Package/version verification results must be preserved.
9. Universal APKs are preferred where suitable.
10. Architecture-specific APKs remain valid when universal is absent.
11. Pre-release artifacts are rejected by default.
12. Source provenance is retained for every chosen artifact.
13. Existing-app review can reuse this module for broken-link repair.
14. No automatic deletion is ever performed here.
15. The module is intentionally independent from the Publisher.

Live HTTP probing and binary metadata parsing will be connected through
separate provider/network modules later. This file provides the stable
APK intelligence core.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Final, Iterable, Protocol, Sequence
from urllib.parse import urlparse

from discovery import (
    SourceType,
    is_valid_http_url,
    normalize_url,
    sanitize_error,
    sanitize_text,
)


# ============================================================
# Component identity
# ============================================================

APK_COMPONENT: Final[str] = "APK Intelligence"
APK_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Safety limits
# ============================================================

DEFAULT_PROBE_TIMEOUT_SECONDS: Final[float] = 8.0
MIN_PROBE_TIMEOUT_SECONDS: Final[float] = 1.0
MAX_PROBE_TIMEOUT_SECONDS: Final[float] = 30.0

DEFAULT_MAX_REDIRECTS: Final[int] = 5
MAX_REDIRECTS: Final[int] = 10

DEFAULT_MAX_ARTIFACTS: Final[int] = 20
MAX_ARTIFACTS: Final[int] = 100

DEFAULT_MAX_PROBE_BYTES: Final[int] = 1_000_000
MIN_PROBE_BYTES: Final[int] = 64_000
MAX_PROBE_BYTES: Final[int] = 20_000_000

MAX_URL_LENGTH: Final[int] = 2048
MAX_FILENAME_LENGTH: Final[int] = 255
MAX_VERSION_LENGTH: Final[int] = 128
MAX_PROVIDER_NAME_LENGTH: Final[int] = 80
MAX_WARNINGS: Final[int] = 100
MAX_ERRORS: Final[int] = 100


# ============================================================
# Patterns
# ============================================================

APK_FILENAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)\.apk(?:$|[?#])"
)

VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._+~:-]{0,127}$"
)

PRERELEASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:alpha|beta|rc|preview|nightly|snapshot|dev|canary)"
)

ARM64_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:arm64|aarch64|armv8)"
)

ARMV7_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:armeabi-v7a|armv7|armeabi)"
)

X86_64_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:x86_64|x64)"
)

X86_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:^|[-_.])x86(?:[-_.]|$)"
)

UNIVERSAL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:universal|all|noarch)"
)

BUNDLE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?i)\.(?:aab|apks|xapk)(?:$|[?#])"
)


# ============================================================
# Enums
# ============================================================

class ApkArchitecture(str, Enum):
    UNIVERSAL = "universal"
    ARM64_V8A = "arm64-v8a"
    ARMEABI_V7A = "armeabi-v7a"
    X86_64 = "x86_64"
    X86 = "x86"
    UNKNOWN = "unknown"


class ReleaseChannel(str, Enum):
    STABLE = "stable"
    PRERELEASE = "prerelease"
    NIGHTLY = "nightly"
    UNKNOWN = "unknown"


class ArtifactStatus(str, Enum):
    CANDIDATE = "candidate"
    VALID = "valid"
    INVALID = "invalid"
    UNREACHABLE = "unreachable"
    CONFLICT = "conflict"
    REVIEW = "review"


class ProbeStatus(str, Enum):
    NOT_PROBED = "not-probed"
    SUCCESS = "success"
    FAILURE = "failure"
    REDIRECT_BLOCKED = "redirect-blocked"


class VerificationState(str, Enum):
    UNKNOWN = "unknown"
    MATCH = "match"
    MISMATCH = "mismatch"
    NOT_AVAILABLE = "not-available"


class SelectionStatus(str, Enum):
    SELECTED = "selected"
    NO_VALID_APK = "no-valid-apk"
    CONFLICT = "conflict"
    REVIEW = "review"
    FAILED = "failed"


# ============================================================
# Host policy
# ============================================================

TRUSTED_APK_HOST_SUFFIXES: Final[tuple[str, ...]] = (
    "github.com",
    "githubusercontent.com",
    "f-droid.org",
    "gitlab.com",
    "codeberg.org",
)

TRUSTED_SOURCE_WEIGHTS: Final[dict[SourceType, float]] = {
    SourceType.GITHUB: 0.95,
    SourceType.FDROID: 0.95,
    SourceType.GITLAB: 0.90,
    SourceType.CODEBERG: 0.90,
    SourceType.OFFICIAL: 0.85,
}


# ============================================================
# Core models
# ============================================================

@dataclass(frozen=True, slots=True)
class ApkEvidence:
    provider_name: str
    source_type: SourceType
    source_url: str
    confidence: float
    note: str | None = None
    observed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def validate(self) -> None:
        if not self.provider_name.strip():
            raise ValueError("APK evidence provider name cannot be empty.")

        if len(self.provider_name) > MAX_PROVIDER_NAME_LENGTH:
            raise ValueError("APK evidence provider name is too long.")

        if not is_valid_http_url(self.source_url, require_https=True):
            raise ValueError("APK evidence requires a valid HTTPS source URL.")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("APK evidence confidence must be between 0 and 1.")


@dataclass(slots=True)
class UrlProbeResult:
    status: ProbeStatus = ProbeStatus.NOT_PROBED
    final_url: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    redirects: int = 0
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.status == ProbeStatus.SUCCESS and self.error is None


@dataclass(slots=True)
class ApkArtifact:
    url: str
    source_type: SourceType
    provider_name: str

    version: str | None = None
    filename: str | None = None
    architecture: ApkArchitecture = ApkArchitecture.UNKNOWN
    channel: ReleaseChannel = ReleaseChannel.UNKNOWN

    package_id_hint: str | None = None
    size_bytes: int | None = None

    evidence_confidence: float = 0.5

    evidence: list[ApkEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    probe: UrlProbeResult = field(default_factory=UrlProbeResult)

    package_verification: VerificationState = VerificationState.UNKNOWN
    version_verification: VerificationState = VerificationState.UNKNOWN

    status: ArtifactStatus = ArtifactStatus.CANDIDATE

    discovered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def normalized_url(self) -> str:
        return normalize_url(self.url)

    @property
    def identity(self) -> str:
        raw = "|".join(
            (
                self.normalized_url,
                (self.version or "").lower(),
                self.architecture.value,
            )
        )

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add_warning(self, message: str) -> None:
        if len(self.warnings) >= MAX_WARNINGS:
            return

        cleaned = sanitize_text(message, max_length=400)

        if cleaned and cleaned not in self.warnings:
            self.warnings.append(cleaned)

    def add_evidence(self, item: ApkEvidence) -> None:
        item.validate()

        fingerprint = apk_evidence_fingerprint(item)

        known = {
            apk_evidence_fingerprint(existing)
            for existing in self.evidence
        }

        if fingerprint not in known:
            self.evidence.append(item)

    def validate(self) -> None:
        validate_apk_url(self.url)

        if len(self.provider_name) > MAX_PROVIDER_NAME_LENGTH:
            raise ValueError("APK provider name is too long.")

        if not self.provider_name.strip():
            raise ValueError("APK provider name cannot be empty.")

        if self.version is not None:
            validate_version(self.version)

        if self.filename is not None:
            if len(self.filename) > MAX_FILENAME_LENGTH:
                raise ValueError("APK filename is too long.")

        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("APK size cannot be negative.")

        if not 0.0 <= self.evidence_confidence <= 1.0:
            raise ValueError(
                "APK evidence confidence must be between 0 and 1."
            )


@dataclass(slots=True)
class ApkProviderResult:
    provider_name: str
    artifacts: list[ApkArtifact] = field(default_factory=list)
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(slots=True)
class ApkSelectionReport:
    started_at: datetime
    finished_at: datetime | None = None

    status: SelectionStatus = SelectionStatus.NO_VALID_APK

    selected: ApkArtifact | None = None

    candidates: list[ApkArtifact] = field(default_factory=list)

    provider_results: list[ApkProviderResult] = field(default_factory=list)

    duplicates_removed: int = 0
    invalid_removed: int = 0
    prerelease_removed: int = 0
    untrusted_host_removed: int = 0

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        end_time = self.finished_at or datetime.now(timezone.utc)

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )

    def add_warning(self, message: str) -> None:
        if len(self.warnings) >= MAX_WARNINGS:
            return

        cleaned = sanitize_text(message, max_length=500)

        if cleaned and cleaned not in self.warnings:
            self.warnings.append(cleaned)

    def add_error(self, message: str) -> None:
        if len(self.errors) >= MAX_ERRORS:
            return

        cleaned = sanitize_text(message, max_length=500)

        if cleaned:
            self.errors.append(cleaned)


# ============================================================
# Settings
# ============================================================

@dataclass(frozen=True, slots=True)
class ApkPolicy:
    require_https: bool = True
    require_trusted_host: bool = True

    allow_prerelease: bool = False
    allow_unknown_channel: bool = True

    prefer_universal: bool = True
    allow_arch_specific: bool = True

    require_apk_extension: bool = True
    reject_bundle_formats: bool = True

    require_latest_stable: bool = True

    verify_url_alive: bool = True
    verify_content_type: bool = True
    verify_package_identity: bool = True
    verify_version_consistency: bool = True

    max_artifacts: int = DEFAULT_MAX_ARTIFACTS
    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS
    max_redirects: int = DEFAULT_MAX_REDIRECTS
    max_probe_bytes: int = DEFAULT_MAX_PROBE_BYTES

    def validate(self) -> None:
        if not 1 <= self.max_artifacts <= MAX_ARTIFACTS:
            raise ValueError("APK max_artifacts outside allowed range.")

        if not (
            MIN_PROBE_TIMEOUT_SECONDS
            <= self.probe_timeout_seconds
            <= MAX_PROBE_TIMEOUT_SECONDS
        ):
            raise ValueError("APK probe timeout outside allowed range.")

        if not 0 <= self.max_redirects <= MAX_REDIRECTS:
            raise ValueError("APK max_redirects outside allowed range.")

        if not MIN_PROBE_BYTES <= self.max_probe_bytes <= MAX_PROBE_BYTES:
            raise ValueError("APK max_probe_bytes outside allowed range.")


# ============================================================
# Provider protocol
# ============================================================

class ApkProvider(Protocol):
    name: str
    source_type: SourceType

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        ...


class BaseApkProvider:
    name: str = "unknown"
    source_type: SourceType = SourceType.OFFICIAL

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        raise NotImplementedError


# ============================================================
# Utility validation
# ============================================================

def host_matches_suffix(host: str, suffix: str) -> bool:
    host = host.lower().strip(".")
    suffix = suffix.lower().strip(".")

    return host == suffix or host.endswith("." + suffix)


def is_trusted_apk_host(url: str) -> bool:
    if not is_valid_http_url(url, require_https=True):
        return False

    parsed = urlparse(url)

    host = (parsed.hostname or "").lower()

    return any(
        host_matches_suffix(host, suffix)
        for suffix in TRUSTED_APK_HOST_SUFFIXES
    )


def validate_version(version: str) -> None:
    version = version.strip()

    if not version:
        raise ValueError("Version cannot be empty.")

    if len(version) > MAX_VERSION_LENGTH:
        raise ValueError("Version is too long.")

    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"Invalid version: {version!r}")


def validate_apk_url(url: str) -> None:
    if len(url) > MAX_URL_LENGTH:
        raise ValueError("APK URL is too long.")

    if not is_valid_http_url(url, require_https=True):
        raise ValueError("APK URL must be a valid HTTPS URL.")

    if BUNDLE_PATTERN.search(url):
        raise ValueError(
            "Bundle package format detected; direct APK expected."
        )


def filename_from_url(url: str) -> str:
    parsed = urlparse(url)

    filename = parsed.path.rsplit("/", 1)[-1]

    return sanitize_text(
        filename,
        max_length=MAX_FILENAME_LENGTH,
    )


def looks_like_apk_url(url: str) -> bool:
    return bool(APK_FILENAME_PATTERN.search(url))


# ============================================================
# Architecture detection
# ============================================================

def detect_architecture(value: str) -> ApkArchitecture:
    if UNIVERSAL_PATTERN.search(value):
        return ApkArchitecture.UNIVERSAL

    if ARM64_PATTERN.search(value):
        return ApkArchitecture.ARM64_V8A

    if ARMV7_PATTERN.search(value):
        return ApkArchitecture.ARMEABI_V7A

    if X86_64_PATTERN.search(value):
        return ApkArchitecture.X86_64

    if X86_PATTERN.search(value):
        return ApkArchitecture.X86

    return ApkArchitecture.UNKNOWN


# ============================================================
# Release channel detection
# ============================================================

def detect_release_channel(
    *,
    version: str | None,
    filename: str | None,
) -> ReleaseChannel:
    combined = " ".join(
        value
        for value in (version, filename)
        if value
    )

    lowered = combined.lower()

    if "nightly" in lowered or "snapshot" in lowered:
        return ReleaseChannel.NIGHTLY

    if PRERELEASE_PATTERN.search(combined):
        return ReleaseChannel.PRERELEASE

    if combined:
        return ReleaseChannel.STABLE

    return ReleaseChannel.UNKNOWN


# ============================================================
# Version sorting
# ============================================================

def tokenize_version(version: str | None) -> tuple[tuple[int, object], ...]:
    """
    Conservative version tokenizer.

    Numeric pieces sort numerically. Text pieces sort lexically.
    This is not intended to replace a full semantic-version library
    for all projects, but it provides deterministic ordering until
    the dedicated version module is connected.
    """

    if not version:
        return tuple()

    pieces = re.split(r"([0-9]+)", version.lower())

    tokens: list[tuple[int, object]] = []

    for piece in pieces:
        if not piece:
            continue

        if piece.isdigit():
            tokens.append((1, int(piece)))
        else:
            tokens.append((0, piece))

    return tuple(tokens)


def compare_versions(
    first: str | None,
    second: str | None,
) -> int:
    a = tokenize_version(first)
    b = tokenize_version(second)

    if a == b:
        return 0

    return 1 if a > b else -1


# ============================================================
# Evidence fingerprint
# ============================================================

def apk_evidence_fingerprint(evidence: ApkEvidence) -> str:
    raw = "|".join(
        (
            evidence.provider_name.lower(),
            evidence.source_type.value,
            normalize_url(evidence.source_url),
            f"{evidence.confidence:.6f}",
        )
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ============================================================
# Artifact normalization
# ============================================================

def normalize_artifact(artifact: ApkArtifact) -> ApkArtifact:
    artifact.validate()

    artifact.url = normalize_url(artifact.url)

    if not artifact.filename:
        artifact.filename = filename_from_url(artifact.url)

    if artifact.architecture == ApkArchitecture.UNKNOWN:
        artifact.architecture = detect_architecture(
            artifact.filename or artifact.url
        )

    if artifact.channel == ReleaseChannel.UNKNOWN:
        artifact.channel = detect_release_channel(
            version=artifact.version,
            filename=artifact.filename,
        )

    return artifact


# ============================================================
# Artifact validation pipeline
# ============================================================

@dataclass(slots=True)
class ArtifactValidationResult:
    valid: bool
    artifact: ApkArtifact
    error: str | None = None


def validate_artifact(
    artifact: ApkArtifact,
    *,
    policy: ApkPolicy,
) -> ArtifactValidationResult:
    try:
        normalize_artifact(artifact)

        if policy.require_trusted_host:
            if not is_trusted_apk_host(artifact.url):
                raise ValueError("APK host is not trusted.")

        if policy.require_apk_extension:
            if not looks_like_apk_url(artifact.url):
                raise ValueError("Artifact does not look like a direct APK.")

        if policy.reject_bundle_formats:
            if BUNDLE_PATTERN.search(artifact.url):
                raise ValueError("Bundle format rejected.")

        if not policy.allow_prerelease:
            if artifact.channel in {
                ReleaseChannel.PRERELEASE,
                ReleaseChannel.NIGHTLY,
            }:
                raise ValueError("Pre-release APK rejected by policy.")

        if (
            artifact.channel == ReleaseChannel.UNKNOWN
            and not policy.allow_unknown_channel
        ):
            raise ValueError("Unknown release channel rejected.")

        artifact.status = ArtifactStatus.VALID

        return ArtifactValidationResult(
            valid=True,
            artifact=artifact,
        )

    except Exception as exc:
        artifact.status = ArtifactStatus.INVALID

        return ArtifactValidationResult(
            valid=False,
            artifact=artifact,
            error=sanitize_error(exc),
        )


# ============================================================
# Deduplication
# ============================================================

def merge_artifacts(
    existing: ApkArtifact,
    incoming: ApkArtifact,
) -> ApkArtifact:
    if incoming.evidence_confidence > existing.evidence_confidence:
        preferred = incoming
        other = existing
    else:
        preferred = existing
        other = incoming

    for evidence in other.evidence:
        preferred.add_evidence(evidence)

    for warning in other.warnings:
        preferred.add_warning(warning)

    if preferred.size_bytes is None and other.size_bytes is not None:
        preferred.size_bytes = other.size_bytes

    if (
        preferred.package_id_hint is None
        and other.package_id_hint is not None
    ):
        preferred.package_id_hint = other.package_id_hint

    return preferred


def deduplicate_artifacts(
    artifacts: Iterable[ApkArtifact],
) -> tuple[list[ApkArtifact], int]:
    selected: dict[str, ApkArtifact] = {}
    duplicates = 0

    for artifact in artifacts:
        identity = artifact.identity

        existing = selected.get(identity)

        if existing is None:
            selected[identity] = artifact
            continue

        duplicates += 1

        selected[identity] = merge_artifacts(
            existing,
            artifact,
        )

    return list(selected.values()), duplicates


# ============================================================
# Ranking
# ============================================================

ARCHITECTURE_RANK: Final[dict[ApkArchitecture, int]] = {
    ApkArchitecture.UNIVERSAL: 0,
    ApkArchitecture.ARM64_V8A: 1,
    ApkArchitecture.ARMEABI_V7A: 2,
    ApkArchitecture.X86_64: 3,
    ApkArchitecture.X86: 4,
    ApkArchitecture.UNKNOWN: 5,
}

CHANNEL_RANK: Final[dict[ReleaseChannel, int]] = {
    ReleaseChannel.STABLE: 0,
    ReleaseChannel.UNKNOWN: 1,
    ReleaseChannel.PRERELEASE: 2,
    ReleaseChannel.NIGHTLY: 3,
}


def artifact_score(
    artifact: ApkArtifact,
    *,
    policy: ApkPolicy,
) -> float:
    score = 0.0

    score += artifact.evidence_confidence * 50.0

    score += TRUSTED_SOURCE_WEIGHTS.get(
        artifact.source_type,
        0.5,
    ) * 20.0

    if artifact.channel == ReleaseChannel.STABLE:
        score += 15.0

    if (
        policy.prefer_universal
        and artifact.architecture == ApkArchitecture.UNIVERSAL
    ):
        score += 10.0

    if artifact.probe.succeeded:
        score += 10.0

    if artifact.package_verification == VerificationState.MATCH:
        score += 15.0

    if artifact.version_verification == VerificationState.MATCH:
        score += 10.0

    if artifact.package_verification == VerificationState.MISMATCH:
        score -= 100.0

    if artifact.version_verification == VerificationState.MISMATCH:
        score -= 50.0

    return score


def artifact_sort_key(
    artifact: ApkArtifact,
    *,
    policy: ApkPolicy,
) -> tuple[object, ...]:
    version_tokens = tokenize_version(artifact.version)

    return (
        -artifact_score(artifact, policy=policy),
        CHANNEL_RANK[artifact.channel],
        ARCHITECTURE_RANK[artifact.architecture],
        tuple(
            (-kind, value if isinstance(value, str) else -value)
            for kind, value in version_tokens
        ),
        artifact.url,
    )


# ============================================================
# Selection rules
# ============================================================

def choose_latest_version_group(
    artifacts: Sequence[ApkArtifact],
) -> list[ApkArtifact]:
    if not artifacts:
        return []

    latest = artifacts[0].version

    for artifact in artifacts[1:]:
        if compare_versions(artifact.version, latest) > 0:
            latest = artifact.version

    return [
        artifact
        for artifact in artifacts
        if compare_versions(artifact.version, latest) == 0
    ]


def select_best_artifact(
    artifacts: Sequence[ApkArtifact],
    *,
    policy: ApkPolicy,
) -> ApkArtifact | None:
    if not artifacts:
        return None

    candidates = list(artifacts)

    if policy.require_latest_stable:
        stable = [
            artifact
            for artifact in candidates
            if artifact.channel == ReleaseChannel.STABLE
        ]

        if stable:
            candidates = choose_latest_version_group(stable)

    candidates.sort(
        key=lambda artifact: artifact_sort_key(
            artifact,
            policy=policy,
        )
    )

    return candidates[0] if candidates else None


# ============================================================
# Provider validation and registry
# ============================================================

def validate_provider(provider: ApkProvider) -> None:
    name = getattr(provider, "name", None)
    source_type = getattr(provider, "source_type", None)
    method = getattr(provider, "find_apks", None)

    if not isinstance(name, str) or not name.strip():
        raise ValueError("APK provider requires a non-empty name.")

    if len(name) > MAX_PROVIDER_NAME_LENGTH:
        raise ValueError("APK provider name is too long.")

    if not isinstance(source_type, SourceType):
        raise TypeError("APK provider requires SourceType.")

    if not callable(method):
        raise TypeError("APK provider requires find_apks().")


class ApkProviderRegistry:
    def __init__(self) -> None:
        self._providers: list[ApkProvider] = []
        self._names: set[str] = set()

    @property
    def providers(self) -> tuple[ApkProvider, ...]:
        return tuple(self._providers)

    def register(self, provider: ApkProvider) -> None:
        validate_provider(provider)

        normalized = provider.name.strip().lower()

        if normalized in self._names:
            raise ValueError(
                f"Duplicate APK provider name: {provider.name}"
            )

        self._providers.append(provider)
        self._names.add(normalized)

    def extend(self, providers: Iterable[ApkProvider]) -> None:
        for provider in providers:
            self.register(provider)


# ============================================================
# Provider execution
# ============================================================

def run_apk_provider(
    provider: ApkProvider,
    *,
    package_id: str | None,
    repository_url: str | None,
    source_url: str | None,
    version_hint: str | None,
    limit: int,
    timeout_seconds: float,
) -> ApkProviderResult:
    started = time.monotonic()

    try:
        validate_provider(provider)

        if not 1 <= limit <= MAX_ARTIFACTS:
            raise ValueError("APK provider limit outside allowed range.")

        if not (
            MIN_PROBE_TIMEOUT_SECONDS
            <= timeout_seconds
            <= MAX_PROBE_TIMEOUT_SECONDS
        ):
            raise ValueError("APK provider timeout outside allowed range.")

        artifacts = provider.find_apks(
            package_id=package_id,
            repository_url=repository_url,
            source_url=source_url,
            version_hint=version_hint,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

        if not isinstance(artifacts, list):
            raise TypeError("APK provider must return a list.")

        return ApkProviderResult(
            provider_name=provider.name,
            artifacts=artifacts[:limit],
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )

    except Exception as exc:
        return ApkProviderResult(
            provider_name=getattr(provider, "name", "unknown"),
            error=sanitize_error(exc),
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )


# ============================================================
# Main APK Intelligence orchestration
# ============================================================

def analyze_apks(
    providers: Sequence[ApkProvider],
    *,
    package_id: str | None,
    repository_url: str | None,
    source_url: str | None,
    version_hint: str | None,
    policy: ApkPolicy | None = None,
) -> ApkSelectionReport:
    if policy is None:
        policy = ApkPolicy()

    policy.validate()

    report = ApkSelectionReport(
        started_at=datetime.now(timezone.utc)
    )

    collected: list[ApkArtifact] = []

    for provider in providers:
        provider_result = run_apk_provider(
            provider,
            package_id=package_id,
            repository_url=repository_url,
            source_url=source_url,
            version_hint=version_hint,
            limit=policy.max_artifacts,
            timeout_seconds=policy.probe_timeout_seconds,
        )

        report.provider_results.append(provider_result)

        if provider_result.succeeded:
            collected.extend(provider_result.artifacts)
        else:
            report.add_warning(
                f"APK provider {provider_result.provider_name!r} failed: "
                f"{provider_result.error or 'unknown error'}"
            )

    valid_artifacts: list[ApkArtifact] = []

    for artifact in collected:
        validation = validate_artifact(
            artifact,
            policy=policy,
        )

        if validation.valid:
            valid_artifacts.append(validation.artifact)
            continue

        report.invalid_removed += 1

        error = validation.error or ""

        if "Pre-release" in error:
            report.prerelease_removed += 1

        if "host is not trusted" in error:
            report.untrusted_host_removed += 1

    unique, duplicate_count = deduplicate_artifacts(
        valid_artifacts
    )

    report.duplicates_removed = duplicate_count

    report.candidates = unique

    selected = select_best_artifact(
        unique,
        policy=policy,
    )

    if selected is None:
        report.status = SelectionStatus.NO_VALID_APK
        report.add_warning(
            "No valid APK artifact was selected."
        )
    else:
        selected.status = ArtifactStatus.VALID
        report.selected = selected
        report.status = SelectionStatus.SELECTED

    report.finished_at = datetime.now(timezone.utc)

    return report


# ============================================================
# Diagnostic provider
# ============================================================

class DiagnosticApkProvider(BaseApkProvider):
    name = "diagnostic-apk"
    source_type = SourceType.GITHUB

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        del repository_url
        del source_url
        del timeout_seconds

        if limit < 1:
            return []

        version = version_hint or "1.0.0"

        artifact = ApkArtifact(
            url=(
                "https://github.com/example/osguide-diagnostic/"
                "releases/download/v1.0.0/osguide-universal.apk"
            ),
            source_type=self.source_type,
            provider_name=self.name,
            version=version,
            filename="osguide-universal.apk",
            architecture=ApkArchitecture.UNIVERSAL,
            channel=ReleaseChannel.STABLE,
            package_id_hint=package_id or "org.osguide.diagnostic",
            size_bytes=12_000_000,
            evidence_confidence=0.90,
        )

        artifact.add_evidence(
            ApkEvidence(
                provider_name=self.name,
                source_type=self.source_type,
                source_url="https://github.com/",
                confidence=0.90,
                note="Synthetic diagnostic APK evidence.",
            )
        )

        return [artifact]


class DiagnosticPrereleaseApkProvider(BaseApkProvider):
    name = "diagnostic-prerelease"
    source_type = SourceType.GITHUB

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        del package_id
        del repository_url
        del source_url
        del version_hint
        del timeout_seconds

        if limit < 1:
            return []

        return [
            ApkArtifact(
                url=(
                    "https://github.com/example/osguide-diagnostic/"
                    "releases/download/v2.0.0-beta/app-beta.apk"
                ),
                source_type=self.source_type,
                provider_name=self.name,
                version="2.0.0-beta",
                filename="app-beta.apk",
                architecture=ApkArchitecture.UNIVERSAL,
                channel=ReleaseChannel.PRERELEASE,
                evidence_confidence=0.80,
            )
        ]


class DiagnosticDuplicateApkProvider(BaseApkProvider):
    name = "diagnostic-duplicate-apk"
    source_type = SourceType.GITHUB

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        del repository_url
        del source_url
        del timeout_seconds

        if limit < 1:
            return []

        return [
            ApkArtifact(
                url=(
                    "https://github.com/example/osguide-diagnostic/"
                    "releases/download/v1.0.0/osguide-universal.apk"
                ),
                source_type=self.source_type,
                provider_name=self.name,
                version=version_hint or "1.0.0",
                filename="osguide-universal.apk",
                architecture=ApkArchitecture.UNIVERSAL,
                channel=ReleaseChannel.STABLE,
                package_id_hint=package_id or "org.osguide.diagnostic",
                evidence_confidence=0.70,
            )
        ]


class DiagnosticFailingApkProvider(BaseApkProvider):
    name = "diagnostic-apk-failure"
    source_type = SourceType.CODEBERG

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        del package_id
        del repository_url
        del source_url
        del version_hint
        del limit
        del timeout_seconds

        raise RuntimeError(
            "Intentional APK provider failure for diagnostics."
        )


# ============================================================
# Diagnostic registries
# ============================================================

def build_default_apk_registry() -> ApkProviderRegistry:
    registry = ApkProviderRegistry()

    registry.register(
        DiagnosticApkProvider()
    )

    return registry


def build_extended_apk_registry() -> ApkProviderRegistry:
    registry = ApkProviderRegistry()

    registry.extend(
        (
            DiagnosticApkProvider(),
            DiagnosticPrereleaseApkProvider(),
            DiagnosticDuplicateApkProvider(),
            DiagnosticFailingApkProvider(),
        )
    )

    return registry


# ============================================================
# Public diagnostics
# ============================================================

def run_apk_diagnostic(
    *,
    package_id: str = "org.osguide.diagnostic",
    version_hint: str = "1.0.0",
) -> ApkSelectionReport:
    registry = build_default_apk_registry()

    policy = ApkPolicy(
        require_https=True,
        require_trusted_host=True,
        allow_prerelease=False,
        allow_unknown_channel=True,
        prefer_universal=True,
        allow_arch_specific=True,
        require_apk_extension=True,
        reject_bundle_formats=True,
        require_latest_stable=True,
        verify_url_alive=False,
        verify_content_type=False,
        verify_package_identity=False,
        verify_version_consistency=False,
        max_artifacts=20,
        probe_timeout_seconds=5.0,
        max_redirects=5,
        max_probe_bytes=1_000_000,
    )

    return analyze_apks(
        registry.providers,
        package_id=package_id,
        repository_url="https://github.com/",
        source_url="https://github.com/",
        version_hint=version_hint,
        policy=policy,
    )


def run_extended_apk_diagnostic(
    *,
    package_id: str = "org.osguide.diagnostic",
    version_hint: str = "1.0.0",
) -> ApkSelectionReport:
    registry = build_extended_apk_registry()

    policy = ApkPolicy(
        require_https=True,
        require_trusted_host=True,
        allow_prerelease=False,
        allow_unknown_channel=True,
        prefer_universal=True,
        allow_arch_specific=True,
        require_apk_extension=True,
        reject_bundle_formats=True,
        require_latest_stable=True,
        verify_url_alive=False,
        verify_content_type=False,
        verify_package_identity=False,
        verify_version_consistency=False,
        max_artifacts=30,
        probe_timeout_seconds=5.0,
        max_redirects=5,
        max_probe_bytes=1_000_000,
    )

    return analyze_apks(
        registry.providers,
        package_id=package_id,
        repository_url="https://github.com/",
        source_url="https://github.com/",
        version_hint=version_hint,
        policy=policy,
    )


# ============================================================
# Report helpers
# ============================================================

def artifact_summary(
    artifact: ApkArtifact,
) -> dict[str, object]:
    return {
        "url": artifact.url,
        "source_type": artifact.source_type.value,
        "provider_name": artifact.provider_name,
        "version": artifact.version,
        "filename": artifact.filename,
        "architecture": artifact.architecture.value,
        "channel": artifact.channel.value,
        "package_id_hint": artifact.package_id_hint,
        "size_bytes": artifact.size_bytes,
        "evidence_confidence": artifact.evidence_confidence,
        "package_verification": artifact.package_verification.value,
        "version_verification": artifact.version_verification.value,
        "probe_status": artifact.probe.status.value,
        "status": artifact.status.value,
        "warnings": list(artifact.warnings),
    }


def apk_report_summary(
    report: ApkSelectionReport,
) -> dict[str, object]:
    return {
        "status": report.status.value,
        "duration_seconds": round(
            report.duration_seconds,
            3,
        ),
        "selected": (
            artifact_summary(report.selected)
            if report.selected
            else None
        ),
        "candidate_count": len(report.candidates),
        "duplicates_removed": report.duplicates_removed,
        "invalid_removed": report.invalid_removed,
        "prerelease_removed": report.prerelease_removed,
        "untrusted_host_removed": report.untrusted_host_removed,
        "provider_failures": sum(
            1
            for provider_result in report.provider_results
            if not provider_result.succeeded
        ),
        "warnings": list(report.warnings),
        "errors": list(report.errors),
    }


# ============================================================
# Future live provider contracts
# ============================================================

class FutureGithubApkProvider(BaseApkProvider):
    name = "github-apk"
    source_type = SourceType.GITHUB

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        del package_id
        del repository_url
        del source_url
        del version_hint
        del limit
        del timeout_seconds

        raise NotImplementedError(
            "Live GitHub APK provider is not connected yet."
        )


class FutureFdroidApkProvider(BaseApkProvider):
    name = "fdroid-apk"
    source_type = SourceType.FDROID

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        del package_id
        del repository_url
        del source_url
        del version_hint
        del limit
        del timeout_seconds

        raise NotImplementedError(
            "Live F-Droid APK provider is not connected yet."
        )


class FutureOfficialApkProvider(BaseApkProvider):
    name = "official-apk"
    source_type = SourceType.OFFICIAL

    def find_apks(
        self,
        *,
        package_id: str | None,
        repository_url: str | None,
        source_url: str | None,
        version_hint: str | None,
        limit: int,
        timeout_seconds: float,
    ) -> list[ApkArtifact]:
        del package_id
        del repository_url
        del source_url
        del version_hint
        del limit
        del timeout_seconds

        raise NotImplementedError(
            "Live official-site APK provider is not connected yet."
        )


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "APK_COMPONENT",
    "APK_SCHEMA_VERSION",
    "ApkArchitecture",
    "ApkArtifact",
    "ApkEvidence",
    "ApkPolicy",
    "ApkProvider",
    "ApkProviderRegistry",
    "ApkProviderResult",
    "ApkSelectionReport",
    "ArtifactStatus",
    "ArtifactValidationResult",
    "BaseApkProvider",
    "DiagnosticApkProvider",
    "DiagnosticDuplicateApkProvider",
    "DiagnosticFailingApkProvider",
    "DiagnosticPrereleaseApkProvider",
    "FutureFdroidApkProvider",
    "FutureGithubApkProvider",
    "FutureOfficialApkProvider",
    "ProbeStatus",
    "ReleaseChannel",
    "SelectionStatus",
    "TRUSTED_APK_HOST_SUFFIXES",
    "UrlProbeResult",
    "VerificationState",
    "analyze_apks",
    "apk_evidence_fingerprint",
    "apk_report_summary",
    "artifact_score",
    "artifact_sort_key",
    "artifact_summary",
    "build_default_apk_registry",
    "build_extended_apk_registry",
    "choose_latest_version_group",
    "compare_versions",
    "deduplicate_artifacts",
    "detect_architecture",
    "detect_release_channel",
    "filename_from_url",
    "host_matches_suffix",
    "is_trusted_apk_host",
    "looks_like_apk_url",
    "merge_artifacts",
    "normalize_artifact",
    "run_apk_diagnostic",
    "run_apk_provider",
    "run_extended_apk_diagnostic",
    "select_best_artifact",
    "tokenize_version",
    "validate_apk_url",
    "validate_artifact",
    "validate_provider",
    "validate_version",
)
