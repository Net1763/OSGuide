"""
OSGuide Engine
Observability Layer

Purpose
-------
The Observability Layer provides structured, security-conscious visibility
into OSGuide Engine executions without becoming part of the business logic.

It records:
- run lifecycle
- stage lifecycle
- timing
- bounded counters
- warnings and errors
- per-application progress summaries
- decision and publication outcomes
- memory activity
- security-relevant events
- operator-readable summaries
- machine-readable JSON reports
- diagnostic traces
- optional local JSONL event output

Architecture rules
------------------
1. Observability never decides whether an app is published.
2. Observability never modifies Supabase application records.
3. Observability never stores or prints secrets.
4. Secret-like fields are redacted before logging.
5. Raw tokens, passwords, cookies, Authorization headers and API keys are
   forbidden in event metadata.
6. Events are bounded in size and count.
7. One malformed event must not stop the engine.
8. Logging failures must not corrupt engine state.
9. Application identifiers such as Package ID may be logged.
10. Public source URLs may be logged when useful.
11. Large raw API payloads, raw HTML and APK bytes are never logged.
12. Diagnostic output is deterministic where practical.
13. JSON serialization never executes arbitrary code.
14. No pickle is used.
15. Stage timing uses monotonic clocks.
16. Wall-clock timestamps use UTC.
17. Errors are summarized safely without leaking sensitive values.
18. The layer supports in-memory diagnostics and optional local file output.
19. File output uses append-only JSONL for event streams.
20. File permissions are restricted where supported.
21. The engine can produce a compact final run report.
22. Cancellation, deadline and partial-completion states are represented.
23. Security-relevant events are classified separately.
24. Observability can be used from GitHub Actions without third-party
   dependencies.
25. This file uses only the Python standard library.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Final,
    Iterable,
    Mapping,
    MutableMapping,
    Sequence,
)


# ============================================================
# Component identity
# ============================================================

OBSERVABILITY_COMPONENT: Final[str] = "Observability"
OBSERVABILITY_SCHEMA_VERSION: Final[str] = "1"


# ============================================================
# Limits
# ============================================================

DEFAULT_MAX_EVENTS: Final[int] = 5_000
HARD_MAX_EVENTS: Final[int] = 50_000

DEFAULT_MAX_STAGE_RECORDS: Final[int] = 1_000
HARD_MAX_STAGE_RECORDS: Final[int] = 10_000

DEFAULT_MAX_APP_RECORDS: Final[int] = 2_000
HARD_MAX_APP_RECORDS: Final[int] = 20_000

DEFAULT_MAX_MESSAGE_LENGTH: Final[int] = 2_000
HARD_MAX_MESSAGE_LENGTH: Final[int] = 20_000

DEFAULT_MAX_METADATA_ITEMS: Final[int] = 100
HARD_MAX_METADATA_ITEMS: Final[int] = 500

DEFAULT_MAX_METADATA_DEPTH: Final[int] = 6
HARD_MAX_METADATA_DEPTH: Final[int] = 12

DEFAULT_MAX_TEXT_VALUE_LENGTH: Final[int] = 4_000
HARD_MAX_TEXT_VALUE_LENGTH: Final[int] = 20_000

DEFAULT_MAX_FILE_BYTES: Final[int] = 25_000_000
HARD_MAX_FILE_BYTES: Final[int] = 200_000_000


# ============================================================
# Secret detection
# ============================================================

SECRET_FIELD_RE: Final[re.Pattern[str]] = re.compile(
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

class EventSeverity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SECURITY = "security"


class EventKind(str, Enum):
    RUN_STARTED = "run-started"
    RUN_FINISHED = "run-finished"
    RUN_FAILED = "run-failed"
    RUN_CANCELLED = "run-cancelled"
    RUN_DEADLINE = "run-deadline"

    STAGE_STARTED = "stage-started"
    STAGE_FINISHED = "stage-finished"
    STAGE_FAILED = "stage-failed"
    STAGE_SKIPPED = "stage-skipped"

    APP_STARTED = "app-started"
    APP_FINISHED = "app-finished"
    APP_SKIPPED = "app-skipped"
    APP_REVIEW = "app-review"
    APP_FAILED = "app-failed"

    DISCOVERY = "discovery"
    RESOLUTION = "resolution"
    APK = "apk"
    CONTENT = "content"
    DECISION = "decision"
    MEMORY = "memory"
    PUBLISHER = "publisher"

    RETRY = "retry"
    CHECKPOINT = "checkpoint"
    DIAGNOSTIC = "diagnostic"
    SECURITY = "security"
    OPERATOR = "operator"


class RunState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"
    PARTIAL = "partial"


class StageState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class AppState(str, Enum):
    CREATED = "created"
    PROCESSING = "processing"
    SUCCESS = "success"
    SKIPPED = "skipped"
    REVIEW = "review"
    FAILED = "failed"
    BLOCKED = "blocked"


# ============================================================
# Time helpers
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).isoformat()


# ============================================================
# Redaction and safe serialization
# ============================================================

def clean_text(
    value: object,
    *,
    max_length: int = DEFAULT_MAX_TEXT_VALUE_LENGTH,
) -> str:
    text = str(value).replace("\x00", "")

    text = (
        text.replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )

    text = re.sub(r"\s+", " ", text)

    if len(text) > max_length:
        text = text[:max_length]

    return text


def looks_secret_like(
    field_name: str,
    value: object,
) -> bool:
    if SECRET_FIELD_RE.search(field_name):
        return True

    if not isinstance(value, str):
        return False

    text = value.strip()

    if not text:
        return False

    if JWT_RE.fullmatch(text):
        return True

    if LONG_SECRET_RE.fullmatch(text):
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
    depth: int = 0,
    max_depth: int = DEFAULT_MAX_METADATA_DEPTH,
    max_items: int = DEFAULT_MAX_METADATA_ITEMS,
    max_text_length: int = DEFAULT_MAX_TEXT_VALUE_LENGTH,
    field_name: str = "",
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

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return isoformat_utc(
            value
        )

    if isinstance(value, str):
        return clean_text(
            value,
            max_length=max_text_length,
        )

    if is_dataclass(value):
        return safe_value(
            asdict(value),
            depth=depth + 1,
            max_depth=max_depth,
            max_items=max_items,
            max_text_length=max_text_length,
        )

    if isinstance(value, Mapping):
        output: dict[str, object] = {}

        for index, (key, item) in enumerate(
            value.items()
        ):
            if index >= max_items:
                output["__truncated__"] = True
                break

            safe_key = clean_text(
                key,
                max_length=128,
            )

            if not safe_key:
                continue

            output[safe_key] = safe_value(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_text_length=max_text_length,
                field_name=safe_key,
            )

        return output

    if isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        output_list: list[object] = []

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
                    max_text_length=max_text_length,
                )
            )

        return output_list

    return clean_text(
        value,
        max_length=max_text_length,
    )


def safe_metadata(
    metadata: Mapping[str, object] | None,
    *,
    max_depth: int = DEFAULT_MAX_METADATA_DEPTH,
    max_items: int = DEFAULT_MAX_METADATA_ITEMS,
    max_text_length: int = DEFAULT_MAX_TEXT_VALUE_LENGTH,
) -> dict[str, object]:
    if not metadata:
        return {}

    value = safe_value(
        metadata,
        max_depth=max_depth,
        max_items=max_items,
        max_text_length=max_text_length,
    )

    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


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
# Configuration
# ============================================================

@dataclass(frozen=True, slots=True)
class ObservabilityPolicy:
    enabled: bool = True
    debug_enabled: bool = False

    max_events: int = DEFAULT_MAX_EVENTS
    max_stage_records: int = DEFAULT_MAX_STAGE_RECORDS
    max_app_records: int = DEFAULT_MAX_APP_RECORDS

    max_message_length: int = DEFAULT_MAX_MESSAGE_LENGTH
    max_metadata_items: int = DEFAULT_MAX_METADATA_ITEMS
    max_metadata_depth: int = DEFAULT_MAX_METADATA_DEPTH
    max_text_value_length: int = DEFAULT_MAX_TEXT_VALUE_LENGTH

    include_public_urls: bool = True
    include_package_ids: bool = True

    include_exception_type: bool = True
    include_exception_message: bool = True

    include_event_fingerprint: bool = True

    def validate(self) -> None:
        if not 1 <= self.max_events <= HARD_MAX_EVENTS:
            raise ValueError(
                "max_events outside allowed range."
            )

        if not (
            1
            <= self.max_stage_records
            <= HARD_MAX_STAGE_RECORDS
        ):
            raise ValueError(
                "max_stage_records outside allowed range."
            )

        if not (
            1
            <= self.max_app_records
            <= HARD_MAX_APP_RECORDS
        ):
            raise ValueError(
                "max_app_records outside allowed range."
            )

        if not (
            100
            <= self.max_message_length
            <= HARD_MAX_MESSAGE_LENGTH
        ):
            raise ValueError(
                "max_message_length outside allowed range."
            )

        if not (
            1
            <= self.max_metadata_items
            <= HARD_MAX_METADATA_ITEMS
        ):
            raise ValueError(
                "max_metadata_items outside allowed range."
            )

        if not (
            1
            <= self.max_metadata_depth
            <= HARD_MAX_METADATA_DEPTH
        ):
            raise ValueError(
                "max_metadata_depth outside allowed range."
            )

        if not (
            100
            <= self.max_text_value_length
            <= HARD_MAX_TEXT_VALUE_LENGTH
        ):
            raise ValueError(
                "max_text_value_length outside allowed range."
            )


# ============================================================
# Counter model
# ============================================================

@dataclass(slots=True)
class CounterSet:
    discovered: int = 0
    candidates_processed: int = 0
    resolved: int = 0
    apk_selected: int = 0
    content_built: int = 0

    inserts: int = 0
    updates: int = 0
    repairs: int = 0
    skipped: int = 0
    reviews: int = 0
    blocked: int = 0
    failures: int = 0

    retries: int = 0
    memory_hits: int = 0
    memory_misses: int = 0

    warnings: int = 0
    security_events: int = 0

    def increment(
        self,
        name: str,
        amount: int = 1,
    ) -> None:
        if amount < 0:
            raise ValueError(
                "Counter increments cannot be negative."
            )

        if not hasattr(
            self,
            name,
        ):
            raise ValueError(
                f"Unknown counter: {name}"
            )

        current = getattr(
            self,
            name,
        )

        if not isinstance(
            current,
            int,
        ):
            raise TypeError(
                f"Counter {name} is not an integer."
            )

        setattr(
            self,
            name,
            current + amount,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "discovered": self.discovered,
            "candidates_processed": self.candidates_processed,
            "resolved": self.resolved,
            "apk_selected": self.apk_selected,
            "content_built": self.content_built,
            "inserts": self.inserts,
            "updates": self.updates,
            "repairs": self.repairs,
            "skipped": self.skipped,
            "reviews": self.reviews,
            "blocked": self.blocked,
            "failures": self.failures,
            "retries": self.retries,
            "memory_hits": self.memory_hits,
            "memory_misses": self.memory_misses,
            "warnings": self.warnings,
            "security_events": self.security_events,
        }


# ============================================================
# Event model
# ============================================================

@dataclass(frozen=True, slots=True)
class ObservabilityEvent:
    sequence: int
    kind: EventKind
    severity: EventSeverity
    message: str

    timestamp: datetime

    run_id: str | None = None
    stage: str | None = None
    app_key: str | None = None
    package_id: str | None = None

    metadata: Mapping[str, object] = field(
        default_factory=dict
    )

    fingerprint: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": isoformat_utc(
                self.timestamp
            ),
            "run_id": self.run_id,
            "stage": self.stage,
            "app_key": self.app_key,
            "package_id": self.package_id,
            "metadata": dict(
                self.metadata
            ),
            "fingerprint": self.fingerprint,
        }


# ============================================================
# Stage model
# ============================================================

@dataclass(slots=True)
class StageRecord:
    name: str
    state: StageState = StageState.CREATED

    started_at: datetime | None = None
    finished_at: datetime | None = None

    started_monotonic: float | None = None
    finished_monotonic: float | None = None

    attempts: int = 0
    failures: int = 0
    processed: int = 0

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    last_error: str | None = None

    @property
    def duration_seconds(self) -> float:
        if self.started_monotonic is None:
            return 0.0

        end = (
            self.finished_monotonic
            if self.finished_monotonic is not None
            else time.monotonic()
        )

        return max(
            0.0,
            end - self.started_monotonic,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "state": self.state.value,
            "started_at": isoformat_utc(
                self.started_at
            ),
            "finished_at": isoformat_utc(
                self.finished_at
            ),
            "duration_seconds": round(
                self.duration_seconds,
                6,
            ),
            "attempts": self.attempts,
            "failures": self.failures,
            "processed": self.processed,
            "metadata": dict(
                self.metadata
            ),
            "last_error": self.last_error,
        }


# ============================================================
# Application record
# ============================================================

@dataclass(slots=True)
class AppRecord:
    key: str
    state: AppState = AppState.CREATED

    name: str | None = None
    package_id: str | None = None
    source_type: str | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None

    started_monotonic: float | None = None
    finished_monotonic: float | None = None

    current_stage: str | None = None
    decision_action: str | None = None
    publication_status: str | None = None

    warning_count: int = 0
    failure_count: int = 0

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    last_error: str | None = None

    @property
    def duration_seconds(self) -> float:
        if self.started_monotonic is None:
            return 0.0

        end = (
            self.finished_monotonic
            if self.finished_monotonic is not None
            else time.monotonic()
        )

        return max(
            0.0,
            end - self.started_monotonic,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "state": self.state.value,
            "name": self.name,
            "package_id": self.package_id,
            "source_type": self.source_type,
            "started_at": isoformat_utc(
                self.started_at
            ),
            "finished_at": isoformat_utc(
                self.finished_at
            ),
            "duration_seconds": round(
                self.duration_seconds,
                6,
            ),
            "current_stage": self.current_stage,
            "decision_action": self.decision_action,
            "publication_status": self.publication_status,
            "warning_count": self.warning_count,
            "failure_count": self.failure_count,
            "metadata": dict(
                self.metadata
            ),
            "last_error": self.last_error,
        }


# ============================================================
# Run record
# ============================================================

@dataclass(slots=True)
class RunRecord:
    run_id: str
    state: RunState = RunState.CREATED

    started_at: datetime | None = None
    finished_at: datetime | None = None

    started_monotonic: float | None = None
    finished_monotonic: float | None = None

    run_mode: str | None = None
    max_apps: int | None = None
    runtime_minutes: int | None = None

    counters: CounterSet = field(
        default_factory=CounterSet
    )

    metadata: dict[str, object] = field(
        default_factory=dict
    )

    last_error: str | None = None

    @property
    def duration_seconds(self) -> float:
        if self.started_monotonic is None:
            return 0.0

        end = (
            self.finished_monotonic
            if self.finished_monotonic is not None
            else time.monotonic()
        )

        return max(
            0.0,
            end - self.started_monotonic,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "state": self.state.value,
            "started_at": isoformat_utc(
                self.started_at
            ),
            "finished_at": isoformat_utc(
                self.finished_at
            ),
            "duration_seconds": round(
                self.duration_seconds,
                6,
            ),
            "run_mode": self.run_mode,
            "max_apps": self.max_apps,
            "runtime_minutes": self.runtime_minutes,
            "counters": self.counters.as_dict(),
            "metadata": dict(
                self.metadata
            ),
            "last_error": self.last_error,
        }


# ============================================================
# Event sink protocol
# ============================================================

class EventSink:
    def write(
        self,
        event: ObservabilityEvent,
    ) -> None:
        raise NotImplementedError


class NullEventSink(EventSink):
    def write(
        self,
        event: ObservabilityEvent,
    ) -> None:
        del event


class MemoryEventSink(EventSink):
    def __init__(
        self,
        *,
        max_events: int = DEFAULT_MAX_EVENTS,
    ) -> None:
        self.max_events = max_events
        self.events: list[
            ObservabilityEvent
        ] = []

    def write(
        self,
        event: ObservabilityEvent,
    ) -> None:
        self.events.append(
            event
        )

        if len(self.events) > self.max_events:
            self.events = self.events[
                -self.max_events:
            ]


class JsonlEventSink(EventSink):
    """
    Append-only JSONL sink.

    This sink is intentionally simple. The engine can upload the resulting
    file as a GitHub Actions artifact if desired.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ) -> None:
        if not 1_000 <= max_file_bytes <= HARD_MAX_FILE_BYTES:
            raise ValueError(
                "max_file_bytes outside allowed range."
            )

        self.path = Path(
            path
        )

        self.max_file_bytes = max_file_bytes

        self._lock = threading.Lock()

    def write(
        self,
        event: ObservabilityEvent,
    ) -> None:
        line = (
            json.dumps(
                event.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=json_default,
            )
            + "\n"
        )

        encoded = line.encode(
            "utf-8"
        )

        with self._lock:
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


