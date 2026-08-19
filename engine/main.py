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
    run_discovery_diagnostic,
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
    config: EngineConfig,
    stats: RunStats,
    deadline: DeadlineController,
) -> None:
    """
    Execute the current safe discovery phase.

    This phase intentionally uses the diagnostic discovery source.
    Real F-Droid/GitHub/other trusted source providers will be
    connected in later files without replacing this controller.
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

        if config.publishing_enabled:
            if not PUBLISHER_CONNECTED:
                warning = (
                    "Publish mode was selected, but the Publisher "
                    "layer is not connected in this phase. "
                    "The run remains non-destructive."
                )

                stats.warnings.append(warning)

                log_warning(warning)

        log_info(
            "Starting safe discovery diagnostic."
        )

        report = run_discovery_diagnostic(
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
            # IMPORTANT:
            # This is where the future Super Resolver will run.
            # The candidate is currently only passed through
            # the diagnostic pipeline and deliberately skipped.
            # ------------------------------------------------

            stats.candidates_processed += 1
            stats.skipped += 1

            log_info(
                "Candidate completed the Phase 2 diagnostic path."
            )

            stats.current_candidate = None

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

    elif not PUBLISHER_CONNECTED:
        print()
        print(
            "Safety lock confirmed: "
            "Publisher is not connected, therefore "
            "no external data was modified."
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
