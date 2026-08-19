"""
OSGuide Engine
Audit & Rollback Layer

Purpose
-------
This module provides the non-destructive audit and rollback planning layer
for the OSGuide automation engine.

It is responsible for:
- immutable-style audit events
- before/after snapshots
- field-level change records
- publication transaction summaries
- rollback plans
- rollback eligibility checks
- Admin ownership protection
- tombstone protection
- conflict detection
- bounded local audit storage
- deterministic fingerprints
- safe JSON serialization
- diagnostics

Architecture rules
------------------
1. This module never deletes applications automatically.
2. This module never bypasses Publisher policy.
3. This module never overrides Admin-owned fields.
4. This module never clears a tombstone automatically.
5. Rollback is a plan until Publisher explicitly executes it.
6. Audit records never contain secrets.
7. Secret-like values are redacted before persistence.
8. Rollback snapshots contain only fields required to restore engine-owned
   state.
9. Every rollback plan is bounded and auditable.
10. A rollback plan must identify the original publication event.
11. Automatic rollback is disabled by default.
12. Manual approval can be required independently for every rollback.
13. Insert rollback means "revert engine insertion" only when policy allows;
    it does not imply unconditional deletion.
14. Update rollback restores only fields the engine changed.
15. Repair rollback restores only fields the engine changed.
16. Review/skip decisions do not generate destructive rollback operations.
17. Corrupt audit files fail closed.
18. Local persistence uses JSON/JSONL only.
19. Pickle and arbitrary object execution are forbidden.
20. File writes are atomic where appropriate.
21. File permissions are restricted where supported.
22. Large raw API payloads, APK bytes and HTML are never stored.
23. Audit event count and payload sizes are bounded.
24. One malformed audit record must not corrupt unrelated records.
25. Public identifiers such as Package ID may be stored.
26. Public source URLs may be stored when needed for traceability.
27. Supabase credentials are never stored.
28. GitHub tokens are never stored.
29. AI provider keys are never stored.
30. Rollback conflicts require REVIEW instead of silent overwrite.
31. The layer is usable in dry-run mode.
32. The layer uses only the Python standard library.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import (
    Final,
    Iterable,
    Mapping,
    MutableMapping,
    Protocol,
    Sequence,
)


# ============================================================
# Component identity
# ============================================================

AUDIT_COMPONENT: Final[str] = "Audit & Rollback"
AUDIT_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Limits
# ============================================================

DEFAULT_MAX_AUDIT_EVENTS: Final[int] = 10_000
HARD_MAX_AUDIT_EVENTS: Final[int] = 100_000

DEFAULT_MAX_CHANGES_PER_EVENT: Final[int] = 100
HARD_MAX_CHANGES_PER_EVENT: Final[int] = 500

DEFAULT_MAX_ROLLBACK_OPERATIONS: Final[int] = 100
HARD_MAX_ROLLBACK_OPERATIONS: Final[int] = 500

DEFAULT_MAX_TEXT_LENGTH: Final[int] = 4_000
HARD_MAX_TEXT_LENGTH: Final[int] = 20_000

DEFAULT_MAX_METADATA_ITEMS: Final[int] = 100
HARD_MAX_METADATA_ITEMS: Final[int] = 500

DEFAULT_MAX_FILE_BYTES: Final[int] = 30_000_000
HARD_MAX_FILE_BYTES: Final[int] = 250_000_000


# ============================================================
# Secret detection
# ============================================================

SECRET_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:"
    r"secret|token|password|passwd|authorization|cookie|session|"
    r"api[_-]?key|service[_-]?role|private[_-]?key|access[_-]?key|"
    r"refresh[_-]?token|client[_-]?secret|bearer"
    r")"
)

JWT_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$"
)

LONG_SECRET_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9+/=_-]{48,}$"
)


# ============================================================
# Enums
# ============================================================

class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    SECURITY = "security"


class AuditEventType(str, Enum):
    DISCOVERY = "discovery"
    RESOLUTION = "resolution"
    APK = "apk"
    CONTENT = "content"
    DECISION = "decision"
    MEMORY = "memory"
    PUBLISH_PREPARE = "publish-prepare"
    PUBLISH_COMMIT = "publish-commit"
    PUBLISH_FAILURE = "publish-failure"
    REVIEW_REQUIRED = "review-required"
    ADMIN_BLOCK = "admin-block"
    TOMBSTONE_BLOCK = "tombstone-block"
    ROLLBACK_PLAN = "rollback-plan"
    ROLLBACK_APPROVED = "rollback-approved"
    ROLLBACK_REJECTED = "rollback-rejected"
    ROLLBACK_EXECUTED = "rollback-executed"
    ROLLBACK_FAILURE = "rollback-failure"
    SECURITY = "security"
    OPERATOR = "operator"


class ChangeKind(str, Enum):
    INSERT = "insert"
    UPDATE = "update"
    REPAIR = "repair"
    NOOP = "noop"


class Ownership(str, Enum):
    ENGINE = "engine"
    ADMIN = "admin"
    UNKNOWN = "unknown"


class RollbackState(str, Enum):
    PLANNED = "planned"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    BLOCKED = "blocked"


class RollbackOperationKind(str, Enum):
    RESTORE_FIELD = "restore-field"
    CLEAR_ENGINE_FIELD = "clear-engine-field"
    RESTORE_RECORD = "restore-record"
    REVERT_INSERT = "revert-insert"
    NOOP = "noop"


class RollbackBlockReason(str, Enum):
    NONE = "none"
    ADMIN_OWNED_FIELD = "admin-owned-field"
    TOMBSTONE = "tombstone"
    CURRENT_VALUE_CHANGED = "current-value-changed"
    MISSING_ORIGINAL_EVENT = "missing-original-event"
    UNSUPPORTED_CHANGE = "unsupported-change"
    POLICY = "policy"
    INVALID_SNAPSHOT = "invalid-snapshot"
    MANUAL_APPROVAL_REQUIRED = "manual-approval-required"


# ============================================================
# Helpers
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).isoformat()


def parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    text = str(value).strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def clean_text(
    value: object,
    *,
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
) -> str:
    text = str(value).replace("\x00", "")

    text = (
        text.replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    if len(text) > max_length:
        text = text[:max_length]

    return text


def looks_secret_like(
    field_name: str,
    value: object,
) -> bool:
    if SECRET_NAME_RE.search(
        field_name
    ):
        return True

    if not isinstance(
        value,
        str,
    ):
        return False

    text = value.strip()

    if not text:
        return False

    if JWT_RE.fullmatch(
        text
    ):
        return True

    if LONG_SECRET_RE.fullmatch(
        text
    ):
        lowered = text.lower()

        if not lowered.startswith(
            (
                "http://",
                "https://",
                "org.",
                "com.",
                "io.",
                "net.",
            )
        ):
            return True

    return False


def safe_value(
    value: object,
    *,
    field_name: str = "",
    depth: int = 0,
    max_depth: int = 6,
    max_items: int = DEFAULT_MAX_METADATA_ITEMS,
) -> object:
    if looks_secret_like(
        field_name,
        value,
    ):
        return "[REDACTED]"

    if depth >= max_depth:
        return "[MAX_DEPTH]"

    if value is None:
        return None

    if isinstance(
        value,
        (bool, int, float),
    ):
        return value

    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if isinstance(
        value,
        datetime,
    ):
        return isoformat_utc(
            value
        )

    if isinstance(
        value,
        str,
    ):
        return clean_text(
            value
        )

    if is_dataclass(
        value
    ):
        return safe_value(
            asdict(value),
            depth=depth + 1,
            max_depth=max_depth,
            max_items=max_items,
        )

    if isinstance(
        value,
        Mapping,
    ):
        output: dict[
            str,
            object,
        ] = {}

        for index, (key, item) in enumerate(
            value.items()
        ):
            if index >= max_items:
                output[
                    "__truncated__"
                ] = True
                break

            safe_key = clean_text(
                key,
                max_length=128,
            )

            if not safe_key:
                continue

            output[
                safe_key
            ] = safe_value(
                item,
                field_name=safe_key,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
            )

        return output

    if isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        output_list: list[
            object
        ] = []

        for index, item in enumerate(
            value
        ):
            if index >= max_items:
                output_list.append(
                    "[TRUNCATED]"
                )
                break

            output_list.append(
                safe_value(
                    item,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_items=max_items,
                )
            )

        return output_list

    return clean_text(
        value
    )


def safe_mapping(
    mapping: Mapping[str, object] | None,
) -> dict[str, object]:
    if not mapping:
        return {}

    value = safe_value(
        mapping
    )

    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


def stable_json(
    value: object,
) -> str:
    return json.dumps(
        safe_value(
            value
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default,
    )


def json_default(
    value: object,
) -> object:
    if isinstance(
        value,
        datetime,
    ):
        return isoformat_utc(
            value
        )

    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if is_dataclass(
        value
    ):
        return asdict(
            value
        )

    return str(
        value
    )


def fingerprint(
    value: object,
) -> str:
    return hashlib.sha256(
        stable_json(
            value
        ).encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# Policy
# ============================================================

@dataclass(frozen=True, slots=True)
class AuditPolicy:
    enabled: bool = True

    max_events: int = DEFAULT_MAX_AUDIT_EVENTS
    max_changes_per_event: int = DEFAULT_MAX_CHANGES_PER_EVENT
    max_rollback_operations: int = DEFAULT_MAX_ROLLBACK_OPERATIONS

    automatic_rollback_enabled: bool = False
    require_manual_approval: bool = True

    protect_admin_fields: bool = True
    protect_tombstones: bool = True
    require_current_value_match: bool = True

    allow_revert_insert: bool = False
    allow_restore_missing_engine_fields: bool = True

    retain_before_snapshot: bool = True
    retain_after_snapshot: bool = True

    def validate(self) -> None:
        if not (
            1
            <= self.max_events
            <= HARD_MAX_AUDIT_EVENTS
        ):
            raise ValueError(
                "max_events outside allowed range."
            )

        if not (
            1
            <= self.max_changes_per_event
            <= HARD_MAX_CHANGES_PER_EVENT
        ):
            raise ValueError(
                "max_changes_per_event outside allowed range."
            )

        if not (
            1
            <= self.max_rollback_operations
            <= HARD_MAX_ROLLBACK_OPERATIONS
        ):
            raise ValueError(
                "max_rollback_operations outside allowed range."
            )

        if (
            self.automatic_rollback_enabled
            and self.require_manual_approval
        ):
            raise ValueError(
                "automatic_rollback_enabled conflicts with manual approval."
            )

        if not self.protect_admin_fields:
            raise ValueError(
                "Admin field protection must remain enabled."
            )

        if not self.protect_tombstones:
            raise ValueError(
                "Tombstone protection must remain enabled."
            )


# ============================================================
# Snapshot models
# ============================================================

@dataclass(frozen=True, slots=True)
class FieldSnapshot:
    name: str
    value: object
    ownership: Ownership = Ownership.UNKNOWN

    def to_dict(self) -> dict[str, object]:
        return {
            "name": clean_text(
                self.name,
                max_length=128,
            ),
            "value": safe_value(
                self.value,
                field_name=self.name,
            ),
            "ownership": self.ownership.value,
        }

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, object],
    ) -> "FieldSnapshot":
        name = clean_text(
            raw.get(
                "name",
                "",
            ),
            max_length=128,
        )

        if not name:
            raise ValueError(
                "FieldSnapshot name cannot be empty."
            )

        ownership_raw = str(
            raw.get(
                "ownership",
                Ownership.UNKNOWN.value,
            )
        )

        try:
            ownership = Ownership(
                ownership_raw
            )
        except ValueError:
            ownership = Ownership.UNKNOWN

        return cls(
            name=name,
            value=safe_value(
                raw.get(
                    "value"
                ),
                field_name=name,
            ),
            ownership=ownership,
        )


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    package_id: str | None
    record_id: str | None

    exists: bool
    tombstoned: bool

    fields: Mapping[
        str,
        FieldSnapshot,
    ]

    captured_at: datetime = field(
        default_factory=utc_now
    )

    fingerprint: str | None = None

    def with_fingerprint(
        self,
    ) -> "ApplicationSnapshot":
        calculated = snapshot_fingerprint(
            self
        )

        return ApplicationSnapshot(
            package_id=self.package_id,
            record_id=self.record_id,
            exists=self.exists,
            tombstoned=self.tombstoned,
            fields=self.fields,
            captured_at=self.captured_at,
            fingerprint=calculated,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "record_id": self.record_id,
            "exists": self.exists,
            "tombstoned": self.tombstoned,
            "fields": {
                key: value.to_dict()
                for key, value in sorted(
                    self.fields.items()
                )
            },
            "captured_at": isoformat_utc(
                self.captured_at
            ),
            "fingerprint": (
                self.fingerprint
                or snapshot_fingerprint(
                    self
                )
            ),
        }

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, object],
    ) -> "ApplicationSnapshot":
        fields_raw = raw.get(
            "fields"
        )

        fields: dict[
            str,
            FieldSnapshot,
        ] = {}

        if isinstance(
            fields_raw,
            Mapping,
        ):
            for key, value in fields_raw.items():
                if not isinstance(
                    value,
                    Mapping,
                ):
                    continue

                merged = dict(
                    value
                )

                merged.setdefault(
                    "name",
                    str(key),
                )

                try:
                    field_snapshot = FieldSnapshot.from_dict(
                        merged
                    )
                except Exception:
                    continue

                fields[
                    field_snapshot.name
                ] = field_snapshot

        snapshot = cls(
            package_id=(
                clean_text(
                    raw.get(
                        "package_id"
                    ),
                    max_length=300,
                )
                if raw.get(
                    "package_id"
                )
                else None
            ),
            record_id=(
                clean_text(
                    raw.get(
                        "record_id"
                    ),
                    max_length=300,
                )
                if raw.get(
                    "record_id"
                )
                else None
            ),
            exists=bool(
                raw.get(
                    "exists",
                    False,
                )
            ),
            tombstoned=bool(
                raw.get(
                    "tombstoned",
                    False,
                )
            ),
            fields=fields,
            captured_at=parse_datetime(
                raw.get(
                    "captured_at"
                )
            ) or utc_now(),
            fingerprint=(
                clean_text(
                    raw.get(
                        "fingerprint"
                    ),
                    max_length=128,
                )
                if raw.get(
                    "fingerprint"
                )
                else None
            ),
        )

        return snapshot


def snapshot_fingerprint(
    snapshot: ApplicationSnapshot,
) -> str:
    payload = {
        "package_id": snapshot.package_id,
        "record_id": snapshot.record_id,
        "exists": snapshot.exists,
        "tombstoned": snapshot.tombstoned,
        "fields": {
            key: field_snapshot.to_dict()
            for key, field_snapshot in sorted(
                snapshot.fields.items()
            )
        },
    }

    return fingerprint(
        payload
    )


# ============================================================
# Change models
# ============================================================

@dataclass(frozen=True, slots=True)
class FieldChange:
    field_name: str

    before: object
    after: object

    ownership_before: Ownership
    ownership_after: Ownership

    changed: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "field_name": self.field_name,
            "before": safe_value(
                self.before,
                field_name=self.field_name,
            ),
            "after": safe_value(
                self.after,
                field_name=self.field_name,
            ),
            "ownership_before": self.ownership_before.value,
            "ownership_after": self.ownership_after.value,
            "changed": self.changed,
        }


def compute_field_changes(
    before: ApplicationSnapshot,
    after: ApplicationSnapshot,
    *,
    max_changes: int = DEFAULT_MAX_CHANGES_PER_EVENT,
) -> list[FieldChange]:
    names = sorted(
        set(
            before.fields
        )
        | set(
            after.fields
        )
    )

    output: list[
        FieldChange
    ] = []

    for name in names:
        if len(output) >= max_changes:
            break

        before_field = before.fields.get(
            name
        )

        after_field = after.fields.get(
            name
        )

        before_value = (
            before_field.value
            if before_field
            else None
        )

        after_value = (
            after_field.value
            if after_field
            else None
        )

        ownership_before = (
            before_field.ownership
            if before_field
            else Ownership.UNKNOWN
        )

        ownership_after = (
            after_field.ownership
            if after_field
            else Ownership.UNKNOWN
        )

        changed = (
            safe_value(
                before_value,
                field_name=name,
            )
            != safe_value(
                after_value,
                field_name=name,
            )
            or ownership_before
            != ownership_after
        )

        if not changed:
            continue

        output.append(
            FieldChange(
                field_name=name,
                before=before_value,
                after=after_value,
                ownership_before=ownership_before,
                ownership_after=ownership_after,
                changed=True,
            )
        )

    return output


# ============================================================
# Audit event model
# ============================================================

@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    event_type: AuditEventType
    severity: AuditSeverity

    run_id: str | None
    app_key: str | None
    package_id: str | None

    message: str

    timestamp: datetime

    change_kind: ChangeKind = ChangeKind.NOOP

    before: ApplicationSnapshot | None = None
    after: ApplicationSnapshot | None = None

    changes: Sequence[
        FieldChange
    ] = field(
        default_factory=tuple
    )

    metadata: Mapping[
        str,
        object,
    ] = field(
        default_factory=dict
    )

    previous_event_id: str | None = None

    fingerprint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "run_id": self.run_id,
            "app_key": self.app_key,
            "package_id": self.package_id,
            "message": self.message,
            "timestamp": isoformat_utc(
                self.timestamp
            ),
            "change_kind": self.change_kind.value,
            "before": (
                self.before.to_dict()
                if self.before
                else None
            ),
            "after": (
                self.after.to_dict()
                if self.after
                else None
            ),
            "changes": [
                change.to_dict()
                for change in self.changes
            ],
            "metadata": safe_mapping(
                self.metadata
            ),
            "previous_event_id": self.previous_event_id,
            "fingerprint": (
                self.fingerprint
                or audit_event_fingerprint(
                    self
                )
            ),
        }


def audit_event_fingerprint(
    event: AuditEvent,
) -> str:
    payload = {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "severity": event.severity.value,
        "run_id": event.run_id,
        "app_key": event.app_key,
        "package_id": event.package_id,
        "message": event.message,
        "timestamp": isoformat_utc(
            event.timestamp
        ),
        "change_kind": event.change_kind.value,
        "before": (
            event.before.to_dict()
            if event.before
            else None
        ),
        "after": (
            event.after.to_dict()
            if event.after
            else None
        ),
        "changes": [
            change.to_dict()
            for change in event.changes
        ],
        "metadata": safe_mapping(
            event.metadata
        ),
        "previous_event_id": event.previous_event_id,
    }

    return fingerprint(
        payload
    )


def create_event_id(
    *,
    run_id: str | None,
    app_key: str | None,
    event_type: AuditEventType,
    timestamp: datetime | None = None,
) -> str:
    timestamp = timestamp or utc_now()

    seed = {
        "run_id": run_id,
        "app_key": app_key,
        "event_type": event_type.value,
        "timestamp": isoformat_utc(
            timestamp
        ),
        "nonce": os.urandom(
            16
        ).hex(),
    }

    return (
        "audit_"
        + fingerprint(
            seed
        )[:32]
    )


# ============================================================
# Audit store
# ============================================================

@dataclass(slots=True)
class AuditStore:
    events: list[
        AuditEvent
    ] = field(
        default_factory=list
    )

    created_at: datetime = field(
        default_factory=utc_now
    )

    updated_at: datetime = field(
        default_factory=utc_now
    )

    def append(
        self,
        event: AuditEvent,
        *,
        policy: AuditPolicy,
    ) -> None:
        policy.validate()

        self.events.append(
            event
        )

        if len(
            self.events
        ) > policy.max_events:
            self.events = self.events[
                -policy.max_events:
            ]

        self.updated_at = utc_now()

    def find(
        self,
        event_id: str,
    ) -> AuditEvent | None:
        for event in reversed(
            self.events
        ):
            if event.event_id == event_id:
                return event

        return None

    def events_for_app(
        self,
        app_key: str,
    ) -> list[AuditEvent]:
        return [
            event
            for event in self.events
            if event.app_key == app_key
        ]

    def latest_for_app(
        self,
        app_key: str,
    ) -> AuditEvent | None:
        for event in reversed(
            self.events
        ):
            if event.app_key == app_key:
                return event

        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "component": AUDIT_COMPONENT,
            "schema_version": AUDIT_SCHEMA_VERSION,
            "created_at": isoformat_utc(
                self.created_at
            ),
            "updated_at": isoformat_utc(
                self.updated_at
            ),
            "events": [
                event.to_dict()
                for event in self.events
            ],
        }


# ============================================================
# Audit backend
# ============================================================

class AuditBackend(Protocol):
    def append(
        self,
        event: AuditEvent,
    ) -> None:
        ...


class NullAuditBackend:
    def append(
        self,
        event: AuditEvent,
    ) -> None:
        del event


class InMemoryAuditBackend:
    def __init__(
        self,
        *,
        policy: AuditPolicy | None = None,
    ) -> None:
        self.policy = (
            policy
            or AuditPolicy()
        )

        self.policy.validate()

        self.store = AuditStore()

    def append(
        self,
        event: AuditEvent,
    ) -> None:
        self.store.append(
            event,
            policy=self.policy,
        )


class JsonlAuditBackend:
    def __init__(
        self,
        path: str | Path,
        *,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        if not (
            1_000
            <= max_file_bytes
            <= HARD_MAX_FILE_BYTES
        ):
            raise ValueError(
                "max_file_bytes outside allowed range."
            )

        self.path = Path(
            path
        )

        self.max_file_bytes = max_file_bytes

    def append(
        self,
        event: AuditEvent,
    ) -> None:
        payload = json.dumps(
            event.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=json_default,
        ) + "\n"

        encoded = payload.encode(
            "utf-8"
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if self.path.exists():
            try:
                current_size = self.path.stat().st_size
            except OSError:
                current_size = 0

            if (
                current_size
                + len(encoded)
                > self.max_file_bytes
            ):
                return

        with self.path.open(
            "ab"
        ) as handle:
            handle.write(
                encoded
            )

        try:
            os.chmod(
                self.path,
                0o600,
            )
        except OSError:
            pass


class CompositeAuditBackend:
    def __init__(
        self,
        backends: Iterable[
            AuditBackend
        ],
    ) -> None:
        self.backends = list(
            backends
        )

    def append(
        self,
        event: AuditEvent,
    ) -> None:
        for backend in self.backends:
            try:
                backend.append(
                    event
                )
            except Exception:
                continue


# ============================================================
# Auditor
# ============================================================

class EngineAuditor:
    def __init__(
        self,
        *,
        policy: AuditPolicy | None = None,
        backend: AuditBackend | None = None,
    ) -> None:
        self.policy = (
            policy
            or AuditPolicy()
        )

        self.policy.validate()

        self.backend = (
            backend
            or InMemoryAuditBackend(
                policy=self.policy
            )
        )

        self._last_event_id: str | None = None

    def record(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        message: str,
        *,
        run_id: str | None = None,
        app_key: str | None = None,
        package_id: str | None = None,
        change_kind: ChangeKind = ChangeKind.NOOP,
        before: ApplicationSnapshot | None = None,
        after: ApplicationSnapshot | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> AuditEvent | None:
        if not self.policy.enabled:
            return None

        timestamp = utc_now()

        changes: list[
            FieldChange
        ] = []

        if (
            before is not None
            and after is not None
        ):
            changes = compute_field_changes(
                before,
                after,
                max_changes=self.policy.max_changes_per_event,
            )

        event = AuditEvent(
            event_id=create_event_id(
                run_id=run_id,
                app_key=app_key,
                event_type=event_type,
                timestamp=timestamp,
            ),
            event_type=event_type,
            severity=severity,
            run_id=(
                clean_text(
                    run_id,
                    max_length=200,
                )
                if run_id
                else None
            ),
            app_key=(
                clean_text(
                    app_key,
                    max_length=300,
                )
                if app_key
                else None
            ),
            package_id=(
                clean_text(
                    package_id,
                    max_length=300,
                )
                if package_id
                else None
            ),
            message=clean_text(
                message
            ),
            timestamp=timestamp,
            change_kind=change_kind,
            before=(
                before.with_fingerprint()
                if before
                else None
            ),
            after=(
                after.with_fingerprint()
                if after
                else None
            ),
            changes=tuple(
                changes
            ),
            metadata=safe_mapping(
                metadata
            ),
            previous_event_id=self._last_event_id,
        )

        final_event = AuditEvent(
            **{
                **event.__dict__,
                "fingerprint": audit_event_fingerprint(
                    event
                ),
            }
        )

        try:
            self.backend.append(
                final_event
            )
        except Exception:
            return None

        self._last_event_id = final_event.event_id

        return final_event

    def record_publication_prepare(
        self,
        *,
        run_id: str,
        app_key: str,
        package_id: str | None,
        change_kind: ChangeKind,
        before: ApplicationSnapshot,
        after: ApplicationSnapshot,
        metadata: Mapping[str, object] | None = None,
    ) -> AuditEvent | None:
        return self.record(
            AuditEventType.PUBLISH_PREPARE,
            AuditSeverity.INFO,
            "Publisher change prepared.",
            run_id=run_id,
            app_key=app_key,
            package_id=package_id,
            change_kind=change_kind,
            before=before,
            after=after,
            metadata=metadata,
        )

    def record_publication_commit(
        self,
        *,
        run_id: str,
        app_key: str,
        package_id: str | None,
        change_kind: ChangeKind,
        before: ApplicationSnapshot,
        after: ApplicationSnapshot,
        metadata: Mapping[str, object] | None = None,
    ) -> AuditEvent | None:
        return self.record(
            AuditEventType.PUBLISH_COMMIT,
            AuditSeverity.INFO,
            "Publisher change committed.",
            run_id=run_id,
            app_key=app_key,
            package_id=package_id,
            change_kind=change_kind,
            before=before,
            after=after,
            metadata=metadata,
        )

    def record_publication_failure(
        self,
        *,
        run_id: str,
        app_key: str,
        package_id: str | None,
        error: object,
        metadata: Mapping[str, object] | None = None,
    ) -> AuditEvent | None:
        return self.record(
            AuditEventType.PUBLISH_FAILURE,
            AuditSeverity.HIGH,
            "Publisher change failed.",
            run_id=run_id,
            app_key=app_key,
            package_id=package_id,
            metadata={
                "error": clean_text(
                    error
                ),
                **safe_mapping(
                    metadata
                ),
            },
        )

    def record_security_block(
        self,
        *,
        run_id: str | None,
        app_key: str | None,
        package_id: str | None,
        reason: object,
        tombstone: bool = False,
    ) -> AuditEvent | None:
        return self.record(
            (
                AuditEventType.TOMBSTONE_BLOCK
                if tombstone
                else AuditEventType.ADMIN_BLOCK
            ),
            AuditSeverity.SECURITY,
            clean_text(
                reason
            ),
            run_id=run_id,
            app_key=app_key,
            package_id=package_id,
        )


# ============================================================
# Snapshot builders
# ============================================================

def build_snapshot(
    *,
    package_id: str | None,
    record_id: str | None,
    exists: bool,
    tombstoned: bool,
    values: Mapping[str, object],
    ownership: Mapping[str, Ownership | str] | None = None,
) -> ApplicationSnapshot:
    ownership = ownership or {}

    fields: dict[
        str,
        FieldSnapshot,
    ] = {}

    for key, value in values.items():
        field_name = clean_text(
            key,
            max_length=128,
        )

        if not field_name:
            continue

        ownership_value = ownership.get(
            field_name,
            Ownership.UNKNOWN,
        )

        if isinstance(
            ownership_value,
            Ownership,
        ):
            normalized_ownership = ownership_value

        else:
            try:
                normalized_ownership = Ownership(
                    str(
                        ownership_value
                    )
                )
            except ValueError:
                normalized_ownership = Ownership.UNKNOWN

        fields[
            field_name
        ] = FieldSnapshot(
            name=field_name,
            value=safe_value(
                value,
                field_name=field_name,
            ),
            ownership=normalized_ownership,
        )

    snapshot = ApplicationSnapshot(
        package_id=(
            clean_text(
                package_id,
                max_length=300,
            )
            if package_id
            else None
        ),
        record_id=(
            clean_text(
                record_id,
                max_length=300,
            )
            if record_id
            else None
        ),
        exists=bool(
            exists
        ),
        tombstoned=bool(
            tombstoned
        ),
        fields=fields,
    )

    return snapshot.with_fingerprint()


# ============================================================
# Rollback models
# ============================================================

@dataclass(frozen=True, slots=True)
class RollbackOperation:
    kind: RollbackOperationKind
    field_name: str | None

    expected_current_value: object
    restore_value: object

    ownership: Ownership

    blocked: bool = False
    block_reason: RollbackBlockReason = RollbackBlockReason.NONE

    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "field_name": self.field_name,
            "expected_current_value": safe_value(
                self.expected_current_value,
                field_name=self.field_name or "",
            ),
            "restore_value": safe_value(
                self.restore_value,
                field_name=self.field_name or "",
            ),
            "ownership": self.ownership.value,
            "blocked": self.blocked,
            "block_reason": self.block_reason.value,
            "message": self.message,
        }


@dataclass(slots=True)
class RollbackPlan:
    plan_id: str
    original_event_id: str

    run_id: str | None
    app_key: str | None
    package_id: str | None

    state: RollbackState

    operations: list[
        RollbackOperation
    ]

    created_at: datetime = field(
        default_factory=utc_now
    )

    approved_at: datetime | None = None
    executed_at: datetime | None = None

    approval_note: str | None = None
    failure_reason: str | None = None

    metadata: dict[
        str,
        object,
    ] = field(
        default_factory=dict
    )

    @property
    def blocked(self) -> bool:
        return any(
            operation.blocked
            for operation in self.operations
        )

    @property
    def executable_operations(
        self,
    ) -> list[RollbackOperation]:
        return [
            operation
            for operation in self.operations
            if not operation.blocked
            and operation.kind
            != RollbackOperationKind.NOOP
        ]

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "original_event_id": self.original_event_id,
            "run_id": self.run_id,
            "app_key": self.app_key,
            "package_id": self.package_id,
            "state": self.state.value,
            "operations": [
                operation.to_dict()
                for operation in self.operations
            ],
            "created_at": isoformat_utc(
                self.created_at
            ),
            "approved_at": isoformat_utc(
                self.approved_at
            ),
            "executed_at": isoformat_utc(
                self.executed_at
            ),
            "approval_note": self.approval_note,
            "failure_reason": self.failure_reason,
            "blocked": self.blocked,
            "metadata": safe_mapping(
                self.metadata
            ),
        }


def create_plan_id(
    original_event_id: str,
) -> str:
    return (
        "rollback_"
        + fingerprint(
            {
                "original_event_id": original_event_id,
                "time": isoformat_utc(
                    utc_now()
                ),
                "nonce": os.urandom(
                    16
                ).hex(),
            }
        )[:32]
    )


# ============================================================
# Rollback planning
# ============================================================

def plan_rollback(
    event: AuditEvent,
    *,
    current: ApplicationSnapshot | None = None,
    policy: AuditPolicy | None = None,
) -> RollbackPlan:
    policy = (
        policy
        or AuditPolicy()
    )

    policy.validate()

    operations: list[
        RollbackOperation
    ] = []

    if event.before is None or event.after is None:
        return RollbackPlan(
            plan_id=create_plan_id(
                event.event_id
            ),
            original_event_id=event.event_id,
            run_id=event.run_id,
            app_key=event.app_key,
            package_id=event.package_id,
            state=RollbackState.BLOCKED,
            operations=[
                RollbackOperation(
                    kind=RollbackOperationKind.NOOP,
                    field_name=None,
                    expected_current_value=None,
                    restore_value=None,
                    ownership=Ownership.UNKNOWN,
                    blocked=True,
                    block_reason=RollbackBlockReason.INVALID_SNAPSHOT,
                    message=(
                        "Original audit event has no complete before/after snapshot."
                    ),
                )
            ],
        )

    before = event.before
    after = event.after

    if (
        current is not None
        and current.tombstoned
        and policy.protect_tombstones
    ):
        return RollbackPlan(
            plan_id=create_plan_id(
                event.event_id
            ),
            original_event_id=event.event_id,
            run_id=event.run_id,
            app_key=event.app_key,
            package_id=event.package_id,
            state=RollbackState.BLOCKED,
            operations=[
                RollbackOperation(
                    kind=RollbackOperationKind.NOOP,
                    field_name=None,
                    expected_current_value=None,
                    restore_value=None,
                    ownership=Ownership.UNKNOWN,
                    blocked=True,
                    block_reason=RollbackBlockReason.TOMBSTONE,
                    message=(
                        "Current application has an active tombstone."
                    ),
                )
            ],
        )

    if event.change_kind == ChangeKind.INSERT:
        blocked = not policy.allow_revert_insert

        operations.append(
            RollbackOperation(
                kind=(
                    RollbackOperationKind.REVERT_INSERT
                    if not blocked
                    else RollbackOperationKind.NOOP
                ),
                field_name=None,
                expected_current_value=True,
                restore_value=False,
                ownership=Ownership.ENGINE,
                blocked=blocked,
                block_reason=(
                    RollbackBlockReason.POLICY
                    if blocked
                    else RollbackBlockReason.NONE
                ),
                message=(
                    "Revert engine-created record."
                    if not blocked
                    else (
                        "Insert rollback is disabled; no automatic deletion "
                        "will be planned."
                    )
                ),
            )
        )

    else:
        for change in event.changes:
            if len(operations) >= policy.max_rollback_operations:
                break

            field_name = change.field_name

            current_field = (
                current.fields.get(
                    field_name
                )
                if current is not None
                else None
            )

            current_value = (
                current_field.value
                if current_field is not None
                else change.after
            )

            current_ownership = (
                current_field.ownership
                if current_field is not None
                else change.ownership_after
            )

            if (
                policy.protect_admin_fields
                and current_ownership
                == Ownership.ADMIN
            ):
                operations.append(
                    RollbackOperation(
                        kind=RollbackOperationKind.NOOP,
                        field_name=field_name,
                        expected_current_value=current_value,
                        restore_value=change.before,
                        ownership=current_ownership,
                        blocked=True,
                        block_reason=RollbackBlockReason.ADMIN_OWNED_FIELD,
                        message=(
                            "Admin-owned field cannot be rolled back automatically."
                        ),
                    )
                )
                continue

            if (
                policy.require_current_value_match
                and current is not None
                and safe_value(
                    current_value,
                    field_name=field_name,
                )
                != safe_value(
                    change.after,
                    field_name=field_name,
                )
            ):
                operations.append(
                    RollbackOperation(
                        kind=RollbackOperationKind.NOOP,
                        field_name=field_name,
                        expected_current_value=change.after,
                        restore_value=change.before,
                        ownership=current_ownership,
                        blocked=True,
                        block_reason=RollbackBlockReason.CURRENT_VALUE_CHANGED,
                        message=(
                            "Current field value changed after the original event."
                        ),
                    )
                )
                continue

            if change.before is None:
                if not policy.allow_restore_missing_engine_fields:
                    operations.append(
                        RollbackOperation(
                            kind=RollbackOperationKind.NOOP,
                            field_name=field_name,
                            expected_current_value=change.after,
                            restore_value=None,
                            ownership=current_ownership,
                            blocked=True,
                            block_reason=RollbackBlockReason.POLICY,
                            message=(
                                "Clearing newly created engine fields is disabled."
                            ),
                        )
                    )
                    continue

                operation_kind = RollbackOperationKind.CLEAR_ENGINE_FIELD

            else:
                operation_kind = RollbackOperationKind.RESTORE_FIELD

            operations.append(
                RollbackOperation(
                    kind=operation_kind,
                    field_name=field_name,
                    expected_current_value=change.after,
                    restore_value=change.before,
                    ownership=current_ownership,
                    blocked=False,
                    block_reason=RollbackBlockReason.NONE,
                    message=(
                        "Field may be restored to its previous engine-safe value."
                    ),
                )
            )

    if not operations:
        operations.append(
            RollbackOperation(
                kind=RollbackOperationKind.NOOP,
                field_name=None,
                expected_current_value=None,
                restore_value=None,
                ownership=Ownership.UNKNOWN,
                blocked=False,
                block_reason=RollbackBlockReason.NONE,
                message="No rollback operation is required.",
            )
        )

    any_blocked = any(
        operation.blocked
        for operation in operations
    )

    if any_blocked:
        state = RollbackState.REVIEW

    elif policy.require_manual_approval:
        state = RollbackState.REVIEW

    elif policy.automatic_rollback_enabled:
        state = RollbackState.APPROVED

    else:
        state = RollbackState.PLANNED

    return RollbackPlan(
        plan_id=create_plan_id(
            event.event_id
        ),
        original_event_id=event.event_id,
        run_id=event.run_id,
        app_key=event.app_key,
        package_id=event.package_id,
        state=state,
        operations=operations,
        metadata={
            "change_kind": event.change_kind.value,
            "original_event_fingerprint": (
                event.fingerprint
                or audit_event_fingerprint(
                    event
                )
            ),
        },
    )


# ============================================================
# Rollback approval
# ============================================================

def approve_rollback(
    plan: RollbackPlan,
    *,
    operator_note: str,
    policy: AuditPolicy | None = None,
) -> RollbackPlan:
    policy = (
        policy
        or AuditPolicy()
    )

    policy.validate()

    if plan.blocked:
        raise PermissionError(
            "Blocked rollback plan cannot be approved."
        )

    note = clean_text(
        operator_note,
        max_length=2_000,
    )

    if not note:
        raise ValueError(
            "Rollback approval requires an operator note."
        )

    plan.state = RollbackState.APPROVED
    plan.approved_at = utc_now()
    plan.approval_note = note

    return plan


def reject_rollback(
    plan: RollbackPlan,
    *,
    operator_note: str,
) -> RollbackPlan:
    note = clean_text(
        operator_note,
        max_length=2_000,
    )

    if not note:
        raise ValueError(
            "Rollback rejection requires an operator note."
        )

    plan.state = RollbackState.REJECTED
    plan.approval_note = note

    return plan


# ============================================================
# Rollback execution contract
# ============================================================

@dataclass(frozen=True, slots=True)
class RollbackMutation:
    field_name: str | None
    value: object
    operation: RollbackOperationKind

    expected_current_value: object = None

    def to_dict(self) -> dict[str, object]:
        return {
            "field_name": self.field_name,
            "value": safe_value(
                self.value,
                field_name=self.field_name or "",
            ),
            "operation": self.operation.value,
            "expected_current_value": safe_value(
                self.expected_current_value,
                field_name=self.field_name or "",
            ),
        }


@dataclass(frozen=True, slots=True)
class RollbackExecutionRequest:
    plan_id: str
    original_event_id: str

    app_key: str | None
    package_id: str | None

    mutations: Sequence[
        RollbackMutation
    ]

    manual_approval_present: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "original_event_id": self.original_event_id,
            "app_key": self.app_key,
            "package_id": self.package_id,
            "mutations": [
                mutation.to_dict()
                for mutation in self.mutations
            ],
            "manual_approval_present": self.manual_approval_present,
        }


def build_execution_request(
    plan: RollbackPlan,
    *,
    policy: AuditPolicy | None = None,
) -> RollbackExecutionRequest:
    policy = (
        policy
        or AuditPolicy()
    )

    policy.validate()

    if plan.blocked:
        raise PermissionError(
            "Rollback plan contains blocked operations."
        )

    if (
        policy.require_manual_approval
        and plan.state
        != RollbackState.APPROVED
    ):
        raise PermissionError(
            "Rollback plan requires manual approval."
        )

    if plan.state in {
        RollbackState.REJECTED,
        RollbackState.EXECUTED,
        RollbackState.FAILED,
        RollbackState.BLOCKED,
    }:
        raise ValueError(
            f"Rollback plan state cannot execute: {plan.state.value}"
        )

    mutations: list[
        RollbackMutation
    ] = []

    for operation in plan.executable_operations:
        if operation.kind == RollbackOperationKind.RESTORE_FIELD:
            mutations.append(
                RollbackMutation(
                    field_name=operation.field_name,
                    value=operation.restore_value,
                    operation=operation.kind,
                    expected_current_value=operation.expected_current_value,
                )
            )

        elif operation.kind == RollbackOperationKind.CLEAR_ENGINE_FIELD:
            mutations.append(
                RollbackMutation(
                    field_name=operation.field_name,
                    value=None,
                    operation=operation.kind,
                    expected_current_value=operation.expected_current_value,
                )
            )

        elif operation.kind == RollbackOperationKind.REVERT_INSERT:
            mutations.append(
                RollbackMutation(
                    field_name=None,
                    value=None,
                    operation=operation.kind,
                    expected_current_value=True,
                )
            )

    return RollbackExecutionRequest(
        plan_id=plan.plan_id,
        original_event_id=plan.original_event_id,
        app_key=plan.app_key,
        package_id=plan.package_id,
        mutations=tuple(
            mutations
        ),
        manual_approval_present=(
            plan.approved_at
            is not None
        ),
    )


# ============================================================
# Plan completion
# ============================================================

def mark_rollback_executed(
    plan: RollbackPlan,
) -> RollbackPlan:
    if plan.state != RollbackState.APPROVED:
        raise ValueError(
            "Only approved rollback plans can be marked executed."
        )

    plan.state = RollbackState.EXECUTED
    plan.executed_at = utc_now()
    plan.failure_reason = None

    return plan


def mark_rollback_failed(
    plan: RollbackPlan,
    error: object,
) -> RollbackPlan:
    plan.state = RollbackState.FAILED
    plan.failure_reason = clean_text(
        error
    )

    return plan


# ============================================================
# Snapshot comparison
# ============================================================

@dataclass(frozen=True, slots=True)
class SnapshotComparison:
    same_identity: bool
    same_tombstone_state: bool
    same_fingerprint: bool

    changed_fields: Sequence[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "same_identity": self.same_identity,
            "same_tombstone_state": self.same_tombstone_state,
            "same_fingerprint": self.same_fingerprint,
            "changed_fields": list(
                self.changed_fields
            ),
        }


def compare_snapshots(
    left: ApplicationSnapshot,
    right: ApplicationSnapshot,
) -> SnapshotComparison:
    changes = compute_field_changes(
        left,
        right,
        max_changes=HARD_MAX_CHANGES_PER_EVENT,
    )

    return SnapshotComparison(
        same_identity=(
            left.package_id
            == right.package_id
            and left.record_id
            == right.record_id
        ),
        same_tombstone_state=(
            left.tombstoned
            == right.tombstoned
        ),
        same_fingerprint=(
            snapshot_fingerprint(
                left
            )
            == snapshot_fingerprint(
                right
            )
        ),
        changed_fields=tuple(
            change.field_name
            for change in changes
        ),
    )


# ============================================================
# Local audit store serialization
# ============================================================

def write_audit_store(
    store: AuditStore,
    path: str | Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> Path:
    if not (
        1_000
        <= max_file_bytes
        <= HARD_MAX_FILE_BYTES
    ):
        raise ValueError(
            "max_file_bytes outside allowed range."
        )

    target = Path(
        path
    )

    payload = json.dumps(
        store.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=json_default,
    )

    encoded = payload.encode(
        "utf-8"
    )

    if len(
        encoded
    ) > max_file_bytes:
        raise ValueError(
            "Audit store exceeds configured maximum size."
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary_raw = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(
            target.parent
        ),
    )

    temporary = Path(
        temporary_raw
    )

    try:
        with os.fdopen(
            fd,
            "wb",
        ) as handle:
            handle.write(
                encoded
            )

            handle.flush()

            try:
                os.fsync(
                    handle.fileno()
                )
            except OSError:
                pass

        try:
            os.chmod(
                temporary,
                0o600,
            )
        except OSError:
            pass

        os.replace(
            temporary,
            target,
        )

        try:
            os.chmod(
                target,
                0o600,
            )
        except OSError:
            pass

    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass

    return target


# ============================================================
# Diagnostics
# ============================================================

def diagnostic_before_snapshot() -> ApplicationSnapshot:
    return build_snapshot(
        package_id="org.osguide.diagnostic",
        record_id="diagnostic-1",
        exists=True,
        tombstoned=False,
        values={
            "name": "Diagnostic App",
            "version": "1.0.0",
            "apk_url": "https://example.org/app-1.0.0.apk",
            "short_description": "Old text",
        },
        ownership={
            "name": Ownership.ADMIN,
            "version": Ownership.ENGINE,
            "apk_url": Ownership.ENGINE,
            "short_description": Ownership.ENGINE,
        },
    )


def diagnostic_after_snapshot() -> ApplicationSnapshot:
    return build_snapshot(
        package_id="org.osguide.diagnostic",
        record_id="diagnostic-1",
        exists=True,
        tombstoned=False,
        values={
            "name": "Diagnostic App",
            "version": "1.1.0",
            "apk_url": "https://example.org/app-1.1.0.apk",
            "short_description": "New text",
        },
        ownership={
            "name": Ownership.ADMIN,
            "version": Ownership.ENGINE,
            "apk_url": Ownership.ENGINE,
            "short_description": Ownership.ENGINE,
        },
    )


def run_audit_diagnostic() -> dict[str, object]:
    policy = AuditPolicy()

    backend = InMemoryAuditBackend(
        policy=policy
    )

    auditor = EngineAuditor(
        policy=policy,
        backend=backend,
    )

    before = diagnostic_before_snapshot()
    after = diagnostic_after_snapshot()

    event = auditor.record_publication_commit(
        run_id="diagnostic-run",
        app_key="package:org.osguide.diagnostic",
        package_id="org.osguide.diagnostic",
        change_kind=ChangeKind.UPDATE,
        before=before,
        after=after,
        metadata={
            "diagnostic": True,
            "api_key": "must-be-redacted",
        },
    )

    if event is None:
        raise RuntimeError(
            "Diagnostic event was not recorded."
        )

    plan = plan_rollback(
        event,
        current=after,
        policy=policy,
    )

    return {
        "event_id": event.event_id,
        "event_fingerprint": event.fingerprint,
        "change_count": len(
            event.changes
        ),
        "plan_state": plan.state.value,
        "operation_count": len(
            plan.operations
        ),
        "blocked": plan.blocked,
        "event_count": len(
            backend.store.events
        ),
    }


def run_admin_protection_diagnostic() -> dict[str, object]:
    policy = AuditPolicy()

    before = diagnostic_before_snapshot()
    after = diagnostic_after_snapshot()

    current_values = {
        key: field_snapshot.value
        for key, field_snapshot in after.fields.items()
    }

    current_values[
        "name"
    ] = "Admin Custom Name"

    current = build_snapshot(
        package_id=after.package_id,
        record_id=after.record_id,
        exists=True,
        tombstoned=False,
        values=current_values,
        ownership={
            "name": Ownership.ADMIN,
            "version": Ownership.ENGINE,
            "apk_url": Ownership.ENGINE,
            "short_description": Ownership.ENGINE,
        },
    )

    event = AuditEvent(
        event_id="diagnostic-event",
        event_type=AuditEventType.PUBLISH_COMMIT,
        severity=AuditSeverity.INFO,
        run_id="diagnostic-run",
        app_key="package:org.osguide.diagnostic",
        package_id="org.osguide.diagnostic",
        message="Diagnostic publication.",
        timestamp=utc_now(),
        change_kind=ChangeKind.UPDATE,
        before=before,
        after=after,
        changes=tuple(
            compute_field_changes(
                before,
                after,
            )
        ),
    )

    plan = plan_rollback(
        event,
        current=current,
        policy=policy,
    )

    return {
        "state": plan.state.value,
        "blocked": plan.blocked,
        "operations": [
            operation.to_dict()
            for operation in plan.operations
        ],
    }


def run_tombstone_protection_diagnostic() -> dict[str, object]:
    policy = AuditPolicy()

    before = diagnostic_before_snapshot()
    after = diagnostic_after_snapshot()

    current = build_snapshot(
        package_id=after.package_id,
        record_id=after.record_id,
        exists=True,
        tombstoned=True,
        values={
            key: field_snapshot.value
            for key, field_snapshot in after.fields.items()
        },
        ownership={
            key: field_snapshot.ownership
            for key, field_snapshot in after.fields.items()
        },
    )

    event = AuditEvent(
        event_id="diagnostic-tombstone-event",
        event_type=AuditEventType.PUBLISH_COMMIT,
        severity=AuditSeverity.INFO,
        run_id="diagnostic-run",
        app_key="package:org.osguide.diagnostic",
        package_id="org.osguide.diagnostic",
        message="Diagnostic publication.",
        timestamp=utc_now(),
        change_kind=ChangeKind.UPDATE,
        before=before,
        after=after,
        changes=tuple(
            compute_field_changes(
                before,
                after,
            )
        ),
    )

    plan = plan_rollback(
        event,
        current=current,
        policy=policy,
    )

    return {
        "state": plan.state.value,
        "blocked": plan.blocked,
        "reason": (
            plan.operations[0].block_reason.value
            if plan.operations
            else None
        ),
    }


# ============================================================
# Summary helpers
# ============================================================

def audit_event_summary(
    event: AuditEvent,
) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "severity": event.severity.value,
        "run_id": event.run_id,
        "app_key": event.app_key,
        "package_id": event.package_id,
        "change_kind": event.change_kind.value,
        "change_count": len(
            event.changes
        ),
        "timestamp": isoformat_utc(
            event.timestamp
        ),
        "fingerprint": (
            event.fingerprint
            or audit_event_fingerprint(
                event
            )
        ),
    }


def rollback_plan_summary(
    plan: RollbackPlan,
) -> dict[str, object]:
    blocked_operations = sum(
        1
        for operation in plan.operations
        if operation.blocked
    )

    return {
        "plan_id": plan.plan_id,
        "original_event_id": plan.original_event_id,
        "state": plan.state.value,
        "package_id": plan.package_id,
        "operation_count": len(
            plan.operations
        ),
        "blocked_operations": blocked_operations,
        "executable_operations": len(
            plan.executable_operations
        ),
        "approved_at": isoformat_utc(
            plan.approved_at
        ),
        "executed_at": isoformat_utc(
            plan.executed_at
        ),
    }


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "AUDIT_COMPONENT",
    "AUDIT_SCHEMA_VERSION",
    "ApplicationSnapshot",
    "AuditBackend",
    "AuditEvent",
    "AuditEventType",
    "AuditPolicy",
    "AuditSeverity",
    "AuditStore",
    "ChangeKind",
    "CompositeAuditBackend",
    "DEFAULT_MAX_AUDIT_EVENTS",
    "DEFAULT_MAX_CHANGES_PER_EVENT",
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_METADATA_ITEMS",
    "DEFAULT_MAX_ROLLBACK_OPERATIONS",
    "DEFAULT_MAX_TEXT_LENGTH",
    "EngineAuditor",
    "FieldChange",
    "FieldSnapshot",
    "InMemoryAuditBackend",
    "JsonlAuditBackend",
    "NullAuditBackend",
    "Ownership",
    "RollbackBlockReason",
    "RollbackExecutionRequest",
    "RollbackMutation",
    "RollbackOperation",
    "RollbackOperationKind",
    "RollbackPlan",
    "RollbackState",
    "SnapshotComparison",
    "approve_rollback",
    "audit_event_fingerprint",
    "audit_event_summary",
    "build_execution_request",
    "build_snapshot",
    "clean_text",
    "compare_snapshots",
    "compute_field_changes",
    "create_event_id",
    "create_plan_id",
    "diagnostic_after_snapshot",
    "diagnostic_before_snapshot",
    "fingerprint",
    "isoformat_utc",
    "json_default",
    "looks_secret_like",
    "mark_rollback_executed",
    "mark_rollback_failed",
    "parse_datetime",
    "plan_rollback",
    "reject_rollback",
    "rollback_plan_summary",
    "run_admin_protection_diagnostic",
    "run_audit_diagnostic",
    "run_tombstone_protection_diagnostic",
    "safe_mapping",
    "safe_value",
    "snapshot_fingerprint",
    "stable_json",
    "utc_now",
    "write_audit_store",
)
