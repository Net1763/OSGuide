"""
OSGuide Engine
Content Intelligence Layer

Purpose
-------
This module builds trustworthy user-facing application content from
verified source evidence.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Final, Iterable, Mapping, Protocol, Sequence

from discovery import SourceType, sanitize_error, sanitize_text


CONTENT_COMPONENT: Final[str] = "Content Intelligence"
CONTENT_SCHEMA_VERSION: Final[str] = "1"

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

SENTENCE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")
WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
URL_RE: Final[re.Pattern[str]] = re.compile(r"https?://\S+", re.IGNORECASE)


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


@dataclass(frozen=True, slots=True)
class ContentEvidence:
    source_name: str
    source_type: SourceType
    source_kind: ContentSourceKind
    source_url: str | None
    text: str
    confidence: float
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    note: str | None = None

    def validate(self) -> None:
        if not self.source_name.strip():
            raise ValueError("Content evidence source name cannot be empty.")
        if not self.text.strip():
            raise ValueError("Content evidence text cannot be empty.")
        if len(self.text) > MAX_SINGLE_EVIDENCE_CHARS:
            raise ValueError("Content evidence text exceeds per-item limit.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Content evidence confidence must be between 0 and 1.")


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


@dataclass(slots=True)
class ContentPackage:
    app_name: str
    short_description: GeneratedField = field(default_factory=lambda: GeneratedField(field=ContentField.SHORT_DESCRIPTION))
    full_description: GeneratedField = field(default_factory=lambda: GeneratedField(field=ContentField.FULL_DESCRIPTION))
    capabilities: GeneratedField = field(default_factory=lambda: GeneratedField(field=ContentField.CAPABILITIES))
    use_cases: GeneratedField = field(default_factory=lambda: GeneratedField(field=ContentField.USE_CASES))
    beginner_note: GeneratedField = field(default_factory=lambda: GeneratedField(field=ContentField.BEGINNER_NOTE))
    guide_seed: GeneratedField = field(default_factory=lambda: GeneratedField(field=ContentField.GUIDE_SEED))

    status: ContentStatus = ContentStatus.PARTIAL
    evidence_count: int = 0
    evidence_chars: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        end_time = self.finished_at or datetime.now(timezone.utc)
        return max(0.0, (end_time - self.started_at).total_seconds())

    @property
    def populated_fields(self) -> int:
        fields = (self.short_description, self.full_description, self.capabilities, self.use_cases, self.beginner_note, self.guide_seed)
        return sum(1 for field_result in fields if field_result.populated)

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
    minimum_evidence_confidence: float = DEFAULT_MIN_EVIDENCE_CONFIDENCE
    strong_evidence_confidence: float = DEFAULT_STRONG_EVIDENCE_CONFIDENCE
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
            raise ValueError("minimum_evidence_confidence must be between 0 and 1.")
        if not 0.0 <= self.strong_evidence_confidence <= 1.0:
            raise ValueError("strong_evidence_confidence must be between 0 and 1.")
        if self.strong_evidence_confidence < self.minimum_evidence_confidence:
            raise ValueError("strong_evidence_confidence cannot be lower than minimum_evidence_confidence.")
        if not 1 <= self.max_source_documents <= MAX_SOURCE_DOCUMENTS:
            raise ValueError("max_source_documents outside allowed range.")
        if not 1_000 <= self.max_evidence_chars <= MAX_EVIDENCE_TEXT_CHARS:
            raise ValueError("max_evidence_chars outside allowed range.")
        if not (MIN_SHORT_DESCRIPTION_CHARS <= self.short_description_max_chars <= 500):
            raise ValueError("short_description_max_chars outside allowed range.")
        if not 500 <= self.full_description_max_chars <= 20_000:
            raise ValueError("full_description_max_chars outside allowed range.")
        if not 1 <= self.max_capabilities <= MAX_CAPABILITIES:
            raise ValueError("max_capabilities outside allowed range.")
        if not 1 <= self.max_use_cases <= MAX_USE_CASES:
            raise ValueError("max_use_cases outside allowed range.")


def normalize_content_text(value: str, *, max_chars: int) -> str:
    value = value.replace("\x00", " ")
    value = URL_RE.sub("", value)
    value = WHITESPACE_RE.sub(" ", value).strip()
    if len(value) > max_chars:
        value = value[:max_chars].rstrip()
    return value


def normalize_list_item(value: str, *, max_chars: int) -> str:
    value = normalize_content_text(value, max_chars=max_chars)
    value = re.sub(r"^[\-*•\d.)\s]+", "", value).strip()
    return value


def content_evidence_fingerprint(evidence: ContentEvidence) -> str:
    raw = "|".join(
        (
            evidence.source_name.lower(),
            evidence.source_type.value,
            evidence.source_kind.value,
            (evidence.source_url or "").lower(),
            normalize_content_text(evidence.text, max_chars=MAX_SINGLE_EVIDENCE_CHARS).lower(),
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def collect_evidence(evidence_items: Iterable[ContentEvidence], *, policy: ContentPolicy) -> EvidenceCollection:
    policy.validate()
    collection = EvidenceCollection()
    fingerprints: set[str] = set()
    source_names: set[str] = set()

    for evidence in evidence_items:
        try:
            evidence.validate()
        except Exception as exc:
            collection.rejected += 1
            collection.add_warning(f"Rejected invalid content evidence: {sanitize_error(exc)}")
            continue

        if evidence.confidence < policy.minimum_evidence_confidence:
            collection.rejected += 1
            continue

        fingerprint = content_evidence_fingerprint(evidence)
        if fingerprint in fingerprints:
            collection.duplicates += 1
            continue

        if evidence.source_name not in source_names and len(source_names) >= policy.max_source_documents:
            collection.rejected += 1
            continue

        remaining = policy.max_evidence_chars - collection.total_chars
        if remaining <= 0:
            collection.add_warning("Content evidence character budget reached.")
            break

        text = normalize_content_text(evidence.text, max_chars=min(MAX_SINGLE_EVIDENCE_CHARS, remaining))
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
        fingerprints.add(content_evidence_fingerprint(normalized))
        source_names.add(normalized.source_name)

        if len(collection.items) >= MAX_EVIDENCE_ITEMS:
            collection.add_warning("Content evidence item limit reached.")
            break

    return collection


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


def evidence_sort_key(evidence: ContentEvidence) -> tuple[float, int, str]:
    return (-evidence.confidence, SOURCE_KIND_PRIORITY[evidence.source_kind], evidence.source_name.lower())


def ordered_evidence(collection: EvidenceCollection) -> list[ContentEvidence]:
    return sorted(collection.items, key=evidence_sort_key)


def split_sentences(text: str) -> list[str]:
    text = normalize_content_text(text, max_chars=MAX_SINGLE_EVIDENCE_CHARS)
    if not text:
        return []
    sentences = SENTENCE_SPLIT_RE.split(text)
    output: list[str] = []
    for sentence in sentences:
        sentence = normalize_content_text(sentence, max_chars=600)
        if len(sentence) < 10:
            continue
        output.append(sentence)
    return output


def unique_sentences(evidence: Sequence[ContentEvidence]) -> list[str]:
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


def deterministic_short_description(app_name: str, evidence: Sequence[ContentEvidence], *, max_chars: int) -> str:
    sentences = unique_sentences(evidence)
    if sentences:
        best = sentences[0]
        if len(best) <= max_chars:
            return best
        truncated = best[:max_chars].rstrip(" ,;:-")
        if truncated:
            return truncated
    return normalize_content_text(f"{app_name} is an open-source Android application.", max_chars=max_chars)


def deterministic_full_description(app_name: str, evidence: Sequence[ContentEvidence], *, max_chars: int) -> str:
    sentences = unique_sentences(evidence)
    if not sentences:
        return normalize_content_text(
            f"{app_name} is an open-source Android application. OSGuide could not obtain enough verified source text to produce a detailed description yet.",
            max_chars=max_chars,
        )

    selected: list[str] = []
    current_chars = 0

    for sentence in sentences:
        projected = current_chars + len(sentence) + (1 if selected else 0)
        if projected > max_chars:
            continue
        selected.append(sentence)
        current_chars = projected
        if len(selected) >= 8:
            break

    if not selected:
        selected = [sentences[0][:max_chars]]

    return " ".join(selected).strip()


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
    ("audio", "Work with audio content"),
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


def deterministic_capabilities(evidence: Sequence[ContentEvidence], *, max_items: int) -> list[str]:
    combined = " ".join(item.text.lower() for item in evidence)
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


def deterministic_use_cases(evidence: Sequence[ContentEvidence], *, max_items: int) -> list[str]:
    combined = " ".join(item.text.lower() for item in evidence)
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


def deterministic_beginner_note(app_name: str, capabilities: Sequence[str]) -> str:
    if capabilities:
        return normalize_content_text(
            f"{app_name} may include several features. Start with the function you need first and review the app's official documentation for advanced options.",
            max_chars=500,
        )
    return normalize_content_text(
        f"Start by exploring {app_name}'s main screen and official documentation before changing advanced settings.",
        max_chars=500,
    )


def deterministic_guide_seed(app_name: str, capabilities: Sequence[str], use_cases: Sequence[str]) -> str:
    lines: list[str] = [f"Introduction to {app_name}", "What the application is designed to do"]
    if capabilities:
        lines.append("Main capabilities:")
        for capability in capabilities[:6]:
            lines.append(f"- {capability}")
    if use_cases:
        lines.append("Practical use cases:")
        for use_case in use_cases[:6]:
            lines.append(f"- {use_case}")
    lines.extend(("First steps for a new user", "Important settings and limitations", "Where to find official documentation"))
    return normalize_content_text("\n".join(lines), max_chars=MAX_GUIDE_SEED_CHARS)


def evidence_fingerprints(evidence: Sequence[ContentEvidence]) -> list[str]:
    return [content_evidence_fingerprint(item) for item in evidence]


def generate_deterministic_content(app_name: str, evidence_collection: EvidenceCollection, *, policy: ContentPolicy) -> ContentPackage:
    policy.validate()
    package = ContentPackage(app_name=app_name)
    evidence = ordered_evidence(evidence_collection)
    fingerprints = evidence_fingerprints(evidence)
    package.evidence_count = len(evidence)
    package.evidence_chars = evidence_collection.total_chars

    if policy.evidence_required and not evidence:
        package.add_warning("No qualifying source evidence was available.")

    if policy.generate_short_description:
        short_description = deterministic_short_description(app_name, evidence, max_chars=policy.short_description_max_chars)
        package.short_description.value = short_description
        package.short_description.generator = GeneratorKind.DETERMINISTIC
        package.short_description.confidence = evidence_collection.strongest_confidence if evidence else 0.30
        package.short_description.evidence_fingerprints = list(fingerprints)

    if policy.generate_full_description:
        full_description = deterministic_full_description(app_name, evidence, max_chars=policy.full_description_max_chars)
        package.full_description.value = full_description
        package.full_description.generator = GeneratorKind.DETERMINISTIC
        package.full_description.confidence = evidence_collection.strongest_confidence if evidence else 0.30
        package.full_description.evidence_fingerprints = list(fingerprints)

    capabilities: list[str] = []
    if policy.generate_capabilities:
        capabilities = deterministic_capabilities(evidence, max_items=policy.max_capabilities)
        package.capabilities.value = capabilities
        package.capabilities.generator = GeneratorKind.DETERMINISTIC
        package.capabilities.confidence = evidence_collection.strongest_confidence if capabilities else 0.0
        package.capabilities.evidence_fingerprints = list(fingerprints)

    use_cases: list[str] = []
    if policy.generate_use_cases:
        use_cases = deterministic_use_cases(evidence, max_items=policy.max_use_cases)
        package.use_cases.value = use_cases
        package.use_cases.generator = GeneratorKind.DETERMINISTIC
        package.use_cases.confidence = evidence_collection.strongest_confidence if use_cases else 0.0
        package.use_cases.evidence_fingerprints = list(fingerprints)

    if policy.generate_beginner_note:
        package.beginner_note.value = deterministic_beginner_note(app_name, capabilities)
        package.beginner_note.generator = GeneratorKind.DETERMINISTIC
        package.beginner_note.confidence = 0.60
        package.beginner_note.evidence_fingerprints = list(fingerprints)

    if policy.generate_guide_seed:
        package.guide_seed.value = deterministic_guide_seed(app_name, capabilities, use_cases)
        package.guide_seed.generator = GeneratorKind.DETERMINISTIC
        package.guide_seed.confidence = 0.60
        package.guide_seed.evidence_fingerprints = list(fingerprints)

    package.status = evaluate_content_status(package, policy=policy)
    package.finished_at = datetime.now(timezone.utc)
    return package


def evaluate_content_status(package: ContentPackage, *, policy: ContentPolicy) -> ContentStatus:
    if package.errors and package.populated_fields == 0:
        return ContentStatus.FAILED

    short_ok = not policy.generate_short_description or package.short_description.populated
    full_ok = not policy.generate_full_description or package.full_description.populated

    if short_ok and full_ok:
        if package.populated_fields >= 4:
            return ContentStatus.COMPLETE
        return ContentStatus.PARTIAL

    if package.populated_fields > 0:
        return ContentStatus.PARTIAL

    return ContentStatus.REVIEW


def build_content_package(app_name: str, evidence_items: Iterable[ContentEvidence], *, policy: ContentPolicy | None = None, ai_generator: ContentGenerator | None = None) -> ContentPackage:
    if policy is None:
        policy = ContentPolicy()
    policy.validate()

    collection = collect_evidence(evidence_items, policy=policy)
    package = generate_deterministic_content(app_name, collection, policy=policy)

    for warning in collection.warnings:
        package.add_warning(warning)

    package.status = evaluate_content_status(package, policy=policy)
    package.finished_at = datetime.now(timezone.utc)
    return package


def run_live_content_intelligence(
    *,
    app_name: str,
    source_type: SourceType,
    source_url: str | None = None,
    short_description: str | None = None,
    full_description: str | None = None,
    confidence: float = 0.95,
) -> ContentPackage:
    cleaned_name = sanitize_text(app_name, max_length=300)
    if not cleaned_name:
        raise ValueError("Live Content Intelligence requires a non-empty app name.")

    bounded_confidence = max(0.0, min(1.0, float(confidence)))
    evidence: list[ContentEvidence] = []

    def add_evidence(label: str, value: str | None) -> None:
        if not value:
            return
        cleaned = sanitize_text(value, max_length=MAX_SINGLE_EVIDENCE_CHARS)
        if not cleaned:
            return
        evidence.append(
            ContentEvidence(
                source_name=label,
                source_type=source_type,
                source_kind=(ContentSourceKind.FDROID if source_type == SourceType.FDROID else ContentSourceKind.OTHER),
                source_url=source_url,
                text=cleaned,
                confidence=bounded_confidence,
                note="Source-backed text supplied by the live Resolver path.",
            )
        )

    add_evidence("resolver-short-description", short_description)
    add_evidence("resolver-full-description", full_description)

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
        max_evidence_chars=MAX_EVIDENCE_TEXT_CHARS,
        short_description_max_chars=MAX_SHORT_DESCRIPTION_CHARS,
        full_description_max_chars=MAX_FULL_DESCRIPTION_CHARS,
        max_capabilities=8,
        max_use_cases=8,
        allow_ai=False,
        deterministic_fallback=True,
    )

    package = build_content_package(cleaned_name, evidence, policy=policy, ai_generator=None)

    if not evidence:
        package.add_warning("Live Resolver supplied no qualifying textual evidence; deterministic fallback content was used.")

    package.status = evaluate_content_status(package, policy=policy)
    return package


def generated_field_summary(field_result: GeneratedField) -> dict[str, object]:
    return {
        "field": field_result.field.value,
        "value": field_result.value,
        "generator": field_result.generator.value,
        "confidence": field_result.confidence,
        "evidence_count": len(field_result.evidence_fingerprints),
        "warnings": list(field_result.warnings),
    }


def content_package_summary(package: ContentPackage) -> dict[str, object]:
    return {
        "app_name": package.app_name,
        "status": package.status.value,
        "duration_seconds": round(package.duration_seconds, 3),
        "evidence_count": package.evidence_count,
        "evidence_chars": package.evidence_chars,
        "populated_fields": package.populated_fields,
        "short_description": generated_field_summary(package.short_description),
        "full_description": generated_field_summary(package.full_description),
        "capabilities": generated_field_summary(package.capabilities),
        "use_cases": generated_field_summary(package.use_cases),
        "beginner_note": generated_field_summary(package.beginner_note),
        "guide_seed": generated_field_summary(package.guide_seed),
        "warnings": list(package.warnings),
        "errors": list(package.errors),
    }
