from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from quwoquan_ops.cli.lib.output_paths import (
    deployment_target_path_in_work_root,
)
from quwoquan_ops.cli.prod import render_prod_plane_stack as render


ROOT = Path(__file__).resolve().parents[4]
CANDIDATE_DIGEST = "sha256:" + ("b" * 64)
ARTIFACT_DIGEST = "sha256:" + ("c" * 64)
POLICY_PATH = ROOT / "quwoquan_ops/environments/prod/rollout/routing_policy.yaml"


class ProdPlaneRuntimeStackTest(unittest.TestCase):
    """spec_ref: zero-risk-production-readiness/spec.md#GWT-003"""
    @staticmethod
    def _resolver_path(tmp: str, *segments: str) -> Path:
        root = Path(tmp)
        return deployment_target_path_in_work_root(
            root / "deploy",
            "prod-hosted",
            *segments,
        )

    @staticmethod
    def _render_dir(tmp: str, name: str) -> Path:
        root = Path(tmp)
        return deployment_target_path_in_work_root(
            root / "deploy",
            "prod-hosted",
            "rendered",
            name,
        )

    @staticmethod
    def _render_env(tmp: str) -> tuple[dict[str, str], Path]:
        output_root = Path(tmp) / ".qwq_output"
        deploy_root = Path(tmp) / "deploy"
        artifact_manifest = Path(tmp) / "release-artifact-manifest.json"
        artifact_manifest.write_text("{}\n", encoding="utf-8")
        service_names = sorted(
            {
                str(service)
                for plane_name in ("service", "edge")
                for service in (
                    render._plane_spec(plane_name).get("rootlessConfigServices") or []
                )
            }
        )
        for service in service_names:
            package = deployment_target_path_in_work_root(
                deploy_root,
                "prod-hosted",
                "packages",
                "services",
                service,
            )
            package.mkdir(parents=True, exist_ok=True)
            environment_config = package / "config/config.yaml"
            environment_config.parent.mkdir(parents=True, exist_ok=True)
            config_version = "sha256:" + ("a" * 64)
            environment_config.write_text(
                "config:\n  version: sha256:" + ("a" * 64) + "\n",
                encoding="utf-8",
            )

            def digest(path: Path) -> str:
                return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

            config_digest = digest(environment_config)
            (package / "provenance.json").write_text(
                json.dumps(
                    {
                        "schema": "qwq.service_package",
                        "service": service,
                        "environment": "prod",
                        "configVersion": config_version,
                        "digests": {"config": config_digest},
                        "releaseEvidence": {
                            "manifest": str(artifact_manifest),
                            "evidenceFileDigest": digest(artifact_manifest),
                            "artifactDigest": ARTIFACT_DIGEST,
                            "candidateId": CANDIDATE_DIGEST,
                            "verifiedConfigDigest": config_digest,
                        },
                    }
                ),
                encoding="utf-8",
            )
        legal = deployment_target_path_in_work_root(
            deploy_root,
            "prod-hosted",
            "packages",
            "legal-static",
            "current",
            "public",
        )
        legal.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["QWQ_OUTPUT_ROOT"] = str(output_root)
        env["QWQ_DEPLOY_WORK_ROOT"] = str(deploy_root)
        return env, output_root

    def test_render_service_plane_outputs_onebox_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._render_dir(tmp, "service-prod-r0")
            env, output_root = self._render_env(tmp)
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    "service",
                    "--instance",
                    "prod",
                    "--candidate-digest",
                    CANDIDATE_DIGEST,
                    "--image-transport-tag",
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
                    "api-edge",
                    "recommendation-service",
                    "content-service",
                    "chat-service",
                    "circle-service",
                    "user-service",
                    "assistant-service",
                    "product-ops-service",
                    "platform-ops-service",
                    "search-service",
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
            self.assertIn("\n  search-service:\n", compose)
            self.assertIn("\n  circle-service:\n", compose)
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
            self.assertNotIn("INTEGRATION_PUSH_ENABLED", integration_env)
            self.assertNotIn("INTEGRATION_PUSH_MODE", integration_env)
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
            self.assertIn(
                "(business_api_edge) {\n"
                "\treverse_proxy api-edge:18079 {\n"
                "\t\theader_up X-Edge-Client-IP {remote_host}",
                caddy_text,
            )
            self.assertIn(
                "handle_path /api/* {\n\t\timport business_api_edge\n\t}",
                caddy_text,
            )
            api_gateway = caddy_text.split("api.quwoquan.com {", 1)[1].split(
                "\n}\n\nops.quwoquan.com {", 1
            )[0]
            self.assertIn(
                "handle {\n\t\timport business_api_edge\n\t}",
                api_gateway,
            )
            self.assertNotRegex(
                caddy_text,
                r"reverse_proxy\s+(?:tag|search|user|entity)-service(?::\d+)?\b",
            )
            self.assertNotRegex(caddy_text, r"@(api|pub)_[a-z_]+\s+path")
            # API and public-Web authorities each expose the same immutable
            # legal package; this is one package with two routed surfaces.
            self.assertEqual(caddy_text.count("handle /legal/manifest.json {"), 2)
            self.assertEqual(
                caddy_text.count('Content-Type "text/html; charset=utf-8"'),
                3,
            )
            # 服务启动与 Platform ConfigSnapshot 共同消费同一 package 有效配置；
            # 不得复制旧的 versioned/repository-shaped config tree。
            for service in report["configServices"]:
                release = out_dir / "runtime/config-root" / f"{service}.yaml"
                self.assertTrue(release.is_file(), release)
                self.assertRegex(
                    yaml.safe_load(release.read_text(encoding="utf-8"))["config"]["version"],
                    r"^sha256:[0-9a-f]{64}$",
                )
            self.assertFalse((out_dir / "runtime/config-root/releases").exists())
            self.assertFalse(
                (out_dir / "runtime/config-root/quwoquan_service").exists()
            )
            runtime_policy = out_dir / "runtime/config-root/rollout/routing_policy.yaml"
            portal_policy = out_dir / "runtime/config-root/gray-routing/policy.yaml"
            self.assertEqual(runtime_policy.read_bytes(), POLICY_PATH.read_bytes())
            self.assertEqual(portal_policy.read_bytes(), POLICY_PATH.read_bytes())

    def test_prevalidate_render_is_isolated_digest_pinned_and_systemd_owned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._render_dir(tmp, "service-prevalidate-r0")
            env, _ = self._render_env(tmp)
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    "service",
                    "--instance",
                    "prevalidate",
                    "--prevalidate-scope",
                    "first-party",
                    "--data-mode",
                    "isolated",
                    "--candidate-digest",
                    CANDIDATE_DIGEST,
                    "--image-transport-tag",
                    "1.20260726.42",
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
            self.assertEqual(report["instance"], "prevalidate")
            self.assertEqual(report["dataMode"], "isolated")
            self.assertEqual(report["imageAndConfigOnlyServices"], ["integration-service"])
            self.assertNotIn("integration-service", report["startupServices"])
            self.assertIsNone(report["observabilityRuntime"])
            self.assertFalse(
                report["configSources"]["prevalidationProjection"][
                    "releaseEvidenceEligible"
                ]
            )

            compose = yaml.safe_load(
                (out_dir / "docker-compose.prod-hosted.yaml").read_text(encoding="utf-8")
            )
            services = compose["services"]
            for name in (
                "postgres",
                "mongodb",
                "mongo-init",
                "redis",
                "object-storage",
                "object-storage-init",
                "elasticsearch",
            ):
                self.assertRegex(services[name]["image"], r"@sha256:[0-9a-f]{64}$")
                self.assertRegex(services[name]["mem_limit"], r"^[1-9][0-9]*m$")
                self.assertGreater(services[name]["pids_limit"], 0)
            self.assertEqual(
                services["elasticsearch"]["environment"]["ES_JAVA_OPTS"],
                "-Xms128m -Xmx128m",
            )
            self.assertIn("integration-service", services)
            self.assertNotIn("livekit", services)
            self.assertNotIn("coturn", services)
            self.assertEqual(
                services["content-service"]["environment"]["MONGO_URI"],
                "mongodb://mongodb:27017/?directConnection=true",
            )
            self.assertEqual(
                services["entity-service"]["environment"]["SEARCH_ES_ENDPOINTS"],
                "http://elasticsearch:9200",
            )
            self.assertEqual(
                services["user-service"]["environment"]["APP_ENV"], "prod"
            )
            self.assertEqual(
                services["user-service"]["environment"][
                    "QWQ_NONPROMOTABLE_PREVALIDATION"
                ],
                "first-party",
            )
            self.assertEqual(
                services["assistant-service"]["environment"][
                    "ASSISTANT_MODEL_API_KEY"
                ],
                "provider-unavailable",
            )
            self.assertNotIn(
                "./release-ledger:/var/lib/quwoquan/release-state:ro",
                services["platform-ops-service"].get("volumes") or [],
            )
            self.assertNotIn("env_file", services["integration-service"])
            unit = (
                out_dir / "systemd/quwoquan-service-prevalidate.service"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "WorkingDirectory=/home/prod-service-svc/stack/prevalidate",
                unit,
            )
            exec_start = next(
                line for line in unit.splitlines() if line.startswith("ExecStart=")
            )
            self.assertNotIn("integration-service", exec_start)
            self.assertIn("recommendation-service", exec_start)
            self.assertNotIn("/credentials/runtime.env", unit)
            self.assertIn("WantedBy=default.target", unit)
            env_text = (out_dir / "stack.env").read_text(encoding="utf-8")
            self.assertEqual((out_dir / "stack.env").stat().st_mode & 0o777, 0o600)
            for key in (
                "AUTH_JWT_SECRET",
                "AUTH_DEVICE_TICKET_SECRET",
                "OTP_CODE_REF_KEYS_JSON",
                "QWQ_PUSH_TOKEN_ENCRYPTION_KEY",
                "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET",
                "QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT",
            ):
                self.assertRegex(env_text, rf"(?m)^{key}=.+$")
            required = set(
                re.findall(
                    r"\$\{([A-Z0-9_]+):\?",
                    (out_dir / "docker-compose.prod-hosted.yaml").read_text(
                        encoding="utf-8"
                    ),
                )
            )
            available = {
                line.split("=", 1)[0]
                for line in env_text.splitlines()
                if "=" in line
            }
            self.assertEqual(required - available, set())

    def test_render_gray_instance_uses_non_prod_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = self._render_dir(tmp, "service-gray-r0")
            env, _ = self._render_env(tmp)
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    "service",
                    "--instance",
                    "gray",
                    "--candidate-digest",
                    CANDIDATE_DIGEST,
                    "--image-transport-tag",
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
            out_dir = self._render_dir(tmp, "edge-prod-r0")
            env, _ = self._render_env(tmp)
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    "edge",
                    "--instance",
                    "prod",
                    "--candidate-digest",
                    CANDIDATE_DIGEST,
                    "--image-transport-tag",
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
            out_dir = self._render_dir(tmp, "service-prod-r0")
            env, _ = self._render_env(tmp)
            report = self._resolver_path(
                tmp,
                "packages",
                "services",
                "content-service",
                "provenance.json",
            )
            report.write_text("{}\n", encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--candidate-digest",
                    CANDIDATE_DIGEST,
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

    def test_render_rejects_unscoped_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env, _ = self._render_env(tmp)
            rejected_output = Path(tmp) / "outside-render"
            result = subprocess.run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    "service",
                    "--instance",
                    "prod",
                    "--candidate-digest",
                    CANDIDATE_DIGEST,
                    "--output-dir",
                    str(rejected_output),
                ],
                cwd=str(ROOT),
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("resolver-derived", result.stdout + result.stderr)
            self.assertFalse(rejected_output.exists())

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
                    "--image-transport-tag",
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
