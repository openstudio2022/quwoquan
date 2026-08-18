"""local gamma 启动编排、release 生命周期与配置身份合约。
"""
from __future__ import annotations

import yaml

from quwoquan_ops.tests.support.local_gamma_content_service_config_test_support import (
    CADDYFILE,
    COMPOSE_FILE,
    OBJECT_STORAGE_LIFECYCLE_FILE,
    PRODUCT_OPS_LOCAL_ES_COMPOSE_FILE,
    Path,
    RELEASE_CONSUMER_SCRIPT,
    ROOT,
    START_SCRIPT,
    importlib,
    json,
    mock,
    service_compose,
    tempfile,
    unittest,
)


class LocalGammaStartupReleaseLifecycleTest(unittest.TestCase):
    def test_skip_build_fails_before_compose_for_missing_provenance_image(self) -> None:
        start_script = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("docker image inspect", start_script)
        self.assertIn("GATE_BLOCK: packaged image is unavailable", start_script)
        self.assertIn('if [[ "$skip_build" == "1" ]]', start_script)

    def test_temporary_upload_lifecycle_is_bootstrapped_before_content_service(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        init_block = compose.split("  object-storage-init:\n", 1)[1].split(
            "\n  elasticsearch:\n", 1
        )[0]
        content_service_block = service_compose("content-service")
        lifecycle = json.loads(OBJECT_STORAGE_LIFECYCLE_FILE.read_text(encoding="utf-8"))

        self.assertIn(
            "${LOCAL_GAMMA_OBJECT_STORAGE_LIFECYCLE_FILE:?packaged object-storage lifecycle file is required}:"
            "/etc/qwq-object-storage/lifecycle.json:ro",
            init_block,
        )
        self.assertIn(
            "${LOCAL_GAMMA_LIVEKIT_CONFIG_FILE:?packaged LiveKit config file is required}:"
            "/etc/livekit/livekit.yaml:ro",
            compose,
        )
        self.assertIn(
            "SSL_CERT_FILE: /etc/ssl/certs/quwoquan-local-managed.crt",
            init_block,
        )
        self.assertIn(
            "${LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE:?LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE is required}:"
            "/etc/ssl/certs/quwoquan-local-managed.crt:ro",
            init_block,
        )
        self.assertIn(
            "mc ilm rule import \"qwq/${LOCAL_GAMMA_OBJECT_STORAGE_BUCKET}\" < "
            "/etc/qwq-object-storage/lifecycle.json",
            init_block,
        )
        self.assertIn("object-storage-init:\n        condition: service_completed_successfully", content_service_block)
        self.assertEqual(
            lifecycle,
            {
                "Rules": [
                    {
                        "ID": "expire-content-temporary-uploads-after-24h",
                        "Status": "Enabled",
                        "Filter": {"Prefix": "uploads/"},
                        "Expiration": {"Days": 1},
                    }
                ]
            },
        )

    def test_public_media_miss_uses_only_prefix_scoped_object_storage_origin(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        caddy = CADDYFILE.read_text(encoding="utf-8")
        init_block = compose.split("  object-storage-init:\n", 1)[1].split(
            "\n  livekit-sfu:\n", 1
        )[0]

        self.assertIn(
            'mc anonymous set download "qwq/${LOCAL_GAMMA_OBJECT_STORAGE_BUCKET}/media/$${media_kind}/s"',
            init_block,
        )
        self.assertIn(
            "for media_kind in avatar image video background attachment; do",
            init_block,
        )
        for private_prefix in ("uploads", "media/objects", "media/processed"):
            self.assertNotIn(f"/{private_prefix}", init_block)
        self.assertIn(
            "${LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE:?LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE is required}:"
            "/etc/caddy/tls/object-storage-ca.pem:ro",
            compose,
        )
        self.assertEqual(caddy.count("@object_store_public_slice not file {path}"), 3)
        self.assertEqual(
            caddy.count(
                "rewrite @object_store_public_slice /{$LOCAL_GAMMA_OBJECT_STORAGE_BUCKET}{uri}"
            ),
            3,
        )
        self.assertEqual(
            caddy.count(
                "reverse_proxy @object_store_public_slice "
                "https://object-storage:{$LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT}"
            ),
            3,
        )
        self.assertEqual(
            caddy.count(
                "tls_trust_pool file /etc/caddy/tls/object-storage-ca.pem"
            ),
            3,
        )
        self.assertEqual(
            caddy.count("tls_server_name {$QWQ_PUBLIC_UPLOAD_HOST}"),
            3,
        )
        for binding in (
            'QWQ_PUBLIC_UPLOAD_HOST: "${QWQ_PUBLIC_UPLOAD_HOST:?QWQ_PUBLIC_UPLOAD_HOST is required}"',
            'LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT: "${LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT:?LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT is required}"',
            'LOCAL_GAMMA_OBJECT_STORAGE_BUCKET: "${LOCAL_GAMMA_OBJECT_STORAGE_BUCKET:?LOCAL_GAMMA_OBJECT_STORAGE_BUCKET is required}"',
        ):
            self.assertIn(binding, compose)

    def test_local_single_node_search_is_not_blocked_by_colima_build_cache_watermark(self) -> None:
        service_block = PRODUCT_OPS_LOCAL_ES_COMPOSE_FILE.read_text(encoding="utf-8")

        self.assertIn(
            'cluster.routing.allocation.disk.threshold_enabled: "false"',
            service_block,
        )
        self.assertIn(
            "product-ops-elasticsearch-data:/usr/share/elasticsearch/data",
            service_block,
        )

    def test_user_service_uses_protected_nonprod_provider_bindings(self) -> None:
        service_block = service_compose("user-service")

        for credential in (
            "WECHAT_OAUTH_APP_ID",
            "WECHAT_OAUTH_APP_SECRET",
            "ALIPAY_OAUTH_APP_ID",
            "ALIPAY_OAUTH_APP_PRIVATE_KEY_PEM",
            "ALIPAY_OAUTH_PLATFORM_PUBLIC_KEY_PEM",
            "ALIPAY_OAUTH_MERCHANT_PID",
            "QQ_OAUTH_APP_ID",
            "ALIYUN_DYPNS_ACCESS_KEY_ID",
            "ALIYUN_DYPNS_ACCESS_KEY_SECRET",
        ):
            self.assertIn(f"{credential}:", service_block)
        self.assertNotIn("IDENTITY_ONE_TAP_FIXTURE_", service_block)
        self.assertNotIn("IDENTITY_SOCIAL_FIXTURE_", service_block)

    def test_assistant_service_uses_generated_binding_without_runtime_selector(self) -> None:
        service_block = service_compose("assistant-service")
        start_script = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn(
            'ASSISTANT_MODEL_API_KEY: "${ASSISTANT_MODEL_API_KEY:-}"',
            service_block,
        )
        for binding in (
            "ASSISTANT_MODEL_COMPLETION_URL:",
            "ASSISTANT_PUBLIC_SEARCH_URL:",
            "ASSISTANT_WEATHER_GEOCODING_URL:",
            "ASSISTANT_WEATHER_FORECAST_URL:",
            "ASSISTANT_FINANCE_CHART_URL:",
        ):
            self.assertIn(binding, service_block)
        for selector in (
            "ASSISTANT_MODEL_PROVIDER",
            "ASSISTANT_SEARCH_PROVIDER",
            "ALLOW_DETERMINISTIC_BETA",
        ):
            self.assertNotIn(selector, service_block)
            self.assertNotIn(selector, start_script)

    def test_entity_service_receives_the_shared_access_token_contract(self) -> None:
        service_block = service_compose("entity-service")
        start_script = START_SCRIPT.read_text(encoding="utf-8")

        for key in (
            "AUTH_JWT_SECRET",
            "AUTH_JWT_ISSUER",
            "AUTH_JWT_AUDIENCE",
            "AUTH_JWT_TOKEN_VERSION",
        ):
            required = f'{key}: "${{{key}:?{key} is required}}"'
            self.assertIn(required, service_block)
            self.assertIn(
                f'-e {key}="${{{key}:?{key} is required}}"',
                start_script,
            )

    def test_tag_service_receives_the_shared_auth_contract_on_all_local_runtimes(self) -> None:
        service_block = service_compose("tag-service")
        start_script = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("TAG_REDIS_GENERAL_ADDR: redis:6379", service_block)
        self.assertIn("-e TAG_REDIS_GENERAL_ADDR=redis:6379", start_script)
        for key in (
            "AUTH_JWT_SECRET",
            "AUTH_JWT_ISSUER",
            "AUTH_JWT_AUDIENCE",
            "AUTH_JWT_TOKEN_VERSION",
            "AUTH_DEVICE_TICKET_SECRET",
            "AUTH_DEVICE_TICKET_ISSUER",
            "AUTH_DEVICE_TICKET_AUDIENCE",
            "AUTH_DEVICE_TICKET_TOKEN_VERSION",
        ):
            required = f'{key}: "${{{key}:?{key} is required}}"'
            self.assertIn(required, service_block)
            self.assertIn(
                f'-e {key}="${{{key}:?{key} is required}}"',
                start_script,
            )

    def test_gamma_waits_for_tag_service_without_copying_owner_routes_into_caddy(self) -> None:
        gamma_compose = COMPOSE_FILE.read_text(encoding="utf-8")
        start_script = START_SCRIPT.read_text(encoding="utf-8")
        gamma_proxy = gamma_compose[
            gamma_compose.index("  gamma-proxy:") :
            gamma_compose.index("\n    environment:", gamma_compose.index("  gamma-proxy:"))
        ]

        self.assertIn("      api-edge:", gamma_proxy)
        self.assertIn("condition: service_healthy", gamma_proxy)
        self.assertNotIn("tag-service:", gamma_proxy)
        self.assertIn("gamma_full_workload_dependencies_ready", start_script)
        self.assertIn(
            'curl -fsS "http://127.0.0.1:${LOCAL_GAMMA_TAG_PORT:-19270}/healthz"',
            start_script,
        )
        self.assertIn(
            'if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then',
            start_script,
        )
        self.assertNotIn("seed_tag_service_data", start_script)
        self.assertNotIn("ENABLE_FIXTURE_SEEDS", start_script)

    def test_host_probe_services_attach_edge_publish_network(self) -> None:
        """default is internal:true; host/Colima probes need the edge bridge.

        The assertion reads the parsed service map rather than a literal text
        shape, because a registry entry may also carry the `profiles` gate that
        keeps a projected-away fragment from degrading into an image-less
        service. Gating changes which workloads start the service; it never
        changes that a started service must reach the host through `edge`.
        """
        gamma_compose = COMPOSE_FILE.read_text(encoding="utf-8")
        self.assertIn("internal: true", gamma_compose)
        self.assertIn("\n  edge:\n", gamma_compose)
        marker = (
            "# Host/Colima readiness probes hit these published ports through the edge"
        )
        self.assertIn(marker, gamma_compose)
        services = yaml.safe_load(gamma_compose)["services"]
        for service in (
            "user-service",
            "product-ops-service",
            "platform-ops-service",
            "integration-service",
            "notification-service",
            "tag-service",
        ):
            self.assertEqual(services[service]["networks"], ["default", "edge"])

    def test_product_ops_receives_local_elasticsearch_endpoint(self) -> None:
        service_block = service_compose("product-ops-service")
        start_script = START_SCRIPT.read_text(encoding="utf-8")

        key = "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT"
        self.assertIn(f'{key}: "${{{key}:-}}"', service_block)
        self.assertIn(f'-z "${{{key}:-}}"', start_script)
        self.assertIn(
            "QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE",
            start_script,
        )
        self.assertNotIn(
            "product-ops-service/deploy/local-elasticsearch.compose.yaml",
            start_script,
        )
        self.assertNotIn("PRODUCT_OPS_LOCAL_LOG_SINK", service_block)
        self.assertNotIn("PRODUCT_OPS_LOCAL_LOG_SINK", start_script)

    def test_gamma_startup_precreates_the_portal_mount_root(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('"${LOCAL_GAMMA_PORTAL_ROOT}"', source)
        self.assertIn(
            '"${LOCAL_GAMMA_PORTAL_ROOT}" \\\n'
            '  "${QWQ_OUTPUT_ROOT}/env/repo/local/control-plane/process/',
            source,
        )

    def test_gamma_startup_has_no_business_seed_proof_path(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn(
            "immutable release activation owns business data and search projections",
            source,
        )
        self.assertNotIn("seed_gamma_premium_pool_data", source)
        self.assertNotIn("seed_gamma_intersection_data", source)
        self.assertNotIn("seed_search_index", source)
        self.assertNotIn("fixture_user_current", source)
        self.assertNotIn("redis-cli --scan", source)
        self.assertNotIn("deleteMany", source)
        self.assertNotIn("insertMany", source)

    def test_gamma_startup_removes_only_non_running_named_residue(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("cleanup_stale_named_gamma_containers", source)
        self.assertIn(
            "unmanaged active container blocks canonical compose ownership",
            source,
        )
        self.assertIn("removing stale non-running container", source)
        release_branches = source.split(
            'if [[ "$formal_release" != "1" ]]; then', 1
        )[1]
        development_branch = release_branches.split("\n  else", 1)[0]
        formal_branch = release_branches.split("\n  else", 1)[1].split(
            "\n  ensure_docker_gamma_proxy_started", 1
        )[0]
        self.assertIn("cleanup_stale_named_gamma_containers", development_branch)
        self.assertNotIn("cleanup_stale_named_gamma_containers", formal_branch)

    def test_gamma_failure_log_dump_survives_service_core_projection(self) -> None:
        """candidate topology 把 11 个逻辑服务投影为 service-core;
        `docker compose logs` 对任一未知服务名整体拒绝执行,
        一次性多服务名单会把 up 失败的唯一日志证据全部丢掉。
        """
        source = START_SCRIPT.read_text(encoding="utf-8")

        # 旧的一次性多服务 dump 形态不得回归。
        self.assertNotIn("logs --tail 80 integration-service", source)
        self.assertNotIn(
            "logs --tail 120 \\\n"
            "        service-core user-service recommendation-service",
            source,
        )
        self.assertNotIn(
            "logs --tail 120 \\\n"
            "    gamma-proxy api-edge content-service",
            source,
        )
        # dump 必须以 config --services 为服务名真相源并逐服务执行,
        # 名单需同时覆盖投影形态(service-core)与 dev 形态(content-service 等)。
        self.assertIn(
            'teardown_available_services="$("${compose_cmd[@]}" config --services 2>/dev/null || true)"',
            source,
        )
        self.assertIn(
            "diagnostic_available_services=\"$(docker compose -p \"$LOCAL_GAMMA_COMPOSE_PROJECT_NAME\" "
            "\"${COMPOSE_FILE_ARGS[@]}\" config --services 2>/dev/null || true)\"",
            source,
        )
        for loop_member in ("service-core", "recommendation-service", "content-service"):
            for list_variable in ("teardown_log_service", "diagnostic_log_service"):
                block = source.split(f"for {list_variable} in \\", 1)[1].split("; do", 1)[0]
                self.assertIn(loop_member, block)
        self.assertIn(
            '"${compose_cmd[@]}" logs --tail 120 "$teardown_log_service" >&2 || true',
            source,
        )
        self.assertIn(
            'logs --tail 120 "$diagnostic_log_service" >&2 || true',
            source,
        )
        # 失败态健康检查 inspect 名单必须覆盖投影后的一方服务。
        inspect_list = source.split("for svc in ", 1)[1].split("; do", 1)[0]
        self.assertIn("service-core", inspect_list)
        self.assertIn("recommendation-service", inspect_list)

    def test_gamma_up_bootstraps_policy_owner_before_full_stack(self) -> None:
        """Gamma 冷启动 policy 死锁：投影拓扑 product-ops -> service-core(healthy)
        -> recommendation(healthy)，而 recommendation full runtime 又硬性要求
        Product Ops 已激活 rec_model_vs_rule。全栈 compose up 前必须先经
        loopback published port 用公开 command 激活 canonical 政策。
        """

        source = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("bootstrap_experiment_policy_owner() {", source)
        # bootstrap 必须在全栈 compose up 之前执行。
        bootstrap_call_index = source.index(
            'if [[ "$PRODUCT_OPS_REQUIRED" == "1" ]]; then\n'
            "    if ! bootstrap_experiment_policy_owner; then"
        )
        full_up_index = source.index(
            'if ! run_compose_up_with_timeout "${compose_up_args[@]}"; then'
        )
        self.assertLess(bootstrap_call_index, full_up_index)
        bootstrap_block = source.split("bootstrap_experiment_policy_owner() {", 1)[1]
        bootstrap_block = bootstrap_block.split(
            'if [[ "$PRODUCT_OPS_REQUIRED" == "1" ]]; then', 1
        )[0]
        # 投影后 product-ops 的启动依赖是 service-core healthy（死锁环），
        # bootstrap 必须以 --no-deps 独立启动 owner。
        self.assertIn(
            'up -d --no-build --no-deps product-ops-service',
            bootstrap_block,
        )
        # 激活只允许走公开 command 的 loopback 变体；禁止直写 Mongo/Redis。
        self.assertIn(
            "activate_search_experiment_policy_via_published_port",
            bootstrap_block,
        )
        self.assertNotIn("mongosh", bootstrap_block)
        self.assertNotIn("redis-cli", bootstrap_block)
        # owner 启动即 fail-fast 的网络依赖闭包：可写 replica-set primary、
        # healthy 的 Postgres/Redis，以及 Elasticsearch（telemetry ILM/index
        # 初始化重试耗尽后 exit 1）。基础设施集必须一次补齐。
        self.assertIn(
            "for bootstrap_service in mongodb mongo-init postgres redis elasticsearch; do",
            bootstrap_block,
        )
        self.assertIn('"${compose_cmd[@]}" ps -aq mongo-init', bootstrap_block)
        self.assertIn(
            "for bootstrap_service in postgres redis elasticsearch; do",
            bootstrap_block,
        )
        # Elasticsearch 冷启动可超 8 分钟；等待期限必须沿用 compose up 的
        # 有界超时而不是通用 180s。
        self.assertIn(
            'deadline=$((SECONDS + ${LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS:?'
            "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS is required}))",
            bootstrap_block,
        )
        # 收据必须落入 run attachments 以供 up receipt 审计。
        self.assertIn(
            'bootstrap_receipt="${QWQ_RUN_ROOT}/attachments/experiment-policy-owner-bootstrap.json"',
            bootstrap_block,
        )

    def test_gamma_explicit_service_selections_survive_service_core_projection(
        self,
    ) -> None:
        """candidate 投影把 core 逻辑服务合并为 service-core；content-slice up
        名单与 compose build 名单必须经投影映射，否则 docker compose 对任一
        未知服务名整体拒绝执行（no such service）。
        """

        source = START_SCRIPT.read_text(encoding="utf-8")

        # core 模块集合必须来自 canonical 组合真相源，不得在脚本内再抄名单。
        self.assertIn(
            "from quwoquan_ops.cli.lib.service_core_composition import SERVICE_CORE_MODULE_SET",
            source,
        )
        self.assertIn("project_first_party_service_selection() {", source)
        self.assertIn(
            'AVAILABLE_COMPOSE_SERVICES="$("${compose_cmd[@]}" config --services 2>/dev/null || true)"',
            source,
        )
        # content-slice up 名单必须经投影映射后再进入 compose up 参数。
        self.assertIn(
            'project_first_party_service_selection "${content_slice_up_services[@]}"',
            source,
        )
        self.assertNotIn(
            "compose_up_args+=(\n    recommendation-service\n    content-service",
            source,
        )
        # build/镜像校验名单必须经同一映射。
        self.assertIn(
            'project_first_party_service_selection "${compose_build_services[@]}"',
            source,
        )

    def test_gamma_compose_failure_is_never_downgraded_to_readiness_warning(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn(
            "compose up failed; runtime readiness cannot be inferred from partial containers",
            source,
        )
        self.assertNotIn(
            "compose up reported a startup error; deferring to host readiness probes",
            source,
        )
        self.assertNotIn("compose_up_failed", source)
        self.assertNotIn("ensure_docker_gamma_proxy_started || true\nfi", source)

    def test_gamma_config_root_uses_flat_autonomous_service_packages(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('config_file="${package_dir}/config/config.yaml"', source)
        self.assertIn('cp "$config_file" "$out/${service}.yaml"', source)
        self.assertIn('provenance.get("configVersion")', source)
        self.assertNotIn("releases/config", source)

    def test_gamma_configuration_identity_is_digest_only_and_fail_closed(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")
        verifier = (
            ROOT
            / "quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'CONFIG_VERSION="${LOCAL_GAMMA_CONFIG_VERSION:-}"',
            source,
        )
        self.assertIn(
            "LOCAL_GAMMA_CONFIG_VERSION must be the canonical sha256 runtime configuration digest",
            source,
        )
        self.assertIn(
            '[[ ! "$CONFIG_VERSION" =~ ^sha256:[0-9a-f]{64}$ ]]',
            source,
        )
        self.assertIn(
            '[[ "$packaged_configuration_digest" != "$CONFIG_VERSION" ]]',
            source,
        )
        self.assertNotIn("local-gamma-v1", source)
        self.assertNotIn("local-gamma-down", source)
        self.assertIn('"--configuration-digest"', verifier)
        self.assertIn('"configurationDigest": args.configuration_digest', verifier)
        self.assertNotIn("local-gamma-v1", verifier)
        self.assertNotIn('"--config-version"', verifier)

    def test_release_consumer_rejects_reports_in_mutable_local_runtime_state(self) -> None:
        spec = importlib.util.spec_from_file_location("local_gamma_release_consumer_report_path_test", RELEASE_CONSUMER_SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "output"
            allowed = (
                output_root
                / "env"
                / "gamma"
                / "runs"
                / "release-consumer"
                / "release_consumer.json"
            )
            forbidden = (
                output_root
                / "env"
                / "gamma"
                / "local"
                / "gamma-local"
                / "release_consumer_forbidden.json"
            )
            with mock.patch.dict(
                module.os.environ,
                {"QWQ_OUTPUT_ROOT": str(output_root)},
            ):
                self.assertEqual(module.default_release_consumer_report_path(), allowed)
                self.assertEqual(
                    module.resolve_release_consumer_report_path(str(allowed)),
                    allowed.resolve(),
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "QWQ_OUTPUT_ROOT/env/gamma/runs",
                ):
                    module.resolve_release_consumer_report_path(str(forbidden))

