"""
OSGuide Engine
Discovery Layer

Responsible for discovering candidate Android applications from
trusted open-source sources.

This layer does NOT:
- publish applications
- modify Supabase
- download APK files
- modify the public website

Discovery failures are isolated so that one failing source does not
stop the entire discovery process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Final, Iterable
from urllib.parse import urlparse
import hashlib


# ============================================================
# Discovery constants
# ============================================================

DISCOVERY_COMPONENT: Final[str] = "Discovery"

DEFAULT_SOURCE_CONFIDENCE: Final[float] = 0.50
MIN_SOURCE_CONFIDENCE: Final[float] = 0.0
MAX_SOURCE_CONFIDENCE: Final[float] = 1.0

TRUSTED_SOURCE_TYPES: Final[tuple[str, ...]] = (
    "fdroid",
    "github",
    "gitlab",
    "codeberg",
)


# ============================================================
# Candidate model
# ============================================================

@dataclass(slots=True)
class AppCandidate:
    """
    A raw application candidate discovered by the engine.

    A candidate is not automatically approved for OSGuide.
    Later engine stages must verify and resolve its metadata.
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

    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def identity(self) -> str:
        """
        Return a stable identity used for candidate deduplication.

        Package ID is preferred when available.
        """

        if self.package_id:
            return f"package:{self.package_id.strip().lower()}"

        normalized_url = normalize_url(self.source_url)

        digest = hashlib.sha256(
            normalized_url.encode("utf-8")
        ).hexdigest()

        return f"url:{digest}"

    def validate(self) -> None:
        """Validate basic candidate structure."""

        if not self.name.strip():
            raise ValueError("Candidate name cannot be empty.")

        if self.source_type not in TRUSTED_SOURCE_TYPES:
            raise ValueError(
                f"Unsupported source type: {self.source_type}"
            )

        if not is_valid_http_url(self.source_url):
            raise ValueError(
                f"Invalid source URL: {self.source_url}"
            )

        if self.repository_url and not is_valid_http_url(
            self.repository_url
        ):
            raise ValueError(
                f"Invalid repository URL: {self.repository_url}"
            )

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


# ============================================================
# Source result model
# ============================================================

@dataclass(slots=True)
class DiscoverySourceResult:
    """
    Result produced by one discovery source.

    Errors are stored instead of immediately terminating the engine.
    """

    source_name: str

    candidates: list[AppCandidate] = field(default_factory=list)

    error: str | None = None

    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.error is None


# ============================================================
# Discovery report
# ============================================================

@dataclass(slots=True)
class DiscoveryReport:
    """Aggregated result from all discovery sources."""

    started_at: datetime

    finished_at: datetime | None = None

    source_results: list[DiscoverySourceResult] = field(
        default_factory=list
    )

    candidates: list[AppCandidate] = field(default_factory=list)

    duplicates_removed: int = 0

    invalid_candidates_removed: int = 0

    @property
    def duration_seconds(self) -> float:
        end_time = self.finished_at or datetime.now(timezone.utc)

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
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
            if not result.succeeded
        )


# ============================================================
# URL helpers
# ============================================================

def is_valid_http_url(value: str) -> bool:
    """Return True only for valid HTTP or HTTPS URLs."""

    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False

    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
    )


def normalize_url(value: str) -> str:
    """Normalize URLs for stable comparisons."""

    value = value.strip()

    try:
        parsed = urlparse(value)
    except ValueError:
        return value.lower()

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()

    port = parsed.port

    if port is not None:
        hostname = f"{hostname}:{port}"

    path = parsed.path.rstrip("/")

    normalized = f"{scheme}://{hostname}{path}"

    if parsed.query:
        normalized += f"?{parsed.query}"

    return normalized


# ============================================================
# Candidate validation
# ============================================================

def validate_candidates(
    candidates: Iterable[AppCandidate],
) -> tuple[list[AppCandidate], int]:
    """
    Validate candidates without allowing one malformed candidate
    to terminate the discovery run.
    """

    valid: list[AppCandidate] = []
    invalid_count = 0

    for candidate in candidates:
        try:
            candidate.validate()
        except (TypeError, ValueError):
            invalid_count += 1
            continue

        valid.append(candidate)

    return valid, invalid_count


