from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "quwoquan_ops" / "environments" / "compose" / "docker-compose.gamma-local.yaml"
START_SCRIPT = ROOT / "quwoquan_app" / "scripts" / "gamma" / "start_local_gamma_mirror.sh"


class LocalGammaContentServiceConfigTest(unittest.TestCase):
    def test_content_service_declares_all_required_runtime_bindings(self) -> None:
        content = COMPOSE_FILE.read_text(encoding="utf-8")
        service_block = content.split("  content-service:\n", 1)[1].split("\n  chat-service:\n", 1)[0]

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
            "CONTENT_CDN_DOMAIN:",
            "CONTENT_CDN_SIGN_KEY:",
            "SEARCH_ES_ENABLED:",
            "SEARCH_ES_ENDPOINTS:",
            "REC_MODEL_SERVICE_ENABLED:",
            "REC_MODEL_SERVICE_URL:",
        ):
            self.assertIn(binding, service_block)

        self.assertIn("SSL_CERT_FILE: /etc/ssl/local-ca/object-storage-ca.crt", service_block)
        self.assertIn("/etc/ssl/local-ca/object-storage-ca.crt:ro", service_block)

    def test_local_single_node_search_is_not_blocked_by_colima_build_cache_watermark(self) -> None:
        content = COMPOSE_FILE.read_text(encoding="utf-8")
        service_block = content.split("  elasticsearch:\n", 1)[1].split(
            "\n  search-service:\n", 1
        )[0]

        self.assertIn(
            'cluster.routing.allocation.disk.threshold_enabled: "false"',
            service_block,
        )
        self.assertIn("local-gamma-es:/usr/share/elasticsearch/data", service_block)

    def test_user_service_uses_local_acceptance_identity_without_fake_provider_credentials(self) -> None:
        content = COMPOSE_FILE.read_text(encoding="utf-8")
        service_block = content.split("  user-service:\n", 1)[1].split(
            "\n  assistant-service:\n", 1
        )[0]

        self.assertIn("USER_AUTH_EXTERNAL_PROVIDER_MODE: anonymous_only", service_block)
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
            self.assertNotIn(f"{credential}:", service_block)

    def test_entity_service_receives_the_shared_access_token_contract(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        service_block = compose.split("  entity-service:\n", 1)[1].split(
            "\n  circle-service:\n", 1
        )[0]
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

    def test_product_ops_receives_real_sls_deployment_secret_bindings(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        service_block = compose.split("  product-ops-service:\n", 1)[1].split(
            "\n  platform-ops-service:\n", 1
        )[0]
        start_script = START_SCRIPT.read_text(encoding="utf-8")

        for key in (
            "PRODUCT_OPS_SLS_REGION",
            "PRODUCT_OPS_SLS_ENDPOINT",
            "PRODUCT_OPS_SLS_PROJECT",
            "ALIBABA_CLOUD_ACCESS_KEY_ID",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        ):
            self.assertIn(f'{key}: "${{{key}:-}}"', service_block)
            self.assertIn(f"{key} is required", start_script)

    def test_premium_pool_proof_uses_a_run_scoped_actor_without_erasing_exposure(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('run_id = Path(report_path).parent.name', source)
        self.assertIn('subject=f"premium-pool-seed-{run_id}"', source)
        self.assertNotIn('subject="premium-pool-seed",', source)
        self.assertNotIn('premium-pool-seed-v1', source)
        self.assertNotIn("redis-cli --scan", source)

    def test_gamma_startup_removes_only_non_running_named_residue(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("cleanup_stale_named_gamma_containers", source)
        self.assertIn(
            "unmanaged active container blocks canonical compose ownership",
            source,
        )
        self.assertIn("removing stale non-running container", source)
        self.assertIn("cleanup_stale_named_gamma_containers\n  #", source)

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


if __name__ == "__main__":
    unittest.main()
