from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
RENDER_PATH = ROOT / "quwoquan_ops/cli/prod/render_prod_plane_stack.py"


def _load_render_module():
    spec = importlib.util.spec_from_file_location("render_prod_plane_stack_spool", RENDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RuntimeLogSpoolWiringContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.render = _load_render_module()

    def rewrite(self, name: str):
        return self.render._rewrite_service(
            name,
            {"image": f"example/{name}:digest", "environment": {}, "volumes": []},
            {name, "product-ops-service"},
            image_version="1.20260720.1",
            config_version="config-20260720-1",
            versioned_image=True,
            instance="prod",
            replica_id="r0",
            config_root="/runtime/config-root",
            media_root="/runtime/media",
            legal_root="/runtime/legal",
            portal_root="/runtime/portal",
            web_root="/runtime/public-web",
            caddyfile_path="/runtime/Caddyfile",
            model_cache_root="/runtime/model-cache",
        )

    def test_prod_service_image_is_never_latest(self) -> None:
        rendered = self.rewrite("content-service")
        self.assertEqual(
            rendered["image"],
            "localhost/quwoquan_service_content-service:1.20260720.1",
        )

    def test_go_services_receive_fail_closed_ingest_and_durable_spool(self) -> None:
        rendered = self.rewrite("content-service")
        env = rendered["environment"]
        self.assertEqual(
            env["RUNTIME_LOG_INGEST_URL"],
            "http://product-ops-service:18086/ops/internal/runtime-logs:ingest",
        )
        self.assertIn("RUNTIME_LOG_INGEST_TOKEN is required", env["RUNTIME_LOG_INGEST_TOKEN"])
        self.assertEqual(
            env["RUNTIME_LOG_SPOOL_DIR"],
            "/var/lib/quwoquan/runtime-log-spool/content-service",
        )
        self.assertIn(
            "runtime-log-spool:/var/lib/quwoquan/runtime-log-spool",
            rendered["volumes"],
        )

    def test_product_ops_uses_the_durable_spool_without_http_feedback_loop(self) -> None:
        rendered = self.rewrite("product-ops-service")
        env = rendered["environment"]
        self.assertEqual(
            env["RUNTIME_LOG_INGEST_URL"],
            "http://product-ops-service:18086/ops/internal/runtime-logs:ingest",
        )
        self.assertIn("RUNTIME_LOG_INGEST_TOKEN is required", env["RUNTIME_LOG_INGEST_TOKEN"])
        self.assertEqual(
            env["RUNTIME_LOG_SPOOL_DIR"],
            "/var/lib/quwoquan/runtime-log-spool/product-ops-service",
        )
        self.assertIn(
            "runtime-log-spool:/var/lib/quwoquan/runtime-log-spool",
            rendered["volumes"],
        )

    def test_non_go_recommendation_process_is_not_given_unused_spool(self) -> None:
        rendered = self.rewrite("recommendation-service")
        env = rendered["environment"]
        self.assertNotIn("RUNTIME_LOG_INGEST_URL", env)
        self.assertNotIn("RUNTIME_LOG_SPOOL_DIR", env)

    def test_platform_ops_does_not_mount_release_ledger_as_a_portal_data_source(self) -> None:
        rendered = self.rewrite("platform-ops-service")
        self.assertNotIn(
            "QWQ_PROD_RELEASE_STATE_DIR",
            rendered["environment"],
        )
        self.assertNotIn(
            "./release-ledger:/var/lib/quwoquan/release-state:ro",
            rendered["volumes"],
        )

    def test_every_managed_runtime_service_receives_bound_config_ack_identity(self) -> None:
        for service in sorted(self.render.RUNTIME_LOG_EXPORT_SERVICES):
            with self.subTest(service=service):
                rendered = self.rewrite(service)
                environment = rendered["environment"]
                cluster = "prod-prod-control-r0"
                self.assertEqual(
                    environment["PLATFORM_OPS_BASE_URL"],
                    "http://platform-ops-service:18088",
                )
                self.assertEqual(environment["CLUSTER_NAME"], cluster)
                self.assertEqual(
                    environment["SERVICE_INSTANCE_ID"],
                    f"{service}-{cluster}-0",
                )
                self.assertEqual(environment["IMAGE_VERSION"], "1.20260720.1")

        platform = self.rewrite("platform-ops-service")["environment"]
        expected = {
            f"{service}-prod-prod-control-r0-0"
            for service in self.render.RUNTIME_LOG_EXPORT_SERVICES
        }
        self.assertEqual(
            set(platform["CONFIG_ACK_REQUIRED_INSTANCES"].split(",")),
            expected,
        )
        self.assertEqual(platform["CONFIG_ACK_MAX_AGE_SECONDS"], "120")


if __name__ == "__main__":
    unittest.main()
