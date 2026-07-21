from __future__ import annotations

import json
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]


class ProdPlaneRuntimeStackTest(unittest.TestCase):
    @staticmethod
    def _render_env(tmp: str) -> tuple[dict[str, str], Path]:
        output_root = Path(tmp) / ".qwq_output"
        deploy_root = Path(tmp) / "deploy"
        package_root = deploy_root / "prod-hosted" / "packages"
        artifact_manifest = Path(tmp) / "release-artifact-manifest.json"
        artifact_manifest.write_text("{}\n", encoding="utf-8")
        service_names = [
            "rec-model-service",
            "content-service",
            "chat-service",
            "user-service",
            "assistant-service",
            "product-ops-service",
            "platform-ops-service",
            "tag-service",
            "entity-service",
            "integration-service",
            "notification-service",
            "realtime-gateway",
            "rtc-service",
        ]
        for service in service_names:
            package = package_root / "service" / service
            package.mkdir(parents=True, exist_ok=True)
            default_config = package / "default_config.yaml"
            environment_config = package / "config.yaml"
            default_config.write_text("{}\n", encoding="utf-8")
            environment_config.write_text("{}\n", encoding="utf-8")
            release = package / "releases/local-gamma-v1.yaml"
            release.parent.mkdir(parents=True, exist_ok=True)
            release.write_text("config:\n  version: local-gamma-v1\n", encoding="utf-8")
            digest = lambda path: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            (package / "report.json").write_text(
                json.dumps(
                    {
                        "provenance": {
                            "files": {
                                "defaultConfig": digest(default_config),
                                "environmentConfig": digest(environment_config),
                            },
                            "releaseFiles": {release.name: digest(release)},
                            "releaseArtifact": {
                                "manifest": str(artifact_manifest),
                                "manifestSha256": digest(artifact_manifest),
                                "configVersion": "local-gamma-v1",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
        legal = package_root / "legal-static/current/public"
        legal.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["QWQ_OUTPUT_ROOT"] = str(output_root)
        env["QWQ_DEPLOY_WORK_ROOT"] = str(deploy_root)
        return env, output_root

    def test_render_service_plane_outputs_onebox_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "service"
            env, output_root = self._render_env(tmp)
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
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))
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
                    "platform-ops-service",
                    "tag-service",
                    "entity-service",
                    "integration-service",
                    "notification-service",
                ],
            )
            self.assertEqual(report["supportComposeServices"], ["gamma-proxy"])
            compose = (out_dir / "docker-compose.prod-hosted.yaml").read_text(encoding="utf-8")
            self.assertIn("gamma-proxy", compose)
            self.assertIn("content-service", compose)
            self.assertIn("host.containers.internal", compose)
            self.assertIn("directConnection=true", compose)
            self.assertIn(
                f"{output_root / 'env/prod/local/prod-hosted/process/volumes/media'}:/srv/media:ro",
                compose,
            )
            self.assertIn(
                "./runtime/legal-static:/srv/legal:ro",
                compose,
            )
            self.assertNotIn("gamma/local/gamma-local", compose)
            self.assertNotIn("\n  postgres:\n", compose)
            self.assertNotIn("\n  mongodb:\n", compose)
            self.assertNotIn("\n  redis:\n", compose)
            self.assertNotIn("\n  search-service:\n", compose)
            self.assertNotIn("\n  circle-service:\n", compose)
            compose_payload = yaml.safe_load(compose)
            entity_env = compose_payload["services"]["entity-service"]["environment"]
            self.assertEqual(
                entity_env["ENTITY_MONGO_URI"],
                "mongodb://host.containers.internal:19410/?directConnection=true",
            )
            # prod-hosted 首波不含 elasticsearch，write-time 投影必须关闭。
            self.assertEqual(entity_env["SEARCH_ES_ENABLED"], "false")
            self.assertNotIn("SEARCH_ES_ENDPOINTS", entity_env)
            integration = compose_payload["services"]["integration-service"]
            integration_env = integration["environment"]
            self.assertEqual(
                integration_env["INTEGRATION_MONGO_URI"],
                "mongodb://host.containers.internal:19410/?directConnection=true",
            )
            self.assertEqual(integration_env["INTEGRATION_PUSH_ENABLED"], "true")
            self.assertEqual(integration_env["INTEGRATION_PUSH_MODE"], "real")
            self.assertEqual(
                integration_env["INTEGRATION_PUSH_APNS_ENVIRONMENT"],
                "production",
            )
            self.assertEqual(
                integration["env_file"],
                ["/home/prod-service-svc/credentials/integration/push.env"],
            )
            self.assertIn(
                "/home/prod-service-svc/credentials/integration/apns-auth-key.p8:"
                "/run/secrets/quwoquan/integration/apns-auth-key.p8:ro",
                integration["volumes"],
            )
            self.assertIn(
                "/home/prod-service-svc/credentials/integration/"
                "fcm-service-account.json:/run/secrets/quwoquan/integration/"
                "fcm-service-account.json:ro",
                integration["volumes"],
            )
            notification_env = compose_payload["services"]["notification-service"][
                "environment"
            ]
            self.assertEqual(
                notification_env["NOTIFICATION_MONGO_URI"],
                "mongodb://host.containers.internal:19410/?directConnection=true",
            )
            self.assertEqual(
                notification_env["NOTIFICATION_REDIS_ADDR"],
                "host.containers.internal:19420",
            )
            self.assertEqual(notification_env["NOTIFICATION_REDIS_GENERAL_DB"], "1")
            self.assertEqual(notification_env["NOTIFICATION_REDIS_REALTIME_DB"], "4")
            self.assertEqual(
                notification_env["NOTIFICATION_REALTIME_BASE_URL"],
                "http://host.containers.internal:"
                "${LOCAL_GAMMA_REALTIME_PORT:?realtime port is required}",
            )
            env_text = (out_dir / "stack.env").read_text(encoding="utf-8")
            self.assertIn("LOCAL_GAMMA_IMAGE_VERSION=1.20260617.rootless-service-plane", env_text)
            self.assertIn("LOCAL_GAMMA_HTTPS_PORT=18443", env_text)
            self.assertIn("LOCAL_GAMMA_ADMIN_PORT=12019", env_text)
            self.assertIn("LOCAL_GAMMA_INTEGRATION_PORT=19310", env_text)
            self.assertIn("LOCAL_GAMMA_NOTIFICATION_PORT=19320", env_text)
            self.assertIn("LOCAL_GAMMA_REALTIME_PORT=19340", env_text)
            self.assertNotIn("INTEGRATION_PUSH_APNS_KEY_ID", env_text)
            self.assertNotIn("INTEGRATION_PUSH_FCM_PROJECT_ID", env_text)
            caddy_text = (out_dir / "runtime/Caddyfile").read_text(encoding="utf-8")
            self.assertNotIn("/v1/", caddy_text)
            self.assertNotIn("\n:80 {", caddy_text)
            self.assertIn("handle /config/app", caddy_text)
            self.assertIn("@api_tag path /tag*", caddy_text)
            self.assertIn(
                "@api_user path /auth* /owner* /user* /me /me/*",
                caddy_text,
            )
            self.assertIn("@api_entity path /homepages*", caddy_text)
            self.assertNotIn("@pub_entity path /homepages*", caddy_text)
            self.assertEqual(caddy_text.count("reverse_proxy entity-service:18084"), 1)
            self.assertEqual(caddy_text.count("handle /legal/manifest.json {"), 1)
            self.assertEqual(
                caddy_text.count('Content-Type "text/html; charset=utf-8"'),
                1,
            )
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
            # 服务启动与 Platform ConfigSnapshot 共同消费同一发布包路径；
            # 不得复制旧的 repository-shaped config tree。
            for service in report["configServices"]:
                release = (
                    out_dir
                    / "runtime/config-root/releases/config"
                    / service
                    / "local-gamma-v1.yaml"
                )
                self.assertTrue(release.is_file(), release)
                self.assertEqual(
                    yaml.safe_load(release.read_text(encoding="utf-8"))["config"][
                        "version"
                    ],
                    "local-gamma-v1",
                )
            self.assertFalse(
                (out_dir / "runtime/config-root/quwoquan_service").exists()
            )

    def test_render_gray_instance_uses_non_prod_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "service-gray"
            env, _ = self._render_env(tmp)
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
                env=env,
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
            self.assertIn("LOCAL_GAMMA_INTEGRATION_PORT=29310", env_text)
            self.assertIn("LOCAL_GAMMA_NOTIFICATION_PORT=29320", env_text)
            self.assertIn("LOCAL_GAMMA_REALTIME_PORT=29340", env_text)
            self.assertIn("LOCAL_GAMMA_RTC_PORT=29350", env_text)
            self.assertIn("LOCAL_GAMMA_POSTGRES_PORT=29400", env_text)

    def test_render_edge_plane_wires_realtime_and_rtc_with_external_data(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "edge"
            env, _ = self._render_env(tmp)
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    "edge",
                    "--instance",
                    "prod",
                    "--config-version",
                    "local-gamma-v1",
                    "--image-version",
                    "d6ccc4c96adb",
                    "--output-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(
                (out_dir / "provenance.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["plane"], "edge")
            self.assertEqual(
                report["governedComposeServices"],
                ["realtime-gateway", "rtc-service"],
            )
            compose = yaml.safe_load(
                (out_dir / "docker-compose.prod-hosted.yaml").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                set(compose["services"]),
                {"realtime-gateway", "rtc-service"},
            )
            realtime_env = compose["services"]["realtime-gateway"]["environment"]
            rtc_env = compose["services"]["rtc-service"]["environment"]
            self.assertEqual(
                realtime_env["REALTIME_REDIS_ADDR"],
                "host.containers.internal:19420",
            )
            self.assertEqual(
                rtc_env["MONGO_URI"],
                "mongodb://host.containers.internal:19410/?directConnection=true",
            )
            self.assertEqual(rtc_env["REDIS_ADDR"], "host.containers.internal:19420")
            self.assertIn(
                "PROD_RTC_MEDIA_CONNECTION_URL",
                rtc_env["RTC_MEDIA_CONNECTION_URL"],
            )
            self.assertNotIn("depends_on", compose["services"]["realtime-gateway"])
            self.assertNotIn("depends_on", compose["services"]["rtc-service"])
            env_text = (out_dir / "stack.env").read_text(encoding="utf-8")
            self.assertIn(
                "LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE="
                "localhost/quwoquan_service_realtime-gateway:d6ccc4c96adb",
                env_text,
            )
            self.assertIn(
                "LOCAL_GAMMA_RTC_SERVICE_IMAGE="
                "localhost/quwoquan_service_rtc-service:d6ccc4c96adb",
                env_text,
            )
            self.assertIn("LOCAL_GAMMA_REALTIME_PORT=19340", env_text)
            self.assertIn("LOCAL_GAMMA_RTC_PORT=19350", env_text)

    def test_render_rejects_package_without_release_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "service"
            env, _ = self._render_env(tmp)
            report = Path(tmp) / "deploy/prod-hosted/packages/service/content-service/report.json"
            report.write_text("{}\n", encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--config-version",
                    "local-gamma-v1",
                    "--output-dir",
                    str(out_dir),
                ],
                cwd=str(ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid package provenance", result.stdout + result.stderr)

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
                    "--image-version",
                    "test-build-123",
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
                "localhost/quwoquan_service_content-service:test-build-123",
            )
            self.assertEqual(
                report["images"]["tag-service"],
                "localhost/quwoquan_service_tag-service:test-build-123",
            )


if __name__ == "__main__":
    unittest.main()
