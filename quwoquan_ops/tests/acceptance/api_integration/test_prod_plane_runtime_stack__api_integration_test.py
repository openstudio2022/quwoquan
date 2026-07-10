from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]


class ProdPlaneRuntimeStackTest(unittest.TestCase):
    def test_render_service_plane_outputs_onebox_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "service"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    "service",
                    "--instance",
                    "prod",
                    "--config-version",
                    "local-gamma-v1",
                    "--image-version",
                    "1.20260617.rootless-service-plane",
                    "--output-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((out_dir / "render_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["plane"], "service")
            self.assertEqual(
                report["governedComposeServices"],
                [
                    "rec-model-service",
                    "content-service",
                    "chat-service",
                    "user-service",
                    "assistant-service",
                    "product-ops-service",
                    "tag-service",
                    "entity-service",
                ],
            )
            self.assertEqual(report["supportComposeServices"], ["gamma-proxy"])
            compose = (out_dir / "docker-compose.prod-hosted.yaml").read_text(encoding="utf-8")
            self.assertIn("gamma-proxy", compose)
            self.assertIn("content-service", compose)
            self.assertIn("host.containers.internal", compose)
            self.assertIn("directConnection=true", compose)
            self.assertIn("/opt/quwoquan/gamma/.qwq_output/env/gamma/local/gamma-local/media:/srv/media:ro", compose)
            self.assertIn(
                "${LOCAL_GAMMA_LEGAL_STATIC_ROOT:-../../../.qwq_output/env/gamma/release/legal-static/current/public}:/srv/legal:ro",
                compose,
            )
            self.assertNotIn("./runtime/media", compose)
            self.assertNotIn("\n  postgres:\n", compose)
            self.assertNotIn("\n  mongodb:\n", compose)
            self.assertNotIn("\n  redis:\n", compose)
            self.assertNotIn("search-service:", compose)
            self.assertNotIn("circle-service:", compose)
            compose_payload = yaml.safe_load(compose)
            entity_env = compose_payload["services"]["entity-service"]["environment"]
            self.assertEqual(
                entity_env["ENTITY_MONGO_URI"],
                "mongodb://host.containers.internal:19410/?directConnection=true",
            )
            # prod-hosted 首波不含 elasticsearch，write-time 投影必须关闭。
            self.assertEqual(entity_env["SEARCH_ES_ENABLED"], "false")
            self.assertNotIn("SEARCH_ES_ENDPOINTS", entity_env)
            env_text = (out_dir / "stack.env").read_text(encoding="utf-8")
            self.assertIn("LOCAL_GAMMA_IMAGE_VERSION=1.20260617.rootless-service-plane", env_text)
            self.assertIn("LOCAL_GAMMA_HTTPS_PORT=18443", env_text)
            self.assertIn("LOCAL_GAMMA_ADMIN_PORT=12019", env_text)
            caddy_text = (out_dir / "runtime/Caddyfile").read_text(encoding="utf-8")
            self.assertIn("handle /v1/config/app", caddy_text)
            self.assertIn("@api_tag path /v1/tag*", caddy_text)
            self.assertIn("@pub_user path /v1/user* /v1/me /v1/me/*", caddy_text)
            self.assertIn("@api_entity path /v1/homepages*", caddy_text)
            self.assertIn("@pub_entity path /v1/homepages*", caddy_text)
            self.assertEqual(caddy_text.count("reverse_proxy entity-service:18084"), 2)
            content_prod = yaml.safe_load(
                (out_dir / "runtime/config-root/configs/content-service/prod/config.yaml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(content_prod["mongo"]["uri"], "${MONGO_URI}")
            self.assertEqual(content_prod["redis"]["rec"]["mode"], "standalone")
            self.assertEqual(content_prod["redis"]["rec"]["addr"], "${CONTENT_REDIS_REC_ADDR}")
            user_prod = yaml.safe_load(
                (out_dir / "runtime/config-root/configs/user-service/prod/config.yaml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(user_prod["postgres"]["dsn"], "${POSTGRES_DSN}")
            self.assertEqual(user_prod["mongodb"]["uri"], "${MONGODB_URI}")
            self.assertEqual(user_prod["redis"]["general"]["mode"], "standalone")
            self.assertEqual(user_prod["redis"]["general"]["addr"], "${REDIS_ADDR}")
            entity_prod = yaml.safe_load(
                (out_dir / "runtime/config-root/configs/entity-service/prod/config.yaml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIs(entity_prod["es"]["enabled"], False)

    def test_render_gray_instance_uses_non_prod_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "service-gray"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    "service",
                    "--instance",
                    "gray",
                    "--config-version",
                    "local-gamma-v1",
                    "--image-version",
                    "1.20260617.rootless-service-plane",
                    "--output-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            env_text = (out_dir / "stack.env").read_text(encoding="utf-8")
            self.assertIn("LOCAL_GAMMA_IMAGE_VERSION=1.20260617.rootless-service-plane", env_text)
            self.assertIn("LOCAL_GAMMA_HTTP_PORT=29000", env_text)
            self.assertIn("LOCAL_GAMMA_CONTENT_PORT=29220", env_text)
            self.assertIn("LOCAL_GAMMA_ENTITY_PORT=29290", env_text)
            self.assertIn("LOCAL_GAMMA_POSTGRES_PORT=29400", env_text)

    def test_load_prod_plane_images_dry_run_reports_localhost_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_dir = Path(tmp) / "keys"
            key_dir.mkdir(parents=True, exist_ok=True)
            (key_dir / "prod-service-svc").write_text("fake-key", encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/load_prod_plane_images.py",
                    "--plane",
                    "service",
                    "--key-dir",
                    str(key_dir),
                    "--services",
                    "content-service,tag-service",
                    "--dry-run",
                ],
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout.strip())
            self.assertEqual(report["services"], ["content-service", "tag-service"])
            self.assertEqual(
                report["images"]["content-service"],
                "localhost/quwoquan_service_content-service:latest",
            )
            self.assertEqual(
                report["images"]["tag-service"],
                "localhost/quwoquan_service_tag-service:latest",
            )


if __name__ == "__main__":
    unittest.main()
