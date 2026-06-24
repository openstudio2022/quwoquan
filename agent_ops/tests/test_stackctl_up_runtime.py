from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_ops.deploy import stackctl
from agent_ops.deploy.probes import run_environment_integration_probe as integration_probe
from quwoquan_app.scripts.gamma import run_local_gamma_t3 as local_gamma_t3


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_parser_accepts_report_dir_after_subcommand(self) -> None:
        parser = stackctl.build_parser()
        cases = [
            ["package", "--env", "alpha", "--report-dir", "artifacts/stackctl/alpha/package"],
            [
                "verify",
                "--env",
                "alpha",
                "--target",
                "alpha-local",
                "--kind",
                "all",
                "--tier",
                "t1",
                "--report-dir",
                "artifacts/stackctl/alpha/verify",
            ],
            ["up", "--target", "alpha-local", "--report-dir", "artifacts/stackctl/alpha/up"],
            [
                "health",
                "--target",
                "alpha-local",
                "--scope",
                "full",
                "--report-dir",
                "artifacts/stackctl/alpha/health",
            ],
            [
                "inspect",
                "--target",
                "alpha-local",
                "--scope",
                "all",
                "--report-dir",
                "artifacts/stackctl/alpha/inspect",
            ],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertTrue(getattr(args, "report_dir", "").startswith("artifacts/stackctl/"))

    def test_parser_keeps_global_report_dir_before_subcommand(self) -> None:
        parser = stackctl.build_parser()
        args = parser.parse_args(
            ["--report-dir", "artifacts/stackctl/alpha/global", "package", "--env", "alpha"]
        )
        self.assertEqual(args.report_dir, "artifacts/stackctl/alpha/global")

    def test_format_stage_header(self) -> None:
        self.assertEqual(stackctl._format_stage_header(2, 3, "app-launch"), "[step 2/3] app-launch")

    def test_is_interactive_terminal_false_when_stdout_not_tty(self) -> None:
        with (
            mock.patch("sys.stdout.isatty", return_value=False),
            mock.patch("sys.stderr.isatty", return_value=True),
        ):
            self.assertFalse(stackctl._is_interactive_terminal())

    def test_tail_file_for_startup_skips_non_interactive(self) -> None:
        with mock.patch("agent_ops.deploy.stackctl._is_interactive_terminal", return_value=False):
            result = stackctl._tail_file_for_startup(Path("/tmp/does-not-matter.log"))
        self.assertEqual(result["followed"], False)
        self.assertEqual(result["reason"], "log-not-created")

    def test_tail_file_for_startup_reads_existing_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "app.log"
            log_path.write_text("line one\nline two\n", encoding="utf-8")
            with (
                mock.patch("agent_ops.deploy.stackctl._is_interactive_terminal", return_value=True),
                mock.patch("sys.stdout", new=io.StringIO()) as fake_stdout,
            ):
                result = stackctl._tail_file_for_startup(
                    log_path,
                    process=None,
                    idle_timeout_seconds=0.01,
                    max_follow_seconds=0.05,
                )
            self.assertTrue(result["followed"])
            self.assertGreaterEqual(result["lines"], 2)
            self.assertIn("line one", fake_stdout.getvalue())

    def test_tail_file_for_startup_marks_ready_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "app.log"
            log_path.write_text(
                "Launching lib/main.dart on iPhone...\n"
                "Syncing files to device iPhone...\n",
                encoding="utf-8",
            )
            with (
                mock.patch("agent_ops.deploy.stackctl._is_interactive_terminal", return_value=True),
                mock.patch("sys.stdout", new=io.StringIO()),
            ):
                result = stackctl._tail_file_for_startup(
                    log_path,
                    process=None,
                    idle_timeout_seconds=0.01,
                    max_follow_seconds=0.05,
                    ready_patterns=("Syncing files to device",),
                    ready_idle_timeout_seconds=0.01,
                )
            self.assertTrue(result["readySeen"])

    def test_tail_file_for_startup_reads_ready_in_non_interactive_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "app.log"
            log_path.write_text(
                "Launching lib/main.dart on iPhone...\n"
                "A Dart VM Service on iPhone is available at: http://127.0.0.1:1234/\n",
                encoding="utf-8",
            )
            with mock.patch("agent_ops.deploy.stackctl._is_interactive_terminal", return_value=False):
                result = stackctl._tail_file_for_startup(
                    log_path,
                    process=None,
                    idle_timeout_seconds=0.01,
                    max_follow_seconds=0.05,
                    ready_patterns=("A Dart VM Service",),
                    ready_idle_timeout_seconds=0.01,
                )
            self.assertTrue(result["followed"])
            self.assertTrue(result["readySeen"])

    def test_tail_file_for_startup_waits_until_timeout_before_ready(self) -> None:
        class _RunningProcess:
            def poll(self) -> None:
                return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "app.log"
            log_path.write_text(
                "Launching lib/main.dart on iPhone...\n"
                "Running Xcode build...\n",
                encoding="utf-8",
            )
            with mock.patch("agent_ops.deploy.stackctl._is_interactive_terminal", return_value=False):
                result = stackctl._tail_file_for_startup(
                    log_path,
                    process=_RunningProcess(),
                    idle_timeout_seconds=0.01,
                    max_follow_seconds=0.05,
                    ready_patterns=("A Dart VM Service",),
                    ready_idle_timeout_seconds=0.01,
                )
            self.assertEqual(result["reason"], "timeout")
            self.assertFalse(result["readySeen"])

    def test_app_launch_failure_detail_requires_ready_signal(self) -> None:
        detail = stackctl._app_launch_failure_detail(
            {
                "failureSeen": False,
                "readySeen": False,
                "reason": "idle",
            },
            default_message="alpha app launch failed",
            process_exit_code=None,
        )
        self.assertEqual(
            detail,
            "alpha app launch failed: app did not reach Flutter ready state before idle",
        )

    def test_app_launch_failure_detail_accepts_ready_process(self) -> None:
        detail = stackctl._app_launch_failure_detail(
            {
                "failureSeen": False,
                "readySeen": True,
                "reason": "idle",
            },
            default_message="alpha app launch failed",
            process_exit_code=None,
        )
        self.assertIsNone(detail)

    def test_app_launch_failure_detail_prefers_failure_line(self) -> None:
        detail = stackctl._app_launch_failure_detail(
            {
                "failureSeen": True,
                "failureLine": "Failed to build iOS app",
                "readySeen": False,
                "reason": "process-exited",
            },
            default_message="alpha app launch failed",
            process_exit_code=1,
        )
        self.assertEqual(detail, "Failed to build iOS app")

    def test_run_with_live_output_collects_stdout(self) -> None:
        script = "import sys; print('hello'); print('world')"
        with mock.patch("agent_ops.deploy.stackctl._is_interactive_terminal", return_value=False):
            result = stackctl._run_with_live_output(["python3", "-c", script])
        self.assertEqual(result.returncode, 0)
        self.assertIn("hello", result.stdout)
        self.assertIn("world", result.stdout)

    def test_integration_probe_resolves_test_auth_token_from_env(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"GAMMA_TEST_AUTH_TOKEN": "-starts-with-dash", "TEST_AUTH_TOKEN": ""},
            clear=False,
        ):
            self.assertEqual(
                integration_probe._resolve_test_auth_token("gamma", ""),
                "-starts-with-dash",
            )

    def test_run_environment_integration_probe_passes_token_via_env(self) -> None:
        topology = {"targets": []}
        target = {
            "env": "gamma",
            "publicBases": {
                "api": "http://gamma.example",
                "productOps": "http://ops.example",
            },
        }

        with (
            mock.patch("agent_ops.deploy.stackctl.get_target", return_value=target),
            mock.patch(
                "agent_ops.deploy.stackctl._resolve_test_auth_token",
                return_value="-starts-with-dash",
            ),
            mock.patch(
                "agent_ops.deploy.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
        ):
            stackctl._run_environment_integration_probe(topology, "gamma-local", Path("/tmp/report"))

        kwargs = run_probe.call_args.kwargs
        self.assertNotIn("--test-auth-token", kwargs["argv"])
        self.assertEqual(kwargs["env"]["TEST_AUTH_TOKEN"], "-starts-with-dash")
        self.assertEqual(kwargs["env"]["GAMMA_TEST_AUTH_TOKEN"], "-starts-with-dash")

    def test_local_gamma_t3_resolves_test_auth_token_from_env(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "LOCAL_GAMMA_TEST_AUTH_TOKEN": "",
                "GAMMA_TEST_AUTH_TOKEN": "",
                "TEST_AUTH_TOKEN": "-starts-with-dash",
            },
            clear=False,
        ):
            self.assertEqual(local_gamma_t3.default_test_auth_token(), "-starts-with-dash")

    def test_tail_multiple_logs_for_startup_reads_existing_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_a = Path(tmp_dir) / "a.log"
            log_b = Path(tmp_dir) / "b.log"
            log_a.write_text("a1\n", encoding="utf-8")
            log_b.write_text("b1\nb2\n", encoding="utf-8")
            with (
                mock.patch("agent_ops.deploy.stackctl._is_interactive_terminal", return_value=True),
                mock.patch("sys.stdout", new=io.StringIO()) as fake_stdout,
            ):
                result = stackctl._tail_multiple_logs_for_startup(
                    [("svc-a", log_a), ("svc-b", log_b)],
                    idle_timeout_seconds=0.01,
                    max_follow_seconds=0.05,
                )
            self.assertTrue(result["followed"])
            self.assertEqual(len(result["logs"]), 2)
            self.assertIn("[svc-a] a1", fake_stdout.getvalue())
            self.assertIn("[svc-b] b2", fake_stdout.getvalue())

    def test_doctor_prod_hosted_missing_release_state_is_advisory(self) -> None:
        topology = {
            "targets": {
                "prod-hosted": {
                    "env": "prod",
                    "backend": "ssh-hosted",
                    "portProfile": None,
                    "publicBases": {
                        "api": "https://118.31.239.122:19000",
                        "productOps": "https://118.31.239.122:19010",
                    },
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = mock.Mock(target="prod-hosted", report_dir=tmp_dir)
            health_payload = {
                "exitCode": 0,
                "summary": "stackctl health prod-hosted: 4/4 healthy",
                "details": [],
                "reportDir": "tmp",
            }
            with (
                mock.patch("agent_ops.deploy.stackctl.load_environment_topology", return_value=topology),
                mock.patch("agent_ops.deploy.stackctl.get_target", return_value=topology["targets"]["prod-hosted"]),
                mock.patch("agent_ops.deploy.stackctl.command_health", return_value=health_payload),
                mock.patch("agent_ops.deploy.stackctl._load_release_state", return_value={}),
            ):
                result = stackctl.command_doctor(args)
            self.assertEqual(result["exitCode"], 0)
            self.assertTrue(
                any("prod rollout release-state is missing" in item for item in result["details"])
            )


if __name__ == "__main__":
    unittest.main()
