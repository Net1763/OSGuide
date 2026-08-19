"""
OSGuide Engine
Configuration Layer

This module contains the safe runtime configuration used by the
OSGuide automation engine.

No secrets, API keys, Supabase credentials, or tokens belong here.
Secrets will be supplied later through GitHub Actions Secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final


# ============================================================
# Engine identity
# ============================================================

ENGINE_NAME: Final[str] = "OSGuide Engine"
ENGINE_VERSION: Final[str] = "0.1.0"
ENGINE_COMPONENT: Final[str] = "Discovery"


# ============================================================
# Safe limits
# ============================================================

DEFAULT_RUNTIME_MINUTES: Final[int] = 5
MIN_RUNTIME_MINUTES: Final[int] = 1
MAX_RUNTIME_MINUTES: Final[int] = 15

DEFAULT_MAX_APPS: Final[int] = 5
MIN_MAX_APPS: Final[int] = 1
MAX_MAX_APPS: Final[int] = 20

ALLOWED_RUN_MODES: Final[tuple[str, ...]] = (
    "dry-run",
    "publish",
)


# ============================================================
# Runtime configuration object
# ============================================================

@dataclass(frozen=True, slots=True)
class EngineConfig:
    run_mode: str
    runtime_minutes: int
    max_apps: int

    @property
    def dry_run(self) -> bool:
        return self.run_mode == "dry-run"

    @property
    def publishing_enabled(self) -> bool:
        return self.run_mode == "publish"

    @property
    def runtime_seconds(self) -> int:
        return self.runtime_minutes * 60


# ============================================================
# Internal helpers
# ============================================================

def _read_integer(
    variable_name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(variable_name, "").strip()

    if not raw_value:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"{variable_name} must contain a valid integer."
        ) from exc

    if value < minimum or value > maximum:
        raise ValueError(
            f"{variable_name} must be between "
            f"{minimum} and {maximum}. Received: {value}"
        )

    return value


def _read_run_mode() -> str:
    run_mode = os.getenv(
        "OSGUIDE_RUN_MODE",
        "dry-run",
    ).strip().lower()

    if run_mode not in ALLOWED_RUN_MODES:
        allowed = ", ".join(ALLOWED_RUN_MODES)

        raise ValueError(
            f"Invalid OSGUIDE_RUN_MODE: {run_mode!r}. "
            f"Allowed values: {allowed}"
        )

    return run_mode


# ============================================================
# Public configuration loader
# ============================================================

def load_config() -> EngineConfig:
    """
    Read and validate configuration supplied by GitHub Actions.

    Invalid values fail safely instead of silently changing
    the behaviour of the engine.
    """

    run_mode = _read_run_mode()

    runtime_minutes = _read_integer(
        variable_name="OSGUIDE_RUNTIME_MINUTES",
        default=DEFAULT_RUNTIME_MINUTES,
        minimum=MIN_RUNTIME_MINUTES,
        maximum=MAX_RUNTIME_MINUTES,
    )

    max_apps = _read_integer(
        variable_name="OSGUIDE_MAX_APPS",
        default=DEFAULT_MAX_APPS,
        minimum=MIN_MAX_APPS,
        maximum=MAX_MAX_APPS,
    )

    return EngineConfig(
        run_mode=run_mode,
        runtime_minutes=runtime_minutes,
        max_apps=max_apps,
    )


# ============================================================
# Safe diagnostic output
# ============================================================

def describe_config(config: EngineConfig) -> str:
    """
    Produce a safe configuration summary.

    This function deliberately contains no secret values.
    """

    return (
        f"{ENGINE_NAME} v{ENGINE_VERSION}\n"
        f"Component: {ENGINE_COMPONENT}\n"
        f"Mode: {config.run_mode}\n"
        f"Runtime limit: {config.runtime_minutes} minute(s)\n"
        f"Maximum applications: {config.max_apps}\n"
        f"Publishing enabled: "
        f"{'yes' if config.publishing_enabled else 'no'}"
    )
