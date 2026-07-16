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

    def test_user_service_requires_real_external_identity_credentials(self) -> None:
        content = COMPOSE_FILE.read_text(encoding="utf-8")
        service_block = content.split("  user-service:\n", 1)[1].split(
            "\n  assistant-service:\n", 1
        )[0]

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
            self.assertIn(
                f'{credential}: "${{{credential}:?{credential} is required}}"',
                service_block,
            )

    def test_premium_pool_proof_uses_a_run_scoped_actor_without_erasing_exposure(self) -> None:
        source = START_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('run_id = Path(report_path).parent.name', source)
        self.assertIn('subject=f"premium-pool-seed-{run_id}"', source)
        self.assertNotIn('subject="premium-pool-seed",', source)
        self.assertNotIn('premium-pool-seed-v1', source)
        self.assertNotIn("redis-cli --scan", source)


if __name__ == "__main__":
    unittest.main()
