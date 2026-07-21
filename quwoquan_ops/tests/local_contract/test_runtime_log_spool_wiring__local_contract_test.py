from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
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
            versioned_image=True,
            instance="prod",
            config_root="/runtime/config-root",
            media_root="/runtime/media",
            legal_root="/runtime/legal",
            portal_root="/runtime/portal",
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
        rendered = self.rewrite("rec-model-service")
        env = rendered["environment"]
        self.assertNotIn("RUNTIME_LOG_INGEST_URL", env)
        self.assertNotIn("RUNTIME_LOG_SPOOL_DIR", env)

    def test_platform_ops_reads_the_synced_release_ledger_projection(self) -> None:
        rendered = self.rewrite("platform-ops-service")
        self.assertEqual(
            rendered["environment"]["QWQ_PROD_RELEASE_STATE_DIR"],
            "/var/lib/quwoquan/release-state",
        )
        self.assertIn(
            "./release-ledger:/var/lib/quwoquan/release-state:ro",
            rendered["volumes"],
        )


if __name__ == "__main__":
    unittest.main()
