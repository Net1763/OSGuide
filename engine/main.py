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

from publisher import (
    ApplicationPayload,
    DiagnosticPublisherBackend,
    PublicationAction,
    PublicationRequest,
    PublicationStatus,
    PublisherCounters,
    PublisherPolicy,
    WriteMode,
    create_live_backend,
    execute_publication,
    live_policy_from_environment,
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

# This protects against accidentally enabling destructive behavior
# before the Publisher layer is intentionally connected.
PUBLISHER_CONNECTED: Final[bool] = False

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

    publisher_connected: bool = False
    publisher_mode: str = "diagnostic-dry-run"
    publisher_external_write: bool = False

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
    run_id: str,
    config: EngineConfig,
    stats: RunStats,
    deadline: DeadlineController,
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

        # Publisher runtime connection.
        #
        # Supabase can be connected for read-only dry-run operation without
        # granting writes. Live writes require BOTH:
        #   1) the engine run to be in publish mode, and
        #   2) OSGUIDE_PUBLISH_ENABLED to be explicitly enabled.
        #
        # The Publisher module still enforces Admin priority, tombstones,
        # manual-field protection, snapshots, bounded writes and no deletes.
        publisher_backend_name = "diagnostic"
        publisher_backend = DiagnosticPublisherBackend()
        publisher_counters = PublisherCounters()
        publisher_policy = PublisherPolicy(
            enabled=False,
            write_mode=WriteMode.DRY_RUN,
        )

        if (
            os.getenv("OSGUIDE_SUPABASE_URL", "").strip()
            and os.getenv("OSGUIDE_ENGINE_KEY", "").strip()
        ):
            try:
                publisher_backend = create_live_backend()
                stats.publisher_connected = True

                if config.publishing_enabled:
                    publisher_policy = live_policy_from_environment()
                else:
                    publisher_policy = PublisherPolicy(
                        enabled=False,
                        write_mode=WriteMode.DRY_RUN,
                    )

                if (
                    publisher_policy.enabled
                    and publisher_policy.write_mode == WriteMode.LIVE
                ):
                    publisher_backend_name = "supabase-live"
                    stats.publisher_mode = "supabase-live"
                    log_warning(
                        "Publisher backend: Supabase LIVE mode enabled. "
                        "Writes remain subject to Publisher safety policy."
                    )
                else:
                    publisher_backend_name = "supabase-readonly"
                    stats.publisher_mode = "supabase-readonly-dry-run"
                    log_info(
                        "Publisher backend: Supabase read-only dry-run "
                        "(external writes remain disabled)."
                    )
            except Exception as publisher_backend_exc:
                warning = (
                    "Supabase Publisher backend could not be initialized; "
                    "diagnostic dry-run backend will be used instead: "
                    f"{sanitize_exception(publisher_backend_exc)}"
                )
                stats.warnings.append(warning)
                log_warning(warning)
                publisher_backend = DiagnosticPublisherBackend()
                publisher_policy = PublisherPolicy(
                    enabled=False,
                    write_mode=WriteMode.DRY_RUN,
                )
                publisher_backend_name = "diagnostic"
                stats.publisher_connected = False
                stats.publisher_mode = "diagnostic-dry-run"
        else:
            log_warning(
                "Supabase Publisher credentials are not available; "
                "using diagnostic dry-run backend."
            )

        for candidate in report.candidates:
            if CANCELLATION.requested:
                stats.cancelled = True

                log_warning(
                    "Cancellation requested. "
                    "No new candidate will be processed."
                )

                break

            if not deadline.can_start_new_work():
                stats.stopped_by_deadline = True

                log_warning(
                    "Runtime deadline is approaching. "
                    "No new candidate will be processed."
                )

                break

            stats.current_candidate = candidate.name
            stats.candidates_seen += 1

            log_candidate(candidate)

            # ------------------------------------------------
            # Phase 3: live read-only Resolver.
            # No publishing or external writes occur here.
            # ------------------------------------------------

            stats.candidates_processed += 1

            try:
                resolved = run_live_resolver(candidate)

                log_info(
                    "Resolver status: "
                    f"{resolved.status.value}; "
                    f"resolved fields: {resolved.resolved_field_count}; "
                    f"conflicts: {resolved.conflict_count}."
                )

                for metadata_field in (
                    MetadataField.PACKAGE_ID,
                    MetadataField.VERSION,
                    MetadataField.APK_URL,
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

                                    content_report = (
                                        run_live_content_intelligence(
                                            app_name=candidate.name,
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
                                                    # Existing-backend lookup is
                                                    # intentionally not connected
                                                    # yet.  The Decision Engine is
                                                    # read-only in this phase.
                                                    existing=None,
                                                )

                                                decision_result = decide(
                                                    decision_input
                                                )

                                                stats.decision_candidates_processed += 1

                                                action_value = (
                                                    decision_result.action.value
                                                )

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

                                                log_info(
                                                    "Candidate completed the "
                                                    "read-only Decision Engine path."
                                                )

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
                                                                name=candidate.name,
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
                                                                    content_report,
                                                                    "short_description",
                                                                    None,
                                                                )
                                                                or resolved_value(
                                                                    MetadataField.SHORT_DESCRIPTION
                                                                ),
                                                                full_description=getattr(
                                                                    content_report,
                                                                    "full_description",
                                                                    None,
                                                                )
                                                                or resolved_value(
                                                                    MetadataField.FULL_DESCRIPTION
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

                                                        if (
                                                            publication_outcome.status
                                                            == PublicationStatus.DRY_RUN
                                                        ):
                                                            stats.publisher_dry_run += 1
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.PUBLISHED
                                                        ):
                                                            stats.published += 1
                                                            stats.publisher_external_write = True
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.UPDATED
                                                        ):
                                                            stats.updated += 1
                                                            stats.publisher_external_write = True
                                                        elif (
                                                            publication_outcome.status
                                                            == PublicationStatus.REPAIRED
                                                        ):
                                                            stats.repaired += 1
                                                            stats.publisher_external_write = True
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

                                                        external_write = (
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
                                                            f"external_write={'yes' if external_write else 'no'}."
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
                                                            "Publisher dry-run failed for "
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
            "connected": stats.publisher_connected,
            "mode": stats.publisher_mode,
            "dry_run": stats.publisher_dry_run,
            "blocked": stats.publisher_blocked,
            "review": stats.publisher_review,
            "skipped": stats.publisher_skipped,
            "failed": stats.publisher_failed,
            "external_write": stats.publisher_external_write,
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
    print(
        "  Connected: "
        + ("yes" if stats.publisher_connected else "no")
    )
    print(
        "  Mode: "
        + stats.publisher_mode
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
    print(
        "  External writes: "
        + ("yes" if stats.publisher_external_write else "no")
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

    elif not stats.publisher_external_write:
        print()
        print(
            "Publisher run completed without an external mutation."
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
            run_id=run_id,
            config=config,
            stats=stats,
            deadline=deadline,
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
