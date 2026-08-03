from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.compose_layout import gamma_compose_files
from quwoquan_ops.cli.alpha.content_release_runtime import _compose_build_environment
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "quwoquan_ops" / "environments" / "compose" / "docker-compose.gamma-local.yaml"
CADDYFILE = ROOT / "quwoquan_ops" / "environments" / "gamma" / "local" / "Caddyfile"
CONTENT_GAMMA_COMPOSE_FILE = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "content-service"
    / "environments"
    / "gamma"
    / "deploy"
    / "compose.yaml"
)
OBJECT_STORAGE_LIFECYCLE_FILE = (
    ROOT
    / "quwoquan_ops"
    / "environments"
    / "compose"
    / "object-storage-lifecycle.json"
)
START_SCRIPT = ROOT / "quwoquan_app" / "scripts" / "gamma" / "start_local_gamma_mirror.sh"
PRODUCT_OPS_LOCAL_ES_COMPOSE_FILE = (
    ROOT
    / "quwoquan_service"
    / "services"
    / "product-ops-service"
    / "deploy"
    / "local-elasticsearch.compose.yaml"
)
T3_SCRIPT = ROOT / "quwoquan_app" / "scripts" / "gamma" / "run_local_gamma_t3.py"


def service_compose(service: str) -> str:
    return (
        ROOT
        / "quwoquan_service"
        / "services"
        / service
        / "deploy"
        / "compose.yaml"
    ).read_text(encoding="utf-8")


