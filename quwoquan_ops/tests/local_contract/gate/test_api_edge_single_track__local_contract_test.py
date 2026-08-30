# spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from quwoquan_ops.cli.prod import render_prod_plane_stack as renderer


ROOT = Path(__file__).resolve().parents[4]
GAMMA_CADDY = ROOT / "quwoquan_ops/environments/gamma/local/Caddyfile"
GAMMA_COMPOSE = (
    ROOT / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
)


class ApiEdgeSingleTrackLocalContractTest(unittest.TestCase):
    def test_gamma_caddy_terminates_tls_without_copying_business_routes(self) -> None:
        caddy = GAMMA_CADDY.read_text(encoding="utf-8")
        self.assertEqual(caddy.count("reverse_proxy api-edge:18079"), 1)
        self.assertIn("header_up X-Edge-Client-IP {remote_host}", caddy)
        for forbidden_owner in (
            "assistant-service",
            "chat-service",
            "circle-service",
            "entity-service",
            "integration-service",
            "notification-service",
            "platform-ops-service",
            "product-ops-service",
            "realtime-gateway",
            "rtc-service",
            "search-service",
            "tag-service",
            "user-service",
        ):
            owner_proxy = f"reverse_proxy {forbidden_owner}:"
            if forbidden_owner == "product-ops-service":
                self.assertEqual(caddy.count(owner_proxy), 2)
                continue
            self.assertNotIn(owner_proxy, caddy)
        # publicWeb host 的 SEO/transfer 读面由 public-content owner 承接；
        # 只允许这一条精确映射，业务 API 仍必须唯一进入 api-edge。
        self.assertEqual(caddy.count("reverse_proxy content-service:18080"), 1)
        self.assertIn("@public_web_seo", caddy)
        self.assertIn("rewrite * /public-web{uri}", caddy)

    def test_product_ops_edge_forwards_both_canonical_probe_paths(self) -> None:
        caddy = GAMMA_CADDY.read_text(encoding="utf-8")
        product_ops_block = caddy.split(
            "https://{$QWQ_PUBLIC_OPS_HOST}:{$LOCAL_GAMMA_PRODUCT_OPS_PORT:", 1
        )[1].split("https://{$QWQ_PUBLIC_CDN_HOST}:", 1)[0]
        for path in ("/healthz", "/readyz"):
            self.assertIn(f"handle {path} {{", product_ops_block)
        self.assertEqual(
            product_ops_block.count("reverse_proxy product-ops-service:18086"), 2
        )
        self.assertEqual(product_ops_block.count("import business_api_edge"), 3)

    def test_gamma_proxy_readiness_depends_on_the_canonical_edge_only(self) -> None:
        compose = yaml.safe_load(GAMMA_COMPOSE.read_text(encoding="utf-8"))
        dependencies = compose["services"]["gamma-proxy"]["depends_on"]
        self.assertEqual(set(dependencies), {"api-edge"})
        self.assertEqual(
            dependencies["api-edge"]["condition"],
            "service_healthy",
        )

    def test_prod_and_gray_caddy_keep_the_same_business_edge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            renderer._write_caddyfile(output, "prod")
            prod = (output / "runtime/Caddyfile").read_text(encoding="utf-8")
            renderer._write_caddyfile(output, "gray")
            gray = (output / "runtime/Caddyfile").read_text(encoding="utf-8")
        for caddy in (prod, gray):
            self.assertEqual(caddy.count("reverse_proxy api-edge:18079"), 1)
            self.assertIn("header_up X-Edge-Client-IP {remote_host}", caddy)
            self.assertNotIn("reverse_proxy content-service:", caddy)
            self.assertNotIn("reverse_proxy product-ops-service:", caddy)


if __name__ == "__main__":
    unittest.main()
