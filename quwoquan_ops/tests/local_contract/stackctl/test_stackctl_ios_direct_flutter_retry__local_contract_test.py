import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import app_preflight_uat_platform as platform_launch
from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    COCOAPODS_ENVIRONMENT_KEYS,
    AppDependencyToolchainError,
)


_COCOAPODS_FIELDS = {
    "QWQ_COCOAPODS_EXECUTABLE": "/toolchain/cocoapods/bin/pod",
    "QWQ_COCOAPODS_VERSION": "1.16.2",
    "QWQ_COCOAPODS_EXECUTABLE_DIGEST": "sha256:" + "1" * 64,
    "QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST": "sha256:" + "2" * 64,
    "QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST": "sha256:" + "3" * 64,
    "QWQ_COCOAPODS_BINDING_SEAL": "sha256:" + "4" * 64,
}
_FROZEN_COCOAPODS_ENVIRONMENT_KEYS = ("PATH", *COCOAPODS_ENVIRONMENT_KEYS)


class _CocoaPodsIdentity:
    def as_environment(self) -> dict[str, str]:
        return dict(_COCOAPODS_FIELDS)


class _Lock:
    def close(self) -> None:
        pass


def _passing_direct_evidence() -> dict[str, object]:
    return {
        "status": "passed",
        "launchProvenance": "canonical_launcher",
        "runtimeConfigSupplyMode": "external_runtime_package",
        "consumerLeaseId": "sha256:" + "7" * 64,
        "reportPath": "/evidence/canonical-hot-restart.json",
        "runtimeIdentitySnapshots": [
            {
                "runtimeConfigDigest": "runtime-package-digest",
                "effectiveLaunchManifestDigest": "launch-manifest-digest",
            }
        ],
    }


def _invoke_platform_launch(
    fake_stackctl: SimpleNamespace,
    *,
    dry_run: bool = False,
) -> tuple[bool, list[str], list[dict[str, object]]]:
    issues: list[str] = []
    runs: list[dict[str, object]] = []
    launch_binding = {
        "buildProjectionSeal": {
            "buildProjectionDigest": "sha256:" + "8" * 64,
        },
        "runtimeConfigPackageDigest": "runtime-package-digest",
        "effectiveLaunchManifestDigest": "launch-manifest-digest",
    }
    passed = platform_launch.execute_canonical_platform_launch(
        args=SimpleNamespace(platform="ios-simulator", dry_run=dry_run),
        stackctl=fake_stackctl,
        environment="alpha",
        target="alpha-local",
        device_id="SIMULATOR-UDID",
        launch_attempt_path=Path(
            "/evidence/alpha-local/canonical-launch/attempt-1/attempt.json"
        ),
        launch_report_path=Path(
            "/evidence/alpha-local/canonical-launch/attempt-1/report.json"
        ),
        launch_control={
            "sourceCapsuleManifestRef": "/candidate/manifest.json",
            "controlRef": (
                "/evidence/alpha-local/canonical-launch/attempt-1/control.json"
            ),
            "controlDigest": "sha256:" + "5" * 64,
            "startupTerminalReceiptRef": (
                "/evidence/alpha-local/canonical-launch/attempt-1/"
                "startup-terminal.json"
            ),
        },
        canonical_output_root=Path("/evidence"),
        launch_app_root=Path("/candidate/quwoquan_app"),
        runtime_binding={},
        launch_projection={},
        build_projection_policy_id="ios-policy",
        report_dir=Path("/evidence/uat"),
        issues=issues,
        runs=runs,
        launch_bindings={},
        canonical_launch_command=lambda **_kwargs: ([], {}),
        launch_binding_reader=lambda **_kwargs: dict(launch_binding),
        write_launch_control=lambda **_kwargs: {
            "controlRef": (
                "/evidence/uat/alpha-local/canonical-launch/attempt-2/control.json"
            ),
            "controlDigest": "sha256:" + "6" * 64,
            "startupTerminalReceiptRef": (
                "/evidence/uat/alpha-local/canonical-launch/attempt-2/"
                "startup-terminal.json"
            ),
        },
    )
    return passed, issues, runs


