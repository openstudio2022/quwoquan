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
            "content-service",
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
            self.assertNotIn(f"reverse_proxy {forbidden_owner}:", caddy)

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
