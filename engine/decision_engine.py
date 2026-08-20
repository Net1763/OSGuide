"""
OSGuide Engine
Decision Engine

Purpose
-------
This module combines the outputs of Discovery, Super Resolver,
APK Intelligence, Content Intelligence and existing-backend state
into one controlled recommendation for the Publisher.

The Decision Engine does not perform external writes. It decides only:
- INSERT
- UPDATE
- REPAIR
- SKIP
- REVIEW

Core guarantees
---------------
1. Admin authority always wins.
2. An active Admin tombstone blocks automatic republishing.
3. Missing descriptive prose alone never rejects an otherwise valid app.
4. Package identity conflicts are high-risk and require REVIEW.
5. APK conflicts are high-risk and require REVIEW.
6. A missing APK can trigger REPAIR/REVIEW rather than invention.
7. New applications require stronger evidence than routine repairs.
8. The engine may continue with partial metadata when safe.
9. A low-confidence candidate is never silently published.
10. AI-generated content never upgrades identity confidence.
11. Existing manually managed fields are protected later by Publisher.
12. Decision reasons are structured and auditable.
13. No deletion action exists in this engine.
14. No network calls are performed here.
15. No secret values are handled here.
16. Decision scores are bounded and deterministic.
17. Thresholds are centralized in DecisionPolicy.
18. One failed application does not stop the entire batch.
19. Existing-app health issues are distinguished from new-app discovery.
20. Publisher remains the final write safety boundary.

The module intentionally contains the full decision framework rather than
a tiny if/else chain so later engine stages can be extended without
breaking current behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Final, Iterable, Mapping, Sequence

from discovery import AppCandidate
from resolver import (
    MetadataField,
    ResolvedApplication,
    ResolutionStatus,
)
from apk_intelligence import (
    ApkArtifact,
    ApkSelectionReport,
    SelectionStatus,
    VerificationState,
)
from content_intelligence import (
    ContentPackage,
    ContentStatus,
)
from publisher import (
    ApplicationPayload,
    ExistingApplication,
    FieldOwnership,
    PublicationAction,
    PublicationRequest,
    TombstoneState,
)


# ============================================================
# Identity
# ============================================================

DECISION_COMPONENT: Final[str] = "Decision Engine"
DECISION_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Enums
# ============================================================

class DecisionKind(str, Enum):
    NEW_APPLICATION = "new-application"
    EXISTING_UPDATE = "existing-update"
    EXISTING_REPAIR = "existing-repair"
    NO_CHANGE = "no-change"
    MANUAL_REVIEW = "manual-review"
    BLOCKED = "blocked"


class DecisionSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    SECURITY = "security"


class DecisionReasonCode(str, Enum):
    NEW_APP_READY = "new-app-ready"
    EXISTING_APP_UPDATE = "existing-app-update"
    EXISTING_APP_REPAIR = "existing-app-repair"
    NO_MEANINGFUL_CHANGE = "no-meaningful-change"

    ADMIN_TOMBSTONE = "admin-tombstone"
    ADMIN_STATE_UNKNOWN = "admin-state-unknown"

    PACKAGE_ID_MISSING = "package-id-missing"
    PACKAGE_ID_CONFLICT = "package-id-conflict"
    PACKAGE_ID_VERIFICATION_FAILED = "package-id-verification-failed"

    APK_MISSING = "apk-missing"
    APK_INVALID = "apk-invalid"
    APK_PACKAGE_MISMATCH = "apk-package-mismatch"
    APK_VERSION_MISMATCH = "apk-version-mismatch"

    SOURCE_CONFIDENCE_LOW = "source-confidence-low"
    RESOLUTION_CONFLICT = "resolution-conflict"
    RESOLUTION_FAILED = "resolution-failed"

    CONTENT_PARTIAL = "content-partial"
    CONTENT_FAILED = "content-failed"
    SHORT_DESCRIPTION_ONLY = "short-description-only"

    LICENSE_MISSING = "license-missing"
    VERSION_MISSING = "version-missing"
    REPOSITORY_MISSING = "repository-missing"

    SCORE_TOO_LOW = "score-too-low"
    REVIEW_THRESHOLD = "review-threshold"
    AUTO_THRESHOLD = "auto-threshold"

    EXISTING_RECORD_MISSING = "existing-record-missing"
    EXISTING_RECORD_PRESENT = "existing-record-present"

    MANUAL_FIELDS_PRESENT = "manual-fields-present"
    SAFE_PARTIAL_METADATA = "safe-partial-metadata"


class AppHealthState(str, Enum):
    HEALTHY = "healthy"
    NEEDS_UPDATE = "needs-update"
    NEEDS_REPAIR = "needs-repair"
    REVIEW = "review"
    UNKNOWN = "unknown"


# ============================================================
# Policy
# ============================================================

@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    """
    Central decision thresholds.

    Scores are normalized to 0..1.
    """

    auto_insert_threshold: float = 0.82
    auto_update_threshold: float = 0.78
    auto_repair_threshold: float = 0.72
    review_threshold: float = 0.55

    minimum_source_confidence: float = 0.50
    preferred_source_confidence: float = 0.80

    require_package_id_for_insert: bool = True
    require_apk_for_insert: bool = True

    require_version_for_insert: bool = True
    require_license_for_insert: bool = False
    require_repository_for_insert: bool = False

    allow_partial_content: bool = True
    short_description_never_blocks: bool = True

    block_on_package_conflict: bool = True
    block_on_apk_package_mismatch: bool = True

    review_on_apk_version_mismatch: bool = True
    review_on_resolution_conflict: bool = True

    admin_priority: bool = True
    respect_tombstones: bool = True
    fail_closed_on_unknown_admin_state: bool = True

    prefer_repair_over_update_when_broken: bool = True

    def validate(self) -> None:
        thresholds = (
            self.auto_insert_threshold,
            self.auto_update_threshold,
            self.auto_repair_threshold,
            self.review_threshold,
            self.minimum_source_confidence,
            self.preferred_source_confidence,
        )

        for value in thresholds:
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    "Decision threshold values must be between 0 and 1."
                )

        if self.review_threshold > self.auto_insert_threshold:
            raise ValueError(
                "review_threshold cannot exceed auto_insert_threshold."
            )

        if self.review_threshold > self.auto_update_threshold:
            raise ValueError(
                "review_threshold cannot exceed auto_update_threshold."
            )

        if self.review_threshold > self.auto_repair_threshold:
            raise ValueError(
                "review_threshold cannot exceed auto_repair_threshold."
            )

        if self.preferred_source_confidence < self.minimum_source_confidence:
            raise ValueError(
                "preferred_source_confidence cannot be lower than minimum."
            )

        if not self.admin_priority:
            raise ValueError(
                "Admin priority must remain enabled."
            )


# ============================================================
# Reason models
# ============================================================

@dataclass(frozen=True, slots=True)
class DecisionReason:
    code: DecisionReasonCode
    severity: DecisionSeverity
    message: str
    weight: float = 0.0
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ScoreBreakdown:
    source: float = 0.0
    identity: float = 0.0
    apk: float = 0.0
    metadata: float = 0.0
    content: float = 0.0
    admin: float = 0.0
    conflict_penalty: float = 0.0
    risk_penalty: float = 0.0

    @property
    def total(self) -> float:
        raw = (
            self.source
            + self.identity
            + self.apk
            + self.metadata
            + self.content
            + self.admin
            - self.conflict_penalty
            - self.risk_penalty
        )

        return max(0.0, min(1.0, raw))

    def as_dict(self) -> dict[str, float]:
        return {
            "source": round(self.source, 4),
            "identity": round(self.identity, 4),
            "apk": round(self.apk, 4),
            "metadata": round(self.metadata, 4),
            "content": round(self.content, 4),
            "admin": round(self.admin, 4),
            "conflict_penalty": round(self.conflict_penalty, 4),
            "risk_penalty": round(self.risk_penalty, 4),
            "total": round(self.total, 4),
        }


# ============================================================
# Input bundle
# ============================================================

@dataclass(slots=True)
class DecisionInput:
    candidate: AppCandidate
    resolution: ResolvedApplication | None
    apk: ApkSelectionReport | None
    content: ContentPackage | None

    existing: ExistingApplication | None = None

    run_id: str | None = None

    detected_broken_apk: bool = False
    detected_stale_version: bool = False
    detected_missing_icon: bool = False
    detected_missing_content: bool = False
    detected_broken_source_url: bool = False


# ============================================================
# Result model
# ============================================================

@dataclass(slots=True)
class DecisionResult:
    action: PublicationAction
    kind: DecisionKind
    confidence: float

    score: ScoreBreakdown

    reasons: list[DecisionReason] = field(default_factory=list)

    payload: ApplicationPayload | None = None

    health: AppHealthState = AppHealthState.UNKNOWN

    blocked: bool = False
    requires_review: bool = False

    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def add_reason(
        self,
        code: DecisionReasonCode,
        severity: DecisionSeverity,
        message: str,
        *,
        weight: float = 0.0,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.reasons.append(
            DecisionReason(
                code=code,
                severity=severity,
                message=message,
                weight=weight,
                details=dict(details or {}),
            )
        )

    @property
    def reason_text(self) -> str:
        if not self.reasons:
            return "No structured decision reason."

        return "; ".join(
            reason.message
            for reason in self.reasons
        )


# ============================================================
# Resolver helpers
# ============================================================

def resolved_value(
    resolution: ResolvedApplication | None,
    field_name: MetadataField,
) -> str | None:
    if resolution is None:
        return None

    item = resolution.fields.get(
        field_name
    )

    if item is None:
        return None

    return item.value


def resolved_confidence(
    resolution: ResolvedApplication | None,
    field_name: MetadataField,
) -> float:
    if resolution is None:
        return 0.0

    item = resolution.fields.get(
        field_name
    )

    if item is None:
        return 0.0

    return max(
        0.0,
        min(1.0, item.confidence),
    )


# ============================================================
# APK helpers
# ============================================================

def selected_apk(
    report: ApkSelectionReport | None,
) -> ApkArtifact | None:
    if report is None:
        return None

    return report.selected


def selected_apk_url(
    report: ApkSelectionReport | None,
) -> str | None:
    artifact = selected_apk(
        report
    )

    return artifact.url if artifact else None


def selected_version(
    report: ApkSelectionReport | None,
) -> str | None:
    artifact = selected_apk(
        report
    )

    return artifact.version if artifact else None


# ============================================================
# Content helpers
# ============================================================

def content_short(
    content: ContentPackage | None,
) -> str | None:
    if content is None:
        return None

    value = content.short_description.value

    if isinstance(value, str):
        return value

    return None


def content_full(
    content: ContentPackage | None,
) -> str | None:
    if content is None:
        return None

    value = content.full_description.value

    if isinstance(value, str):
        return value

    return None


# ============================================================
# Admin safeguards
# ============================================================

def admin_block_reason(
    existing: ExistingApplication | None,
    *,
    policy: DecisionPolicy,
) -> DecisionReason | None:
    if existing is None:
        return None

    if not policy.respect_tombstones:
        return None

    if existing.tombstone == TombstoneState.ACTIVE:
        return DecisionReason(
            code=DecisionReasonCode.ADMIN_TOMBSTONE,
            severity=DecisionSeverity.SECURITY,
            message=(
                "Admin deletion tombstone blocks automatic republishing."
            ),
            weight=-1.0,
        )

    if (
        existing.tombstone == TombstoneState.UNKNOWN
        and policy.fail_closed_on_unknown_admin_state
    ):
        return DecisionReason(
            code=DecisionReasonCode.ADMIN_STATE_UNKNOWN,
            severity=DecisionSeverity.SECURITY,
            message=(
                "Admin deletion state is unknown; automatic write requires review."
            ),
            weight=-0.8,
        )

    return None


def count_manual_fields(
    existing: ExistingApplication | None,
) -> int:
    if existing is None:
        return 0

    return sum(
        1
        for ownership in existing.managed_fields.values()
        if ownership == FieldOwnership.MANUAL
    )


# ============================================================
# Conflict helpers
# ============================================================

def has_package_conflict(
    resolution: ResolvedApplication | None,
) -> bool:
    if resolution is None:
        return False

    field_result = resolution.fields.get(
        MetadataField.PACKAGE_ID
    )

    if field_result is None:
        return False

    return bool(
        field_result.conflicts
    )


def has_high_resolution_conflict(
    resolution: ResolvedApplication | None,
) -> bool:
    if resolution is None:
        return False

    return (
        resolution.status
        == ResolutionStatus.CONFLICT
    )


def apk_package_mismatch(
    apk_report: ApkSelectionReport | None,
) -> bool:
    artifact = selected_apk(
        apk_report
    )

    if artifact is None:
        return False

    return (
        artifact.package_verification
        == VerificationState.MISMATCH
    )


def apk_version_mismatch(
    apk_report: ApkSelectionReport | None,
) -> bool:
    artifact = selected_apk(
        apk_report
    )

    if artifact is None:
        return False

    return (
        artifact.version_verification
        == VerificationState.MISMATCH
    )


# ============================================================
# Score calculation
# ============================================================

def score_source(
    data: DecisionInput,
    *,
    policy: DecisionPolicy,
) -> float:
    confidence = max(
        0.0,
        min(
            1.0,
            data.candidate.source_confidence,
        ),
    )

    if confidence < policy.minimum_source_confidence:
        return 0.02

    if confidence >= policy.preferred_source_confidence:
        return 0.16

    return 0.10


def score_identity(
    data: DecisionInput,
) -> float:
    package_id = (
        resolved_value(
            data.resolution,
            MetadataField.PACKAGE_ID,
        )
        or data.candidate.package_id
    )

    if not package_id:
        return 0.0

    confidence = max(
        resolved_confidence(
            data.resolution,
            MetadataField.PACKAGE_ID,
        ),
        data.candidate.source_confidence,
    )

    if confidence >= 0.90:
        return 0.24

    if confidence >= 0.75:
        return 0.20

    if confidence >= 0.60:
        return 0.14

    return 0.08


def score_apk(
    data: DecisionInput,
) -> float:
    artifact = selected_apk(
        data.apk
    )

    if artifact is None:
        return 0.0

    if data.apk is None:
        return 0.0

    if data.apk.status != SelectionStatus.SELECTED:
        return 0.0

    score = 0.18

    if artifact.package_verification == VerificationState.MATCH:
        score += 0.04

    if artifact.version_verification == VerificationState.MATCH:
        score += 0.03

    return min(
        0.25,
        score,
    )


def score_metadata(
    data: DecisionInput,
) -> float:
    values = (
        resolved_value(
            data.resolution,
            MetadataField.VERSION,
        )
        or selected_version(data.apk),
        resolved_value(
            data.resolution,
            MetadataField.LICENSE,
        ),
        resolved_value(
            data.resolution,
            MetadataField.REPOSITORY_URL,
        ),
        resolved_value(
            data.resolution,
            MetadataField.CATEGORY,
        ),
        resolved_value(
            data.resolution,
            MetadataField.ICON_URL,
        ),
    )

    present = sum(
        1
        for value in values
        if value
    )

    return min(
        0.16,
        present * 0.032,
    )


def score_content(
    data: DecisionInput,
) -> float:
    content = data.content

    if content is None:
        return 0.0

    if content.status == ContentStatus.COMPLETE:
        return 0.10

    if content.status in {
        ContentStatus.PARTIAL,
        ContentStatus.FALLBACK,
    }:
        return 0.06

    if (
        content.short_description.populated
        or content.full_description.populated
    ):
        return 0.03

    return 0.0


def score_admin_state(
    data: DecisionInput,
) -> float:
    if data.existing is None:
        return 0.02

    if data.existing.tombstone == TombstoneState.CLEAR:
        return 0.04

    return 0.0


def score_conflict_penalty(
    data: DecisionInput,
) -> float:
    penalty = 0.0

    if has_package_conflict(
        data.resolution
    ):
        penalty += 0.35

    elif has_high_resolution_conflict(
        data.resolution
    ):
        penalty += 0.20

    if apk_package_mismatch(
        data.apk
    ):
        penalty += 0.45

    if apk_version_mismatch(
        data.apk
    ):
        penalty += 0.18

    return min(
        0.80,
        penalty,
    )


def score_risk_penalty(
    data: DecisionInput,
    *,
    policy: DecisionPolicy,
) -> float:
    penalty = 0.0

    if (
        data.candidate.source_confidence
        < policy.minimum_source_confidence
    ):
        penalty += 0.18

    if (
        data.resolution is not None
        and data.resolution.status
        == ResolutionStatus.FAILED
    ):
        penalty += 0.20

    if (
        data.apk is not None
        and data.apk.status
        == SelectionStatus.FAILED
    ):
        penalty += 0.25

    return min(
        0.50,
        penalty,
    )


def calculate_score(
    data: DecisionInput,
    *,
    policy: DecisionPolicy,
) -> ScoreBreakdown:
    return ScoreBreakdown(
        source=score_source(
            data,
            policy=policy,
        ),
        identity=score_identity(
            data
        ),
        apk=score_apk(
            data
        ),
        metadata=score_metadata(
            data
        ),
        content=score_content(
            data
        ),
        admin=score_admin_state(
            data
        ),
        conflict_penalty=score_conflict_penalty(
            data
        ),
        risk_penalty=score_risk_penalty(
            data,
            policy=policy,
        ),
    )


# ============================================================
# Health classification
# ============================================================

def classify_existing_health(
    data: DecisionInput,
) -> AppHealthState:
    if data.existing is None:
        return AppHealthState.UNKNOWN

    if (
        data.detected_broken_apk
        or data.detected_broken_source_url
        or data.detected_missing_icon
        or data.detected_missing_content
    ):
        return AppHealthState.NEEDS_REPAIR

    if data.detected_stale_version:
        return AppHealthState.NEEDS_UPDATE

    if (
        data.resolution is not None
        and data.resolution.status
        == ResolutionStatus.CONFLICT
    ):
        return AppHealthState.REVIEW

    return AppHealthState.HEALTHY


# ============================================================
# Payload construction
# ============================================================

def build_payload(
    data: DecisionInput,
) -> ApplicationPayload:
    candidate = data.candidate

    package_id = (
        resolved_value(
            data.resolution,
            MetadataField.PACKAGE_ID,
        )
        or candidate.package_id
    )

    version = (
        selected_version(
            data.apk
        )
        or resolved_value(
            data.resolution,
            MetadataField.VERSION,
        )
    )

    apk_url = selected_apk_url(
        data.apk
    )

    repository_url = (
        resolved_value(
            data.resolution,
            MetadataField.REPOSITORY_URL,
        )
        or candidate.repository_url
    )

    source_url = (
        resolved_value(
            data.resolution,
            MetadataField.SOURCE_URL,
        )
        or candidate.source_url
    )

    name = (
        resolved_value(
            data.resolution,
            MetadataField.NAME,
        )
        or candidate.name
    )

    payload = ApplicationPayload(
        name=name,
        package_id=package_id,
        version=version,
        apk_url=apk_url,
        source_url=source_url,
        repository_url=repository_url,
        license=resolved_value(
            data.resolution,
            MetadataField.LICENSE,
        ),
        category=resolved_value(
            data.resolution,
            MetadataField.CATEGORY,
        ),
        short_description=content_short(
            data.content
        )
        or resolved_value(
            data.resolution,
            MetadataField.SHORT_DESCRIPTION,
        ),
        full_description=content_full(
            data.content
        )
        or resolved_value(
            data.resolution,
            MetadataField.FULL_DESCRIPTION,
        ),
        icon_url=resolved_value(
            data.resolution,
            MetadataField.ICON_URL,
        ),
        source=candidate.source_type,
        visible=True,
        extra={},
    )

    return payload


# ============================================================
# Requirement helpers
# ============================================================

def package_id_for(
    data: DecisionInput,
) -> str | None:
    return (
        resolved_value(
            data.resolution,
            MetadataField.PACKAGE_ID,
        )
        or data.candidate.package_id
    )


def version_for(
    data: DecisionInput,
) -> str | None:
    return (
        selected_version(
            data.apk
        )
        or resolved_value(
            data.resolution,
            MetadataField.VERSION,
        )
    )


def license_for(
    data: DecisionInput,
) -> str | None:
    return resolved_value(
        data.resolution,
        MetadataField.LICENSE,
    )


def repository_for(
    data: DecisionInput,
) -> str | None:
    return (
        resolved_value(
            data.resolution,
            MetadataField.REPOSITORY_URL,
        )
        or data.candidate.repository_url
    )


# ============================================================
# Hard safety evaluation
# ============================================================

def apply_hard_guards(
    result: DecisionResult,
    data: DecisionInput,
    *,
    policy: DecisionPolicy,
) -> bool:
    """
    Return True when a hard guard fully determines REVIEW/BLOCKED.
    """

    admin_reason = admin_block_reason(
        data.existing,
        policy=policy,
    )

    if admin_reason is not None:
        result.reasons.append(
            admin_reason
        )

        result.blocked = True
        result.requires_review = True
        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.BLOCKED
        result.confidence = 1.0

        return True

    if (
        policy.block_on_package_conflict
        and has_package_conflict(
            data.resolution
        )
    ):
        result.add_reason(
            DecisionReasonCode.PACKAGE_ID_CONFLICT,
            DecisionSeverity.SECURITY,
            (
                "Conflicting Package ID evidence requires manual review."
            ),
            weight=-1.0,
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True
        result.confidence = 1.0

        return True

    if (
        policy.block_on_apk_package_mismatch
        and apk_package_mismatch(
            data.apk
        )
    ):
        result.add_reason(
            DecisionReasonCode.APK_PACKAGE_MISMATCH,
            DecisionSeverity.SECURITY,
            (
                "Selected APK does not match the expected Package ID."
            ),
            weight=-1.0,
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True
        result.confidence = 1.0

        return True

    return False


# ============================================================
# New app decision
# ============================================================

def decide_new_application(
    result: DecisionResult,
    data: DecisionInput,
    *,
    policy: DecisionPolicy,
) -> DecisionResult:
    package_id = package_id_for(
        data
    )

    if (
        policy.require_package_id_for_insert
        and not package_id
    ):
        result.add_reason(
            DecisionReasonCode.PACKAGE_ID_MISSING,
            DecisionSeverity.HIGH,
            "New application has no verified Package ID.",
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True

        return result

    if (
        policy.require_apk_for_insert
        and selected_apk(data.apk) is None
    ):
        result.add_reason(
            DecisionReasonCode.APK_MISSING,
            DecisionSeverity.WARNING,
            (
                "No verified direct APK is available for the new application."
            ),
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True

        return result

    if (
        policy.require_version_for_insert
        and not version_for(data)
    ):
        result.add_reason(
            DecisionReasonCode.VERSION_MISSING,
            DecisionSeverity.WARNING,
            "New application has no resolved version.",
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True

        return result

    if (
        policy.require_license_for_insert
        and not license_for(data)
    ):
        result.add_reason(
            DecisionReasonCode.LICENSE_MISSING,
            DecisionSeverity.WARNING,
            "New application has no resolved license.",
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True

        return result

    if (
        policy.require_repository_for_insert
        and not repository_for(data)
    ):
        result.add_reason(
            DecisionReasonCode.REPOSITORY_MISSING,
            DecisionSeverity.WARNING,
            "New application has no resolved repository.",
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True

        return result

    if (
        data.candidate.source_confidence
        < policy.minimum_source_confidence
    ):
        result.add_reason(
            DecisionReasonCode.SOURCE_CONFIDENCE_LOW,
            DecisionSeverity.WARNING,
            "Discovery source confidence is below the automatic threshold.",
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True

        return result

    if (
        data.resolution is not None
        and data.resolution.status
        == ResolutionStatus.FAILED
    ):
        result.add_reason(
            DecisionReasonCode.RESOLUTION_FAILED,
            DecisionSeverity.WARNING,
            "Resolver failed to produce usable metadata.",
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True

        return result

    if (
        data.content is None
        or data.content.status
        in {
            ContentStatus.PARTIAL,
            ContentStatus.FALLBACK,
            ContentStatus.REVIEW,
        }
    ):
        result.add_reason(
            DecisionReasonCode.CONTENT_PARTIAL,
            DecisionSeverity.INFO,
            (
                "Content is partial; this alone does not block a valid application."
            ),
        )

    if result.score.total >= policy.auto_insert_threshold:
        result.action = PublicationAction.INSERT
        result.kind = DecisionKind.NEW_APPLICATION
        result.confidence = result.score.total

        result.add_reason(
            DecisionReasonCode.NEW_APP_READY,
            DecisionSeverity.INFO,
            "New application meets automatic publication requirements.",
            weight=0.5,
        )

        result.add_reason(
            DecisionReasonCode.AUTO_THRESHOLD,
            DecisionSeverity.INFO,
            "Automatic insert confidence threshold was met.",
            details={
                "score": result.score.total,
                "threshold": policy.auto_insert_threshold,
            },
        )

        return result

    if result.score.total >= policy.review_threshold:
        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True
        result.confidence = result.score.total

        result.add_reason(
            DecisionReasonCode.REVIEW_THRESHOLD,
            DecisionSeverity.WARNING,
            (
                "Application is plausible but below the automatic insert threshold."
            ),
            details={
                "score": result.score.total,
                "threshold": policy.auto_insert_threshold,
            },
        )

        return result

    result.action = PublicationAction.SKIP
    result.kind = DecisionKind.NO_CHANGE
    result.confidence = result.score.total

    result.add_reason(
        DecisionReasonCode.SCORE_TOO_LOW,
        DecisionSeverity.WARNING,
        "Candidate confidence is too low for automatic publication.",
        details={
            "score": result.score.total,
            "review_threshold": policy.review_threshold,
        },
    )

    return result


# ============================================================
# Existing app decision
# ============================================================

def decide_existing_application(
    result: DecisionResult,
    data: DecisionInput,
    *,
    policy: DecisionPolicy,
) -> DecisionResult:
    health = classify_existing_health(
        data
    )

    result.health = health

    manual_count = count_manual_fields(
        data.existing
    )

    if manual_count:
        result.add_reason(
            DecisionReasonCode.MANUAL_FIELDS_PRESENT,
            DecisionSeverity.INFO,
            (
                "Existing application contains Admin-managed fields; "
                "Publisher will preserve them."
            ),
            details={
                "manual_field_count": manual_count,
            },
        )

    if health == AppHealthState.HEALTHY:
        if not data.detected_stale_version:
            result.action = PublicationAction.SKIP
            result.kind = DecisionKind.NO_CHANGE
            result.confidence = max(
                0.80,
                result.score.total,
            )

            result.add_reason(
                DecisionReasonCode.NO_MEANINGFUL_CHANGE,
                DecisionSeverity.INFO,
                "Existing application appears healthy with no required change.",
            )

            return result

    if health == AppHealthState.NEEDS_REPAIR:
        if selected_apk(data.apk) is None and data.detected_broken_apk:
            result.action = PublicationAction.REVIEW
            result.kind = DecisionKind.MANUAL_REVIEW
            result.requires_review = True

            result.add_reason(
                DecisionReasonCode.APK_MISSING,
                DecisionSeverity.WARNING,
                (
                    "Existing application needs APK repair but no safe "
                    "replacement APK was resolved."
                ),
            )

            return result

        if result.score.total >= policy.auto_repair_threshold:
            result.action = PublicationAction.REPAIR
            result.kind = DecisionKind.EXISTING_REPAIR
            result.confidence = result.score.total

            result.add_reason(
                DecisionReasonCode.EXISTING_APP_REPAIR,
                DecisionSeverity.INFO,
                "Existing application qualifies for automatic repair.",
                details={
                    "score": result.score.total,
                    "threshold": policy.auto_repair_threshold,
                },
            )

            return result

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True
        result.confidence = result.score.total

        result.add_reason(
            DecisionReasonCode.REVIEW_THRESHOLD,
            DecisionSeverity.WARNING,
            "Repair evidence is insufficient for automatic repair.",
        )

        return result

    if health == AppHealthState.NEEDS_UPDATE:
        if result.score.total >= policy.auto_update_threshold:
            result.action = PublicationAction.UPDATE
            result.kind = DecisionKind.EXISTING_UPDATE
            result.confidence = result.score.total

            result.add_reason(
                DecisionReasonCode.EXISTING_APP_UPDATE,
                DecisionSeverity.INFO,
                "Existing application qualifies for automatic update.",
                details={
                    "score": result.score.total,
                    "threshold": policy.auto_update_threshold,
                },
            )

            return result

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True
        result.confidence = result.score.total

        result.add_reason(
            DecisionReasonCode.REVIEW_THRESHOLD,
            DecisionSeverity.WARNING,
            "Update evidence is insufficient for automatic update.",
        )

        return result

    if health == AppHealthState.REVIEW:
        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True

        result.add_reason(
            DecisionReasonCode.RESOLUTION_CONFLICT,
            DecisionSeverity.HIGH,
            "Existing application has conflicting resolution evidence.",
        )

        return result

    result.action = PublicationAction.REVIEW
    result.kind = DecisionKind.MANUAL_REVIEW
    result.requires_review = True

    result.add_reason(
        DecisionReasonCode.REVIEW_THRESHOLD,
        DecisionSeverity.WARNING,
        "Existing application health could not be classified safely.",
    )

    return result


# ============================================================
# Main decision function
# ============================================================

def decide(
    data: DecisionInput,
    *,
    policy: DecisionPolicy | None = None,
) -> DecisionResult:
    if policy is None:
        policy = DecisionPolicy()

    policy.validate()
    data.candidate.validate()

    score = calculate_score(
        data,
        policy=policy,
    )

    result = DecisionResult(
        action=PublicationAction.REVIEW,
        kind=DecisionKind.MANUAL_REVIEW,
        confidence=score.total,
        score=score,
        payload=None,
        health=AppHealthState.UNKNOWN,
        blocked=False,
        requires_review=False,
    )

    if apply_hard_guards(
        result,
        data,
        policy=policy,
    ):
        return result

    if (
        policy.review_on_apk_version_mismatch
        and apk_version_mismatch(data.apk)
    ):
        result.add_reason(
            DecisionReasonCode.APK_VERSION_MISMATCH,
            DecisionSeverity.HIGH,
            (
                "APK version conflicts with expected version; manual review required."
            ),
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True
        result.payload = build_payload(
            data
        )

        return result

    if (
        policy.review_on_resolution_conflict
        and has_high_resolution_conflict(
            data.resolution
        )
    ):
        result.add_reason(
            DecisionReasonCode.RESOLUTION_CONFLICT,
            DecisionSeverity.HIGH,
            "Resolver reported high-risk metadata conflicts.",
        )

        result.action = PublicationAction.REVIEW
        result.kind = DecisionKind.MANUAL_REVIEW
        result.requires_review = True
        result.payload = build_payload(
            data
        )

        return result

    result.payload = build_payload(
        data
    )

    if data.existing is None:
        return decide_new_application(
            result,
            data,
            policy=policy,
        )

    return decide_existing_application(
        result,
        data,
        policy=policy,
    )


# ============================================================
# Publication request conversion
# ============================================================

def to_publication_request(
    decision: DecisionResult,
    *,
    run_id: str | None = None,
    candidate_identity: str | None = None,
) -> PublicationRequest:
    if decision.payload is None:
        raise ValueError(
            "Decision has no publication payload."
        )

    return PublicationRequest(
        action=decision.action,
        payload=decision.payload,
        expected_existing=(
            decision.kind
            in {
                DecisionKind.EXISTING_UPDATE,
                DecisionKind.EXISTING_REPAIR,
                DecisionKind.NO_CHANGE,
            }
        ),
        decision_confidence=decision.confidence,
        decision_reason=decision.reason_text,
        run_id=run_id,
        candidate_identity=candidate_identity,
    )


# ============================================================
# Batch decision
# ============================================================

@dataclass(slots=True)
class DecisionBatchReport:
    started_at: datetime
    finished_at: datetime | None = None

    results: list[DecisionResult] = field(default_factory=list)

    inserts: int = 0
    updates: int = 0
    repairs: int = 0
    skips: int = 0
    reviews: int = 0
    blocked: int = 0
    failures: int = 0

    @property
    def duration_seconds(self) -> float:
        end = (
            self.finished_at
            or datetime.now(timezone.utc)
        )

        return max(
            0.0,
            (end - self.started_at).total_seconds(),
        )

    def record(
        self,
        result: DecisionResult,
    ) -> None:
        self.results.append(
            result
        )

        if result.blocked:
            self.blocked += 1
            return

        if result.action == PublicationAction.INSERT:
            self.inserts += 1

        elif result.action == PublicationAction.UPDATE:
            self.updates += 1

        elif result.action == PublicationAction.REPAIR:
            self.repairs += 1

        elif result.action == PublicationAction.SKIP:
            self.skips += 1

        elif result.action == PublicationAction.REVIEW:
            self.reviews += 1


def decide_batch(
    items: Iterable[DecisionInput],
    *,
    policy: DecisionPolicy | None = None,
) -> DecisionBatchReport:
    if policy is None:
        policy = DecisionPolicy()

    policy.validate()

    report = DecisionBatchReport(
        started_at=datetime.now(timezone.utc)
    )

    for item in items:
        try:
            result = decide(
                item,
                policy=policy,
            )

            report.record(
                result
            )

        except Exception:
            report.failures += 1

    report.finished_at = datetime.now(
        timezone.utc
    )

    return report


# ============================================================
# Diagnostics
# ============================================================

def _diagnostic_candidate() -> AppCandidate:
    return AppCandidate(
        name="OSGuide Diagnostic App",
        source_type="github",
        source_url="https://github.com/",
        package_id="org.osguide.diagnostic",
        repository_url="https://github.com/",
        description=(
            "Diagnostic application used to verify the Decision Engine."
        ),
        source_confidence=0.95,
    )


def _diagnostic_resolution() -> ResolvedApplication:
    from resolver import run_resolver_diagnostic

    return run_resolver_diagnostic(
        _diagnostic_candidate()
    )


def _diagnostic_apk() -> ApkSelectionReport:
    from apk_intelligence import run_apk_diagnostic

    return run_apk_diagnostic(
        package_id="org.osguide.diagnostic",
        version_hint="1.0.0",
    )


def _diagnostic_content() -> ContentPackage:
    from content_intelligence import run_content_diagnostic

    return run_content_diagnostic()


def run_new_app_decision_diagnostic() -> DecisionResult:
    data = DecisionInput(
        candidate=_diagnostic_candidate(),
        resolution=_diagnostic_resolution(),
        apk=_diagnostic_apk(),
        content=_diagnostic_content(),
        existing=None,
        run_id="diagnostic-new-app",
    )

    return decide(
        data
    )


def run_existing_update_decision_diagnostic() -> DecisionResult:
    from publisher import (
        PublisherSchema,
        diagnostic_existing_row,
        parse_existing_application,
    )

    schema = PublisherSchema()

    existing = parse_existing_application(
        diagnostic_existing_row(
            schema=schema
        ),
        schema=schema,
    )

    data = DecisionInput(
        candidate=_diagnostic_candidate(),
        resolution=_diagnostic_resolution(),
        apk=_diagnostic_apk(),
        content=_diagnostic_content(),
        existing=existing,
        run_id="diagnostic-update",
        detected_stale_version=True,
    )

    return decide(
        data
    )


def run_existing_repair_decision_diagnostic() -> DecisionResult:
    from publisher import (
        PublisherSchema,
        diagnostic_existing_row,
        parse_existing_application,
    )

    schema = PublisherSchema()

    existing = parse_existing_application(
        diagnostic_existing_row(
            schema=schema
        ),
        schema=schema,
    )

    data = DecisionInput(
        candidate=_diagnostic_candidate(),
        resolution=_diagnostic_resolution(),
        apk=_diagnostic_apk(),
        content=_diagnostic_content(),
        existing=existing,
        run_id="diagnostic-repair",
        detected_missing_content=True,
    )

    return decide(
        data
    )


def run_tombstone_decision_diagnostic() -> DecisionResult:
    from publisher import (
        PublisherSchema,
        diagnostic_tombstoned_row,
        parse_existing_application,
    )

    schema = PublisherSchema()

    existing = parse_existing_application(
        diagnostic_tombstoned_row(
            schema=schema
        ),
        schema=schema,
    )

    data = DecisionInput(
        candidate=_diagnostic_candidate(),
        resolution=_diagnostic_resolution(),
        apk=_diagnostic_apk(),
        content=_diagnostic_content(),
        existing=existing,
        run_id="diagnostic-tombstone",
        detected_stale_version=True,
    )

    return decide(
        data
    )


# ============================================================
# Summary helpers
# ============================================================

def reason_summary(
    reason: DecisionReason,
) -> dict[str, object]:
    return {
        "code": reason.code.value,
        "severity": reason.severity.value,
        "message": reason.message,
        "weight": reason.weight,
        "details": dict(
            reason.details
        ),
    }


def decision_summary(
    decision: DecisionResult,
) -> dict[str, object]:
    return {
        "action": decision.action.value,
        "kind": decision.kind.value,
        "confidence": round(
            decision.confidence,
            4,
        ),
        "score": decision.score.as_dict(),
        "health": decision.health.value,
        "blocked": decision.blocked,
        "requires_review": decision.requires_review,
        "package_id": (
            decision.payload.package_id
            if decision.payload
            else None
        ),
        "version": (
            decision.payload.version
            if decision.payload
            else None
        ),
        "apk_url": (
            decision.payload.apk_url
            if decision.payload
            else None
        ),
        "reasons": [
            reason_summary(
                reason
            )
            for reason in decision.reasons
        ],
    }


def decision_batch_summary(
    report: DecisionBatchReport,
) -> dict[str, object]:
    return {
        "duration_seconds": round(
            report.duration_seconds,
            3,
        ),
        "counts": {
            "inserts": report.inserts,
            "updates": report.updates,
            "repairs": report.repairs,
            "skips": report.skips,
            "reviews": report.reviews,
            "blocked": report.blocked,
            "failures": report.failures,
        },
        "results": [
            decision_summary(
                result
            )
            for result in report.results
        ],
    }


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "AppHealthState",
    "DECISION_COMPONENT",
    "DECISION_SCHEMA_VERSION",
    "DecisionBatchReport",
    "DecisionInput",
    "DecisionKind",
    "DecisionPolicy",
    "DecisionReason",
    "DecisionReasonCode",
    "DecisionResult",
    "DecisionSeverity",
    "ScoreBreakdown",
    "admin_block_reason",
    "apk_package_mismatch",
    "apk_version_mismatch",
    "apply_hard_guards",
    "build_payload",
    "calculate_score",
    "classify_existing_health",
    "content_full",
    "content_short",
    "count_manual_fields",
    "decide",
    "decide_batch",
    "decide_existing_application",
    "decide_new_application",
    "decision_batch_summary",
    "decision_summary",
    "has_high_resolution_conflict",
    "has_package_conflict",
    "license_for",
    "package_id_for",
    "reason_summary",
    "repository_for",
    "resolved_confidence",
    "resolved_value",
    "run_existing_repair_decision_diagnostic",
    "run_existing_update_decision_diagnostic",
    "run_new_app_decision_diagnostic",
    "run_tombstone_decision_diagnostic",
    "score_admin_state",
    "score_apk",
    "score_conflict_penalty",
    "score_content",
    "score_identity",
    "score_metadata",
    "score_risk_penalty",
    "score_source",
    "selected_apk",
    "selected_apk_url",
    "selected_version",
    "to_publication_request",
    "version_for",
)