# ============================================================
# Deduplication
# ============================================================

def deduplicate_candidates(
    candidates: Iterable[AppCandidate],
) -> tuple[list[AppCandidate], int]:
    """
    Remove duplicate candidates.

    If duplicate candidates exist, the candidate with the highest
    source confidence is retained.
    """

    selected: dict[str, AppCandidate] = {}

    duplicate_count = 0

    for candidate in candidates:
        identity = candidate.identity

        existing = selected.get(identity)

        if existing is None:
            selected[identity] = candidate
            continue

        duplicate_count += 1

        if candidate.source_confidence > existing.source_confidence:
            selected[identity] = candidate

    return list(selected.values()), duplicate_count


# ============================================================
# Discovery source interface
# ============================================================

class DiscoverySource:
    """
    Base interface for discovery providers.

    Concrete providers will be added separately so source-specific
    failures remain isolated.
    """

    name: str = "unknown"

    def discover(
        self,
        *,
        limit: int,
    ) -> list[AppCandidate]:
        raise NotImplementedError


# ============================================================
# Safe source execution
# ============================================================

def run_source(
    source: DiscoverySource,
    *,
    limit: int,
) -> DiscoverySourceResult:
    """
    Execute one discovery source safely.

    A failing source produces an error result instead of stopping
    the entire discovery engine.
    """

    import time

    started = time.monotonic()

    try:
        candidates = source.discover(limit=limit)

        if not isinstance(candidates, list):
            raise TypeError(
                "Discovery source must return a list."
            )

        return DiscoverySourceResult(
            source_name=source.name,
            candidates=candidates,
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )

    except Exception as exc:
        return DiscoverySourceResult(
            source_name=source.name,
            error=f"{type(exc).__name__}: {exc}",
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )


# ============================================================
# Discovery coordinator
# ============================================================

def discover_candidates(
    sources: Iterable[DiscoverySource],
    *,
    max_apps: int,
) -> DiscoveryReport:
    """
    Run all configured discovery sources and produce a safe,
    deduplicated candidate report.
    """

    if max_apps < 1:
        raise ValueError("max_apps must be at least 1.")

    report = DiscoveryReport(
        started_at=datetime.now(timezone.utc)
    )

    collected: list[AppCandidate] = []

    for source in sources:
        result = run_source(
            source,
            limit=max_apps,
        )

        report.source_results.append(result)

        if result.succeeded:
            collected.extend(result.candidates)

    valid_candidates, invalid_count = validate_candidates(
        collected
    )

    unique_candidates, duplicate_count = deduplicate_candidates(
        valid_candidates
    )

    unique_candidates.sort(
        key=lambda candidate: (
            -candidate.source_confidence,
            candidate.name.lower(),
        )
    )

    report.candidates = unique_candidates[:max_apps]

    report.invalid_candidates_removed = invalid_count
    report.duplicates_removed = duplicate_count

    report.finished_at = datetime.now(timezone.utc)

    return report


# ============================================================
# Diagnostic source
# ============================================================

class DiagnosticDiscoverySource(DiscoverySource):
    """
    Internal source used only to verify the discovery pipeline.

    It performs no network requests.
    """

    name = "diagnostic"

    def discover(
        self,
        *,
        limit: int,
    ) -> list[AppCandidate]:

        if limit < 1:
            return []

        return [
            AppCandidate(
                name="OSGuide Diagnostic Candidate",
                source_type="github",
                source_url="https://github.com/",
                repository_url="https://github.com/",
                description=(
                    "Internal candidate used to verify the "
                    "OSGuide discovery pipeline."
                ),
                source_confidence=1.0,
                metadata={
                    "diagnostic": True,
                },
            )
        ]


# ============================================================
# Public diagnostic test
# ============================================================

def run_discovery_diagnostic(
    *,
    max_apps: int = 5,
) -> DiscoveryReport:
    """
    Run a harmless local discovery test.

    No external API calls or writes are performed.
    """

    return discover_candidates(
        [
            DiagnosticDiscoverySource(),
        ],
        max_apps=max_apps,
    )
