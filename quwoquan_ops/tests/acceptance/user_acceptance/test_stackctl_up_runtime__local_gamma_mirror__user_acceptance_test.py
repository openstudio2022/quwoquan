# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-003
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-004
"""场景：local gamma mirror 启动脚本约束——print-env 早退与精确 candidate 门、
无环境业务 seed 路径、release-owned 媒体、compose created-only 重试、bounded
content workload 服务切片与 product-ops 运行时鉴权。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class StackctlUpRuntimeTest(unittest.TestCase):
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
        self.assertIn(
            "transactional teardown will preserve the receipt",
            script,
        )
        self.assertIn("write_startup_attempt partial", script)
        self.assertIn("write_startup_attempt running", script)
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

    def test_local_gamma_content_release_excludes_out_of_scope_assistant(self) -> None:
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
        bounded_content_services = script.split(
            "content_slice_services=(", 1
        )[1].split("\n  )", 1)[0]

        self.assertIn('profiles: ["assistant-runtime"]', assistant)
        self.assertIn(
            "commercial-observability,assistant-runtime,edge-media",
            script,
        )
        self.assertIn(
            'if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then',
            script,
        )
        self.assertIn("content_slice_services=(", script)
        for service_name in (
            "api-edge",
            "recommendation-service",
            "content-service",
            "user-service",
            "entity-service",
        ):
            self.assertIn(service_name, script)
        self.assertIn(
            'COMPOSE_FILES+=("$service_compose_file")',
            script,
        )
        self.assertIn(
            'COMPOSE_FILES+=("$ROOT/quwoquan_service/control-plane/platform-ops/deploy/compose.yaml")',
            script,
        )
        self.assertIn(
            '[[ "$service_name" == "assistant-service" ]] ||',
            script,
        )
        self.assertIn("content_slice_services+=(product-ops-service)", script)
        self.assertIn("PRODUCT_OPS_REQUIRED=1", script)
        self.assertIn("PRODUCT_TELEMETRY_AVAILABLE=0", script)
        self.assertIn("compose_up_args+=(product-ops-service)", script)
        self.assertIn("compose_up_args+=(api-edge gamma-proxy)", script)
        self.assertIn(
            "bounded content workloads require canonical Docker Compose service slicing",
            script,
        )
        self.assertIn("gamma_full_workload_dependencies_ready", script)
        self.assertIn("--provider-runtime-digest", script)
        self.assertIn("prepare_down_compose_environment()", script)
        self.assertIn("prepare_down_compose_environment\n  down_args=(down)", script)
        self.assertIn('"${COMPOSE_FILE_ARGS[@]}" "${down_args[@]}"', script)
        self.assertIn("validate_local_gamma_image_composition()", script)
        self.assertIn('composition_args+=("$service" "$image_ref")', script)
        self.assertNotIn("source-provenance-required", script)
        self.assertNotIn(":down", script)
        self.assertIn(
            "api-edge:\n        condition: service_healthy",
            proxy,
        )
        self.assertNotIn("assistant-service", bounded_content_services)
        self.assertNotIn("required: false", proxy)

    def test_local_gamma_print_env_requires_exact_candidate_before_profiles(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script = root / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        env = dict(os.environ)
        env.pop("COMPOSE_PROFILES", None)
        env.pop("LOCAL_GAMMA_RTC_SERVICE_IMAGE", None)
        env["QWQ_WORKLOAD"] = "content-release"
        env["QWQ_PROVIDER_RUNTIME_DIGEST"] = "sha256:" + "a" * 64
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
            "GATE_BLOCK: exact runtime candidate root is required",
            result.stderr,
        )
        self.assertNotIn("LOCAL_GAMMA_CONFIG_VERSION", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn(
            'if [[ "$print_env" != "1" ]] && local_gamma_has_existing_stack; then',
            script.read_text(encoding="utf-8"),
        )

    def test_local_gamma_rejects_unbound_candidate_before_url_projection(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script = root / "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        env = dict(os.environ)
        env["QWQ_WORKLOAD"] = "content-release"
        env["QWQ_PROVIDER_RUNTIME_DIGEST"] = "sha256:" + "a" * 64
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
            "GATE_BLOCK: exact runtime candidate root is required",
            result.stderr,
        )
        self.assertNotIn("LOCAL_GAMMA_CONFIG_VERSION", result.stderr)
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

    def test_local_gamma_social_graph_seed_and_fixture_are_retired(self) -> None:
        root = Path(__file__).resolve().parents[4]
        script_path = (
            root
            / "quwoquan_service/services/content-service/cmd/jobs/seed-social-graph/main.py"
        )
        fixture_path = (
            root
            / "quwoquan_service/contracts/metadata/_shared/test_fixtures/content_recommendation_social_graph.gamma_seed.json"
        )
        self.assertFalse(script_path.exists())
        self.assertFalse(fixture_path.exists())


if __name__ == "__main__":
    unittest.main()
