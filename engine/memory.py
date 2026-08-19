"""
OSGuide Engine
Memory Layer

Purpose
-------
This module provides durable, security-conscious runtime memory for the
OSGuide automation engine.

The Memory Layer is designed to remember:
- discovered candidates already seen
- resolution attempts and outcomes
- APK intelligence outcomes
- content generation state
- Decision Engine outcomes
- publication attempts
- retry eligibility
- review-required state
- failure cooldowns
- application processing fingerprints
- bounded historical summaries
- existing-application repair state
- operator-visible notes
- run checkpoints

Architecture rules
------------------
1. Memory does not decide publication.
2. Memory does not write to Supabase application tables.
3. Memory does not contain secrets.
4. Secret-like values are rejected or redacted before persistence.
5. Package IDs may be stored because they are application identifiers,
   not credentials.
6. APK URLs, repository URLs and public source URLs may be stored when
   required for deduplication and repair.
7. Authentication tokens, API keys, passwords and cookies must never be
   stored.
8. Memory must remain bounded.
9. Corrupt memory must fail safely rather than crash the whole engine.
10. One bad record must not invalidate unrelated records.
11. Memory supports dry-run and live engine modes equally.
12. The engine must be able to forget stale transient failures.
13. Admin-review and tombstone-related states must not be silently erased.
14. Automatic retries use explicit cooldowns and attempt limits.
15. Repeated candidates should be deduplicated using stable fingerprints.
16. Memory records include schema versioning.
17. Memory writes are atomic when filesystem-backed.
18. Memory files use restrictive permissions where supported.
19. Memory serialization is deterministic.
20. No external code is executed from memory content.
21. No pickle or arbitrary-object deserialization is used.
22. JSON is the only built-in persistence format.
23. Memory can run fully in-memory for diagnostics and CI.
24. Memory supports checkpoint-style state for resumable runs.
25. Historical events are compact summaries, not full source dumps.
26. Full raw HTML, APK binaries and giant API responses are never stored.
27. Existing Admin-owned fields are never treated as engine memory.
28. Memory can record that an app was manually reviewed, but manual values
   remain owned by the database/Admin system.
29. An automatic "forget" operation never removes protected review blocks.
30. The module intentionally favors correctness and auditability over
   minimum line count.

Primary use
-----------
Discovery -> Resolver -> APK Intelligence -> Content Intelligence ->
Decision Engine -> Memory -> Publisher

Memory is used before and after Decision/Publisher:
- before processing: decide whether a candidate should be skipped,
  retried, reviewed, or processed again
- after processing: store the bounded result and next eligibility time

This file intentionally contains the stable Memory core. A later Supabase
memory adapter can implement the same backend protocol if durable remote
memory becomes desirable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import (
    Any,
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

MEMORY_COMPONENT: Final[str] = "Memory"
MEMORY_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Limits
# ============================================================

DEFAULT_MAX_RECORDS: Final[int] = 5_000
HARD_MAX_RECORDS: Final[int] = 50_000

DEFAULT_MAX_EVENTS_PER_RECORD: Final[int] = 30
HARD_MAX_EVENTS_PER_RECORD: Final[int] = 200

DEFAULT_MAX_GLOBAL_EVENTS: Final[int] = 500
HARD_MAX_GLOBAL_EVENTS: Final[int] = 5_000

DEFAULT_MAX_ATTEMPTS: Final[int] = 5
HARD_MAX_ATTEMPTS: Final[int] = 50

DEFAULT_FAILURE_COOLDOWN_MINUTES: Final[int] = 60
DEFAULT_REVIEW_COOLDOWN_MINUTES: Final[int] = 24 * 60
DEFAULT_SUCCESS_RECHECK_MINUTES: Final[int] = 7 * 24 * 60

MIN_COOLDOWN_MINUTES: Final[int] = 1
MAX_COOLDOWN_MINUTES: Final[int] = 365 * 24 * 60

MAX_KEY_LENGTH: Final[int] = 256
MAX_TEXT_LENGTH: Final[int] = 4_000
MAX_URL_LENGTH: Final[int] = 2_048
MAX_METADATA_ITEMS: Final[int] = 100
MAX_METADATA_VALUE_LENGTH: Final[int] = 2_000
MAX_MEMORY_FILE_BYTES: Final[int] = 20_000_000
MAX_CHECKPOINT_ITEMS: Final[int] = 1_000

PACKAGE_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$"
)

SAFE_KEY_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9._:/@+-]{1,256}$"
)

SECRET_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)(?:secret|token|password|passwd|authorization|cookie|api[_-]?key|"
    r"service[_-]?role|private[_-]?key|bearer|session)"
)

JWT_LIKE_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$"
)

LONG_SECRET_LIKE_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9+/=_-]{40,}$"
)


# ============================================================
# Enums
# ============================================================

class MemoryStatus(str, Enum):
    NEW = "new"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REVIEW = "review"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    PUBLISHED = "published"
    UPDATED = "updated"
    REPAIRED = "repaired"
    TOMBSTONED = "tombstoned"
    UNKNOWN = "unknown"


class MemoryEventKind(str, Enum):
    SEEN = "seen"
    STARTED = "started"
    RESOLVED = "resolved"
    APK_SELECTED = "apk-selected"
    CONTENT_BUILT = "content-built"
    DECIDED = "decided"
    PUBLISH_ATTEMPT = "publish-attempt"
    PUBLISHED = "published"
    UPDATED = "updated"
    REPAIRED = "repaired"
    REVIEW_REQUIRED = "review-required"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRY_SCHEDULED = "retry-scheduled"
    CHECKPOINT = "checkpoint"
    OPERATOR_NOTE = "operator-note"
    MEMORY_REPAIR = "memory-repair"


class RetryDecision(str, Enum):
    PROCESS = "process"
    SKIP_RECENT_SUCCESS = "skip-recent-success"
    WAIT_COOLDOWN = "wait-cooldown"
    REVIEW_REQUIRED = "review-required"
    BLOCKED = "blocked"
    ATTEMPTS_EXHAUSTED = "attempts-exhausted"


class MemoryBackendStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not-found"
    CORRUPT = "corrupt"
    FAILURE = "failure"


class ProtectedState(str, Enum):
    NONE = "none"
    REVIEW = "review"
    TOMBSTONE = "tombstone"
    ADMIN_BLOCK = "admin-block"


# ============================================================
# Utility helpers
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
    max_length: int = MAX_TEXT_LENGTH,
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
    name: str,
    value: object,
) -> bool:
    if SECRET_NAME_RE.search(name):
        return True

    if not isinstance(value, str):
        return False

    text = value.strip()

    if not text:
        return False

    if JWT_LIKE_RE.fullmatch(text):
        return True

    if LONG_SECRET_LIKE_RE.fullmatch(text):
        lowered = text.lower()

        safe_prefixes = (
            "http",
            "org.",
            "com.",
            "io.",
            "net.",
        )

        if not lowered.startswith(safe_prefixes):
            return True

    return False


def safe_metadata(
    metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    if not metadata:
        return {}

    output: dict[str, object] = {}

    for index, (key, value) in enumerate(metadata.items()):
        if index >= MAX_METADATA_ITEMS:
            break

        safe_key = clean_text(
            key,
            max_length=128,
        )

        if not safe_key:
            continue

        if looks_secret_like(
            safe_key,
            value,
        ):
            output[safe_key] = "[REDACTED]"
            continue

        output[safe_key] = safe_metadata_value(
            value
        )

    return output


def safe_metadata_value(
    value: object,
) -> object:
    if value is None:
        return None

    if isinstance(
        value,
        (bool, int, float),
    ):
        return value

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return isoformat_utc(
            value
        )

    if isinstance(value, str):
        return clean_text(
            value,
            max_length=MAX_METADATA_VALUE_LENGTH,
        )

    if isinstance(value, Mapping):
        return safe_metadata(
            value
        )

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [
            safe_metadata_value(item)
            for item in list(value)[:100]
        ]

    if is_dataclass(value):
        return safe_metadata(
            asdict(value)
        )

    return clean_text(
        value,
        max_length=MAX_METADATA_VALUE_LENGTH,
    )


def stable_json(
    value: object,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default,
    )


def json_default(
    value: object,
) -> object:
    if isinstance(value, datetime):
        return isoformat_utc(
            value
        )

    if isinstance(value, Enum):
        return value.value

    if is_dataclass(value):
        return asdict(value)

    return str(value)


# ============================================================
# Fingerprinting
# ============================================================

def fingerprint_text(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def fingerprint_mapping(
    value: Mapping[str, object],
) -> str:
    return fingerprint_text(
        stable_json(
            safe_metadata(value)
        )
    )


def normalize_package_id(
    package_id: str | None,
) -> str | None:
    if package_id is None:
        return None

    package_id = package_id.strip()

    if not package_id:
        return None

    if not PACKAGE_ID_RE.fullmatch(
        package_id
    ):
        return None

    return package_id


def normalize_public_url(
    url: str | None,
) -> str | None:
    if url is None:
        return None

    text = url.strip()

    if not text:
        return None

    if len(text) > MAX_URL_LENGTH:
        return None

    if not (
        text.startswith("https://")
        or text.startswith("http://")
    ):
        return None

    return text


def build_candidate_key(
    *,
    package_id: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    repository_url: str | None = None,
    name: str | None = None,
) -> str:
    """
    Build a stable candidate memory key.

    Priority:
    1. package ID
    2. repository URL
    3. source URL
    4. source type + normalized app name
    """

    package_id = normalize_package_id(
        package_id
    )

    if package_id:
        return (
            "package:"
            + package_id.lower()
        )

    repository_url = normalize_public_url(
        repository_url
    )

    if repository_url:
        return (
            "repo:"
            + fingerprint_text(
                repository_url.lower()
            )[:40]
        )

    source_url = normalize_public_url(
        source_url
    )

    if source_url:
        return (
            "source:"
            + fingerprint_text(
                source_url.lower()
            )[:40]
        )

    source_type = clean_text(
        source_type or "unknown",
        max_length=80,
    ).lower()

    normalized_name = clean_text(
        name or "unnamed",
        max_length=300,
    ).casefold()

    return (
        "name:"
        + fingerprint_text(
            source_type
            + "|"
            + normalized_name
        )[:40]
    )


def validate_memory_key(
    key: str,
) -> str:
    key = key.strip()

    if not key:
        raise ValueError(
            "Memory key cannot be empty."
        )

    if len(key) > MAX_KEY_LENGTH:
        raise ValueError(
            "Memory key exceeds maximum length."
        )

    if not SAFE_KEY_RE.fullmatch(
        key
    ):
        raise ValueError(
            "Memory key contains unsupported characters."
        )

    return key


# ============================================================
# Event model
# ============================================================

@dataclass(frozen=True, slots=True)
class MemoryEvent:
    kind: MemoryEventKind
    message: str
    timestamp: datetime = field(
        default_factory=utc_now
    )
    metadata: Mapping[str, object] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "message": clean_text(
                self.message,
                max_length=MAX_TEXT_LENGTH,
            ),
            "timestamp": isoformat_utc(
                self.timestamp
            ),
            "metadata": safe_metadata(
                self.metadata
            ),
        }

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, object],
    ) -> "MemoryEvent":
        kind_raw = raw.get(
            "kind",
            MemoryEventKind.SEEN.value,
        )

        try:
            kind = MemoryEventKind(
                str(kind_raw)
            )
        except ValueError:
            kind = MemoryEventKind.SEEN

        timestamp = parse_datetime(
            raw.get("timestamp")
        ) or utc_now()

        message = clean_text(
            raw.get("message", ""),
            max_length=MAX_TEXT_LENGTH,
        )

        metadata_raw = raw.get(
            "metadata"
        )

        metadata = (
            safe_metadata(
                metadata_raw
                if isinstance(
                    metadata_raw,
                    Mapping,
                )
                else {}
            )
        )

        return cls(
            kind=kind,
            message=message,
            timestamp=timestamp,
            metadata=metadata,
        )


# ============================================================
# Checkpoint model
# ============================================================

@dataclass(slots=True)
class RunCheckpoint:
    run_id: str
    stage: str
    completed_keys: list[str] = field(
        default_factory=list
    )
    failed_keys: list[str] = field(
        default_factory=list
    )
    review_keys: list[str] = field(
        default_factory=list
    )
    updated_at: datetime = field(
        default_factory=utc_now
    )

    def validate(self) -> None:
        self.run_id = clean_text(
            self.run_id,
            max_length=200,
        )

        self.stage = clean_text(
            self.stage,
            max_length=100,
        )

        if not self.run_id:
            raise ValueError(
                "Checkpoint run_id cannot be empty."
            )

        if not self.stage:
            raise ValueError(
                "Checkpoint stage cannot be empty."
            )

        self.completed_keys = _normalize_key_list(
            self.completed_keys
        )

        self.failed_keys = _normalize_key_list(
            self.failed_keys
        )

        self.review_keys = _normalize_key_list(
            self.review_keys
        )

    def to_dict(self) -> dict[str, object]:
        self.validate()

        return {
            "run_id": self.run_id,
            "stage": self.stage,
            "completed_keys": list(
                self.completed_keys
            ),
            "failed_keys": list(
                self.failed_keys
            ),
            "review_keys": list(
                self.review_keys
            ),
            "updated_at": isoformat_utc(
                self.updated_at
            ),
        }

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, object],
    ) -> "RunCheckpoint":
        checkpoint = cls(
            run_id=clean_text(
                raw.get("run_id", ""),
                max_length=200,
            ),
            stage=clean_text(
                raw.get("stage", ""),
                max_length=100,
            ),
            completed_keys=_as_string_list(
                raw.get(
                    "completed_keys"
                )
            ),
            failed_keys=_as_string_list(
                raw.get(
                    "failed_keys"
                )
            ),
            review_keys=_as_string_list(
                raw.get(
                    "review_keys"
                )
            ),
            updated_at=parse_datetime(
                raw.get("updated_at")
            ) or utc_now(),
        )

        checkpoint.validate()

        return checkpoint


def _as_string_list(
    value: object,
) -> list[str]:
    if not isinstance(
        value,
        Sequence,
    ) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return []

    return [
        str(item)
        for item in list(value)[:MAX_CHECKPOINT_ITEMS]
    ]


def _normalize_key_list(
    values: Iterable[str],
) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()

    for value in values:
        try:
            key = validate_memory_key(
                str(value)
            )
        except ValueError:
            continue

        if key in seen:
            continue

        seen.add(key)
        output.append(key)

        if len(output) >= MAX_CHECKPOINT_ITEMS:
            break

    return output


# ============================================================
# Memory record
# ============================================================

@dataclass(slots=True)
class MemoryRecord:
    key: str

    status: MemoryStatus = MemoryStatus.NEW
    protected_state: ProtectedState = ProtectedState.NONE

    first_seen_at: datetime = field(
        default_factory=utc_now
    )
    last_seen_at: datetime = field(
        default_factory=utc_now
    )
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    next_eligible_at: datetime | None = None

    attempts: int = 0
    consecutive_failures: int = 0

    package_id: str | None = None
    app_name: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    repository_url: str | None = None

    last_candidate_fingerprint: str | None = None
    last_resolution_fingerprint: str | None = None
    last_apk_fingerprint: str | None = None
    last_content_fingerprint: str | None = None
    last_decision_fingerprint: str | None = None
    last_publication_fingerprint: str | None = None

    last_decision_action: str | None = None
    last_error: str | None = None

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    events: list[MemoryEvent] = field(
        default_factory=list
    )

    def validate(
        self,
        *,
        max_events: int = DEFAULT_MAX_EVENTS_PER_RECORD,
    ) -> None:
        self.key = validate_memory_key(
            self.key
        )

        if self.attempts < 0:
            self.attempts = 0

        if self.consecutive_failures < 0:
            self.consecutive_failures = 0

        self.package_id = normalize_package_id(
            self.package_id
        )

        if self.app_name is not None:
            self.app_name = clean_text(
                self.app_name,
                max_length=500,
            ) or None

        if self.source_type is not None:
            self.source_type = clean_text(
                self.source_type,
                max_length=100,
            ) or None

        self.source_url = normalize_public_url(
            self.source_url
        )

        self.repository_url = normalize_public_url(
            self.repository_url
        )

        if self.last_decision_action is not None:
            self.last_decision_action = clean_text(
                self.last_decision_action,
                max_length=100,
            ) or None

        if self.last_error is not None:
            self.last_error = clean_text(
                self.last_error,
                max_length=MAX_TEXT_LENGTH,
            ) or None

        self.metadata = safe_metadata(
            self.metadata
        )

        self.events = [
            event
            for event in self.events
            if isinstance(
                event,
                MemoryEvent,
            )
        ][-max_events:]

    def add_event(
        self,
        kind: MemoryEventKind,
        message: str,
        *,
        metadata: Mapping[str, object] | None = None,
        max_events: int = DEFAULT_MAX_EVENTS_PER_RECORD,
    ) -> None:
        event = MemoryEvent(
            kind=kind,
            message=clean_text(
                message,
                max_length=MAX_TEXT_LENGTH,
            ),
            metadata=safe_metadata(
                metadata
            ),
        )

        self.events.append(
            event
        )

        if len(self.events) > max_events:
            self.events = self.events[
                -max_events:
            ]

    def to_dict(self) -> dict[str, object]:
        self.validate()

        return {
            "key": self.key,
            "status": self.status.value,
            "protected_state": self.protected_state.value,
            "first_seen_at": isoformat_utc(
                self.first_seen_at
            ),
            "last_seen_at": isoformat_utc(
                self.last_seen_at
            ),
            "last_attempt_at": isoformat_utc(
                self.last_attempt_at
            ),
            "last_success_at": isoformat_utc(
                self.last_success_at
            ),
            "next_eligible_at": isoformat_utc(
                self.next_eligible_at
            ),
            "attempts": self.attempts,
            "consecutive_failures": self.consecutive_failures,
            "package_id": self.package_id,
            "app_name": self.app_name,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "repository_url": self.repository_url,
            "last_candidate_fingerprint": self.last_candidate_fingerprint,
            "last_resolution_fingerprint": self.last_resolution_fingerprint,
            "last_apk_fingerprint": self.last_apk_fingerprint,
            "last_content_fingerprint": self.last_content_fingerprint,
            "last_decision_fingerprint": self.last_decision_fingerprint,
            "last_publication_fingerprint": self.last_publication_fingerprint,
            "last_decision_action": self.last_decision_action,
            "last_error": self.last_error,
            "metadata": safe_metadata(
                self.metadata
            ),
            "events": [
                event.to_dict()
                for event in self.events
            ],
        }

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, object],
        *,
        max_events: int = DEFAULT_MAX_EVENTS_PER_RECORD,
    ) -> "MemoryRecord":
        status_raw = raw.get(
            "status",
            MemoryStatus.UNKNOWN.value,
        )

        try:
            status = MemoryStatus(
                str(status_raw)
            )
        except ValueError:
            status = MemoryStatus.UNKNOWN

        protected_raw = raw.get(
            "protected_state",
            ProtectedState.NONE.value,
        )

        try:
            protected_state = ProtectedState(
                str(protected_raw)
            )
        except ValueError:
            protected_state = ProtectedState.NONE

        events_raw = raw.get(
            "events"
        )

        events: list[MemoryEvent] = []

        if isinstance(
            events_raw,
            Sequence,
        ) and not isinstance(
            events_raw,
            (str, bytes, bytearray),
        ):
            for item in list(events_raw)[
                -max_events:
            ]:
                if not isinstance(
                    item,
                    Mapping,
                ):
                    continue

                try:
                    events.append(
                        MemoryEvent.from_dict(
                            item
                        )
                    )
                except Exception:
                    continue

        metadata_raw = raw.get(
            "metadata"
        )

        record = cls(
            key=str(
                raw.get(
                    "key",
                    "",
                )
            ),
            status=status,
            protected_state=protected_state,
            first_seen_at=parse_datetime(
                raw.get("first_seen_at")
            ) or utc_now(),
            last_seen_at=parse_datetime(
                raw.get("last_seen_at")
            ) or utc_now(),
            last_attempt_at=parse_datetime(
                raw.get("last_attempt_at")
            ),
            last_success_at=parse_datetime(
                raw.get("last_success_at")
            ),
            next_eligible_at=parse_datetime(
                raw.get("next_eligible_at")
            ),
            attempts=_safe_int(
                raw.get("attempts"),
                minimum=0,
                default=0,
            ),
            consecutive_failures=_safe_int(
                raw.get(
                    "consecutive_failures"
                ),
                minimum=0,
                default=0,
            ),
            package_id=(
                str(raw["package_id"])
                if raw.get("package_id") is not None
                else None
            ),
            app_name=(
                str(raw["app_name"])
                if raw.get("app_name") is not None
                else None
            ),
            source_type=(
                str(raw["source_type"])
                if raw.get("source_type") is not None
                else None
            ),
            source_url=(
                str(raw["source_url"])
                if raw.get("source_url") is not None
                else None
            ),
            repository_url=(
                str(raw["repository_url"])
                if raw.get("repository_url") is not None
                else None
            ),
            last_candidate_fingerprint=_optional_text(
                raw.get(
                    "last_candidate_fingerprint"
                ),
                128,
            ),
            last_resolution_fingerprint=_optional_text(
                raw.get(
                    "last_resolution_fingerprint"
                ),
                128,
            ),
            last_apk_fingerprint=_optional_text(
                raw.get(
                    "last_apk_fingerprint"
                ),
                128,
            ),
            last_content_fingerprint=_optional_text(
                raw.get(
                    "last_content_fingerprint"
                ),
                128,
            ),
            last_decision_fingerprint=_optional_text(
                raw.get(
                    "last_decision_fingerprint"
                ),
                128,
            ),
            last_publication_fingerprint=_optional_text(
                raw.get(
                    "last_publication_fingerprint"
                ),
                128,
            ),
            last_decision_action=_optional_text(
                raw.get(
                    "last_decision_action"
                ),
                100,
            ),
            last_error=_optional_text(
                raw.get(
                    "last_error"
                ),
                MAX_TEXT_LENGTH,
            ),
            metadata=safe_metadata(
                metadata_raw
                if isinstance(
                    metadata_raw,
                    Mapping,
                )
                else {}
            ),
            events=events,
        )

        record.validate(
            max_events=max_events
        )

        return record


def _safe_int(
    value: object,
    *,
    minimum: int,
    default: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(
        minimum,
        parsed,
    )


def _optional_text(
    value: object,
    max_length: int,
) -> str | None:
    if value is None:
        return None

    cleaned = clean_text(
        value,
        max_length=max_length,
    )

    return cleaned or None


# ============================================================
# Memory policy
# ============================================================

@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    max_records: int = DEFAULT_MAX_RECORDS
    max_events_per_record: int = DEFAULT_MAX_EVENTS_PER_RECORD
    max_global_events: int = DEFAULT_MAX_GLOBAL_EVENTS

    max_attempts: int = DEFAULT_MAX_ATTEMPTS

    failure_cooldown_minutes: int = DEFAULT_FAILURE_COOLDOWN_MINUTES
    review_cooldown_minutes: int = DEFAULT_REVIEW_COOLDOWN_MINUTES
    success_recheck_minutes: int = DEFAULT_SUCCESS_RECHECK_MINUTES

    preserve_review_state: bool = True
    preserve_tombstones: bool = True
    preserve_admin_blocks: bool = True

    forget_transient_failures_after_days: int = 30
    prune_success_after_days: int = 180

    allow_retry_after_failure: bool = True
    allow_recheck_after_success: bool = True

    def validate(self) -> None:
        if not 1 <= self.max_records <= HARD_MAX_RECORDS:
            raise ValueError(
                "max_records outside allowed range."
            )

        if not (
            1
            <= self.max_events_per_record
            <= HARD_MAX_EVENTS_PER_RECORD
        ):
            raise ValueError(
                "max_events_per_record outside allowed range."
            )

        if not (
            1
            <= self.max_global_events
            <= HARD_MAX_GLOBAL_EVENTS
        ):
            raise ValueError(
                "max_global_events outside allowed range."
            )

        if not 1 <= self.max_attempts <= HARD_MAX_ATTEMPTS:
            raise ValueError(
                "max_attempts outside allowed range."
            )

        for value in (
            self.failure_cooldown_minutes,
            self.review_cooldown_minutes,
            self.success_recheck_minutes,
        ):
            if not (
                MIN_COOLDOWN_MINUTES
                <= value
                <= MAX_COOLDOWN_MINUTES
            ):
                raise ValueError(
                    "Memory cooldown outside allowed range."
                )

        if self.forget_transient_failures_after_days < 1:
            raise ValueError(
                "forget_transient_failures_after_days must be positive."
            )

        if self.prune_success_after_days < 1:
            raise ValueError(
                "prune_success_after_days must be positive."
            )


# ============================================================
# Store model
# ============================================================

@dataclass(slots=True)
class MemoryStore:
    schema_version: str = MEMORY_SCHEMA_VERSION

    records: dict[str, MemoryRecord] = field(
        default_factory=dict
    )

    checkpoints: dict[str, RunCheckpoint] = field(
        default_factory=dict
    )

    global_events: list[MemoryEvent] = field(
        default_factory=list
    )

    created_at: datetime = field(
        default_factory=utc_now
    )

    updated_at: datetime = field(
        default_factory=utc_now
    )

    def validate(
        self,
        *,
        policy: MemoryPolicy,
    ) -> None:
        policy.validate()

        cleaned_records: dict[
            str,
            MemoryRecord,
        ] = {}

        for key, record in list(
            self.records.items()
        ):
            if len(cleaned_records) >= policy.max_records:
                break

            if not isinstance(
                record,
                MemoryRecord,
            ):
                continue

            try:
                record.validate(
                    max_events=policy.max_events_per_record
                )

                normalized_key = validate_memory_key(
                    key
                )

            except Exception:
                continue

            if record.key != normalized_key:
                record.key = normalized_key

            cleaned_records[
                normalized_key
            ] = record

        self.records = cleaned_records

        cleaned_checkpoints: dict[
            str,
            RunCheckpoint,
        ] = {}

        for run_id, checkpoint in self.checkpoints.items():
            if not isinstance(
                checkpoint,
                RunCheckpoint,
            ):
                continue

            try:
                checkpoint.validate()
            except Exception:
                continue

            cleaned_checkpoints[
                clean_text(
                    run_id,
                    max_length=200,
                )
            ] = checkpoint

        self.checkpoints = cleaned_checkpoints

        self.global_events = [
            event
            for event in self.global_events
            if isinstance(
                event,
                MemoryEvent,
            )
        ][
            -policy.max_global_events:
        ]

    def add_global_event(
        self,
        kind: MemoryEventKind,
        message: str,
        *,
        metadata: Mapping[str, object] | None = None,
        policy: MemoryPolicy,
    ) -> None:
        self.global_events.append(
            MemoryEvent(
                kind=kind,
                message=clean_text(
                    message,
                    max_length=MAX_TEXT_LENGTH,
                ),
                metadata=safe_metadata(
                    metadata
                ),
            )
        )

        if len(self.global_events) > policy.max_global_events:
            self.global_events = self.global_events[
                -policy.max_global_events:
            ]

        self.updated_at = utc_now()

    def to_dict(
        self,
        *,
        policy: MemoryPolicy,
    ) -> dict[str, object]:
        self.validate(
            policy=policy
        )

        return {
            "schema_version": self.schema_version,
            "component": MEMORY_COMPONENT,
            "created_at": isoformat_utc(
                self.created_at
            ),
            "updated_at": isoformat_utc(
                self.updated_at
            ),
            "records": {
                key: record.to_dict()
                for key, record in sorted(
                    self.records.items()
                )
            },
            "checkpoints": {
                key: checkpoint.to_dict()
                for key, checkpoint in sorted(
                    self.checkpoints.items()
                )
            },
            "global_events": [
                event.to_dict()
                for event in self.global_events
            ],
        }

    @classmethod
    def from_dict(
        cls,
        raw: Mapping[str, object],
        *,
        policy: MemoryPolicy,
    ) -> "MemoryStore":
        policy.validate()

        records: dict[str, MemoryRecord] = {}

        records_raw = raw.get(
            "records"
        )

        if isinstance(
            records_raw,
            Mapping,
        ):
            for key, record_raw in records_raw.items():
                if len(records) >= policy.max_records:
                    break

                if not isinstance(
                    record_raw,
                    Mapping,
                ):
                    continue

                merged = dict(
                    record_raw
                )

                merged.setdefault(
                    "key",
                    str(key),
                )

                try:
                    record = MemoryRecord.from_dict(
                        merged,
                        max_events=policy.max_events_per_record,
                    )

                except Exception:
                    continue

                records[
                    record.key
                ] = record

        checkpoints: dict[
            str,
            RunCheckpoint,
        ] = {}

        checkpoints_raw = raw.get(
            "checkpoints"
        )

        if isinstance(
            checkpoints_raw,
            Mapping,
        ):
            for run_id, checkpoint_raw in checkpoints_raw.items():
                if not isinstance(
                    checkpoint_raw,
                    Mapping,
                ):
                    continue

                try:
                    checkpoint = RunCheckpoint.from_dict(
                        checkpoint_raw
                    )
                except Exception:
                    continue

                checkpoints[
                    clean_text(
                        run_id,
                        max_length=200,
                    )
                ] = checkpoint

        global_events: list[
            MemoryEvent
        ] = []

        global_events_raw = raw.get(
            "global_events"
        )

        if isinstance(
            global_events_raw,
            Sequence,
        ) and not isinstance(
            global_events_raw,
            (str, bytes, bytearray),
        ):
            for item in list(global_events_raw)[
                -policy.max_global_events:
            ]:
                if not isinstance(
                    item,
                    Mapping,
                ):
                    continue

                try:
                    global_events.append(
                        MemoryEvent.from_dict(
                            item
                        )
                    )
                except Exception:
                    continue

        store = cls(
            schema_version=clean_text(
                raw.get(
                    "schema_version",
                    MEMORY_SCHEMA_VERSION,
                ),
                max_length=50,
            ),
            records=records,
            checkpoints=checkpoints,
            global_events=global_events,
            created_at=parse_datetime(
                raw.get("created_at")
            ) or utc_now(),
            updated_at=parse_datetime(
                raw.get("updated_at")
            ) or utc_now(),
        )

        store.validate(
            policy=policy
        )

        return store


# ============================================================
# Backend protocol
# ============================================================

@dataclass(slots=True)
class MemoryBackendResult:
    status: MemoryBackendStatus
    store: MemoryStore | None = None
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return (
            self.status == MemoryBackendStatus.SUCCESS
            and self.error is None
        )


class MemoryBackend(Protocol):
    def load(
        self,
        *,
        policy: MemoryPolicy,
    ) -> MemoryBackendResult:
        ...

    def save(
        self,
        store: MemoryStore,
        *,
        policy: MemoryPolicy,
    ) -> MemoryBackendResult:
        ...


# ============================================================
# In-memory backend
# ============================================================

class InMemoryBackend:
    def __init__(
        self,
        initial_store: MemoryStore | None = None,
    ) -> None:
        self._store = (
            initial_store
            or MemoryStore()
        )

    def load(
        self,
        *,
        policy: MemoryPolicy,
    ) -> MemoryBackendResult:
        try:
            raw = self._store.to_dict(
                policy=policy
            )

            copied = MemoryStore.from_dict(
                raw,
                policy=policy,
            )

            return MemoryBackendResult(
                status=MemoryBackendStatus.SUCCESS,
                store=copied,
            )

        except Exception as exc:
            return MemoryBackendResult(
                status=MemoryBackendStatus.FAILURE,
                error=clean_text(
                    exc,
                    max_length=500,
                ),
            )

    def save(
        self,
        store: MemoryStore,
        *,
        policy: MemoryPolicy,
    ) -> MemoryBackendResult:
        try:
            raw = store.to_dict(
                policy=policy
            )

            self._store = MemoryStore.from_dict(
                raw,
                policy=policy,
            )

            return MemoryBackendResult(
                status=MemoryBackendStatus.SUCCESS,
                store=self._store,
            )

        except Exception as exc:
            return MemoryBackendResult(
                status=MemoryBackendStatus.FAILURE,
                error=clean_text(
                    exc,
                    max_length=500,
                ),
            )


# ============================================================
# JSON file backend
# ============================================================

class JsonFileMemoryBackend:
    """
    Local JSON backend with atomic replacement.

    Intended for:
    - local development
    - CI artifacts
    - GitHub Actions workspace/cache use

    Do not commit runtime memory files that contain operational history
    unless that is a deliberate project decision.
    """

    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(
            path
        )

    def load(
        self,
        *,
        policy: MemoryPolicy,
    ) -> MemoryBackendResult:
        policy.validate()

        if not self.path.exists():
            return MemoryBackendResult(
                status=MemoryBackendStatus.NOT_FOUND,
                store=MemoryStore(),
            )

        try:
            stat = self.path.stat()

            if stat.st_size > MAX_MEMORY_FILE_BYTES:
                return MemoryBackendResult(
                    status=MemoryBackendStatus.CORRUPT,
                    error=(
                        "Memory file exceeds configured safety size."
                    ),
                )

            raw_text = self.path.read_text(
                encoding="utf-8"
            )

            parsed = json.loads(
                raw_text
            )

            if not isinstance(
                parsed,
                Mapping,
            ):
                return MemoryBackendResult(
                    status=MemoryBackendStatus.CORRUPT,
                    error=(
                        "Memory file root must be a JSON object."
                    ),
                )

            store = MemoryStore.from_dict(
                parsed,
                policy=policy,
            )

            return MemoryBackendResult(
                status=MemoryBackendStatus.SUCCESS,
                store=store,
            )

        except json.JSONDecodeError as exc:
            return MemoryBackendResult(
                status=MemoryBackendStatus.CORRUPT,
                error=(
                    "Memory JSON is invalid: "
                    + clean_text(
                        exc,
                        max_length=500,
                    )
                ),
            )

        except Exception as exc:
            return MemoryBackendResult(
                status=MemoryBackendStatus.FAILURE,
                error=clean_text(
                    exc,
                    max_length=500,
                ),
            )

    def save(
        self,
        store: MemoryStore,
        *,
        policy: MemoryPolicy,
    ) -> MemoryBackendResult:
        policy.validate()

        try:
            payload = store.to_dict(
                policy=policy
            )

            serialized = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                default=json_default,
            )

            encoded = serialized.encode(
                "utf-8"
            )

            if len(encoded) > MAX_MEMORY_FILE_BYTES:
                return MemoryBackendResult(
                    status=MemoryBackendStatus.FAILURE,
                    error=(
                        "Serialized memory exceeds safety size."
                    ),
                )

            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temp_fd, temp_path_raw = tempfile.mkstemp(
                prefix=self.path.name + ".",
                suffix=".tmp",
                dir=str(
                    self.path.parent
                ),
            )

            temp_path = Path(
                temp_path_raw
            )

            try:
                with os.fdopen(
                    temp_fd,
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
                        temp_path,
                        0o600,
                    )
                except OSError:
                    pass

                os.replace(
                    temp_path,
                    self.path,
                )

                try:
                    os.chmod(
                        self.path,
                        0o600,
                    )
                except OSError:
                    pass

            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass

            return MemoryBackendResult(
                status=MemoryBackendStatus.SUCCESS,
                store=store,
            )

        except Exception as exc:
            return MemoryBackendResult(
                status=MemoryBackendStatus.FAILURE,
                error=clean_text(
                    exc,
                    max_length=500,
                ),
            )


# ============================================================
# Memory manager
# ============================================================

class EngineMemory:
    def __init__(
        self,
        backend: MemoryBackend,
        *,
        policy: MemoryPolicy | None = None,
    ) -> None:
        self.backend = backend
        self.policy = (
            policy
            or MemoryPolicy()
        )

        self.policy.validate()

        self.store = MemoryStore()

        self.loaded = False

    def load(self) -> MemoryBackendResult:
        result = self.backend.load(
            policy=self.policy
        )

        if result.status == MemoryBackendStatus.NOT_FOUND:
            self.store = MemoryStore()

            self.loaded = True

            return MemoryBackendResult(
                status=MemoryBackendStatus.SUCCESS,
                store=self.store,
            )

        if result.succeeded and result.store is not None:
            self.store = result.store

            self.loaded = True

        return result

    def save(self) -> MemoryBackendResult:
        self.store.updated_at = utc_now()

        self.store.validate(
            policy=self.policy
        )

        return self.backend.save(
            self.store,
            policy=self.policy,
        )

    def ensure_loaded(self) -> None:
        if self.loaded:
            return

        result = self.load()

        if not result.succeeded:
            raise RuntimeError(
                result.error
                or "Unable to load engine memory."
            )

    def get(
        self,
        key: str,
    ) -> MemoryRecord | None:
        self.ensure_loaded()

        key = validate_memory_key(
            key
        )

        return self.store.records.get(
            key
        )

    def get_or_create(
        self,
        key: str,
        *,
        package_id: str | None = None,
        app_name: str | None = None,
        source_type: str | None = None,
        source_url: str | None = None,
        repository_url: str | None = None,
    ) -> MemoryRecord:
        self.ensure_loaded()

        key = validate_memory_key(
            key
        )

        existing = self.store.records.get(
            key
        )

        now = utc_now()

        if existing is not None:
            existing.last_seen_at = now

            _merge_identity_fields(
                existing,
                package_id=package_id,
                app_name=app_name,
                source_type=source_type,
                source_url=source_url,
                repository_url=repository_url,
            )

            return existing

        if len(self.store.records) >= self.policy.max_records:
            self.prune()

        if len(self.store.records) >= self.policy.max_records:
            raise RuntimeError(
                "Memory record limit reached and no safe records could be pruned."
            )

        record = MemoryRecord(
            key=key,
            status=MemoryStatus.NEW,
            first_seen_at=now,
            last_seen_at=now,
            package_id=normalize_package_id(
                package_id
            ),
            app_name=clean_text(
                app_name or "",
                max_length=500,
            ) or None,
            source_type=clean_text(
                source_type or "",
                max_length=100,
            ) or None,
            source_url=normalize_public_url(
                source_url
            ),
            repository_url=normalize_public_url(
                repository_url
            ),
        )

        record.add_event(
            MemoryEventKind.SEEN,
            "Candidate first observed by OSGuide memory.",
            max_events=self.policy.max_events_per_record,
        )

        self.store.records[
            key
        ] = record

        return record

    def mark_processing(
        self,
        key: str,
    ) -> MemoryRecord:
        record = self.require(
            key
        )

        now = utc_now()

        record.status = MemoryStatus.PROCESSING
        record.last_attempt_at = now
        record.last_seen_at = now
        record.attempts += 1

        record.add_event(
            MemoryEventKind.STARTED,
            "Engine processing started.",
            metadata={
                "attempt": record.attempts,
            },
            max_events=self.policy.max_events_per_record,
        )

        return record

    def mark_success(
        self,
        key: str,
        *,
        status: MemoryStatus = MemoryStatus.SUCCESS,
        action: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> MemoryRecord:
        record = self.require(
            key
        )

        if status not in {
            MemoryStatus.SUCCESS,
            MemoryStatus.PUBLISHED,
            MemoryStatus.UPDATED,
            MemoryStatus.REPAIRED,
            MemoryStatus.SKIPPED,
        }:
            raise ValueError(
                "mark_success received a non-success status."
            )

        now = utc_now()

        record.status = status
        record.last_success_at = now
        record.last_seen_at = now
        record.consecutive_failures = 0
        record.last_error = None
        record.last_decision_action = (
            clean_text(
                action,
                max_length=100,
            )
            if action
            else record.last_decision_action
        )

        if self.policy.allow_recheck_after_success:
            record.next_eligible_at = (
                now
                + timedelta(
                    minutes=self.policy.success_recheck_minutes
                )
            )
        else:
            record.next_eligible_at = None

        event_kind = {
            MemoryStatus.PUBLISHED: MemoryEventKind.PUBLISHED,
            MemoryStatus.UPDATED: MemoryEventKind.UPDATED,
            MemoryStatus.REPAIRED: MemoryEventKind.REPAIRED,
            MemoryStatus.SKIPPED: MemoryEventKind.SKIPPED,
        }.get(
            status,
            MemoryEventKind.DECIDED,
        )

        record.add_event(
            event_kind,
            "Processing completed successfully.",
            metadata=safe_metadata(
                metadata
            ),
            max_events=self.policy.max_events_per_record,
        )

        return record

    def mark_failure(
        self,
        key: str,
        error: object,
        *,
        retryable: bool = True,
        metadata: Mapping[str, object] | None = None,
    ) -> MemoryRecord:
        record = self.require(
            key
        )

        now = utc_now()

        record.status = MemoryStatus.FAILED
        record.last_seen_at = now
        record.consecutive_failures += 1
        record.last_error = clean_text(
            error,
            max_length=MAX_TEXT_LENGTH,
        )

        if (
            retryable
            and self.policy.allow_retry_after_failure
            and record.attempts < self.policy.max_attempts
        ):
            multiplier = min(
                8,
                max(
                    1,
                    record.consecutive_failures,
                ),
            )

            cooldown = (
                self.policy.failure_cooldown_minutes
                * multiplier
            )

            cooldown = min(
                cooldown,
                MAX_COOLDOWN_MINUTES,
            )

            record.next_eligible_at = (
                now
                + timedelta(
                    minutes=cooldown
                )
            )
        else:
            record.next_eligible_at = None

        record.add_event(
            MemoryEventKind.FAILED,
            record.last_error
            or "Processing failed.",
            metadata=safe_metadata(
                metadata
            ),
            max_events=self.policy.max_events_per_record,
        )

        if record.next_eligible_at is not None:
            record.add_event(
                MemoryEventKind.RETRY_SCHEDULED,
                "Automatic retry scheduled after cooldown.",
                metadata={
                    "next_eligible_at": isoformat_utc(
                        record.next_eligible_at
                    ),
                },
                max_events=self.policy.max_events_per_record,
            )

        return record

    def mark_review(
        self,
        key: str,
        reason: object,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> MemoryRecord:
        record = self.require(
            key
        )

        now = utc_now()

        record.status = MemoryStatus.REVIEW
        record.protected_state = ProtectedState.REVIEW
        record.last_seen_at = now
        record.last_error = clean_text(
            reason,
            max_length=MAX_TEXT_LENGTH,
        )

        record.next_eligible_at = (
            now
            + timedelta(
                minutes=self.policy.review_cooldown_minutes
            )
        )

        record.add_event(
            MemoryEventKind.REVIEW_REQUIRED,
            record.last_error
            or "Manual review required.",
            metadata=safe_metadata(
                metadata
            ),
            max_events=self.policy.max_events_per_record,
        )

        return record

    def mark_blocked(
        self,
        key: str,
        reason: object,
        *,
        tombstone: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> MemoryRecord:
        record = self.require(
            key
        )

        record.status = (
            MemoryStatus.TOMBSTONED
            if tombstone
            else MemoryStatus.BLOCKED
        )

        record.protected_state = (
            ProtectedState.TOMBSTONE
            if tombstone
            else ProtectedState.ADMIN_BLOCK
        )

        record.last_error = clean_text(
            reason,
            max_length=MAX_TEXT_LENGTH,
        )

        record.next_eligible_at = None

        record.add_event(
            MemoryEventKind.BLOCKED,
            record.last_error
            or "Processing blocked.",
            metadata=safe_metadata(
                metadata
            ),
            max_events=self.policy.max_events_per_record,
        )

        return record

    def clear_review_protection(
        self,
        key: str,
        *,
        operator_note: str,
    ) -> MemoryRecord:
        record = self.require(
            key
        )

        if record.protected_state != ProtectedState.REVIEW:
            return record

        record.protected_state = ProtectedState.NONE
        record.status = MemoryStatus.NEW
        record.next_eligible_at = utc_now()

        record.add_event(
            MemoryEventKind.OPERATOR_NOTE,
            (
                "Review protection cleared explicitly: "
                + clean_text(
                    operator_note,
                    max_length=1_000,
                )
            ),
            max_events=self.policy.max_events_per_record,
        )

        return record

    def clear_admin_block(
        self,
        key: str,
        *,
        operator_note: str,
        allow_tombstone_clear: bool = False,
    ) -> MemoryRecord:
        record = self.require(
            key
        )

        if record.protected_state == ProtectedState.TOMBSTONE:
            if not allow_tombstone_clear:
                raise PermissionError(
                    "Tombstone protection requires explicit allow_tombstone_clear."
                )

        if record.protected_state not in {
            ProtectedState.ADMIN_BLOCK,
            ProtectedState.TOMBSTONE,
        }:
            return record

        record.protected_state = ProtectedState.NONE
        record.status = MemoryStatus.NEW
        record.next_eligible_at = utc_now()

        record.add_event(
            MemoryEventKind.OPERATOR_NOTE,
            (
                "Admin block cleared explicitly: "
                + clean_text(
                    operator_note,
                    max_length=1_000,
                )
            ),
            max_events=self.policy.max_events_per_record,
        )

        return record

    def require(
        self,
        key: str,
    ) -> MemoryRecord:
        record = self.get(
            key
        )

        if record is None:
            raise KeyError(
                f"Memory record not found: {key}"
            )

        return record

    def retry_decision(
        self,
        key: str,
        *,
        now: datetime | None = None,
    ) -> RetryDecision:
        record = self.get(
            key
        )

        if record is None:
            return RetryDecision.PROCESS

        now = (
            now
            or utc_now()
        )

        if record.protected_state in {
            ProtectedState.TOMBSTONE,
            ProtectedState.ADMIN_BLOCK,
        }:
            return RetryDecision.BLOCKED

        if (
            record.protected_state == ProtectedState.REVIEW
            or record.status == MemoryStatus.REVIEW
        ):
            return RetryDecision.REVIEW_REQUIRED

        if (
            record.attempts >= self.policy.max_attempts
            and record.status == MemoryStatus.FAILED
        ):
            return RetryDecision.ATTEMPTS_EXHAUSTED

        if record.next_eligible_at is not None:
            if now < record.next_eligible_at:
                if record.status in {
                    MemoryStatus.SUCCESS,
                    MemoryStatus.PUBLISHED,
                    MemoryStatus.UPDATED,
                    MemoryStatus.REPAIRED,
                    MemoryStatus.SKIPPED,
                }:
                    return RetryDecision.SKIP_RECENT_SUCCESS

                return RetryDecision.WAIT_COOLDOWN

        return RetryDecision.PROCESS

    def set_fingerprint(
        self,
        key: str,
        *,
        stage: str,
        value: object,
    ) -> str:
        record = self.require(
            key
        )

        fingerprint = fingerprint_object(
            value
        )

        stage = clean_text(
            stage,
            max_length=50,
        ).lower()

        mapping = {
            "candidate": "last_candidate_fingerprint",
            "resolution": "last_resolution_fingerprint",
            "apk": "last_apk_fingerprint",
            "content": "last_content_fingerprint",
            "decision": "last_decision_fingerprint",
            "publication": "last_publication_fingerprint",
        }

        attr = mapping.get(
            stage
        )

        if attr is None:
            raise ValueError(
                f"Unsupported memory fingerprint stage: {stage}"
            )

        setattr(
            record,
            attr,
            fingerprint,
        )

        return fingerprint

    def fingerprint_changed(
        self,
        key: str,
        *,
        stage: str,
        value: object,
    ) -> bool:
        record = self.get(
            key
        )

        if record is None:
            return True

        current = fingerprint_object(
            value
        )

        mapping = {
            "candidate": record.last_candidate_fingerprint,
            "resolution": record.last_resolution_fingerprint,
            "apk": record.last_apk_fingerprint,
            "content": record.last_content_fingerprint,
            "decision": record.last_decision_fingerprint,
            "publication": record.last_publication_fingerprint,
        }

        if stage not in mapping:
            raise ValueError(
                f"Unsupported memory fingerprint stage: {stage}"
            )

        return (
            mapping[stage]
            != current
        )

    def add_note(
        self,
        key: str,
        note: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> MemoryRecord:
        record = self.require(
            key
        )

        record.add_event(
            MemoryEventKind.OPERATOR_NOTE,
            clean_text(
                note,
                max_length=MAX_TEXT_LENGTH,
            ),
            metadata=safe_metadata(
                metadata
            ),
            max_events=self.policy.max_events_per_record,
        )

        return record

    def set_checkpoint(
        self,
        checkpoint: RunCheckpoint,
    ) -> None:
        self.ensure_loaded()

        checkpoint.validate()

        self.store.checkpoints[
            checkpoint.run_id
        ] = checkpoint

        self.store.add_global_event(
            MemoryEventKind.CHECKPOINT,
            "Run checkpoint updated.",
            metadata={
                "run_id": checkpoint.run_id,
                "stage": checkpoint.stage,
                "completed": len(
                    checkpoint.completed_keys
                ),
                "failed": len(
                    checkpoint.failed_keys
                ),
                "review": len(
                    checkpoint.review_keys
                ),
            },
            policy=self.policy,
        )

    def get_checkpoint(
        self,
        run_id: str,
    ) -> RunCheckpoint | None:
        self.ensure_loaded()

        run_id = clean_text(
            run_id,
            max_length=200,
        )

        return self.store.checkpoints.get(
            run_id
        )

    def delete_checkpoint(
        self,
        run_id: str,
    ) -> bool:
        self.ensure_loaded()

        run_id = clean_text(
            run_id,
            max_length=200,
        )

        return (
            self.store.checkpoints.pop(
                run_id,
                None,
            )
            is not None
        )

    def prune(
        self,
        *,
        now: datetime | None = None,
    ) -> int:
        """
        Remove only stale, unprotected records.

        Protected review/tombstone/admin-block states are retained.
        """

        self.ensure_loaded()

        now = (
            now
            or utc_now()
        )

        removable: list[
            tuple[datetime, str]
        ] = []

        for key, record in self.store.records.items():
            if record.protected_state != ProtectedState.NONE:
                continue

            age = now - record.last_seen_at

            if record.status == MemoryStatus.FAILED:
                threshold = timedelta(
                    days=self.policy.forget_transient_failures_after_days
                )

                if age >= threshold:
                    removable.append(
                        (
                            record.last_seen_at,
                            key,
                        )
                    )

            elif record.status in {
                MemoryStatus.SUCCESS,
                MemoryStatus.PUBLISHED,
                MemoryStatus.UPDATED,
                MemoryStatus.REPAIRED,
                MemoryStatus.SKIPPED,
            }:
                threshold = timedelta(
                    days=self.policy.prune_success_after_days
                )

                if age >= threshold:
                    removable.append(
                        (
                            record.last_seen_at,
                            key,
                        )
                    )

        removable.sort(
            key=lambda item: item[0]
        )

        removed = 0

        target = max(
            0,
            len(self.store.records)
            - self.policy.max_records
            + 100,
        )

        for _, key in removable:
            if target and removed >= target:
                break

            if self.store.records.pop(
                key,
                None,
            ) is not None:
                removed += 1

        if removed:
            self.store.add_global_event(
                MemoryEventKind.MEMORY_REPAIR,
                "Stale unprotected memory records pruned.",
                metadata={
                    "removed": removed,
                },
                policy=self.policy,
            )

        return removed


def _merge_identity_fields(
    record: MemoryRecord,
    *,
    package_id: str | None,
    app_name: str | None,
    source_type: str | None,
    source_url: str | None,
    repository_url: str | None,
) -> None:
    package_id = normalize_package_id(
        package_id
    )

    if package_id:
        record.package_id = package_id

    if app_name:
        cleaned = clean_text(
            app_name,
            max_length=500,
        )

        if cleaned:
            record.app_name = cleaned

    if source_type:
        cleaned = clean_text(
            source_type,
            max_length=100,
        )

        if cleaned:
            record.source_type = cleaned

    normalized_source_url = normalize_public_url(
        source_url
    )

    if normalized_source_url:
        record.source_url = normalized_source_url

    normalized_repository_url = normalize_public_url(
        repository_url
    )

    if normalized_repository_url:
        record.repository_url = normalized_repository_url


# ============================================================
# Generic object fingerprinting
# ============================================================

def fingerprint_object(
    value: object,
) -> str:
    return fingerprint_text(
        stable_json(
            canonicalize_object(
                value
            )
        )
    )


def canonicalize_object(
    value: object,
) -> object:
    if value is None:
        return None

    if isinstance(
        value,
        (bool, int, float, str),
    ):
        if isinstance(
            value,
            str,
        ):
            return clean_text(
                value,
                max_length=MAX_TEXT_LENGTH,
            )

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

    if is_dataclass(
        value
    ):
        return canonicalize_object(
            asdict(value)
        )

    if isinstance(
        value,
        Mapping,
    ):
        output: dict[
            str,
            object,
        ] = {}

        for key, item in sorted(
            value.items(),
            key=lambda pair: str(pair[0]),
        ):
            safe_key = clean_text(
                key,
                max_length=128,
            )

            if looks_secret_like(
                safe_key,
                item,
            ):
                output[
                    safe_key
                ] = "[REDACTED]"
            else:
                output[
                    safe_key
                ] = canonicalize_object(
                    item
                )

        return output

    if isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [
            canonicalize_object(
                item
            )
            for item in list(value)[:500]
        ]

    return clean_text(
        value,
        max_length=MAX_TEXT_LENGTH,
    )


# ============================================================
# Candidate integration helpers
# ============================================================

def candidate_identity_fields(
    candidate: object,
) -> dict[str, str | None]:
    """
    Extract common candidate identity fields without tightly coupling
    Memory to one concrete Discovery model implementation.
    """

    package_id = getattr(
        candidate,
        "package_id",
        None,
    )

    name = getattr(
        candidate,
        "name",
        None,
    )

    source_type = getattr(
        candidate,
        "source_type",
        None,
    )

    if isinstance(
        source_type,
        Enum,
    ):
        source_type = source_type.value

    source_url = getattr(
        candidate,
        "source_url",
        None,
    )

    repository_url = getattr(
        candidate,
        "repository_url",
        None,
    )

    return {
        "package_id": (
            str(package_id)
            if package_id
            else None
        ),
        "app_name": (
            str(name)
            if name
            else None
        ),
        "source_type": (
            str(source_type)
            if source_type
            else None
        ),
        "source_url": (
            str(source_url)
            if source_url
            else None
        ),
        "repository_url": (
            str(repository_url)
            if repository_url
            else None
        ),
    }


def memory_key_for_candidate(
    candidate: object,
) -> str:
    fields = candidate_identity_fields(
        candidate
    )

    return build_candidate_key(
        package_id=fields[
            "package_id"
        ],
        source_type=fields[
            "source_type"
        ],
        source_url=fields[
            "source_url"
        ],
        repository_url=fields[
            "repository_url"
        ],
        name=fields[
            "app_name"
        ],
    )


def remember_candidate(
    memory: EngineMemory,
    candidate: object,
) -> MemoryRecord:
    fields = candidate_identity_fields(
        candidate
    )

    key = build_candidate_key(
        package_id=fields[
            "package_id"
        ],
        source_type=fields[
            "source_type"
        ],
        source_url=fields[
            "source_url"
        ],
        repository_url=fields[
            "repository_url"
        ],
        name=fields[
            "app_name"
        ],
    )

    record = memory.get_or_create(
        key,
        package_id=fields[
            "package_id"
        ],
        app_name=fields[
            "app_name"
        ],
        source_type=fields[
            "source_type"
        ],
        source_url=fields[
            "source_url"
        ],
        repository_url=fields[
            "repository_url"
        ],
    )

    memory.set_fingerprint(
        key,
        stage="candidate",
        value=candidate,
    )

    return record


# ============================================================
# Stage recording helpers
# ============================================================

def remember_resolution(
    memory: EngineMemory,
    key: str,
    resolution: object,
    *,
    summary: Mapping[str, object] | None = None,
) -> str:
    fingerprint = memory.set_fingerprint(
        key,
        stage="resolution",
        value=resolution,
    )

    record = memory.require(
        key
    )

    record.add_event(
        MemoryEventKind.RESOLVED,
        "Resolver stage completed.",
        metadata={
            "fingerprint": fingerprint,
            **safe_metadata(
                summary
            ),
        },
        max_events=memory.policy.max_events_per_record,
    )

    return fingerprint


def remember_apk(
    memory: EngineMemory,
    key: str,
    apk_report: object,
    *,
    summary: Mapping[str, object] | None = None,
) -> str:
    fingerprint = memory.set_fingerprint(
        key,
        stage="apk",
        value=apk_report,
    )

    record = memory.require(
        key
    )

    record.add_event(
        MemoryEventKind.APK_SELECTED,
        "APK Intelligence stage completed.",
        metadata={
            "fingerprint": fingerprint,
            **safe_metadata(
                summary
            ),
        },
        max_events=memory.policy.max_events_per_record,
    )

    return fingerprint


def remember_content(
    memory: EngineMemory,
    key: str,
    content_package: object,
    *,
    summary: Mapping[str, object] | None = None,
) -> str:
    fingerprint = memory.set_fingerprint(
        key,
        stage="content",
        value=content_package,
    )

    record = memory.require(
        key
    )

    record.add_event(
        MemoryEventKind.CONTENT_BUILT,
        "Content Intelligence stage completed.",
        metadata={
            "fingerprint": fingerprint,
            **safe_metadata(
                summary
            ),
        },
        max_events=memory.policy.max_events_per_record,
    )

    return fingerprint


def remember_decision(
    memory: EngineMemory,
    key: str,
    decision: object,
    *,
    action: str | None = None,
    summary: Mapping[str, object] | None = None,
) -> str:
    fingerprint = memory.set_fingerprint(
        key,
        stage="decision",
        value=decision,
    )

    record = memory.require(
        key
    )

    if action:
        record.last_decision_action = clean_text(
            action,
            max_length=100,
        )

    record.add_event(
        MemoryEventKind.DECIDED,
        "Decision Engine stage completed.",
        metadata={
            "fingerprint": fingerprint,
            "action": record.last_decision_action,
            **safe_metadata(
                summary
            ),
        },
        max_events=memory.policy.max_events_per_record,
    )

    return fingerprint


def remember_publication(
    memory: EngineMemory,
    key: str,
    outcome: object,
    *,
    summary: Mapping[str, object] | None = None,
) -> str:
    fingerprint = memory.set_fingerprint(
        key,
        stage="publication",
        value=outcome,
    )

    record = memory.require(
        key
    )

    record.add_event(
        MemoryEventKind.PUBLISH_ATTEMPT,
        "Publisher stage completed.",
        metadata={
            "fingerprint": fingerprint,
            **safe_metadata(
                summary
            ),
        },
        max_events=memory.policy.max_events_per_record,
    )

    return fingerprint


# ============================================================
# Batch retry helper
# ============================================================

@dataclass(slots=True)
class MemoryEligibilityReport:
    process: list[str] = field(
        default_factory=list
    )
    skipped_recent_success: list[str] = field(
        default_factory=list
    )
    cooldown: list[str] = field(
        default_factory=list
    )
    review: list[str] = field(
        default_factory=list
    )
    blocked: list[str] = field(
        default_factory=list
    )
    exhausted: list[str] = field(
        default_factory=list
    )

    @property
    def total(self) -> int:
        return sum(
            len(group)
            for group in (
                self.process,
                self.skipped_recent_success,
                self.cooldown,
                self.review,
                self.blocked,
                self.exhausted,
            )
        )


def classify_keys(
    memory: EngineMemory,
    keys: Iterable[str],
) -> MemoryEligibilityReport:
    report = MemoryEligibilityReport()

    for key in keys:
        decision = memory.retry_decision(
            key
        )

        if decision == RetryDecision.PROCESS:
            report.process.append(
                key
            )
        elif decision == RetryDecision.SKIP_RECENT_SUCCESS:
            report.skipped_recent_success.append(
                key
            )
        elif decision == RetryDecision.WAIT_COOLDOWN:
            report.cooldown.append(
                key
            )
        elif decision == RetryDecision.REVIEW_REQUIRED:
            report.review.append(
                key
            )
        elif decision == RetryDecision.BLOCKED:
            report.blocked.append(
                key
            )
        elif decision == RetryDecision.ATTEMPTS_EXHAUSTED:
            report.exhausted.append(
                key
            )

    return report


# ============================================================
# Diagnostics
# ============================================================

def run_memory_diagnostic() -> dict[str, object]:
    policy = MemoryPolicy(
        max_records=100,
        max_events_per_record=20,
        max_global_events=100,
        max_attempts=5,
        failure_cooldown_minutes=10,
        review_cooldown_minutes=60,
        success_recheck_minutes=120,
        preserve_review_state=True,
        preserve_tombstones=True,
        preserve_admin_blocks=True,
        forget_transient_failures_after_days=30,
        prune_success_after_days=180,
        allow_retry_after_failure=True,
        allow_recheck_after_success=True,
    )

    backend = InMemoryBackend()

    memory = EngineMemory(
        backend,
        policy=policy,
    )

    load_result = memory.load()

    if not load_result.succeeded:
        raise RuntimeError(
            load_result.error
            or "Diagnostic memory failed to load."
        )

    key = build_candidate_key(
        package_id="org.osguide.diagnostic",
        source_type="github",
        source_url="https://github.com/example/project",
        repository_url="https://github.com/example/project",
        name="OSGuide Diagnostic App",
    )

    memory.get_or_create(
        key,
        package_id="org.osguide.diagnostic",
        app_name="OSGuide Diagnostic App",
        source_type="github",
        source_url="https://github.com/example/project",
        repository_url="https://github.com/example/project",
    )

    first_decision = memory.retry_decision(
        key
    )

    memory.mark_processing(
        key
    )

    memory.set_fingerprint(
        key,
        stage="candidate",
        value={
            "name": "OSGuide Diagnostic App",
            "package_id": "org.osguide.diagnostic",
        },
    )

    memory.mark_success(
        key,
        status=MemoryStatus.SUCCESS,
        action="insert",
        metadata={
            "diagnostic": True,
        },
    )

    second_decision = memory.retry_decision(
        key
    )

    save_result = memory.save()

    if not save_result.succeeded:
        raise RuntimeError(
            save_result.error
            or "Diagnostic memory failed to save."
        )

    record = memory.require(
        key
    )

    return {
        "key": key,
        "first_retry_decision": first_decision.value,
        "second_retry_decision": second_decision.value,
        "status": record.status.value,
        "attempts": record.attempts,
        "event_count": len(
            record.events
        ),
        "protected_state": record.protected_state.value,
        "candidate_fingerprint": record.last_candidate_fingerprint,
    }


def run_failure_retry_diagnostic() -> dict[str, object]:
    backend = InMemoryBackend()

    policy = MemoryPolicy(
        max_attempts=3,
        failure_cooldown_minutes=1,
    )

    memory = EngineMemory(
        backend,
        policy=policy,
    )

    memory.load()

    key = build_candidate_key(
        package_id="org.osguide.failure",
        name="Failure Diagnostic",
    )

    memory.get_or_create(
        key,
        package_id="org.osguide.failure",
        app_name="Failure Diagnostic",
    )

    memory.mark_processing(
        key
    )

    memory.mark_failure(
        key,
        "Intentional diagnostic failure.",
        retryable=True,
    )

    decision = memory.retry_decision(
        key
    )

    record = memory.require(
        key
    )

    return {
        "key": key,
        "status": record.status.value,
        "retry_decision": decision.value,
        "attempts": record.attempts,
        "consecutive_failures": record.consecutive_failures,
        "next_eligible_at": isoformat_utc(
            record.next_eligible_at
        ),
    }


def run_review_protection_diagnostic() -> dict[str, object]:
    backend = InMemoryBackend()

    memory = EngineMemory(
        backend
    )

    memory.load()

    key = build_candidate_key(
        package_id="org.osguide.review",
        name="Review Diagnostic",
    )

    memory.get_or_create(
        key,
        package_id="org.osguide.review",
        app_name="Review Diagnostic",
    )

    memory.mark_review(
        key,
        "Intentional diagnostic review state.",
    )

    before = memory.retry_decision(
        key
    )

    memory.clear_review_protection(
        key,
        operator_note="Diagnostic operator approval.",
    )

    after = memory.retry_decision(
        key
    )

    return {
        "key": key,
        "before": before.value,
        "after": after.value,
    }


def run_tombstone_protection_diagnostic() -> dict[str, object]:
    backend = InMemoryBackend()

    memory = EngineMemory(
        backend
    )

    memory.load()

    key = build_candidate_key(
        package_id="org.osguide.tombstone",
        name="Tombstone Diagnostic",
    )

    memory.get_or_create(
        key,
        package_id="org.osguide.tombstone",
        app_name="Tombstone Diagnostic",
    )

    memory.mark_blocked(
        key,
        "Intentional Admin tombstone diagnostic.",
        tombstone=True,
    )

    decision = memory.retry_decision(
        key
    )

    return {
        "key": key,
        "status": memory.require(key).status.value,
        "protected_state": memory.require(
            key
        ).protected_state.value,
        "retry_decision": decision.value,
    }


# ============================================================
# Summary helpers
# ============================================================

def memory_record_summary(
    record: MemoryRecord,
) -> dict[str, object]:
    return {
        "key": record.key,
        "status": record.status.value,
        "protected_state": record.protected_state.value,
        "package_id": record.package_id,
        "app_name": record.app_name,
        "source_type": record.source_type,
        "attempts": record.attempts,
        "consecutive_failures": record.consecutive_failures,
        "last_seen_at": isoformat_utc(
            record.last_seen_at
        ),
        "last_attempt_at": isoformat_utc(
            record.last_attempt_at
        ),
        "last_success_at": isoformat_utc(
            record.last_success_at
        ),
        "next_eligible_at": isoformat_utc(
            record.next_eligible_at
        ),
        "last_decision_action": record.last_decision_action,
        "last_error": record.last_error,
        "event_count": len(
            record.events
        ),
        "fingerprints": {
            "candidate": record.last_candidate_fingerprint,
            "resolution": record.last_resolution_fingerprint,
            "apk": record.last_apk_fingerprint,
            "content": record.last_content_fingerprint,
            "decision": record.last_decision_fingerprint,
            "publication": record.last_publication_fingerprint,
        },
    }


def memory_store_summary(
    store: MemoryStore,
) -> dict[str, object]:
    status_counts: dict[
        str,
        int,
    ] = {}

    protected_counts: dict[
        str,
        int,
    ] = {}

    for record in store.records.values():
        status_counts[
            record.status.value
        ] = (
            status_counts.get(
                record.status.value,
                0,
            )
            + 1
        )

        protected_counts[
            record.protected_state.value
        ] = (
            protected_counts.get(
                record.protected_state.value,
                0,
            )
            + 1
        )

    return {
        "schema_version": store.schema_version,
        "record_count": len(
            store.records
        ),
        "checkpoint_count": len(
            store.checkpoints
        ),
        "global_event_count": len(
            store.global_events
        ),
        "status_counts": status_counts,
        "protected_counts": protected_counts,
        "created_at": isoformat_utc(
            store.created_at
        ),
        "updated_at": isoformat_utc(
            store.updated_at
        ),
    }


def eligibility_summary(
    report: MemoryEligibilityReport,
) -> dict[str, object]:
    return {
        "total": report.total,
        "process": len(
            report.process
        ),
        "skipped_recent_success": len(
            report.skipped_recent_success
        ),
        "cooldown": len(
            report.cooldown
        ),
        "review": len(
            report.review
        ),
        "blocked": len(
            report.blocked
        ),
        "exhausted": len(
            report.exhausted
        ),
    }


# ============================================================
# Default factories
# ============================================================

def default_memory_policy() -> MemoryPolicy:
    return MemoryPolicy()


def create_in_memory_manager(
    *,
    policy: MemoryPolicy | None = None,
) -> EngineMemory:
    manager = EngineMemory(
        InMemoryBackend(),
        policy=policy,
    )

    result = manager.load()

    if not result.succeeded:
        raise RuntimeError(
            result.error
            or "Unable to initialize in-memory manager."
        )

    return manager


def create_json_memory_manager(
    path: str | Path,
    *,
    policy: MemoryPolicy | None = None,
) -> EngineMemory:
    manager = EngineMemory(
        JsonFileMemoryBackend(
            path
        ),
        policy=policy,
    )

    result = manager.load()

    if result.status == MemoryBackendStatus.CORRUPT:
        raise RuntimeError(
            result.error
            or "Memory file is corrupt."
        )

    if not result.succeeded:
        raise RuntimeError(
            result.error
            or "Unable to initialize JSON memory manager."
        )

    return manager


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "DEFAULT_FAILURE_COOLDOWN_MINUTES",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_EVENTS_PER_RECORD",
    "DEFAULT_MAX_GLOBAL_EVENTS",
    "DEFAULT_MAX_RECORDS",
    "DEFAULT_REVIEW_COOLDOWN_MINUTES",
    "DEFAULT_SUCCESS_RECHECK_MINUTES",
    "EngineMemory",
    "InMemoryBackend",
    "JsonFileMemoryBackend",
    "MEMORY_COMPONENT",
    "MEMORY_SCHEMA_VERSION",
    "MemoryBackend",
    "MemoryBackendResult",
    "MemoryBackendStatus",
    "MemoryEligibilityReport",
    "MemoryEvent",
    "MemoryEventKind",
    "MemoryPolicy",
    "MemoryRecord",
    "MemoryStatus",
    "MemoryStore",
    "ProtectedState",
    "RetryDecision",
    "RunCheckpoint",
    "build_candidate_key",
    "candidate_identity_fields",
    "canonicalize_object",
    "classify_keys",
    "clean_text",
    "create_in_memory_manager",
    "create_json_memory_manager",
    "default_memory_policy",
    "eligibility_summary",
    "fingerprint_mapping",
    "fingerprint_object",
    "fingerprint_text",
    "isoformat_utc",
    "looks_secret_like",
    "memory_key_for_candidate",
    "memory_record_summary",
    "memory_store_summary",
    "normalize_package_id",
    "normalize_public_url",
    "parse_datetime",
    "remember_apk",
    "remember_candidate",
    "remember_content",
    "remember_decision",
    "remember_publication",
    "remember_resolution",
    "run_failure_retry_diagnostic",
    "run_memory_diagnostic",
    "run_review_protection_diagnostic",
    "run_tombstone_protection_diagnostic",
    "safe_metadata",
    "safe_metadata_value",
    "stable_json",
    "utc_now",
    "validate_memory_key",
)
