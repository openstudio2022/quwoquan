# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-005
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.cli.prod import render_prod_plane_stack as render


ROOT = Path(__file__).resolve().parents[4]
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
        for key in (
            "SEARCH_ELASTICSEARCH_EXPORTER_URI",
            "SEARCH_ELASTICSEARCH_EXPORTER_API_KEY",
            "SEARCH_OBJECTS_ELASTICSEARCH_EXPORTER_API_KEY",
            "TELEMETRY_ELASTICSEARCH_EXPORTER_URI",
            "TELEMETRY_ELASTICSEARCH_EXPORTER_API_KEY",
            "PRODUCT_TELEMETRY_ELASTICSEARCH_EXPORTER_API_KEY",
            "RUNTIME_LOGS_ELASTICSEARCH_EXPORTER_API_KEY",
            "OBSERVABILITY_GRAFANA_IMAGE",
            "OBSERVABILITY_BLACKBOX_EXPORTER_IMAGE",
            "OBSERVABILITY_ELASTICSEARCH_EXPORTER_IMAGE",
        ):
            self.assertIn(key, runtime["requiredEnvironment"])

    def test_rendered_service_plane_contains_the_observability_composition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            deploy_root = Path(temporary) / "deploy"
            output = deploy_root / "prod-hosted/rendered/service-prod"
            remote_root = "/srv/quwoquan/service/instances/prod/service-a"
            with mock.patch.dict(
                os.environ,
                {"QWQ_DEPLOY_WORK_ROOT": str(deploy_root)},
                clear=False,
            ):
                render._write_observability_tree(
                    output,
                    "service",
                    render_name="service-prod",
                    remote_root=remote_root,
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
            self.assertIn(f"WorkingDirectory={remote_root}", unit_source)
            self.assertIn("ExecStart=/usr/bin/podman compose", unit_source)
            self.assertIn("ExecStop=/usr/bin/podman compose", unit_source)
            self.assertFalse((output / "observability/monitoring.env").exists())

    def test_observability_images_are_secret_env_injected_and_digest_required(self) -> None:
        compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        expected = {
            "prometheus": "OBSERVABILITY_PROMETHEUS_IMAGE",
            "alertmanager": "OBSERVABILITY_ALERTMANAGER_IMAGE",
            "grafana": "OBSERVABILITY_GRAFANA_IMAGE",
            "otel-collector": "OBSERVABILITY_OTEL_COLLECTOR_IMAGE",
            "blackbox-exporter": "OBSERVABILITY_BLACKBOX_EXPORTER_IMAGE",
            "node-exporter": "OBSERVABILITY_NODE_EXPORTER_IMAGE",
            "podman-exporter": "OBSERVABILITY_PODMAN_EXPORTER_IMAGE",
            "mongodb-exporter": "OBSERVABILITY_MONGODB_EXPORTER_IMAGE",
            "postgres-exporter": "OBSERVABILITY_POSTGRES_EXPORTER_IMAGE",
            "redis-exporter": "OBSERVABILITY_REDIS_EXPORTER_IMAGE",
            "search-elasticsearch-exporter": "OBSERVABILITY_ELASTICSEARCH_EXPORTER_IMAGE",
            "telemetry-elasticsearch-exporter": "OBSERVABILITY_ELASTICSEARCH_EXPORTER_IMAGE",
            "search-objects-elasticsearch-exporter": "OBSERVABILITY_ELASTICSEARCH_EXPORTER_IMAGE",
            "product-telemetry-elasticsearch-exporter": "OBSERVABILITY_ELASTICSEARCH_EXPORTER_IMAGE",
            "runtime-logs-elasticsearch-exporter": "OBSERVABILITY_ELASTICSEARCH_EXPORTER_IMAGE",
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
        physical_exporters = {
            "search-elasticsearch-exporter": (
                "SEARCH_ELASTICSEARCH_EXPORTER_URI",
                "SEARCH_ELASTICSEARCH_EXPORTER_API_KEY",
            ),
            "telemetry-elasticsearch-exporter": (
                "TELEMETRY_ELASTICSEARCH_EXPORTER_URI",
                "TELEMETRY_ELASTICSEARCH_EXPORTER_API_KEY",
            ),
        }
        owner_exporters = {
            "search-objects-elasticsearch-exporter": (
                "SEARCH_ELASTICSEARCH_EXPORTER_URI",
                "SEARCH_OBJECTS_ELASTICSEARCH_EXPORTER_API_KEY",
            ),
            "product-telemetry-elasticsearch-exporter": (
                "TELEMETRY_ELASTICSEARCH_EXPORTER_URI",
                "PRODUCT_TELEMETRY_ELASTICSEARCH_EXPORTER_API_KEY",
            ),
            "runtime-logs-elasticsearch-exporter": (
                "TELEMETRY_ELASTICSEARCH_EXPORTER_URI",
                "RUNTIME_LOGS_ELASTICSEARCH_EXPORTER_API_KEY",
            ),
        }
        for service, (uri_key, api_key) in {
            **physical_exporters,
            **owner_exporters,
        }.items():
            exporter = compose["services"][service]
            self.assertIn(
                f"--es.uri=${{{uri_key}:?{uri_key} is required}}",
                exporter["command"],
            )
            self.assertEqual(
                exporter["environment"]["ES_API_KEY"],
                f"${{{api_key}:?{api_key} is required}}",
            )
            self.assertNotIn("ports", exporter)
        for service in physical_exporters:
            exporter = compose["services"][service]
            self.assertIn("--es.all", exporter["command"])
            self.assertIn("--es.shards", exporter["command"])
        for service in owner_exporters:
            exporter = compose["services"][service]
            self.assertNotIn("--es.all", exporter["command"])
            self.assertIn("--es.indices", exporter["command"])
            self.assertIn("--es.shards", exporter["command"])

        telemetry_uris = {
            next(
                argument for argument in compose["services"][service]["command"]
                if argument.startswith("--es.uri=")
            )
            for service in (
                "telemetry-elasticsearch-exporter",
                "product-telemetry-elasticsearch-exporter",
                "runtime-logs-elasticsearch-exporter",
            )
        }
        self.assertEqual(
            telemetry_uris,
            {
                "--es.uri=${TELEMETRY_ELASTICSEARCH_EXPORTER_URI:?"
                "TELEMETRY_ELASTICSEARCH_EXPORTER_URI is required}"
            },
        )

        prometheus = yaml.safe_load(
            (COMPOSE.parent / "prometheus.yml").read_text(encoding="utf-8")
        )
        jobs = {job["job_name"]: job for job in prometheus["scrape_configs"]}
        physical_jobs = {
            "search-elasticsearch-exporter": "search-elasticsearch",
            "telemetry-elasticsearch-exporter": "telemetry-elasticsearch",
        }
        for job_name, resource in physical_jobs.items():
            static_config = jobs[job_name]["static_configs"][0]
            self.assertEqual(static_config["labels"]["data_resource"], resource)
            self.assertNotIn("data_owner", static_config["labels"])
            self.assertEqual(
                jobs[job_name]["metric_relabel_configs"][0]["action"],
                "drop",
            )
        for job_name, owner in (
            ("search-objects-elasticsearch-exporter", "search-objects"),
            ("product-telemetry-elasticsearch-exporter", "product-telemetry"),
            ("runtime-logs-elasticsearch-exporter", "runtime-logs"),
        ):
            static_config = jobs[job_name]["static_configs"][0]
            self.assertEqual(static_config["labels"]["data_owner"], owner)
            self.assertNotIn("data_resource", static_config["labels"])
            self.assertEqual(
                jobs[job_name]["metric_relabel_configs"][0]["action"],
                "keep",
            )
            self.assertEqual(
                static_config["targets"],
                [f"{job_name}:9114"],
            )

        alerts = yaml.safe_load(
            (COMPOSE.parent / "alerts/quwoquan_alerts.yaml").read_text(encoding="utf-8")
        )
        alert_names = {
            rule["alert"]
            for group in alerts["groups"]
            for rule in group.get("rules", [])
            if "alert" in rule
        }
        self.assertTrue(
            {
                "ElasticsearchHeapPressureHigh",
                "ElasticsearchPrimaryShardUnavailable",
                "ElasticsearchUnassignedShardsPresent",
                "ElasticsearchMergeTimeHigh",
                "ElasticsearchSnapshotStale",
                "ElasticsearchSnapshotShardFailure",
            }.issubset(alert_names)
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
        self.assertIn("deploy_observability_replica()", source)
        self.assertIn("rootlessObservabilityRuntime", source)
        self.assertIn("unit_source", source)
        self.assertIn("systemd/user", source)
        self.assertIn("observability_env", source)
        self.assertIn("runtime_env", source)
        self.assertIn("systemctl --user enable --now", source)
        self.assertIn("systemctl --user is-active --quiet", source)
        self.assertIn("/api/v1/targets", source)
        self.assertIn("Prometheus targets are not up", source)
        observability_call = (
            'deploy_observability_replica "$account" "$remote_root" '
            '"$secret_name" "$credentials_root" "$ssh_host" "$host_id" "$replica_id"'
        )
        self.assertIn(observability_call, source)
        self.assertIn(
            "[skip] observability remains bound to stable prod replicas during gray rollout",
            source,
        )
        self.assertLess(
            source.index(observability_call),
            source.index('update_stable_gray_router_replica "$account"'),
        )


if __name__ == "__main__":
    unittest.main()
