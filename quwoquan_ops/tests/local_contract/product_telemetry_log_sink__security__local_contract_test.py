from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.common import ROOT, load_json_yaml
from quwoquan_ops.cli.lib.product_telemetry_log_sink import (
    ProductTelemetryLogSink,
    load_product_telemetry_log_sink,
)


GAMMA_ES_ENVIRONMENT = {
    "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT": "http://elasticsearch:9200",
}
PROD_SLS_ENVIRONMENT = {
    "PRODUCT_OPS_SLS_REGION": "cn-shanghai",
    "PRODUCT_OPS_SLS_ENDPOINT": "https://cn-shanghai.log.aliyuncs.com",
    "PRODUCT_OPS_SLS_PROJECT": "quwoquan-prod",
    "ALIBABA_CLOUD_ACCESS_KEY_ID": "should-not-be-read",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "should-not-be-read",
}


class ProductTelemetryLogSinkSecurityLocalContractTest(unittest.TestCase):
    def test_gamma_profile_declares_elasticsearch_without_sls_secret(self) -> None:
        specification = load_json_yaml(
            ROOT
            / "quwoquan_ops/environments/cloud-providers/aliyun/sls"
            / "product_telemetry.yaml"
        )
        profiles = specification["spec"]["deploymentProfiles"]

        self.assertEqual(specification["metadata"]["environments"], ["prod"])
        for profile in ("integration", "release"):
            gamma = profiles["gamma"][profile]
            self.assertEqual(gamma["backend"], "elasticsearch_local")
            self.assertFalse(gamma["requiresSecret"])
        self.assertEqual(profiles["prod"]["backend"], "aliyun_sls")
        self.assertTrue(profiles["prod"]["requiresSecret"])

    def test_gamma_uses_topology_elasticsearch_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            home = Path(temporary_dir) / "home"
            home.mkdir()
            bundle = load_product_telemetry_log_sink(
                "gamma",
                "gamma-local",
                process_environment=PROD_SLS_ENVIRONMENT,
                home=home,
            )

        self.assertEqual(bundle.source, "gamma-local-elasticsearch-topology")
        self.assertEqual(bundle.status, "ready")
        self.assertEqual(bundle.environment, GAMMA_ES_ENVIRONMENT)
        self.assertIsNone(bundle.secret_path)
        self.assertTrue(bundle.redacted_digest.startswith("sha256:"))
        serialized = json.dumps(bundle.redacted_receipt(), sort_keys=True)
        self.assertNotIn("elasticsearch:9200", serialized)
        for value in PROD_SLS_ENVIRONMENT.values():
            self.assertNotIn(value, serialized)

    def test_beta_uses_postgres_service_config_without_material(self) -> None:
        bundle = load_product_telemetry_log_sink("beta", "beta-local")

        self.assertEqual(bundle.source, "service-config-postgres-telemetry")
        self.assertEqual(bundle.status, "ready")
        self.assertEqual(bundle.environment, {})
        self.assertIsNone(bundle.secret_path)

    def test_cross_environment_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported product telemetry target"):
            load_product_telemetry_log_sink("beta", "gamma-local")

    def test_gamma_binding_clears_inherited_prod_provider_material(self) -> None:
        environment = dict(PROD_SLS_ENVIRONMENT)
        storage = mock.Mock(environment={}, host_endpoint="http://object-storage:9000")
        with (
            mock.patch.object(
                stackctl,
                "prepare_local_gamma_object_storage",
                return_value=storage,
            ),
            mock.patch.object(
                stackctl,
                "_bind_local_external_provider_environment",
                return_value=None,
            ),
            mock.patch.object(
                stackctl,
                "load_port_manifest",
                return_value={},
            ),
            mock.patch.object(
                stackctl,
                "profile_ports",
                return_value={"object-storage-edge": 19440},
            ),
        ):
            error = stackctl._bind_gamma_external_provider_environment(environment)

        self.assertIsNone(error)
        for key in PROD_SLS_ENVIRONMENT:
            self.assertEqual(environment[key], "")

    def test_full_workload_missing_binding_returns_redacted_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            args = argparse.Namespace(
                env="beta",
                target="",
                workload="full",
                skip_app=True,
                skip_build=False,
                build_only=False,
                build_services="",
                device_id="",
                rollout_mode="",
            )
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(stackctl, "get_target", return_value={"env": "beta"}),
                mock.patch.object(stackctl, "resolve_report_dir", return_value=report_dir),
                mock.patch.object(
                    stackctl,
                    "can_reuse_package",
                    return_value=(True, "fixed candidate ready"),
                ),
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_log_sink",
                    side_effect=RuntimeError(
                        "endpoint=https://provider.internal token=should-not-appear"
                    ),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_up(args)

            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(result["status"], "gate_block")
            self.assertEqual(
                result["logSink"],
                {
                    "source": "unavailable",
                    "status": "gate_block",
                    "redactedDigest": "",
                },
            )
            serialized = json.dumps(
                {
                    "result": result,
                    "report": json.loads(
                        (report_dir / "report.json").read_text(encoding="utf-8")
                    ),
                },
                sort_keys=True,
            )
            self.assertNotIn("https://provider.internal", serialized)
            self.assertNotIn("should-not-appear", serialized)

    def test_controlled_health_receipt_is_provider_neutral_and_redacted(self) -> None:
        bundle = ProductTelemetryLogSink(
            environment=GAMMA_ES_ENVIRONMENT,
            secret_path=None,
            source="gamma-local-elasticsearch-topology",
            status="ready",
            redacted_digest="sha256:1234567890abcdef",
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            args = argparse.Namespace(target="gamma-local", action="health")
            with (
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(stackctl, "get_target", return_value={"env": "gamma"}),
                mock.patch.object(stackctl, "resolve_report_dir", return_value=report_dir),
                mock.patch.object(
                    stackctl,
                    "load_product_telemetry_log_sink",
                    return_value=bundle,
                ),
                mock.patch.object(
                    stackctl,
                    "command_health",
                    return_value={"exitCode": 0},
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_product_telemetry_log_sink(args)

            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(
                result["actions"],
                [{"action": "health", "status": "passed"}],
            )
            self.assertEqual(result["logSink"], bundle.redacted_receipt())
            serialized = json.dumps(
                {
                    "result": result,
                    "report": json.loads(
                        (report_dir / "report.json").read_text(encoding="utf-8")
                    ),
                },
                sort_keys=True,
            )
            self.assertNotIn("elasticsearch:9200", serialized)

    def test_gamma_query_control_requires_protected_operator_token(self) -> None:
        with mock.patch.dict(
            stackctl.os.environ,
            {"PRODUCT_TELEMETRY_QUERY_TOKEN": ""},
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "query authorization is unavailable",
            ):
                stackctl._log_sink_control_query_session(
                    api_base="https://api.gamma.quwoquan.com:19000",
                    environment="gamma",
                    target_name="gamma-local",
                )

    def test_cold_start_reuses_package_bound_images(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary_dir,
            mock.patch.object(
                stackctl,
                "command_up",
                return_value={"exitCode": 0},
            ) as command_up,
        ):
            stackctl._run_product_telemetry_log_sink_control_action(
                action="cold-start",
                target_name="gamma-local",
                environment="gamma",
                report_dir=Path(temporary_dir),
            )

        args = command_up.call_args.args[0]
        self.assertTrue(args.skip_build)
        self.assertTrue(args.skip_app)
        self.assertEqual(args.workload, "full")

    def test_control_parser_exposes_all_required_actions(self) -> None:
        parser = stackctl.build_parser()
        for action in ("cold-start", "health", "send-query", "permission-failure"):
            with self.subTest(action=action):
                args = parser.parse_args(
                    [
                        "product-telemetry-log-sink",
                        "--target",
                        "beta-local",
                        "--action",
                        action,
                    ]
                )
                self.assertEqual(args.command, "product-telemetry-log-sink")
                self.assertEqual(args.action, action)


if __name__ == "__main__":
    unittest.main()
