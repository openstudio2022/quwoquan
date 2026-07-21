from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.cli.prod import render_prod_plane_stack as render


ROOT = Path(__file__).resolve().parents[3]


class ProdColdStartRenderContractTest(unittest.TestCase):
    def test_public_caddy_uses_automatic_tls_and_security_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            render._write_caddyfile(output, "prod")
            caddy = (output / "runtime" / "Caddyfile").read_text(encoding="utf-8")

        for token in (
            "api.quwoquan.com",
            "realtime.quwoquan.com",
            "ops.quwoquan.com",
            "cdn.quwoquan.com",
            "upload.quwoquan.com",
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "try_files {path} /index.html",
        ):
            self.assertIn(token, caddy)
        for forbidden in ("local_certs", "tls internal", ".test", "\n:80 {"):
            self.assertNotIn(forbidden, caddy)

    def test_gray_caddy_is_private_http_upstream_without_certificate_issuance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            render._write_caddyfile(output, "gray")
            caddy = (output / "runtime" / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn(":80 {", caddy)
        self.assertNotIn("tls internal", caddy)
        self.assertNotIn("quwoquan.com", caddy)

    def test_stable_router_only_targets_gray_before_full_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            render._write_caddyfile(output, "prod", "gray-initial")
            initial = (output / "runtime" / "Caddyfile").read_text(encoding="utf-8")
            render._write_caddyfile(output, "prod", "full")
            full = (output / "runtime" / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("@gray_userids", initial)
        self.assertIn("host.containers.internal:29000", initial)
        self.assertNotIn("@gray_", full)

    def test_prod_proxy_exposes_acme_ports_and_support_image_is_digest_pinned(self) -> None:
        compose_path = (
            ROOT
            / "quwoquan_ops"
            / "environments"
            / "compose"
            / "docker-compose.gamma-local.yaml"
        )
        compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        proxy = render._rewrite_service(
            "gamma-proxy",
            compose["services"]["gamma-proxy"],
            {"gamma-proxy", "content-service", "product-ops-service"},
            image_version="1.20260720.1",
            versioned_image=False,
            instance="prod",
            config_root="/runtime/config-root",
            media_root="/runtime/media",
            legal_root="/runtime/legal",
            portal_root="/runtime/portal",
            caddyfile_path="/runtime/Caddyfile",
            model_cache_root="/runtime/model-cache",
        )
        self.assertEqual(
            proxy["ports"],
            ["80:80", "443:443", "127.0.0.1:12019:2019"],
        )
        self.assertRegex(
            proxy["image"],
            r"^docker\.io/library/caddy:[^@]+@sha256:[0-9a-f]{64}$",
        )

    def test_prod_domain_truth_source_rejects_local_fallbacks(self) -> None:
        hosts = render._prod_public_hosts()
        self.assertEqual(hosts["api"], "api.quwoquan.com")
        self.assertTrue(all(not host.endswith(".test") for host in hosts.values()))

    def test_render_rejects_disposable_output_as_deployment_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            disposable_output = Path(temporary) / ".qwq_output"
            deployment_output = disposable_output / "env/prod/local/prod-hosted/process/service"
            with mock.patch.dict(
                os.environ,
                {"QWQ_OUTPUT_ROOT": str(disposable_output)},
                clear=False,
            ):
                with self.assertRaisesRegex(SystemExit, "QWQ_DEPLOY_WORK_ROOT"):
                    render._require_external_deployment_root(deployment_output)


if __name__ == "__main__":
    unittest.main()
