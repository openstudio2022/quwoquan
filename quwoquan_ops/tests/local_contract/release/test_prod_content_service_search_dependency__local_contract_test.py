from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from quwoquan_ops.cli.prod import render_prod_plane_stack as renderer


ROOT = Path(__file__).resolve().parents[4]


class ProdContentServiceSearchDependencyTest(unittest.TestCase):
    def _rewrite(
        self,
        *,
        data_mode: str,
        selected: set[str],
        startup_services: set[str],
    ) -> dict[str, object]:
        compose = yaml.safe_load(
            (
                ROOT
                / "quwoquan_service/services/content-service/deploy/compose.yaml"
            ).read_text(encoding="utf-8")
        )
        return renderer._rewrite_service(
            "content-service",
            compose["services"]["content-service"],
            selected,
            image_version="sha256-content",
            config_version="sha256-config",
            versioned_image=False,
            instance="prevalidate",
            replica_id="r0",
            config_root="runtime/config-root",
            media_root="runtime/media",
            legal_root="runtime/legal",
            portal_root="runtime/portal",
            web_root="runtime/web",
            caddyfile_path="runtime/Caddyfile",
            model_cache_root="runtime/model-cache",
            data_mode=data_mode,
            startup_services=startup_services,
        )

    def test_isolated_prod_content_waits_for_selected_elasticsearch_health(self) -> None:
        selected = {
            "content-service",
            "mongodb",
            "mongo-init",
            "object-storage-init",
            "redis",
            "recommendation-service",
            "elasticsearch",
        }
        rendered = self._rewrite(
            data_mode="isolated",
            selected=selected,
            startup_services=selected,
        )

        self.assertEqual(
            rendered["depends_on"]["elasticsearch"],
            {"condition": "service_healthy"},
        )
        self.assertEqual(rendered["environment"]["SEARCH_ES_ENABLED"], "true")
        self.assertEqual(
            rendered["environment"]["SEARCH_ES_ENDPOINTS"],
            "http://elasticsearch:9200",
        )

    def test_isolated_prod_content_rejects_missing_es_startup_service(self) -> None:
        selected = {"content-service", "mongodb", "redis"}
        with self.assertRaisesRegex(SystemExit, "Elasticsearch startup dependency"):
            self._rewrite(
                data_mode="isolated",
                selected=selected,
                startup_services=selected,
            )

    def test_external_prod_content_uses_managed_endpoint_without_local_dependency(self) -> None:
        selected = {"content-service", "mongodb", "redis"}
        rendered = self._rewrite(
            data_mode="external",
            selected=selected,
            startup_services=selected,
        )

        self.assertNotIn("elasticsearch", rendered.get("depends_on", {}))
        self.assertEqual(rendered["environment"]["SEARCH_ES_ENABLED"], "true")
        self.assertEqual(
            rendered["environment"]["SEARCH_ES_ENDPOINTS"],
            "${PROD_CONTENT_SEARCH_ES_ENDPOINTS:?managed content search endpoint is required}",
        )


if __name__ == "__main__":
    unittest.main()