class CompositeEventSink(EventSink):
    def __init__(
        self,
        sinks: Iterable[EventSink],
    ) -> None:
        self.sinks = list(
            sinks
        )

    def write(
        self,
        event: ObservabilityEvent,
    ) -> None:
        for sink in self.sinks:
            try:
                sink.write(
                    event
                )
            except Exception:
                continue


# ============================================================
# Exception safety
# ============================================================

def safe_exception_summary(
    exc: BaseException,
    *,
    policy: ObservabilityPolicy,
) -> dict[str, object]:
    output: dict[str, object] = {}

    if policy.include_exception_type:
        output["type"] = clean_text(
            type(exc).__name__,
            max_length=200,
        )

    if policy.include_exception_message:
        message = clean_text(
            exc,
            max_length=policy.max_message_length,
        )

        if looks_secret_like(
            "exception_message",
            message,
        ):
            message = "[REDACTED]"

        output["message"] = message

    return output


# ============================================================
# Fingerprints
# ============================================================

def event_fingerprint(
    *,
    kind: EventKind,
    severity: EventSeverity,
    message: str,
    run_id: str | None,
    stage: str | None,
    app_key: str | None,
    package_id: str | None,
    metadata: Mapping[str, object],
) -> str:
    payload = {
        "kind": kind.value,
        "severity": severity.value,
        "message": message,
        "run_id": run_id,
        "stage": stage,
        "app_key": app_key,
        "package_id": package_id,
        "metadata": metadata,
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default,
    )

    return hashlib.sha256(
        serialized.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================
# Main observer
# ============================================================

class EngineObserver:
    def __init__(
        self,
        *,
        policy: ObservabilityPolicy | None = None,
        sink: EventSink | None = None,
    ) -> None:
        self.policy = (
            policy
            or ObservabilityPolicy()
        )

        self.policy.validate()

        self.sink = (
            sink
            or MemoryEventSink(
                max_events=self.policy.max_events
            )
        )

        self.run: RunRecord | None = None

        self.stages: dict[
            str,
            StageRecord,
        ] = {}

        self.apps: dict[
            str,
            AppRecord,
        ] = {}

        self._sequence = 0

        self._lock = threading.RLock()

    # --------------------------------------------------------
    # Low-level event
    # --------------------------------------------------------

    def emit(
        self,
        kind: EventKind,
        severity: EventSeverity,
        message: str,
        *,
        run_id: str | None = None,
        stage: str | None = None,
        app_key: str | None = None,
        package_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ObservabilityEvent | None:
        if not self.policy.enabled:
            return None

        if (
            severity == EventSeverity.DEBUG
            and not self.policy.debug_enabled
        ):
            return None

        with self._lock:
            self._sequence += 1

            safe_message = clean_text(
                message,
                max_length=self.policy.max_message_length,
            )

            safe_run_id = (
                clean_text(
                    run_id,
                    max_length=200,
                )
                if run_id
                else None
            )

            safe_stage = (
                clean_text(
                    stage,
                    max_length=100,
                )
                if stage
                else None
            )

            safe_app_key = (
                clean_text(
                    app_key,
                    max_length=300,
                )
                if app_key
                else None
            )

            safe_package_id = (
                clean_text(
                    package_id,
                    max_length=300,
                )
                if (
                    package_id
                    and self.policy.include_package_ids
                )
                else None
            )

            safe_meta = safe_metadata(
                metadata,
                max_depth=self.policy.max_metadata_depth,
                max_items=self.policy.max_metadata_items,
                max_text_length=self.policy.max_text_value_length,
            )

            fingerprint = None

            if self.policy.include_event_fingerprint:
                fingerprint = event_fingerprint(
                    kind=kind,
                    severity=severity,
                    message=safe_message,
                    run_id=safe_run_id,
                    stage=safe_stage,
                    app_key=safe_app_key,
                    package_id=safe_package_id,
                    metadata=safe_meta,
                )

            event = ObservabilityEvent(
                sequence=self._sequence,
                kind=kind,
                severity=severity,
                message=safe_message,
                timestamp=utc_now(),
                run_id=safe_run_id,
                stage=safe_stage,
                app_key=safe_app_key,
                package_id=safe_package_id,
                metadata=safe_meta,
                fingerprint=fingerprint,
            )

            try:
                self.sink.write(
                    event
                )
            except Exception:
                pass

            if (
                self.run is not None
                and severity == EventSeverity.WARNING
            ):
                self.run.counters.warnings += 1

            if (
                self.run is not None
                and severity == EventSeverity.SECURITY
            ):
                self.run.counters.security_events += 1

            if (
                app_key
                and app_key in self.apps
                and severity == EventSeverity.WARNING
            ):
                self.apps[
                    app_key
                ].warning_count += 1

            if (
                app_key
                and app_key in self.apps
                and severity in {
                    EventSeverity.ERROR,
                    EventSeverity.SECURITY,
                }
            ):
                self.apps[
                    app_key
                ].failure_count += 1

            return event

    # --------------------------------------------------------
    # Run lifecycle
    # --------------------------------------------------------

    def start_run(
        self,
        run_id: str,
        *,
        run_mode: str | None = None,
        max_apps: int | None = None,
        runtime_minutes: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> RunRecord:
        with self._lock:
            if (
                self.run is not None
                and self.run.state == RunState.RUNNING
            ):
                raise RuntimeError(
                    "A run is already active."
                )

            now = utc_now()

            record = RunRecord(
                run_id=clean_text(
                    run_id,
                    max_length=200,
                ),
                state=RunState.RUNNING,
                started_at=now,
                started_monotonic=time.monotonic(),
                run_mode=(
                    clean_text(
                        run_mode,
                        max_length=100,
                    )
                    if run_mode
                    else None
                ),
                max_apps=max_apps,
                runtime_minutes=runtime_minutes,
                metadata=safe_metadata(
                    metadata,
                    max_depth=self.policy.max_metadata_depth,
                    max_items=self.policy.max_metadata_items,
                    max_text_length=self.policy.max_text_value_length,
                ),
            )

            if not record.run_id:
                raise ValueError(
                    "run_id cannot be empty."
                )

            self.run = record

            self.emit(
                EventKind.RUN_STARTED,
                EventSeverity.INFO,
                "OSGuide Engine run started.",
                run_id=record.run_id,
                metadata={
                    "run_mode": record.run_mode,
                    "max_apps": record.max_apps,
                    "runtime_minutes": record.runtime_minutes,
                },
            )

            return record

    def finish_run(
        self,
        *,
        state: RunState = RunState.SUCCESS,
        metadata: Mapping[str, object] | None = None,
    ) -> RunRecord:
        with self._lock:
            if self.run is None:
                raise RuntimeError(
                    "No active run."
                )

            if state not in {
                RunState.SUCCESS,
                RunState.FAILED,
                RunState.CANCELLED,
                RunState.DEADLINE,
                RunState.PARTIAL,
            }:
                raise ValueError(
                    "Invalid terminal run state."
                )

            self.run.state = state
            self.run.finished_at = utc_now()
            self.run.finished_monotonic = time.monotonic()

            if metadata:
                self.run.metadata.update(
                    safe_metadata(
                        metadata,
                        max_depth=self.policy.max_metadata_depth,
                        max_items=self.policy.max_metadata_items,
                        max_text_length=self.policy.max_text_value_length,
                    )
                )

            event_kind = {
                RunState.SUCCESS: EventKind.RUN_FINISHED,
                RunState.PARTIAL: EventKind.RUN_FINISHED,
                RunState.FAILED: EventKind.RUN_FAILED,
                RunState.CANCELLED: EventKind.RUN_CANCELLED,
                RunState.DEADLINE: EventKind.RUN_DEADLINE,
            }[state]

            severity = (
                EventSeverity.INFO
                if state in {
                    RunState.SUCCESS,
                    RunState.PARTIAL,
                }
                else EventSeverity.WARNING
            )

            self.emit(
                event_kind,
                severity,
                f"OSGuide Engine run finished with state: {state.value}.",
                run_id=self.run.run_id,
                metadata={
                    "duration_seconds": round(
                        self.run.duration_seconds,
                        6,
                    ),
                    "counters": self.run.counters.as_dict(),
                },
            )

            return self.run

    def fail_run(
        self,
        exc: BaseException,
    ) -> RunRecord:
        if self.run is None:
            raise RuntimeError(
                "No active run."
            )

        self.run.last_error = clean_text(
            exc,
            max_length=self.policy.max_message_length,
        )

        self.emit(
            EventKind.RUN_FAILED,
            EventSeverity.ERROR,
            "OSGuide Engine run failed.",
            run_id=self.run.run_id,
            metadata={
                "exception": safe_exception_summary(
                    exc,
                    policy=self.policy,
                )
            },
        )

        return self.finish_run(
            state=RunState.FAILED
        )

    # --------------------------------------------------------
    # Stage lifecycle
    # --------------------------------------------------------

    def start_stage(
        self,
        name: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> StageRecord:
        with self._lock:
            safe_name = clean_text(
                name,
                max_length=100,
            )

            if not safe_name:
                raise ValueError(
                    "Stage name cannot be empty."
                )

            if (
                safe_name not in self.stages
                and len(self.stages)
                >= self.policy.max_stage_records
            ):
                raise RuntimeError(
                    "Stage record limit reached."
                )

            stage = self.stages.get(
                safe_name
            )

            if stage is None:
                stage = StageRecord(
                    name=safe_name
                )

                self.stages[
                    safe_name
                ] = stage

            stage.state = StageState.RUNNING
            stage.started_at = utc_now()
            stage.started_monotonic = time.monotonic()
            stage.finished_at = None
            stage.finished_monotonic = None
            stage.attempts += 1
            stage.last_error = None

            if metadata:
                stage.metadata.update(
                    safe_metadata(
                        metadata,
                        max_depth=self.policy.max_metadata_depth,
                        max_items=self.policy.max_metadata_items,
                        max_text_length=self.policy.max_text_value_length,
                    )
                )

            self.emit(
                EventKind.STAGE_STARTED,
                EventSeverity.INFO,
                f"Stage started: {safe_name}.",
                run_id=(
                    self.run.run_id
                    if self.run
                    else None
                ),
                stage=safe_name,
            )

            return stage

    def finish_stage(
        self,
        name: str,
        *,
        state: StageState = StageState.SUCCESS,
        processed: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> StageRecord:
        with self._lock:
            safe_name = clean_text(
                name,
                max_length=100,
            )

            stage = self.stages.get(
                safe_name
            )

            if stage is None:
                raise KeyError(
                    f"Unknown stage: {safe_name}"
                )

            if state not in {
                StageState.SUCCESS,
                StageState.FAILED,
                StageState.SKIPPED,
            }:
                raise ValueError(
                    "Invalid terminal stage state."
                )

            stage.state = state
            stage.finished_at = utc_now()
            stage.finished_monotonic = time.monotonic()

            if processed is not None:
                stage.processed = max(
                    0,
                    int(processed),
                )

            if metadata:
                stage.metadata.update(
                    safe_metadata(
                        metadata,
                        max_depth=self.policy.max_metadata_depth,
                        max_items=self.policy.max_metadata_items,
                        max_text_length=self.policy.max_text_value_length,
                    )
                )

            event_kind = {
                StageState.SUCCESS: EventKind.STAGE_FINISHED,
                StageState.FAILED: EventKind.STAGE_FAILED,
                StageState.SKIPPED: EventKind.STAGE_SKIPPED,
            }[state]

            severity = (
                EventSeverity.INFO
                if state != StageState.FAILED
                else EventSeverity.ERROR
            )

            self.emit(
                event_kind,
                severity,
                f"Stage finished: {safe_name} ({state.value}).",
                run_id=(
                    self.run.run_id
                    if self.run
                    else None
                ),
                stage=safe_name,
                metadata={
                    "duration_seconds": round(
                        stage.duration_seconds,
                        6,
                    ),
                    "processed": stage.processed,
                    "attempts": stage.attempts,
                    "failures": stage.failures,
                },
            )

            return stage

    def fail_stage(
        self,
        name: str,
        exc: BaseException,
    ) -> StageRecord:
        safe_name = clean_text(
            name,
            max_length=100,
        )

        stage = self.stages.get(
            safe_name
        )

        if stage is None:
            stage = self.start_stage(
                safe_name
            )

        stage.failures += 1
        stage.last_error = clean_text(
            exc,
            max_length=self.policy.max_message_length,
        )

        self.emit(
            EventKind.STAGE_FAILED,
            EventSeverity.ERROR,
            f"Stage failed: {safe_name}.",
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage=safe_name,
            metadata={
                "exception": safe_exception_summary(
                    exc,
                    policy=self.policy,
                )
            },
        )

        return self.finish_stage(
            safe_name,
            state=StageState.FAILED,
        )

    # --------------------------------------------------------
    # Application lifecycle
    # --------------------------------------------------------

    def start_app(
        self,
        app_key: str,
        *,
        name: str | None = None,
        package_id: str | None = None,
        source_type: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> AppRecord:
        with self._lock:
            safe_key = clean_text(
                app_key,
                max_length=300,
            )

            if not safe_key:
                raise ValueError(
                    "app_key cannot be empty."
                )

            if (
                safe_key not in self.apps
                and len(self.apps)
                >= self.policy.max_app_records
            ):
                raise RuntimeError(
                    "Application observability record limit reached."
                )

            record = self.apps.get(
                safe_key
            )

            if record is None:
                record = AppRecord(
                    key=safe_key
                )

                self.apps[
                    safe_key
                ] = record

            record.state = AppState.PROCESSING
            record.name = (
                clean_text(
                    name,
                    max_length=500,
                )
                if name
                else record.name
            )

            record.package_id = (
                clean_text(
                    package_id,
                    max_length=300,
                )
                if package_id
                else record.package_id
            )

            record.source_type = (
                clean_text(
                    source_type,
                    max_length=100,
                )
                if source_type
                else record.source_type
            )

            record.started_at = utc_now()
            record.started_monotonic = time.monotonic()
            record.finished_at = None
            record.finished_monotonic = None
            record.last_error = None

            if metadata:
                record.metadata.update(
                    safe_metadata(
                        metadata,
                        max_depth=self.policy.max_metadata_depth,
                        max_items=self.policy.max_metadata_items,
                        max_text_length=self.policy.max_text_value_length,
                    )
                )

            if self.run is not None:
                self.run.counters.candidates_processed += 1

            self.emit(
                EventKind.APP_STARTED,
                EventSeverity.INFO,
                "Application processing started.",
                run_id=(
                    self.run.run_id
                    if self.run
                    else None
                ),
                app_key=safe_key,
                package_id=record.package_id,
                metadata={
                    "name": record.name,
                    "source_type": record.source_type,
                },
            )

            return record

    def set_app_stage(
        self,
        app_key: str,
        stage: str,
    ) -> None:
        record = self.require_app(
            app_key
        )

        record.current_stage = clean_text(
            stage,
            max_length=100,
        )

    def set_app_decision(
        self,
        app_key: str,
        action: str,
        *,
        confidence: float | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        record = self.require_app(
            app_key
        )

        record.decision_action = clean_text(
            action,
            max_length=100,
        )

        event_meta: dict[
            str,
            object,
        ] = {
            "action": record.decision_action,
        }

        if confidence is not None:
            event_meta[
                "confidence"
            ] = max(
                0.0,
                min(
                    1.0,
                    float(confidence),
                ),
            )

        event_meta.update(
            safe_metadata(
                metadata
            )
        )

        if self.run is not None:
            action_lower = record.decision_action.lower()

            if action_lower == "insert":
                self.run.counters.inserts += 1
            elif action_lower == "update":
                self.run.counters.updates += 1
            elif action_lower == "repair":
                self.run.counters.repairs += 1
            elif action_lower == "skip":
                self.run.counters.skipped += 1
            elif action_lower == "review":
                self.run.counters.reviews += 1

        self.emit(
            EventKind.DECISION,
            EventSeverity.INFO,
            "Decision Engine result recorded.",
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="decision",
            app_key=record.key,
            package_id=record.package_id,
            metadata=event_meta,
        )

    def set_app_publication(
        self,
        app_key: str,
        status: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        record = self.require_app(
            app_key
        )

        record.publication_status = clean_text(
            status,
            max_length=100,
        )

        self.emit(
            EventKind.PUBLISHER,
            EventSeverity.INFO,
            "Publisher result recorded.",
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="publisher",
            app_key=record.key,
            package_id=record.package_id,
            metadata={
                "status": record.publication_status,
                **safe_metadata(
                    metadata
                ),
            },
        )

    def finish_app(
        self,
        app_key: str,
        *,
        state: AppState = AppState.SUCCESS,
        metadata: Mapping[str, object] | None = None,
    ) -> AppRecord:
        record = self.require_app(
            app_key
        )

        if state not in {
            AppState.SUCCESS,
            AppState.SKIPPED,
            AppState.REVIEW,
            AppState.FAILED,
            AppState.BLOCKED,
        }:
            raise ValueError(
                "Invalid terminal application state."
            )

        record.state = state
        record.finished_at = utc_now()
        record.finished_monotonic = time.monotonic()

        if metadata:
            record.metadata.update(
                safe_metadata(
                    metadata,
                    max_depth=self.policy.max_metadata_depth,
                    max_items=self.policy.max_metadata_items,
                    max_text_length=self.policy.max_text_value_length,
                )
            )

        event_kind = {
            AppState.SUCCESS: EventKind.APP_FINISHED,
            AppState.SKIPPED: EventKind.APP_SKIPPED,
            AppState.REVIEW: EventKind.APP_REVIEW,
            AppState.FAILED: EventKind.APP_FAILED,
            AppState.BLOCKED: EventKind.APP_REVIEW,
        }[state]

        severity = (
            EventSeverity.INFO
            if state in {
                AppState.SUCCESS,
                AppState.SKIPPED,
            }
            else (
                EventSeverity.WARNING
                if state in {
                    AppState.REVIEW,
                    AppState.BLOCKED,
                }
                else EventSeverity.ERROR
            )
        )

        if self.run is not None:
            if state == AppState.SKIPPED:
                self.run.counters.skipped += 1
            elif state == AppState.REVIEW:
                self.run.counters.reviews += 1
            elif state == AppState.BLOCKED:
                self.run.counters.blocked += 1
            elif state == AppState.FAILED:
                self.run.counters.failures += 1

        self.emit(
            event_kind,
            severity,
            f"Application processing finished: {state.value}.",
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            app_key=record.key,
            package_id=record.package_id,
            metadata={
                "duration_seconds": round(
                    record.duration_seconds,
                    6,
                ),
                "decision_action": record.decision_action,
                "publication_status": record.publication_status,
            },
        )

        return record

    def fail_app(
        self,
        app_key: str,
        exc: BaseException,
    ) -> AppRecord:
        record = self.require_app(
            app_key
        )

        record.last_error = clean_text(
            exc,
            max_length=self.policy.max_message_length,
        )

        self.emit(
            EventKind.APP_FAILED,
            EventSeverity.ERROR,
            "Application processing failed.",
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            app_key=record.key,
            package_id=record.package_id,
            metadata={
                "exception": safe_exception_summary(
                    exc,
                    policy=self.policy,
                )
            },
        )

        return self.finish_app(
            app_key,
            state=AppState.FAILED,
        )

    def require_app(
        self,
        app_key: str,
    ) -> AppRecord:
        safe_key = clean_text(
            app_key,
            max_length=300,
        )

        record = self.apps.get(
            safe_key
        )

        if record is None:
            raise KeyError(
                f"Application observability record not found: {safe_key}"
            )

        return record

    # --------------------------------------------------------
    # Convenience stage events
    # --------------------------------------------------------

    def discovery_event(
        self,
        message: str,
        *,
        severity: EventSeverity = EventSeverity.INFO,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.emit(
            EventKind.DISCOVERY,
            severity,
            message,
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="discovery",
            metadata=metadata,
        )

    def resolution_event(
        self,
        message: str,
        *,
        app_key: str | None = None,
        package_id: str | None = None,
        severity: EventSeverity = EventSeverity.INFO,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.emit(
            EventKind.RESOLUTION,
            severity,
            message,
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="resolver",
            app_key=app_key,
            package_id=package_id,
            metadata=metadata,
        )

    def apk_event(
        self,
        message: str,
        *,
        app_key: str | None = None,
        package_id: str | None = None,
        severity: EventSeverity = EventSeverity.INFO,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.emit(
            EventKind.APK,
            severity,
            message,
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="apk-intelligence",
            app_key=app_key,
            package_id=package_id,
            metadata=metadata,
        )

    def content_event(
        self,
        message: str,
        *,
        app_key: str | None = None,
        package_id: str | None = None,
        severity: EventSeverity = EventSeverity.INFO,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.emit(
            EventKind.CONTENT,
            severity,
            message,
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="content-intelligence",
            app_key=app_key,
            package_id=package_id,
            metadata=metadata,
        )

    def memory_event(
        self,
        message: str,
        *,
        app_key: str | None = None,
        package_id: str | None = None,
        severity: EventSeverity = EventSeverity.INFO,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.emit(
            EventKind.MEMORY,
            severity,
            message,
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="memory",
            app_key=app_key,
            package_id=package_id,
            metadata=metadata,
        )

    def security_event(
        self,
        message: str,
        *,
        app_key: str | None = None,
        package_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.emit(
            EventKind.SECURITY,
            EventSeverity.SECURITY,
            message,
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="security",
            app_key=app_key,
            package_id=package_id,
            metadata=metadata,
        )

    def diagnostic_event(
        self,
        message: str,
        *,
        severity: EventSeverity = EventSeverity.INFO,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.emit(
            EventKind.DIAGNOSTIC,
            severity,
            message,
            run_id=(
                self.run.run_id
                if self.run
                else None
            ),
            stage="diagnostic",
            metadata=metadata,
        )

    # --------------------------------------------------------
    # Counter helpers
    # --------------------------------------------------------

    def increment(
        self,
        name: str,
        amount: int = 1,
    ) -> None:
        if self.run is None:
            return

        self.run.counters.increment(
            name,
            amount,
        )

    # --------------------------------------------------------
    # Reports
    # --------------------------------------------------------

    def run_summary(
        self,
    ) -> dict[str, object]:
        return {
            "component": OBSERVABILITY_COMPONENT,
            "schema_version": OBSERVABILITY_SCHEMA_VERSION,
            "run": (
                self.run.to_dict()
                if self.run
                else None
            ),
            "stage_count": len(
                self.stages
            ),
            "application_count": len(
                self.apps
            ),
            "stages": {
                name: stage.to_dict()
                for name, stage in sorted(
                    self.stages.items()
                )
            },
            "applications": {
                key: app.to_dict()
                for key, app in sorted(
                    self.apps.items()
                )
            },
        }

    def compact_summary(
        self,
    ) -> dict[str, object]:
        run = self.run

        return {
            "run_id": (
                run.run_id
                if run
                else None
            ),
            "state": (
                run.state.value
                if run
                else RunState.CREATED.value
            ),
            "duration_seconds": (
                round(
                    run.duration_seconds,
                    3,
                )
                if run
                else 0.0
            ),
            "counters": (
                run.counters.as_dict()
                if run
                else CounterSet().as_dict()
            ),
            "stages": {
                name: {
                    "state": stage.state.value,
                    "duration_seconds": round(
                        stage.duration_seconds,
                        3,
                    ),
                    "processed": stage.processed,
                    "failures": stage.failures,
                }
                for name, stage in sorted(
                    self.stages.items()
                )
            },
        }

    def write_report(
        self,
        path: str | Path,
        *,
        compact: bool = False,
    ) -> Path:
        target = Path(
            path
        )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = (
            self.compact_summary()
            if compact
            else self.run_summary()
        )

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            default=json_default,
        )

        target.write_text(
            serialized,
            encoding="utf-8",
        )

        try:
            os.chmod(
                target,
                0o600,
            )
        except OSError:
            pass

        return target


# ============================================================
# Context helpers
# ============================================================

class StageScope:
    def __init__(
        self,
        observer: EngineObserver,
        name: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.observer = observer
        self.name = name
        self.metadata = metadata

    def __enter__(
        self,
    ) -> StageRecord:
        return self.observer.start_stage(
            self.name,
            metadata=self.metadata,
        )

    def __exit__(
        self,
        exc_type: object,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        del exc_type
        del traceback

        if exc is None:
            self.observer.finish_stage(
                self.name,
                state=StageState.SUCCESS,
            )
            return False

        self.observer.fail_stage(
            self.name,
            exc,
        )

        return False


class AppScope:
    def __init__(
        self,
        observer: EngineObserver,
        app_key: str,
        *,
        name: str | None = None,
        package_id: str | None = None,
        source_type: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.observer = observer
        self.app_key = app_key
        self.name = name
        self.package_id = package_id
        self.source_type = source_type
        self.metadata = metadata

    def __enter__(
        self,
    ) -> AppRecord:
        return self.observer.start_app(
            self.app_key,
            name=self.name,
            package_id=self.package_id,
            source_type=self.source_type,
            metadata=self.metadata,
        )

    def __exit__(
        self,
        exc_type: object,
        exc: BaseException | None,
        traceback: object,
    ) -> bool:
        del exc_type
        del traceback

        if exc is None:
            record = self.observer.require_app(
                self.app_key
            )

            if record.state == AppState.PROCESSING:
                self.observer.finish_app(
                    self.app_key,
                    state=AppState.SUCCESS,
                )

            return False

        self.observer.fail_app(
            self.app_key,
            exc,
        )

        return False


def stage_scope(
    observer: EngineObserver,
    name: str,
    *,
    metadata: Mapping[str, object] | None = None,
) -> StageScope:
    return StageScope(
        observer,
        name,
        metadata=metadata,
    )


def app_scope(
    observer: EngineObserver,
    app_key: str,
    *,
    name: str | None = None,
    package_id: str | None = None,
    source_type: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> AppScope:
    return AppScope(
        observer,
        app_key,
        name=name,
        package_id=package_id,
        source_type=source_type,
        metadata=metadata,
    )


# ============================================================
# Factory helpers
# ============================================================

def create_memory_observer(
    *,
    policy: ObservabilityPolicy | None = None,
) -> EngineObserver:
    effective_policy = (
        policy
        or ObservabilityPolicy()
    )

    effective_policy.validate()

    sink = MemoryEventSink(
        max_events=effective_policy.max_events
    )

    return EngineObserver(
        policy=effective_policy,
        sink=sink,
    )


def create_jsonl_observer(
    path: str | Path,
    *,
    policy: ObservabilityPolicy | None = None,
    also_keep_memory: bool = True,
) -> EngineObserver:
    effective_policy = (
        policy
        or ObservabilityPolicy()
    )

    effective_policy.validate()

    sinks: list[
        EventSink
    ] = [
        JsonlEventSink(
            path
        )
    ]

    if also_keep_memory:
        sinks.append(
            MemoryEventSink(
                max_events=effective_policy.max_events
            )
        )

    return EngineObserver(
        policy=effective_policy,
        sink=CompositeEventSink(
            sinks
        ),
    )


# ============================================================
# Diagnostics
# ============================================================

def run_observability_diagnostic() -> dict[str, object]:
    observer = create_memory_observer(
        policy=ObservabilityPolicy(
            enabled=True,
            debug_enabled=True,
            max_events=500,
            max_stage_records=100,
            max_app_records=100,
        )
    )

    observer.start_run(
        "diagnostic-run",
        run_mode="dry-run",
        max_apps=5,
        runtime_minutes=5,
        metadata={
            "diagnostic": True,
            "api_key": "should-be-redacted",
        },
    )

    with stage_scope(
        observer,
        "discovery",
    ):
        observer.increment(
            "discovered",
            1,
        )

        observer.discovery_event(
            "Diagnostic candidate discovered.",
            metadata={
                "source": "github",
            },
        )

    app_key = "package:org.osguide.diagnostic"

    with app_scope(
        observer,
        app_key,
        name="OSGuide Diagnostic App",
        package_id="org.osguide.diagnostic",
        source_type="github",
    ):
        observer.set_app_stage(
            app_key,
            "resolver",
        )

        observer.resolution_event(
            "Diagnostic resolution completed.",
            app_key=app_key,
            package_id="org.osguide.diagnostic",
            metadata={
                "confidence": 0.95,
            },
        )

        observer.increment(
            "resolved",
            1,
        )

        observer.set_app_stage(
            app_key,
            "apk-intelligence",
        )

        observer.apk_event(
            "Diagnostic APK selected.",
            app_key=app_key,
            package_id="org.osguide.diagnostic",
            metadata={
                "verification": "match",
            },
        )

        observer.increment(
            "apk_selected",
            1,
        )

        observer.set_app_decision(
            app_key,
            "insert",
            confidence=0.95,
        )

        observer.set_app_publication(
            app_key,
            "dry-run",
        )

    observer.finish_run(
        state=RunState.SUCCESS
    )

    sink = observer.sink

    event_count = None

    if isinstance(
        sink,
        MemoryEventSink,
    ):
        event_count = len(
            sink.events
        )

    return {
        "event_count": event_count,
        "summary": observer.compact_summary(),
    }


def run_redaction_diagnostic() -> dict[str, object]:
    metadata = {
        "api_key": "abc123-super-secret",
        "authorization": "Bearer example",
        "normal_value": "safe",
        "nested": {
            "token": "secret-token",
            "package_id": "org.osguide.example",
        },
    }

    return safe_metadata(
        metadata
    )


# ============================================================
# Public exports
# ============================================================

__all__: Final[tuple[str, ...]] = (
    "AppRecord",
    "AppScope",
    "AppState",
    "CompositeEventSink",
    "CounterSet",
    "DEFAULT_MAX_APP_RECORDS",
    "DEFAULT_MAX_EVENTS",
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_MESSAGE_LENGTH",
    "DEFAULT_MAX_METADATA_DEPTH",
    "DEFAULT_MAX_METADATA_ITEMS",
    "DEFAULT_MAX_STAGE_RECORDS",
    "DEFAULT_MAX_TEXT_VALUE_LENGTH",
    "EngineObserver",
    "EventKind",
    "EventSeverity",
    "EventSink",
    "JsonlEventSink",
    "MemoryEventSink",
    "NullEventSink",
    "OBSERVABILITY_COMPONENT",
    "OBSERVABILITY_SCHEMA_VERSION",
    "ObservabilityEvent",
    "ObservabilityPolicy",
    "RunRecord",
    "RunState",
    "StageRecord",
    "StageScope",
    "StageState",
    "app_scope",
    "clean_text",
    "create_jsonl_observer",
    "create_memory_observer",
    "event_fingerprint",
    "isoformat_utc",
    "json_default",
    "looks_secret_like",
    "run_observability_diagnostic",
    "run_redaction_diagnostic",
    "safe_exception_summary",
    "safe_metadata",
    "safe_value",
    "stage_scope",
    "utc_now",
)
