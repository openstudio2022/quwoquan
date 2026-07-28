"""local_contract：四环境门禁矩阵预算、编排与加速短路。"""
from __future__ import annotations

import json
import os
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
                claim="LOCAL_ENV_GATE_GREEN",
                cache_mode="warm",
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "local-env-gate-timing")
        self.assertEqual(payload["wallClockSeconds"], 120.5)
        self.assertFalse(payload["overSoftBudget"])
        self.assertFalse(payload["overHardBudget"])
        self.assertEqual(payload["phases"][0]["name"], "alpha_up")

    def test_matrix_orchestrator_serial_and_reuse_package(self) -> None:
        from quwoquan_ops.cli.lib.local_env_gate_matrix import run_local_env_gate_matrix

        calls: list[str] = []

        def _ok(name: str):
            def _fn(args):
                calls.append(f"{name}:{getattr(args, 'env', '')}:{getattr(args, 'target', '')}:{getattr(args, 'command', '')}")
                if name == "verify":
                    self.assertTrue(getattr(args, "reuse_package", False))
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
            "quwoquan_ops.cli.lib.local_env_gate_matrix.gamma_images_warm",
            return_value=True,
        ), mock.patch(
            "quwoquan_ops.cli.lib.local_env_gate_matrix.beta_images_warm",
            return_value=True,
        ), mock.patch(
            "quwoquan_ops.cli.lib.local_env_gate_matrix.force_cleanup_target",
            return_value={"exitCode": 0, "summary": "down", "reportDir": ""},
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
                include_l0=True,
                cache_mode="warm",
                auto_wipe_drift=True,
            )
        self.assertEqual(payload["exitCode"], 0)
        self.assertEqual(payload["claim"], "LOCAL_ENV_GATE_GREEN")
        self.assertLessEqual(payload["wallClockSeconds"], 600)
        # Serial order: package/up/health/verify for local envs, then prod package/verify.
        package_envs = [
            c.split(":")[1] for c in calls if c.startswith("package:")
        ]
        self.assertEqual(package_envs, ["alpha", "beta", "gamma", "prod"])
        timing_path = ROOT / payload["reportDir"] / "timing.json"
        self.assertTrue(timing_path.is_file(), timing_path)
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
        self.assertEqual(timing["cacheMode"], "warm")
        self.assertFalse(timing["overHardBudget"])
        phase_names = [p["name"] for p in timing["phases"]]
        self.assertIn("L0_commit_gate", phase_names)
        self.assertIn("gamma_up", phase_names)
        self.assertIn("prod_verify_release", phase_names)

    def test_package_reuse_fingerprint(self) -> None:
        from quwoquan_ops.cli.lib.package_reuse import (
            can_reuse_package,
            write_package_fingerprint,
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            app_dir = tmp_path / "app"
            app_dir.mkdir()
            (app_dir / "marker").write_text("ok", encoding="utf-8")
            svc_dir = tmp_path / "svc"
            svc_dir.mkdir()
            with mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.app_deployment_package_dir",
                return_value=app_dir,
            ), mock.patch(
                "quwoquan_ops.cli.lib.package_reuse.service_deployment_package_dir",
                return_value=svc_dir,
            ):
                write_package_fingerprint(
                    "alpha",
                    "alpha-local",
                    report_dir="runs/pkg",
                    include_services=True,
                    details=["ready"],
                )
                ok, detail = can_reuse_package(
                    "alpha", "alpha-local", include_services=True
                )
                self.assertTrue(ok, detail)

    def test_force_release_skips_docker_proxy_listeners(self) -> None:
        from quwoquan_ops.cli.lib import local_env_gate_matrix as matrix_mod

        fake_lsof = (
            "COMMAND     PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
            "docker-proxy 111 user   4u  IPv4 1      0t0  TCP *:17220 (LISTEN)\n"
            "Python       222 user   4u  IPv4 2      0t0  TCP 127.0.0.1:17220 (LISTEN)\n"
        )
        with mock.patch.object(
            matrix_mod.subprocess,
            "run",
            side_effect=[
                mock.Mock(returncode=0, stdout=fake_lsof, stderr=""),
                mock.Mock(returncode=0, stdout="", stderr=""),
                mock.Mock(returncode=0, stdout="COMMAND PID\n", stderr=""),
            ],
        ) as run:
            pids = matrix_mod._host_listener_pids(17220)
            self.assertEqual(pids, ["222"])
            # ensure kill path would only target host Python, never docker-proxy
            matrix_mod.subprocess.run(["kill", "-TERM", *pids], check=False)
            kill_calls = [
                call.args[0]
                for call in run.call_args_list
                if call.args and call.args[0][:1] == ["kill"]
            ]
            self.assertTrue(any(call == ["kill", "-TERM", "222"] for call in kill_calls))

    def test_force_cleanup_cannot_bypass_active_consumer_lease(self) -> None:
        from quwoquan_ops.cli.lib import local_env_gate_matrix as matrix_mod

        down_payload = {
            "exitCode": 2,
            "reason": "active_consumer_lease",
            "summary": "stackctl down is GATE_BLOCK for alpha-local",
            "details": ["active consumer lease: device=ELS-AN00"],
        }
        down = mock.Mock(return_value=down_payload)
        with mock.patch.object(
            matrix_mod,
            "_clear_stale_operation_lock",
            return_value=[],
        ), mock.patch.object(
            matrix_mod,
            "_force_release_target_ports",
        ) as release_ports:
            payload = matrix_mod.force_cleanup_target(
                "alpha-local",
                down_fn=down,
            )

        self.assertEqual(payload["reason"], "active_consumer_lease")
        down.assert_called_once()
        release_ports.assert_not_called()

    def test_stackctl_skip_nested_up_short_circuits_profile_up(self) -> None:
        from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
        from quwoquan_ops.cli import stackctl as stackctl_mod

        with mock.patch.dict(os.environ, {"STACKCTL_SKIP_NESTED_UP": "1"}, clear=False):
            commands = stackctl_mod._selected_profile_commands(
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
            )
        names = [item["name"] for item in commands]
        self.assertIn("beta-local-health-preflight", names)
        self.assertNotIn("beta-local-up", names)

    def test_start_script_has_reuse_data_plane_watermark(self) -> None:
        script = (
            ROOT
            / "quwoquan_app"
            / "scripts"
            / "gamma"
            / "start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("LOCAL_GAMMA_REUSE_DATA_PLANE", script)
        self.assertIn("data-plane-watermark.json", script)
        self.assertIn("maybe_reuse_local_gamma_data_plane", script)
        self.assertIn("write_local_gamma_data_plane_watermark", script)

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


if __name__ == "__main__":
    unittest.main()
