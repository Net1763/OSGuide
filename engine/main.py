"""
OSGuide Engine
Main Controller

Purpose
-------
This file is the central controller for the OSGuide automation engine.

Current responsibilities:
- Load and validate GitHub Actions runtime configuration.
- Create a unique run ID.
- Enforce a global runtime budget.
- Support graceful cancellation.
- Execute the Discovery layer safely.
- Isolate failures.
- Preserve dry-run safety.
- Produce a detailed final report.

Important architectural rules preserved here:
- Admin remains the highest authority.
- No automatic deletion.
- One app/source failure must not stop the entire run.
- Publish mode must never write unless the Publisher layer is explicitly connected.
- Secrets must never be printed.
- Runtime limits and safe shutdown are mandatory.
- Future modules (Resolver, APK Intelligence, AI, Publisher, Memory,
  Audit, Rollback, Review) plug into this controller without replacing it.

This phase is intentionally non-destructive.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Final

from config import (
    ENGINE_NAME,
    ENGINE_VERSION,
    EngineConfig,
    describe_config,
    load_config,
)

from discovery import (
    AppCandidate,
    DiscoveryReport,
    DiscoverySourceResult,
    run_default_discovery,
)

from resolver import (
    MetadataField,
    ResolutionStatus,
    run_live_resolver,
)

from apk_intelligence import (
    ApkSelectionStatus,
    run_live_apk_intelligence,
)

from content_intelligence import (
    ContentStatus,
    run_live_content_intelligence,
)

from decision_engine import (
    DecisionInput,
    decide,
)

from ai_review import (
    ai_review_log_summary,
    review_decision,
)

from publisher import (
    ApplicationPayload,
    BackendStatus,
    DiagnosticPublisherBackend,
    PublicationAction,
    PublicationRequest,
    PublicationStatus,
    PublisherCounters,
    PublisherPolicy,
    PublisherSchema,
    SupabaseRestBackend,
    WriteMode,
    execute_publication,
    live_policy_from_environment,
    parse_existing_application,
)

from memory import (
    MemoryStatus,
    RetryDecision,
    create_in_memory_manager,
    create_json_memory_manager,
    remember_apk,
    remember_candidate,
    remember_content,
    remember_decision,
    remember_publication,
    remember_resolution,
)


# ============================================================
# Exit codes
# ============================================================

EXIT_SUCCESS: Final[int] = 0
EXIT_CONFIGURATION_ERROR: Final[int] = 2
EXIT_RUNTIME_ERROR: Final[int] = 3
EXIT_CANCELLED: Final[int] = 130


# ============================================================
# Controller constants
# ============================================================

DEADLINE_SAFETY_SECONDS: Final[int] = 5
REPORT_SCHEMA_VERSION: Final[str] = "1"
RUN_COMPONENT: Final[str] = "discover"

# The Publisher layer is connected. Real external writes still require
# BOTH run_mode=publish and OSGUIDE_PUBLISH_ENABLED=true at runtime.
# Dry-run remains non-destructive and uses the diagnostic backend.
PUBLISHER_CONNECTED: Final[bool] = True

# Future phase names are centralized here so logs and reports
# remain stable as the engine grows.
PHASE_DISCOVERY: Final[str] = "discovery"
PHASE_RESOLUTION: Final[str] = "resolution"
PHASE_VERIFICATION: Final[str] = "verification"
PHASE_CONTENT: Final[str] = "content"
PHASE_DECISION: Final[str] = "decision"
PHASE_PUBLISH: Final[str] = "publish"


# ============================================================
# Runtime state models
# ============================================================

@dataclass(slots=True)
class PhaseStats:
    name: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    succeeded: bool = False
    skipped: bool = False
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        if self.started_at is None:
            return 0.0

        end_time = self.finished_at or datetime.now(timezone.utc)

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )


@dataclass(slots=True)
class RunStats:
    started_at: datetime
    finished_at: datetime | None = None

    candidates_seen: int = 0
    candidates_processed: int = 0

    published: int = 0
    updated: int = 0
    repaired: int = 0
    skipped: int = 0
    review_required: int = 0
    failures: int = 0

    content_candidates_processed: int = 0
    content_candidates_completed: int = 0
    content_candidates_review_required: int = 0
    content_candidates_failed: int = 0

    decision_candidates_processed: int = 0
    decision_insert_recommended: int = 0
    decision_update_recommended: int = 0
    decision_repair_recommended: int = 0
    decision_skip_recommended: int = 0
    decision_review_recommended: int = 0
    decision_blocked: int = 0
    decision_failed: int = 0

    publisher_dry_run: int = 0
    publisher_blocked: int = 0
    publisher_review: int = 0
    publisher_skipped: int = 0
    publisher_failed: int = 0

    discovery_sources_succeeded: int = 0
    discovery_sources_failed: int = 0
    discovery_duplicates_removed: int = 0
    discovery_invalid_removed: int = 0

    stopped_by_deadline: bool = False
    cancelled: bool = False

    current_candidate: str | None = None

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    phases: dict[str, PhaseStats] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        end_time = self.finished_at or datetime.now(timezone.utc)

        return max(
            0.0,
            (end_time - self.started_at).total_seconds(),
        )


# ============================================================
# Logging helpers
# ============================================================

def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def log_header(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def log_info(message: str) -> None:
    print(f"[{_timestamp()}] [INFO] {message}")


def log_warning(message: str) -> None:
    print(f"[{_timestamp()}] [WARN] {message}")


def log_error(message: str) -> None:
    print(
        f"[{_timestamp()}] [ERROR] {message}",
        file=sys.stderr,
    )


def log_debug(message: str) -> None:
    if os.getenv("OSGUIDE_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print(f"[{_timestamp()}] [DEBUG] {message}")


# ============================================================
# Safe text helpers
# ============================================================

def safe_text(value: object, *, max_length: int = 500) -> str:
    """
    Convert arbitrary values to safe printable text.

    This helper intentionally limits length to prevent very large
    external values from flooding GitHub Actions logs.
    """

    text = str(value)

    text = text.replace("\r", " ").replace("\n", " ")

    if len(text) > max_length:
        text = text[:max_length] + "…"

    return text


def app_name_requires_review(value: object) -> bool:
    """
    Reject obviously unsafe/low-quality display names before publication.

    This intentionally does not invent a replacement name. A suspicious
    name is sent to review instead of being published.
    """
    name = str(value or "").strip()

    if not name:
        return True

    if len(name) < 2 or len(name) > 120:
        return True

    compact = re.sub(r"[\s._+\-]+", "", name)

    # Examples such as "12345" must never be auto-published.
    if compact.isdigit():
        return True

    # A package ID is not an acceptable public application name.
    if (
        "." in name
        and " " not in name
        and re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+",
            name,
        )
    ):
        return True

    # Require at least one alphabetic character for automatic publication.
    if not any(character.isalpha() for character in name):
        return True

    return False


def sanitize_exception(exc: BaseException) -> str:
    """
    Return a bounded exception description without stack traces,
    environment variables, or secret values.
    """

    return (
        f"{type(exc).__name__}: "
        f"{safe_text(exc, max_length=300)}"
    )


# ============================================================
# Run identifier
# ============================================================

def create_run_id() -> str:
    """
    Create a deterministic human-readable run identifier.

    Example:
        20260819-130500-discover
    """

    now = datetime.now(timezone.utc)

    return (
        now.strftime("%Y%m%d-%H%M%S")
        + f"-{RUN_COMPONENT}"
    )


# ============================================================
# Deadline controller
# ============================================================

class DeadlineController:
    """
    Central runtime budget controller.

    Every expensive engine stage should consult this object before
    starting new work. This prevents a single candidate from causing
    the GitHub Action to overrun its intended time window.
    """

    def __init__(self, runtime_seconds: int) -> None:
        if runtime_seconds <= 0:
            raise ValueError(
                "runtime_seconds must be greater than zero."
            )

        self._started_monotonic = time.monotonic()
        self._runtime_seconds = runtime_seconds

    @property
    def elapsed_seconds(self) -> float:
        return max(
            0.0,
            time.monotonic() - self._started_monotonic,
        )

    @property
    def remaining_seconds(self) -> float:
        return max(
            0.0,
            self._runtime_seconds - self.elapsed_seconds,
        )

    def deadline_reached(self) -> bool:
        return self.remaining_seconds <= 0

    def can_start_new_work(
        self,
        *,
        safety_seconds: int = DEADLINE_SAFETY_SECONDS,
    ) -> bool:
        return self.remaining_seconds > safety_seconds

    def require_time_for_new_work(
        self,
        *,
        safety_seconds: int = DEADLINE_SAFETY_SECONDS,
    ) -> None:
        if not self.can_start_new_work(
            safety_seconds=safety_seconds
        ):
            raise RuntimeError(
                "Runtime deadline is too close to start new work."
            )


# ============================================================
# Cancellation controller
# ============================================================

class CancellationController:
    """
    Tracks graceful shutdown requests.

    GitHub Actions cancellation may terminate the process quickly,
    but when Python receives SIGTERM/SIGINT we mark the run as
    cancelled and stop starting new candidate work.
    """

    def __init__(self) -> None:
        self._requested = False
        self._signal_name: str | None = None

    @property
    def requested(self) -> bool:
        return self._requested

    @property
    def signal_name(self) -> str | None:
        return self._signal_name

    def request(self, signal_name: str) -> None:
        self._requested = True
        self._signal_name = signal_name


CANCELLATION = CancellationController()


def _signal_handler(signum: int, _frame: object) -> None:
    try:
        signal_name = signal.Signals(signum).name
    except Exception:
        signal_name = f"signal-{signum}"

    CANCELLATION.request(signal_name)

    log_warning(
        f"Graceful cancellation requested by {signal_name}."
    )


def install_signal_handlers() -> None:
    for signal_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signal_name, None)

        if sig is not None:
            signal.signal(sig, _signal_handler)


# ============================================================
# Phase bookkeeping
# ============================================================

def begin_phase(
    stats: RunStats,
    phase_name: str,
) -> PhaseStats:
    phase = PhaseStats(
        name=phase_name,
        started_at=datetime.now(timezone.utc),
    )

    stats.phases[phase_name] = phase

    log_header(
        f"PHASE — {phase_name.upper()}"
    )

    return phase


def finish_phase_success(
    phase: PhaseStats,
) -> None:
    phase.finished_at = datetime.now(timezone.utc)
    phase.succeeded = True


def finish_phase_skipped(
    phase: PhaseStats,
    reason: str,
) -> None:
    phase.finished_at = datetime.now(timezone.utc)
    phase.skipped = True
    phase.error = reason


def finish_phase_failure(
    phase: PhaseStats,
    error: str,
) -> None:
    phase.finished_at = datetime.now(timezone.utc)
    phase.error = error


# ============================================================
# Candidate logging
# ============================================================

def log_candidate(candidate: AppCandidate) -> None:
    log_info(
        f"Candidate: {safe_text(candidate.name, max_length=120)}"
    )

    log_info(
        "Source type: "
        f"{safe_text(candidate.source_type, max_length=40)}"
    )

    log_info(
        "Source confidence: "
        f"{candidate.source_confidence:.2f}"
    )

    if candidate.package_id:
        log_info(
            "Package ID hint: "
            f"{safe_text(candidate.package_id, max_length=160)}"
        )

    if candidate.repository_url:
        log_info(
            "Repository: "
            f"{safe_text(candidate.repository_url, max_length=300)}"
        )


# ============================================================
# Discovery reporting helpers
# ============================================================

def apply_discovery_report(
    report: DiscoveryReport,
    stats: RunStats,
) -> None:
    stats.discovery_sources_succeeded = (
        report.sources_succeeded
    )

    stats.discovery_sources_failed = (
        report.sources_failed
    )

    stats.discovery_duplicates_removed = (
        report.duplicates_removed
    )

    stats.discovery_invalid_removed = (
        report.invalid_candidates_removed
    )


def log_source_result(
    result: DiscoverySourceResult,
    stats: RunStats,
) -> None:
    source_name = safe_text(
        result.source_name,
        max_length=80,
    )

    if result.succeeded:
        log_info(
            f"Source {source_name!r} succeeded with "
            f"{len(result.candidates)} candidate(s) "
            f"in {result.duration_seconds:.2f}s."
        )

        return

    stats.failures += 1

    message = (
        f"Source {source_name!r} failed: "
        f"{safe_text(result.error or 'unknown error', max_length=300)}"
    )

    stats.warnings.append(message)

    log_warning(message)


# ============================================================
# Current Phase 2 discovery pipeline
# ============================================================

def run_discovery_phase(
    *,
    config: EngineConfig,
    stats: RunStats,
    deadline: DeadlineController,
    run_id: str,
) -> None:
    """
    Execute the current safe discovery phase.

    Execute the connected default discovery registry safely.
    Trusted discovery providers are selected by discovery.py while
    this controller preserves runtime and dry-run safety.
    """

    phase = begin_phase(
        stats,
        PHASE_DISCOVERY,
    )

    try:
        if CANCELLATION.requested:
            stats.cancelled = True

            finish_phase_skipped(
                phase,
                "Cancellation requested before discovery started.",
            )

            return

        if not deadline.can_start_new_work():
            stats.stopped_by_deadline = True

            finish_phase_skipped(
                phase,
                "Runtime deadline too close to begin discovery.",
            )

            log_warning(
                "Runtime deadline is too close to begin discovery."
            )

            return

        if config.publishing_enabled and not PUBLISHER_CONNECTED:
            raise RuntimeError(
                "Publish mode was selected, but the Publisher layer is not connected."
            )

        log_info(
            "Starting default discovery pipeline."
        )

        report = run_default_discovery(
            max_apps=config.max_apps,
        )

        apply_discovery_report(
            report,
            stats,
        )

        for source_result in report.source_results:
            log_source_result(
                source_result,
                stats,
            )

        # Publisher backend selection.
        # Dry-run always uses the local diagnostic backend.
        # Publish mode uses the real Supabase backend only when the Publisher
        # environment safety switch is explicitly enabled.
        publisher_schema = PublisherSchema()
        publisher_counters = PublisherCounters()

        if config.publishing_enabled:
            publisher_policy = live_policy_from_environment()

            if (
                not publisher_policy.enabled
                or publisher_policy.write_mode != WriteMode.LIVE
            ):
                raise RuntimeError(
                    "Publish mode was selected, but the live Publisher safety "
                    "switch is not enabled. Expected OSGUIDE_PUBLISH_ENABLED=true."
                )

            publisher_backend = SupabaseRestBackend(
                schema=publisher_schema,
                timeout_seconds=publisher_policy.request_timeout_seconds,
            )
            publisher_backend_name = "supabase-live"
            publisher_external_writes_enabled = True
            log_info(
                "Publisher: live Supabase backend ready; controlled external writes enabled."
            )
        else:
            publisher_backend = DiagnosticPublisherBackend(
                schema=publisher_schema
            )
            publisher_policy = PublisherPolicy(
                enabled=False,
                write_mode=WriteMode.DRY_RUN,
            )
            publisher_backend_name = "diagnostic"
            publisher_external_writes_enabled = False
            log_info(
                "Publisher: diagnostic dry-run backend ready; external writes disabled."
            )

        # Existing-application lookup is always read-only. In live publish mode
        # the same Supabase transport can safely perform the lookup before the
        # Publisher later executes a controlled mutation.
        existing_lookup_backend: SupabaseRestBackend | None = None

        if isinstance(publisher_backend, SupabaseRestBackend):
            existing_lookup_backend = publisher_backend
            log_info(
                "Existing-application lookup: Supabase read-only connection ready."
            )
        elif (
            os.getenv("OSGUIDE_SUPABASE_URL", "").strip()
            and os.getenv("OSGUIDE_ENGINE_KEY", "").strip()
        ):
            try:
                existing_lookup_backend = SupabaseRestBackend(
                    schema=publisher_schema
                )
                log_info(
                    "Existing-application lookup: Supabase read-only connection ready."
                )
            except Exception as lookup_backend_exc:
                warning = (
                    "Existing-application lookup could not be initialized; "
                    "duplicate-sensitive decisions will fail closed: "
                    f"{sanitize_exception(lookup_backend_exc)}"
                )
                stats.warnings.append(warning)
                log_warning(warning)
        else:
            warning = (
                "Existing-application lookup credentials are unavailable; "
                "duplicate-sensitive decisions will fail closed."
            )
            stats.warnings.append(warning)
            log_warning(warning)

        # Durable Memory Layer. The JSON file is safe engine runtime state only;
        # it never contains Supabase credentials and never writes application rows.
        memory_path = (
            os.getenv("OSGUIDE_MEMORY_PATH", ".osguide/runtime/memory.json").strip()
            or ".osguide/runtime/memory.json"
        )

        try:
            engine_memory = create_json_memory_manager(memory_path)
            log_info(
                "Memory Layer: file-backed runtime memory ready at "
                f"{safe_text(memory_path, max_length=240)}."
            )
        except Exception as memory_init_exc:
            warning = (
                "Memory Layer could not initialize durable storage; "
                "falling back to in-memory safety for this run: "
                f"{sanitize_exception(memory_init_exc)}"
            )
            stats.warnings.append(warning)
            log_warning(warning)
            engine_memory = create_in_memory_manager()

        def save_memory_safely() -> None:
            try:
                save_result = engine_memory.save()
                if not save_result.succeeded:
                    warning = (
                        "Memory Layer save failed: "
                        + safe_text(save_result.error or "unknown error", max_length=300)
                    )
                    stats.warnings.append(warning)
                    log_warning(warning)
            except Exception as memory_save_exc:
                warning = (
                    "Memory Layer save raised an error: "
                    f"{sanitize_exception(memory_save_exc)}"
                )
                stats.warnings.append(warning)
                log_warning(warning)

        for candidate in report.candidates:
            if CANCELLATION.requested:
                stats.cancelled = True

                log_warning(
                    "Cancellation requested. "
                    "No new candidate will be processed."
                )

                # KEY FIX: Continue instead of Break to process all remaining candidates
                # if they fit within the time window.
                continue

            if not deadline.can_start_new_work():
                stats.stopped_by_deadline = True

                log_warning(
                    "Runtime deadline is approaching. "
                    "No new candidate will be processed."
                )

                # KEY FIX: Continue instead of Break. The remaining seconds
                # should be used to process the next candidate, not wasted.
                continue

            stats.current_candidate = candidate.name
            stats.candidates_seen += 1

            log_candidate(candidate)

            # ------------------------------------------------
            # Memory preflight: stable identity + retry/cooldown policy.
            # This happens before expensive Resolver/APK/Content work.
            # ------------------------------------------------
            memory_record = remember_candidate(engine_memory, candidate)
            memory_key = memory_record.key
            retry_decision = engine_memory.retry_decision(memory_key)

            log_info(
                "Memory preflight: "
                f"key={safe_text(memory_key, max_length=220)}; "
                f"decision={retry_decision.value}."
            )

            if retry_decision != RetryDecision.PROCESS:
                stats.skipped += 1

                if retry_decision in {
                    RetryDecision.REVIEW_REQUIRED,
                    RetryDecision.BLOCKED,
                    RetryDecision.ATTEMPTS_EXHAUSTED,
                }:
                    stats.review_required += 1

                log_info(
                    "Candidate skipped by Memory Layer before expensive processing: "
                    f"{retry_decision.value}."
                )
                save_memory_safely()
                stats.current_candidate = None
                continue

            engine_memory.mark_processing(memory_key)

            # ------------------------------------------------
            # Phase 3: live read-only Resolver.
            # No publishing or external writes occur here.
            # ------------------------------------------------

            stats.candidates_processed += 1

            try:
                resolved = run_live_resolver(candidate)

                remember_resolution(
                    engine_memory,
                    memory_key,
                    resolved,
                    summary={
                        "status": resolved.status.value,
                        "resolved_fields": resolved.resolved_field_count,
                        "conflicts": resolved.conflict_count,
                    },
                )

                log_info(
                    "Resolver status: "
                    f"{resolved.status.value}; "
                    f"resolved fields: {resolved.resolved_field_count}; "
                    f"conflicts: {resolved.conflict_count}."
                )

                for metadata_field in (
                    MetadataField.NAME,
                    MetadataField.PACKAGE_ID,
                    MetadataField.VERSION,
                    MetadataField.APK_URL,
                    MetadataField.ICON_URL,
                    MetadataField.LICENSE,
                    MetadataField.CATEGORY,
                    MetadataField.SHORT_DESCRIPTION,
                    MetadataField.FULL_DESCRIPTION,
                    MetadataField.SOURCE_URL,
                ):
                    field_result = resolved.field_result(metadata_field)

                    if field_result.resolved:
                        log_info(
                            f"Resolved {metadata_field.value}: "
                            f"{safe_text(field_result.value, max_length=300)}"
                        )

                if resolved.status in {
                    ResolutionStatus.RESOLVED,
                    ResolutionStatus.PARTIAL,
                }:
                    log_info(
                        "Candidate completed the live read-only "
                        "Resolver path."
                    )

                    # --------------------------------------------
                    # Phase 4: live read-only APK Intelligence.
                    # Structural/trusted-source APK selection only.
                    # No APK body download or external write occurs.
                    # --------------------------------------------
                    package_result = resolved.field_result(
                        MetadataField.PACKAGE_ID
                    )
                    version_result = resolved.field_result(
                        MetadataField.VERSION
                    )
                    repository_result = resolved.field_result(
                        MetadataField.REPOSITORY_URL
                    )
                    source_result = resolved.field_result(
                        MetadataField.SOURCE_URL
                    )

                    package_id = (
                        package_result.value
                        if package_result.resolved
                        else candidate.package_id
                    )

                    existing_application = None
                    existing_lookup_confirmed = False

                    if package_id and existing_lookup_backend is not None:
                        lookup_response = existing_lookup_backend.get_by_package_id(
                            package_id
                        )

                        if lookup_response.status == BackendStatus.NOT_FOUND:
                            existing_lookup_confirmed = True
                            log_info(
                                "Existing-application lookup: package is not present "
                                "in Supabase."
                            )
                        elif (
                            lookup_response.status == BackendStatus.SUCCESS
                            and isinstance(lookup_response.data, dict)
                        ):
                            try:
                                existing_application = parse_existing_application(
                                    lookup_response.data,
                                    schema=publisher_schema,
                                )
                                existing_lookup_confirmed = True
                                log_info(
                                    "Existing-application lookup: matching package "
                                    "already exists in Supabase."
                                )
                            except Exception as existing_parse_exc:
                                warning = (
                                    "Existing application could not be parsed safely; "
                                    "candidate will not be treated as new: "
                                    f"{sanitize_exception(existing_parse_exc)}"
                                )
                                stats.warnings.append(warning)
                                log_warning(warning)
                        else:
                            warning = (
                                "Existing-application lookup failed; candidate will "
                                "not be treated as new. "
                                f"status={lookup_response.status.value}; "
                                f"http={lookup_response.status_code or 'n/a'}"
                            )
                            stats.warnings.append(warning)
                            log_warning(warning)

                    if package_id and not existing_lookup_confirmed:
                        stats.skipped += 1
                        stats.review_required += 1
                        log_warning(
                            "Candidate skipped because existing-application state "
                            "could not be confirmed safely."
                        )
                        continue

                    if package_id:
                        apk_report = run_live_apk_intelligence(
                            package_id=package_id,
                            repository_url=(
                                repository_result.value
                                if repository_result.resolved
                                else candidate.repository_url
                            ),
                            source_url=(
                                source_result.value
                                if source_result.resolved
                                else candidate.source_url
                            ),
                            version_hint=(
                                version_result.value
                                if version_result.resolved
                                else None
                            ),
                        )

                        remember_apk(
                            engine_memory,
                            memory_key,
                            apk_report,
                            summary={
                                "status": apk_report.status.value,
                                "artifacts_seen": apk_report.artifacts_seen,
                                "accepted": apk_report.artifacts_accepted,
                                "rejected": apk_report.artifacts_rejected,
                            },
                        )

                        log_info(
                            "APK Intelligence status: "
                            f"{apk_report.status.value}; "
                            f"artifacts seen: {apk_report.artifacts_seen}; "
                            f"accepted: {apk_report.artifacts_accepted}; "
                            f"rejected: {apk_report.artifacts_rejected}."
                        )

                        if apk_report.selected is not None:
                            log_info(
                                "Selected APK: "
                                f"{safe_text(apk_report.selected.url, max_length=300)}"
                            )
                            if apk_report.selected.version:
                                log_info(
                                    "Selected APK version: "
                                    f"{safe_text(apk_report.selected.version, max_length=120)}"
                                )
                            log_info(
                                "Candidate completed the live read-only "
                                "APK Intelligence path."
                            )

                            # ----------------------------------------
                            # Phase 5: live read-only Content Intelligence.
                            # Generate bounded explanatory content only
                            # after Resolver + APK Intelligence succeeded.
                            # No publishing or external write occurs here.
                            # ----------------------------------------
                            content_phase = stats.phases.get(PHASE_CONTENT)

                            if content_phase is None:
                                content_phase = begin_phase(
                                    stats,
                                    PHASE_CONTENT,
                                )

                            if (
                                CANCELLATION.requested
                                or not deadline.can_start_new_work()
                            ):
                                if CANCELLATION.requested:
                                    stats.cancelled = True
                                    reason = (
                                        "Cancellation requested before "
                                        "Content Intelligence."
                                    )
                                else:
                                    stats.stopped_by_deadline = True
                                    reason = (
                                        "Runtime deadline too close to run "
                                        "Content Intelligence."
                                    )

                                stats.skipped += 1
                                log_warning(reason)
                            else:
                                try:
                                    short_result = resolved.field_result(
                                        MetadataField.SHORT_DESCRIPTION
                                    )
                                    full_result = resolved.field_result(
                                        MetadataField.FULL_DESCRIPTION
                                    )

                                    name_result = resolved.field_result(
                                        MetadataField.NAME
                                    )
                                    resolved_name = (
                                        name_result.value
                                        if name_result.resolved and name_result.value
                                        else candidate.name
                                    )

                                    if app_name_requires_review(resolved_name):
                                        stats.skipped += 1
                                        stats.review_required += 1

                                        name_warning = (
                                            "Candidate requires review because the "
                                            "resolved application name is not suitable "
                                            "for automatic publication: "
                                            f"{safe_text(resolved_name, max_length=120)!r}."
                                        )

                                        stats.warnings.append(name_warning)
                                        log_warning(name_warning)

                                        engine_memory.mark_review(
                                            memory_key,
                                            name_warning,
                                            metadata={
                                                "stage": "name-quality",
                                                "resolved_name": safe_text(
                                                    resolved_name,
                                                    max_length=120,
                                                ),
                                            },
                                        )

                                        save_memory_safely()
                                        stats.current_candidate = None
                                        continue

                                    content_report = (
                                        run_live_content_intelligence(
                                            app_name=resolved_name,
                                            source_type=candidate.source_enum,
                                            source_url=(
                                                source_result.value
                                                if source_result.resolved
                                                else candidate.source_url
                                            ),
                                            short_description=(
                                                short_result.value
                                                if short_result.resolved
                                                else candidate.description
                                            ),
                                            full_description=(
                                                full_result.value
                                                if full_result.resolved
                                                else None
                                            ),
                                            confidence=(
                                                candidate.source_confidence
                                            ),
                                        )
                                    )

                                    remember_content(
                                        engine_memory,
                                        memory_key,
                                        content_report,
                                        summary={
                                            "status": content_report.status.value,
                                            "evidence_count": content_report.evidence_count,
                                            "populated_fields": content_report.populated_fields,
                                        },
                                    )

                                    stats.content_candidates_processed += 1

                                    log_info(
                                        "Content Intelligence status: "
                                        f"{content_report.status.value}; "
                                        "evidence: "
                                        f"{content_report.evidence_count}; "
                                        "populated fields: "
                                        f"{content_report.populated_fields}."
                                    )

                                    if content_report.status == ContentStatus.COMPLETE:
                                        stats.content_candidates_completed += 1
                                        log_info(
                                            "Candidate completed the live "
                                            "read-only Content Intelligence path."
                                        )

                                        # ------------------------------------
                                        # Phase 6: read-only Decision Engine.
                                        # This phase only recommends an action.
                                        # Publisher remains disconnected and
                                        # no external write is performed here.
                                        # ------------------------------------
                                        decision_phase = stats.phases.get(
                                            PHASE_DECISION
                                        )

                                        if decision_phase is None:
                                            decision_phase = begin_phase(
                                                stats,
                                                PHASE_DECISION,
                                            )

                                        if (
                                            CANCELLATION.requested
                                            or not deadline.can_start_new_work()
                                        ):
                                            if CANCELLATION.requested:
                                                stats.cancelled = True
                                                reason = (
                                                    "Cancellation requested before "
                                                    "Decision Engine."
                                                )
                                            else:
                                                stats.stopped_by_deadline = True
                                                reason = (
                                                    "Runtime deadline too close to "
                                                    "run Decision Engine."
                                                )

                                            stats.skipped += 1
                                            log_warning(reason)
                                        else:
                                            try:
                                                decision_input = DecisionInput(
                                                    candidate=candidate,
                                                    resolution=resolved,
                                                    apk=apk_report,
                                                    content=content_report,
                                                    # Supabase is consulted read-only
                                                    # before this point. Existing rows are
                                                    # passed to the Decision Engine so a
                                                    # duplicate can never be classified as
                                                    # a new application merely because the
                                                    # current run has no local memory.
                                                    existing=existing_application,
                                                )

                                                decision_result = decide(
                                                    decision_input
                                                )

                                                action_value = (
                                                    decision_result.action.value
                                                )

                                                remember_decision(
                                                    engine_memory,
                                                    memory_key,
                                                    decision_result,
                                                    action=action_value,
                                                    summary={
                                                        "kind": decision_result.kind.value,
                                                        "confidence": round(
                                                            decision_result.confidence,
                                                            4,
                                                        ),
                                                        "review": decision_result.requires_review,
                                                        "blocked": decision_result.blocked,
                                                    },
                                                )

                                                stats.decision_candidates_processed += 1

                                                if decision_result.blocked:
                                                    stats.decision_blocked += 1
                                                elif action_value == "insert":
                                                    stats.decision_insert_recommended += 1
                                                elif action_value == "update":
                                                    stats.decision_update_recommended += 1
                                                elif action_value == "repair":
                                                    stats.decision_repair_recommended += 1
                                                elif action_value == "skip":
                                                    stats.decision_skip_recommended += 1
                                                elif action_value == "review":
                                                    stats.decision_review_recommended += 1

                                                if decision_result.requires_review:
                                                    stats.review_required += 1

                                                log_info(
                                                    "Decision Engine result: "
                                                    f"action={action_value}; "
                                                    f"kind={decision_result.kind.value}; "
                                                    f"confidence={decision_result.confidence:.3f}; "
                                                    f"review={decision_result.requires_review}; "
                                                    f"blocked={decision_result.blocked}."
                                                )

                                                for decision_reason in (
                                                    decision_result.reasons
                                                ):
                                                    log_info(
                                                        "Decision reason: "
                                                        f"{decision_reason.code.value} — "
                                                        f"{safe_text(decision_reason.message, max_length=260)}"
                                                    )

                                                if decision_result.blocked:
                                                    engine_memory.mark_blocked(
                                                        memory_key,
                                                        decision_result.reason_text,
                                                    )
                                                elif decision_result.requires_review:
                                                    engine_memory.mark_review(
                                                        memory_key,
                                                        decision_result.reason_text,
                                                        metadata={
                                                            "action": action_value,
                                                        },
                                                    )
                                                elif action_value == "skip":
                                                    engine_memory.mark_success(
                                                        memory_key,
                                                        status=MemoryStatus.SKIPPED,
                                                        action=action_value,
                                                        metadata={
                                                            "reason": decision_result.reason_text,
                                                        },
                                                    )

                                                log_info(
                                                    "Candidate completed the "
                                                    "read-only Decision Engine path."
                                                )

                                                # ------------------------------------
                                                # AI Review Bridge: non-destructive gate.
                                                # It can only tighten an automatic core
                                                # decision before Publisher; it never
                                                # mutates DecisionResult or publishes.
                                                # ------------------------------------
                                                ai_review_result = review_decision(
                                                    candidate=candidate,
                                                    decision_result=decision_result,
                                                )

                                                log_info(
                                                    "AI Review Bridge result: "
                                                    + ai_review_log_summary(
                                                        ai_review_result
                                                    )
                                                )

                                                if ai_review_result.blocks_automatic_publish:
                                                    stats.review_required += 1
                                                    stats.skipped += 1

                                                    ai_review_reason = (
                                                        "AI Review Bridge held candidate "
                                                        "for manual review: "
                                                        + safe_text(
                                                            ai_review_result.reason,
                                                            max_length=300,
                                                        )
                                                    )

                                                    log_warning(ai_review_reason)

                                                    engine_memory.mark_review(
                                                        memory_key,
                                                        ai_review_reason,
                                                        metadata={
                                                            "stage": "ai-review",
                                                            "action": action_value,
                                                            "ai_decision": (
                                                                ai_review_result.decision.value
                                                            ),
                                                        },
                                                    )

                                                    save_memory_safely()
                                                    stats.current_candidate = None
                                                    continue

                                                # ------------------------------------
                                                # Phase 7: Publisher diagnostic dry-run.
                                                # The Decision Engine recommendation is
                                                # validated by the real Publisher safety
                                                # layer, but the diagnostic backend makes
                                                # no network request and no external write.
                                                # ------------------------------------
                                                publish_phase = stats.phases.get(
                                                    PHASE_PUBLISH
                                                )

                                                if publish_phase is None:
                                                    publish_phase = begin_phase(
                                                        stats,
                                                        PHASE_PUBLISH,
                                                    )

                                                if (
                                                    CANCELLATION.requested
                                                    or not deadline.can_start_new_work()
                                                ):
                                                    if CANCELLATION.requested:
                                                        stats.cancelled = True
                                                        publish_reason = (
                                                            "Cancellation requested before "
                                                            "Publisher dry-run."
                                                        )
                                                    else:
                                                        stats.stopped_by_deadline = True
                                                        publish_reason = (
                                                            "Runtime deadline too close to "
                                                            "run Publisher dry-run."
                                                        )

                                                    stats.publisher_skipped += 1
                                                    log_warning(publish_reason)
                                                else:
                                                    try:
                                                        def resolved_value(
                                                            field: MetadataField,
                                                        ) -> object | None:
                                                            result = resolved.field_result(field)
                                                            return (
                                                                result.value
                                                                if result.resolved
                                                                else None
                                                            )

                                                        publication_action = PublicationAction(
                                                            action_value
                                                        )

                                                        publication_request = PublicationRequest(
                                                            action=publication_action,
                                                            payload=ApplicationPayload(
                                                                name=resolved_name,
                                                                package_id=package_id,
                                                                version=(
                                                                    apk_report.selected.version
                                                                    or resolved_value(
                                                                        MetadataField.VERSION
                                                                    )
                                                                ),
                                                                apk_url=apk_report.selected.url,
                                                                source_url=resolved_value(
                                                                    MetadataField.SOURCE_URL
                                                                )
                                                                or candidate.source_url,
                                                                repository_url=resolved_value(
                                                                    MetadataField.REPOSITORY_URL
                                                                )
                                                                or candidate.repository_url,
                                                                license=resolved_value(
                                                                    MetadataField.LICENSE
                                                                ),
                                                                category=resolved_value(
                                                                    MetadataField.CATEGORY
                                                                ),
                                                                short_description=getattr(
                                                                    getattr(
                                                                        content_report,
                                                                        "short_description",
                                                                        None,
                                                                    ),
                                                                    "value",
                                                                    None,
                                                                )
                                                                or resolved_value(
                                                                    MetadataField.SHORT_DESCRIPTION
                                                                ),
                                                                full_description=getattr(
                                                                    getattr(
                                                                        content_report,
                                                                        "full_description",
                                                                        None,
                                                                    ),
                                                                    "value",
                                                                    None,
                                                                )
                                                                or resolved_value(
                                                                    MetadataField.FULL_DESCRIPTION
                                                                ),
                                                                icon_url=resolved_value(
                                                                    MetadataField.ICON_URL
                                                                ),
                                                                source=str(
                                                                    candidate.source_type
                                                                ),
                                                            ),
                                                            decision_confidence=(
                                                                decision_result.confidence
                                                            ),
                                                            decision_reason="; ".join(
                                                                safe_text(
                                                                    reason.message,
                                                                    max_length=300,
                                                                )
                                                                for reason in decision_result.reasons
                                                            ),
                                                            run_id=run_id,
                                                            candidate_identity=(
                                                                package_id or candidate.name
                                                            ),
                                                        )

                                                        publication_outcome = execute_publication(
                                                            publication_request,
                                                            publisher_backend,
                                                            policy=publisher_policy,
                                                            counters=publisher_counters,
                                                        )

                                                        remember_publication(
                                                            engine_memory,
                                                            memory_key,
                                                            publication_outcome,
                                                            summary={
                                                                "status": publication_outcome.status.value,
                                                                "action": publication_action.value,
                                                                "external_write": (
                                                                    publisher_external_writes_enabled
                                                                    and publication_outcome.status
                                                                    in {
                                                                        PublicationStatus.PUBLISHED,
                                                                        PublicationStatus.UPDATED,
                                                                        PublicationStatus.REPAIRED,
                                                                    }
                                                                ),
                                                            },
                                                        )

                                                        if (
                                                            publication_outcome.status
                                                            == PublicationStatus.PUBLISHED
                                                        ):
                                                            stats.published += 1
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.UPDATED
                                                        ):
                                                            stats.updated += 1
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.REPAIRED
                                                        ):
                                                            stats.repaired += 1
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.DRY_RUN
                                                        ):
                                                            stats.publisher_dry_run += 1
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.BLOCKED
                                                        ):
                                                            stats.publisher_blocked += 1
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.REVIEW
                                                        ):
                                                            stats.publisher_review += 1
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.SKIPPED
                                                        ):
                                                            stats.publisher_skipped += 1
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.FAILED
                                                        ):
                                                            stats.publisher_failed += 1
                                                            stats.failures += 1

                                                        external_write_happened = (
                                                            publication_outcome.status
                                                            in {
                                                                PublicationStatus.PUBLISHED,
                                                                PublicationStatus.UPDATED,
                                                                PublicationStatus.REPAIRED,
                                                            }
                                                        )

                                                        log_info(
                                                            "Publisher result: "
                                                            f"status={publication_outcome.status.value}; "
                                                            f"action={publication_action.value}; "
                                                            f"backend={publisher_backend_name}; "
                                                            "external_write="
                                                            f"{'yes' if external_write_happened else 'no'}."
                                                        )

                                                        if publication_outcome.error:
                                                            log_warning(
                                                                "Publisher outcome: "
                                                                + safe_text(
                                                                    publication_outcome.error,
                                                                    max_length=300,
                                                                )
                                                            )

                                                    except Exception as publisher_exc:
                                                        stats.publisher_failed += 1
                                                        stats.failures += 1

                                                        publisher_error = (
                                                            "Publisher failed for "
                                                            "candidate "
                                                            f"{safe_text(candidate.name, max_length=120)!r}: "
                                                            f"{sanitize_exception(publisher_exc)}"
                                                        )

                                                        stats.warnings.append(
                                                            publisher_error
                                                        )
                                                        log_warning(publisher_error)

                                            except Exception as decision_exc:
                                                stats.decision_candidates_processed += 1
                                                stats.decision_failed += 1
                                                stats.failures += 1
                                                stats.skipped += 1

                                                decision_error = (
                                                    "Decision Engine failed for "
                                                    "candidate "
                                                    f"{safe_text(candidate.name, max_length=120)!r}: "
                                                    f"{sanitize_exception(decision_exc)}"
                                                )

                                                stats.warnings.append(
                                                    decision_error
                                                )
                                                log_warning(decision_error)

                                    elif content_report.status == ContentStatus.REVIEW:
                                        stats.content_candidates_review_required += 1
                                        stats.review_required += 1
                                        log_warning(
                                            "Content Intelligence requires "
                                            "manual review for this candidate."
                                        )
                                    elif content_report.status == ContentStatus.FAILED:
                                        stats.content_candidates_failed += 1
                                        stats.failures += 1
                                        stats.skipped += 1
                                        log_warning(
                                            "Content Intelligence failed for "
                                            "this candidate; candidate remains "
                                            "skipped."
                                        )
                                    else:
                                        stats.skipped += 1
                                        log_warning(
                                            "Content Intelligence returned a "
                                            "non-complete result; candidate "
                                            "remains skipped."
                                        )

                                    for warning in content_report.warnings:
                                        bounded_warning = safe_text(
                                            warning,
                                            max_length=300,
                                        )
                                        stats.warnings.append(bounded_warning)
                                        log_warning(bounded_warning)

                                    for content_error in content_report.errors:
                                        bounded_error = safe_text(
                                            content_error,
                                            max_length=300,
                                        )
                                        stats.warnings.append(bounded_error)
                                        log_warning(bounded_error)

                                except Exception as content_exc:
                                    stats.content_candidates_processed += 1
                                    stats.content_candidates_failed += 1
                                    stats.failures += 1
                                    stats.skipped += 1

                                    content_error = (
                                        "Content Intelligence failed for "
                                        "candidate "
                                        f"{safe_text(candidate.name, max_length=120)!r}: "
                                        f"{sanitize_exception(content_exc)}"
                                    )

                                    stats.warnings.append(content_error)
                                    log_warning(content_error)
                        else:
                            stats.skipped += 1
                            log_warning(
                                "APK Intelligence did not select a trusted "
                                "APK artifact; candidate remains skipped."
                            )
                            engine_memory.mark_failure(
                                memory_key,
                                "APK Intelligence did not select a trusted artifact.",
                                retryable=True,
                                metadata={
                                    "stage": "apk",
                                    "status": apk_report.status.value,
                                },
                            )

                        for warning in apk_report.warnings:
                            bounded_warning = safe_text(
                                warning,
                                max_length=300,
                            )
                            stats.warnings.append(bounded_warning)
                            log_warning(bounded_warning)

                        for provider_error in apk_report.provider_errors:
                            bounded_error = safe_text(
                                provider_error,
                                max_length=300,
                            )
                            stats.warnings.append(bounded_error)
                            log_warning(bounded_error)
                    else:
                        stats.skipped += 1
                        log_warning(
                            "APK Intelligence skipped because no resolved "
                            "Package ID is available."
                        )
                else:
                    stats.skipped += 1
                    log_warning(
                        "Candidate was not sufficiently resolved and "
                        "remains skipped for later phases."
                    )

                for warning in resolved.warnings:
                    bounded_warning = safe_text(warning, max_length=300)
                    stats.warnings.append(bounded_warning)
                    log_warning(bounded_warning)

                for provider_error in resolved.provider_errors:
                    bounded_error = safe_text(provider_error, max_length=300)
                    stats.warnings.append(bounded_error)
                    log_warning(bounded_error)

            except Exception as resolver_exc:
                stats.failures += 1
                stats.skipped += 1

                resolver_error = (
                    "Resolver failed for candidate "
                    f"{safe_text(candidate.name, max_length=120)!r}: "
                    f"{sanitize_exception(resolver_exc)}"
                )

                stats.warnings.append(resolver_error)
                log_warning(resolver_error)

                try:
                    engine_memory.mark_failure(
                        memory_key,
                        resolver_error,
                        retryable=True,
                        metadata={
                            "stage": "candidate-pipeline",
                        },
                    )
                except Exception as memory_failure_exc:
                    log_warning(
                        "Memory Layer could not record candidate failure: "
                        f"{sanitize_exception(memory_failure_exc)}"
                    )

            save_memory_safely()
            stats.current_candidate = None

        content_phase = stats.phases.get(PHASE_CONTENT)
        if (
            content_phase is not None
            and content_phase.finished_at is None
        ):
            finish_phase_success(content_phase)

        decision_phase = stats.phases.get(PHASE_DECISION)
        if (
            decision_phase is not None
            and decision_phase.finished_at is None
        ):
            finish_phase_success(decision_phase)

        publish_phase = stats.phases.get(PHASE_PUBLISH)
        if (
            publish_phase is not None
            and publish_phase.finished_at is None
        ):
            finish_phase_success(publish_phase)

        save_memory_safely()

        finish_phase_success(
            phase,
        )

    except Exception as exc:
        error = sanitize_exception(exc)

        stats.failures += 1
        stats.errors.append(error)

        finish_phase_failure(
            phase,
            error,
        )

        raise


# ============================================================
# Future phase placeholders
# ============================================================

def run_future_phase_placeholders(
    *,
    stats: RunStats,
) -> None:
    """
    Register future phases in the report.

    They are explicitly marked skipped instead of silently omitted,
    which keeps the final report structurally stable as the engine
    grows.
    """

    future_phases = (
        PHASE_RESOLUTION,
        PHASE_VERIFICATION,
        PHASE_CONTENT,
        PHASE_DECISION,
        PHASE_PUBLISH,
    )

    for phase_name in future_phases:
        if phase_name in stats.phases:
            continue

        phase = PhaseStats(
            name=phase_name,
            started_at=datetime.now(timezone.utc),
        )

        stats.phases[phase_name] = phase

        finish_phase_skipped(
            phase,
            "Not connected in the current engine phase.",
        )


# ============================================================
# Final report helpers
# ============================================================

def _phase_report_payload(
    phase: PhaseStats,
) -> dict[str, object]:
    return {
        "name": phase.name,
        "succeeded": phase.succeeded,
        "skipped": phase.skipped,
        "error": phase.error,
        "duration_seconds": round(
            phase.duration_seconds,
            3,
        ),
    }


def build_report_payload(
    *,
    run_id: str,
    config: EngineConfig,
    stats: RunStats,
) -> dict[str, object]:
    stop_reason = "normal-completion"

    if stats.cancelled:
        stop_reason = "cancelled"
    elif stats.stopped_by_deadline:
        stop_reason = "runtime-limit"

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
        },
        "mode": config.run_mode,
        "stop_reason": stop_reason,
        "runtime_minutes": config.runtime_minutes,
        "max_apps": config.max_apps,
        "duration_seconds": round(
            stats.duration_seconds,
            3,
        ),
        "candidates": {
            "seen": stats.candidates_seen,
            "processed": stats.candidates_processed,
            "published": stats.published,
            "updated": stats.updated,
            "repaired": stats.repaired,
            "skipped": stats.skipped,
            "review_required": stats.review_required,
        },
        "content": {
            "processed": stats.content_candidates_processed,
            "completed": stats.content_candidates_completed,
            "review_required": (
                stats.content_candidates_review_required
            ),
            "failed": stats.content_candidates_failed,
        },
        "decision": {
            "processed": stats.decision_candidates_processed,
            "insert_recommended": stats.decision_insert_recommended,
            "update_recommended": stats.decision_update_recommended,
            "repair_recommended": stats.decision_repair_recommended,
            "skip_recommended": stats.decision_skip_recommended,
            "review_recommended": stats.decision_review_recommended,
            "blocked": stats.decision_blocked,
            "failed": stats.decision_failed,
        },
        "publisher": {
            "connected": PUBLISHER_CONNECTED,
            "mode": (
                "supabase-live"
                if config.publishing_enabled
                else "diagnostic-dry-run"
            ),
            "published": stats.published,
            "updated": stats.updated,
            "repaired": stats.repaired,
            "dry_run": stats.publisher_dry_run,
            "blocked": stats.publisher_blocked,
            "review": stats.publisher_review,
            "skipped": stats.publisher_skipped,
            "failed": stats.publisher_failed,
            "external_write": (
                stats.published + stats.updated + stats.repaired > 0
            ),
        },
        "discovery": {
            "sources_succeeded": (
                stats.discovery_sources_succeeded
            ),
            "sources_failed": (
                stats.discovery_sources_failed
            ),
            "duplicates_removed": (
                stats.discovery_duplicates_removed
            ),
            "invalid_candidates_removed": (
                stats.discovery_invalid_removed
            ),
        },
        "failures": stats.failures,
        "warnings": list(stats.warnings),
        "errors": list(stats.errors),
        "phases": {
            name: _phase_report_payload(phase)
            for name, phase in stats.phases.items()
        },
    }


def print_human_report(
    *,
    run_id: str,
    config: EngineConfig,
    stats: RunStats,
) -> None:
    log_header(
        "OSGUIDE ENGINE REPORT"
    )

    payload = build_report_payload(
        run_id=run_id,
        config=config,
        stats=stats,
    )

    print(f"Run ID: {run_id}")
    print(
        f"Engine: {ENGINE_NAME} v{ENGINE_VERSION}"
    )
    print(f"Mode: {config.run_mode}")
    print(
        f"Stop reason: {payload['stop_reason']}"
    )
    print()

    print("Discovery")
    print(
        "  Sources succeeded: "
        f"{stats.discovery_sources_succeeded}"
    )
    print(
        "  Sources failed: "
        f"{stats.discovery_sources_failed}"
    )
    print(
        "  Duplicates removed: "
        f"{stats.discovery_duplicates_removed}"
    )
    print(
        "  Invalid candidates removed: "
        f"{stats.discovery_invalid_removed}"
    )
    print()

    print("Candidates")
    print(
        f"  Seen: {stats.candidates_seen}"
    )
    print(
        f"  Processed: {stats.candidates_processed}"
    )
    print(
        f"  Published: {stats.published}"
    )
    print(
        f"  Updated: {stats.updated}"
    )
    print(
        f"  Repaired: {stats.repaired}"
    )
    print(
        f"  Skipped: {stats.skipped}"
    )
    print(
        "  Review required: "
        f"{stats.review_required}"
    )
    print()

    print("Content Intelligence")
    print(
        "  Processed: "
        f"{stats.content_candidates_processed}"
    )
    print(
        "  Completed: "
        f"{stats.content_candidates_completed}"
    )
    print(
        "  Review required: "
        f"{stats.content_candidates_review_required}"
    )
    print(
        "  Failed: "
        f"{stats.content_candidates_failed}"
    )
    print()

    print("Decision Engine")
    print(
        "  Processed: "
        f"{stats.decision_candidates_processed}"
    )
    print(
        "  Insert recommended: "
        f"{stats.decision_insert_recommended}"
    )
    print(
        "  Update recommended: "
        f"{stats.decision_update_recommended}"
    )
    print(
        "  Repair recommended: "
        f"{stats.decision_repair_recommended}"
    )
    print(
        "  Skip recommended: "
        f"{stats.decision_skip_recommended}"
    )
    print(
        "  Review recommended: "
        f"{stats.decision_review_recommended}"
    )
    print(
        "  Blocked: "
        f"{stats.decision_blocked}"
    )
    print(
        "  Failed: "
        f"{stats.decision_failed}"
    )
    print()

    print("Publisher")
    print("  Connected: yes")
    print(
        "  Mode: "
        + (
            "supabase live"
            if config.publishing_enabled
            else "diagnostic dry-run"
        )
    )
    print(
        "  Published: "
        f"{stats.published}"
    )
    print(
        "  Updated: "
        f"{stats.updated}"
    )
    print(
        "  Repaired: "
        f"{stats.repaired}"
    )
    print(
        "  Dry-run validated: "
        f"{stats.publisher_dry_run}"
    )
    print(
        "  Blocked: "
        f"{stats.publisher_blocked}"
    )
    print(
        "  Review: "
        f"{stats.publisher_review}"
    )
    print(
        "  Skipped: "
        f"{stats.publisher_skipped}"
    )
    print(
        "  Failed: "
        f"{stats.publisher_failed}"
    )
    external_writes = stats.published + stats.updated + stats.repaired
    print(
        "  External writes: "
        + ("yes" if external_writes > 0 else "no")
    )
    print()

    print(
        f"Failures: {stats.failures}"
    )

    print(
        "Duration: "
        f"{stats.duration_seconds:.2f} seconds"
    )

    if stats.warnings:
        print()
        print("Warnings")

        for warning in stats.warnings:
            print(
                f"  - {safe_text(warning, max_length=400)}"
            )

    if stats.errors:
        print()
        print("Errors")

        for error in stats.errors:
            print(
                f"  - {safe_text(error, max_length=400)}"
            )

    if config.dry_run:
        print()
        print(
            "Dry run confirmed: "
            "no external data was modified."
        )

    elif PUBLISHER_CONNECTED:
        print()
        if stats.published + stats.updated + stats.repaired > 0:
            print(
                "Live Publisher confirmed: controlled external writes "
                "were completed through Supabase."
            )
        else:
            print(
                "Live Publisher completed without a successful external mutation."
            )


def print_machine_report(
    *,
    run_id: str,
    config: EngineConfig,
    stats: RunStats,
) -> None:
    """
    Print a bounded JSON report.

    Later phases can persist this to an artifact or Supabase audit
    table. For now it remains visible in GitHub Actions logs.
    """

    payload = build_report_payload(
        run_id=run_id,
        config=config,
        stats=stats,
    )

    log_header(
        "OSGUIDE MACHINE REPORT"
    )

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )


# ============================================================
# Main execution
# ============================================================

def main() -> int:
    install_signal_handlers()

    run_id = create_run_id()

    stats = RunStats(
        started_at=datetime.now(timezone.utc),
    )

    log_header(
        f"{ENGINE_NAME} v{ENGINE_VERSION}"
    )

    log_info(
        f"Run ID: {run_id}"
    )

    try:
        config = load_config()

    except ValueError as exc:
        log_error(
            "Configuration rejected: "
            f"{sanitize_exception(exc)}"
        )

        return EXIT_CONFIGURATION_ERROR

    print()
    print(
        describe_config(config)
    )

    deadline = DeadlineController(
        runtime_seconds=config.runtime_seconds,
    )

    exit_code = EXIT_SUCCESS

    try:
        run_discovery_phase(
            config=config,
            stats=stats,
            deadline=deadline,
            run_id=run_id,
        )

        if CANCELLATION.requested:
            stats.cancelled = True
            exit_code = EXIT_CANCELLED

    except KeyboardInterrupt:
        stats.cancelled = True
        stats.failures += 1

        warning = (
            "Engine interrupted manually."
        )

        stats.warnings.append(warning)

        log_warning(warning)

        exit_code = EXIT_CANCELLED

    except Exception as exc:
        stats.failures += 1

        error = sanitize_exception(exc)

        stats.errors.append(error)

        log_error(
            "Unexpected controller failure: "
            f"{error}"
        )

        log_debug(
            traceback.format_exc()
        )

        exit_code = EXIT_RUNTIME_ERROR

    finally:
        stats.current_candidate = None

        run_future_phase_placeholders(
            stats=stats,
        )

        stats.finished_at = datetime.now(
            timezone.utc
        )

        try:
            print_human_report(
                run_id=run_id,
                config=config,
                stats=stats,
            )

            print_machine_report(
                run_id=run_id,
                config=config,
                stats=stats,
            )

        except Exception as report_exc:
            # Reporting must never hide the original engine result.
            log_error(
                "Final report generation failed: "
                f"{sanitize_exception(report_exc)}"
            )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
