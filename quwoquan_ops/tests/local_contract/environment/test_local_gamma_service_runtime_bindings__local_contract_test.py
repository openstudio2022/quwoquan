"""local gamma 各服务 runtime 绑定、依赖健康与镜像来源合约。
"""
from __future__ import annotations

from quwoquan_ops.tests.support.local_gamma_content_service_config_test_support import (
    CADDYFILE,
    COMPOSE_FILE,
    CONTENT_GAMMA_COMPOSE_FILE,
    CONTENT_SERVICE_ROOT,
    PRODUCT_OPS_LOCAL_ES_COMPOSE_FILE,
    RELEASE_CONSUMER_SCRIPT,
    ROOT,
    START_SCRIPT,
    _compose_build_environment,
    content_environment_compose,
    gamma_compose_files,
    get_target,
    load_environment_topology,
    service_compose,
    unittest,
    yaml,
)


class LocalGammaServiceRuntimeBindingsTest(unittest.TestCase):
    def test_alpha_content_release_derives_build_images_from_environment_policy(self) -> None:
        target = get_target(load_environment_topology(), "alpha-local")
        build_images = target["buildImages"]

        self.assertEqual(
            _compose_build_environment(),
            {
                "QWQ_COMPOSE_GO_BASE_IMAGE": build_images["goBaseImage"],
                "QWQ_COMPOSE_ALPINE_BASE_IMAGE": build_images["alpineBaseImage"],
                "QWQ_COMPOSE_PUBLIC_WEB_BASE_URL": (
                    "https://alpha.quwoquan.com:17000"
                ),
                "QWQ_COMPOSE_MEDIA_AVATAR_BASE_URL": (
                    "https://cdn.alpha.quwoquan.com:17100/media/avatar"
                ),
                "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL": (
                    "https://cdn.alpha.quwoquan.com:17100"
                ),
                "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL": (
                    "https://upload.alpha.quwoquan.com:17130"
                ),
            },
        )

    def test_release_consumer_runtime_is_a_read_only_release_consumer(self) -> None:
        source = RELEASE_CONSUMER_SCRIPT.read_text(encoding="utf-8")

        for retired in (
            "setup_runtime_fixtures",
            "setup_comment_thread",
            "seed_content_moment_channel",
            "seed_content_social_graph",
            "seed_content_object_cards",
            "mongosh",
        ):
            self.assertNotIn(retired, source)
        self.assertIn("quwoquan_data/scripts/cli.py", source)
        self.assertIn('"ship"', source)
        self.assertIn('"verify"', source)
        for mutating_command in ('"import"', '"publish"', '"activate"', '"seed"'):
            self.assertNotIn(mutating_command, source)

    def test_content_release_consumer_identity_is_owned_by_canonical_readiness_receipt(
        self,
    ) -> None:
        source = RELEASE_CONSUMER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("load_release_content_identity", source)
        self.assertIn("resolve_readiness_path", source)
        self.assertIn('expected_environment="gamma"', source)
        for field in (
            "releaseId",
            "importRunId",
            "verifyRunId",
        ):
            self.assertIn(f'identity["{field}"]', source)
        self.assertNotIn('parser.add_argument("--release-id"', source)
        self.assertNotIn('parser.add_argument("--import-run-id"', source)
        self.assertNotIn('parser.add_argument("--verification-run-id"', source)

    def test_user_release_consumer_does_not_provision_contact_discovery(
        self,
    ) -> None:
        source = RELEASE_CONSUMER_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("provision_contact_discovery", source)
        self.assertNotIn("hashedPhones", source)
        self.assertNotIn("_ACTIVE_SESSION", source)

    def test_core_readback_does_not_mint_anonymous_identity_in_release_consumer(
        self,
    ) -> None:
        source = RELEASE_CONSUMER_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("open_public_anonymous_session", source)
        self.assertNotIn("LocalGammaAcceptanceSession", source)
        self.assertNotIn("/auth/login", source)
        self.assertNotIn("accessToken", source)

    def test_core_readback_does_not_provision_chat_inbox_in_release_consumer(self) -> None:
        source = RELEASE_CONSUMER_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("provision_chat_core_readback", source)
        self.assertNotIn("/chat/conversations", source)
        self.assertNotIn("runtime-message", source)
        self.assertNotIn("http_request", source)

    def test_content_service_declares_all_required_runtime_bindings(self) -> None:
        service_block = service_compose("content-service")

        for binding in (
            "CONTENT_MONGO_URI:",
            "CONTENT_POSTGRES_REPORT_DSN:",
            "CONTENT_REDIS_REC_ADDR:",
            "CONTENT_REDIS_GENERAL_ADDR:",
            "CONTENT_REDIS_REALTIME_ADDR:",
            "CONTENT_OSS_ENDPOINT:",
            "CONTENT_OSS_BUCKET:",
            "CONTENT_OSS_REGION:",
            "CONTENT_OSS_ACCESS_KEY_ID:",
            "CONTENT_OSS_ACCESS_KEY_SECRET:",
            "CONTENT_MEDIA_DELIVERY_BASE_URL:",
            "CONTENT_MEDIA_UPLOAD_BASE_URL:",
            "CONTENT_CDN_SIGN_KEY:",
            "SEARCH_ES_ENABLED:",
            "SEARCH_ES_ENDPOINTS:",
            "CONTENT_REC_MODEL_SERVICE_ENABLED:",
            "CONTENT_REC_MODEL_SERVICE_URL:",
        ):
            self.assertIn(binding, service_block)
        self.assertIn(
            'CONTENT_REC_MODEL_SERVICE_ENABLED: "${QWQ_COMPOSE_REC_MODEL_SERVICE_ENABLED:-true}"',
            service_block,
        )

        self.assertNotIn("SSL_CERT_FILE:", service_block)
        self.assertNotIn("object-storage-ca.crt", service_block)

    def test_local_environment_overlays_own_required_elasticsearch_dependency(self) -> None:
        content = service_compose("content-service")
        search = service_compose("search-service")
        entity = service_compose("entity-service")
        circle = service_compose("circle-service")
        expected = "elasticsearch:\n        condition: service_healthy"
        self.assertNotIn(expected, content)
        for environment in ("alpha", "beta", "gamma"):
            with self.subTest(environment=environment):
                environment_overlay = content_environment_compose(environment).read_text(
                    encoding="utf-8"
                )
                for dependency, condition in (
                    ("mongodb", "service_healthy"),
                    ("mongo-init", "service_completed_successfully"),
                    ("object-storage-init", "service_completed_successfully"),
                    ("redis", "service_healthy"),
                    ("recommendation-service", "service_healthy"),
                    ("elasticsearch", "service_healthy"),
                ):
                    self.assertIn(
                        f"{dependency}:\n        condition: {condition}",
                        environment_overlay,
                    )
                self.assertNotIn("sleep ", environment_overlay)
                self.assertIn(
                    "x-qwq-workloads: [full, content-commercial]",
                    environment_overlay,
                )
                environment_config = (
                    CONTENT_SERVICE_ROOT
                    / "environments"
                    / environment
                    / "config.yaml"
                ).read_text(encoding="utf-8")
                self.assertIn("sys.content-service.es.enabled: true", environment_config)
        schema = yaml.safe_load(
            (CONTENT_SERVICE_ROOT / "config" / "schema.yaml").read_text(
                encoding="utf-8"
            )
        )
        defaults = {
            entry["key"]: entry.get("default")
            for entry in schema["configs"]
        }
        self.assertEqual(
            defaults["sys.content-service.es.startupTimeoutMs"],
            60000,
        )
        self.assertEqual(
            defaults["sys.content-service.es.startupInitialBackoffMs"],
            100,
        )
        self.assertEqual(
            defaults["sys.content-service.es.startupMaxBackoffMs"],
            2000,
        )
        for environment in ("alpha", "beta", "gamma", "prod"):
            with self.subTest(environment_config=environment):
                overrides = yaml.safe_load(
                    (
                        CONTENT_SERVICE_ROOT
                        / "environments"
                        / environment
                        / "config.yaml"
                    ).read_text(encoding="utf-8")
                )["overrides"]
                for key in (
                    "sys.content-service.es.startupTimeoutMs",
                    "sys.content-service.es.startupInitialBackoffMs",
                    "sys.content-service.es.startupMaxBackoffMs",
                ):
                    self.assertNotIn(key, overrides)
        for block in (search, entity, circle):
            self.assertIn(expected, block)

    def test_elasticsearch_dependency_wait_is_health_bounded_not_blind_sleep(self) -> None:
        service_block = PRODUCT_OPS_LOCAL_ES_COMPOSE_FILE.read_text(encoding="utf-8")

        self.assertIn("curl -fsS 'http://localhost:9200/_ilm/status'", service_block)
        for bounded_setting in (
            "interval: 10s",
            "timeout: 5s",
            "start_period: 1200s",
            "retries: 60",
        ):
            self.assertIn(bounded_setting, service_block)
        self.assertNotIn("sleep ", service_block)

    def test_gamma_redis_health_requires_ready_command_processing(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")

        self.assertIn(
            'test: ["CMD-SHELL", "redis-cli --raw ping | grep -qx PONG"]',
            compose,
        )
        self.assertNotIn('test: ["CMD", "redis-cli", "ping"]', compose)

    def test_mongo_init_waits_for_writable_primary_before_dependents(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")

        mongodb = yaml.safe_load(compose)["services"]["mongodb"]
        self.assertEqual(mongodb["healthcheck"]["timeout"], "10s")
        self.assertIn("db.hello().isWritablePrimary", compose)
        self.assertIn("mongo-init timed out waiting for writable primary", compose)
        self.assertIn(
            "recommendation-service:\n"
            "    depends_on:\n"
            "      mongo-init:\n"
            "        condition: service_completed_successfully",
            compose,
        )

    def test_package_owns_elasticsearch_architecture_selection(self) -> None:
        """canonical ES workload 是 CJK 插件镜像（analysis-ik/analysis-pinyin，
        specs/feature-tree/global-search-experience/design.md#dec-002）；
        架构/JVM 选择由 packaging 真相源 x-qwq-package-elasticsearch 拥有，
        启动脚本不得再做架构或镜像选择。禁止倒退回无 CJK 插件的官方镜像。
        """

        compose = PRODUCT_OPS_LOCAL_ES_COMPOSE_FILE.read_text(encoding="utf-8")
        script = START_SCRIPT.read_text(encoding="utf-8")
        cjk_image = "quwoquan/elasticsearch-cjk:8.13.4"
        retired_official_repository = "docker.elastic.co/elasticsearch/elasticsearch"

        self.assertNotIn("platform: linux/amd64", compose)
        self.assertIn(
            'image: "${QWQ_COMPOSE_ELASTICSEARCH_IMAGE:-' + cjk_image + '}"',
            compose,
        )
        self.assertNotIn(retired_official_repository, compose)
        self.assertIn(
            "CLI_JAVA_OPTS: \"${QWQ_COMPOSE_ELASTICSEARCH_CLI_JAVA_OPTS:-}\"",
            compose,
        )
        self.assertIn(
            "ES_JAVA_OPTS: \"${QWQ_COMPOSE_ELASTICSEARCH_JAVA_OPTS:--Xms512m -Xmx512m}\"",
            compose,
        )
        self.assertIn("x-qwq-package-elasticsearch:", compose)
        # packaging 真相源必须为两个目标架构都声明 CJK 镜像。
        packaging_block = compose.split("x-qwq-package-elasticsearch:", 1)[1].split(
            "services:", 1
        )[0]
        self.assertIn("arm64:", packaging_block)
        self.assertIn("amd64:", packaging_block)
        self.assertEqual(packaging_block.count(f'image: "{cjk_image}"'), 2)
        self.assertNotIn('case "$(uname -m)" in', script)
        self.assertNotIn(cjk_image, script)
        self.assertNotIn(retired_official_repository, script)
        self.assertIn("QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE", script)
        self.assertIn("QWQ_OBSERVABILITY_LOG_SINK_DIGEST", script)
        self.assertNotIn("LOCAL_GAMMA_ELASTICSEARCH_IMAGE", script)
        self.assertNotIn("--platform=linux/amd64", script)
        self.assertNotIn("QWQ_COMPOSE_ELASTICSEARCH_IMAGE", script)

    def test_gamma_runtime_applies_service_owned_content_overlay_after_base(self) -> None:
        compose_files = gamma_compose_files(ROOT)
        content_base = (
            ROOT / "quwoquan_service/services/content-service/deploy/compose.yaml"
        )

        self.assertIn(CONTENT_GAMMA_COMPOSE_FILE, compose_files)
        self.assertLess(
            compose_files.index(content_base),
            compose_files.index(CONTENT_GAMMA_COMPOSE_FILE),
        )
        start_script = START_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            'services_root.glob(f"*/environments/{env_name}/deploy/compose.yaml")',
            start_script,
        )

    def test_content_release_does_not_wait_for_full_control_plane(self) -> None:
        script = START_SCRIPT.read_text(encoding="utf-8")
        platform_ready = script.split("gamma_platform_ops_ready() {", 1)[1].split(
            "\n}\n\nwait_local_gamma_host_ready", 1
        )[0]

        self.assertIn(
            'if [[ "$WORKLOAD" == "content-release" || "$WORKLOAD" == "content-commercial" ]]; then',
            platform_ready,
        )
        self.assertIn("gamma_platform_ops_ready", script)

    def test_rebuildable_state_purge_is_explicit_and_target_scoped(self) -> None:
        script = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--purge-rebuildable-state", script)
        self.assertIn("down_args+=(--volumes --remove-orphans)", script)
        self.assertIn(
            'docker compose -p "$LOCAL_GAMMA_COMPOSE_PROJECT_NAME"',
            script,
        )

    def test_recommendation_service_receives_the_selected_workload(self) -> None:
        service_block = service_compose("recommendation-service")
        gamma_config = (
            ROOT
            / "quwoquan_service/services/recommendation-service/environments/gamma/config.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn('QWQ_WORKLOAD: "${QWQ_WORKLOAD:-full}"', service_block)
        self.assertIn(
            "QWQ_COMPOSE_REC_POLICY_SOURCE:?QWQ_COMPOSE_REC_POLICY_SOURCE is required}",
            service_block,
        )
        self.assertIn(
            "sys.recommendation-service.redis.general.addr: redis:6379",
            gamma_config,
        )
        self.assertIn(
            "sys.recommendation-service.redis.rec.addr: redis:6379",
            gamma_config,
        )

    def test_recommendation_healthcheck_has_socket_timeout_and_single_worker_default(
        self,
    ) -> None:
        service_block = service_compose("recommendation-service")

        self.assertIn(
            'QWQ_COMPOSE_REC_MODEL_WORKERS:-1}',
            service_block,
        )
        self.assertIn(
            "urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)",
            service_block,
        )
        self.assertNotIn(
            "urllib.request.urlopen('http://127.0.0.1:8000/health')\" || exit 1",
            service_block,
        )

    def test_user_service_compose_injects_protected_nonprod_provider_material(self) -> None:
        service_block = service_compose("user-service")
        user_main = (
            ROOT / "quwoquan_service/services/user-service/cmd/api/bootstrap.go"
        ).read_text(encoding="utf-8")
        for key in (
            "ALIYUN_DYPNS_ENDPOINT:",
            "ALIYUN_DYPNS_ACCESS_KEY_ID:",
            "ALIYUN_DYPNS_ACCESS_KEY_SECRET:",
            "WECHAT_OAUTH_TOKEN_URL:",
            "ALIPAY_OAUTH_TOKEN_URL:",
            "QQ_OAUTH_USER_INFO_URL:",
        ):
            self.assertIn(key, service_block)
        for key in (
            "INTEGRATION_SERVICE_MTLS_CA_FILE:",
            "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE:",
            "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE:",
            "INTEGRATION_SERVICE_MTLS_SERVER_NAME:",
        ):
            self.assertIn(key, service_block)
        self.assertIn('QWQ_WORKLOAD: "${QWQ_WORKLOAD:-full}"', service_block)
        self.assertIn("if !contentSliceExternalAuthDisabled()", user_main)
        self.assertIn("WithExternalInteractionClient(externalInteractionClient)", user_main)

    def test_full_gamma_optional_services_have_nonproduction_runtime_prerequisites(self) -> None:
        product_runtime_config = (
            ROOT
            / "quwoquan_service"
            / "services"
            / "product-ops-service"
            / "cmd"
            / "api"
            / "runtime_config.go"
        ).read_text(encoding="utf-8")
        assistant_compose = service_compose("assistant-service")

        self.assertIn("case logsink.ElasticsearchAdapterID:", product_runtime_config)
        # 环境合法性（alpha|beta|gamma|prod）与配置身份校验由 servicekit 的
        # ResolveIdentity 统一承担，服务侧只声明通用段并内嵌 BaseConfig。
        self.assertIn("servicekit.BaseConfig", product_runtime_config)
        self.assertIn("ASSISTANT_POSTGRES_DSN:", assistant_compose)
        self.assertIn(
            "postgres:\n        condition: service_healthy",
            assistant_compose,
        )

    def test_gamma_uses_nonmemory_provider_adapters_without_compose_overlay(self) -> None:
        provider_services = {
            "assistant-service": "ext.llm.protocol_fixture",
            "integration-service": "ext.map.protocol_fixture",
            "rtc-service": "infra.livekit_sfu",
        }
        for service, adapter in provider_services.items():
            service_root = ROOT / "quwoquan_service" / "services" / service
            gamma_config = (service_root / "environments" / "gamma" / "config.yaml").read_text(
                encoding="utf-8"
            )

            self.assertIn(adapter, gamma_config)
            self.assertFalse(
                (service_root / "environments" / "gamma" / "deploy" / "compose.yaml").exists()
            )

        user_root = ROOT / "quwoquan_service" / "services" / "user-service"
        user_gamma_config = (
            user_root / "environments" / "gamma" / "config.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("identity.carrier.one_tap:\n    state: enabled", user_gamma_config)
        self.assertIn("adapter: ext.auth.carrier_one_tap_protocol_fixture", user_gamma_config)
        self.assertIn("identity.social.login:\n    state: enabled", user_gamma_config)
        self.assertIn("adapter: ext.auth.federated_identity_protocol_fixture", user_gamma_config)
        self.assertFalse(
            (user_root / "environments" / "gamma" / "deploy" / "compose.yaml").exists()
        )

    def test_full_gamma_edge_media_builds_rtc_from_its_packaged_provenance(self) -> None:
        rtc_compose = service_compose("rtc-service")
        realtime_compose = service_compose("realtime-gateway")
        start_script = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('profiles: ["edge-media"]', rtc_compose)
        self.assertIn("dockerfile: services/rtc-service/build/Dockerfile", rtc_compose)
        self.assertIn("CONFIG_ROOT: /etc/qwq-config", rtc_compose)
        self.assertIn("USER_SERVICE_BASE_URL: http://user-service:18081", rtc_compose)
        self.assertIn(
            "QWQ_COMPOSE_CONFIG_ROOT:?QWQ_COMPOSE_CONFIG_ROOT is required}:/etc/qwq-config:ro",
            rtc_compose,
        )
        for binding in (
            "RTC_MEDIA_CONNECTION_URL:",
            "RTC_MEDIA_API_KEY:",
            "RTC_MEDIA_API_SECRET:",
            "AUTH_JWT_SECRET:",
            "AUTH_JWT_ISSUER:",
            "AUTH_JWT_AUDIENCE:",
            "AUTH_JWT_TOKEN_VERSION:",
            "AUTH_DEVICE_TICKET_SECRET:",
            "AUTH_DEVICE_TICKET_ISSUER:",
            "AUTH_DEVICE_TICKET_AUDIENCE:",
            "AUTH_DEVICE_TICKET_TOKEN_VERSION:",
        ):
            self.assertIn(binding, rtc_compose)
        self.assertIn('profiles: ["edge-media"]', realtime_compose)
        self.assertIn(
            "dockerfile: services/realtime-gateway/build/Dockerfile",
            realtime_compose,
        )
        self.assertIn("compose_build_services+=(realtime-gateway)", start_script)
        self.assertIn("compose_build_services+=(rtc-service)", start_script)
        self.assertNotIn("\n  travel-service\n", start_script)
        self.assertIn(
            "commercial-observability,assistant-runtime,edge-media",
            start_script,
        )

    def test_user_service_image_packs_shard_directory_contract(self) -> None:
        dockerfile = (
            ROOT
            / "quwoquan_service"
            / "services"
            / "user-service"
            / "build"
            / "Dockerfile"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "contracts/account/user_account/shard_directory.yaml",
            dockerfile,
        )
        self.assertIn(
            "/app/contracts/account/user_account/shard_directory.yaml",
            dockerfile,
        )

    def test_gamma_user_service_uses_one_internal_port_across_runtime_paths(self) -> None:
        caddy = CADDYFILE.read_text(encoding="utf-8")
        start_script = START_SCRIPT.read_text(encoding="utf-8")
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        api_edge_schema = (
            ROOT / "quwoquan_service/services/api-edge/config/schema.yaml"
        ).read_text(encoding="utf-8")

        self.assertEqual(caddy.count("reverse_proxy api-edge:18079"), 1)
        self.assertNotIn("reverse_proxy user-service:", caddy)
        self.assertEqual(api_edge_schema.count("http://user-service:18081"), 2)
        self.assertNotIn("http://user-service:18082", api_edge_schema)
        for expected in (
            "USER_SERVICE_ADDR=:18081",
            'LOCAL_GAMMA_USER_PORT:-19210}:18081',
            "http://127.0.0.1:18081/healthz",
            "NOTIFICATION_USER_BASE_URL=http://user-service:18081",
            "-e ALIYUN_DYPNS_ENDPOINT",
            "-e WECHAT_OAUTH_TOKEN_URL",
        ):
            self.assertIn(expected, start_script)
        self.assertIn(
            "${LOCAL_GAMMA_CADDYFILE:?packaged Caddyfile is required}:/etc/caddy/Caddyfile:ro",
            compose,
        )
        self.assertNotIn("../gamma/local/Caddyfile", compose)
        self.assertIn(
            'LOCAL_GAMMA_CADDYFILE="${LOCAL_GAMMA_RUNTIME_SHARED_ROOT}/Caddyfile"',
            start_script,
        )

    def test_public_web_seo_routes_bind_content_service_public_web_plane(self) -> None:
        """公开 SEO 读面接线（public-content-web-entry）不可回退。

        publicWeb host 的对象页 / robots / sitemap / 中转页必须经 edge
        rewrite 到 content-service `/public-web/*`；content-service compose
        必须消费 publicWeb origin 与媒体 CDN origin（origin 为空时服务侧
        fail-closed 不挂载该读面）。
        """
        caddy = CADDYFILE.read_text(encoding="utf-8")
        self.assertIn("@public_web_seo", caddy)
        self.assertIn(
            "path /post/* /robots.txt /sitemap-posts.xml /open /s/*",
            caddy,
        )
        self.assertIn("rewrite * /public-web{uri}", caddy)
        self.assertIn("reverse_proxy content-service:18080", caddy)

        content_compose = (
            CONTENT_SERVICE_ROOT / "deploy/compose.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'CONTENT_PUBLIC_WEB_ORIGIN: "${QWQ_COMPOSE_PUBLIC_WEB_BASE_URL:-}"',
            content_compose,
        )
        self.assertIn(
            'CONTENT_PUBLIC_WEB_CDN_ORIGIN: "${QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL:-}"',
            content_compose,
        )
