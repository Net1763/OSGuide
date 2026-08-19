"""
OSGuide Engine
Main Controller

Phase 1:
- Load and validate GitHub Actions runtime configuration.
- Start the engine safely.
- Enforce the internal deadline.
- Run a harmless dry-run controller test.
- Produce a structured final report.

No Supabase writes, discovery requests, APK downloads,
or external API calls are performed in this phase.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from config import (
    ENGINE_NAME,
    ENGINE_VERSION,
    EngineConfig,
    describe_config,
    load_config,
)


# ============================================================
# Exit codes
# ============================================================

EXIT_SUCCESS: Final[int] = 0
EXIT_CONFIGURATION_ERROR: Final[int] = 2
EXIT_RUNTIME_ERROR: Final[int] = 3


# ============================================================
# Controller constants
# ============================================================

DEADLINE_SAFETY_SECONDS: Final[int] = 3

DRY_RUN_TEST_DELAY_SECONDS: Final[float] = 0.15


# ============================================================
# Run state
# ============================================================

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

    stopped_by_deadline: bool = False

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

def log_header(title: str) -> None:
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def log_info(message: str) -> None:
    print(f"[INFO] {message}")


def log_warning(message: str) -> None:
    print(f"[WARN] {message}")


def log_error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


# ============================================================
# Deadline controller
# ============================================================

class DeadlineController:
    def __init__(self, runtime_seconds: int) -> None:
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

    def can_start_new_work(self) -> bool:
        return (
            self.remaining_seconds
            > DEADLINE_SAFETY_SECONDS
        )

    def deadline_reached(self) -> bool:
        return self.remaining_seconds <= 0


# ============================================================
# Run identifier
# ============================================================

def create_run_id() -> str:
    now = datetime.now(timezone.utc)

    return (
        now.strftime("%Y%m%d-%H%M%S")
        + "-discover"
    )


# ============================================================
# Phase 1 dry-run controller test
# ============================================================

def run_controller_test(
    config: EngineConfig,
    stats: RunStats,
    deadline: DeadlineController,
) -> None:
    """
    Exercise the controller without touching external services.

    Each simulated candidate represents future engine work.
    """

    log_header("PHASE 1 — CONTROLLER TEST")

    if not config.dry_run:
        log_warning(
            "Publish mode was selected, but Phase 1 has "
            "no publisher connected."
        )
        log_warning(
            "The engine will remain non-destructive."
        )

    for candidate_number in range(
        1,
        config.max_apps + 1,
    ):
        if not deadline.can_start_new_work():
            stats.stopped_by_deadline = True

            log_warning(
                "Runtime deadline is approaching. "
                "No new candidate will be started."
            )

            break

        stats.candidates_seen += 1

        log_info(
            f"Candidate {candidate_number}: "
            "controller simulation started."
        )

        time.sleep(
            DRY_RUN_TEST_DELAY_SECONDS
        )

        stats.candidates_processed += 1
        stats.skipped += 1

        log_info(
            f"Candidate {candidate_number}: "
            "dry-run simulation completed."
        )

    if deadline.deadline_reached():
        stats.stopped_by_deadline = True


# ============================================================
# Final report
# ============================================================

def print_final_report(
    run_id: str,
    config: EngineConfig,
    stats: RunStats,
) -> None:
    log_header("OSGUIDE ENGINE REPORT")

    stop_reason = (
        "runtime limit"
        if stats.stopped_by_deadline
        else "normal completion"
    )

    print(f"Run ID: {run_id}")
    print(f"Engine: {ENGINE_NAME} v{ENGINE_VERSION}")
    print(f"Mode: {config.run_mode}")
    print(f"Stopped by: {stop_reason}")
    print()
    print(f"Candidates seen: {stats.candidates_seen}")
    print(
        "Candidates processed: "
        f"{stats.candidates_processed}"
    )
    print(f"Published: {stats.published}")
    print(f"Updated: {stats.updated}")
    print(f"Repaired: {stats.repaired}")
    print(f"Skipped: {stats.skipped}")
    print(
        "Review required: "
        f"{stats.review_required}"
    )
    print(f"Failures: {stats.failures}")
    print()
    print(
        "Duration: "
        f"{stats.duration_seconds:.2f} seconds"
    )

    if config.dry_run:
        print()
        print(
            "Dry run confirmed: "
            "no external data was modified."
        )


# ============================================================
# Main controller
# ============================================================

def main() -> int:
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
            f"Configuration rejected: {exc}"
        )

        return EXIT_CONFIGURATION_ERROR

    print()
    print(describe_config(config))

    deadline = DeadlineController(
        runtime_seconds=config.runtime_seconds,
    )

    try:
        run_controller_test(
            config=config,
            stats=stats,
            deadline=deadline,
        )

    except KeyboardInterrupt:
        stats.failures += 1

        log_warning(
            "Engine interrupted manually."
        )

        stats.finished_at = datetime.now(
            timezone.utc
        )

        print_final_report(
            run_id=run_id,
            config=config,
            stats=stats,
        )

        return EXIT_RUNTIME_ERROR

    except Exception as exc:
        stats.failures += 1

        log_error(
            "Unexpected controller failure: "
            f"{type(exc).__name__}: {exc}"
        )

        stats.finished_at = datetime.now(
            timezone.utc
        )

        print_final_report(
            run_id=run_id,
            config=config,
            stats=stats,
        )

        return EXIT_RUNTIME_ERROR

    stats.finished_at = datetime.now(
        timezone.utc
    )

    print_final_report(
        run_id=run_id,
        config=config,
        stats=stats,
    )

    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
