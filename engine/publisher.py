"""
OSGuide Engine
Publisher Layer

Purpose
-------
This module is the controlled write boundary between the OSGuide
automation engine and the application's persistent backend.

The Publisher is intentionally conservative. It does not decide which
application should be published. It receives an already-evaluated
publication request from the Decision Engine and enforces final safety,
admin-authority, audit, snapshot and write-policy rules before any
external change is attempted.

Architecture rules
------------------
1. Dry-run is the default behavior.
2. A GitHub Actions input named "publish" is not enough by itself.
3. Real publishing additionally requires Publisher policy to be enabled.
4. No automatic hard deletion is permitted.
5. Admin decisions have priority over automation.
6. Applications manually deleted by Admin must not be silently recreated.
7. Manually managed fields must not be overwritten automatically.
8. Before/after snapshots are generated for all mutations.
9. Publication actions must be bounded per run.
10. Insert, update and repair are separate operations.
11. One failed application must not corrupt the whole run.
12. External responses are treated as untrusted data.
13. Secrets are read at runtime and never logged.
14. Supabase service-level credentials must never be exposed to the
    public website.
15. Publisher code must remain independent from UI code.
16. Publisher never executes external code or shell commands.
17. Rollback uses snapshots; it does not blindly reverse newer Admin work.
18. An Admin deletion marker ("tombstone") blocks automated republishing
    until explicitly cleared by Admin.
19. Field-level ownership metadata is respected when available.
20. Network calls use HTTPS only and strict timeouts.
21. The Publisher can run in a fully local diagnostic mode without any
    Supabase credentials.
22. Audit information is generated even in dry-run mode.
23. Existing applications can be repaired without being treated as new.
24. Publishing is idempotent where the backend schema supports stable
    identifiers such as Package ID.
25. No feature is removed merely to shorten this file.

This module currently provides:
- publication action models
- publication request validation
- admin-authority guards
- manual-field protection
- tombstone protection
- field-diff computation
- before/after snapshots
- safe bounded counters
- dry-run execution
- Supabase REST transport
- REST response validation
- controlled insert/update/repair operations
- publication reports
- rollback-plan generation
- diagnostic backend
- failure isolation
- serialization helpers
- secret-safe logging helpers

Expected backend
----------------
The live Supabase schema may evolve. Therefore concrete table and column
names are centralized in PublisherSchema rather than scattered through
the code. Change the schema adapter when the database schema is finalized;
do not rewrite the safety layer.

No credential belongs in this file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any,
    Final,
    Iterable,
    Mapping,
    MutableMapping,
    Protocol,
    Sequence,
)
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


# ============================================================
# Component identity
# ============================================================

PUBLISHER_COMPONENT: Final[str] = "Publisher"
PUBLISHER_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Hard safety limits
# ============================================================

DEFAULT_HTTP_TIMEOUT_SECONDS: Final[float] = 10.0
MIN_HTTP_TIMEOUT_SECONDS: Final[float] = 1.0
MAX_HTTP_TIMEOUT_SECONDS: Final[float] = 30.0

DEFAULT_MAX_INSERTS: Final[int] = 20
DEFAULT_MAX_UPDATES: Final[int] = 50
DEFAULT_MAX_REPAIRS: Final[int] = 50

MAX_INSERTS_HARD_LIMIT: Final[int] = 100
MAX_UPDATES_HARD_LIMIT: Final[int] = 500
MAX_REPAIRS_HARD_LIMIT: Final[int] = 500

MAX_REQUEST_BODY_BYTES: Final[int] = 1_000_000
MAX_RESPONSE_BODY_BYTES: Final[int] = 2_000_000

MAX_FIELD_NAME_LENGTH: Final[int] = 128
MAX_TEXT_FIELD_LENGTH: Final[int] = 100_000
MAX_AUDIT_MESSAGE_LENGTH: Final[int] = 2_000
MAX_AUDIT_ITEMS: Final[int] = 500
MAX_SNAPSHOT_FIELDS: Final[int] = 200

PACKAGE_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$"
)

SAFE_COLUMN_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]{0,127}$"
)

SAFE_TABLE_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]{0,127}$"
)


# ============================================================
# Environment variable names
# ============================================================

ENV_SUPABASE_URL: Final[str] = "OSGUIDE_SUPABASE_URL"
ENV_ENGINE_KEY: Final[str] = "OSGUIDE_ENGINE_KEY"
ENV_PUBLISH_ENABLED: Final[str] = "OSGUIDE_PUBLISH_ENABLED"


# ============================================================
# Enums
# ============================================================

class PublicationAction(str, Enum):
    INSERT = "insert"
    UPDATE = "update"
    REPAIR = "repair"
    SKIP = "skip"
    REVIEW = "review"


class PublicationStatus(str, Enum):
    PUBLISHED = "published"
    UPDATED = "updated"
    REPAIRED = "repaired"
    DRY_RUN = "dry-run"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    REVIEW = "review"
    FAILED = "failed"


class WriteMode(str, Enum):
    DRY_RUN = "dry-run"
    LIVE = "live"


class FieldOwnership(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class TombstoneState(str, Enum):
    ACTIVE = "active"
    CLEAR = "clear"
    UNKNOWN = "unknown"


class BackendStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not-found"
    CONFLICT = "conflict"
    FAILURE = "failure"


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SECURITY = "security"


# ============================================================
# Schema adapter
# ============================================================

@dataclass(frozen=True, slots=True)
class PublisherSchema:
    """
    Centralized mapping of database table and column names.

    The final Supabase schema may differ. Change this adapter when
    necessary rather than scattering literal column names across
    write logic.
    """

    applications_table: str = "applications"

    # Actual public.applications schema used by OSGuide.
    package_id_column: str = "package_id"
    name_column: str = "name"
    version_column: str = "version"
    apk_url_column: str = "download_url"

    # There is no standalone source_url column in the current table.
    # repository_url is stored separately and source_url remains
    # backend-neutral only.
    source_url_column: str | None = None
    repository_url_column: str = "repository_url"

    license_column: str = "license"
    category_column: str = "category"
    short_description_column: str = "description"
    full_description_column: str = "long_description"
    icon_url_column: str = "image_url"
    source_column: str = "source"
    visible_column: str = "is_published"

    created_at_column: str = "created_at"
    updated_at_column: str = "metadata_updated_at"

    # These Publisher safety/ownership columns are not present in the
    # current table. None means "do not write a fabricated column".
    managed_fields_column: str | None = None
    tombstone_column: str | None = None
    tombstone_at_column: str | None = None
    engine_metadata_column: str | None = None

    def validate(self) -> None:
        values = asdict(self)

        for field_name, value in values.items():
            if value is None:
                continue

            if field_name.endswith("_table"):
                if not SAFE_TABLE_RE.fullmatch(value):
                    raise ValueError(
                        f"Unsafe table name configured for {field_name}."
                    )
            else:
                if not SAFE_COLUMN_RE.fullmatch(value):
                    raise ValueError(
                        f"Unsafe column name configured for {field_name}."
                    )


# ============================================================
# Policy model
# ============================================================

@dataclass(frozen=True, slots=True)
class PublisherPolicy:
    enabled: bool = False
    write_mode: WriteMode = WriteMode.DRY_RUN

    allow_insert: bool = True
    allow_update: bool = True
    allow_repair: bool = True

    allow_delete: bool = False
    automatic_delete: bool = False

    admin_priority: bool = True
    preserve_manual_fields: bool = True
    respect_tombstones: bool = True

    require_before_after_snapshot: bool = True
    require_package_id_for_write: bool = True
    require_https_urls: bool = True

    max_inserts: int = DEFAULT_MAX_INSERTS
    max_updates: int = DEFAULT_MAX_UPDATES
    max_repairs: int = DEFAULT_MAX_REPAIRS

    request_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS

    fail_closed_on_admin_metadata_error: bool = True
    fail_closed_on_unknown_tombstone: bool = True

    def validate(self) -> None:
        if self.allow_delete:
            raise ValueError(
                "Publisher automatic deletion permission is forbidden."
            )

        if self.automatic_delete:
            raise ValueError(
                "Publisher automatic_delete must remain false."
            )

        if not self.admin_priority:
            raise ValueError(
                "Admin priority must remain enabled."
            )

        if not 0 <= self.max_inserts <= MAX_INSERTS_HARD_LIMIT:
            raise ValueError(
                "max_inserts outside allowed range."
            )

        if not 0 <= self.max_updates <= MAX_UPDATES_HARD_LIMIT:
            raise ValueError(
                "max_updates outside allowed range."
            )

        if not 0 <= self.max_repairs <= MAX_REPAIRS_HARD_LIMIT:
            raise ValueError(
                "max_repairs outside allowed range."
            )

        if not (
            MIN_HTTP_TIMEOUT_SECONDS
            <= self.request_timeout_seconds
            <= MAX_HTTP_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "request_timeout_seconds outside allowed range."
            )

        if self.write_mode == WriteMode.LIVE and not self.enabled:
            raise ValueError(
                "Live write mode cannot be used while Publisher is disabled."
            )


# ============================================================
# Publication payload
# ============================================================

@dataclass(slots=True)
class ApplicationPayload:
    """
    Backend-neutral application data.

    Optional fields may be None when the Decision Engine chooses a
    partial repair/review flow. Publisher never fabricates missing
    values.
    """

    name: str
    package_id: str | None

    version: str | None = None
    apk_url: str | None = None
    source_url: str | None = None
    repository_url: str | None = None
    license: str | None = None
    category: str | None = None
    short_description: str | None = None
    full_description: str | None = None
    icon_url: str | None = None
    source: str | None = None

    visible: bool = True

    extra: dict[str, object] = field(default_factory=dict)

    def validate(
        self,
        *,
        require_package_id: bool,
        require_https_urls: bool,
    ) -> None:
        self.name = _clean_text(
            self.name,
            max_length=500,
        )

        if (
            self.package_id
            and self.name.strip() == self.package_id.strip()
            and self.repository_url
        ):
            fallback_name = _humanize_repository_name(
                self.repository_url
            )
            if fallback_name:
                self.name = _clean_text(
                    fallback_name,
                    max_length=500,
                )

        if not self.name:
            raise ValueError(
                "Application name cannot be empty."
            )

        if self.package_id is not None:
            package_id = self.package_id.strip()

            if package_id:
                if not PACKAGE_ID_RE.fullmatch(package_id):
                    raise ValueError(
                        f"Invalid Android package ID: {package_id!r}"
                    )

                self.package_id = package_id
            else:
                self.package_id = None

        if require_package_id and not self.package_id:
            raise ValueError(
                "Publisher write requires a verified Package ID."
            )

        for attr in (
            "version",
            "license",
            "category",
            "source",
        ):
            value = getattr(self, attr)

            if value is not None:
                cleaned = _clean_text(
                    value,
                    max_length=500,
                )

                setattr(
                    self,
                    attr,
                    cleaned or None,
                )

        for attr, max_length in (
            ("short_description", 2_000),
            ("full_description", 100_000),
        ):
            value = getattr(self, attr)

            if value is not None:
                cleaned = _clean_text(
                    value,
                    max_length=max_length,
                )

                setattr(
                    self,
                    attr,
                    cleaned or None,
                )

        for attr in (
            "apk_url",
            "source_url",
            "repository_url",
            "icon_url",
        ):
            value = getattr(self, attr)

            if value is None:
                continue

            cleaned = value.strip()

            if not cleaned:
                setattr(self, attr, None)
                continue

            _validate_external_url(
                cleaned,
                require_https=require_https_urls,
            )

            setattr(self, attr, cleaned)

        if len(self.extra) > 100:
            raise ValueError(
                "ApplicationPayload.extra contains too many fields."
            )


# ============================================================
# Publication request
# ============================================================

@dataclass(slots=True)
class PublicationRequest:
    action: PublicationAction
    payload: ApplicationPayload

    expected_existing: bool | None = None

    decision_confidence: float = 0.0

    decision_reason: str = ""

    run_id: str | None = None

    candidate_identity: str | None = None

    requested_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def validate(
        self,
        *,
        policy: PublisherPolicy,
    ) -> None:
        policy.validate()

        if not 0.0 <= self.decision_confidence <= 1.0:
            raise ValueError(
                "decision_confidence must be between 0 and 1."
            )

        self.decision_reason = _clean_text(
            self.decision_reason,
            max_length=2_000,
        )

        if self.run_id is not None:
            self.run_id = _clean_text(
                self.run_id,
                max_length=200,
            ) or None

        if self.candidate_identity is not None:
            self.candidate_identity = _clean_text(
                self.candidate_identity,
                max_length=500,
            ) or None

        require_package = (
            policy.require_package_id_for_write
            and self.action
            in {
                PublicationAction.INSERT,
                PublicationAction.UPDATE,
                PublicationAction.REPAIR,
            }
        )

        self.payload.validate(
            require_package_id=require_package,
            require_https_urls=policy.require_https_urls,
        )


# ============================================================
# Existing record model
# ============================================================

@dataclass(slots=True)
class ExistingApplication:
    raw: dict[str, object]

    package_id: str | None
    exists: bool = True

    tombstone: TombstoneState = TombstoneState.UNKNOWN

    managed_fields: dict[str, FieldOwnership] = field(
        default_factory=dict
    )

    updated_at: str | None = None

    def ownership_for(
        self,
        field_name: str,
    ) -> FieldOwnership:
        return self.managed_fields.get(
            field_name,
            FieldOwnership.UNKNOWN,
        )


# ============================================================
# Audit models
# ============================================================

@dataclass(frozen=True, slots=True)
class AuditEvent:
    severity: AuditSeverity
    code: str
    message: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class AuditTrail:
    events: list[AuditEvent] = field(default_factory=list)

    def add(
        self,
        severity: AuditSeverity,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        if len(self.events) >= MAX_AUDIT_ITEMS:
            return

        safe_code = _clean_text(
            code,
            max_length=100,
        )

        safe_message = _clean_text(
            message,
            max_length=MAX_AUDIT_MESSAGE_LENGTH,
        )

        self.events.append(
            AuditEvent(
                severity=severity,
                code=safe_code,
                message=safe_message,
                details=dict(details or {}),
            )
        )


# ============================================================
# Snapshot model
# ============================================================

@dataclass(frozen=True, slots=True)
class PublicationSnapshot:
    fingerprint: str
    captured_at: datetime
    data: Mapping[str, object]

    @classmethod
    def create(
        cls,
        data: Mapping[str, object],
    ) -> "PublicationSnapshot":
        safe_data = _safe_snapshot_data(data)

        serialized = json.dumps(
            safe_data,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )

        digest = hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

        return cls(
            fingerprint=digest,
            captured_at=datetime.now(timezone.utc),
            data=safe_data,
        )


# ============================================================
# Field diff model
# ============================================================

@dataclass(frozen=True, slots=True)
class FieldChange:
    field_name: str
    old_value: object
    new_value: object
    ownership: FieldOwnership
    allowed: bool
    reason: str


@dataclass(slots=True)
class ChangeSet:
    changes: list[FieldChange] = field(default_factory=list)

    @property
    def allowed_changes(self) -> list[FieldChange]:
        return [
            change
            for change in self.changes
            if change.allowed
        ]

    @property
    def blocked_changes(self) -> list[FieldChange]:
        return [
            change
            for change in self.changes
            if not change.allowed
        ]

    @property
    def empty(self) -> bool:
        return not self.allowed_changes


# ============================================================
# Backend response
# ============================================================

@dataclass(slots=True)
class BackendResponse:
    status: BackendStatus
    status_code: int | None = None
    data: object | None = None
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def succeeded(self) -> bool:
        return (
            self.status == BackendStatus.SUCCESS
            and self.error is None
        )


# ============================================================
# Publication outcome
# ============================================================

@dataclass(slots=True)
class PublicationOutcome:
    request: PublicationRequest
    status: PublicationStatus

    before: PublicationSnapshot | None = None
    after: PublicationSnapshot | None = None

    changes: ChangeSet = field(default_factory=ChangeSet)

    audit: AuditTrail = field(default_factory=AuditTrail)

    backend_response: BackendResponse | None = None

    error: str | None = None

    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    finished_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        end_time = (
            self.finished_at
            or datetime.now(timezone.utc)
        )

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )


# ============================================================
# Batch report
# ============================================================

@dataclass(slots=True)
class PublisherCounters:
    inserts: int = 0
    updates: int = 0
    repairs: int = 0
    skipped: int = 0
    blocked: int = 0
    reviews: int = 0
    failures: int = 0

    def can_execute(
        self,
        action: PublicationAction,
        *,
        policy: PublisherPolicy,
    ) -> bool:
        if action == PublicationAction.INSERT:
            return self.inserts < policy.max_inserts

        if action == PublicationAction.UPDATE:
            return self.updates < policy.max_updates

        if action == PublicationAction.REPAIR:
            return self.repairs < policy.max_repairs

        return True

    def record(
        self,
        action: PublicationAction,
        status: PublicationStatus,
    ) -> None:
        if status == PublicationStatus.PUBLISHED:
            self.inserts += 1

        elif status == PublicationStatus.UPDATED:
            self.updates += 1

        elif status == PublicationStatus.REPAIRED:
            self.repairs += 1

        elif status == PublicationStatus.SKIPPED:
            self.skipped += 1

        elif status == PublicationStatus.BLOCKED:
            self.blocked += 1

        elif status == PublicationStatus.REVIEW:
            self.reviews += 1

        elif status == PublicationStatus.FAILED:
            self.failures += 1

        elif status == PublicationStatus.DRY_RUN:
            if action == PublicationAction.INSERT:
                self.inserts += 1
            elif action == PublicationAction.UPDATE:
                self.updates += 1
            elif action == PublicationAction.REPAIR:
                self.repairs += 1


@dataclass(slots=True)
class PublisherReport:
    started_at: datetime

    finished_at: datetime | None = None

    outcomes: list[PublicationOutcome] = field(default_factory=list)

    counters: PublisherCounters = field(default_factory=PublisherCounters)

    warnings: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        end_time = (
            self.finished_at
            or datetime.now(timezone.utc)
        )

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )


# ============================================================
# Backend protocol
# ============================================================

class PublisherBackend(Protocol):
    def get_by_package_id(
        self,
        package_id: str,
    ) -> BackendResponse:
        ...

    def insert(
        self,
        row: Mapping[str, object],
    ) -> BackendResponse:
        ...

    def update_by_package_id(
        self,
        package_id: str,
        patch: Mapping[str, object],
    ) -> BackendResponse:
        ...


# ============================================================
# Safe helpers
# ============================================================

def _extract_text_value(value: object) -> object:
    """
    Unwrap content/resolver value objects before text normalization.

    OSGuide intelligence layers may pass small dataclass/value objects
    (for example GeneratedField) instead of raw strings. Converting those
    objects directly with str(...) stores their Python repr in Supabase.
    This helper extracts the actual generated value without importing or
    coupling Publisher to the intelligence-layer classes.
    """
    if value is None or isinstance(value, (str, bytes, bytearray)):
        return value

    candidate_keys = (
        "value",
        "text",
        "content",
        "generated_text",
        "result",
    )

    if isinstance(value, Mapping):
        for key in candidate_keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate

    if is_dataclass(value):
        try:
            data = asdict(value)
        except Exception:
            data = {}

        for key in candidate_keys:
            candidate = data.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate

    for key in candidate_keys:
        try:
            candidate = getattr(value, key)
        except Exception:
            continue

        if isinstance(candidate, str) and candidate.strip():
            return candidate

    return value


def _clean_text(
    value: object,
    *,
    max_length: int,
) -> str:
    value = _extract_text_value(value)

    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif isinstance(value, bytearray):
        text = bytes(value).decode("utf-8", errors="replace")
    else:
        text = str(value)

    text = text.replace("\x00", "")

    text = (
        text.replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )

    text = re.sub(r"\s+", " ", text)

    if len(text) > max_length:
        text = text[:max_length]

    return text


def _looks_like_package_id(value: str | None) -> bool:
    if not value:
        return False

    return bool(PACKAGE_ID_RE.fullmatch(value.strip()))


def _humanize_repository_name(repository_url: str | None) -> str | None:
    """Return a readable fallback name from the repository slug."""
    if not repository_url:
        return None

    try:
        parsed = urlparse(repository_url)
        slug = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    except Exception:
        return None

    slug = re.sub(r"\.git$", "", slug, flags=re.IGNORECASE).strip()
    if not slug:
        return None

    # Preserve meaningful separators such as the hyphen in "10-bit" while
    # splitting camelCase / PascalCase and ordinary underscores.
    slug = slug.replace("_", " ")
    slug = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", slug)
    slug = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", slug)
    slug = re.sub(r"\s+", " ", slug).strip()

    return slug or None


def _validate_external_url(
    url: str,
    *,
    require_https: bool,
) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            "Only HTTP(S) URLs are allowed."
        )

    if require_https and parsed.scheme != "https":
        raise ValueError(
            "HTTPS is required."
        )

    if not parsed.hostname:
        raise ValueError(
            "URL hostname is missing."
        )

    if parsed.username or parsed.password:
        raise ValueError(
            "Credential-bearing URLs are forbidden."
        )


def _safe_snapshot_data(
    data: Mapping[str, object],
) -> dict[str, object]:
    output: dict[str, object] = {}

    for index, (key, value) in enumerate(data.items()):
        if index >= MAX_SNAPSHOT_FIELDS:
            break

        safe_key = _clean_text(
            key,
            max_length=MAX_FIELD_NAME_LENGTH,
        )

        if not SAFE_COLUMN_RE.fullmatch(safe_key):
            continue

        output[safe_key] = _safe_snapshot_value(value)

    return output


def _safe_snapshot_value(
    value: object,
) -> object:
    if value is None:
        return None

    if isinstance(
        value,
        (bool, int, float),
    ):
        return value

    if isinstance(value, str):
        return value[:MAX_TEXT_FIELD_LENGTH]

    if isinstance(value, Mapping):
        return {
            _clean_text(key, max_length=128): _safe_snapshot_value(item)
            for key, item in list(value.items())[:100]
        }

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [
            _safe_snapshot_value(item)
            for item in list(value)[:100]
        ]

    return _clean_text(
        value,
        max_length=10_000,
    )


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Enum):
        return value.value

    if is_dataclass(value):
        return asdict(value)

    return str(value)


def _secret_present(
    name: str,
) -> bool:
    return bool(
        os.getenv(name, "").strip()
    )


def secret_presence_summary() -> dict[str, bool]:
    """
    Return only credential presence booleans.
    Secret values are never returned.
    """

    return {
        "supabase_url": _secret_present(
            ENV_SUPABASE_URL
        ),
        "engine_key": _secret_present(
            ENV_ENGINE_KEY
        ),
    }


# ============================================================
# Payload conversion
# ============================================================

def payload_to_backend_row(
    payload: ApplicationPayload,
    *,
    schema: PublisherSchema,
    include_none: bool = False,
) -> dict[str, object]:
    mapping: dict[str, object] = {
        schema.name_column: payload.name,
        schema.package_id_column: payload.package_id,
        schema.version_column: payload.version,
        schema.apk_url_column: payload.apk_url,
        schema.repository_url_column: payload.repository_url,
        schema.license_column: payload.license,
        schema.category_column: payload.category,
        schema.short_description_column: payload.short_description,
        schema.full_description_column: payload.full_description,
        schema.icon_url_column: payload.icon_url,
        schema.source_column: payload.source,
        schema.visible_column: payload.visible,
    }

    if schema.source_url_column is not None:
        mapping[schema.source_url_column] = payload.source_url

    for key, value in payload.extra.items():
        if not isinstance(key, str):
            continue
        if not SAFE_COLUMN_RE.fullmatch(key):
            continue
        if key in mapping:
            continue
        mapping[key] = value

    if include_none:
        return mapping

    return {
        key: value
        for key, value in mapping.items()
        if value is not None
    }


# ============================================================
# Existing record parsing
# ============================================================

def _parse_field_ownership(
    value: object,
) -> dict[str, FieldOwnership]:
    if value is None:
        return {}

    if not isinstance(value, Mapping):
        raise ValueError(
            "managed_fields must be an object."
        )

    output: dict[str, FieldOwnership] = {}

    for key, raw_ownership in value.items():
        if not isinstance(key, str):
            continue

        if not SAFE_COLUMN_RE.fullmatch(key):
            continue

        try:
            ownership = FieldOwnership(
                str(raw_ownership).strip().lower()
            )

        except ValueError:
            ownership = FieldOwnership.UNKNOWN

        output[key] = ownership

    return output


def parse_existing_application(
    raw: Mapping[str, object],
    *,
    schema: PublisherSchema,
) -> ExistingApplication:
    package_id_raw = raw.get(
        schema.package_id_column
    )

    package_id = (
        str(package_id_raw).strip()
        if package_id_raw is not None
        else None
    )

    if schema.tombstone_column is None:
        # Current DB has no tombstone column. Treat existing rows as
        # unknown so LIVE update/repair remains fail-closed.
        tombstone = TombstoneState.UNKNOWN
    else:
        tombstone_raw = raw.get(schema.tombstone_column)
        if tombstone_raw is True:
            tombstone = TombstoneState.ACTIVE
        elif tombstone_raw is False:
            tombstone = TombstoneState.CLEAR
        else:
            tombstone = TombstoneState.UNKNOWN

    managed_fields = (
        _parse_field_ownership(raw.get(schema.managed_fields_column))
        if schema.managed_fields_column is not None
        else {}
    )

    updated_at_raw = raw.get(
        schema.updated_at_column
    )

    updated_at = (
        str(updated_at_raw)
        if updated_at_raw is not None
        else None
    )

    return ExistingApplication(
        raw=dict(raw),
        package_id=package_id,
        exists=True,
        tombstone=tombstone,
        managed_fields=managed_fields,
        updated_at=updated_at,
    )


# ============================================================
# Admin authority
# ============================================================

def publication_block_reason(
    request: PublicationRequest,
    existing: ExistingApplication | None,
    *,
    policy: PublisherPolicy,
) -> str | None:
    if request.action in {
        PublicationAction.SKIP,
        PublicationAction.REVIEW,
    }:
        return None

    if not policy.enabled:
        if policy.write_mode == WriteMode.LIVE:
            return "Publisher is disabled."

    if existing is None:
        return None

    if policy.respect_tombstones:
        if existing.tombstone == TombstoneState.ACTIVE:
            return (
                "Application is protected by an active Admin deletion "
                "tombstone."
            )

        if (
            existing.tombstone == TombstoneState.UNKNOWN
            and policy.fail_closed_on_unknown_tombstone
        ):
            return (
                "Admin deletion state is unknown; write blocked by "
                "fail-closed policy."
            )

    return None


# ============================================================
# Change computation
# ============================================================

def compute_changes(
    payload: ApplicationPayload,
    existing: ExistingApplication,
    *,
    schema: PublisherSchema,
    policy: PublisherPolicy,
) -> ChangeSet:
    desired = payload_to_backend_row(
        payload,
        schema=schema,
        include_none=False,
    )

    changes = ChangeSet()

    protected_columns = {
        column
        for column in (
            schema.created_at_column,
            schema.tombstone_column,
            schema.tombstone_at_column,
            schema.managed_fields_column,
        )
        if column is not None
    }

    for field_name, new_value in desired.items():
        if field_name in protected_columns:
            continue

        old_value = existing.raw.get(
            field_name
        )

        if _values_equivalent(
            old_value,
            new_value,
        ):
            continue

        ownership = existing.ownership_for(
            field_name
        )

        allowed = True
        reason = "Automatic field may be updated."

        if (
            policy.preserve_manual_fields
            and ownership == FieldOwnership.MANUAL
        ):
            allowed = False
            reason = (
                "Field is manually managed by Admin and is protected."
            )

        changes.changes.append(
            FieldChange(
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                ownership=ownership,
                allowed=allowed,
                reason=reason,
            )
        )

    return changes


def allowed_patch(
    change_set: ChangeSet,
    *,
    schema: PublisherSchema,
) -> dict[str, object]:
    patch = {
        change.field_name: change.new_value
        for change in change_set.allowed_changes
    }

    if patch:
        patch[
            schema.updated_at_column
        ] = datetime.now(timezone.utc).isoformat()

    return patch


def _values_equivalent(
    first: object,
    second: object,
) -> bool:
    if first is None and second is None:
        return True

    if isinstance(first, str) and isinstance(second, str):
        return first.strip() == second.strip()

    return first == second


# ============================================================
# Publication metadata
# ============================================================

def engine_metadata(
    request: PublicationRequest,
) -> dict[str, object]:
    return {
        "publisher_component": PUBLISHER_COMPONENT,
        "publisher_schema": PUBLISHER_SCHEMA_VERSION,
        "run_id": request.run_id,
        "candidate_identity": request.candidate_identity,
        "decision_confidence": request.decision_confidence,
        "decision_reason": request.decision_reason,
        "requested_action": request.action.value,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# Insert row construction
# ============================================================

def build_insert_row(
    request: PublicationRequest,
    *,
    schema: PublisherSchema,
) -> dict[str, object]:
    row = payload_to_backend_row(
        request.payload,
        schema=schema,
        include_none=False,
    )

    now = datetime.now(timezone.utc).isoformat()

    row.setdefault(
        schema.created_at_column,
        now,
    )

    row[
        schema.updated_at_column
    ] = now

    if schema.tombstone_column is not None:
        row[schema.tombstone_column] = False

    if schema.engine_metadata_column is not None:
        row[schema.engine_metadata_column] = engine_metadata(request)

    return row


# ============================================================
# Supabase REST backend
# ============================================================

class SupabaseRestBackend:
    """
    Minimal controlled Supabase/PostgREST transport.

    It deliberately avoids a large client SDK at this stage and keeps
    the write surface narrow.

    Credential requirements:
    - OSGUIDE_SUPABASE_URL
    - OSGUIDE_ENGINE_KEY

    The engine key must be stored only as a GitHub Actions secret or
    equivalent backend secret. It must never appear in frontend code.
    """

    def __init__(
        self,
        *,
        schema: PublisherSchema | None = None,
        timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
        supabase_url: str | None = None,
        engine_key: str | None = None,
    ) -> None:
        self.schema = (
            schema
            or PublisherSchema()
        )

        self.schema.validate()

        if not (
            MIN_HTTP_TIMEOUT_SECONDS
            <= timeout_seconds
            <= MAX_HTTP_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "Supabase backend timeout outside allowed range."
            )

        self.timeout_seconds = timeout_seconds

        self._supabase_url = (
            supabase_url
            or os.getenv(
                ENV_SUPABASE_URL,
                "",
            )
        ).strip()

        self._engine_key = (
            engine_key
            or os.getenv(
                ENV_ENGINE_KEY,
                "",
            )
        ).strip()

        self._validate_credentials()

    def _validate_credentials(self) -> None:
        if not self._supabase_url:
            raise ValueError(
                f"{ENV_SUPABASE_URL} is missing."
            )

        _validate_external_url(
            self._supabase_url,
            require_https=True,
        )

        parsed = urlparse(
            self._supabase_url
        )

        if parsed.path not in {
            "",
            "/",
        }:
            raise ValueError(
                "Supabase base URL should not contain an API path."
            )

        if not self._engine_key:
            raise ValueError(
                f"{ENV_ENGINE_KEY} is missing."
            )

        if len(self._engine_key) < 20:
            raise ValueError(
                "Configured engine key appears invalid."
            )

        # Supabase publishable keys map to the anonymous role and are
        # not appropriate for this privileged backend Publisher.
        if self._engine_key.startswith("sb_publishable_"):
            raise ValueError(
                "Publisher requires a Supabase secret key "
                "(sb_secret_...) or legacy service_role key; "
                "a publishable key cannot be used for backend publishing."
            )

    @property
    def rest_base_url(self) -> str:
        return (
            self._supabase_url.rstrip("/")
            + "/rest/v1"
        )

    def _headers(
        self,
        *,
        content_type: bool = True,
        prefer: str | None = None,
    ) -> dict[str, str]:
        # Supabase's modern sb_secret_ keys are opaque API keys, not JWTs.
        # Sending one as Authorization: Bearer makes the platform try to
        # parse it as a JWT and can produce HTTP 401. Modern keys therefore
        # go only in the apikey header. Legacy service_role JWT keys keep
        # the historical Authorization header for compatibility.
        headers = {
            "apikey": self._engine_key,
            "Accept": "application/json",
        }

        if not self._engine_key.startswith("sb_"):
            headers["Authorization"] = (
                f"Bearer {self._engine_key}"
            )

        if content_type:
            headers[
                "Content-Type"
            ] = "application/json"

        if prefer:
            headers[
                "Prefer"
            ] = prefer

        return headers

    def _request(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str] | None = None,
        body: object | None = None,
        prefer: str | None = None,
    ) -> BackendResponse:
        started = time.monotonic()

        url = (
            self.rest_base_url
            + "/"
            + path.lstrip("/")
        )

        if query:
            url += "?" + urlencode(
                query,
                safe="(),.*",
            )

        encoded_body: bytes | None = None

        if body is not None:
            serialized = json.dumps(
                body,
                ensure_ascii=False,
                separators=(",", ":"),
                default=_json_default,
            )

            encoded_body = serialized.encode(
                "utf-8"
            )

            if len(encoded_body) > MAX_REQUEST_BODY_BYTES:
                return BackendResponse(
                    status=BackendStatus.FAILURE,
                    error="Publisher request body exceeds safety limit.",
                    duration_seconds=max(
                        0.0,
                        time.monotonic() - started,
                    ),
                )

        request = Request(
            url=url,
            data=encoded_body,
            method=method,
            headers=self._headers(
                content_type=body is not None,
                prefer=prefer,
            ),
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw = response.read(
                    MAX_RESPONSE_BODY_BYTES + 1
                )

                if len(raw) > MAX_RESPONSE_BODY_BYTES:
                    return BackendResponse(
                        status=BackendStatus.FAILURE,
                        status_code=response.status,
                        error=(
                            "Publisher response exceeded safety limit."
                        ),
                        duration_seconds=max(
                            0.0,
                            time.monotonic() - started,
                        ),
                    )

                data = _parse_json_response(
                    raw
                )

                return BackendResponse(
                    status=BackendStatus.SUCCESS,
                    status_code=response.status,
                    data=data,
                    duration_seconds=max(
                        0.0,
                        time.monotonic() - started,
                    ),
                )

        except HTTPError as exc:
            raw = b""

            try:
                raw = exc.read(
                    MAX_RESPONSE_BODY_BYTES
                )
            except Exception:
                raw = b""

            parsed = _parse_json_response(
                raw
            )

            status = BackendStatus.FAILURE

            if exc.code == 404:
                status = BackendStatus.NOT_FOUND
            elif exc.code in {409, 412}:
                status = BackendStatus.CONFLICT

            return BackendResponse(
                status=status,
                status_code=exc.code,
                data=parsed,
                error=(
                    f"Supabase HTTP error {exc.code}."
                ),
                duration_seconds=max(
                    0.0,
                    time.monotonic() - started,
                ),
            )

        except URLError as exc:
            return BackendResponse(
                status=BackendStatus.FAILURE,
                error=(
                    "Supabase network error: "
                    + _clean_text(
                        getattr(
                            exc,
                            "reason",
                            "unknown",
                        ),
                        max_length=300,
                    )
                ),
                duration_seconds=max(
                    0.0,
                    time.monotonic() - started,
                ),
            )

        except Exception as exc:
            return BackendResponse(
                status=BackendStatus.FAILURE,
                error=(
                    "Unexpected Supabase transport error: "
                    + _clean_text(
                        type(exc).__name__,
                        max_length=100,
                    )
                ),
                duration_seconds=max(
                    0.0,
                    time.monotonic() - started,
                ),
            )

    def get_by_package_id(
        self,
        package_id: str,
    ) -> BackendResponse:
        query = {
            self.schema.package_id_column: (
                "eq."
                + package_id
            ),
            "limit": "1",
            "select": "*",
        }

        response = self._request(
            method="GET",
            path=self.schema.applications_table,
            query=query,
        )

        if not response.succeeded:
            return response

        if not isinstance(
            response.data,
            list,
        ):
            return BackendResponse(
                status=BackendStatus.FAILURE,
                status_code=response.status_code,
                error="Unexpected Supabase lookup response shape.",
                duration_seconds=response.duration_seconds,
            )

        if not response.data:
            return BackendResponse(
                status=BackendStatus.NOT_FOUND,
                status_code=response.status_code,
                data=None,
                duration_seconds=response.duration_seconds,
            )

        return BackendResponse(
            status=BackendStatus.SUCCESS,
            status_code=response.status_code,
            data=response.data[0],
            duration_seconds=response.duration_seconds,
        )

    def insert(
        self,
        row: Mapping[str, object],
    ) -> BackendResponse:
        return self._request(
            method="POST",
            path=self.schema.applications_table,
            body=dict(row),
            prefer="return=representation",
        )

    def update_by_package_id(
        self,
        package_id: str,
        patch: Mapping[str, object],
    ) -> BackendResponse:
        query = {
            self.schema.package_id_column: (
                "eq."
                + package_id
            ),
        }

        return self._request(
            method="PATCH",
            path=self.schema.applications_table,
            query=query,
            body=dict(patch),
            prefer="return=representation",
        )


# ============================================================
# JSON response parser
# ============================================================

def _parse_json_response(
    raw: bytes,
) -> object | None:
    if not raw:
        return None

    try:
        text = raw.decode(
            "utf-8",
            errors="strict",
        )

        return json.loads(
            text
        )

    except Exception:
        return None


# ============================================================
# Diagnostic backend
# ============================================================

class DiagnosticPublisherBackend:
    """
    In-memory backend used for Publisher diagnostics.

    It performs no network requests.
    """

    def __init__(
        self,
        initial_rows: Iterable[
            Mapping[str, object]
        ] = (),
        *,
        schema: PublisherSchema | None = None,
    ) -> None:
        self.schema = (
            schema
            or PublisherSchema()
        )

        self.rows: dict[
            str,
            dict[str, object],
        ] = {}

        for row in initial_rows:
            package_id_raw = row.get(
                self.schema.package_id_column
            )

            if package_id_raw is None:
                continue

            package_id = str(
                package_id_raw
            ).strip()

            if package_id:
                self.rows[
                    package_id
                ] = dict(row)

    def get_by_package_id(
        self,
        package_id: str,
    ) -> BackendResponse:
        started = time.monotonic()

        row = self.rows.get(
            package_id
        )

        if row is None:
            return BackendResponse(
                status=BackendStatus.NOT_FOUND,
                status_code=404,
                duration_seconds=max(
                    0.0,
                    time.monotonic() - started,
                ),
            )

        return BackendResponse(
            status=BackendStatus.SUCCESS,
            status_code=200,
            data=dict(row),
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )

    def insert(
        self,
        row: Mapping[str, object],
    ) -> BackendResponse:
        started = time.monotonic()

        package_id_raw = row.get(
            self.schema.package_id_column
        )

        if package_id_raw is None:
            return BackendResponse(
                status=BackendStatus.FAILURE,
                status_code=400,
                error="Diagnostic insert requires package ID.",
            )

        package_id = str(
            package_id_raw
        )

        if package_id in self.rows:
            return BackendResponse(
                status=BackendStatus.CONFLICT,
                status_code=409,
                error="Duplicate diagnostic package ID.",
            )

        self.rows[
            package_id
        ] = dict(row)

        return BackendResponse(
            status=BackendStatus.SUCCESS,
            status_code=201,
            data=[
                dict(row)
            ],
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )

    def update_by_package_id(
        self,
        package_id: str,
        patch: Mapping[str, object],
    ) -> BackendResponse:
        started = time.monotonic()

        existing = self.rows.get(
            package_id
        )

        if existing is None:
            return BackendResponse(
                status=BackendStatus.NOT_FOUND,
                status_code=404,
                error="Diagnostic row does not exist.",
            )

        existing.update(
            dict(patch)
        )

        return BackendResponse(
            status=BackendStatus.SUCCESS,
            status_code=200,
            data=[
                dict(existing)
            ],
            duration_seconds=max(
                0.0,
                time.monotonic() - started,
            ),
        )


# ============================================================
# Lookup helper
# ============================================================

def lookup_existing(
    request: PublicationRequest,
    backend: PublisherBackend,
    *,
    schema: PublisherSchema,
) -> tuple[
    ExistingApplication | None,
    BackendResponse,
]:
    package_id = request.payload.package_id

    if not package_id:
        response = BackendResponse(
            status=BackendStatus.NOT_FOUND,
            error="No Package ID available for existing-record lookup.",
        )

        return None, response

    response = backend.get_by_package_id(
        package_id
    )

    if response.status == BackendStatus.NOT_FOUND:
        return None, response

    if not response.succeeded:
        return None, response

    if not isinstance(
        response.data,
        Mapping,
    ):
        return (
            None,
            BackendResponse(
                status=BackendStatus.FAILURE,
                status_code=response.status_code,
                error="Existing application response has invalid shape.",
                duration_seconds=response.duration_seconds,
            ),
        )

    try:
        existing = parse_existing_application(
            response.data,
            schema=schema,
        )

    except Exception as exc:
        return (
            None,
            BackendResponse(
                status=BackendStatus.FAILURE,
                status_code=response.status_code,
                error=(
                    "Existing application metadata is invalid: "
                    + _clean_text(
                        exc,
                        max_length=500,
                    )
                ),
                duration_seconds=response.duration_seconds,
            ),
        )

    return existing, response


# ============================================================
# Publication execution
# ============================================================

def execute_publication(
    request: PublicationRequest,
    backend: PublisherBackend,
    *,
    policy: PublisherPolicy,
    schema: PublisherSchema | None = None,
    counters: PublisherCounters | None = None,
) -> PublicationOutcome:
    if schema is None:
        schema = PublisherSchema()

    if counters is None:
        counters = PublisherCounters()

    schema.validate()
    policy.validate()
    request.validate(
        policy=policy
    )

    outcome = PublicationOutcome(
        request=request,
        status=PublicationStatus.SKIPPED,
    )

    outcome.audit.add(
        AuditSeverity.INFO,
        "publisher.request.received",
        (
            f"Publication request received: "
            f"{request.action.value}"
        ),
        details={
            "candidate_identity": request.candidate_identity,
            "package_id": request.payload.package_id,
            "decision_confidence": request.decision_confidence,
        },
    )

    if request.action == PublicationAction.SKIP:
        outcome.status = PublicationStatus.SKIPPED

        outcome.audit.add(
            AuditSeverity.INFO,
            "publisher.request.skip",
            "Decision Engine requested skip.",
        )

        outcome.finished_at = datetime.now(timezone.utc)
        counters.record(
            request.action,
            outcome.status,
        )
        return outcome

    if request.action == PublicationAction.REVIEW:
        outcome.status = PublicationStatus.REVIEW

        outcome.audit.add(
            AuditSeverity.INFO,
            "publisher.request.review",
            "Decision Engine requested manual review.",
        )

        outcome.finished_at = datetime.now(timezone.utc)
        counters.record(
            request.action,
            outcome.status,
        )
        return outcome

    if not counters.can_execute(
        request.action,
        policy=policy,
    ):
        outcome.status = PublicationStatus.BLOCKED

        outcome.audit.add(
            AuditSeverity.SECURITY,
            "publisher.run.limit",
            "Run publication limit reached; action blocked.",
        )

        outcome.finished_at = datetime.now(timezone.utc)
        counters.record(
            request.action,
            outcome.status,
        )
        return outcome

    existing, lookup_response = lookup_existing(
        request,
        backend,
        schema=schema,
    )

    if (
        lookup_response.status
        not in {
            BackendStatus.SUCCESS,
            BackendStatus.NOT_FOUND,
        }
    ):
        outcome.status = PublicationStatus.FAILED
        outcome.error = (
            lookup_response.error
            or "Existing application lookup failed."
        )

        outcome.audit.add(
            AuditSeverity.ERROR,
            "publisher.lookup.failed",
            outcome.error,
        )

        outcome.finished_at = datetime.now(timezone.utc)
        counters.record(
            request.action,
            outcome.status,
        )
        return outcome

    if existing is not None:
        outcome.before = PublicationSnapshot.create(
            existing.raw
        )

    block_reason = publication_block_reason(
        request,
        existing,
        policy=policy,
    )

    if block_reason:
        outcome.status = PublicationStatus.BLOCKED

        outcome.audit.add(
            AuditSeverity.SECURITY,
            "publisher.admin.block",
            block_reason,
        )

        outcome.finished_at = datetime.now(timezone.utc)
        counters.record(
            request.action,
            outcome.status,
        )
        return outcome

    if request.action == PublicationAction.INSERT:
        outcome = _execute_insert(
            outcome,
            backend,
            existing=existing,
            policy=policy,
            schema=schema,
        )

    elif request.action in {
        PublicationAction.UPDATE,
        PublicationAction.REPAIR,
    }:
        outcome = _execute_update_or_repair(
            outcome,
            backend,
            existing=existing,
            policy=policy,
            schema=schema,
        )

    else:
        outcome.status = PublicationStatus.FAILED
        outcome.error = (
            f"Unsupported publication action: {request.action.value}"
        )

    outcome.finished_at = datetime.now(timezone.utc)

    counters.record(
        request.action,
        outcome.status,
    )

    return outcome


# ============================================================
# Insert implementation
# ============================================================

def _execute_insert(
    outcome: PublicationOutcome,
    backend: PublisherBackend,
    *,
    existing: ExistingApplication | None,
    policy: PublisherPolicy,
    schema: PublisherSchema,
) -> PublicationOutcome:
    request = outcome.request

    if not policy.allow_insert:
        outcome.status = PublicationStatus.BLOCKED

        outcome.audit.add(
            AuditSeverity.SECURITY,
            "publisher.insert.disabled",
            "Insert action is disabled by policy.",
        )

        return outcome

    if existing is not None:
        outcome.status = PublicationStatus.REVIEW

        outcome.audit.add(
            AuditSeverity.WARNING,
            "publisher.insert.exists",
            (
                "Insert requested but application already exists. "
                "Manual review required."
            ),
        )

        return outcome

    row = build_insert_row(
        request,
        schema=schema,
    )

    outcome.after = PublicationSnapshot.create(
        row
    )

    if policy.write_mode == WriteMode.DRY_RUN:
        outcome.status = PublicationStatus.DRY_RUN

        outcome.audit.add(
            AuditSeverity.INFO,
            "publisher.insert.dry_run",
            "Insert validated successfully; no external write performed.",
        )

        return outcome

    response = backend.insert(
        row
    )

    outcome.backend_response = response

    if response.succeeded:
        outcome.status = PublicationStatus.PUBLISHED

        outcome.audit.add(
            AuditSeverity.INFO,
            "publisher.insert.success",
            "Application inserted successfully.",
        )

    elif response.status == BackendStatus.CONFLICT:
        outcome.status = PublicationStatus.REVIEW
        outcome.error = response.error

        outcome.audit.add(
            AuditSeverity.WARNING,
            "publisher.insert.conflict",
            "Backend reported an insert conflict.",
        )

    else:
        outcome.status = PublicationStatus.FAILED
        outcome.error = (
            response.error
            or "Backend insert failed."
        )

        outcome.audit.add(
            AuditSeverity.ERROR,
            "publisher.insert.failed",
            outcome.error,
        )

    return outcome


# ============================================================
# Update / repair implementation
# ============================================================

def _execute_update_or_repair(
    outcome: PublicationOutcome,
    backend: PublisherBackend,
    *,
    existing: ExistingApplication | None,
    policy: PublisherPolicy,
    schema: PublisherSchema,
) -> PublicationOutcome:
    request = outcome.request

    if request.action == PublicationAction.UPDATE:
        if not policy.allow_update:
            outcome.status = PublicationStatus.BLOCKED

            outcome.audit.add(
                AuditSeverity.SECURITY,
                "publisher.update.disabled",
                "Update action is disabled by policy.",
            )

            return outcome

    if request.action == PublicationAction.REPAIR:
        if not policy.allow_repair:
            outcome.status = PublicationStatus.BLOCKED

            outcome.audit.add(
                AuditSeverity.SECURITY,
                "publisher.repair.disabled",
                "Repair action is disabled by policy.",
            )

            return outcome

    if existing is None:
        outcome.status = PublicationStatus.REVIEW

        outcome.audit.add(
            AuditSeverity.WARNING,
            "publisher.update.missing",
            (
                "Update/repair requested but application does not exist. "
                "Automatic insert substitution is intentionally forbidden."
            ),
        )

        return outcome

    change_set = compute_changes(
        request.payload,
        existing,
        schema=schema,
        policy=policy,
    )

    outcome.changes = change_set

    for blocked_change in change_set.blocked_changes:
        outcome.audit.add(
            AuditSeverity.SECURITY,
            "publisher.field.manual",
            (
                f"Protected manual field not modified: "
                f"{blocked_change.field_name}"
            ),
            details={
                "field": blocked_change.field_name,
                "ownership": blocked_change.ownership.value,
            },
        )

    patch = allowed_patch(
        change_set,
        schema=schema,
    )

    if not patch:
        outcome.status = PublicationStatus.SKIPPED

        outcome.audit.add(
            AuditSeverity.INFO,
            "publisher.no_change",
            "No allowed field changes remain after policy evaluation.",
        )

        outcome.after = PublicationSnapshot.create(
            existing.raw
        )

        return outcome

    patch[
        schema.engine_metadata_column
    ] = engine_metadata(
        request
    )

    after_raw = dict(
        existing.raw
    )

    after_raw.update(
        patch
    )

    outcome.after = PublicationSnapshot.create(
        after_raw
    )

    if policy.write_mode == WriteMode.DRY_RUN:
        outcome.status = PublicationStatus.DRY_RUN

        outcome.audit.add(
            AuditSeverity.INFO,
            "publisher.patch.dry_run",
            (
                "Update/repair validated successfully; "
                "no external write performed."
            ),
            details={
                "allowed_change_count": len(
                    change_set.allowed_changes
                ),
                "blocked_change_count": len(
                    change_set.blocked_changes
                ),
            },
        )

        return outcome

    package_id = request.payload.package_id

    if not package_id:
        outcome.status = PublicationStatus.FAILED
        outcome.error = (
            "Package ID unexpectedly missing before backend patch."
        )

        return outcome

    response = backend.update_by_package_id(
        package_id,
        patch,
    )

    outcome.backend_response = response

    if response.succeeded:
        if request.action == PublicationAction.UPDATE:
            outcome.status = PublicationStatus.UPDATED
            event_code = "publisher.update.success"
            event_message = "Application updated successfully."
        else:
            outcome.status = PublicationStatus.REPAIRED
            event_code = "publisher.repair.success"
            event_message = "Application repaired successfully."

        outcome.audit.add(
            AuditSeverity.INFO,
            event_code,
            event_message,
            details={
                "allowed_change_count": len(
                    change_set.allowed_changes
                ),
                "blocked_change_count": len(
                    change_set.blocked_changes
                ),
            },
        )

    elif response.status == BackendStatus.NOT_FOUND:
        outcome.status = PublicationStatus.REVIEW
        outcome.error = response.error

        outcome.audit.add(
            AuditSeverity.WARNING,
            "publisher.patch.not_found",
            (
                "Application disappeared before update. "
                "Automatic insert fallback was not attempted."
            ),
        )

    else:
        outcome.status = PublicationStatus.FAILED
        outcome.error = (
            response.error
            or "Backend patch failed."
        )

        outcome.audit.add(
            AuditSeverity.ERROR,
            "publisher.patch.failed",
            outcome.error,
        )

    return outcome


# ============================================================
# Batch publication
# ============================================================

def publish_requests(
    requests: Iterable[PublicationRequest],
    backend: PublisherBackend,
    *,
    policy: PublisherPolicy,
    schema: PublisherSchema | None = None,
) -> PublisherReport:
    if schema is None:
        schema = PublisherSchema()

    policy.validate()
    schema.validate()

    report = PublisherReport(
        started_at=datetime.now(timezone.utc)
    )

    for request in requests:
        try:
            outcome = execute_publication(
                request,
                backend,
                policy=policy,
                schema=schema,
                counters=report.counters,
            )

        except Exception as exc:
            outcome = PublicationOutcome(
                request=request,
                status=PublicationStatus.FAILED,
                error=(
                    "Unexpected publication failure: "
                    + _clean_text(
                        type(exc).__name__,
                        max_length=100,
                    )
                ),
                finished_at=datetime.now(timezone.utc),
            )

            outcome.audit.add(
                AuditSeverity.ERROR,
                "publisher.unexpected_failure",
                outcome.error,
            )

            report.counters.failures += 1

        report.outcomes.append(
            outcome
        )

    report.finished_at = datetime.now(timezone.utc)

    return report


# ============================================================
# Rollback plan
# ============================================================

@dataclass(frozen=True, slots=True)
class RollbackPlan:
    package_id: str | None
    original_snapshot: PublicationSnapshot | None
    published_snapshot: PublicationSnapshot | None
    allowed: bool
    reason: str
    patch: Mapping[str, object]


def build_rollback_plan(
    outcome: PublicationOutcome,
    *,
    schema: PublisherSchema,
) -> RollbackPlan:
    package_id = outcome.request.payload.package_id

    if outcome.before is None:
        return RollbackPlan(
            package_id=package_id,
            original_snapshot=None,
            published_snapshot=outcome.after,
            allowed=False,
            reason=(
                "New application insert cannot be blindly hard-deleted. "
                "Use a visibility/tombstone-safe rollback workflow."
            ),
            patch={},
        )

    if outcome.after is None:
        return RollbackPlan(
            package_id=package_id,
            original_snapshot=outcome.before,
            published_snapshot=None,
            allowed=False,
            reason="No post-publication snapshot exists.",
            patch={},
        )

    patch: dict[str, object] = {}

    for change in outcome.changes.allowed_changes:
        if change.field_name in {
            schema.tombstone_column,
            schema.tombstone_at_column,
            schema.managed_fields_column,
        }:
            continue

        patch[
            change.field_name
        ] = change.old_value

    if not patch:
        return RollbackPlan(
            package_id=package_id,
            original_snapshot=outcome.before,
            published_snapshot=outcome.after,
            allowed=False,
            reason="No reversible automatic field changes were recorded.",
            patch={},
        )

    return RollbackPlan(
        package_id=package_id,
        original_snapshot=outcome.before,
        published_snapshot=outcome.after,
        allowed=True,
        reason=(
            "Rollback patch contains only fields changed by this "
            "publication outcome. Newer Admin changes must still be "
            "checked before execution."
        ),
        patch=patch,
    )


# ============================================================
# Diagnostic fixtures
# ============================================================

def diagnostic_existing_row(
    *,
    schema: PublisherSchema | None = None,
) -> dict[str, object]:
    if schema is None:
        schema = PublisherSchema()

    return {
        schema.package_id_column: "org.osguide.diagnostic",
        schema.name_column: "OSGuide Diagnostic App",
        schema.version_column: "1.0.0",
        schema.apk_url_column: (
            "https://github.com/example/osguide-diagnostic/"
            "releases/download/v1.0.0/app.apk"
        ),
        **(
            {schema.source_url_column: "https://github.com/"}
            if schema.source_url_column is not None
            else {}
        ),
        schema.repository_url_column: "https://github.com/",
        schema.license_column: "GPL-3.0",
        schema.category_column: "Development",
        schema.short_description_column: "Existing diagnostic description.",
        schema.full_description_column: "Existing diagnostic full description.",
        schema.icon_url_column: "https://github.com/favicon.ico",
        schema.source_column: "GitHub",
        schema.visible_column: True,
        **(
            {schema.tombstone_column: False}
            if schema.tombstone_column is not None
            else {}
        ),
        **(
            {
                schema.managed_fields_column: {
                    schema.name_column: FieldOwnership.MANUAL.value,
                    schema.version_column: FieldOwnership.AUTO.value,
                    schema.apk_url_column: FieldOwnership.AUTO.value,
                    schema.short_description_column: FieldOwnership.AUTO.value,
                }
            }
            if schema.managed_fields_column is not None
            else {}
        ),
        schema.updated_at_column: "2026-01-01T00:00:00+00:00",
    }


def diagnostic_update_request() -> PublicationRequest:
    return PublicationRequest(
        action=PublicationAction.UPDATE,
        payload=ApplicationPayload(
            name="OSGuide Diagnostic App (engine suggestion)",
            package_id="org.osguide.diagnostic",
            version="1.1.0",
            apk_url=(
                "https://github.com/example/osguide-diagnostic/"
                "releases/download/v1.1.0/app.apk"
            ),
            source_url="https://github.com/",
            repository_url="https://github.com/",
            license="GPL-3.0",
            category="Development",
            short_description=(
                "Updated source-backed diagnostic description."
            ),
            full_description=(
                "Updated source-backed diagnostic full description."
            ),
            icon_url="https://github.com/favicon.ico",
            source="GitHub",
            visible=True,
        ),
        expected_existing=True,
        decision_confidence=0.95,
        decision_reason=(
            "Synthetic diagnostic update for Publisher validation."
        ),
        run_id="diagnostic-run",
        candidate_identity="package:org.osguide.diagnostic",
    )


def diagnostic_insert_request() -> PublicationRequest:
    return PublicationRequest(
        action=PublicationAction.INSERT,
        payload=ApplicationPayload(
            name="OSGuide New Diagnostic App",
            package_id="org.osguide.newdiagnostic",
            version="1.0.0",
            apk_url=(
                "https://github.com/example/osguide-new-diagnostic/"
                "releases/download/v1.0.0/app.apk"
            ),
            source_url="https://github.com/",
            repository_url="https://github.com/",
            license="GPL-3.0",
            category="Development",
            short_description=(
                "New synthetic diagnostic application."
            ),
            full_description=(
                "New synthetic diagnostic application used to validate "
                "safe Publisher insert behavior."
            ),
            icon_url="https://github.com/favicon.ico",
            source="GitHub",
            visible=True,
        ),
        expected_existing=False,
        decision_confidence=0.95,
        decision_reason=(
            "Synthetic diagnostic insert for Publisher validation."
        ),
        run_id="diagnostic-run",
        candidate_identity="package:org.osguide.newdiagnostic",
    )


# ============================================================
# Tombstone diagnostic
# ============================================================

def diagnostic_tombstoned_row(
    *,
    schema: PublisherSchema | None = None,
) -> dict[str, object]:
    if schema is None:
        schema = PublisherSchema()

    row = diagnostic_existing_row(
        schema=schema
    )

    if schema.tombstone_column is not None:
        row[schema.tombstone_column] = True

    if schema.tombstone_at_column is not None:
        row[schema.tombstone_at_column] = "2026-01-02T00:00:00+00:00"

    return row


# ============================================================
# Public diagnostics
# ============================================================

def run_publisher_diagnostic() -> PublisherReport:
    """
    Test dry-run insert + update with manual-field preservation.

    No network calls.
    """

    schema = PublisherSchema()

    backend = DiagnosticPublisherBackend(
        [
            diagnostic_existing_row(
                schema=schema
            )
        ],
        schema=schema,
    )

    policy = PublisherPolicy(
        enabled=False,
        write_mode=WriteMode.DRY_RUN,
        allow_insert=True,
        allow_update=True,
        allow_repair=True,
        allow_delete=False,
        automatic_delete=False,
        admin_priority=True,
        preserve_manual_fields=True,
        respect_tombstones=True,
        require_before_after_snapshot=True,
        require_package_id_for_write=True,
        require_https_urls=True,
        max_inserts=20,
        max_updates=50,
        max_repairs=50,
        request_timeout_seconds=10.0,
        fail_closed_on_admin_metadata_error=True,
        fail_closed_on_unknown_tombstone=False,
    )

    return publish_requests(
        (
            diagnostic_insert_request(),
            diagnostic_update_request(),
        ),
        backend,
        policy=policy,
        schema=schema,
    )


def run_live_diagnostic_backend_test() -> PublisherReport:
    """
    Exercise the exact live-write control flow against the in-memory
    backend.

    Still performs no network requests.
    """

    schema = PublisherSchema()

    backend = DiagnosticPublisherBackend(
        [
            diagnostic_existing_row(
                schema=schema
            )
        ],
        schema=schema,
    )

    policy = PublisherPolicy(
        enabled=True,
        write_mode=WriteMode.LIVE,
        allow_insert=True,
        allow_update=True,
        allow_repair=True,
        allow_delete=False,
        automatic_delete=False,
        admin_priority=True,
        preserve_manual_fields=True,
        respect_tombstones=True,
        require_before_after_snapshot=True,
        require_package_id_for_write=True,
        require_https_urls=True,
        max_inserts=20,
        max_updates=50,
        max_repairs=50,
        request_timeout_seconds=10.0,
        fail_closed_on_admin_metadata_error=True,
        fail_closed_on_unknown_tombstone=False,
    )

    return publish_requests(
        (
            diagnostic_insert_request(),
            diagnostic_update_request(),
        ),
        backend,
        policy=policy,
        schema=schema,
    )


def run_tombstone_diagnostic() -> PublicationOutcome:
    schema = PublisherSchema()

    backend = DiagnosticPublisherBackend(
        [
            diagnostic_tombstoned_row(
                schema=schema
            )
        ],
        schema=schema,
    )

    policy = PublisherPolicy(
        enabled=True,
        write_mode=WriteMode.LIVE,
        allow_insert=True,
        allow_update=True,
        allow_repair=True,
        allow_delete=False,
        automatic_delete=False,
        admin_priority=True,
        preserve_manual_fields=True,
        respect_tombstones=True,
        require_before_after_snapshot=True,
        require_package_id_for_write=True,
        require_https_urls=True,
        max_inserts=20,
        max_updates=50,
        max_repairs=50,
        request_timeout_seconds=10.0,
        fail_closed_on_admin_metadata_error=True,
        fail_closed_on_unknown_tombstone=True,
    )

    return execute_publication(
        diagnostic_update_request(),
        backend,
        policy=policy,
        schema=schema,
    )


# ============================================================
# Live backend factory
# ============================================================

def create_live_backend(
    *,
    schema: PublisherSchema | None = None,
    timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS,
) -> SupabaseRestBackend:
    """
    Create live Supabase backend using runtime secrets.

    Calling this function does not make a write. It only validates
    configuration and constructs the transport.
    """

    return SupabaseRestBackend(
        schema=schema,
        timeout_seconds=timeout_seconds,
    )


# ============================================================
# Safe policy factory
# ============================================================

def default_dry_run_policy() -> PublisherPolicy:
    return PublisherPolicy(
        enabled=False,
        write_mode=WriteMode.DRY_RUN,
        allow_insert=True,
        allow_update=True,
        allow_repair=True,
        allow_delete=False,
        automatic_delete=False,
        admin_priority=True,
        preserve_manual_fields=True,
        respect_tombstones=True,
        require_before_after_snapshot=True,
        require_package_id_for_write=True,
        require_https_urls=True,
        max_inserts=DEFAULT_MAX_INSERTS,
        max_updates=DEFAULT_MAX_UPDATES,
        max_repairs=DEFAULT_MAX_REPAIRS,
        request_timeout_seconds=DEFAULT_HTTP_TIMEOUT_SECONDS,
        fail_closed_on_admin_metadata_error=True,
        fail_closed_on_unknown_tombstone=True,
    )


def live_policy_from_environment() -> PublisherPolicy:
    enabled_raw = os.getenv(
        ENV_PUBLISH_ENABLED,
        "",
    ).strip().lower()

    enabled = enabled_raw in {
        "1",
        "true",
        "yes",
        "on",
        "enabled",
    }

    if not enabled:
        return default_dry_run_policy()

    if not _secret_present(
        ENV_SUPABASE_URL
    ):
        raise ValueError(
            "Live Publisher enabled but Supabase URL is missing."
        )

    if not _secret_present(
        ENV_ENGINE_KEY
    ):
        raise ValueError(
            "Live Publisher enabled but engine key is missing."
        )

    return PublisherPolicy(
        enabled=True,
        write_mode=WriteMode.LIVE,
        allow_insert=True,
        allow_update=True,
        allow_repair=True,
        allow_delete=False,
        automatic_delete=False,
        admin_priority=True,
        preserve_manual_fields=True,
        respect_tombstones=True,
        require_before_after_snapshot=True,
        require_package_id_for_write=True,
        require_https_urls=True,
        max_inserts=DEFAULT_MAX_INSERTS,
        max_updates=DEFAULT_MAX_UPDATES,
        max_repairs=DEFAULT_MAX_REPAIRS,
        request_timeout_seconds=DEFAULT_HTTP_TIMEOUT_SECONDS,
        fail_closed_on_admin_metadata_error=True,
        fail_closed_on_unknown_tombstone=True,
    )


# ============================================================
# Summary helpers
# ============================================================

def change_summary(
    change_set: ChangeSet,
) -> dict[str, object]:
    return {
        "allowed": [
            {
                "field": item.field_name,
                "ownership": item.ownership.value,
                "reason": item.reason,
            }
            for item in change_set.allowed_changes
        ],
        "blocked": [
            {
                "field": item.field_name,
                "ownership": item.ownership.value,
                "reason": item.reason,
            }
            for item in change_set.blocked_changes
        ],
    }


def audit_summary(
    audit: AuditTrail,
) -> list[dict[str, object]]:
    return [
        {
            "severity": event.severity.value,
            "code": event.code,
            "message": event.message,
            "timestamp": event.timestamp.isoformat(),
            "details": dict(event.details),
        }
        for event in audit.events
    ]


def outcome_summary(
    outcome: PublicationOutcome,
) -> dict[str, object]:
    return {
        "action": outcome.request.action.value,
        "status": outcome.status.value,
        "package_id": outcome.request.payload.package_id,
        "candidate_identity": outcome.request.candidate_identity,
        "duration_seconds": round(
            outcome.duration_seconds,
            3,
        ),
        "before_fingerprint": (
            outcome.before.fingerprint
            if outcome.before
            else None
        ),
        "after_fingerprint": (
            outcome.after.fingerprint
            if outcome.after
            else None
        ),
        "changes": change_summary(
            outcome.changes
        ),
        "error": outcome.error,
        "audit": audit_summary(
            outcome.audit
        ),
    }


def publisher_report_summary(
    report: PublisherReport,
) -> dict[str, object]:
    return {
        "duration_seconds": round(
            report.duration_seconds,
            3,
        ),
        "counts": {
            "inserts": report.counters.inserts,
            "updates": report.counters.updates,
            "repairs": report.counters.repairs,
            "skipped": report.counters.skipped,
            "blocked": report.counters.blocked,
            "reviews": report.counters.reviews,
            "failures": report.counters.failures,
        },
        "outcomes": [
            outcome_summary(
                outcome
            )
            for outcome in report.outcomes
        ],
        "warnings": list(
            report.warnings
        ),
    }


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "ApplicationPayload",
    "AuditEvent",
    "AuditSeverity",
    "AuditTrail",
    "BackendResponse",
    "BackendStatus",
    "ChangeSet",
    "DiagnosticPublisherBackend",
    "ExistingApplication",
    "FieldChange",
    "FieldOwnership",
    "PUBLISHER_COMPONENT",
    "PUBLISHER_SCHEMA_VERSION",
    "PublicationAction",
    "PublicationOutcome",
    "PublicationRequest",
    "PublicationSnapshot",
    "PublicationStatus",
    "PublisherBackend",
    "PublisherCounters",
    "PublisherPolicy",
    "PublisherReport",
    "PublisherSchema",
    "RollbackPlan",
    "SupabaseRestBackend",
    "TombstoneState",
    "WriteMode",
    "allowed_patch",
    "audit_summary",
    "build_insert_row",
    "build_rollback_plan",
    "change_summary",
    "compute_changes",
    "create_live_backend",
    "default_dry_run_policy",
    "diagnostic_existing_row",
    "diagnostic_insert_request",
    "diagnostic_tombstoned_row",
    "diagnostic_update_request",
    "engine_metadata",
    "execute_publication",
    "live_policy_from_environment",
    "lookup_existing",
    "outcome_summary",
    "parse_existing_application",
    "payload_to_backend_row",
    "publication_block_reason",
    "publish_requests",
    "publisher_report_summary",
    "run_live_diagnostic_backend_test",
    "run_publisher_diagnostic",
    "run_tombstone_diagnostic",
    "secret_presence_summary",
)
