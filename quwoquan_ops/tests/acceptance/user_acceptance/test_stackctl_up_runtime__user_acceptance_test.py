from __future__ import annotations

import argparse
import builtins
import io
import importlib.util
import json
import subprocess
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

    def test_repair_restart_stack_supplies_complete_noninteractive_up_args(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value={"env": "gamma"}),
            mock.patch.object(stackctl, "resolve_report_dir", return_value=Path(tmp_dir)),
            mock.patch.object(
                stackctl,
                "command_down",
                return_value={"exitCode": 0, "summary": "down"},
            ),
            mock.patch.object(
                stackctl,
                "command_up",
                return_value={"exitCode": 0, "summary": "up"},
            ) as command_up,
        ):
            result = stackctl.command_repair(
                argparse.Namespace(
                    command="repair",
                    target="gamma-local",
                    fix="restart-stack",
                    report_dir="",
                )
            )

        self.assertEqual(result["exitCode"], 0)
        up_args = command_up.call_args.args[0]
        self.assertEqual(up_args.env, "")
        self.assertEqual(up_args.target, "gamma-local")
        self.assertTrue(up_args.skip_app)
        self.assertEqual(up_args.rollout_mode, "")

    def test_format_stage_header(self) -> None:
        self.assertEqual(stackctl._format_stage_header(2, 3, "app-launch"), "[step 2/3] app-launch")

    def test_legal_static_packages_preserve_utf8_documents_and_current_pointers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir)
            for env_name in ("alpha", "beta", "gamma"):
                with self.subTest(env=env_name):
                    payload = legal_static.build_package(env_name, output_root=output_root)
                    self.assertEqual(payload["status"], "ok")
                    package_dir = (
                        output_root
                        / env_name
                        / "release"
                        / "legal-static"
                        / "2026-07"
                    )
                    self.assertTrue((package_dir / "checksums.json").is_file())
                    self.assertTrue(
                        (
                            output_root
                            / env_name
                            / "release"
                            / "legal-static"
                            / "current"
                        ).exists()
                    )

                    for document in payload["documents"]:
                        stable_document = (
                            package_dir / "public" / "legal" / document["slug"]
                        )
                        self.assertTrue(stable_document.is_file())
                        self.assertIn(
                            document["title"],
                            stable_document.read_text(encoding="utf-8"),
                        )

                    verified = legal_static.verify_package(
                        env_name,
                        output_root=output_root,
                    )
                    self.assertEqual(verified["status"], "ok")

    def test_legal_static_html_validation_requires_utf8_document_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "user-agreement.html"
            source.write_text(
                '<html lang="zh-CN"><head></head><body>用户协议</body></html>',
                encoding="utf-8",
            )

            issues = legal_static._validate_html(
                source,
                doc_slug="user-agreement",
                version="2026-07",
                allowlist=[],
                env_name="alpha",
            )

        self.assertTrue(
            any("UTF-8 charset meta" in issue for issue in issues),
            issues,
        )

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

    def test_post_deploy_probe_blocks_without_verified_test_token(self) -> None:
        args = argparse.Namespace(
            env="gamma",
            mode="post-deploy",
            test_auth_token="",
            base_url="https://gamma.example",
            product_ops_base_url="",
            media_base_url="",
            resolve_host="",
            request_timeout_seconds=12,
            retry_attempts=1,
            retry_sleep_seconds=0.0,
            require_non_empty_content_feed=False,
        )
        with mock.patch.object(integration_probe, "build_checks", return_value=[]):
            report = integration_probe.run_checks(args)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(
            report["findings"],
            [
                "GATE_BLOCK: post-deploy integration requires a valid environment test auth token"
            ],
        )

    def test_environment_probe_uses_ready_entity_operation_not_blocked_chat(self) -> None:
        args = argparse.Namespace(
            env="gamma",
            test_auth_token="runtime-bearer",
            base_url="https://gamma.example",
            product_ops_base_url="",
            media_base_url="",
        )

        checks = integration_probe.build_checks(args)
        by_name = {check["name"]: check for check in checks}

        self.assertNotIn("chat_inbox", by_name)
        self.assertEqual(
            by_name["entity_homepage_search"]["url"],
            "https://gamma.example/v1/homepages/search?query=%E8%A5%BF%E6%B9%96&limit=1",
        )

    def test_local_gamma_print_env_exits_before_runtime_preparation(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        print_defines = script.index("print_defines()")
        print_env_exit = script.rindex('if [[ "$print_env" == "1" ]]; then')
        prepare_runtime = script.index("\nprepare_config_root\n")

        self.assertLess(print_defines, print_env_exit)
        self.assertLess(print_env_exit, prepare_runtime)
        self.assertIn("  print_defines\n  exit 0", script[print_env_exit:prepare_runtime])

    def test_local_gamma_content_seed_is_idempotent_and_fail_closed(self) -> None:
        fixture_payload = {
            "seedSets": {
                "content_core": {
                    "posts": [
                        {
                            "postId": "alpha_moment_grid_1",
                            "contentType": "micro",
                            "createdAt": "2026-01-01T00:00:00Z",
                        }
                    ]
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture_payload), encoding="utf-8")
            artifact_root = Path(tmp_dir) / "artifacts"
            with (
                mock.patch.object(
                    local_gamma_t3,
                    "gamma_content_fixture_spec",
                    return_value=(fixture_path, ["content_core"]),
                ),
                mock.patch.object(local_gamma_t3, "GAMMA_RUN_ROOT", artifact_root),
                mock.patch.object(local_gamma_t3, "compose_command", return_value=["mongosh"]),
                mock.patch.object(
                    local_gamma_t3.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(["mongosh"], 0, "seed ok"),
                ),
            ):
                result = local_gamma_t3.seed_content()

            seed_script = (artifact_root / "seed-content.js").read_text(encoding="utf-8")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["insertedCount"], 1)
        self.assertIn("deleteMany({_id: {$in: ids}})", seed_script)
        self.assertIn("storedCount !== docs.length", seed_script)
        self.assertIn("quit(1);", seed_script)

    def test_local_gamma_seed_failures_block_startup(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("GATE_BLOCK: content seed", script)
        self.assertIn("GATE_BLOCK: intersection seed", script)
        self.assertIn("GATE_BLOCK: premium pool seed", script)
        self.assertNotIn("WARN: content seed failed", script)
        self.assertNotIn("WARN: intersection seed failed", script)
        self.assertNotIn("WARN: premium pool seed failed", script)
        self.assertNotIn("X-Client-User-Id", script)
        self.assertNotIn("X-Test-Auth-Token", script)

    def test_local_gamma_retries_created_only_compose_runtime_once(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("retry_compose_up_after_created_only_failure", script)
        self.assertIn('--filter status=created', script)
        self.assertIn('--filter status=running', script)
        self.assertIn('retry_args+=(--no-build)', script)
        self.assertIn("compose created-only retry recovered startup", script)

    def test_local_gamma_product_ops_uses_required_runtime_auth(self) -> None:
        compose = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        product_ops = compose.split("\n  product-ops-service:\n", 1)[1].split(
            "\n  platform-ops-service:\n", 1
        )[0]

        for name in (
            "AUTH_JWT_SECRET",
            "AUTH_JWT_ISSUER",
            "AUTH_JWT_AUDIENCE",
            "AUTH_JWT_TOKEN_VERSION",
        ):
            self.assertIn(f'{name}: "${{{name}:?{name} is required}}"', product_ops)

    def test_local_gamma_content_probe_methods_come_from_contract_graph(self) -> None:
        methods = local_gamma_t3.content_route_methods()

        self.assertIn(
            "POST", methods["/v1/content/comments/{commentId}/reaction"]
        )
        self.assertIn(
            "POST", methods["/v1/content/comments/{commentId}/media:bind"]
        )

    def test_local_gamma_blocked_operation_requires_metadata_enforced_403(self) -> None:
        manifest = {
            "seedRefs": [
                {
                    "domain": "assistant",
                    "verifiedEndpoints": ["/v1/assistant/conversations/fixture"],
                },
            ]
        }
        forbidden = local_gamma_t3.urllib.error.HTTPError(
            "https://gamma.example/v1/assistant/conversations/fixture",
            403,
            "Forbidden",
            {},
            None,
        )
        with mock.patch.object(local_gamma_t3, "http_get", side_effect=forbidden):
            checks = local_gamma_t3.endpoint_checks(
                manifest,
                "https://gamma.example",
                {"assistant"},
                {},
            )

        self.assertEqual(checks[0]["commercialStatus"], "blocked")
        self.assertEqual(checks[0]["status"], "contract_blocked")
        self.assertEqual(checks[0]["expectedHttpStatus"], 403)

    def test_local_gamma_blocked_operation_fails_if_it_unexpectedly_accepts(self) -> None:
        manifest = {
            "seedRefs": [
                {
                    "domain": "assistant",
                    "verifiedEndpoints": ["/v1/assistant/conversations/fixture"],
                },
            ]
        }
        with mock.patch.object(local_gamma_t3, "http_get", return_value=(200, b"{}")):
            checks = local_gamma_t3.endpoint_checks(
                manifest,
                "https://gamma.example",
                {"assistant"},
                {},
            )

        self.assertEqual(checks[0]["status"], "failed")
        self.assertIn("unexpectedly accepted", checks[0]["error"])

    def test_local_gamma_runtime_refs_keep_owner_and_persona_ids_distinct(self) -> None:
        manifest = {
            "seedRefs": [
                {
                    "domain": "content",
                    "verifiedEndpoints": [
                        "/v1/content/sub-accounts/{activePersonaId}/interactions/received?type=share"
                    ],
                },
                {
                    "domain": "user",
                    "verifiedEndpoints": ["/v1/user/profile/fixture_user_current"],
                },
            ]
        }
        with (
            mock.patch.object(local_gamma_t3, "content_route_methods", return_value={}),
            mock.patch.object(local_gamma_t3, "http_get", return_value=(200, b"{}")),
        ):
            checks = local_gamma_t3.endpoint_checks(
                manifest,
                "https://gamma-api.quwoquan-env.test:19000",
                {"content", "user"},
                {"{activePersonaId}": "persona-runtime"},
            )

        self.assertEqual(
            checks[0]["resolvedPath"],
            "/v1/content/sub-accounts/persona-runtime/interactions/received?type=share",
        )
        self.assertNotIn("resolvedPath", checks[1])
        self.assertEqual(checks[1]["path"], "/v1/user/profile/fixture_user_current")

    def test_local_gamma_comment_setup_uses_current_command_contract(self) -> None:
        responses = [
            (201, b'{"id":"comment-parent","version":1,"status":"active"}'),
            (201, b'{"id":"comment-reply","version":1,"status":"active"}'),
            (200, b'{"id":"reaction-1","version":1,"reaction":"like"}'),
            (200, b'{"id":"comment-parent","version":2,"status":"active"}'),
        ]
        with mock.patch.object(
            local_gamma_t3,
            "http_request",
            side_effect=responses,
        ) as request:
            result = local_gamma_t3.setup_comment_thread("https://gamma.example")

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["parentCommentId"], "comment-parent")
        self.assertEqual(result["replyCommentId"], "comment-reply")
        self.assertEqual(result["mediaBind"]["version"], 2)
        calls = request.call_args_list
        self.assertEqual(
            calls[0].kwargs["headers"]["Idempotency-Key"],
            local_gamma_t3.gamma_probe_idempotency_key("comment-parent"),
        )
        self.assertEqual(
            calls[1].kwargs["headers"]["Idempotency-Key"],
            local_gamma_t3.gamma_probe_idempotency_key("comment-reply"),
        )
        self.assertEqual(
            calls[2].kwargs["headers"]["Idempotency-Key"],
            local_gamma_t3.gamma_probe_idempotency_key("comment-reaction"),
        )
        self.assertEqual(
            calls[3].kwargs["headers"]["Idempotency-Key"],
            local_gamma_t3.gamma_probe_idempotency_key("comment-media-bind"),
        )
        self.assertEqual(
            calls[3].kwargs["body"],
            {"version": 1, "attachmentMediaIds": []},
        )

    def test_local_gamma_social_graph_seed_binds_authenticated_persona(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script_path = (
            root
            / "quwoquan_service/services/seed-box/scripts/apply_content_social_graph_seed.py"
        )
        fixture_path = (
            root
            / "quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_social_graph.gamma_seed.json"
        )
        spec = importlib.util.spec_from_file_location("content_social_graph_seed", script_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)

        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        mongo_script = module.build_mongo_script(fixture, "persona-runtime")

        self.assertIn('sourcePersonaId:"persona-runtime"', mongo_script)
        self.assertIn('userId:"persona-runtime"', mongo_script)
        self.assertNotIn('followerId:"fixture_user_current"', mongo_script)
        self.assertNotIn('userId:"fixture_user_current"', mongo_script)

    def test_environment_probe_does_not_forge_actor_headers(self) -> None:
        anonymous_headers = integration_probe._common_headers("")
        authenticated_headers = integration_probe._common_headers("local-test-bearer")

        self.assertNotIn("X-Client-User-Id", anonymous_headers)
        self.assertNotIn("X-Test-Auth-Token", authenticated_headers)
        self.assertEqual(authenticated_headers["Authorization"], "Bearer local-test-bearer")

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
        self.assertEqual(
            kwargs["argv"][-2:],
            ["--resolve-host", "127.0.0.1"],
        )
        self.assertEqual(kwargs["env"]["TEST_AUTH_TOKEN"], "-starts-with-dash")
        self.assertEqual(kwargs["env"]["GAMMA_TEST_AUTH_TOKEN"], "-starts-with-dash")

    def test_run_environment_integration_probe_mints_local_gamma_session(self) -> None:
        topology = {"targets": []}
        target = {
            "env": "gamma",
            "publicBases": {
                "api": "https://gamma-api.quwoquan-env.test:19000",
                "productOps": "http://ops.example",
            },
        }
        session = mock.Mock(access_token="ephemeral-local-bearer")

        with (
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch(
                "quwoquan_ops.cli.stackctl._resolve_test_auth_token",
                return_value="",
            ),
            mock.patch(
                "quwoquan_ops.cli.stackctl.open_local_gamma_acceptance_session",
                return_value=session,
            ) as login,
            mock.patch(
                "quwoquan_ops.cli.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
        ):
            stackctl._run_environment_integration_probe(
                topology,
                "gamma-local",
                Path("/tmp/report"),
            )

        login.assert_called_once_with(
            "https://gamma-api.quwoquan-env.test:19000",
            resolve_host="127.0.0.1",
        )
        kwargs = run_probe.call_args.kwargs
        self.assertNotIn("--test-auth-token", kwargs["argv"])
        self.assertEqual(kwargs["env"]["TEST_AUTH_TOKEN"], "ephemeral-local-bearer")
        self.assertEqual(
            kwargs["env"]["GAMMA_TEST_AUTH_TOKEN"],
            "ephemeral-local-bearer",
        )

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

    def test_local_gamma_t3_uses_only_runtime_bearer_identity(self) -> None:
        session = local_gamma_t3.LocalGammaAcceptanceSession(
            owner_id="owner-local",
            persona_id="persona-local",
            access_token="runtime-bearer",
        )
        with mock.patch.object(local_gamma_t3, "_ACTIVE_SESSION", session):
            headers = local_gamma_t3.default_request_headers()

        self.assertEqual(headers, {"Authorization": "Bearer runtime-bearer"})
        self.assertNotIn("X-Client-User-Id", headers)
        self.assertNotIn("X-Client-Sub-Account-Id", headers)

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
                mock.patch(
                    "quwoquan_ops.cli.stackctl._prod_plane_runtime_report",
                    return_value={
                        "composeFileExists": True,
                        "envFileExists": True,
                        "containerCount": 1,
                    },
                ),
            ):
                result = stackctl.command_doctor(args)
            self.assertEqual(result["exitCode"], 0)
            self.assertTrue(
                any("prod rollout release-state is missing" in item for item in result["details"])
            )


if __name__ == "__main__":
    unittest.main()
