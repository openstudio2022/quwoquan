"""local_contract：三环境固定候选门禁矩阵。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


class LocalEnvGateMatrixContractTest(unittest.TestCase):
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

    def test_matrix_orchestrator_is_serial_package_bound_and_full(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import run_local_env_gate_matrix

        calls: list[str] = []

        def _ok(name: str):
            def _fn(args):
                calls.append(f"{name}:{getattr(args, 'env', '')}:{getattr(args, 'target', '')}:{getattr(args, 'command', '')}")
                if name == "verify":
                    self.assertFalse(hasattr(args, "reuse_package"))
                if name == "up":
                    self.assertEqual(args.workload, "full")
                    self.assertTrue(args.skip_build)
                return {
                    "exitCode": 0,
                    "summary": f"{name} ok",
                    "details": [],
                    "reportDir": f"runs/{name}",
                }

            return _fn

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
                targets=("alpha-local", "beta-local", "gamma-local"),
                include_l0=True,
            )
        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(payload["claim"], "ALPHA_BETA_GAMMA_LOCAL_GREEN")
        self.assertGreater(payload["executed"], 0)
        self.assertEqual(payload["skipped"], 0)
        self.assertLessEqual(payload["wallClockSeconds"], 600)
        # Serial order: the same package/up/health/verify/down state machine for A/B/G.
        package_envs = [
            c.split(":")[1] for c in calls if c.startswith("package:")
        ]
        self.assertEqual(package_envs, ["alpha", "beta", "gamma"])
        timing_path = ROOT / payload["reportDir"] / "timing.json"
        self.assertTrue(timing_path.is_file(), timing_path)
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        self.assertEqual(timing["cacheMode"], "package-bound")
        self.assertFalse(timing["overHardBudget"])
        matrix = json.loads(
            (ROOT / payload["reportDir"] / "matrix.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(matrix["schema"], "quwoquan.test.case-result")
        phase_names = [p["name"] for p in timing["phases"]]
        self.assertIn("L0_commit_gate", phase_names)
        self.assertIn("gamma-local_up", phase_names)
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
            svc_dir = tmp_path / "svc"
            svc_dir.mkdir()
            (svc_dir / "marker").write_text("ok", encoding="utf-8")
            shared_dir = tmp_path / "runtime-shared"
            shared_dir.mkdir()
            (shared_dir / "marker").write_text("ok", encoding="utf-8")
            legal_dir = tmp_path / "legal-static"
            legal_dir.mkdir()
            (legal_dir / "marker").write_text("ok", encoding="utf-8")
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
                return_value={
                    "target": "alpha-local",
                    "baselineId": f"sha256:{'b' * 64}",
                },
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
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                ok, detail = can_reuse_package(
                    "alpha", "alpha-local", include_services=True
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