class IosDirectFlutterRetryContractTest(unittest.TestCase):
    def test_attempt_one_and_retry_reuse_one_parent_cocoapods_binding(self) -> None:
        retryable_evidence = {
            "status": "failed",
            "reportPath": "/evidence/attempt-1-report.json",
        }
        run = Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    [], 1, json.dumps(retryable_evidence), ""
                ),
                subprocess.CompletedProcess(
                    [], 0, json.dumps(_passing_direct_evidence()), ""
                ),
            ]
        )
        fake_stackctl = SimpleNamespace(
            acquire_patrol_execution_lock=lambda **_kwargs: _Lock(),
            run=run,
            _ios_direct_flutter_log_reader_retryable=lambda _evidence: True,
            _DATA_READINESS_DIGEST_RE=re.compile(r"^sha256:[0-9a-f]{64}$"),
        )
        identity = _CocoaPodsIdentity()

        def project_environment(
            observed_identity: object,
            *,
            base: object,
        ) -> dict[str, str]:
            self.assertIs(observed_identity, identity)
            self.assertIs(base, os.environ)
            return {
                **dict(os.environ),
                "PATH": "/toolchain/cocoapods/bin:/ambient/bin",
                **_COCOAPODS_FIELDS,
            }

        with (
            patch.dict(os.environ, {"PATH": "/ambient/bin"}, clear=True),
            patch.object(
                platform_launch,
                "resolve_cocoapods_identity",
                return_value=identity,
            ) as resolver,
            patch.object(
                platform_launch,
                "cocoapods_environment",
                side_effect=project_environment,
            ) as environment_projector,
        ):
            passed, issues, _runs = _invoke_platform_launch(fake_stackctl)

        self.assertTrue(passed)
        self.assertEqual(issues, [])
        resolver.assert_called_once_with("", search_path="/ambient/bin")
        environment_projector.assert_called_once()
        self.assertEqual(run.call_count, 2)
        attempt_one_environment = dict(run.call_args_list[0].kwargs["env"])
        retry_environment = dict(run.call_args_list[1].kwargs["env"])
        self.assertEqual(
            {
                key: attempt_one_environment[key]
                for key in _FROZEN_COCOAPODS_ENVIRONMENT_KEYS
            },
            {
                key: retry_environment[key]
                for key in _FROZEN_COCOAPODS_ENVIRONMENT_KEYS
            },
        )
        self.assertEqual(
            {
                key
                for key in attempt_one_environment
                if attempt_one_environment.get(key) != retry_environment.get(key)
            },
            {
                "QWQ_APP_LAUNCH_RECEIPT",
                "QWQ_APP_TEST_LIVE_REPORT",
                "QWQ_CANONICAL_LAUNCH_CONTROL",
                "QWQ_CANONICAL_LAUNCH_CONTROL_DIGEST",
                "QWQ_APP_STARTUP_TERMINAL_RECEIPT",
            },
        )

    def test_complete_parent_identity_is_validated_and_path_mix_fails_closed(
        self,
    ) -> None:
        run = Mock()
        fake_stackctl = SimpleNamespace(
            acquire_patrol_execution_lock=Mock(),
            run=run,
            _ios_direct_flutter_log_reader_retryable=Mock(),
            _DATA_READINESS_DIGEST_RE=re.compile(r"^sha256:[0-9a-f]{64}$"),
        )
        mixed_error = AppDependencyToolchainError(
            "APP.DEPENDENCY.cocoapods_mixed: declared executable differs from PATH"
        )
        with (
            patch.dict(
                os.environ,
                {"PATH": "/hostile/bin", **_COCOAPODS_FIELDS},
                clear=True,
            ),
            patch.object(
                platform_launch,
                "resolve_cocoapods_identity",
                side_effect=mixed_error,
            ) as resolver,
            patch.object(platform_launch, "cocoapods_environment") as projector,
        ):
            passed, issues, _runs = _invoke_platform_launch(fake_stackctl)

        self.assertFalse(passed)
        resolver.assert_called_once_with(
            _COCOAPODS_FIELDS["QWQ_COCOAPODS_EXECUTABLE"],
            search_path="/hostile/bin",
        )
        projector.assert_not_called()
        run.assert_not_called()
        self.assertIn("APP.DEPENDENCY.cocoapods_mixed", issues[0])

    def test_incomplete_or_unprojectable_identity_blocks_before_child(self) -> None:
        cases = ("incomplete", "environment-failure")
        for case in cases:
            with self.subTest(case=case):
                run = Mock()
                fake_stackctl = SimpleNamespace(
                    acquire_patrol_execution_lock=Mock(),
                    run=run,
                    _ios_direct_flutter_log_reader_retryable=Mock(),
                    _DATA_READINESS_DIGEST_RE=re.compile(
                        r"^sha256:[0-9a-f]{64}$"
                    ),
                )
                identity = _CocoaPodsIdentity()
                resolver = Mock(return_value=identity)
                projector = Mock(
                    side_effect=AppDependencyToolchainError(
                        "APP.DEPENDENCY.cocoapods_mixed: projection failed"
                    )
                )
                parent_environment = {"PATH": "/ambient/bin"}
                if case == "incomplete":
                    parent_environment["QWQ_COCOAPODS_VERSION"] = "1.16.2"
                with (
                    patch.dict(os.environ, parent_environment, clear=True),
                    patch.object(
                        platform_launch,
                        "resolve_cocoapods_identity",
                        resolver,
                    ),
                    patch.object(
                        platform_launch,
                        "cocoapods_environment",
                        projector,
                    ),
                ):
                    passed, issues, _runs = _invoke_platform_launch(fake_stackctl)

                self.assertFalse(passed)
                run.assert_not_called()
                self.assertIn("APP.DEPENDENCY.cocoapods_mixed", issues[0])
                if case == "incomplete":
                    resolver.assert_not_called()
                    projector.assert_not_called()
                else:
                    resolver.assert_called_once_with(
                        "", search_path="/ambient/bin"
                    )
                    projector.assert_called_once()

    def test_dry_run_does_not_resolve_physical_cocoapods(self) -> None:
        run = Mock(
            return_value=subprocess.CompletedProcess(
                [], 0, json.dumps(_passing_direct_evidence()), ""
            )
        )
        lock = Mock()
        fake_stackctl = SimpleNamespace(
            acquire_patrol_execution_lock=lock,
            run=run,
            _ios_direct_flutter_log_reader_retryable=lambda _evidence: False,
            _DATA_READINESS_DIGEST_RE=re.compile(r"^sha256:[0-9a-f]{64}$"),
        )
        with (
            patch.dict(os.environ, {"PATH": ""}, clear=True),
            patch.object(
                platform_launch,
                "resolve_cocoapods_identity",
            ) as resolver,
            patch.object(
                platform_launch,
                "cocoapods_environment",
            ) as environment_projector,
        ):
            passed, issues, _runs = _invoke_platform_launch(
                fake_stackctl,
                dry_run=True,
            )

        self.assertTrue(passed)
        self.assertEqual(issues, [])
        resolver.assert_not_called()
        environment_projector.assert_not_called()
        lock.assert_not_called()
        run.assert_called_once()
        self.assertNotIn(
            "QWQ_COCOAPODS_EXECUTABLE",
            run.call_args.kwargs["env"],
        )

    def test_only_healthy_cold_terminal_with_lost_log_reader_is_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            flutter_log = Path(temporary_dir) / "flutter-run.log"
            flutter_log.write_text(
                "Error waiting for a debug connection: "
                "The log reader failed unexpectedly\n",
                encoding="utf-8",
            )
            evidence = {
                "status": "failed",
                "issues": [
                    "expected 3 hot-restart Dart startup attempts, got 0"
                ],
                "flutterRunLog": str(flutter_log),
                "flutterProcessGroupStoppedBySigint": True,
                "flutterRunExitCode": 0,
                "attempts": [
                    {
                        "hotRestart": False,
                        "canonicalTerminal": "routerShell",
                        "configurationState": "complete",
                        "bootstrapFailure": False,
                        "terminalEventCount": 1,
                        "reportedSafeTerminalMs": 3492,
                        "nativeReceivedSafeTerminalMs": 4867,
                    }
                ],
            }

            self.assertTrue(
                stackctl._ios_direct_flutter_log_reader_retryable(evidence)
            )
            evidence["attempts"][0]["nativeReceivedSafeTerminalMs"] = 6001
            self.assertFalse(
                stackctl._ios_direct_flutter_log_reader_retryable(evidence)
            )
            evidence["attempts"][0]["nativeReceivedSafeTerminalMs"] = 4867
            evidence["flutterProcessGroupStoppedBySigint"] = False
            self.assertFalse(
                stackctl._ios_direct_flutter_log_reader_retryable(evidence)
            )

    def test_product_or_configuration_failure_is_never_retryable(self) -> None:
        evidence = {
            "status": "failed",
            "issues": ["cold: runtime configuration was not complete"],
            "flutterRunLog": "/missing",
            "attempts": [],
        }

        self.assertFalse(
            stackctl._ios_direct_flutter_log_reader_retryable(evidence)
        )


if __name__ == "__main__":
    unittest.main()
