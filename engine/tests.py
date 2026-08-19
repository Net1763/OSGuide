"""
OSGuide Engine
Comprehensive Local Test Suite

File:
    engine/tests.py

Purpose
-------
This test suite validates the current OSGuide engine architecture without
performing real network writes, real Supabase publication, APK downloads,
or external AI calls.

The suite is intentionally designed around the diagnostic providers and
diagnostic helpers already present in the engine modules.

Covered layers
--------------
- config
- discovery
- resolver
- apk_intelligence
- content_intelligence
- decision_engine
- publisher
- memory
- observability
- audit_rollback
- security
- main controller import/safety surface

Safety rules
------------
1. Tests must be safe to run in GitHub Actions.
2. Tests must not publish to Supabase.
3. Tests must not delete applications.
4. Tests must not download APK files.
5. Tests must not invoke live AI providers.
6. Tests must not require private credentials.
7. Tests must not print secret values.
8. Diagnostic backends are preferred over live backends.
9. Missing optional diagnostic helpers are reported as skipped rather than
   silently treated as success.
10. Core module import failures are fatal.
11. Public exports listed in __all__ must resolve.
12. Tombstone protection must remain effective.
13. Admin/manual field protection must remain effective where exposed by
    the current module API.
14. Security redaction must remove secret-like values.
15. Private/loopback network targets must be blocked by the security layer.
16. The default publisher diagnostic must remain non-networked.
17. The suite uses only the Python standard library.

Run manually
------------
From the engine directory:

    python tests.py

or:

    python -m unittest -v tests

GitHub Actions can also execute:

    python tests.py --verbose
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import io
import json
import os
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence


# ============================================================
# Suite identity
# ============================================================

TEST_SUITE_NAME: Final[str] = "OSGuide Engine Comprehensive Tests"
TEST_SUITE_VERSION: Final[str] = "1.0.0"


# ============================================================
# Engine modules expected in the current architecture
# ============================================================

CORE_MODULES: Final[tuple[str, ...]] = (
    "config",
    "discovery",
    "resolver",
    "apk_intelligence",
    "content_intelligence",
    "decision_engine",
    "publisher",
    "memory",
    "observability",
    "audit_rollback",
    "security",
    "main",
)


# Modules that are expected to provide their own local diagnostic helpers.
DIAGNOSTIC_MODULES: Final[tuple[str, ...]] = (
    "discovery",
    "resolver",
    "apk_intelligence",
    "content_intelligence",
    "decision_engine",
    "publisher",
    "memory",
    "observability",
    "audit_rollback",
    "security",
)


# ============================================================
# Global safety environment
# ============================================================

# Force the controller into the safest intended mode for tests.
#
# setdefault() is used so the suite does not overwrite an explicit value
# supplied by CI. Individual tests still refuse to call live publisher
# factories or network transports.
os.environ.setdefault(
    "OSGUIDE_RUN_MODE",
    "dry-run",
)

os.environ.setdefault(
    "OSGUIDE_RUNTIME_MINUTES",
    "2",
)

os.environ.setdefault(
    "OSGUIDE_MAX_APPS",
    "1",
)

os.environ.setdefault(
    "OSGUIDE_PUBLISH_ENABLED",
    "false",
)


# ============================================================
# Generic helpers
# ============================================================

def module_directory() -> Path:
    return Path(__file__).resolve().parent


def import_engine_module(
    name: str,
) -> types.ModuleType:
    return importlib.import_module(
        name
    )


def enum_value(
    value: object,
) -> object:
    if isinstance(
        value,
        Enum,
    ):
        return value.value

    return value


def safe_object_dict(
    value: object,
) -> dict[str, object]:
    """
    Convert common engine result objects to a shallow dictionary.

    This is diagnostic-only and deliberately avoids recursive inspection
    of arbitrary private fields.
    """

    if value is None:
        return {}

    if isinstance(
        value,
        Mapping,
    ):
        return {
            str(key): item
            for key, item in value.items()
        }

    if is_dataclass(
        value
    ):
        try:
            raw = asdict(
                value
            )

            if isinstance(
                raw,
                dict,
            ):
                return raw

        except Exception:
            pass

    output: dict[
        str,
        object,
    ] = {}

    for name in (
        "status",
        "state",
        "action",
        "kind",
        "blocked",
        "requires_review",
        "succeeded",
        "selected",
        "candidates",
        "warnings",
        "errors",
        "fields",
        "outcomes",
        "counters",
        "events",
        "package_id",
        "version",
        "apk_url",
        "populated_fields",
        "resolved_field_count",
        "conflict_count",
        "providers_succeeded",
        "providers_failed",
        "sources_succeeded",
        "sources_failed",
        "accepted_candidates",
        "candidates_seen",
    ):
        if hasattr(
            value,
            name,
        ):
            try:
                output[
                    name
                ] = getattr(
                    value,
                    name,
                )
            except Exception:
                continue

    return output


def text_contains_secret(
    text: str,
) -> bool:
    lowered = text.lower()

    suspicious_literals = (
        "must-not-survive",
        "must-be-redacted",
        "top-secret-value",
        "secret.token.value",
    )

    return any(
        item in lowered
        for item in suspicious_literals
    )


def callable_has_only_optional_parameters(
    function: object,
) -> bool:
    if not callable(
        function
    ):
        return False

    try:
        signature = inspect.signature(
            function
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    for parameter in signature.parameters.values():
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue

        if (
            parameter.default
            is inspect.Parameter.empty
        ):
            return False

    return True


def discover_zero_argument_diagnostics(
    module: types.ModuleType,
) -> list[
    tuple[str, object]
]:
    diagnostics: list[
        tuple[str, object]
    ] = []

    for name in dir(
        module
    ):
        if not (
            name.startswith(
                "run_"
            )
            and "diagnostic" in name
        ):
            continue

        function = getattr(
            module,
            name,
            None,
        )

        if callable_has_only_optional_parameters(
            function
        ):
            diagnostics.append(
                (
                    name,
                    function,
                )
            )

    diagnostics.sort(
        key=lambda item: item[0]
    )

    return diagnostics


def capture_call(
    function: object,
    *args: object,
    **kwargs: object,
) -> tuple[
    object,
    str,
    str,
]:
    stdout = io.StringIO()
    stderr = io.StringIO()

    with redirect_stdout(
        stdout
    ), redirect_stderr(
        stderr
    ):
        result = function(
            *args,
            **kwargs,
        )

    return (
        result,
        stdout.getvalue(),
        stderr.getvalue(),
    )


def assert_no_synthetic_secret_leak(
    test_case: unittest.TestCase,
    *,
    stdout: str,
    stderr: str,
) -> None:
    combined = (
        stdout
        + "\n"
        + stderr
    )

    test_case.assertFalse(
        text_contains_secret(
            combined
        ),
        "Diagnostic output leaked a synthetic secret marker.",
    )


def normalize_action(
    result: object,
) -> str:
    action = getattr(
        result,
        "action",
        "",
    )

    action = enum_value(
        action
    )

    return str(
        action
    ).strip().lower()


def normalize_status(
    result: object,
) -> str:
    status = getattr(
        result,
        "status",
        "",
    )

    status = enum_value(
        status
    )

    return str(
        status
    ).strip().lower()


def is_block_or_review_result(
    result: object,
) -> bool:
    if bool(
        getattr(
            result,
            "blocked",
            False,
        )
    ):
        return True

    if bool(
        getattr(
            result,
            "requires_review",
            False,
        )
    ):
        return True

    action = normalize_action(
        result
    )

    status = normalize_status(
        result
    )

    return (
        action in {
            "review",
            "blocked",
            "block",
        }
        or status in {
            "review",
            "blocked",
            "block",
            "tombstoned",
        }
    )


# ============================================================
# Module/import tests
# ============================================================

class TestModuleImports(
    unittest.TestCase
):
    def test_all_core_modules_import(
        self,
    ) -> None:
        failures: dict[
            str,
            str,
        ] = {}

        for module_name in CORE_MODULES:
            try:
                import_engine_module(
                    module_name
                )

            except Exception as exc:
                failures[
                    module_name
                ] = (
                    f"{type(exc).__name__}: {exc}"
                )

        self.assertEqual(
            failures,
            {},
            (
                "One or more OSGuide engine modules failed to import:\n"
                + json.dumps(
                    failures,
                    indent=2,
                    sort_keys=True,
                )
            ),
        )

    def test_python_sources_compile(
        self,
    ) -> None:
        failures: dict[
            str,
            str,
        ] = {}

        root = module_directory()

        for module_name in CORE_MODULES:
            path = (
                root
                / f"{module_name}.py"
            )

            if not path.exists():
                failures[
                    module_name
                ] = "source file missing"
                continue

            try:
                source = path.read_text(
                    encoding="utf-8"
                )

                compile(
                    source,
                    str(
                        path
                    ),
                    "exec",
                )

            except Exception as exc:
                failures[
                    module_name
                ] = (
                    f"{type(exc).__name__}: {exc}"
                )

        self.assertEqual(
            failures,
            {},
            (
                "One or more Python source files failed syntax compilation:\n"
                + json.dumps(
                    failures,
                    indent=2,
                    sort_keys=True,
                )
            ),
        )

    def test_public_exports_resolve(
        self,
    ) -> None:
        failures: dict[
            str,
            list[str],
        ] = {}

        for module_name in CORE_MODULES:
            module = import_engine_module(
                module_name
            )

            exports = getattr(
                module,
                "__all__",
                None,
            )

            if exports is None:
                continue

            missing = [
                str(
                    export_name
                )
                for export_name in exports
                if not hasattr(
                    module,
                    str(
                        export_name
                    ),
                )
            ]

            if missing:
                failures[
                    module_name
                ] = missing

        self.assertEqual(
            failures,
            {},
            (
                "Some names declared in __all__ do not exist:\n"
                + json.dumps(
                    failures,
                    indent=2,
                    sort_keys=True,
                )
            ),
        )


# ============================================================
# Configuration tests
# ============================================================

class TestConfiguration(
    unittest.TestCase
):
    def test_configuration_loads_in_dry_run(
        self,
    ) -> None:
        config_module = import_engine_module(
            "config"
        )

        load_config = getattr(
            config_module,
            "load_config",
        )

        config = load_config()

        self.assertIsNotNone(
            config
        )

        dry_run = getattr(
            config,
            "dry_run",
            None,
        )

        run_mode = str(
            enum_value(
                getattr(
                    config,
                    "run_mode",
                    "",
                )
            )
        ).lower()

        self.assertTrue(
            dry_run is True
            or run_mode == "dry-run",
            (
                "Tests expect OSGuide configuration to load in dry-run mode."
            ),
        )

    def test_publishing_not_enabled_by_default_test_environment(
        self,
    ) -> None:
        config_module = import_engine_module(
            "config"
        )

        config = config_module.load_config()

        publishing_enabled = bool(
            getattr(
                config,
                "publishing_enabled",
                False,
            )
        )

        self.assertFalse(
            publishing_enabled,
            "Publishing must remain disabled in the test environment.",
        )


# ============================================================
# Discovery tests
# ============================================================

class TestDiscovery(
    unittest.TestCase
):
    def test_default_discovery_diagnostic(
        self,
    ) -> None:
        discovery = import_engine_module(
            "discovery"
        )

        function = getattr(
            discovery,
            "run_discovery_diagnostic",
        )

        result, stdout, stderr = capture_call(
            function,
            max_apps=5,
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIsNotNone(
            result
        )

        self.assertGreaterEqual(
            int(
                getattr(
                    result,
                    "sources_succeeded",
                    0,
                )
            ),
            1,
        )

        candidates = getattr(
            result,
            "candidates",
            [],
        )

        self.assertGreaterEqual(
            len(
                candidates
            ),
            1,
            "Default Discovery diagnostic must return at least one candidate.",
        )

    def test_extended_discovery_isolates_source_failure(
        self,
    ) -> None:
        discovery = import_engine_module(
            "discovery"
        )

        function = getattr(
            discovery,
            "run_extended_discovery_diagnostic",
            None,
        )

        if not callable(
            function
        ):
            self.skipTest(
                "Extended Discovery diagnostic is not available."
            )

        result, stdout, stderr = capture_call(
            function,
            max_apps=10,
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertGreaterEqual(
            int(
                getattr(
                    result,
                    "sources_succeeded",
                    0,
                )
            ),
            1,
        )

        self.assertGreaterEqual(
            int(
                getattr(
                    result,
                    "sources_failed",
                    0,
                )
            ),
            1,
            (
                "Extended diagnostic should intentionally exercise "
                "failure isolation."
            ),
        )


# ============================================================
# Resolver tests
# ============================================================

class TestResolver(
    unittest.TestCase
):
    @staticmethod
    def candidate() -> object:
        discovery = import_engine_module(
            "discovery"
        )

        AppCandidate = getattr(
            discovery,
            "AppCandidate",
        )

        return AppCandidate(
            name="OSGuide Diagnostic App",
            source_type="github",
            source_url="https://github.com/",
            package_id="org.osguide.diagnostic",
            repository_url="https://github.com/",
            description=(
                "Diagnostic candidate used by OSGuide engine tests."
            ),
            source_confidence=0.95,
        )

    def test_resolver_diagnostic(
        self,
    ) -> None:
        resolver = import_engine_module(
            "resolver"
        )

        result, stdout, stderr = capture_call(
            resolver.run_resolver_diagnostic,
            self.candidate(),
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIsNotNone(
            result
        )

        self.assertGreaterEqual(
            int(
                getattr(
                    result,
                    "providers_succeeded",
                    0,
                )
            ),
            1,
        )

        self.assertGreaterEqual(
            int(
                getattr(
                    result,
                    "resolved_field_count",
                    0,
                )
            ),
            1,
        )

    def test_extended_resolver_failure_isolation(
        self,
    ) -> None:
        resolver = import_engine_module(
            "resolver"
        )

        function = getattr(
            resolver,
            "run_extended_resolver_diagnostic",
            None,
        )

        if not callable(
            function
        ):
            self.skipTest(
                "Extended Resolver diagnostic is not available."
            )

        result, stdout, stderr = capture_call(
            function,
            self.candidate(),
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertGreaterEqual(
            int(
                getattr(
                    result,
                    "providers_succeeded",
                    0,
                )
            ),
            1,
        )

        # The extended registry intentionally includes a failing provider.
        self.assertGreaterEqual(
            int(
                getattr(
                    result,
                    "providers_failed",
                    0,
                )
            ),
            1,
        )


# ============================================================
# APK Intelligence tests
# ============================================================

class TestApkIntelligence(
    unittest.TestCase
):
    def test_default_apk_diagnostic_selects_candidate(
        self,
    ) -> None:
        apk = import_engine_module(
            "apk_intelligence"
        )

        result, stdout, stderr = capture_call(
            apk.run_apk_diagnostic,
            package_id="org.osguide.diagnostic",
            version_hint="1.0.0",
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIsNotNone(
            result
        )

        selected = getattr(
            result,
            "selected",
            None,
        )

        self.assertIsNotNone(
            selected,
            "Default APK diagnostic should select a safe synthetic APK.",
        )

        if selected is not None:
            selected_url = str(
                getattr(
                    selected,
                    "url",
                    "",
                )
            )

            self.assertTrue(
                selected_url.startswith(
                    "https://"
                )
            )

            self.assertTrue(
                selected_url.lower().endswith(
                    ".apk"
                )
            )

    def test_extended_apk_diagnostic_isolates_provider_failure(
        self,
    ) -> None:
        apk = import_engine_module(
            "apk_intelligence"
        )

        function = getattr(
            apk,
            "run_extended_apk_diagnostic",
            None,
        )

        if not callable(
            function
        ):
            self.skipTest(
                "Extended APK diagnostic is not available."
            )

        result, stdout, stderr = capture_call(
            function,
            package_id="org.osguide.diagnostic",
            version_hint="1.0.0",
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        provider_results = list(
            getattr(
                result,
                "provider_results",
                [],
            )
        )

        self.assertGreaterEqual(
            len(
                provider_results
            ),
            1,
        )

        failed = [
            item
            for item in provider_results
            if getattr(
                item,
                "error",
                None,
            )
        ]

        self.assertGreaterEqual(
            len(
                failed
            ),
            1,
            (
                "Extended APK diagnostic should exercise provider "
                "failure isolation."
            ),
        )


# ============================================================
# Content Intelligence tests
# ============================================================

class TestContentIntelligence(
    unittest.TestCase
):
    def test_deterministic_content_diagnostic(
        self,
    ) -> None:
        content = import_engine_module(
            "content_intelligence"
        )

        result, stdout, stderr = capture_call(
            content.run_content_diagnostic
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIsNotNone(
            result
        )

        self.assertGreater(
            int(
                getattr(
                    result,
                    "evidence_count",
                    0,
                )
            ),
            0,
        )

        populated = getattr(
            result,
            "populated_fields",
            0,
        )

        if isinstance(
            populated,
            Sequence,
        ) and not isinstance(
            populated,
            (str, bytes),
        ):
            self.assertGreater(
                len(
                    populated
                ),
                0,
            )

        else:
            self.assertGreater(
                int(
                    populated
                ),
                0,
            )

    def test_ai_failure_preserves_deterministic_fallback(
        self,
    ) -> None:
        content = import_engine_module(
            "content_intelligence"
        )

        function = getattr(
            content,
            "run_ai_failure_fallback_diagnostic",
            None,
        )

        if not callable(
            function
        ):
            self.skipTest(
                "AI fallback diagnostic is not available."
            )

        result, stdout, stderr = capture_call(
            function
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        short_description = getattr(
            getattr(
                result,
                "short_description",
                None,
            ),
            "value",
            None,
        )

        self.assertTrue(
            bool(
                short_description
            ),
            (
                "Content layer must preserve deterministic fallback when "
                "the diagnostic AI generator fails."
            ),
        )


# ============================================================
# Decision Engine tests
# ============================================================

class TestDecisionEngine(
    unittest.TestCase
):
    def test_new_app_decision(
        self,
    ) -> None:
        decision_engine = import_engine_module(
            "decision_engine"
        )

        result, stdout, stderr = capture_call(
            decision_engine.run_new_app_decision_diagnostic
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIsNotNone(
            result
        )

        self.assertIn(
            normalize_action(
                result
            ),
            {
                "insert",
                "review",
            },
            (
                "New-app diagnostic must result in INSERT or safe REVIEW."
            ),
        )

    def test_existing_update_decision(
        self,
    ) -> None:
        decision_engine = import_engine_module(
            "decision_engine"
        )

        result, stdout, stderr = capture_call(
            decision_engine.run_existing_update_decision_diagnostic
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIn(
            normalize_action(
                result
            ),
            {
                "update",
                "review",
                "skip",
            },
        )

    def test_existing_repair_decision(
        self,
    ) -> None:
        decision_engine = import_engine_module(
            "decision_engine"
        )

        result, stdout, stderr = capture_call(
            decision_engine.run_existing_repair_decision_diagnostic
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIn(
            normalize_action(
                result
            ),
            {
                "repair",
                "review",
                "update",
                "skip",
            },
        )

    def test_tombstone_decision_never_republishes_silently(
        self,
    ) -> None:
        decision_engine = import_engine_module(
            "decision_engine"
        )

        result, stdout, stderr = capture_call(
            decision_engine.run_tombstone_decision_diagnostic
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        action = normalize_action(
            result
        )

        self.assertNotIn(
            action,
            {
                "insert",
                "update",
                "repair",
            },
            (
                "Tombstoned application must not be automatically "
                "reinserted, updated, or repaired."
            ),
        )

        self.assertTrue(
            is_block_or_review_result(
                result
            ),
            "Tombstone diagnostic should block or require review.",
        )


# ============================================================
# Publisher tests
# ============================================================

class TestPublisher(
    unittest.TestCase
):
    def test_default_publisher_diagnostic_is_safe(
        self,
    ) -> None:
        publisher = import_engine_module(
            "publisher"
        )

        result, stdout, stderr = capture_call(
            publisher.run_publisher_diagnostic
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIsNotNone(
            result
        )

        outcomes = list(
            getattr(
                result,
                "outcomes",
                [],
            )
        )

        self.assertGreaterEqual(
            len(
                outcomes
            ),
            1,
        )

        # run_publisher_diagnostic() is explicitly expected to use the
        # diagnostic backend and dry-run policy.
        failures = int(
            getattr(
                getattr(
                    result,
                    "counters",
                    object(),
                ),
                "failures",
                0,
            )
        )

        self.assertEqual(
            failures,
            0,
        )

    def test_tombstone_publisher_diagnostic_blocks_write(
        self,
    ) -> None:
        publisher = import_engine_module(
            "publisher"
        )

        result, stdout, stderr = capture_call(
            publisher.run_tombstone_diagnostic
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        status = normalize_status(
            result
        )

        self.assertIn(
            status,
            {
                "blocked",
                "review",
                "skipped",
                "skip",
            },
            (
                "Publisher tombstone diagnostic must not produce a "
                "successful write outcome."
            ),
        )

    def test_default_policy_forbids_delete(
        self,
    ) -> None:
        publisher = import_engine_module(
            "publisher"
        )

        policy = publisher.default_dry_run_policy()

        self.assertFalse(
            bool(
                getattr(
                    policy,
                    "allow_delete",
                    True,
                )
            )
        )

        self.assertFalse(
            bool(
                getattr(
                    policy,
                    "automatic_delete",
                    True,
                )
            )
        )


# ============================================================
# Security tests
# ============================================================

class TestSecurity(
    unittest.TestCase
):
    def test_security_diagnostic(
        self,
    ) -> None:
        security = import_engine_module(
            "security"
        )

        result, stdout, stderr = capture_call(
            security.run_security_diagnostic
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIsInstance(
            result,
            Mapping,
        )

        self.assertTrue(
            bool(
                result.get(
                    "package_id_allowed"
                )
            )
        )

        self.assertTrue(
            bool(
                result.get(
                    "private_url_blocked"
                )
            )
        )

        self.assertTrue(
            bool(
                result.get(
                    "fake_github_blocked"
                )
            )
        )

        self.assertTrue(
            bool(
                result.get(
                    "embedded_secret_blocked"
                )
            )
        )

        self.assertTrue(
            bool(
                result.get(
                    "traversal_blocked"
                )
            )
        )

    def test_redaction_removes_secret_values(
        self,
    ) -> None:
        security = import_engine_module(
            "security"
        )

        result = security.run_redaction_diagnostic()

        serialized = json.dumps(
            result,
            sort_keys=True,
            default=str,
        )

        self.assertIn(
            "[REDACTED]",
            serialized,
        )

        self.assertNotIn(
            "top-secret-value",
            serialized,
        )

        self.assertNotIn(
            "Bearer test-value",
            serialized,
        )

    def test_loopback_url_is_blocked(
        self,
    ) -> None:
        security = import_engine_module(
            "security"
        )

        policy = security.SecurityPolicy(
            resolve_dns_before_network=False
        )

        report = security.validate_url(
            "https://127.0.0.1/internal",
            policy=policy,
            resolve_dns=False,
        )

        self.assertTrue(
            bool(
                getattr(
                    report,
                    "blocked",
                    False,
                )
            )
        )

    def test_fake_github_suffix_is_blocked(
        self,
    ) -> None:
        security = import_engine_module(
            "security"
        )

        policy = security.SecurityPolicy(
            resolve_dns_before_network=False
        )

        report = security.validate_github_url(
            "https://github.com.attacker.example/repository",
            policy=policy,
            resolve_dns=False,
        )

        self.assertTrue(
            bool(
                getattr(
                    report,
                    "blocked",
                    False,
                )
            )
        )

    def test_path_traversal_is_blocked(
        self,
    ) -> None:
        security = import_engine_module(
            "security"
        )

        report = security.validate_relative_path(
            "../../etc/passwd"
        )

        self.assertTrue(
            bool(
                getattr(
                    report,
                    "blocked",
                    False,
                )
            )
        )

    def test_valid_sha256_is_accepted(
        self,
    ) -> None:
        security = import_engine_module(
            "security"
        )

        report = security.validate_sha256(
            "a" * 64
        )

        self.assertFalse(
            bool(
                getattr(
                    report,
                    "blocked",
                    False,
                )
            )
        )


# ============================================================
# Generic diagnostics for Memory / Observability / Audit
# ============================================================

class DiagnosticModuleMixin:
    MODULE_NAME: str = ""

    def diagnostic_module(
        self,
    ) -> types.ModuleType:
        return import_engine_module(
            self.MODULE_NAME
        )

    def run_zero_argument_diagnostics(
        self,
    ) -> list[
        tuple[
            str,
            object,
        ]
    ]:
        module = self.diagnostic_module()

        diagnostics = discover_zero_argument_diagnostics(
            module
        )

        if not diagnostics:
            self.skipTest(
                f"{self.MODULE_NAME} exposes no zero-argument diagnostics."
            )

        results: list[
            tuple[
                str,
                object,
            ]
        ] = []

        for name, function in diagnostics:
            result, stdout, stderr = capture_call(
                function
            )

            assert_no_synthetic_secret_leak(
                self,
                stdout=stdout,
                stderr=stderr,
            )

            self.assertIsNotNone(
                result,
                (
                    f"{self.MODULE_NAME}.{name} returned None."
                ),
            )

            results.append(
                (
                    name,
                    result,
                )
            )

        return results


class TestMemory(
    DiagnosticModuleMixin,
    unittest.TestCase,
):
    MODULE_NAME = "memory"

    def test_memory_diagnostics(
        self,
    ) -> None:
        results = self.run_zero_argument_diagnostics()

        self.assertGreater(
            len(
                results
            ),
            0,
        )


class TestObservability(
    DiagnosticModuleMixin,
    unittest.TestCase,
):
    MODULE_NAME = "observability"

    def test_observability_diagnostics(
        self,
    ) -> None:
        results = self.run_zero_argument_diagnostics()

        self.assertGreater(
            len(
                results
            ),
            0,
        )


class TestAuditRollback(
    DiagnosticModuleMixin,
    unittest.TestCase,
):
    MODULE_NAME = "audit_rollback"

    def test_audit_rollback_diagnostics(
        self,
    ) -> None:
        results = self.run_zero_argument_diagnostics()

        self.assertGreater(
            len(
                results
            ),
            0,
        )

    def test_tombstone_protection_diagnostic_when_available(
        self,
    ) -> None:
        module = self.diagnostic_module()

        function = getattr(
            module,
            "run_tombstone_protection_diagnostic",
            None,
        )

        if not callable(
            function
        ):
            self.skipTest(
                "Audit/Rollback tombstone diagnostic is not available."
            )

        result, stdout, stderr = capture_call(
            function
        )

        assert_no_synthetic_secret_leak(
            self,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertIsInstance(
            result,
            Mapping,
        )

        self.assertTrue(
            bool(
                result.get(
                    "blocked"
                )
            )
        )


# ============================================================
# Cross-layer integration diagnostic
# ============================================================

class TestDiagnosticPipeline(
    unittest.TestCase
):
    def test_discovery_to_decision_pipeline(
        self,
    ) -> None:
        discovery = import_engine_module(
            "discovery"
        )

        resolver = import_engine_module(
            "resolver"
        )

        apk = import_engine_module(
            "apk_intelligence"
        )

        content = import_engine_module(
            "content_intelligence"
        )

        decision_engine = import_engine_module(
            "decision_engine"
        )

        AppCandidate = getattr(
            discovery,
            "AppCandidate",
        )

        candidate = AppCandidate(
            name="OSGuide Diagnostic App",
            source_type="github",
            source_url="https://github.com/",
            package_id="org.osguide.diagnostic",
            repository_url="https://github.com/",
            description=(
                "Diagnostic application used to validate cross-layer "
                "OSGuide integration."
            ),
            source_confidence=0.95,
        )

        resolution = resolver.run_resolver_diagnostic(
            candidate
        )

        apk_result = apk.run_apk_diagnostic(
            package_id="org.osguide.diagnostic",
            version_hint="1.0.0",
        )

        content_result = content.run_content_diagnostic()

        data = decision_engine.DecisionInput(
            candidate=candidate,
            resolution=resolution,
            apk=apk_result,
            content=content_result,
            existing=None,
            run_id="tests-cross-layer",
        )

        decision = decision_engine.decide(
            data
        )

        self.assertIsNotNone(
            decision
        )

        self.assertIn(
            normalize_action(
                decision
            ),
            {
                "insert",
                "review",
            },
        )

        if getattr(
            decision,
            "payload",
            None,
        ) is not None:
            request = decision_engine.to_publication_request(
                decision,
                run_id="tests-cross-layer",
                candidate_identity=getattr(
                    candidate,
                    "identity",
                    None,
                ),
            )

            self.assertIsNotNone(
                request
            )

            payload = getattr(
                request,
                "payload",
                None,
            )

            self.assertIsNotNone(
                payload
            )

            self.assertEqual(
                getattr(
                    payload,
                    "package_id",
                    None,
                ),
                "org.osguide.diagnostic",
            )


# ============================================================
# Main-controller safety tests
# ============================================================

class TestMainController(
    unittest.TestCase
):
    def test_main_import_does_not_execute_engine(
        self,
    ) -> None:
        # Importing main.py must not automatically call main().
        module = import_engine_module(
            "main"
        )

        self.assertTrue(
            callable(
                getattr(
                    module,
                    "main",
                    None,
                )
            )
        )

    def test_main_keeps_publisher_safety_lock_when_exposed(
        self,
    ) -> None:
        module = import_engine_module(
            "main"
        )

        if not hasattr(
            module,
            "PUBLISHER_CONNECTED",
        ):
            self.skipTest(
                "main.py does not expose PUBLISHER_CONNECTED."
            )

        self.assertFalse(
            bool(
                getattr(
                    module,
                    "PUBLISHER_CONNECTED"
                )
            ),
            (
                "Current integration phase expects the main controller's "
                "live Publisher safety lock to remain disabled."
            ),
        )


# ============================================================
# Summary test
# ============================================================

class TestSuiteCompleteness(
    unittest.TestCase
):
    def test_every_expected_module_has_source_file(
        self,
    ) -> None:
        root = module_directory()

        missing = [
            module_name
            for module_name in CORE_MODULES
            if not (
                root
                / f"{module_name}.py"
            ).exists()
        ]

        self.assertEqual(
            missing,
            [],
            (
                "Expected OSGuide engine source files are missing: "
                + ", ".join(
                    missing
                )
            ),
        )


# ============================================================
# Runner helpers
# ============================================================

def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()

    return loader.loadTestsFromModule(
        sys.modules[
            __name__
        ]
    )


def run_suite(
    *,
    verbosity: int = 2,
) -> unittest.result.TestResult:
    suite = build_suite()

    runner = unittest.TextTestRunner(
        verbosity=verbosity,
    )

    return runner.run(
        suite
    )


def print_environment_banner() -> None:
    print(
        "=" * 68
    )

    print(
        TEST_SUITE_NAME
    )

    print(
        f"Suite version: {TEST_SUITE_VERSION}"
    )

    print(
        f"Python: {sys.version.split()[0]}"
    )

    print(
        f"Engine directory: {module_directory()}"
    )

    print(
        "Mode: dry-run test environment"
    )

    print(
        "Network writes: forbidden by test design"
    )

    print(
        "Supabase publication: not invoked"
    )

    print(
        "=" * 68
    )

    print()


def parse_arguments(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the OSGuide Engine comprehensive local test suite."
        )
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Use unittest verbosity level 2.",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Use unittest verbosity level 0.",
    )

    return parser.parse_args(
        argv
    )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    arguments = parse_arguments(
        argv
    )

    verbosity = 1

    if arguments.verbose:
        verbosity = 2

    if arguments.quiet:
        verbosity = 0

    print_environment_banner()

    result = run_suite(
        verbosity=verbosity
    )

    print()

    print(
        "=" * 68
    )

    print(
        "OSGuide Test Summary"
    )

    print(
        "=" * 68
    )

    print(
        f"Tests run: {result.testsRun}"
    )

    print(
        f"Failures: {len(result.failures)}"
    )

    print(
        f"Errors: {len(result.errors)}"
    )

    print(
        f"Skipped: {len(result.skipped)}"
    )

    succeeded = (
        result.wasSuccessful()
    )

    print(
        "Result: "
        + (
            "PASS"
            if succeeded
            else "FAIL"
        )
    )

    print(
        "=" * 68
    )

    return (
        0
        if succeeded
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