class LocalGammaContentServiceConfigTest(unittest.TestCase):
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
                    "https://upload.alpha.quwoquan.com:17100"
                ),
            },
        )

    def test_t3_runtime_is_a_read_only_release_consumer(self) -> None:
        source = T3_SCRIPT.read_text(encoding="utf-8")

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
        self.assertIn('"mutationPolicy": "read_only"', source)

    def test_content_t3_identity_is_owned_by_canonical_readiness_receipt(
        self,
    ) -> None:
        source = T3_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("load_release_content_identity", source)
        self.assertIn("resolve_readiness_path", source)
        self.assertIn('expected_environment="gamma"', source)
        for field in (
            "releaseId",
            "sourceOwner",
            "manifestDigest",
            "mediaManifestDigest",
            "importRunId",
            "verifyRunId",
            "readinessReceiptRef",
        ):
            self.assertIn(f'identity["{field}"]', source)
        self.assertNotIn('parser.add_argument("--release-id"', source)
        self.assertNotIn('parser.add_argument("--import-run-id"', source)
        self.assertNotIn('parser.add_argument("--verification-run-id"', source)

    def test_user_t3_does_not_provision_contact_discovery(
        self,
    ) -> None:
        source = T3_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("provision_contact_discovery", source)
        self.assertNotIn("hashedPhones", source)
        self.assertNotIn("_ACTIVE_SESSION", source)

    def test_core_readback_does_not_mint_anonymous_identity_in_t3(
        self,
    ) -> None:
        source = T3_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("open_public_anonymous_session", source)
        self.assertNotIn("LocalGammaAcceptanceSession", source)
        self.assertNotIn("/auth/login", source)
        self.assertNotIn("accessToken", source)

    def test_core_readback_does_not_provision_chat_inbox_in_t3(self) -> None:
        source = T3_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("provision_chat_core_readback", source)
        self.assertNotIn("/chat/conversations", source)
        self.assertNotIn("runtime-message", source)
        self.assertNotIn("http_request", source)

    def test_content_service_declares_all_required_runtime_bindings(self) -> None:
        service_block = service_compose("content-service")

        for binding in (
            "MONGO_URI:",
            "REPORT_DATABASE_URL:",
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
            "REC_MODEL_SERVICE_ENABLED:",
            "REC_MODEL_SERVICE_URL:",
        ):
            self.assertIn(binding, service_block)
        self.assertIn(
            'REC_MODEL_SERVICE_ENABLED: "${QWQ_COMPOSE_REC_MODEL_SERVICE_ENABLED:-true}"',
            service_block,
        )

        self.assertNotIn("SSL_CERT_FILE:", service_block)
        self.assertNotIn("object-storage-ca.crt", service_block)

    def test_content_service_waits_for_required_elasticsearch_dependency(self) -> None:
        content = service_compose("content-service")
        gamma_content_overlay = CONTENT_GAMMA_COMPOSE_FILE.read_text(encoding="utf-8")
        search = service_compose("search-service")
        entity = service_compose("entity-service")
        circle = service_compose("circle-service")
        expected = "elasticsearch:\n        condition: service_healthy"
        self.assertIn(expected, content)
        self.assertIn(expected, gamma_content_overlay)
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
                gamma_content_overlay,
            )
        for block in (search, entity, circle):
            self.assertIn(expected, block)

    def test_gamma_redis_health_requires_ready_command_processing(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")

        self.assertIn(
            'test: ["CMD-SHELL", "redis-cli --raw ping | grep -qx PONG"]',
            compose,
        )
        self.assertNotIn('test: ["CMD", "redis-cli", "ping"]', compose)

    def test_mongo_init_waits_for_writable_primary_before_dependents(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")

        self.assertIn("db.hello().isWritablePrimary", compose)
        self.assertIn("mongo-init timed out waiting for writable primary", compose)
        self.assertIn(
            "recommendation-service:\n"
            "    depends_on:\n"
            "      mongo-init:\n"
            "        condition: service_completed_successfully",
            compose,
        )

    def test_gamma_elasticsearch_uses_native_architecture_with_arm_sve_guard(self) -> None:
        compose = PRODUCT_OPS_LOCAL_ES_COMPOSE_FILE.read_text(encoding="utf-8")
        script = START_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("platform: linux/amd64", compose)
        self.assertIn(
            "CLI_JAVA_OPTS: \"${QWQ_COMPOSE_ELASTICSEARCH_CLI_JAVA_OPTS:-}\"",
            compose,
        )
        self.assertIn(
            "ES_JAVA_OPTS: \"${QWQ_COMPOSE_ELASTICSEARCH_JAVA_OPTS:--Xms512m -Xmx512m}\"",
            compose,
        )
        self.assertIn('case "$(uname -m)" in', script)
        self.assertIn("arm64|aarch64)", script)
        self.assertIn(
            'LOCAL_GAMMA_ELASTICSEARCH_CLI_JAVA_OPTS:--XX:UseSVE=0',
            script,
        )
        self.assertIn(
            'LOCAL_GAMMA_ELASTICSEARCH_JAVA_OPTS:--XX:UseSVE=0 -Xms512m -Xmx512m',
            script,
        )
        self.assertNotIn("--platform=linux/amd64", script)

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
            '-path "*/environments/${QWQ_LOCAL_RELEASE_ENV}/deploy/compose.yaml" -type f | sort',
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

    def test_user_service_compose_injects_protected_nonprod_provider_material(self) -> None:
        service_block = service_compose("user-service")
        user_main = (
            ROOT / "quwoquan_service/services/user-service/cmd/api/main.go"
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
        self.assertIn('case "alpha", "beta", "gamma", "prod":', product_runtime_config)
        self.assertIn("POSTGRES_DSN:", assistant_compose)
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

    def test_product_ops_receives_local_elasticsearch_endpoint(self) -> None:
        service_block = service_compose("product-ops-service")
        start_script = START_SCRIPT.read_text(encoding="utf-8")

        key = "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT"
        self.assertIn(f'{key}: "${{{key}:-}}"', service_block)
        self.assertIn(
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

    def test_t3_rejects_reports_in_mutable_local_runtime_state(self) -> None:
        spec = importlib.util.spec_from_file_location("local_gamma_t3_report_path_test", T3_SCRIPT)
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
                / "t3.json"
            )
            forbidden = (
                output_root
                / "env"
                / "gamma"
                / "local"
                / "gamma-local"
                / "t3_forbidden.json"
            )
            with mock.patch.dict(
                module.os.environ,
                {"QWQ_OUTPUT_ROOT": str(output_root)},
            ):
                self.assertEqual(module.default_t3_report_path(), allowed)
                self.assertEqual(
                    module.resolve_t3_report_path(str(allowed)),
                    allowed.resolve(),
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "QWQ_OUTPUT_ROOT/env/gamma/runs",
                ):
                    module.resolve_t3_report_path(str(forbidden))


if __name__ == "__main__":
    unittest.main()
