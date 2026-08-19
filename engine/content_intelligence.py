"""
OSGuide Engine
Content Intelligence Layer

Purpose
-------
This module builds trustworthy user-facing application content from
verified source evidence.

It is responsible for:
- collecting source-backed textual evidence
- normalizing descriptions
- distinguishing short vs full descriptions
- extracting capabilities and use cases
- generating deterministic fallback content
- preparing optional AI-assisted content requests
- validating AI output against evidence
- preserving provenance
- avoiding hallucinated technical claims
- preventing a short source description from causing an app to be skipped
- supporting future Guide content seeding
- producing structured content reports

Architecture rules
------------------
1. A short upstream description is NOT a rejection reason.
2. Missing prose is a content problem, not an identity problem.
3. Content must be grounded in source evidence.
4. Package ID, APK URL, version, license and repository are never invented.
5. AI is optional.
6. If AI fails, deterministic non-AI fallback must continue.
7. One content-generation failure must not stop the entire engine run.
8. Admin-edited/manual content must later retain priority.
9. No Supabase writes occur here.
10. No deletion occurs here.
11. No external code execution occurs here.
12. External text is bounded and sanitized.
13. Evidence provenance is retained for generated content.
14. The module can serve both new-app publishing and existing-app repair.
15. Guide seed generation is conservative and source-backed.

This file intentionally provides the stable Content Intelligence core.
Live network fetching and specific AI provider adapters are connected
through separate modules.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Final, Iterable, Mapping, Protocol, Sequence

from discovery import SourceType, sanitize_error, sanitize_text


# ============================================================
# Component identity
# ============================================================

CONTENT_COMPONENT: Final[str] = "Content Intelligence"
CONTENT_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Hard safety limits
# ============================================================

MAX_SOURCE_DOCUMENTS: Final[int] = 20
MAX_EVIDENCE_ITEMS: Final[int] = 100
MAX_EVIDENCE_TEXT_CHARS: Final[int] = 40_000
MAX_SINGLE_EVIDENCE_CHARS: Final[int] = 10_000

MAX_SHORT_DESCRIPTION_CHARS: Final[int] = 240
MIN_SHORT_DESCRIPTION_CHARS: Final[int] = 40

MAX_FULL_DESCRIPTION_CHARS: Final[int] = 4_000
MAX_CAPABILITY_CHARS: Final[int] = 300
MAX_USE_CASE_CHARS: Final[int] = 300
MAX_GUIDE_SEED_CHARS: Final[int] = 2_000

MAX_CAPABILITIES: Final[int] = 12
MAX_USE_CASES: Final[int] = 12
MAX_WARNINGS: Final[int] = 100
MAX_ERRORS: Final[int] = 100

DEFAULT_MIN_EVIDENCE_CONFIDENCE: Final[float] = 0.50
DEFAULT_STRONG_EVIDENCE_CONFIDENCE: Final[float] = 0.80

SENTENCE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<=[.!?])\s+"
)

WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")

URL_RE: Final[re.Pattern[str]] = re.compile(
    r"https?://\S+",
    re.IGNORECASE,
)


# ============================================================
# Enumerations
# ============================================================

class ContentField(str, Enum):
    SHORT_DESCRIPTION = "short_description"
    FULL_DESCRIPTION = "full_description"
    CAPABILITIES = "capabilities"
    USE_CASES = "use_cases"
    BEGINNER_NOTE = "beginner_note"
    GUIDE_SEED = "guide_seed"


class ContentStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FALLBACK = "fallback"
    REVIEW = "review"
    FAILED = "failed"


class ContentSourceKind(str, Enum):
    FDROID = "fdroid"
    README = "readme"
    REPOSITORY = "repository"
    WEBSITE = "website"
    RELEASE = "release"
    MANIFEST = "manifest"
    EXISTING = "existing"
    OTHER = "other"


class GeneratorKind(str, Enum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    MANUAL = "manual"


class EvidenceState(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


# ============================================================
# Evidence model
# ============================================================

@dataclass(frozen=True, slots=True)
class ContentEvidence:
    source_name: str
    source_type: SourceType
    source_kind: ContentSourceKind
    source_url: str | None
    text: str
    confidence: float
    captured_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    note: str | None = None

    def validate(self) -> None:
        if not self.source_name.strip():
            raise ValueError("Content evidence source name cannot be empty.")

        if not self.text.strip():
            raise ValueError("Content evidence text cannot be empty.")

        if len(self.text) > MAX_SINGLE_EVIDENCE_CHARS:
            raise ValueError("Content evidence text exceeds per-item limit.")

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                "Content evidence confidence must be between 0 and 1."
            )


@dataclass(slots=True)
class EvidenceCollection:
    items: list[ContentEvidence] = field(default_factory=list)
    rejected: int = 0
    duplicates: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return sum(len(item.text) for item in self.items)

    @property
    def strongest_confidence(self) -> float:
        if not self.items:
            return 0.0

        return max(item.confidence for item in self.items)

    def add_warning(self, message: str) -> None:
        if len(self.warnings) >= MAX_WARNINGS:
            return

        cleaned = sanitize_text(message, max_length=400)

        if cleaned and cleaned not in self.warnings:
            self.warnings.append(cleaned)


# ============================================================
# Content output models
# ============================================================

@dataclass(slots=True)
class GeneratedField:
    field: ContentField
    value: str | list[str] | None = None
    generator: GeneratorKind = GeneratorKind.DETERMINISTIC
    confidence: float = 0.0
    evidence_fingerprints: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def populated(self) -> bool:
        if self.value is None:
            return False

        if isinstance(self.value, str):
            return bool(self.value.strip())

        return bool(self.value)

    def add_warning(self, message: str) -> None:
        if len(self.warnings) >= MAX_WARNINGS:
            return

        cleaned = sanitize_text(message, max_length=400)

        if cleaned and cleaned not in self.warnings:
            self.warnings.append(cleaned)


@dataclass(slots=True)
class ContentPackage:
    app_name: str

    short_description: GeneratedField = field(
        default_factory=lambda: GeneratedField(
            field=ContentField.SHORT_DESCRIPTION
        )
    )

    full_description: GeneratedField = field(
        default_factory=lambda: GeneratedField(
            field=ContentField.FULL_DESCRIPTION
        )
    )

    capabilities: GeneratedField = field(
        default_factory=lambda: GeneratedField(
            field=ContentField.CAPABILITIES
        )
    )

    use_cases: GeneratedField = field(
        default_factory=lambda: GeneratedField(
            field=ContentField.USE_CASES
        )
    )

    beginner_note: GeneratedField = field(
        default_factory=lambda: GeneratedField(
            field=ContentField.BEGINNER_NOTE
        )
    )

    guide_seed: GeneratedField = field(
        default_factory=lambda: GeneratedField(
            field=ContentField.GUIDE_SEED
        )
    )

    status: ContentStatus = ContentStatus.PARTIAL

    evidence_count: int = 0
    evidence_chars: int = 0

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    finished_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        end_time = self.finished_at or datetime.now(timezone.utc)

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )

    @property
    def populated_fields(self) -> int:
        fields = (
            self.short_description,
            self.full_description,
            self.capabilities,
            self.use_cases,
            self.beginner_note,
            self.guide_seed,
        )

        return sum(
            1
            for field_result in fields
            if field_result.populated
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
# Content policy
# ============================================================

@dataclass(frozen=True, slots=True)
class ContentPolicy:
    generate_short_description: bool = True
    generate_full_description: bool = True
    generate_capabilities: bool = True
    generate_use_cases: bool = True
    generate_beginner_note: bool = True
    generate_guide_seed: bool = True

    evidence_required: bool = True
    do_not_reject_for_short_description: bool = True

    minimum_evidence_confidence: float = (
        DEFAULT_MIN_EVIDENCE_CONFIDENCE
    )

    strong_evidence_confidence: float = (
        DEFAULT_STRONG_EVIDENCE_CONFIDENCE
    )

    max_source_documents: int = 8
    max_evidence_chars: int = MAX_EVIDENCE_TEXT_CHARS

    short_description_max_chars: int = MAX_SHORT_DESCRIPTION_CHARS
    full_description_max_chars: int = MAX_FULL_DESCRIPTION_CHARS

    max_capabilities: int = 8
    max_use_cases: int = 8

    allow_ai: bool = True
    deterministic_fallback: bool = True

    def validate(self) -> None:
        if not 0.0 <= self.minimum_evidence_confidence <= 1.0:
            raise ValueError(
                "minimum_evidence_confidence must be between 0 and 1."
            )

        if not 0.0 <= self.strong_evidence_confidence <= 1.0:
            raise ValueError(
                "strong_evidence_confidence must be between 0 and 1."
            )

        if self.strong_evidence_confidence < self.minimum_evidence_confidence:
            raise ValueError(
                "strong_evidence_confidence cannot be lower than "
                "minimum_evidence_confidence."
            )

        if not 1 <= self.max_source_documents <= MAX_SOURCE_DOCUMENTS:
            raise ValueError(
                "max_source_documents outside allowed range."
            )

        if not 1_000 <= self.max_evidence_chars <= MAX_EVIDENCE_TEXT_CHARS:
            raise ValueError(
                "max_evidence_chars outside allowed range."
            )

        if not (
            MIN_SHORT_DESCRIPTION_CHARS
            <= self.short_description_max_chars
            <= 500
        ):
            raise ValueError(
                "short_description_max_chars outside allowed range."
            )

        if not 500 <= self.full_description_max_chars <= 20_000:
            raise ValueError(
                "full_description_max_chars outside allowed range."
            )

        if not 1 <= self.max_capabilities <= MAX_CAPABILITIES:
            raise ValueError(
                "max_capabilities outside allowed range."
            )

        if not 1 <= self.max_use_cases <= MAX_USE_CASES:
            raise ValueError(
                "max_use_cases outside allowed range."
            )


# ============================================================
# Optional AI adapter contracts
# ============================================================

@dataclass(frozen=True, slots=True)
class ContentGenerationRequest:
    app_name: str
    evidence_text: str
    requested_fields: tuple[ContentField, ...]
    max_short_chars: int
    max_full_chars: int
    max_capabilities: int
    max_use_cases: int


@dataclass(slots=True)
class AiGeneratedContent:
    short_description: str | None = None
    full_description: str | None = None
    capabilities: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    beginner_note: str | None = None
    guide_seed: str | None = None


class ContentGenerator(Protocol):
    name: str

    def generate(
        self,
        request: ContentGenerationRequest,
    ) -> AiGeneratedContent:
        ...


# ============================================================
# Text normalization
# ============================================================

def normalize_content_text(
    value: str,
    *,
    max_chars: int,
) -> str:
    value = value.replace("\x00", " ")

    value = URL_RE.sub("", value)

    value = WHITESPACE_RE.sub(" ", value).strip()

    if len(value) > max_chars:
        value = value[:max_chars].rstrip()

    return value


def normalize_list_item(
    value: str,
    *,
    max_chars: int,
) -> str:
    value = normalize_content_text(
        value,
        max_chars=max_chars,
    )

    value = re.sub(
        r"^[\-*•\d.)\s]+",
        "",
        value,
    ).strip()

    return value


# ============================================================
# Evidence fingerprint
# ============================================================

def content_evidence_fingerprint(
    evidence: ContentEvidence,
) -> str:
    raw = "|".join(
        (
            evidence.source_name.lower(),
            evidence.source_type.value,
            evidence.source_kind.value,
            (evidence.source_url or "").lower(),
            normalize_content_text(
                evidence.text,
                max_chars=MAX_SINGLE_EVIDENCE_CHARS,
            ).lower(),
        )
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# Evidence collection
# ============================================================

def collect_evidence(
    evidence_items: Iterable[ContentEvidence],
    *,
    policy: ContentPolicy,
) -> EvidenceCollection:
    policy.validate()

    collection = EvidenceCollection()

    fingerprints: set[str] = set()

    source_names: set[str] = set()

    for evidence in evidence_items:
        try:
            evidence.validate()

        except Exception as exc:
            collection.rejected += 1

            collection.add_warning(
                f"Rejected invalid content evidence: {sanitize_error(exc)}"
            )

            continue

        if evidence.confidence < policy.minimum_evidence_confidence:
            collection.rejected += 1
            continue

        fingerprint = content_evidence_fingerprint(evidence)

        if fingerprint in fingerprints:
            collection.duplicates += 1
            continue

        if (
            evidence.source_name not in source_names
            and len(source_names) >= policy.max_source_documents
        ):
            collection.rejected += 1
            continue

        remaining = (
            policy.max_evidence_chars
            - collection.total_chars
        )

        if remaining <= 0:
            collection.add_warning(
                "Content evidence character budget reached."
            )
            break

        text = normalize_content_text(
            evidence.text,
            max_chars=min(
                MAX_SINGLE_EVIDENCE_CHARS,
                remaining,
            ),
        )

        if not text:
            collection.rejected += 1
            continue

        normalized = ContentEvidence(
            source_name=evidence.source_name,
            source_type=evidence.source_type,
            source_kind=evidence.source_kind,
            source_url=evidence.source_url,
            text=text,
            confidence=evidence.confidence,
            captured_at=evidence.captured_at,
            note=evidence.note,
        )

        collection.items.append(normalized)

        fingerprints.add(
            content_evidence_fingerprint(normalized)
        )

        source_names.add(normalized.source_name)

        if len(collection.items) >= MAX_EVIDENCE_ITEMS:
            collection.add_warning(
                "Content evidence item limit reached."
            )
            break

    return collection


# ============================================================
# Evidence ordering
# ============================================================

SOURCE_KIND_PRIORITY: Final[Mapping[ContentSourceKind, int]] = {
    ContentSourceKind.FDROID: 10,
    ContentSourceKind.README: 20,
    ContentSourceKind.REPOSITORY: 30,
    ContentSourceKind.WEBSITE: 40,
    ContentSourceKind.RELEASE: 50,
    ContentSourceKind.MANIFEST: 60,
    ContentSourceKind.EXISTING: 70,
    ContentSourceKind.OTHER: 80,
}


def evidence_sort_key(
    evidence: ContentEvidence,
) -> tuple[float, int, str]:
    return (
        -evidence.confidence,
        SOURCE_KIND_PRIORITY[evidence.source_kind],
        evidence.source_name.lower(),
    )


def ordered_evidence(
    collection: EvidenceCollection,
) -> list[ContentEvidence]:
    return sorted(
        collection.items,
        key=evidence_sort_key,
    )


# ============================================================
# Sentence extraction
# ============================================================

def split_sentences(
    text: str,
) -> list[str]:
    text = normalize_content_text(
        text,
        max_chars=MAX_SINGLE_EVIDENCE_CHARS,
    )

    if not text:
        return []

    sentences = SENTENCE_SPLIT_RE.split(text)

    output: list[str] = []

    for sentence in sentences:
        sentence = normalize_content_text(
            sentence,
            max_chars=600,
        )

        if len(sentence) < 10:
            continue

        output.append(sentence)

    return output


def unique_sentences(
    evidence: Sequence[ContentEvidence],
) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []

    for item in evidence:
        for sentence in split_sentences(item.text):
            key = sentence.casefold()

            if key in seen:
                continue

            seen.add(key)
            output.append(sentence)

    return output


# ============================================================
# Short description fallback
# ============================================================

def deterministic_short_description(
    app_name: str,
    evidence: Sequence[ContentEvidence],
    *,
    max_chars: int,
) -> str:
    sentences = unique_sentences(evidence)

    if sentences:
        best = sentences[0]

        if len(best) <= max_chars:
            return best

        truncated = best[:max_chars].rstrip(" ,;:-")

        if truncated:
            return truncated

    return normalize_content_text(
        f"{app_name} is an open-source Android application.",
        max_chars=max_chars,
    )


# ============================================================
# Full description fallback
# ============================================================

def deterministic_full_description(
    app_name: str,
    evidence: Sequence[ContentEvidence],
    *,
    max_chars: int,
) -> str:
    sentences = unique_sentences(evidence)

    if not sentences:
        return normalize_content_text(
            (
                f"{app_name} is an open-source Android application. "
                "OSGuide could not obtain enough verified source text "
                "to produce a detailed description yet."
            ),
            max_chars=max_chars,
        )

    selected: list[str] = []

    current_chars = 0

    for sentence in sentences:
        projected = (
            current_chars
            + len(sentence)
            + (1 if selected else 0)
        )

        if projected > max_chars:
            continue

        selected.append(sentence)
        current_chars = projected

        if len(selected) >= 8:
            break

    if not selected:
        selected = [sentences[0][:max_chars]]

    return " ".join(selected).strip()


# ============================================================
# Capability heuristics
# ============================================================

CAPABILITY_HINTS: Final[tuple[tuple[str, str], ...]] = (
    ("download", "Download and manage supported content"),
    ("stream", "Stream supported media or content"),
    ("terminal", "Work with command-line and terminal tools"),
    ("ssh", "Connect to remote systems using SSH-related workflows"),
    ("sync", "Synchronize supported data"),
    ("backup", "Create or manage backups"),
    ("encrypt", "Encrypt supported data"),
    ("decrypt", "Decrypt supported data"),
    ("password", "Manage password-related workflows"),
    ("camera", "Use camera-related functionality"),
    ("photo", "Work with photos and images"),
    ("image", "Work with image-based content"),
    ("audio", "Work with audio content"),
    ("music", "Work with music-related content"),
    ("video", "Work with video content"),
    ("reader", "Read supported documents or content"),
    ("pdf", "Work with PDF documents"),
    ("browser", "Browse web content"),
    ("maps", "Use map-related functionality"),
    ("navigation", "Use navigation-related functionality"),
    ("note", "Create or manage notes"),
    ("calendar", "Manage calendar-related information"),
    ("contact", "Work with contact information"),
    ("file", "Manage supported files"),
    ("share", "Share supported content"),
    ("privacy", "Use privacy-focused functionality"),
    ("firewall", "Control supported network traffic"),
    ("dns", "Manage DNS-related functionality"),
    ("vpn", "Use VPN-related networking"),
    ("repository", "Work with source-code repositories"),
    ("git", "Work with Git repositories"),
)


def deterministic_capabilities(
    evidence: Sequence[ContentEvidence],
    *,
    max_items: int,
) -> list[str]:
    combined = " ".join(
        item.text.lower()
        for item in evidence
    )

    output: list[str] = []

    for keyword, capability in CAPABILITY_HINTS:
        if keyword not in combined:
            continue

        if capability in output:
            continue

        output.append(capability)

        if len(output) >= max_items:
            break

    return output


# ============================================================
# Use case heuristics
# ============================================================

USE_CASE_HINTS: Final[tuple[tuple[str, str], ...]] = (
    ("terminal", "Use Android as a portable command-line environment"),
    ("ssh", "Access and manage remote systems from Android"),
    ("download", "Save supported content for later access"),
    ("backup", "Protect important data with backup workflows"),
    ("encrypt", "Protect supported information with encryption"),
    ("password", "Organize password-related workflows"),
    ("photo", "Manage image and photo workflows"),
    ("video", "Handle video-related workflows"),
    ("audio", "Handle audio-related workflows"),
    ("reader", "Read supported content on Android"),
    ("pdf", "Read or manage PDF documents"),
    ("note", "Capture and organize notes"),
    ("calendar", "Organize schedules and calendar information"),
    ("file", "Manage files directly on Android"),
    ("privacy", "Use an open-source privacy-focused alternative"),
    ("git", "Work with source code and Git repositories"),
    ("repository", "Inspect or manage source-code repositories"),
    ("vpn", "Use supported private-network workflows"),
    ("maps", "Use supported mapping workflows"),
)


def deterministic_use_cases(
    evidence: Sequence[ContentEvidence],
    *,
    max_items: int,
) -> list[str]:
    combined = " ".join(
        item.text.lower()
        for item in evidence
    )

    output: list[str] = []

    for keyword, use_case in USE_CASE_HINTS:
        if keyword not in combined:
            continue

        if use_case in output:
            continue

        output.append(use_case)

        if len(output) >= max_items:
            break

    return output


# ============================================================
# Beginner note
# ============================================================

def deterministic_beginner_note(
    app_name: str,
    capabilities: Sequence[str],
) -> str:
    if capabilities:
        return normalize_content_text(
            (
                f"{app_name} may include several features. "
                "Start with the function you need first and review "
                "the app's official documentation for advanced options."
            ),
            max_chars=500,
        )

    return normalize_content_text(
        (
            f"Start by exploring {app_name}'s main screen and official "
            "documentation before changing advanced settings."
        ),
        max_chars=500,
    )


# ============================================================
# Guide seed
# ============================================================

def deterministic_guide_seed(
    app_name: str,
    capabilities: Sequence[str],
    use_cases: Sequence[str],
) -> str:
    lines: list[str] = [
        f"Introduction to {app_name}",
        "What the application is designed to do",
    ]

    if capabilities:
        lines.append("Main capabilities:")

        for capability in capabilities[:6]:
            lines.append(f"- {capability}")

    if use_cases:
        lines.append("Practical use cases:")

        for use_case in use_cases[:6]:
            lines.append(f"- {use_case}")

    lines.extend(
        (
            "First steps for a new user",
            "Important settings and limitations",
            "Where to find official documentation",
        )
    )

    return normalize_content_text(
        "\n".join(lines),
        max_chars=MAX_GUIDE_SEED_CHARS,
    )


# ============================================================
# Evidence provenance
# ============================================================

def evidence_fingerprints(
    evidence: Sequence[ContentEvidence],
) -> list[str]:
    return [
        content_evidence_fingerprint(item)
        for item in evidence
    ]


# ============================================================
# Deterministic generator
# ============================================================

def generate_deterministic_content(
    app_name: str,
    evidence_collection: EvidenceCollection,
    *,
    policy: ContentPolicy,
) -> ContentPackage:
    policy.validate()

    package = ContentPackage(
        app_name=app_name,
    )

    evidence = ordered_evidence(
        evidence_collection
    )

    fingerprints = evidence_fingerprints(
        evidence
    )

    package.evidence_count = len(evidence)
    package.evidence_chars = evidence_collection.total_chars

    if policy.evidence_required and not evidence:
        package.add_warning(
            "No qualifying source evidence was available."
        )

    if policy.generate_short_description:
        short_description = deterministic_short_description(
            app_name,
            evidence,
            max_chars=policy.short_description_max_chars,
        )

        package.short_description.value = short_description
        package.short_description.generator = GeneratorKind.DETERMINISTIC
        package.short_description.confidence = (
            evidence_collection.strongest_confidence
            if evidence
            else 0.30
        )
        package.short_description.evidence_fingerprints = list(
            fingerprints
        )

    if policy.generate_full_description:
        full_description = deterministic_full_description(
            app_name,
            evidence,
            max_chars=policy.full_description_max_chars,
        )

        package.full_description.value = full_description
        package.full_description.generator = GeneratorKind.DETERMINISTIC
        package.full_description.confidence = (
            evidence_collection.strongest_confidence
            if evidence
            else 0.30
        )
        package.full_description.evidence_fingerprints = list(
            fingerprints
        )

    capabilities: list[str] = []

    if policy.generate_capabilities:
        capabilities = deterministic_capabilities(
            evidence,
            max_items=policy.max_capabilities,
        )

        package.capabilities.value = capabilities
        package.capabilities.generator = GeneratorKind.DETERMINISTIC
        package.capabilities.confidence = (
            evidence_collection.strongest_confidence
            if capabilities
            else 0.0
        )
        package.capabilities.evidence_fingerprints = list(
            fingerprints
        )

    use_cases: list[str] = []

    if policy.generate_use_cases:
        use_cases = deterministic_use_cases(
            evidence,
            max_items=policy.max_use_cases,
        )

        package.use_cases.value = use_cases
        package.use_cases.generator = GeneratorKind.DETERMINISTIC
        package.use_cases.confidence = (
            evidence_collection.strongest_confidence
            if use_cases
            else 0.0
        )
        package.use_cases.evidence_fingerprints = list(
            fingerprints
        )

    if policy.generate_beginner_note:
        package.beginner_note.value = deterministic_beginner_note(
            app_name,
            capabilities,
        )
        package.beginner_note.generator = GeneratorKind.DETERMINISTIC
        package.beginner_note.confidence = 0.60
        package.beginner_note.evidence_fingerprints = list(
            fingerprints
        )

    if policy.generate_guide_seed:
        package.guide_seed.value = deterministic_guide_seed(
            app_name,
            capabilities,
            use_cases,
        )
        package.guide_seed.generator = GeneratorKind.DETERMINISTIC
        package.guide_seed.confidence = 0.60
        package.guide_seed.evidence_fingerprints = list(
            fingerprints
        )

    package.status = evaluate_content_status(
        package,
        policy=policy,
    )

    package.finished_at = datetime.now(timezone.utc)

    return package


# ============================================================
# AI request construction
# ============================================================

def requested_content_fields(
    policy: ContentPolicy,
) -> tuple[ContentField, ...]:
    mapping = (
        (
            ContentField.SHORT_DESCRIPTION,
            policy.generate_short_description,
        ),
        (
            ContentField.FULL_DESCRIPTION,
            policy.generate_full_description,
        ),
        (
            ContentField.CAPABILITIES,
            policy.generate_capabilities,
        ),
        (
            ContentField.USE_CASES,
            policy.generate_use_cases,
        ),
        (
            ContentField.BEGINNER_NOTE,
            policy.generate_beginner_note,
        ),
        (
            ContentField.GUIDE_SEED,
            policy.generate_guide_seed,
        ),
    )

    return tuple(
        content_field
        for content_field, enabled in mapping
        if enabled
    )


def evidence_as_ai_text(
    collection: EvidenceCollection,
    *,
    max_chars: int,
) -> str:
    blocks: list[str] = []

    current = 0

    for item in ordered_evidence(collection):
        block = (
            f"[Source: {item.source_name} | "
            f"Type: {item.source_kind.value} | "
            f"Confidence: {item.confidence:.2f}]\n"
            f"{item.text}"
        )

        if current + len(block) > max_chars:
            break

        blocks.append(block)
        current += len(block)

    return "\n\n".join(blocks)


def build_ai_request(
    app_name: str,
    collection: EvidenceCollection,
    *,
    policy: ContentPolicy,
) -> ContentGenerationRequest:
    return ContentGenerationRequest(
        app_name=app_name,
        evidence_text=evidence_as_ai_text(
            collection,
            max_chars=policy.max_evidence_chars,
        ),
        requested_fields=requested_content_fields(policy),
        max_short_chars=policy.short_description_max_chars,
        max_full_chars=policy.full_description_max_chars,
        max_capabilities=policy.max_capabilities,
        max_use_cases=policy.max_use_cases,
    )


# ============================================================
# AI output validation
# ============================================================

def validate_ai_short_description(
    value: str | None,
    *,
    policy: ContentPolicy,
) -> str | None:
    if value is None:
        return None

    value = normalize_content_text(
        value,
        max_chars=policy.short_description_max_chars,
    )

    return value or None


def validate_ai_full_description(
    value: str | None,
    *,
    policy: ContentPolicy,
) -> str | None:
    if value is None:
        return None

    value = normalize_content_text(
        value,
        max_chars=policy.full_description_max_chars,
    )

    return value or None


def validate_ai_list(
    values: Sequence[str],
    *,
    max_items: int,
    max_chars: int,
) -> list[str]:
    output: list[str] = []

    seen: set[str] = set()

    for value in values:
        cleaned = normalize_list_item(
            value,
            max_chars=max_chars,
        )

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        output.append(cleaned)

        if len(output) >= max_items:
            break

    return output


# ============================================================
# Evidence-grounding checks
# ============================================================

def tokenize_for_grounding(
    value: str,
) -> set[str]:
    tokens = re.findall(
        r"[A-Za-z0-9][A-Za-z0-9+._-]{2,}",
        value.lower(),
    )

    stopwords = {
        "this",
        "that",
        "with",
        "from",
        "into",
        "your",
        "their",
        "there",
        "where",
        "which",
        "application",
        "android",
        "open",
        "source",
    }

    return {
        token
        for token in tokens
        if token not in stopwords
    }


def grounding_overlap(
    generated_text: str,
    evidence_text: str,
) -> float:
    generated_tokens = tokenize_for_grounding(
        generated_text
    )

    if not generated_tokens:
        return 1.0

    evidence_tokens = tokenize_for_grounding(
        evidence_text
    )

    overlap = (
        generated_tokens
        & evidence_tokens
    )

    return len(overlap) / len(generated_tokens)


def ai_text_is_grounded(
    generated_text: str,
    evidence_text: str,
    *,
    minimum_overlap: float = 0.20,
) -> bool:
    return (
        grounding_overlap(
            generated_text,
            evidence_text,
        )
        >= minimum_overlap
    )


# ============================================================
# AI merge logic
# ============================================================

def apply_ai_content(
    package: ContentPackage,
    ai_content: AiGeneratedContent,
    collection: EvidenceCollection,
    *,
    policy: ContentPolicy,
    generator_name: str,
) -> None:
    evidence_text = evidence_as_ai_text(
        collection,
        max_chars=policy.max_evidence_chars,
    )

    fingerprints = evidence_fingerprints(
        ordered_evidence(collection)
    )

    short_description = validate_ai_short_description(
        ai_content.short_description,
        policy=policy,
    )

    if short_description:
        if ai_text_is_grounded(
            short_description,
            evidence_text,
        ):
            package.short_description.value = short_description
            package.short_description.generator = GeneratorKind.AI
            package.short_description.confidence = max(
                0.60,
                collection.strongest_confidence,
            )
            package.short_description.evidence_fingerprints = list(
                fingerprints
            )
        else:
            package.short_description.add_warning(
                f"AI output from {generator_name} failed grounding check."
            )

    full_description = validate_ai_full_description(
        ai_content.full_description,
        policy=policy,
    )

    if full_description:
        if ai_text_is_grounded(
            full_description,
            evidence_text,
        ):
            package.full_description.value = full_description
            package.full_description.generator = GeneratorKind.AI
            package.full_description.confidence = max(
                0.60,
                collection.strongest_confidence,
            )
            package.full_description.evidence_fingerprints = list(
                fingerprints
            )
        else:
            package.full_description.add_warning(
                f"AI output from {generator_name} failed grounding check."
            )

    capabilities = validate_ai_list(
        ai_content.capabilities,
        max_items=policy.max_capabilities,
        max_chars=MAX_CAPABILITY_CHARS,
    )

    grounded_capabilities = [
        item
        for item in capabilities
        if ai_text_is_grounded(
            item,
            evidence_text,
            minimum_overlap=0.15,
        )
    ]

    if grounded_capabilities:
        package.capabilities.value = grounded_capabilities
        package.capabilities.generator = GeneratorKind.AI
        package.capabilities.confidence = max(
            0.60,
            collection.strongest_confidence,
        )
        package.capabilities.evidence_fingerprints = list(
            fingerprints
        )

    use_cases = validate_ai_list(
        ai_content.use_cases,
        max_items=policy.max_use_cases,
        max_chars=MAX_USE_CASE_CHARS,
    )

    grounded_use_cases = [
        item
        for item in use_cases
        if ai_text_is_grounded(
            item,
            evidence_text,
            minimum_overlap=0.10,
        )
    ]

    if grounded_use_cases:
        package.use_cases.value = grounded_use_cases
        package.use_cases.generator = GeneratorKind.AI
        package.use_cases.confidence = max(
            0.55,
            collection.strongest_confidence,
        )
        package.use_cases.evidence_fingerprints = list(
            fingerprints
        )

    beginner_note = normalize_content_text(
        ai_content.beginner_note or "",
        max_chars=500,
    )

    if beginner_note:
        package.beginner_note.value = beginner_note
        package.beginner_note.generator = GeneratorKind.AI
        package.beginner_note.confidence = 0.55
        package.beginner_note.evidence_fingerprints = list(
            fingerprints
        )

    guide_seed = normalize_content_text(
        ai_content.guide_seed or "",
        max_chars=MAX_GUIDE_SEED_CHARS,
    )

    if guide_seed:
        package.guide_seed.value = guide_seed
        package.guide_seed.generator = GeneratorKind.AI
        package.guide_seed.confidence = 0.55
        package.guide_seed.evidence_fingerprints = list(
            fingerprints
        )


# ============================================================
# Status evaluation
# ============================================================

def evaluate_content_status(
    package: ContentPackage,
    *,
    policy: ContentPolicy,
) -> ContentStatus:
    if package.errors and package.populated_fields == 0:
        return ContentStatus.FAILED

    short_ok = (
        not policy.generate_short_description
        or package.short_description.populated
    )

    full_ok = (
        not policy.generate_full_description
        or package.full_description.populated
    )

    if short_ok and full_ok:
        if package.populated_fields >= 4:
            return ContentStatus.COMPLETE

        return ContentStatus.PARTIAL

    if package.populated_fields > 0:
        return ContentStatus.PARTIAL

    return ContentStatus.REVIEW


# ============================================================
# Main Content Intelligence orchestration
# ============================================================

def build_content_package(
    app_name: str,
    evidence_items: Iterable[ContentEvidence],
    *,
    policy: ContentPolicy | None = None,
    ai_generator: ContentGenerator | None = None,
) -> ContentPackage:
    if policy is None:
        policy = ContentPolicy()

    policy.validate()

    collection = collect_evidence(
        evidence_items,
        policy=policy,
    )

    package = generate_deterministic_content(
        app_name,
        collection,
        policy=policy,
    )

    for warning in collection.warnings:
        package.add_warning(warning)

    if (
        ai_generator is not None
        and policy.allow_ai
        and collection.items
    ):
        try:
            request = build_ai_request(
                app_name,
                collection,
                policy=policy,
            )

            generated = ai_generator.generate(
                request
            )

            if not isinstance(
                generated,
                AiGeneratedContent,
            ):
                raise TypeError(
                    "ContentGenerator must return AiGeneratedContent."
                )

            apply_ai_content(
                package,
                generated,
                collection,
                policy=policy,
                generator_name=getattr(
                    ai_generator,
                    "name",
                    "unknown-ai-generator",
                ),
            )

        except Exception as exc:
            package.add_warning(
                "AI content generation failed; deterministic fallback "
                f"was preserved: {sanitize_error(exc)}"
            )

    package.status = evaluate_content_status(
        package,
        policy=policy,
    )

    package.finished_at = datetime.now(
        timezone.utc
    )

    return package


# ============================================================
# Diagnostic evidence
# ============================================================

def diagnostic_content_evidence() -> list[ContentEvidence]:
    return [
        ContentEvidence(
            source_name="diagnostic-readme",
            source_type=SourceType.GITHUB,
            source_kind=ContentSourceKind.README,
            source_url="https://github.com/",
            text=(
                "OSGuide Diagnostic App is an open-source Android tool "
                "used for testing. It can manage files, work with Git "
                "repositories, create backups, and support privacy-focused "
                "workflows. The diagnostic application exists only to "
                "verify OSGuide content processing."
            ),
            confidence=0.95,
            note="Synthetic local diagnostic content.",
        ),
        ContentEvidence(
            source_name="diagnostic-fdroid",
            source_type=SourceType.FDROID,
            source_kind=ContentSourceKind.FDROID,
            source_url="https://f-droid.org/",
            text=(
                "A diagnostic open-source Android application used to test "
                "description generation, capability extraction, use cases, "
                "and source evidence handling."
            ),
            confidence=0.95,
            note="Synthetic local diagnostic content.",
        ),
    ]


# ============================================================
# Diagnostic AI generator
# ============================================================

class DiagnosticContentGenerator:
    name = "diagnostic-ai"

    def generate(
        self,
        request: ContentGenerationRequest,
    ) -> AiGeneratedContent:
        return AiGeneratedContent(
            short_description=(
                f"{request.app_name} is an open-source Android tool "
                "for file, Git, backup, and privacy-focused workflows."
            ),
            full_description=(
                f"{request.app_name} is an open-source Android tool used "
                "for file management, Git repository workflows, backups, "
                "and privacy-focused tasks. This diagnostic text is based "
                "only on the evidence supplied to the content generator."
            ),
            capabilities=[
                "Manage supported files",
                "Work with Git repositories",
                "Create or manage backups",
                "Use privacy-focused functionality",
            ],
            use_cases=[
                "Manage files directly on Android",
                "Work with source code and Git repositories",
                "Protect important data with backup workflows",
            ],
            beginner_note=(
                "Start with the main file and repository features before "
                "exploring advanced options."
            ),
            guide_seed=(
                "Introduction\n"
                "File management\n"
                "Git repository basics\n"
                "Backup workflows\n"
                "Privacy-related options"
            ),
        )


class DiagnosticFailingContentGenerator:
    name = "diagnostic-ai-failure"

    def generate(
        self,
        request: ContentGenerationRequest,
    ) -> AiGeneratedContent:
        del request

        raise RuntimeError(
            "Intentional AI content failure for diagnostics."
        )


# ============================================================
# Public diagnostics
# ============================================================

def run_content_diagnostic() -> ContentPackage:
    policy = ContentPolicy(
        generate_short_description=True,
        generate_full_description=True,
        generate_capabilities=True,
        generate_use_cases=True,
        generate_beginner_note=True,
        generate_guide_seed=True,
        evidence_required=True,
        do_not_reject_for_short_description=True,
        minimum_evidence_confidence=0.50,
        strong_evidence_confidence=0.80,
        max_source_documents=8,
        max_evidence_chars=40_000,
        short_description_max_chars=240,
        full_description_max_chars=4_000,
        max_capabilities=8,
        max_use_cases=8,
        allow_ai=False,
        deterministic_fallback=True,
    )

    return build_content_package(
        "OSGuide Diagnostic App",
        diagnostic_content_evidence(),
        policy=policy,
    )


def run_ai_content_diagnostic() -> ContentPackage:
    policy = ContentPolicy(
        allow_ai=True,
        deterministic_fallback=True,
    )

    return build_content_package(
        "OSGuide Diagnostic App",
        diagnostic_content_evidence(),
        policy=policy,
        ai_generator=DiagnosticContentGenerator(),
    )


def run_ai_failure_fallback_diagnostic() -> ContentPackage:
    policy = ContentPolicy(
        allow_ai=True,
        deterministic_fallback=True,
    )

    return build_content_package(
        "OSGuide Diagnostic App",
        diagnostic_content_evidence(),
        policy=policy,
        ai_generator=DiagnosticFailingContentGenerator(),
    )


# ============================================================
# Output helpers
# ============================================================

def generated_field_summary(
    field_result: GeneratedField,
) -> dict[str, object]:
    return {
        "field": field_result.field.value,
        "value": field_result.value,
        "generator": field_result.generator.value,
        "confidence": field_result.confidence,
        "evidence_count": len(
            field_result.evidence_fingerprints
        ),
        "warnings": list(field_result.warnings),
    }


def content_package_summary(
    package: ContentPackage,
) -> dict[str, object]:
    return {
        "app_name": package.app_name,
        "status": package.status.value,
        "duration_seconds": round(
            package.duration_seconds,
            3,
        ),
        "evidence_count": package.evidence_count,
        "evidence_chars": package.evidence_chars,
        "populated_fields": package.populated_fields,
        "short_description": generated_field_summary(
            package.short_description
        ),
        "full_description": generated_field_summary(
            package.full_description
        ),
        "capabilities": generated_field_summary(
            package.capabilities
        ),
        "use_cases": generated_field_summary(
            package.use_cases
        ),
        "beginner_note": generated_field_summary(
            package.beginner_note
        ),
        "guide_seed": generated_field_summary(
            package.guide_seed
        ),
        "warnings": list(package.warnings),
        "errors": list(package.errors),
    }


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "AiGeneratedContent",
    "CONTENT_COMPONENT",
    "CONTENT_SCHEMA_VERSION",
    "ContentEvidence",
    "ContentField",
    "ContentGenerationRequest",
    "ContentGenerator",
    "ContentPackage",
    "ContentPolicy",
    "ContentSourceKind",
    "ContentStatus",
    "DiagnosticContentGenerator",
    "DiagnosticFailingContentGenerator",
    "EvidenceCollection",
    "EvidenceState",
    "GeneratedField",
    "GeneratorKind",
    "apply_ai_content",
    "build_ai_request",
    "build_content_package",
    "collect_evidence",
    "content_evidence_fingerprint",
    "content_package_summary",
    "deterministic_beginner_note",
    "deterministic_capabilities",
    "deterministic_full_description",
    "deterministic_guide_seed",
    "deterministic_short_description",
    "deterministic_use_cases",
    "diagnostic_content_evidence",
    "evidence_as_ai_text",
    "evidence_fingerprints",
    "evaluate_content_status",
    "generated_field_summary",
    "grounding_overlap",
    "normalize_content_text",
    "normalize_list_item",
    "ordered_evidence",
    "requested_content_fields",
    "run_ai_content_diagnostic",
    "run_ai_failure_fallback_diagnostic",
    "run_content_diagnostic",
    "split_sentences",
    "tokenize_for_grounding",
    "unique_sentences",
    "validate_ai_full_description",
    "validate_ai_list",
    "validate_ai_short_description",
)
