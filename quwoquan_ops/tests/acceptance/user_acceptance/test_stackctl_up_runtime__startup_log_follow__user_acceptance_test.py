"""场景：startup 日志跟随与 App 启动信号——交互终端判定、tail ready/timeout
语义、多日志聚合、iOS 冷启动超时下限与 launch failure detail 归因。"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_is_interactive_terminal_false_when_stdout_not_tty(self) -> None:
        with (
            mock.patch("sys.stdout.isatty", return_value=False),
            mock.patch("sys.stderr.isatty", return_value=True),
        ):
            self.assertFalse(stackctl._is_interactive_terminal())

    def test_tail_file_for_startup_skips_non_interactive(self) -> None:
        with mock.patch("quwoquan_ops.cli.stackctl._is_interactive_terminal", return_value=False):
            result = stackctl._tail_file_for_startup(Path("/tmp/does-not-matter.log"))
        self.assertEqual(result["followed"], False)
        self.assertEqual(result["reason"], "log-not-created")

    def test_tail_file_for_startup_reads_existing_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "app.log"
            log_path.write_text("line one\nline two\n", encoding="utf-8")
            with (
                mock.patch("quwoquan_ops.cli.stackctl._is_interactive_terminal", return_value=True),
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
                mock.patch("quwoquan_ops.cli.stackctl._is_interactive_terminal", return_value=True),
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
            with mock.patch("quwoquan_ops.cli.stackctl._is_interactive_terminal", return_value=False):
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
            with mock.patch("quwoquan_ops.cli.stackctl._is_interactive_terminal", return_value=False):
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

    def test_alpha_cold_ios_build_timeout_covers_native_plugin_compilation(self) -> None:
        self.assertGreaterEqual(
            stackctl.ALPHA_APP_FIRST_BUILD_TIMEOUT_SECONDS,
            300.0,
        )

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
        with mock.patch("quwoquan_ops.cli.stackctl._is_interactive_terminal", return_value=False):
            result = stackctl._run_with_live_output(["python3", "-c", script])
        self.assertEqual(result.returncode, 0)
        self.assertIn("hello", result.stdout)
        self.assertIn("world", result.stdout)

    def test_tail_multiple_logs_for_startup_reads_existing_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_a = Path(tmp_dir) / "a.log"
            log_b = Path(tmp_dir) / "b.log"
            log_a.write_text("a1\n", encoding="utf-8")
            log_b.write_text("b1\nb2\n", encoding="utf-8")
            with (
                mock.patch("quwoquan_ops.cli.stackctl._is_interactive_terminal", return_value=True),
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


if __name__ == "__main__":
    unittest.main()
