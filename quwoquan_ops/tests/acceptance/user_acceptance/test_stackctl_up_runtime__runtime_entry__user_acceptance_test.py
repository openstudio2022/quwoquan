# spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-004
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-003
"""场景：stackctl up/status/repair 运行时入口——beta content-release 启动依赖、
gamma FilterCatalog 只读边界、CLI parser、健康 scope、telemetry advisory 与
兼容入口/重启修复语义。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl


class StackctlUpRuntimeTest(unittest.TestCase):
    def test_beta_content_release_starts_all_declared_readiness_dependencies(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script = (
            root
            / "quwoquan_app/scripts/tools/device/beta_manual_app.sh"
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
        self.assertIn("quwoquan_ops/cli/stackctl.py", beta_stack_script)
        self.assertIn("--target beta-local", beta_stack_script)
        self.assertNotIn("APP_BETA_CMD", beta_stack_script)
        self.assertNotIn("go run", beta_stack_script)
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

    def test_gamma_runtime_does_not_mutate_or_gate_on_filter_catalog_release(self) -> None:
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
        self.assertIn("wait_local_gamma_host_ready", startup_script)
        self.assertIn(
            "FilterCatalog release is an explicit post-start release gate",
            startup_script,
        )
        self.assertNotIn("filter-catalog --target", startup_script)
        self.assertNotIn(
            'filter-catalog --target "$QWQ_LOCAL_RELEASE_TARGET" --action stage-and-activate',
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

    def test_parser_accepts_bounded_content_commercial_workload(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "up",
                "--env",
                "alpha",
                "--workload",
                "content-commercial",
                "--skip-build",
                "--skip-app",
            ]
        )

        self.assertEqual(args.workload, "content-commercial")

    def test_status_uses_content_consumer_scope_for_current_content_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            process_dir = Path(tmp_dir) / "process"
            process_dir.mkdir()
            health_payload = {"exitCode": 0, "summary": "content release ready"}
            with (
                mock.patch.object(stackctl, "target_process_dir", return_value=process_dir),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={
                        "status": "running",
                        "target": "beta-local",
                        "env": "beta",
                        "workload": "content-release",
                        "composeProject": "quwoquan_beta_release",
                        "configurationDigest": "sha256:" + "1" * 64,
                        "providerRuntimeDigest": "sha256:" + "3" * 64,
                        "imageTransportTag": "sha256:" + "2" * 64,
                    },
                ),
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

    def test_status_uses_bounded_commercial_scope_for_current_content_commercial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            process_dir = Path(tmp_dir) / "process"
            process_dir.mkdir()
            health_payload = {"exitCode": 0, "summary": "content commercial ready"}
            with (
                mock.patch.object(stackctl, "target_process_dir", return_value=process_dir),
                mock.patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value={
                        "status": "running",
                        "target": "beta-local",
                        "env": "beta",
                        "workload": "content-commercial",
                        "composeProject": "quwoquan_beta_release",
                        "configurationDigest": "sha256:" + "1" * 64,
                        "providerRuntimeDigest": "sha256:" + "3" * 64,
                        "imageTransportTag": "sha256:" + "2" * 64,
                    },
                ),
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(stackctl, "get_target", return_value={"env": "beta"}),
                mock.patch.object(stackctl, "resolve_report_dir", return_value=Path(tmp_dir) / "report"),
                mock.patch.object(stackctl, "command_health", return_value=health_payload) as health,
            ):
                result = stackctl.command_status(
                    argparse.Namespace(target="beta-local", output_format="text", report_dir="")
                )

        self.assertEqual(result, health_payload)
        self.assertEqual(health.call_args.args[0].scope, "content-commercial")

    def test_gamma_status_ignores_noncanonical_completed_workload_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            process_dir = Path(tmp_dir) / "process"
            process_dir.mkdir()
            (process_dir / "stack_status.json").write_text(
                json.dumps({"status": "passed", "workload": "content-release"}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(stackctl, "target_process_dir", return_value=process_dir),
                mock.patch.object(stackctl, "load_startup_attempt", return_value=None),
            ):
                scope = stackctl._current_runtime_health_scope("gamma-local")

        self.assertEqual(scope, "full")

    def test_app_startup_treats_missing_log_sink_as_non_blocking_advisory(self) -> None:
        with mock.patch.object(
            stackctl,
            "_load_active_product_telemetry_log_sink",
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
            "_load_active_product_telemetry_log_sink",
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

    def test_beta_compatibility_entry_dispatches_only_to_stackctl(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script = root / "quwoquan_ops/cli/beta/start_beta_stack.sh"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            capture_path = temp_path / "python-args.txt"
            fake_python = temp_path / "python3"
            fake_python.write_text(
                '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$QWQ_CAPTURE_ARGS"\n',
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{temp_path}:{os.environ.get('PATH', '')}",
                "QWQ_CAPTURE_ARGS": str(capture_path),
                "QWQ_OUTPUT_ROOT": str(temp_path / "output"),
            }

            cases = (
                (
                    ("up", "--skip-app"),
                    ("up", "--target", "beta-local", "--skip-app"),
                ),
                (
                    ("down", "--workload", "full"),
                    ("down", "--target", "beta-local", "--workload", "full"),
                ),
                (
                    ("status", "--scope", "config"),
                    (
                        "inspect",
                        "--target",
                        "beta-local",
                        "--kind",
                        "all",
                        "--scope",
                        "config",
                    ),
                ),
            )
            for arguments, expected_tail in cases:
                result = subprocess.run(
                    ["bash", str(script), *arguments],
                    cwd=root,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                captured = capture_path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(
                    Path(captured[0]),
                    root / "quwoquan_ops/cli/stackctl.py",
                )
                self.assertEqual(tuple(captured[1:]), expected_tail)

    def test_repair_restart_stack_supplies_complete_noninteractive_up_args(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value={"env": "gamma"}),
            mock.patch.object(stackctl, "resolve_report_dir", return_value=Path(tmp_dir)),
            mock.patch.object(
                stackctl,
                "_load_active_product_telemetry_log_sink",
            ),
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
                    "_load_active_product_telemetry_log_sink",
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

    def test_repair_restart_stack_never_starts_after_down_failure(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            mock.patch.object(stackctl, "load_environment_topology", return_value={}),
            mock.patch.object(stackctl, "get_target", return_value={"env": "gamma"}),
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(tmp_dir),
            ),
            mock.patch.object(
                stackctl,
                "_load_active_product_telemetry_log_sink",
            ),
            mock.patch.object(
                stackctl,
                "command_down",
                return_value={"exitCode": 2, "summary": "down failed"},
            ),
            mock.patch.object(stackctl, "command_up") as command_up,
        ):
            result = stackctl.command_repair(
                argparse.Namespace(
                    command="repair",
                    target="gamma-local",
                    fix="restart-stack",
                    report_dir="",
                )
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertIn("down failure", result["summary"])
        command_up.assert_not_called()

    def test_format_stage_header(self) -> None:
        self.assertEqual(stackctl._format_stage_header(2, 3, "app-launch"), "[step 2/3] app-launch")


if __name__ == "__main__":
    unittest.main()
