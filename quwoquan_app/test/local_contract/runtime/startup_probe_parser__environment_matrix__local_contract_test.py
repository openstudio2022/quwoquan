# spec_ref: specs/feature-tree/spec.md#uat-003
# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-004
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
#
# 由 1000 行硬顶从 startup_probe_parser__local_contract_test.py 拆出：
# 本文件承接环境矩阵汇总场景组（release 绑定矩阵通过判定、component/release
# 状态区分、partial 证据 gate_block、UAT/Make 候选绑定）；测试逐字搬移。

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))
sys.path.insert(0, str(APP_DIR / "scripts/runtime/platform"))
sys.path.insert(0, str(APP_DIR / "test/support/runtime/launcher"))

import verify_startup_environment_matrix as startup_matrix
from verify_startup_environment_matrix import (
    _case_counts,
    _report_status,
)


class StartupProbeParserContractTest(unittest.TestCase):
    def test_component_runtime_defines_use_exact_test_live_target(self) -> None:
        defines = {
            **{key: "value" for key in startup_matrix.REQUIRED_DEFINES},
            "APP_RUNTIME_ENV": "beta",
        }
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps(defines),
            stderr="",
        )

        with mock.patch(
            "startup_environment_matrix.package_probe._run",
            return_value=completed,
        ) as run:
            self.assertEqual(startup_matrix._runtime_defines("beta"), defines)

        run.assert_called_once_with(
            "python3",
            "scripts/env/print_app_env_dart_defines.py",
            "--env",
            "beta",
            "--target",
            "beta-local",
            "--launch-policy",
            "test_live",
            "--format",
            "json",
        )

    def test_component_failure_prints_typed_issue_and_returns_nonzero(self) -> None:
        argv = [
            "verify_startup_environment_matrix.py",
            "--component-environment",
            "alpha",
        ]
        output = io.StringIO()
        with (
            mock.patch.object(
                startup_matrix.cli,
                "_runtime_defines",
                side_effect=RuntimeError("typed component probe failure"),
            ),
            mock.patch.object(sys, "argv", argv),
            redirect_stdout(output),
        ):
            self.assertEqual(startup_matrix.main(), 1)

        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "failed")
        self.assertEqual(
            report["issues"],
            ["alpha: typed component probe failure"],
        )

    def test_app_static_gate_does_not_hide_component_probe_report(self) -> None:
        gate = (APP_DIR.parent / "quwoquan_ops/gate/gate_repo.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("--component-environment gamma || exit 1", gate)
        self.assertNotIn("--component-environment gamma >/dev/null", gate)

    def test_release_bound_matrix_passes_only_with_all_real_case_results(
        self,
    ) -> None:
        digest = "sha256:" + "d" * 64
        baseline_id = "baseline-001"
        release_id = "release-001"
        runtime_cases = (
            ("alpha", "alpha-local"),
            ("beta", "beta-local"),
            ("gamma", "gamma-local"),
            ("prod", "prod-hosted"),
        )
        defines = {key: "value" for key in startup_matrix.REQUIRED_DEFINES}

        def environment_defines(environment: str) -> dict[str, str]:
            if environment == "prod":
                raise RuntimeError(
                    "test_live target/environment selection is invalid"
                )
            return {**defines, "APP_RUNTIME_ENV": environment}

        def handoff(environment: str, target: str | None = None) -> dict[str, str]:
            resolved_target = target or startup_matrix.RUNTIME_TARGETS[environment]
            return {
                "target": resolved_target,
                "entrypoint": "lib/main_prod.dart",
                "dartDefinesDigest": digest,
                "runtimeConfigDigest": digest,
                "effectiveLaunchManifestDigest": digest,
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "evidence"
            report_path = Path(directory) / "report.json"
            for environment, target in runtime_cases:
                target_root = root / target
                target_root.mkdir(parents=True, exist_ok=True)
                attempt_ids: list[str] = []
                device_ids: list[str] = []
                for platform, device_kind, evidence_stem in (
                    startup_matrix.DEVICE_PROFILES[target]
                ):
                    device_id = f"{evidence_stem}-device"
                    device_ids.append(device_id)
                    samples = []
                    for index in range(2):
                        attempt_id = f"{target}-{evidence_stem}-{index}"
                        attempt_ids.append(attempt_id)
                        sample = {
                            "runtimeEnv": environment,
                            "runtimeTarget": target,
                            "platform": platform,
                            "deviceId": device_id,
                            "deviceKind": device_kind,
                            "passed": True,
                            "attemptId": attempt_id,
                            "rendererFirstFrameMs": 900,
                            "safeTerminalMs": 1200,
                            "reportedSafeTerminalMs": 1190,
                            "nativeReceivedSafeTerminalMs": 1210,
                            "watchdogOutcome": "safe_terminal",
                            "canonicalTerminal": "routerShell",
                            "launchMode": "release_package",
                            "runtimeConfigurationState": "complete",
                            "missingDefineKeys": "",
                            "failureCode": "",
                            "startupSequenceMotionCurrent": True,
                            "effectiveLaunchManifestDigest": digest,
                            "telemetryAcknowledged": True,
                            "sourceReport": f"{target}-{evidence_stem}.json",
                        }
                        if platform == "android":
                            sample.update(
                                {
                                    "launcherIntentUsed": True,
                                    "launcherStarted": True,
                                    "launcherResolution": {
                                        "matchesExpectedGate": True,
                                    },
                                    "gateMainOrderObserved": True,
                                    "taskSnapshot": {
                                        "singleMainTask": True,
                                        "mainActivityInstances": 1,
                                    },
                                    "launchVisual": {
                                        "contractVerified": True,
                                        "sourceDigest": "d" * 64,
                                        "profile": "default",
                                    },
                                }
                            )
                        else:
                            sample.update(
                                {
                                    "sceneLaunchUsed": True,
                                    "sceneStarted": True,
                                    "sceneLauncher": (
                                        "xcrun_devicectl"
                                        if device_kind == "physical"
                                        else "xcrun_simctl"
                                    ),
                                }
                            )
                        samples.append(sample)
                    (target_root / f"{evidence_stem}.json").write_text(
                        json.dumps(
                            {
                                "schema": startup_matrix.RUNTIME_EVIDENCE_SCHEMA,
                                "baselineId": baseline_id,
                                "releaseId": release_id,
                                "releaseDigest": digest,
                                "runtimeEnv": environment,
                                "runtimeTarget": target,
                                "platform": platform,
                                "runs": len(samples),
                                "passed": True,
                                "specRefs": list(startup_matrix.SPEC_REFS),
                                "samples": samples,
                            }
                        ),
                        encoding="utf-8",
                    )
                    (target_root / f"{evidence_stem}.readback.json").write_text(
                        json.dumps(
                            {
                                "schema": startup_matrix.READBACK_EVIDENCE_SCHEMA,
                                "status": "passed",
                                "baselineId": baseline_id,
                                "releaseId": release_id,
                                "releaseDigest": digest,
                                "environment": environment,
                                "target": target,
                                "platform": platform,
                                "deviceId": device_id,
                                "deviceKind": (
                                    "physical"
                                    if device_kind in {
                                        "physical",
                                        "true_device",
                                    }
                                    else "simulator"
                                ),
                                "effectiveLaunchManifestDigest": digest,
                                "executed": 1,
                                "required": 1,
                                "skipped": 0,
                                "failed": 0,
                                "specRefs": list(startup_matrix.SPEC_REFS),
                                "caseResults": [
                                    {
                                        "caseId": "readback",
                                        "status": "passed",
                                        "testExecution": {
                                            "executed": 1,
                                            "skipped": 0,
                                            "failed": 0,
                                        },
                                    }
                                ],
                            }
                        ),
                        encoding="utf-8",
                    )
                (target_root / "observability.json").write_text(
                    json.dumps(
                        {
                            "schema": (
                                startup_matrix.OBSERVABILITY_EVIDENCE_SCHEMA
                            ),
                            "status": "passed",
                            "environment": environment,
                            "target": target,
                            "baselineId": baseline_id,
                            "releaseId": release_id,
                            "releaseDigest": digest,
                            "effectiveLaunchManifestDigest": digest,
                            "attemptIds": attempt_ids,
                            "deviceIds": device_ids,
                            "telemetryBackend": "product-ops-event-record",
                            "backendReceiptRef": f"{target}/telemetry.json",
                            "required": len(attempt_ids),
                            "executed": len(attempt_ids),
                            "skipped": 0,
                            "failed": 0,
                            "specRefs": list(startup_matrix.SPEC_REFS),
                        }
                    ),
                    encoding="utf-8",
                )

            argv = [
                "verify_startup_environment_matrix.py",
                "--evidence-root",
                str(root),
                "--require-runtime-evidence",
                "--require-readback",
                "--require-observability",
                "--require-physical-release",
                "--minimum-runtime-runs",
                "2",
                "--baseline-id",
                baseline_id,
                "--release-id",
                release_id,
                "--release-digest",
                digest,
                "--report",
                str(report_path),
            ]
            with (
                mock.patch.object(
                    startup_matrix.cli,
                    "_runtime_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_ios_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(startup_matrix.cli, "_launcher_handoff", side_effect=handoff),
                mock.patch.object(sys, "argv", argv),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(startup_matrix.main(), 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["required"], 29)
            self.assertEqual(report["executed"], 29)
            self.assertEqual(report["skipped"], 0)
            self.assertEqual(report["failed"], 0)
            prod_component = next(
                case
                for case in report["cases"]
                if case["caseId"] == "component:prod"
            )
            self.assertFalse(prod_component["required"])
            self.assertEqual(prod_component["status"], "expected_fail_closed")

    def test_startup_matrix_status_distinguishes_component_and_release_evidence(
        self,
    ) -> None:
        component = {
            "caseId": "component:alpha",
            "required": True,
            "status": "component_ready",
        }
        self.assertEqual(
            _report_status([component], release_gate=False),
            "component_ready",
        )
        blocked = {
            "caseId": "startup:alpha-local/android",
            "required": True,
            "status": "gate_block",
        }
        self.assertEqual(
            _report_status([component, blocked], release_gate=True),
            "gate_block",
        )
        self.assertEqual(
            _case_counts([component, blocked]),
            {"required": 2, "executed": 1, "skipped": 0, "failed": 0},
        )

    def test_default_component_matrix_requires_non_prod_and_records_prod_boundary(
        self,
    ) -> None:
        digest = "sha256:" + "a" * 64
        defines = {key: "value" for key in startup_matrix.REQUIRED_DEFINES}

        def environment_defines(environment: str) -> dict[str, str]:
            if environment == "prod":
                raise RuntimeError(
                    "test_live target/environment selection is invalid"
                )
            return {**defines, "APP_RUNTIME_ENV": environment}

        def handoff(environment: str, target: str | None = None) -> dict[str, str]:
            self.assertNotEqual(environment, "prod")
            return {
                "target": target or startup_matrix.RUNTIME_TARGETS[environment],
                "entrypoint": "lib/main_prod.dart",
                "dartDefinesDigest": digest,
                "runtimeConfigDigest": digest,
                "effectiveLaunchManifestDigest": digest,
            }

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            argv = [
                "verify_startup_environment_matrix.py",
                "--report",
                str(report_path),
            ]
            with (
                mock.patch.object(
                    startup_matrix.cli,
                    "_runtime_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_ios_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_launcher_handoff",
                    side_effect=handoff,
                ),
                mock.patch.object(sys, "argv", argv),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(startup_matrix.main(), 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(report["packages"]),
                {"alpha", "beta", "gamma", "prod"},
            )
            self.assertEqual(report["status"], "component_ready")
            components = {
                case["environment"]: case
                for case in report["cases"]
                if case["kind"] == "component_readiness"
            }
            for environment in ("alpha", "beta", "gamma"):
                self.assertTrue(components[environment]["required"])
                self.assertEqual(
                    components[environment]["status"],
                    "component_ready",
                )
            self.assertFalse(components["prod"]["required"])
            self.assertEqual(
                components["prod"]["status"],
                "expected_fail_closed",
            )
            self.assertFalse(components["prod"]["componentEligible"])
            self.assertFalse(components["prod"]["promotionEligible"])
            self.assertEqual(
                components["prod"]["reason"],
                "test_live target/environment selection is invalid",
            )
            self.assertEqual(report["packages"]["prod"]["dartDefinesDigest"], "")
            self.assertEqual(
                report["packages"]["prod"]["effectiveLaunchManifestDigest"],
                "",
            )

    def test_prod_component_boundary_fails_if_test_live_is_accepted(self) -> None:
        defines = {
            **{key: "value" for key in startup_matrix.REQUIRED_DEFINES},
            "APP_RUNTIME_ENV": "prod",
        }
        argv = [
            "verify_startup_environment_matrix.py",
            "--component-environment",
            "prod",
        ]
        output = io.StringIO()
        with (
            mock.patch.object(
                startup_matrix.cli,
                "_runtime_defines",
                return_value=defines,
            ),
            mock.patch.object(sys, "argv", argv),
            redirect_stdout(output),
        ):
            self.assertEqual(startup_matrix.main(), 1)

        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "failed")
        prod_component = report["cases"][0]
        self.assertTrue(prod_component["required"])
        self.assertEqual(prod_component["status"], "failed")
        self.assertEqual(
            prod_component["issues"],
            ["prod: test_live was unexpectedly accepted"],
        )

    def test_release_gate_keeps_missing_prod_physical_evidence_blocking(self) -> None:
        digest = "sha256:" + "f" * 64
        defines = {key: "value" for key in startup_matrix.REQUIRED_DEFINES}

        def environment_defines(environment: str) -> dict[str, str]:
            if environment == "prod":
                raise RuntimeError(
                    "test_live target/environment selection is invalid"
                )
            return {**defines, "APP_RUNTIME_ENV": environment}

        def handoff(environment: str, target: str | None = None) -> dict[str, str]:
            return {
                "target": target or startup_matrix.RUNTIME_TARGETS[environment],
                "entrypoint": "lib/main_prod.dart",
                "dartDefinesDigest": digest,
                "runtimeConfigDigest": digest,
                "effectiveLaunchManifestDigest": digest,
            }

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            argv = [
                "verify_startup_environment_matrix.py",
                "--evidence-root",
                str(Path(directory) / "evidence"),
                "--require-runtime-evidence",
                "--require-readback",
                "--require-observability",
                "--require-physical-release",
                "--baseline-id",
                "baseline-001",
                "--release-id",
                "release-001",
                "--release-digest",
                digest,
                "--report",
                str(report_path),
            ]
            with (
                mock.patch.object(
                    startup_matrix.cli,
                    "_runtime_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_ios_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_launcher_handoff",
                    side_effect=handoff,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "RUNTIME_CASES",
                    (("prod", "prod-hosted"),),
                ),
                mock.patch.object(sys, "argv", argv),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(startup_matrix.main(), 2)

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "gate_block")
            prod_component = next(
                case
                for case in report["cases"]
                if case["caseId"] == "component:prod"
            )
            self.assertFalse(prod_component["required"])
            self.assertEqual(prod_component["status"], "expected_fail_closed")
            blocked_prod_cases = {
                case["caseId"]
                for case in report["cases"]
                if case["required"] and case["status"] == "gate_block"
            }
            self.assertIn(
                "startup:prod-hosted/android-physical",
                blocked_prod_cases,
            )
            self.assertIn(
                "startup:prod-hosted/ios-physical",
                blocked_prod_cases,
            )

    def test_partial_release_evidence_request_is_gate_blocked(self) -> None:
        digest = "sha256:" + "e" * 64
        defines = {key: "value" for key in startup_matrix.REQUIRED_DEFINES}

        def environment_defines(environment: str) -> dict[str, str]:
            if environment == "prod":
                raise RuntimeError(
                    "test_live target/environment selection is invalid"
                )
            return {**defines, "APP_RUNTIME_ENV": environment}

        def handoff(environment: str, target: str | None = None) -> dict[str, str]:
            return {
                "target": target or startup_matrix.RUNTIME_TARGETS[environment],
                "entrypoint": "lib/main_prod.dart",
                "dartDefinesDigest": digest,
                "runtimeConfigDigest": digest,
                "effectiveLaunchManifestDigest": digest,
            }

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            argv = [
                "verify_startup_environment_matrix.py",
                "--evidence-root",
                str(Path(directory) / "evidence"),
                "--require-runtime-evidence",
                "--require-physical-release",
                "--baseline-id",
                "baseline-001",
                "--release-id",
                "release-001",
                "--release-digest",
                digest,
                "--report",
                str(report_path),
            ]
            with (
                mock.patch.object(
                    startup_matrix.cli,
                    "_runtime_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_ios_defines",
                    side_effect=environment_defines,
                ),
                mock.patch.object(
                    startup_matrix.cli,
                    "_launcher_handoff",
                    side_effect=handoff,
                ),
                mock.patch.object(sys, "argv", argv),
                mock.patch("builtins.print"),
            ):
                self.assertEqual(startup_matrix.main(), 2)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "gate_block")
            blocked_ids = {
                case["caseId"]
                for case in report["cases"]
                if case["status"] == "gate_block"
            }
            self.assertIn("matrix-policy:app-core-readback", blocked_ids)
            self.assertIn("matrix-policy:observability-readback", blocked_ids)

    def test_required_startup_uat_has_no_dynamic_skip_and_make_is_candidate_bound(
        self,
    ) -> None:
        web_uat = (
            APP_DIR
            / "test/user_acceptance/journeys/app_startup/"
            "startup_web_3s_6s_report__user_acceptance_test.dart"
        ).read_text(encoding="utf-8")
        self.assertNotIn("skip:", web_uat)

        makefile = (APP_DIR.parent / "Makefile").read_text(encoding="utf-8")
        for target in (
            "verify-app-startup-environment-uat:",
            "verify-app-startup-observability-release:",
        ):
            start = makefile.index(target)
            next_target = makefile.find("\nverify-", start + len(target))
            block = makefile[start : next_target if next_target >= 0 else None]
            for token in (
                "GATE_BLOCK: STARTUP_EVIDENCE_ROOT is required",
                "GATE_BLOCK: STARTUP_BASELINE_ID is required",
                "GATE_BLOCK: STARTUP_RELEASE_ID is required",
                "GATE_BLOCK: STARTUP_RELEASE_DIGEST is required",
                "--require-runtime-evidence",
                "--require-readback",
                "--require-observability",
                "--require-physical-release",
                '--baseline-id "$(STARTUP_BASELINE_ID)"',
                '--release-id "$(STARTUP_RELEASE_ID)"',
                '--release-digest "$(STARTUP_RELEASE_DIGEST)"',
            ):
                self.assertIn(token, block, msg=f"{target} missing {token}")


if __name__ == "__main__":
    unittest.main()
