from __future__ import annotations

import builtins
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import legal_static
from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.probes import run_environment_integration_probe as integration_probe
from quwoquan_app.scripts.gamma import run_local_gamma_t3 as local_gamma_t3


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_parser_accepts_report_dir_after_subcommand(self) -> None:
        parser = stackctl.build_parser()
        cases = [
            ["package", "--env", "alpha", "--report-dir", ".qwq_output/env/alpha/runs/package"],
            [
                "package",
                "--env",
                "alpha",
                "--kind",
                "legal-static",
                "--report-dir",
                ".qwq_output/env/alpha/runs/legal-package",
            ],
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
                ".qwq_output/env/alpha/runs/verify",
            ],
            [
                "verify",
                "--env",
                "alpha",
                "--kind",
                "legal-static",
                "--report-dir",
                ".qwq_output/env/alpha/runs/legal-verify",
            ],
            ["up", "--target", "alpha-local", "--report-dir", ".qwq_output/env/alpha/runs/up"],
            [
                "health",
                "--target",
                "alpha-local",
                "--scope",
                "full",
                "--report-dir",
                ".qwq_output/env/alpha/runs/health",
            ],
            [
                "inspect",
                "--target",
                "alpha-local",
                "--scope",
                "all",
                "--report-dir",
                ".qwq_output/env/alpha/runs/inspect",
            ],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertTrue(getattr(args, "report_dir", "").startswith(".qwq_output/env/alpha/runs/"))

    def test_parser_keeps_global_report_dir_before_subcommand(self) -> None:
        parser = stackctl.build_parser()
        args = parser.parse_args(
            ["--report-dir", ".qwq_output/env/alpha/runs/global", "package", "--env", "alpha"]
        )
        self.assertEqual(args.report_dir, ".qwq_output/env/alpha/runs/global")

    def test_format_stage_header(self) -> None:
        self.assertEqual(stackctl._format_stage_header(2, 3, "app-launch"), "[step 2/3] app-launch")

    def test_legal_static_package_builds_current_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir)
            payload = legal_static.build_package("alpha", output_root=output_root)
            self.assertEqual(payload["status"], "ok")
            package_dir = output_root / "alpha" / "release" / "legal-static" / "2026-07"
            self.assertTrue((package_dir / "public/legal/user-agreement").is_file())
            self.assertTrue((package_dir / "checksums.json").is_file())
            self.assertTrue((output_root / "alpha" / "release" / "legal-static" / "current").exists())

            verified = legal_static.verify_package("alpha", output_root=output_root)
            self.assertEqual(verified["status"], "ok")

    def test_legal_static_202607_contract_keywords(self) -> None:
        manifest, issues = legal_static.validate_manifest("alpha")
        self.assertEqual(issues, [])
        self.assertEqual(manifest["currentVersion"], "2026-07")

        legal_root = legal_static.DEFAULT_MANIFEST.parent / "versions" / "2026-07"
        user_agreement = (legal_root / "user-agreement.html").read_text(encoding="utf-8")
        privacy_policy = (legal_root / "privacy-policy.html").read_text(encoding="utf-8")
        permissions = (legal_root / "permissions.html").read_text(encoding="utf-8")
        sdk_list = (legal_root / "third-party-sdk-list.html").read_text(encoding="utf-8")

        for token in (
            "外部平台内容与授权边界",
            "图虫、微信、今日头条、微博、小红书",
            "robots",
            "反爬",
            "用户内容与权利保证",
            "AI 与记忆能力",
            "当前版本为免费社区服务",
        ):
            self.assertIn(token, user_agreement)

        for token in (
            "按功能收集和使用的信息",
            "敏感个人信息",
            "委托处理、共享、转让与公开披露",
            "自动化决策、个性化推荐与 AI",
            "当前免费社区版本默认不向境外提供个人信息",
        ):
            self.assertIn(token, privacy_policy)

        self.assertIn("当前版本未启用独立语音识别系统权限", permissions)
        for token in (
            "LiveKit 实时音视频能力",
            "微信登录 SDK",
            "QQ 登录/分享 SDK",
            "支付宝 SDK",
            "广告、归因、商业化追踪 SDK",
        ):
            self.assertIn(token, sdk_list)

    def test_legal_static_package_builds_when_pyyaml_is_unavailable(self) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "yaml":
                raise ModuleNotFoundError(name)
            return real_import(name, *args, **kwargs)

        with (
            mock.patch("builtins.__import__", side_effect=fake_import),
            tempfile.TemporaryDirectory() as tmp_dir,
        ):
            manifest = load_json_yaml(legal_static.DEFAULT_MANIFEST)
            payload = legal_static.build_package("alpha", output_root=Path(tmp_dir))

        self.assertEqual(manifest["schemaVersion"], "legal-static/v1")
        self.assertEqual(manifest["owner"]["appName"], "趣我圈")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            [doc["slug"] for doc in manifest["documents"]],
            [
                "user-agreement",
                "privacy-policy",
                "permissions",
                "third-party-sdk-list",
            ],
        )

    def test_legal_static_prod_requires_final_legal_identity(self) -> None:
        _, issues = legal_static.validate_manifest("prod")
        self.assertTrue(any("placeholder" in issue for issue in issues))

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
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch(
                "quwoquan_ops.cli.stackctl._resolve_test_auth_token",
                return_value="-starts-with-dash",
            ),
            mock.patch(
                "quwoquan_ops.cli.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
        ):
            stackctl._run_environment_integration_probe(topology, "gamma-local", Path("/tmp/report"))

        kwargs = run_probe.call_args.kwargs
        self.assertNotIn("--test-auth-token", kwargs["argv"])
        self.assertEqual(kwargs["env"]["TEST_AUTH_TOKEN"], "-starts-with-dash")
        self.assertEqual(kwargs["env"]["GAMMA_TEST_AUTH_TOKEN"], "-starts-with-dash")

    def test_verify_tier_starts_gamma_when_dependency_port_is_missing(self) -> None:
        manifest = stackctl.load_port_manifest()
        target = {"env": "gamma", "portProfile": "gamma-local"}
        mongo_port = stackctl.canonical_port(manifest, "gamma-local", "mongodb")

        with (
            mock.patch("quwoquan_ops.cli.stackctl.load_environment_topology", return_value={}),
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch("quwoquan_ops.cli.stackctl.load_port_manifest", return_value=manifest),
            mock.patch(
                "quwoquan_ops.cli.stackctl.socket_probe",
                side_effect=lambda port: port != mongo_port,
            ),
        ):
            commands = stackctl._selected_tier_commands("gamma", "gamma-local", "t3")

        self.assertEqual(commands[0]["name"], "gamma-local-up")

    def test_verify_tier_skips_gamma_up_only_when_runtime_ports_are_ready(self) -> None:
        manifest = stackctl.load_port_manifest()
        target = {"env": "gamma", "portProfile": "gamma-local"}

        with (
            mock.patch("quwoquan_ops.cli.stackctl.load_environment_topology", return_value={}),
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch("quwoquan_ops.cli.stackctl.load_port_manifest", return_value=manifest),
            mock.patch("quwoquan_ops.cli.stackctl.socket_probe", return_value=True),
        ):
            commands = stackctl._selected_tier_commands("gamma", "gamma-local", "t3")

        self.assertEqual(commands[0]["name"], "gamma-local-health-preflight")
        self.assertIn("local runtime ports already listening", " ".join(commands[0]["argv"]))

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

    def test_local_gamma_t3_compose_command_uses_stack_project(self) -> None:
        with mock.patch.object(local_gamma_t3, "COMPOSE_PROJECT", "quwoquan_service"):
            cmd = local_gamma_t3.compose_command("exec", "-T", "mongodb", "mongosh")

        self.assertEqual(cmd[:4], ["docker", "compose", "-p", "quwoquan_service"])
        self.assertEqual(cmd[4], "-f")
        self.assertTrue(cmd[5].endswith("quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"))
        self.assertEqual(cmd[6:], ["exec", "-T", "mongodb", "mongosh"])

    def test_local_gamma_t3_endpoint_checks_marks_scope_externals_out_of_scope(self) -> None:
        manifest = {
            "seedRefs": [
                {"domain": "assistant", "verifiedEndpoints": ["/v1/assistant/conversations"]},
                {
                    "domain": "content",
                    "verificationScopes": ["object-homepage-gamma-real-data-closure"],
                    "verifiedEndpoints": ["/v1/content/feed"],
                },
            ]
        }
        scope = {"domains": ["content"]}
        with (
            mock.patch.object(local_gamma_t3, "content_route_methods", return_value={}),
            mock.patch.object(local_gamma_t3, "http_get", return_value=(200, b"{}")),
        ):
            checks = local_gamma_t3.endpoint_checks(
                manifest,
                "https://gamma-api.quwoquan-env.test:19000",
                {"content"},
                {},
                scope_name="object-homepage-gamma-real-data-closure",
                scope=scope,
            )
        self.assertEqual(checks[0]["status"], "out_of_scope")
        self.assertEqual(checks[1]["status"], "passed")

    def test_local_gamma_t3_strict_endpoint_checks_uses_scope_runtime_refs(self) -> None:
        scope = {
            "runtimeRefs": {"{circleId}": "fixture_circle_photo"},
            "strictEndpoints": [
                {
                    "domain": "content",
                    "path": "/v1/content/intersections/object?objectType=circle&objectId={circleId}",
                    "assertion": "object_intersections_circle",
                }
            ],
        }
        payload = json.dumps(
            {
                "items": [],
                "objectId": "fixture_circle_photo",
                "objectType": "circle",
            }
        ).encode("utf-8")
        with mock.patch.object(local_gamma_t3, "http_get", return_value=(200, payload)):
            checks = local_gamma_t3.strict_endpoint_checks(
                "https://gamma-api.quwoquan-env.test:19000",
                {},
                scope,
            )
        self.assertEqual(
            checks[0]["resolvedPath"],
            "/v1/content/intersections/object?objectType=circle&objectId=fixture_circle_photo",
        )
        self.assertEqual(checks[0]["status"], "failed")
        self.assertIn("items must be non-empty", checks[0]["error"])

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
                mock.patch("quwoquan_ops.cli.stackctl.load_environment_topology", return_value=topology),
                mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=topology["targets"]["prod-hosted"]),
                mock.patch("quwoquan_ops.cli.stackctl.command_health", return_value=health_payload),
                mock.patch("quwoquan_ops.cli.stackctl._load_release_state", return_value={}),
            ):
                result = stackctl.command_doctor(args)
            self.assertEqual(result["exitCode"], 0)
            self.assertTrue(
                any("prod rollout release-state is missing" in item for item in result["details"])
            )


if __name__ == "__main__":
    unittest.main()
