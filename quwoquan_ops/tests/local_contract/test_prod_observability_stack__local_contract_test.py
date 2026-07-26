# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-005
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.cli.prod import render_prod_plane_stack as render


ROOT = Path(__file__).resolve().parents[3]
ACCESS = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
DEPLOY = ROOT / "quwoquan_ops/cli/prod/deploy_to_prod.sh"
COMPOSE = ROOT / "quwoquan_ops/observability/monitoring/docker-compose.prod.yml"
OTEL = ROOT / "quwoquan_ops/observability/monitoring/otel-collector.yml"


class ProdObservabilityStackContractTest(unittest.TestCase):
    def test_service_plane_declares_fail_closed_observability_runtime(self) -> None:
        access = yaml.safe_load(ACCESS.read_text(encoding="utf-8"))
        service_plane = next(
            plane for plane in access["planes"] if plane["plane"] == "service"
        )
        runtime = service_plane["rootlessObservabilityRuntime"]

        self.assertEqual(runtime["composeDirectory"], "observability")
        self.assertEqual(runtime["composeFile"], "docker-compose.prod.yml")
        self.assertEqual(
            runtime["credentialsEnvFile"],
            "observability/monitoring.env",
        )
        self.assertEqual(
            runtime["healthURLs"],
            [
                "http://127.0.0.1:9090/-/ready",
                "http://127.0.0.1:9093/-/ready",
                "http://127.0.0.1:13133/",
            ],
        )
        self.assertEqual(runtime["runtimeEnvFile"], "runtime.env")
        self.assertEqual(runtime["serviceNetworkName"], "quwoquan-prod-service")
        self.assertEqual(
            runtime["systemdUnitFile"],
            "quwoquan-observability.service",
        )
        self.assertIn(
            "ALERTMANAGER_WEBHOOK_SECRET_FILE",
            runtime["requiredEnvironment"],
        )
        self.assertIn(
            "ALERT_INGEST_TOKEN_SECRET_FILE",
            runtime["requiredEnvironment"],
        )
        self.assertIn("OTEL_TRACE_BACKEND_ENDPOINT", runtime["requiredEnvironment"])

    def test_rendered_service_plane_contains_the_observability_composition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            deploy_root = Path(temporary) / "deploy"
            output = deploy_root / "prod-hosted/rendered/service-prod"
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                render._write_observability_tree(
                    output,
                    "service",
                    render_name="service-prod",
                )

            rendered_compose = output / "observability/docker-compose.prod.yml"
            self.assertTrue(rendered_compose.is_file())
            self.assertTrue((output / "observability/prometheus.yml").is_file())
            self.assertTrue(
                (output / "observability/alerts/quwoquan_alerts.yaml").is_file()
            )
            self.assertEqual(
                (output / "observability/runtime.env").read_text(encoding="utf-8"),
                "PROD_SERVICE_NETWORK=quwoquan-prod-service\n",
            )
            unit = output / "observability/systemd/quwoquan-observability.service"
            self.assertTrue(unit.is_file())
            unit_source = unit.read_text(encoding="utf-8")
            self.assertIn("RemainAfterExit=yes", unit_source)
            self.assertIn("ExecStart=/usr/bin/podman compose", unit_source)
            self.assertIn("ExecStop=/usr/bin/podman compose", unit_source)
            self.assertFalse((output / "observability/monitoring.env").exists())

    def test_observability_images_are_secret_env_injected_and_digest_required(self) -> None:
        compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        expected = {
            "prometheus": "OBSERVABILITY_PROMETHEUS_IMAGE",
            "alertmanager": "OBSERVABILITY_ALERTMANAGER_IMAGE",
            "otel-collector": "OBSERVABILITY_OTEL_COLLECTOR_IMAGE",
            "node-exporter": "OBSERVABILITY_NODE_EXPORTER_IMAGE",
            "podman-exporter": "OBSERVABILITY_PODMAN_EXPORTER_IMAGE",
            "mongodb-exporter": "OBSERVABILITY_MONGODB_EXPORTER_IMAGE",
            "postgres-exporter": "OBSERVABILITY_POSTGRES_EXPORTER_IMAGE",
            "redis-exporter": "OBSERVABILITY_REDIS_EXPORTER_IMAGE",
        }
        for service, variable in expected.items():
            image = compose["services"][service]["image"]
            self.assertEqual(image, f"${{{variable}:?{variable} is required}}")
        self.assertEqual(
            compose["services"]["prometheus"]["ports"],
            ["127.0.0.1:9090:9090"],
        )
        self.assertEqual(
            compose["services"]["alertmanager"]["ports"],
            ["127.0.0.1:9093:9093"],
        )
        self.assertEqual(
            compose["services"]["otel-collector"]["ports"],
            ["127.0.0.1:13133:13133"],
        )

        otel = yaml.safe_load(OTEL.read_text(encoding="utf-8"))
        self.assertEqual(
            otel["extensions"]["health_check"]["endpoint"],
            "0.0.0.0:13133",
        )
        self.assertIn("health_check", otel["service"]["extensions"])
        self.assertNotIn("debug", otel["exporters"])
        trace_exporter = otel["exporters"]["otlphttp/traces"]
        self.assertEqual(
            trace_exporter["endpoint"],
            "${env:OTEL_TRACE_BACKEND_ENDPOINT}",
        )
        self.assertFalse(trace_exporter["tls"]["insecure"])
        self.assertTrue(trace_exporter["retry_on_failure"]["enabled"])
        self.assertTrue(trace_exporter["sending_queue"]["enabled"])
        self.assertEqual(
            otel["service"]["pipelines"]["traces"]["exporters"],
            ["otlphttp/traces"],
        )

    def test_deploy_orchestrates_observability_before_traffic_routing(self) -> None:
        source = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("deploy_observability_stack()", source)
        self.assertIn("rootlessObservabilityRuntime", source)
        self.assertIn("unit_source", source)
        self.assertIn("systemd/user", source)
        self.assertIn("observability_env", source)
        self.assertIn("runtime_env", source)
        self.assertIn("systemctl --user enable --now", source)
        self.assertIn("systemctl --user is-active --quiet", source)
        self.assertIn("/api/v1/targets", source)
        self.assertIn("Prometheus targets are not up", source)
        self.assertLess(
            source.index("deploy_observability_stack"),
            source.index("update_stable_gray_router"),
        )


if __name__ == "__main__":
    unittest.main()
