# spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-004

from __future__ import annotations

import argparse
import builtins
import io
import json
import os
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import legal_static
from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.content_release_readiness import VerificationProfile
from quwoquan_ops.cli.lib.output_paths import (
    deployment_target_for_env,
    deployment_target_path,
    legal_static_deployment_package_dir,
)
from quwoquan_ops.cli.probes import run_environment_integration_probe as integration_probe
from quwoquan_app.scripts.gamma import run_local_gamma_t3 as local_gamma_t3


def _gamma_release_identity() -> dict[str, object]:
    return {
        "releaseId": "release-gamma-a",
        "sourceOwner": "qwq_data",
        "manifestDigest": f"sha256:{'1' * 64}",
        "mediaManifestDigest": f"sha256:{'2' * 64}",
        "importRunId": "import-gamma-a",
        "verifyRunId": "verify-gamma-a",
        "readinessReceiptRef": (
            "env/gamma/runs/data-release/release-gamma-a/verify-gamma-a/"
            "release-readiness.json"
        ),
    }


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_beta_content_release_starts_all_declared_readiness_dependencies(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script = (
            root
            / "quwoquan_app/scripts/device/start_app_beta_manual.sh"
        ).read_text(encoding="utf-8")
        beta_stack_script = (
            root / "quwoquan_ops/cli/beta/start_beta_stack.sh"
        ).read_text(encoding="utf-8")
        release_body = script.split(
            "beta_manual_start_content_release_stack() {", 1
        )[1].split("\n}\n\ncleanup()", 1)[0]
        release_media_body = script.split(
            "beta_manual_start_release_media_runtime() {", 1
        )[1].split("\n}\n\nbeta_manual_start_entity_service", 1)[0]
        content_release_caddy = script.split(
            "beta_manual_prepare_tls_caddyfile() {", 1
        )[1].split("\n}\n\nbeta_manual_stop_tls_proxy", 1)[0]
        tls_proxy_body = script.split("beta_manual_start_tls_proxy() {", 1)[1].split(
            "\n}\n\nbeta_manual_wait_https_ok", 1
        )[0]

        self.assertIn("beta_manual_start_release_media_runtime || return 1", release_body)
        self.assertIn("beta_manual_start_entity_service || return 1", release_body)
        self.assertIn("beta_manual_start_tls_proxy || return 1", release_body)
        self.assertLess(
            release_body.index("beta_manual_ensure_data_plane || return 1"),
            release_body.index("beta_manual_start_release_media_runtime || return 1"),
        )
        self.assertLess(
            release_body.index("beta_manual_start_release_media_runtime || return 1"),
            release_body.index("beta_manual_start_entity_service || return 1"),
        )
        self.assertIn(
            'beta_manual_wait_http_ok "http://127.0.0.1:${USER_PORT}/healthz" "user-service"',
            script,
        )
        self.assertIn(
            '"$ROOT_DIR/quwoquan_service/services/user-service/deploy/compose.yaml"',
            script,
        )
        self.assertIn('user-service) export USER_CONFIG_VERSION="$config_version"', script)
        self.assertIn(
            "for service in content-service entity-service recommendation-service user-service",
            script,
        )
        self.assertNotIn("notification-service", script)
        self.assertNotIn("beta_manual_ensure_compose_service_image", script)
        self.assertIn(
            "local compose_up_args=(up -d --remove-orphans)",
            script,
        )
        self.assertIn("COMPOSE_PARALLEL_LIMIT=1 docker compose", script)
        self.assertIn("compose_up_args+=(--no-build)", script)
        self.assertIn("compose_up_args+=(--build)", script)
        self.assertIn('APP_BETA_CMD+=(--skip-build)', beta_stack_script)
        self.assertEqual(
            beta_stack_script.count("APP_BETA_CMD+=(--content-release)"),
            1,
        )
        self.assertIn(
            "@creator_profile_release path /auth /auth/* /user /user/* /users /users/*",
            script,
        )
        self.assertIn("@content_release path /content /content/* /config/app", script)
        self.assertIn(
            "@content_filter_catalog_release path "
            "/internal/content/filter-catalog-releases "
            "/internal/content/filter-catalog-releases/*",
            content_release_caddy,
        )
        self.assertIn(
            "beta_manual_wait_https_ok \\\n"
            '    "$PUBLIC_IMAGE_HOST" \\\n'
            '    "$MEDIA_PORT"',
            release_body,
        )
        self.assertIn('ENTITY_SERVICE_ADDR="${listen_host}:${ENTITY_PORT}"', script)
        self.assertIn(
            'ENTITY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL="http://127.0.0.1:${USER_PORT}"',
            script,
        )
        self.assertIn(
            'beta_manual_wait_http_ok "http://127.0.0.1:${ENTITY_PORT}/healthz" "entity-service" 180',
            script,
        )
        self.assertIn("--listen-host 0.0.0.0", release_media_body)
        lifecycle = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_ops/cli/lib/beta_manual_lifecycle.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("kill -KILL $pids", lifecycle)
        self.assertIn("will not be stopped automatically", lifecycle)
        self.assertIn(
            'local diagnostic_log="$BETA_MANUAL_STATE_DIR/stdout/${name}.log"',
            lifecycle,
        )
        self.assertIn('"--diagnostic-log"', lifecycle)
        self.assertIn(
            'f"diagnostic_log={shlex.quote(str(diagnostic_log))}"',
            lifecycle,
        )
        self.assertIn("TLS_PROXY_PORT_RELEASE_TIMEOUT_SECONDS", script)
        self.assertIn("Caddy port :$port did not release", script)
        self.assertIn('logs --tail 80 "$TLS_PROXY_NAME"', release_body)
        self.assertIn('-p "${GATEWAY_PORT}:${GATEWAY_PORT}"', tls_proxy_body)
        self.assertIn('-p "${MEDIA_PORT}:${MEDIA_PORT}"', tls_proxy_body)
        self.assertNotIn("PRODUCT_OPS_PORT", tls_proxy_body)
        self.assertIn("Caddy configuration preparation failed", tls_proxy_body)
        self.assertIn("Caddy previous deployment did not stop cleanly", tls_proxy_body)
        self.assertIn("beta Caddy deployment failed", tls_proxy_body)
        self.assertIn("deployment exited before readiness", tls_proxy_body)
        self.assertIn(
            "@content_filter_catalog_release path /internal/content/filter-catalog-releases /internal/content/filter-catalog-releases/*",
            script,
        )
        self.assertIn(
            "reverse_proxy ${CONTAINER_HOST_ALIAS}:${CONTENT_PORT}",
            script,
        )
        self.assertIn("ship apply is the only writer of this directory", release_media_body)
        self.assertIn("local_media_origin.py", release_media_body)
        self.assertIn("path.is_symlink()", release_media_body)
        for retired in (
            "contracts/metadata/_shared/test_fixtures",
            "dev_assistant_beta_gateway.py",
            "beta_manual_start_fixture_gateway",
            "beta_manual_start_notification_service",
            "go run ./cmd/seed-fixture",
            "go run ./services/user-service/cmd/seed",
            "fixture_user_current",
            "CONTENT_RELEASE_ONLY",
            "START_ASSISTANT",
            "BETA_FIXTURE_GATEWAY_PORT",
        ):
            self.assertNotIn(retired, script)
        self.assertIn("respond 404", content_release_caddy)

    def test_gamma_content_release_routes_and_activates_filter_catalog(self) -> None:
        root = Path(__file__).resolve().parents[4]
        caddyfile = (
            root / "quwoquan_ops/environments/gamma/local/Caddyfile"
        ).read_text(encoding="utf-8")
        startup_script = (
            root / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn("@api_content_filter_catalog_release", caddyfile)
        self.assertIn("generated-operation api-edge", caddyfile)
        self.assertIn("reverse_proxy api-edge:18079", caddyfile)
        self.assertIn(
            "ensure_gamma_filter_catalog_release()",
            startup_script,
        )
        self.assertIn(
            'filter-catalog --target "$QWQ_LOCAL_RELEASE_TARGET" --action stage-and-activate',
            startup_script,
        )
        self.assertIn(
            "wait_local_gamma_host_ready\n"
            "ensure_gamma_filter_catalog_release",
            startup_script,
        )

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
                "--profile",
                "smoke",
                "--report-dir",
                ".qwq_output/env/alpha/runs/verify",
            ],
            [
                "verify",
                "--env",
                "alpha",
                "--kind",
                "legal-static",
                "--profile",
                "smoke",
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

    def test_status_uses_content_consumer_scope_for_current_content_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            process_dir = Path(tmp_dir) / "process"
            process_dir.mkdir()
            (process_dir / "stack.state").write_text(
                "stack=beta-local\nworkload=content-release\n", encoding="utf-8"
            )
            health_payload = {"exitCode": 0, "summary": "content release ready"}
            with (
                mock.patch.object(stackctl, "target_process_dir", return_value=process_dir),
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(stackctl, "get_target", return_value={"env": "beta"}),
                mock.patch.object(stackctl, "resolve_report_dir", return_value=Path(tmp_dir) / "report"),
                mock.patch.object(stackctl, "command_health", return_value=health_payload) as health,
            ):
                result = stackctl.command_status(
                    argparse.Namespace(target="beta-local", output_format="text", report_dir="")
                )

        self.assertEqual(result, health_payload)
        self.assertEqual(health.call_args.args[0].scope, "content-consumer")

    def test_gamma_status_uses_completed_workload_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            process_dir = Path(tmp_dir) / "process"
            process_dir.mkdir()
            (process_dir / "stack_status.json").write_text(
                json.dumps({"status": "passed", "workload": "content-release"}),
                encoding="utf-8",
            )
            with mock.patch.object(stackctl, "target_process_dir", return_value=process_dir):
                scope = stackctl._current_runtime_health_scope("gamma-local")

        self.assertEqual(scope, "content-consumer")

    def test_app_startup_treats_missing_log_sink_as_non_blocking_advisory(self) -> None:
        with mock.patch.object(
            stackctl,
            "load_product_telemetry_log_sink",
            side_effect=RuntimeError(
                "local provider credentials must not be written into the repository or .qwq_output"
            ),
        ):
            environment, advisory = stackctl._optional_product_telemetry_environment(
                "beta",
                "beta-local",
            )

        self.assertEqual(environment, {"QWQ_PRODUCT_TELEMETRY_AVAILABLE": "0"})
        self.assertIn("must not be written into the repository", advisory)

    def test_app_startup_injects_log_sink_when_observability_is_available(self) -> None:
        with mock.patch.object(
            stackctl,
            "load_product_telemetry_log_sink",
            return_value=mock.Mock(
                environment={
                    "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT": "http://elasticsearch:9200",
                }
            ),
        ):
            environment, advisory = stackctl._optional_product_telemetry_environment(
                "gamma",
                "gamma-local",
            )

        self.assertEqual(environment["QWQ_PRODUCT_TELEMETRY_AVAILABLE"], "1")
        self.assertEqual(
            environment["PRODUCT_OPS_ELASTICSEARCH_ENDPOINT"],
            "http://elasticsearch:9200",
        )
        self.assertEqual(advisory, "")

    def test_beta_cold_start_uses_configurable_backend_readiness_timeout(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_ops/cli/beta/start_beta_stack.sh"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'BETA_BACKEND_READY_TIMEOUT_SECONDS="${BETA_BACKEND_READY_TIMEOUT_SECONDS:-1200}"',
            script,
        )
        self.assertIn(
            "BETA_BACKEND_READY_TIMEOUT_SECONDS must be a positive integer.",
            script,
        )
        self.assertIn(
            'wait_service_ok app-beta "http://127.0.0.1:${CONTENT_PORT}/healthz" "$BETA_BACKEND_READY_TIMEOUT_SECONDS"',
            script,
        )
        self.assertNotIn(
            'wait_service_ok app-beta "http://127.0.0.1:${CONTENT_PORT}/healthz" 420',
            script,
        )

    def test_repair_restart_stack_supplies_complete_noninteractive_up_args(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value={"env": "gamma"}),
            mock.patch.object(stackctl, "resolve_report_dir", return_value=Path(tmp_dir)),
            mock.patch.object(stackctl, "load_product_telemetry_log_sink"),
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

    def test_repair_restart_stack_blocks_before_down_when_materialization_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_dir = Path(tmp_dir)
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(stackctl, "get_target", return_value={"env": "beta"}),
                mock.patch.object(stackctl, "resolve_report_dir", return_value=report_dir),
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_log_sink",
                    side_effect=RuntimeError(
                        "local provider credentials must not be written into the repository or .qwq_output"
                    ),
                ),
                mock.patch.object(stackctl, "command_down") as command_down,
                mock.patch.object(stackctl, "command_up") as command_up,
            ):
                result = stackctl.command_repair(
                    argparse.Namespace(
                        command="repair",
                        target="beta-local",
                        fix="restart-stack",
                        report_dir="",
                    )
                )

            self.assertEqual(result["exitCode"], 2)
            self.assertIn("blocked before stop", result["summary"])
            command_down.assert_not_called()
            command_up.assert_not_called()
            repair_plan = json.loads(
                (report_dir / "repair_plan.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                any("QWQ_DEPLOY_WORK_ROOT" in item for item in repair_plan["actions"])
            )

    def test_format_stage_header(self) -> None:
        self.assertEqual(stackctl._format_stage_header(2, 3, "app-launch"), "[step 2/3] app-launch")

    def test_legal_static_packages_preserve_utf8_documents_and_current_pointers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            deploy_root = Path(tmp_dir) / "deploy"
            with mock.patch.dict(
                os.environ,
                {
                    "QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / ".qwq_output"),
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                },
                clear=False,
            ):
                for env_name in ("alpha", "beta", "gamma"):
                    with self.subTest(env=env_name):
                        target_name = deployment_target_for_env(env_name)
                        output_root = legal_static_deployment_package_dir(env_name)
                        payload = legal_static.build_package(
                            env_name,
                            output_root=output_root,
                        )
                        self.assertEqual(payload["status"], "ok")
                        package_dir = deployment_target_path(
                            target_name,
                            "packages",
                            "legal-static",
                            "2026-07",
                        )
                        self.assertTrue((package_dir / "checksums.json").is_file())
                        self.assertTrue((output_root / "current").exists())

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

    def test_legal_static_rejects_unscoped_package_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            rejected_output = Path(tmp_dir) / "outside-legal-package"
            with mock.patch.dict(
                os.environ,
                {
                    "QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / ".qwq_output"),
                    "QWQ_DEPLOY_WORK_ROOT": str(Path(tmp_dir) / "deploy"),
                },
                clear=False,
            ):
                with self.assertRaisesRegex(ValueError, "target-scoped"):
                    legal_static.build_package(
                        "alpha",
                        output_root=rejected_output,
                    )
            self.assertFalse(rejected_output.exists())

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
            deploy_root = Path(tmp_dir) / "deploy"
            with mock.patch.dict(
                os.environ,
                {
                    "QWQ_OUTPUT_ROOT": str(Path(tmp_dir) / ".qwq_output"),
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                },
                clear=False,
            ):
                payload = legal_static.build_package(
                    "alpha",
                    output_root=legal_static_deployment_package_dir("alpha"),
                )

        self.assertEqual(manifest["schema"], "legal-static")
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
            "https://gamma.example/homepages/search?query=%E8%A5%BF%E6%B9%96&limit=1",
        )
        search = by_name["global_search"]
        self.assertEqual(search["method"], "POST")
        self.assertEqual(search["url"], "https://gamma.example/search")
        self.assertEqual(
            json.loads(search["body"].decode("utf-8")),
            {"query": "西湖", "mode": "result", "limit": 1},
        )

    def test_environment_probe_requires_search_commercial_envelope(self) -> None:
        issue, hit_count = integration_probe._search_semantic_issue(
            json.dumps(
                {
                    "requestId": "search-probe-1",
                    "hits": [],
                }
            )
        )
        self.assertIsNone(issue)
        self.assertEqual(hit_count, 0)

        issue, hit_count = integration_probe._search_semantic_issue(
            json.dumps({"requestId": "search-probe-1", "hits": {}})
        )
        self.assertIn("hits", issue or "")
        self.assertIsNone(hit_count)

    def test_environment_probe_can_gate_only_global_search(self) -> None:
        args = argparse.Namespace(
            env="beta",
            test_auth_token="",
            base_url="https://beta.example",
            product_ops_base_url="",
            media_base_url="",
            request_timeout_seconds=12,
            retry_attempts=1,
            retry_sleep_seconds=0.0,
            require_non_empty_content_feed=False,
            only_check=["global_search"],
            mode="readonly",
        )
        response = json.dumps(
            {
                "requestId": "search-probe-2",
                "hits": [],
            }
        )
        with mock.patch.object(
            integration_probe,
            "request",
            return_value=(True, 200, response),
        ):
            report = integration_probe.run_checks(args)

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["onlyChecks"], ["global_search"])
        self.assertEqual(
            [check["name"] for check in report["checks"]],
            ["global_search"],
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
        source = Path(local_gamma_t3.__file__).read_text(encoding="utf-8")

        for retired in (
            "seed_content",
            "setup_runtime_fixtures",
            "test_fixtures",
            "mongosh",
            "deleteMany",
        ):
            self.assertNotIn(retired, source)
        self.assertIn('"mutationPolicy": "read_only"', source)
        self.assertIn("load_release_content_identity", source)

    def test_local_gamma_video_seed_preserves_work_browser_projection_fields(
        self,
    ) -> None:
        completed = subprocess.CompletedProcess(
            ["quwoquan_data/scripts/cli.py"],
            0,
            stdout="release verification passed",
        )
        with mock.patch.object(
            local_gamma_t3.subprocess,
            "run",
            return_value=completed,
        ) as run:
            result = local_gamma_t3.run_release_consumer(
                identity=_gamma_release_identity(),
            )

        command = run.call_args.args[0]
        self.assertEqual(result["status"], "passed")
        self.assertIn("ship", command)
        self.assertIn("verify", command)
        self.assertEqual(command[command.index("--release-id") + 1], "release-gamma-a")
        self.assertEqual(command[command.index("--import-run-id") + 1], "import-gamma-a")
        self.assertEqual(command[command.index("--run-id") + 1], "verify-gamma-a")
        self.assertNotIn("fixture", " ".join(command))

    def test_local_gamma_relationship_seed_uses_running_stack_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "t3.json"
            with (
                mock.patch.object(
                    local_gamma_t3,
                    "resolve_readiness_path",
                    return_value=Path("/tmp/release-readiness.json"),
                ),
                mock.patch.object(
                    local_gamma_t3,
                    "load_release_content_identity",
                    return_value=_gamma_release_identity(),
                ) as load_identity,
                mock.patch.object(
                    local_gamma_t3,
                    "run_release_consumer",
                    return_value={"status": "passed", "exitCode": 0},
                ),
                mock.patch.object(
                    local_gamma_t3,
                    "resolve_t3_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_t3.sys,
                    "argv",
                    [
                        "run_local_gamma_t3.py",
                        "--release-readiness",
                        "env/gamma/release-readiness.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                result = local_gamma_t3.main()

        self.assertEqual(result, 0)
        load_identity.assert_called_once_with(
            Path("/tmp/release-readiness.json"),
            expected_environment="gamma",
        )

    def test_local_gamma_t3_uses_shared_target_isolated_acceptance_session(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "t3-report.json"
            with (
                mock.patch.object(
                    local_gamma_t3,
                    "resolve_readiness_path",
                    return_value=Path("/tmp/release-readiness.json"),
                ),
                mock.patch.object(
                    local_gamma_t3,
                    "load_release_content_identity",
                    return_value=_gamma_release_identity(),
                ),
                mock.patch.object(
                    local_gamma_t3,
                    "run_release_consumer",
                    return_value={
                        "status": "passed",
                        "exitCode": 0,
                        "command": ["ship", "verify"],
                    },
                ),
                mock.patch.object(
                    local_gamma_t3,
                    "resolve_t3_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_t3.sys,
                    "argv",
                    [
                        "run_local_gamma_t3.py",
                        "--release-readiness",
                        "env/gamma/runs/data-release/release-gamma-a/"
                        "verify-gamma-a/release-readiness.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                self.assertEqual(local_gamma_t3.main(), 0)

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["schema"], "gamma-t3-release-consumer")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["release"], _gamma_release_identity())
        self.assertEqual(report["mutationPolicy"], "read_only")
        self.assertNotIn("auth", report)
        self.assertNotIn("domainSeeds", report)

    def test_local_gamma_seed_only_persists_user_profile_for_authenticated_probes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "t3-seed-report.json"
            with (
                mock.patch.object(
                    local_gamma_t3,
                    "resolve_readiness_path",
                    side_effect=local_gamma_t3.ReleaseVideoDeliveryError(
                        "DATA_RELEASE_READINESS_RECEIPT is required"
                    ),
                ),
                mock.patch.object(local_gamma_t3, "run_release_consumer") as consumer,
                mock.patch.object(
                    local_gamma_t3,
                    "resolve_t3_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_t3.sys,
                    "argv",
                    [
                        "run_local_gamma_t3.py",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                self.assertEqual(local_gamma_t3.main(), 2)

            consumer.assert_not_called()
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "gate_block")
        self.assertIn("DATA_RELEASE_READINESS_RECEIPT is required", report["reason"])
        self.assertEqual(report["mutationPolicy"], "read_only")

    def test_local_gamma_has_no_environment_business_seed_path(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "immutable release activation owns business data and search projections",
            script,
        )
        self.assertNotIn("seed_gamma_content_data", script)
        self.assertNotIn("seed_gamma_intersection_data", script)
        self.assertNotIn("seed_gamma_premium_pool_data", script)
        self.assertNotIn("ENABLE_FIXTURE_SEEDS", script)
        self.assertNotIn("X-Client-User-Id", script)
        self.assertNotIn("X-Test-Auth-Token", script)

    def test_local_gamma_content_release_only_accepts_release_owned_media(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "Data CLI ship apply --full-sync owns public slices",
            script,
        )
        self.assertIn("environment media root contains fixture/mock/seed", script)
        self.assertNotIn("local_gamma_media.py", script)
        self.assertNotIn("test_fixtures/media", script)

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
        self.assertIn("run_compose_build_with_timeout", script)
        self.assertIn(': >"$build_log"', script)
        self.assertIn("LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS", script)
        self.assertIn("LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS", script)
        self.assertIn("LOCAL_GAMMA_COMPOSE_BUILD_PARALLEL_LIMIT", script)
        self.assertIn('COMPOSE_PARALLEL_LIMIT="$compose_parallel_limit"', script)
        self.assertIn("compose build produced no log progress", script)
        self.assertIn("LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS", script)
        self.assertIn("Docker daemon did not answer readiness probe", script)
        self.assertIn(
            "docker info --format '{{.ServerVersion}} {{.Driver}}' >/dev/null 2>&1 &",
            script,
        )
        self.assertNotIn("docker system df &", script)
        self.assertIn("trap cleanup_active_child EXIT INT TERM HUP", script)
        self.assertIn("LOCAL_GAMMA_ACTIVE_CHILD_PID=\"$compose_pid\"", script)
        self.assertIn("stopping active child before exit", script)
        self.assertIn("preserving build log for inspection", script)
        self.assertIn(
            'if [[ "$build_status" -eq 0 ]]; then\n    return 0',
            script,
        )
        self.assertNotIn(
            'if [[ "$build_status" -eq 0 ]]; then\n    rm -f "$build_log"',
            script,
        )
        self.assertIn("run_compose_up_with_timeout", script)
        self.assertIn("LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS", script)
        self.assertIn("preserving the partial runtime for inspection", script)
        self.assertNotIn('LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS:-900', script)
        self.assertIn("compose_up_timed_out=1", script)
        self.assertIn("run stackctl inspect before an explicit restart", script)

    def test_local_gamma_selected_build_services_are_nounset_safe(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("selected_build_service_count=0", script)
        self.assertIn(
            'if [[ "$selected_build_service_count" -gt 0 ]]; then',
            script,
        )
        self.assertIn(
            'if [[ "$selected_build_service_count" == "0" ]]; then',
            script,
        )

    def test_local_gamma_embedding_substitute_needs_no_runtime_material(self) -> None:
        script = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "LOCAL_GAMMA_EMBEDDING_",
            script,
        )
        self.assertNotIn("CONTENT_EMBEDDING_FIXTURE_", script)

    def test_local_gamma_content_release_excludes_secret_backed_assistant(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script = (
            root / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        ).read_text(encoding="utf-8")
        assistant = (
            root
            / "quwoquan_service/services/assistant-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        compose = (
            root
            / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        proxy = compose.split("\n  gamma-proxy:\n", 1)[1].split(
            "\n  # ── edge-media", 1
        )[0]

        self.assertIn('profiles: ["assistant-runtime"]', assistant)
        self.assertIn(
            "commercial-observability,assistant-runtime,edge-media",
            script,
        )
        self.assertIn('if [[ "$WORKLOAD" == "content-release" ]]; then', script)
        self.assertIn(
            '[[ "$service_name" == "assistant-service" ]] ||',
            script,
        )
        self.assertIn('"workload": workload', script)
        self.assertIn("prepare_down_compose_environment()", script)
        self.assertIn("prepare_down_compose_environment\n  docker compose", script)
        self.assertIn("validate_local_gamma_image_composition()", script)
        self.assertIn('composition_args+=("$service" "$image_ref")', script)
        self.assertNotIn("source-provenance-required", script)
        self.assertNotIn(":down", script)
        self.assertIn(
            "api-edge:\n        condition: service_healthy",
            proxy,
        )
        self.assertNotIn("assistant-service:", proxy)
        self.assertNotIn("required: false", proxy)

    def test_local_gamma_content_release_accepts_empty_compose_profiles(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script = root / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        env = dict(os.environ)
        env.pop("COMPOSE_PROFILES", None)
        env.pop("LOCAL_GAMMA_RTC_SERVICE_IMAGE", None)
        env["QWQ_WORKLOAD"] = "content-release"
        env["LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL"] = (
            "https://upload.gamma.quwoquan.com:19100"
        )
        runtime = json.loads(
            (root / "quwoquan_ops/environments/gamma/runtime.yaml").read_text(
                encoding="utf-8"
            )
        )
        build_images = runtime["targets"]["gamma-local"]["buildImages"]
        env["LOCAL_GAMMA_GO_BASE_IMAGE"] = build_images["goBaseImage"]
        env["LOCAL_GAMMA_ALPINE_BASE_IMAGE"] = build_images["alpineBaseImage"]

        with tempfile.TemporaryDirectory() as output_root:
            env["QWQ_OUTPUT_ROOT"] = output_root
            result = subprocess.run(
                ["bash", str(script), "--print-env"],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertNotIn("unbound variable", result.stderr)
        self.assertNotIn("RTC_SERVICE_IMAGE must come", result.stderr)
        self.assertIn(
            "GATE_BLOCK: LOCAL_GAMMA_CONFIG_VERSION must be the canonical sha256 runtime configuration digest",
            result.stderr,
        )
        self.assertEqual(result.stdout, "")
        self.assertIn(
            'if [[ "$print_env" != "1" ]] && local_gamma_has_existing_stack; then',
            script.read_text(encoding="utf-8"),
        )

    def test_local_gamma_rejects_unbound_package_before_url_projection(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script = root / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        env = dict(os.environ)
        env["QWQ_WORKLOAD"] = "content-release"
        env.pop("LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL", None)

        with tempfile.TemporaryDirectory() as output_root:
            env["QWQ_OUTPUT_ROOT"] = output_root
            result = subprocess.run(
                ["bash", str(script), "--print-env"],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "GATE_BLOCK: LOCAL_GAMMA_CONFIG_VERSION must be the canonical sha256 runtime configuration digest",
            result.stderr,
        )
        self.assertNotIn("--dart-define=APP_RUNTIME_ENV=gamma", result.stdout)

    def test_local_gamma_product_ops_uses_required_runtime_auth(self) -> None:
        product_ops = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_service/services/product-ops-service/deploy/compose.yaml"
        ).read_text(encoding="utf-8")

        for name in (
            "AUTH_JWT_SECRET",
            "AUTH_JWT_ISSUER",
            "AUTH_JWT_AUDIENCE",
            "AUTH_JWT_TOKEN_VERSION",
        ):
            self.assertIn(f'{name}: "${{{name}:?{name} is required}}"', product_ops)

    def test_local_gamma_content_probe_methods_come_from_contract_graph(self) -> None:
        source = Path(local_gamma_t3.__file__).read_text(encoding="utf-8")

        self.assertIn('"quwoquan_data/scripts/cli.py"', source)
        self.assertIn('"ship"', source)
        self.assertIn('"verify"', source)
        self.assertNotIn("content_route_methods", source)
        self.assertNotIn("/content/comments", source)

    def test_local_gamma_blocked_operation_requires_metadata_enforced_403(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "t3-invalid-environment.json"
            with (
                mock.patch.object(
                    local_gamma_t3,
                    "resolve_readiness_path",
                    return_value=Path("/tmp/release-readiness.json"),
                ),
                mock.patch.object(
                    local_gamma_t3,
                    "load_release_content_identity",
                    side_effect=local_gamma_t3.ReleaseVideoDeliveryError(
                        "Data readiness environment='beta', expected 'gamma'"
                    ),
                ),
                mock.patch.object(local_gamma_t3, "run_release_consumer") as consumer,
                mock.patch.object(
                    local_gamma_t3,
                    "resolve_t3_report_path",
                    return_value=report_path,
                ),
                mock.patch.object(
                    local_gamma_t3.sys,
                    "argv",
                    [
                        "run_local_gamma_t3.py",
                        "--release-readiness",
                        "env/beta/release-readiness.json",
                        "--report",
                        str(report_path),
                    ],
                ),
            ):
                status = local_gamma_t3.main()

            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(status, 2)
        consumer.assert_not_called()
        self.assertEqual(report["status"], "gate_block")
        self.assertIn("expected 'gamma'", report["reason"])

    def test_local_gamma_blocked_operation_fails_if_it_unexpectedly_accepts(self) -> None:
        failed = subprocess.CompletedProcess(
            ["quwoquan_data/scripts/cli.py"],
            1,
            stdout="GATE_BLOCK: import receipt mismatch",
        )
        with mock.patch.object(
            local_gamma_t3.subprocess,
            "run",
            return_value=failed,
        ):
            result = local_gamma_t3.run_release_consumer(
                identity=_gamma_release_identity(),
            )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exitCode"], 1)
        self.assertIn("import receipt mismatch", result["outputTail"])

    def test_local_gamma_runtime_refs_keep_owner_and_persona_ids_distinct(self) -> None:
        with (
            mock.patch.dict(
                os.environ,
                {
                    "QWQ_DATA_RELEASE_ID": "parallel-release",
                    "QWQ_GAMMA_IMPORT_RUN_ID": "parallel-import",
                },
                clear=False,
            ),
            mock.patch.object(
                local_gamma_t3.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(["ship"], 0, stdout="ok"),
            ) as run,
        ):
            local_gamma_t3.run_release_consumer(identity=_gamma_release_identity())

        command = run.call_args.args[0]
        self.assertIn("release-gamma-a", command)
        self.assertIn("import-gamma-a", command)
        self.assertNotIn("parallel-release", command)
        self.assertNotIn("parallel-import", command)

    def test_local_gamma_comment_setup_uses_current_command_contract(self) -> None:
        source = Path(local_gamma_t3.__file__).read_text(encoding="utf-8")

        for retired in (
            "setup_comment_thread",
            "http_request",
            "Idempotency-Key",
            "attachmentMediaIds",
            "comment-parent",
        ):
            self.assertNotIn(retired, source)

    def test_local_gamma_social_graph_seed_binds_authenticated_persona(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script_path = (
            root
            / "quwoquan_service/services/content-service/cmd/jobs/seed-social-graph/main.py"
        )
        fixture_path = (
            root
            / "quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_social_graph.gamma_seed.json"
        )
        module = runpy.run_path(str(script_path))
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        mongo_script = module["build_mongo_script"](fixture, "persona-runtime")

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
            "backend": "local",
            "publicBases": {
                "api": "https://api.gamma.example.invalid",
                "productOps": "https://ops.gamma.example.invalid",
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
        self.assertNotIn("--resolve-host", kwargs["argv"])
        self.assertEqual(kwargs["env"]["TEST_AUTH_TOKEN"], "-starts-with-dash")
        self.assertEqual(kwargs["env"]["GAMMA_TEST_AUTH_TOKEN"], "-starts-with-dash")

    def test_run_environment_integration_probe_uses_canonical_dns_target(self) -> None:
        topology = {"targets": []}
        target = {
            "env": "beta",
            "backend": "local",
            "publicBases": {
                "api": "https://api.beta.quwoquan.com:18000",
                "productOps": "https://ops.beta.quwoquan.com:18010",
            },
        }

        with (
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch(
                "quwoquan_ops.cli.stackctl._resolve_test_auth_token",
                return_value="beta-bearer",
            ),
            mock.patch(
                "quwoquan_ops.cli.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
        ):
            stackctl._run_environment_integration_probe(
                topology,
                "beta-local",
                Path("/tmp/report"),
            )

        kwargs = run_probe.call_args.kwargs
        self.assertNotIn("--resolve-host", kwargs["argv"])
        self.assertEqual(kwargs["env"]["BETA_TEST_AUTH_TOKEN"], "beta-bearer")

    def test_report_feedback_probe_profile_commands_use_real_environment_modes(
        self,
    ) -> None:
        cases = (
            (
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
                "https://api.beta.quwoquan.com:18000",
                "local",
                "lifecycle",
            ),
            (
                "gamma",
                "gamma-local",
                VerificationProfile.RELEASE,
                "https://api.gamma.quwoquan.com:19000",
                "local",
                "lifecycle",
            ),
            (
                "prod",
                "prod-hosted",
                VerificationProfile.RELEASE,
                "https://api.quwoquan.com",
                "ssh-hosted",
                "read-only",
            ),
        )
        for (
            env_name,
            target_name,
            profile,
            api_base_url,
            backend,
            expected_mode,
        ) in cases:
            with (
                self.subTest(target=target_name),
                tempfile.TemporaryDirectory() as tmp_dir,
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": env_name,
                        "backend": backend,
                        "publicBases": {"api": api_base_url},
                    },
                ),
            ):
                command = stackctl._report_feedback_lifecycle_profile_command(
                    env_name,
                    target_name,
                    profile,
                    Path(tmp_dir),
                )

            self.assertIsNotNone(command)
            assert command is not None
            self.assertEqual(
                command["name"],
                f"{target_name}-report-feedback-lifecycle",
            )
            self.assertIn("--mode", command["argv"])
            self.assertEqual(
                command["argv"][command["argv"].index("--mode") + 1],
                expected_mode,
            )
            self.assertNotIn("--resolve-host", command["argv"])
            self.assertTrue(command["stopOnFailure"])
            self.assertNotIn("AUTH_TOKEN", " ".join(command["argv"]))

    def test_report_feedback_probe_is_not_added_to_unsupported_profiles(self) -> None:
        self.assertIsNone(
            stackctl._report_feedback_lifecycle_profile_command(
                "beta",
                "beta-local",
                VerificationProfile.SMOKE,
                None,
            )
        )
        self.assertIsNone(
            stackctl._report_feedback_lifecycle_profile_command(
                "prod",
                "prod-sim",
                VerificationProfile.RELEASE,
                None,
            )
        )

    def test_media_publication_probe_profile_commands_use_real_environment_modes(
        self,
    ) -> None:
        cases = (
            (
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
                "https://api.beta.quwoquan.com:18000",
                "local",
                "lifecycle",
            ),
            (
                "gamma",
                "gamma-local",
                VerificationProfile.RELEASE,
                "https://api.gamma.quwoquan.com:19000",
                "local",
                "lifecycle",
            ),
            (
                "prod",
                "prod-sim",
                VerificationProfile.INTEGRATION,
                "https://api.sim.quwoquan.com:20000",
                "local",
                "lifecycle",
            ),
            (
                "prod",
                "prod-hosted",
                VerificationProfile.RELEASE,
                "https://api.quwoquan.example",
                "ssh-hosted",
                "read-only",
            ),
        )
        for (
            env_name,
            target_name,
            profile,
            api_base_url,
            backend,
            expected_mode,
        ) in cases:
            moderation_base_url = {
                "beta-local": "http://127.0.0.1:18220",
                "gamma-local": "http://127.0.0.1:19220",
                "prod-sim": "http://127.0.0.1:20220",
            }.get(target_name, "")
            with (
                self.subTest(target=target_name),
                tempfile.TemporaryDirectory() as tmp_dir,
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": env_name,
                        "backend": backend,
                        "publicBases": {"api": api_base_url},
                        "origins": {"contentService": moderation_base_url}
                        if moderation_base_url
                        else {},
                    },
                ),
            ):
                command = stackctl._media_publication_lifecycle_profile_command(
                    env_name,
                    target_name,
                    profile,
                    Path(tmp_dir),
                )

            self.assertIsNotNone(command)
            assert command is not None
            self.assertEqual(
                command["name"],
                f"{target_name}-media-publication-lifecycle",
            )
            self.assertTrue(
                any(
                    str(item).endswith("run_media_publication_lifecycle_probe.py")
                    for item in command["argv"]
                )
            )
            self.assertEqual(
                command["argv"][command["argv"].index("--mode") + 1],
                expected_mode,
            )
            self.assertEqual(
                command["argv"][command["argv"].index("--target-name") + 1],
                target_name,
            )
            self.assertNotIn("--resolve-host", command["argv"])
            self.assertEqual(
                "--moderation-base-url" in command["argv"],
                expected_mode == "lifecycle",
            )
            if moderation_base_url:
                self.assertEqual(
                    command["argv"][
                        command["argv"].index("--moderation-base-url") + 1
                    ],
                    moderation_base_url,
                )
            self.assertTrue(command["stopOnFailure"])
            self.assertNotIn("AUTH_TOKEN", " ".join(command["argv"]))

    def test_media_publication_probe_is_not_added_to_unsupported_profiles(
        self,
    ) -> None:
        self.assertIsNone(
            stackctl._media_publication_lifecycle_profile_command(
                "beta",
                "beta-local",
                VerificationProfile.SMOKE,
                None,
            )
        )
        self.assertIsNone(
            stackctl._media_publication_lifecycle_profile_command(
                "prod",
                "prod-hosted",
                VerificationProfile.INTEGRATION,
                None,
            )
        )

    def test_chat_group_lifecycle_profile_commands_use_safe_environment_modes(
        self,
    ) -> None:
        cases = (
            (
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
                "https://api.beta.quwoquan.com:18000",
                "local",
                True,
            ),
            (
                "gamma",
                "gamma-local",
                VerificationProfile.RELEASE,
                "https://api.gamma.quwoquan.com:19000",
                "local",
                True,
            ),
            (
                "prod",
                "prod-hosted",
                VerificationProfile.RELEASE,
                "https://api.quwoquan.com",
                "ssh-hosted",
                False,
            ),
        )
        for (
            env_name,
            target_name,
            profile,
            api_base_url,
            backend,
            expect_mutating,
        ) in cases:
            with (
                self.subTest(target=target_name),
                tempfile.TemporaryDirectory() as tmp_dir,
                mock.patch.object(
                    stackctl,
                    "load_environment_topology",
                    return_value={},
                ),
                mock.patch.object(
                    stackctl,
                    "get_target",
                    return_value={
                        "env": env_name,
                        "backend": backend,
                        "publicBases": {"api": api_base_url},
                    },
                ),
            ):
                command = stackctl._chat_group_lifecycle_profile_command(
                    env_name,
                    target_name,
                    profile,
                    Path(tmp_dir),
                )

            self.assertIsNotNone(command)
            assert command is not None
            self.assertEqual(command["name"], f"{target_name}-chat-group-lifecycle")
            self.assertTrue(
                any(
                    str(item).endswith("run_chat_group_lifecycle_probe.py")
                    for item in command["argv"]
                )
            )
            self.assertIn("--require-nonempty-sources", command["argv"])
            self.assertEqual("--mutating" in command["argv"], expect_mutating)
            self.assertNotIn("--resolve-host", command["argv"])
            self.assertTrue(command["stopOnFailure"])
            self.assertNotIn("AUTH_TOKEN", " ".join(command["argv"]))

    def test_chat_group_lifecycle_probe_is_not_added_to_unsupported_profiles(
        self,
    ) -> None:
        self.assertIsNone(
            stackctl._chat_group_lifecycle_profile_command(
                "beta",
                "beta-local",
                VerificationProfile.SMOKE,
                None,
            )
        )
        self.assertIsNone(
            stackctl._chat_group_lifecycle_profile_command(
                "prod",
                "prod-sim",
                VerificationProfile.RELEASE,
                None,
            )
        )

    def test_stackctl_selected_profile_includes_chat_group_lifecycle_probe(self) -> None:
        target = {
            "env": "beta",
            "backend": "local",
            "publicBases": {"api": "https://api.beta.quwoquan.com:18000"},
            "origins": {"contentService": "http://127.0.0.1:18220"},
        }
        with (
            mock.patch.object(
                stackctl,
                "load_environment_topology",
                return_value={},
            ),
            mock.patch.object(stackctl, "get_target", return_value=target),
        ):
            commands = stackctl._selected_profile_commands(
                "beta",
                "beta-local",
                VerificationProfile.INTEGRATION,
                Path("/tmp/chat-group-lifecycle"),
            )

        command = next(
            item
            for item in commands
            if item["name"] == "beta-local-chat-group-lifecycle"
        )
        self.assertIn("--mutating", command["argv"])
        self.assertIn("--require-nonempty-sources", command["argv"])

    def test_gamma_validation_profiles_register_media_publication_probe(self) -> None:
        registry_path = (
            stackctl.ROOT
            / "quwoquan_ops"
            / "environments"
            / "gamma"
            / "validation_suites.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        case_id = "media_publication_lifecycle_api_probe"
        case = registry["smokeCases"][case_id]

        self.assertTrue(
            (stackctl.ROOT / case["path"]).is_file(),
            "registered media publication probe must be runnable",
        )
        self.assertEqual(case["runner"], "python")
        for profile_name in (
            "manual_full",
            "nightly_full",
            "release_candidate",
        ):
            self.assertIn(
                case_id,
                registry["profiles"][profile_name]["smokeCases"],
            )

    def test_run_environment_integration_probe_does_not_override_hosted_dns(self) -> None:
        topology = {"targets": []}
        target = {
            "env": "prod",
            "backend": "ssh-hosted",
            "publicBases": {
                "api": "https://api.quwoquan.com",
                "productOps": "https://product-ops.quwoquan.com",
            },
        }

        with (
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch(
                "quwoquan_ops.cli.stackctl._resolve_test_auth_token",
                return_value="prod-bearer",
            ),
            mock.patch(
                "quwoquan_ops.cli.stackctl._run_script_probe",
                return_value=({}, "", []),
            ) as run_probe,
        ):
            stackctl._run_environment_integration_probe(
                topology,
                "prod-hosted",
                Path("/tmp/report"),
            )

        self.assertNotIn("--resolve-host", run_probe.call_args.kwargs["argv"])

    def test_run_environment_integration_probe_mints_local_gamma_session(self) -> None:
        topology = {"targets": []}
        target = {
            "env": "gamma",
            "backend": "local",
            "publicBases": {
                "api": "https://api.gamma.quwoquan.com:19000",
                "productOps": "https://ops.gamma.example.invalid",
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
                "quwoquan_ops.cli.stackctl.open_local_acceptance_session",
                return_value=session,
            ) as login,
            mock.patch(
                "quwoquan_ops.cli.stackctl.resolve_running_local_deployment_work_root",
                return_value=Path("/tmp/gamma-deploy-work"),
            ),
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
            "https://api.gamma.quwoquan.com:19000",
            environment="gamma",
            target_name="gamma-local",
            deployment_work_root=Path("/tmp/gamma-deploy-work"),
        )
        kwargs = run_probe.call_args.kwargs
        self.assertNotIn("--test-auth-token", kwargs["argv"])
        self.assertEqual(kwargs["env"]["TEST_AUTH_TOKEN"], "ephemeral-local-bearer")
        self.assertEqual(
            kwargs["env"]["GAMMA_TEST_AUTH_TOKEN"],
            "ephemeral-local-bearer",
        )

    def test_verify_integration_never_starts_gamma_when_dependency_port_is_missing(self) -> None:
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
            ) as socket_probe,
        ):
            commands = stackctl._selected_profile_commands(
                "gamma",
                "gamma-local",
                VerificationProfile.INTEGRATION,
            )

        self.assertEqual(commands[0]["name"], "gamma-local-health-preflight")
        self.assertIn("health", commands[0]["argv"])
        self.assertNotIn("up", commands[0]["argv"])
        socket_probe.assert_not_called()

    def test_verify_integration_uses_read_only_health_when_runtime_ports_are_ready(self) -> None:
        manifest = stackctl.load_port_manifest()
        target = {"env": "gamma", "portProfile": "gamma-local"}

        with (
            mock.patch("quwoquan_ops.cli.stackctl.load_environment_topology", return_value={}),
            mock.patch("quwoquan_ops.cli.stackctl.get_target", return_value=target),
            mock.patch("quwoquan_ops.cli.stackctl.load_port_manifest", return_value=manifest),
            mock.patch("quwoquan_ops.cli.stackctl.socket_probe", return_value=True) as socket_probe,
        ):
            commands = stackctl._selected_profile_commands(
                "gamma",
                "gamma-local",
                VerificationProfile.INTEGRATION,
            )

        self.assertEqual(commands[0]["name"], "gamma-local-health-preflight")
        self.assertIn("health", commands[0]["argv"])
        self.assertNotIn("up", commands[0]["argv"])
        socket_probe.assert_not_called()

    def test_local_gamma_t3_uses_only_runtime_bearer_identity(self) -> None:
        source = Path(local_gamma_t3.__file__).read_text(encoding="utf-8")

        self.assertNotIn("Authorization", source)
        self.assertNotIn("Bearer", source)
        self.assertNotIn("X-Client-User-Id", source)
        self.assertNotIn("LocalGammaAcceptanceSession", source)
        self.assertIn("DATA_RELEASE_READINESS_RECEIPT", source)

    def test_local_gamma_t3_compose_command_uses_stack_project(self) -> None:
        source = Path(local_gamma_t3.__file__).read_text(encoding="utf-8")

        self.assertNotIn("docker", source)
        self.assertNotIn("compose_command", source)
        self.assertNotIn("mongodb", source)
        self.assertNotIn("mongosh", source)
        self.assertIn("quwoquan_data/scripts/cli.py", source)

    def test_local_gamma_t3_endpoint_checks_marks_scope_externals_out_of_scope(self) -> None:
        long_output = "discarded-prefix" + ("x" * 9000)
        with mock.patch.object(
            local_gamma_t3.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(["ship"], 1, stdout=long_output),
        ):
            result = local_gamma_t3.run_release_consumer(
                identity=_gamma_release_identity(),
            )

        self.assertEqual(len(result["outputTail"]), 8000)
        self.assertNotIn("discarded-prefix", result["outputTail"])
        self.assertEqual(result["status"], "failed")

    def test_local_gamma_t3_strict_endpoint_checks_uses_scope_runtime_refs(self) -> None:
        with (
            mock.patch.object(
                local_gamma_t3.sys,
                "argv",
                ["run_local_gamma_t3.py", "--enabled-domain", "content"],
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            local_gamma_t3.main()

        self.assertEqual(raised.exception.code, 2)

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
                mock.patch(
                    "quwoquan_ops.cli.stackctl._legal_static_command",
                    return_value=(
                        mock.Mock(returncode=0),
                        {"status": "ok", "issues": [], "exitCode": 0},
                    ),
                ),
                mock.patch("quwoquan_ops.cli.stackctl._load_release_state", return_value={}),
                mock.patch(
                    "quwoquan_ops.cli.stackctl._prod_plane_runtime_report",
                    return_value={
                        "composeFileExists": True,
                        "envFileExists": True,
                        "containerCount": 1,
                        "unit": {"enabled": True, "active": True},
                        "containers": [
                            {
                                "name": "quwoquan-plane-service",
                                "running": True,
                                "health": "healthy",
                            }
                        ],
                    },
                ),
            ):
                result = stackctl.command_doctor(args)
            self.assertEqual(result["exitCode"], 0)
            self.assertTrue(
                any("prod rollout release-state is missing" in item for item in result["details"])
            )

    def test_doctor_prod_target_blocks_invalid_legal_static_source(self) -> None:
        topology = {
            "targets": {
                "prod-sim": {
                    "env": "prod",
                    "backend": "local",
                    "portProfile": None,
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = mock.Mock(target="prod-sim", report_dir=tmp_dir)
            health_payload = {
                "exitCode": 0,
                "summary": "stackctl health prod-sim: healthy",
                "details": [],
                "reportDir": "tmp",
            }
            with (
                mock.patch(
                    "quwoquan_ops.cli.stackctl.load_environment_topology",
                    return_value=topology,
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.get_target",
                    return_value=topology["targets"]["prod-sim"],
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.command_health",
                    return_value=health_payload,
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl._legal_static_command",
                    return_value=(
                        mock.Mock(returncode=1),
                        {
                            "status": "failed",
                            "issues": ["owner.operatorName contains placeholder text"],
                            "exitCode": 1,
                        },
                    ),
                ),
            ):
                result = stackctl.command_doctor(args)

            self.assertEqual(result["exitCode"], 1)
            self.assertTrue(
                any("prod legal-static source is invalid" in item for item in result["details"])
            )
            self.assertTrue(
                any("owner.operatorName" in item for item in result["details"])
            )
            repair_plan = json.loads(
                (Path(tmp_dir) / "repair_plan.json").read_text(encoding="utf-8")
            )
            self.assertTrue(any("approved legal facts" in item for item in repair_plan["actions"]))

    def test_doctor_reports_missing_beta_deployment_prerequisite(self) -> None:
        topology = {
            "targets": {
                "beta-local": {
                    "env": "beta",
                    "backend": "local",
                    "portProfile": None,
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = mock.Mock(target="beta-local", report_dir=tmp_dir)
            health_payload = {
                "exitCode": 1,
                "summary": "stackctl health beta-local: failed",
                "details": [],
                "reportDir": "tmp",
            }
            with (
                mock.patch(
                    "quwoquan_ops.cli.stackctl.load_environment_topology",
                    return_value=topology,
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.get_target",
                    return_value=topology["targets"]["beta-local"],
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.load_product_telemetry_log_sink",
                    side_effect=RuntimeError(
                        "local provider credentials must not be written into the repository or .qwq_output"
                    ),
                ),
                mock.patch(
                    "quwoquan_ops.cli.stackctl.command_health",
                    return_value=health_payload,
                ),
            ):
                result = stackctl.command_doctor(args)

            self.assertEqual(result["exitCode"], 1)
            self.assertTrue(
                any("deployment prerequisite failed" in item for item in result["details"])
            )
            repair_plan = json.loads(
                (Path(tmp_dir) / "repair_plan.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                any("QWQ_DEPLOY_WORK_ROOT" in item for item in repair_plan["actions"])
            )
            self.assertFalse(
                any("restart-stack" in item for item in repair_plan["actions"])
            )


if __name__ == "__main__":
    unittest.main()
