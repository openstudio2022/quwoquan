"""local_contract：三环境固定候选门禁矩阵。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]


class LocalEnvGateMatrixContractTest(unittest.TestCase):
    def test_integration_matrix_accepts_only_current_test_data_case_result(self) -> None:
        from quwoquan_ops.cli.lib import local_env_gate_matrix as matrix_mod

        with tempfile.TemporaryDirectory() as temporary:
            report_dir = Path(temporary)
            (report_dir / "report.json").write_text(
                json.dumps(
                    {
                        "profile": "integration",
                        "status": "ok",
                        "steps": [
                            {
                                "kind": "test-data",
                                "caseResult": {
                                    "status": "passed",
                                    "executed": 1,
                                    "skipped": 0,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(
                matrix_mod._integration_verify_has_required_test_data_case(
                    {"reportDir": str(report_dir)}
                )
            )

            retired = json.loads(
                (report_dir / "report.json").read_text(encoding="utf-8")
            )
            retired["steps"][0]["kind"] = "nonprod-business-data"
            (report_dir / "report.json").write_text(
                json.dumps(retired),
                encoding="utf-8",
            )
            self.assertFalse(
                matrix_mod._integration_verify_has_required_test_data_case(
                    {"reportDir": str(report_dir)}
                )
            )

    def test_emulator_only_profile_is_explicitly_non_promotable(self) -> None:
        from quwoquan_ops.cli.lib import local_env_gate_matrix as matrix_mod

        bindings = matrix_mod._device_uat_bindings(
            device_profile=matrix_mod.DEVICE_PROFILE_EMULATOR_ONLY,
            ios_simulator_device="ios-simulator-udid",
            android_emulator_device="emulator-5554",
            android_physical_device="",
        )
        self.assertEqual(
            tuple(key for key, _, _ in bindings),
            ("iosSimulatorUAT", "androidEmulatorUAT"),
        )

        with tempfile.TemporaryDirectory() as temporary:
            matrix_dir = Path(temporary)
            with mock.patch.object(
                matrix_mod,
                "write_timing_bundle",
                return_value=matrix_dir / "timing.json",
            ):
                result = matrix_mod._write_matrix_result(
                    matrix_dir=matrix_dir,
                    phases=[{"name": "matrix", "status": "passed"}],
                    environments={
                        target: {}
                        for target in matrix_mod.CANONICAL_TARGETS
                    },
                    budgets={
                        "softBudgetSeconds": 600,
                        "hardBudgetSeconds": 1800,
                    },
                    wall_seconds=1.0,
                    exit_code=0,
                    failure_category="",
                    baseline_id=f"sha256:{'a' * 64}",
                    release={
                        "releaseId": "release-emulator-only",
                        "releaseDigest": f"sha256:{'b' * 64}",
                    },
                    matrix_run_id="matrix-emulator-only",
                    execution_class="live",
                    device_profile=matrix_mod.DEVICE_PROFILE_EMULATOR_ONLY,
                )
            payload = json.loads(
                (matrix_dir / "matrix.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["claim"], matrix_mod.EMULATOR_ONLY_CLAIM)
        self.assertEqual(payload["schema"], "quwoquan.test.case-result")
        self.assertTrue(payload["nonPromotable"])
        self.assertEqual(
            payload["deviceCoverage"],
            ["ios-simulator", "android-emulator"],
        )
        self.assertEqual(
            payload["waivers"][0]["effect"],
            "release-promotion-blocked",
        )

    def test_provider_phase_requires_explicit_local_functional_scope(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import (
            _provider_local_functional_errors,
        )

        cells = [
            {
                "capabilityId": f"fixture.capability_{index:02d}",
                "adapterId": f"ext.fixture.adapter_{index:02d}",
                "layer": layer,
                "exitCode": 0,
            }
            for index in range(14)
            for layer in (
                "local_contract",
                "api_integration",
                "user_acceptance",
            )
        ]
        payload = {
            "schema": "stackctl-provider-conformance-environment-matrix",
            "readinessScope": "local_functional",
            "releasePromotionClaimed": False,
            "status": "passed",
            "environment": "alpha",
            "target": "alpha-local",
            "capabilityCount": 14,
            "expectedCells": 42,
            "executed": 42,
            "skipped": 0,
            "attemptEvidenceCount": 42,
            "exitCode": 0,
            "issues": [],
            "cells": cells,
        }
        compiled = {
            "providerConformanceCapabilityIds": [
                f"fixture.capability_{index:02d}" for index in range(14)
            ]
        }

        self.assertEqual(
            _provider_local_functional_errors(
                payload,
                environment="alpha",
                target="alpha-local",
                compiled_provider_governance=compiled,
            ),
            [],
        )
        promoted = {**payload, "releasePromotionClaimed": True}
        self.assertTrue(
            any(
                "releasePromotionClaimed" in issue
                for issue in _provider_local_functional_errors(
                    promoted,
                    environment="alpha",
                    target="alpha-local",
                    compiled_provider_governance=compiled,
                )
            )
        )
        duplicate = {**payload, "cells": [*cells[:-1], cells[0]]}
        self.assertTrue(
            any(
                "every compiled capability" in issue
                for issue in _provider_local_functional_errors(
                    duplicate,
                    environment="alpha",
                    target="alpha-local",
                    compiled_provider_governance=compiled,
                )
            )
        )

        extended_capability = "fixture.capability_14"
        extended_cells = [
            *cells,
            *[
                {
                    "capabilityId": extended_capability,
                    "adapterId": "ext.fixture.adapter_14",
                    "layer": layer,
                    "exitCode": 0,
                }
                for layer in (
                    "local_contract",
                    "api_integration",
                    "user_acceptance",
                )
            ],
        ]
        extended = {
            **payload,
            "capabilityCount": 15,
            "expectedCells": 45,
            "executed": 45,
            "attemptEvidenceCount": 45,
            "cells": extended_cells,
        }
        self.assertEqual(
            _provider_local_functional_errors(
                extended,
                environment="alpha",
                target="alpha-local",
                compiled_provider_governance={
                    "providerConformanceCapabilityIds": [
                        *compiled["providerConformanceCapabilityIds"],
                        extended_capability,
                    ]
                },
            ),
            [],
        )

    def test_stackctl_up_rejects_env_and_target_before_locking(self) -> None:
        from quwoquan_ops.cli import stackctl as stackctl_mod

        with mock.patch.object(
            stackctl_mod,
            "_local_stack_operation_lock",
        ) as operation_lock:
            payload = stackctl_mod.command_up(
                SimpleNamespace(env="beta", target="beta-local")
            )

        self.assertEqual(payload["exitCode"], 2)
        self.assertIn(
            "provide exactly one of --env or --target",
            payload["details"],
        )
        operation_lock.assert_not_called()

    def test_live_evidence_requires_package_bound_provider_runtime(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import (
            _live_matrix_evidence_errors,
        )

        baseline_id = f"sha256:{'a' * 64}"
        environments = {
            target: {
                "target": target,
                "environment": environment,
                "package": {
                    "baselineId": baseline_id,
                    "packageDigest": f"sha256:{'b' * 64}",
                    "imageDigest": f"sha256:{'c' * 64}",
                    "observabilityLogSink": {
                        "adapterId": "ext.obs.elasticsearch",
                        "deploymentMode": "package-bound-local",
                    },
                },
            }
            for target, environment in {
                "alpha-local": "alpha",
                "beta-local": "beta",
                "gamma-local": "gamma",
            }.items()
        }

        errors = _live_matrix_evidence_errors(
            environments,
            baseline_id=baseline_id,
        )

        self.assertEqual(
            len(
                [
                    error
                    for error in errors
                    if "package-bound Provider runtime is incomplete" in error
                ]
            ),
            3,
        )

    def test_live_evidence_rejects_cross_target_baseline_drift(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import (
            _live_matrix_evidence_errors,
        )

        baseline_id = f"sha256:{'a' * 64}"
        drifted_baseline_id = f"sha256:{'d' * 64}"
        environments = {
            target: {
                "target": target,
                "environment": environment,
                "package": {
                    "baselineId": (
                        drifted_baseline_id
                        if target == "beta-local"
                        else baseline_id
                    ),
                    "packageDigest": f"sha256:{'b' * 64}",
                    "imageDigest": f"sha256:{'c' * 64}",
                    "observabilityLogSink": {
                        "adapterId": "ext.obs.elasticsearch",
                        "deploymentMode": "package-bound-local",
                    },
                    "providerRuntime": {
                        "composition": {
                            "runtimeCompositionDigest": f"sha256:{'e' * 64}",
                            "workloads": [],
                        }
                    },
                },
            }
            for target, environment in {
                "alpha-local": "alpha",
                "beta-local": "beta",
                "gamma-local": "gamma",
            }.items()
        }

        errors = _live_matrix_evidence_errors(
            environments,
            baseline_id=baseline_id,
        )

        self.assertIn(
            "beta-local: package baselineId is missing or drifted",
            errors,
        )

    def test_timing_budget_gate_exists(self) -> None:
        budgets = json.loads(
            (
                ROOT
                / "quwoquan_ops"
                / "environments"
                / "pr_gate_timing_budgets.json"
            ).read_text(encoding="utf-8")
        )
        gate = budgets["gates"]["01.local_env_matrix"]
        self.assertEqual(gate["budgetSeconds"], 600)
        self.assertEqual(gate["hardFailSeconds"], 1800)
        self.assertIn("gamma_pkg_up_verify_warm", gate["phaseBudgetsSeconds"])

    def test_phase_timer_and_timing_bundle_fields(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_timing import (
            PhaseTimer,
            load_local_env_matrix_budgets,
            write_timing_bundle,
        )

        budgets = load_local_env_matrix_budgets()
        self.assertEqual(budgets["softBudgetSeconds"], 600)
        self.assertEqual(budgets["hardBudgetSeconds"], 1800)
        phase = PhaseTimer("alpha_up").finish(status="ok", details=["demo"])
        with tempfile.TemporaryDirectory() as tmp:
            path = write_timing_bundle(
                Path(tmp),
                phases=[phase],
                wall_clock_seconds=120.5,
                budgets=budgets,
                claim="ALPHA_BETA_GAMMA_LOCAL_GREEN",
                cache_mode="package-bound",
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "local-env-gate-timing")
        self.assertEqual(payload["wallClockSeconds"], 120.5)
        self.assertFalse(payload["overSoftBudget"])
        self.assertFalse(payload["overHardBudget"])
        self.assertEqual(payload["phases"][0]["name"], "alpha_up")

    def test_matrix_orchestrator_is_serial_package_bound_full_integration(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import run_local_env_gate_matrix

        calls: list[str] = []

        def _ok(name: str):
            def _fn(args):
                calls.append(f"{name}:{getattr(args, 'env', '')}:{getattr(args, 'target', '')}:{getattr(args, 'command', '')}")
                if name == "verify":
                    self.assertFalse(hasattr(args, "reuse_package"))
                    self.assertEqual(args.profile, "integration")
                    self.assertEqual(args.test_data_request, "")
                    self.assertEqual(args.test_data_evidence, "")
                if name == "up":
                    self.assertEqual(args.workload, "full")
                    self.assertTrue(args.skip_build)
                if name == "health":
                    self.assertEqual(args.scope, "full")
                payload = {
                    "exitCode": 0,
                    "summary": f"{name} ok",
                    "details": [],
                    "reportDir": f"runs/{name}",
                }
                if name == "package":
                    payload["baselineId"] = f"sha256:{'c' * 64}"
                return payload

            return _fn

        def _data_ok(**kwargs):
            calls.append(
                f"data:{kwargs['environment']}:{kwargs['action']}:"
                f"{Path(kwargs['report_path']).name}"
            )
            payload = {
                "exitCode": 0,
                "summary": f"{kwargs['action']} ok",
                "details": [],
                "reportDir": str(Path(kwargs["report_path"]).parent),
            }
            if kwargs["action"].startswith("acceptance-lease-"):
                action = kwargs["action"].removeprefix("acceptance-lease-")
                argv = kwargs["argv"]
                payload["payload"] = {
                    "schema": "quwoquan_data.release_acceptance_lease_event",
                    "action": action,
                    "environment": kwargs["environment"],
                    "releaseId": argv[argv.index("--release-id") + 1],
                    "leaseId": argv[argv.index("--lease-id") + 1],
                    "eventRef": f"receipt:{kwargs['environment']}:{action}",
                }
            return payload

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        temporary_root = Path(temporary.name)
        candidate_attestation = temporary_root / "candidate.json"
        rollback_attestation = temporary_root / "rollback.json"
        candidate_attestation.write_text(
            json.dumps(
                {
                    "schema": "quwoquan_data.release_attestation",
                    "releaseId": "candidate-release",
                    "payloadSha256": f"sha256:{'a' * 64}",
                }
            ),
            encoding="utf-8",
        )
        rollback_attestation.write_text(
            json.dumps(
                {
                    "schema": "quwoquan_data.release_attestation",
                    "releaseId": "rollback-release",
                    "payloadSha256": f"sha256:{'b' * 64}",
                }
            ),
            encoding="utf-8",
        )

        with mock.patch(
            "quwoquan_ops.cli.lib.local_env_gate_matrix._run_commit_gate",
            return_value={
                "exitCode": 0,
                "durationMs": 10,
                "summary": {},
                "stdout": "",
                "stderr": "",
                "reportDir": "runs/commit-gate",
            },
        ), mock.patch(
            "quwoquan_ops.cli.lib.local_env_gate_matrix.probe_migration_drift",
        ) as drift_probe, mock.patch(
            "quwoquan_ops.cli.lib.local_env_gate_matrix.subprocess.run",
            return_value=mock.Mock(returncode=0, stdout="", stderr=""),
        ):
            from quwoquan_ops.cli.lib.local_postgres_migration_drift import (
                MigrationDriftProbeResult,
            )

            drift_probe.return_value = MigrationDriftProbeResult(
                status="unavailable",
                target="alpha-local",
                container="",
                findings=(),
                detail="not present",
            )
            payload = run_local_env_gate_matrix(
                package_fn=_ok("package"),
                up_fn=_ok("up"),
                health_fn=_ok("health"),
                verify_fn=_ok("verify"),
                down_fn=_ok("down"),
                filter_catalog_fn=_ok("filter-catalog"),
                targets=("alpha-local", "beta-local", "gamma-local"),
                include_l0=True,
                release_attestation=str(candidate_attestation),
                rollback_release_attestation=str(rollback_attestation),
                data_fn=_data_ok,
                execution_class="contract-simulation",
            )
        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(payload["claim"], "CONTRACT_SIMULATION_PASSED")
        self.assertGreater(payload["executed"], 0)
        self.assertEqual(payload["skipped"], 0)
        self.assertLessEqual(payload["wallClockSeconds"], 600)
        # Serial order: the same package/up/health/verify/down state machine for A/B/G.
        package_envs = [
            c.split(":")[1] for c in calls if c.startswith("package:")
        ]
        self.assertEqual(package_envs, ["alpha", "beta", "gamma"])
        data_actions = [
            c.split(":")[2] for c in calls if c.startswith("data:")
        ]
        self.assertEqual(
            data_actions,
            [
                action
                for _environment in ("alpha", "beta", "gamma")
                for action in (
                    "candidate-apply",
                    "candidate-verify",
                    "rollback-apply",
                    "rollback-verify",
                    "replay-apply",
                    "replay-verify",
                    "lifecycle-exit",
                    "acceptance-lease-acquire",
                    "acceptance-lease-revoke",
                )
            ],
        )
        timing_path = ROOT / payload["reportDir"] / "timing.json"
        self.assertTrue(timing_path.is_file(), timing_path)
        self.assertTrue(Path(payload["reportDir"]).name.startswith("matrix-"))
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        self.assertEqual(timing["cacheMode"], "package-bound")
        self.assertFalse(timing["overHardBudget"])
        matrix = json.loads(
            (ROOT / payload["reportDir"] / "matrix.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(matrix["schema"], "quwoquan.test.case-result")
        self.assertEqual(matrix["executionClass"], "contract-simulation")
        self.assertNotEqual(matrix["claim"], "ALPHA_BETA_GAMMA_LOCAL_GREEN")
        phase_names = [p["name"] for p in timing["phases"]]
        self.assertIn("L0_commit_gate", phase_names)
        self.assertIn("gamma-local_up", phase_names)
        self.assertIn("gamma-local_data_candidate_verify", phase_names)
        self.assertIn("gamma-local_full_integration_verify", phase_names)
        self.assertIn("gamma-local_data_lifecycle_exit", phase_names)
        self.assertIn("gamma-local_acceptance_lease_acquire", phase_names)
        self.assertIn("gamma-local_acceptance_lease_revoke", phase_names)
        self.assertNotIn("prod_verify_release", phase_names)

    def test_package_reuse_fingerprint(self) -> None:
        from quwoquan_ops.cli.lib.package_reuse import (
            can_reuse_package,
            write_package_fingerprint,
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            candidate_dir = tmp_path / "candidate"
            app_dir = candidate_dir / "packages/app"
            app_dir.mkdir(parents=True)
            (app_dir / "marker").write_text("ok", encoding="utf-8")
            svc_dir = candidate_dir / "packages/services/content-service"
            svc_dir.mkdir(parents=True)
            (svc_dir / "marker").write_text("ok", encoding="utf-8")
            shared_dir = candidate_dir / "packages/runtime-shared"
            shared_dir.mkdir(parents=True)
            (shared_dir / "marker").write_text("ok", encoding="utf-8")
            legal_dir = candidate_dir / "packages/legal-static"
            legal_dir.mkdir(parents=True)
            (legal_dir / "marker").write_text("ok", encoding="utf-8")

            def verify_capsule(_path, *, expected_snapshot=None):
                if expected_snapshot is not None:
                    return expected_snapshot
                fingerprint = json.loads(
                    (app_dir / "package-fingerprint.json").read_text(
                        encoding="utf-8"
                    )
                )
                deployment_inputs = fingerprint["deploymentInputs"]
                return {
                    "baselineId": fingerprint["baselineId"],
                    "sourceRevision": fingerprint["sourceRevision"],
                    "workspaceStatusDigest": fingerprint[
                        "workspaceStatusDigest"
                    ],
                    "deploymentInputRoots": deployment_inputs["roots"],
                    "deploymentInputDigest": deployment_inputs["digest"],
                    "deploymentInputFileCount": deployment_inputs["fileCount"],
                }

            with mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.app_deployment_package_dir",
                return_value=app_dir,
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.service_deployment_package_dir",
                return_value=svc_dir,
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.runtime_shared_deployment_package_dir",
                return_value=shared_dir,
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.legal_static_deployment_package_dir",
                return_value=legal_dir,
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse._expected_service_packages",
                return_value=["content-service"],
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.deployment_input_digest",
                return_value=(f"sha256:{'a' * 64}", 1),
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.workspace_snapshot",
                return_value={
                    "baselineId": f"sha256:{'b' * 64}",
                    "sourceRevision": "a" * 40,
                    "workspaceStatusDigest": f"sha256:{'c' * 64}",
                    "deploymentInputDigest": f"sha256:{'a' * 64}",
                    "deploymentInputFileCount": 1,
                },
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.active_deployment_candidate",
                side_effect=AssertionError(
                    "explicit candidate reuse must not inspect the active candidate"
                ),
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.verify_package_input_capsule",
                side_effect=verify_capsule,
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.validate_candidate_manifest",
                side_effect=lambda payload, **_kwargs: payload,
            ):
                fingerprint_path = write_package_fingerprint(
                    "alpha",
                    "alpha-local",
                    report_dir="runs/pkg",
                    include_services=True,
                    details=["ready"],
                    release_input_classification="research_inputs",
                    contract_graph_digest=f"sha256:{'d' * 64}",
                    graphql_read_registry={
                        "schema": "stackctl-graphql-read-registry-package",
                        "candidateDigest": f"sha256:{'b' * 64}",
                    },
                )
                fingerprint = json.loads(
                    fingerprint_path.read_text(encoding="utf-8")
                )
                (candidate_dir / "manifest.json").write_text(
                    json.dumps(
                        {
                            "baselineId": fingerprint["baselineId"],
                            "sourceRevision": fingerprint["sourceRevision"],
                            "workspaceStatusDigest": fingerprint[
                                "workspaceStatusDigest"
                            ],
                            "workspaceDigest": fingerprint["deploymentInputs"][
                                "digest"
                            ],
                            "packageDigest": fingerprint["packageContent"][
                                "digest"
                            ],
                            "releaseInputClassification": fingerprint[
                                "releaseInputClassification"
                            ],
                            "contractGraphDigest": fingerprint[
                                "contractGraphDigest"
                            ],
                            "graphqlReadRegistry": fingerprint[
                                "graphqlReadRegistry"
                            ],
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                ok, detail = can_reuse_package(
                    "alpha",
                    "alpha-local",
                    include_services=True,
                    candidate_root=candidate_dir,
                )
                self.assertTrue(ok, detail)

    def test_down_target_uses_only_stackctl_down(self) -> None:
        from quwoquan_ops.cli.lib import local_env_gate_matrix as matrix_mod

        down = mock.Mock(
            return_value={"exitCode": 0, "summary": "down", "details": []}
        )
        payload = matrix_mod._down_target("alpha-local", down_fn=down)
        self.assertEqual(payload["exitCode"], 0)
        down.assert_called_once()
        args = down.call_args.args[0]
        self.assertEqual(args.target, "alpha-local")
        self.assertFalse(args.formal_release_teardown)

    def test_matrix_rejects_target_subset_without_execution(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import run_local_env_gate_matrix

        runner = mock.Mock()
        payload = run_local_env_gate_matrix(
            package_fn=runner,
            up_fn=runner,
            health_fn=runner,
            verify_fn=runner,
            down_fn=runner,
            targets=("alpha-local", "beta-local"),
        )
        self.assertEqual(payload["exitCode"], 2)
        self.assertEqual(payload["claim"], "GATE_BLOCK")
        self.assertEqual(payload["skipped"], 0)
        runner.assert_not_called()

    def test_missing_exit_code_is_gate_block_not_implicit_success(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import _record_phase

        phases: list[dict[str, object]] = []
        exit_code = _record_phase(
            phases,
            name="missing_exit",
            payload={"summary": "ambiguous runner result"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(phases[0]["status"], "gate_block")

    def test_live_matrix_requires_explicit_release_bindings(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import run_local_env_gate_matrix

        runner = mock.Mock()
        payload = run_local_env_gate_matrix(
            package_fn=runner,
            up_fn=runner,
            health_fn=runner,
            verify_fn=runner,
            down_fn=runner,
        )

        self.assertEqual(payload["exitCode"], 2)
        self.assertEqual(payload["claim"], "GATE_BLOCK")
        self.assertIn("release/data inputs", payload["summary"])
        runner.assert_not_called()

    def test_live_matrix_lease_blocks_overlap_and_releases_on_exit(self) -> None:
        from quwoquan_ops.cli.lib import local_env_gate_matrix as matrix_mod

        runner = mock.Mock()
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            candidate = root / "candidate.json"
            rollback = root / "rollback.json"
            candidate.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.release_attestation",
                        "releaseId": "candidate-release",
                        "payloadSha256": f"sha256:{'a' * 64}",
                    }
                ),
                encoding="utf-8",
            )
            rollback.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.release_attestation",
                        "releaseId": "rollback-release",
                        "payloadSha256": f"sha256:{'b' * 64}",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(matrix_mod, "output_root", return_value=root):
                with matrix_mod._matrix_execution_lease("matrix-owner"):
                    payload = matrix_mod.run_local_env_gate_matrix(
                        package_fn=runner,
                        up_fn=runner,
                        health_fn=runner,
                        verify_fn=runner,
                        down_fn=runner,
                        release_attestation=str(candidate),
                        rollback_release_attestation=str(rollback),
                    )

                self.assertEqual(payload["exitCode"], 2)
                self.assertEqual(payload["status"], "gate_block")
                self.assertIn("execution lease", payload["summary"])
                runner.assert_not_called()

                with matrix_mod._matrix_execution_lease("matrix-after-release"):
                    lease = json.loads(
                        matrix_mod._matrix_lease_path().read_text(encoding="utf-8")
                    )
                    self.assertEqual(lease["status"], "active")
                    self.assertEqual(lease["matrixRunId"], "matrix-after-release")

                released = json.loads(
                    matrix_mod._matrix_lease_path().read_text(encoding="utf-8")
                )
                self.assertEqual(released["status"], "released")

    def test_verify_profile_never_performs_nested_up(self) -> None:
        from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
        from quwoquan_ops.cli import stackctl as stackctl_mod

        commands = stackctl_mod._selected_profile_commands(
            "beta",
            "beta-local",
            VerificationProfile.INTEGRATION,
        )
        names = [item["name"] for item in commands]
        self.assertIn("beta-local-health-preflight", names)
        self.assertNotIn("beta-local-up", names)

    def test_start_script_delegates_data_plane_to_immutable_release(self) -> None:
        script = (
            ROOT
            / "quwoquan_app"
            / "scripts"
            / "gamma"
            / "start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "immutable release activation owns business data and search projections",
            script,
        )
        self.assertNotIn("LOCAL_GAMMA_REUSE_DATA_PLANE", script)
        self.assertNotIn("data-plane-watermark.json", script)
        self.assertNotIn("ENABLE_FIXTURE_SEEDS", script)

    def test_alpha_wait_http_early_exits_on_checksum_drift(self) -> None:
        from quwoquan_ops.cli.alpha import content_release_runtime as runtime

        with mock.patch.object(
            runtime,
            "_compose_service_logs_indicate_migration_drift",
            return_value="checksum drift",
        ), mock.patch.object(runtime.time, "monotonic", side_effect=[0, 0.1, 31, 31.5]):
            with mock.patch.object(
                runtime.urllib.request,
                "urlopen",
                side_effect=OSError("down"),
            ):
                with self.assertRaisesRegex(RuntimeError, "migration drift"):
                    runtime._wait_http(
                        "http://127.0.0.1:1/healthz",
                        timeout_seconds=300,
                        compose_service="user-service",
                    )

    def test_alpha_up_checks_public_tls_before_stopping_current_runtime(self) -> None:
        from quwoquan_ops.cli.alpha import content_release_runtime as runtime
        from quwoquan_ops.cli.lib.public_domain_tls import PublicDomainTlsError

        docker_ready = mock.Mock(returncode=0)
        with (
            mock.patch.object(
                runtime.subprocess,
                "run",
                return_value=docker_ready,
            ),
            mock.patch.object(runtime, "assert_local_runtime_available"),
            mock.patch.object(
                runtime,
                "certificate_paths",
                side_effect=PublicDomainTlsError("missing public TLS"),
            ),
            mock.patch.object(runtime, "down") as down,
        ):
            with self.assertRaisesRegex(PublicDomainTlsError, "missing public TLS"):
                runtime.up()

        down.assert_not_called()

    def test_alpha_down_retains_ledger_when_managed_process_survives(self) -> None:
        from quwoquan_ops.cli.alpha import content_release_runtime as runtime

        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            paths = runtime.RuntimePaths(
                process_dir=root / "process",
                media_root=root / "media",
                run_root=root / "run",
                observability_root=root / "observability",
                logs_root=root / "logs",
                config_root=root / "config",
                legal_root=root / "legal",
                caddyfile=root / "Caddyfile",
            )
            paths.process_dir.mkdir(parents=True)
            paths.state_path.write_text(
                json.dumps(
                    {
                        "processes": {
                            "media-origin": {"pid": 101, "pgid": 101}
                        }
                    }
                ),
                encoding="utf-8",
            )
            docker_unavailable = mock.Mock(returncode=1, stdout="", stderr="")
            with (
                mock.patch.object(runtime, "_paths", return_value=paths),
                mock.patch.object(runtime, "_stop_process", return_value=False),
                mock.patch.object(runtime, "_container_exists", return_value=False),
                mock.patch.object(
                    runtime.subprocess, "run", return_value=docker_unavailable
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "managed process groups remain"
                ):
                    runtime.down()

            self.assertTrue(paths.state_path.is_file())

    def test_alpha_orphan_match_requires_target_scoped_wrapper_and_ports(
        self,
    ) -> None:
        from quwoquan_ops.cli.alpha import content_release_runtime as runtime

        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            paths = runtime.RuntimePaths(
                process_dir=root / "process",
                media_root=runtime.ROOT
                / ".qwq_output/env/alpha/local/alpha-local/cache/media",
                run_root=root / "run",
                observability_root=root / "observability",
                logs_root=root / "logs",
                config_root=root / "config",
                legal_root=root / "legal",
                caddyfile=root / "Caddyfile",
            )
            wrapper = runtime.ROOT / "quwoquan_ops/cli/lib/runtime_log_process.py"
            log = (
                runtime.ROOT
                / ".qwq_output/env/alpha/observability/run-1/logs/service/media-edge/local/runtime.log"
            )
            command = (
                f"python3 {wrapper} --log-file {log} --event media-edge -- "
                "python3 quwoquan_ops/cli/lib/http_reverse_proxy.py "
                "--listen-host 0.0.0.0 --listen-port 17120 "
                "--target-base-url http://127.0.0.1:17110"
            )
            ports = {"media-processor": 17120, "media-origin": 17110}

            self.assertTrue(
                runtime._matches_orphaned_wrapper(
                    command, name="media-edge", ports=ports, paths=paths
                )
            )
            self.assertFalse(
                runtime._matches_orphaned_wrapper(
                    command.replace("17120", "18120"),
                    name="media-edge",
                    ports=ports,
                    paths=paths,
                )
            )


if __name__ == "__main__":
    unittest.main()
