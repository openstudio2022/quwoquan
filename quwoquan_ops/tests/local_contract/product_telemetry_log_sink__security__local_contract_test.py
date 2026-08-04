from __future__ import annotations

import argparse
import hashlib
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


LOCAL_ES_ENVIRONMENT = {
    "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT": "http://elasticsearch:9200",
}
UNDECLARED_PROVIDER_ENVIRONMENT = {
    "PRODUCT_OPS_LOG_SINK_ENDPOINT": "https://undeclared-provider.invalid",
    "PRODUCT_OPS_LOG_SINK_TOKEN": "should-not-be-read",
}


def _sha256_digest(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProductTelemetryLogSinkSecurityLocalContractTest(unittest.TestCase):
    def test_contract_declares_one_elasticsearch_adapter_for_four_environments(
        self,
    ) -> None:
        specification = load_json_yaml(
            ROOT
            / "quwoquan_service/services/product-ops-service/contracts/product_ops"
            / "event_record/storage.yaml"
        )
        backends = specification["environment_backends"]

        self.assertEqual(set(backends), {"alpha", "beta", "gamma", "prod"})
        for environment in backends.values():
            self.assertEqual(environment["adapter"], "ext.obs.elasticsearch")
            self.assertEqual(environment["backend"], "elasticsearch")
        self.assertEqual(specification["fallback"], "forbidden")

    def test_all_local_targets_use_topology_elasticsearch_without_secrets(self) -> None:
        for environment, target in (
            ("alpha", "alpha-local"),
            ("beta", "beta-local"),
            ("gamma", "gamma-local"),
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary_dir:
                home = Path(temporary_dir) / "home"
                home.mkdir()
                bundle = load_product_telemetry_log_sink(
                    environment,
                    target,
                    process_environment=UNDECLARED_PROVIDER_ENVIRONMENT,
                    home=home,
                )

            self.assertEqual(bundle.source, f"{target}-elasticsearch-topology")
            self.assertEqual(bundle.status, "ready")
            self.assertEqual(bundle.environment, LOCAL_ES_ENVIRONMENT)
            self.assertIsNone(bundle.secret_path)
            self.assertTrue(bundle.redacted_digest.startswith("sha256:"))
            serialized = json.dumps(bundle.redacted_receipt(), sort_keys=True)
            self.assertNotIn("elasticsearch:9200", serialized)
            for value in UNDECLARED_PROVIDER_ENVIRONMENT.values():
                self.assertNotIn(value, serialized)

    def test_cross_environment_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported product telemetry target"):
            load_product_telemetry_log_sink("beta", "gamma-local")

    def test_full_workload_missing_binding_returns_redacted_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            args = argparse.Namespace(
                env="gamma",
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
                mock.patch.object(stackctl, "get_target", return_value={"env": "gamma"}),
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
                result = stackctl._command_up_impl(args)

            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(result["status"], "gate_block")
            self.assertEqual(
                result["logSink"],
                {
                    "adapterId": "ext.obs.elasticsearch",
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
            environment=LOCAL_ES_ENVIRONMENT,
            secret_path=None,
            source="gamma-local-elasticsearch-topology",
            status="ready",
            redacted_digest=_sha256_digest("gamma-local-elasticsearch-topology"),
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
                ) as command_health,
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                result = stackctl.command_product_telemetry_log_sink(args)

            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(
                result["actions"],
                [{"action": "health", "status": "passed"}],
            )
            self.assertEqual(
                command_health.call_args.args[0].scope,
                "content-commercial",
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

    def test_control_action_scopes_canonical_local_ca_without_leaking_environment(self) -> None:
        bundle = ProductTelemetryLogSink(
            environment=LOCAL_ES_ENVIRONMENT,
            secret_path=None,
            source="alpha-local-elasticsearch-topology",
            status="ready",
            redacted_digest=_sha256_digest("alpha-local-elasticsearch-topology"),
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            report_dir = Path(temporary_dir)
            root = report_dir / "root.pem"
            root.write_text("test-root", encoding="utf-8")
            observed: list[str] = []
            with (
                mock.patch.dict(stackctl.os.environ, {}, clear=False),
                mock.patch.object(stackctl, "load_environment_topology", return_value={}),
                mock.patch.object(stackctl, "get_target", return_value={"env": "alpha"}),
                mock.patch.object(stackctl, "resolve_report_dir", return_value=report_dir),
                mock.patch.object(
                    stackctl, "load_product_telemetry_log_sink", return_value=bundle
                ),
                mock.patch.object(stackctl, "root_certificate_path", return_value=root),
                mock.patch.object(
                    stackctl,
                    "_run_product_telemetry_log_sink_control_action",
                    side_effect=lambda **_kwargs: observed.append(
                        stackctl.os.environ.get("SSL_CERT_FILE", "")
                    ),
                ),
                mock.patch.object(stackctl, "_write_summary_bundle"),
            ):
                original = stackctl.os.environ.pop("SSL_CERT_FILE", None)
                try:
                    result = stackctl.command_product_telemetry_log_sink(
                        argparse.Namespace(target="alpha-local", action="health")
                    )
                    self.assertNotIn("SSL_CERT_FILE", stackctl.os.environ)
                finally:
                    if original is not None:
                        stackctl.os.environ["SSL_CERT_FILE"] = original

        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(observed, [str(root)])

    def test_gamma_query_control_uses_target_scoped_nonprod_operator(self) -> None:
        with mock.patch.object(
            stackctl,
            "mint_local_product_ops_operator_token",
            return_value="managed-local-token",
        ) as mint:
            session = stackctl._log_sink_control_query_session(
                api_base="https://api.gamma.quwoquan.com:19000",
                environment="gamma",
                target_name="gamma-local",
            )
        self.assertEqual(session.owner_id, "operator:content-commercial:gamma")
        self.assertEqual(session.access_token, "managed-local-token")
        mint.assert_called_once_with("gamma", "gamma-local")

    def test_prod_query_control_requires_protected_operator_token(self) -> None:
        with mock.patch.dict(
            stackctl.os.environ,
            {"PRODUCT_TELEMETRY_QUERY_TOKEN": ""},
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "query authorization is unavailable",
            ):
                stackctl._log_sink_control_query_session(
                    api_base="https://api.quwoquan.com",
                    environment="prod",
                    target_name="prod-hosted",
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
        for target in ("alpha-local", "beta-local", "gamma-local"):
            for action in (
                "cold-start",
                "health",
                "send-query",
                "permission-failure",
            ):
                with self.subTest(target=target, action=action):
                    args = parser.parse_args(
                        [
                            "product-telemetry-log-sink",
                            "--target",
                            target,
                            "--action",
                            action,
                        ]
                    )
                    self.assertEqual(args.command, "product-telemetry-log-sink")
                    self.assertEqual(args.target, target)
                    self.assertEqual(args.action, action)

    def test_control_failure_reason_is_actionable_and_redacted(self) -> None:
        identity_error = RuntimeError(
            "GATE_BLOCK: exactly one active candidate-bound identity receipt is required"
        )
        self.assertEqual(
            stackctl._product_telemetry_log_sink_failure_reason(
                "send-query",
                identity_error,
            ),
            str(identity_error),
        )
        http_error = stackctl.LocalEnvironmentHTTPError(
            method="POST",
            path="/ops/events",
            status=403,
        )
        self.assertEqual(
            stackctl._product_telemetry_log_sink_failure_reason(
                "send-query",
                http_error,
            ),
            "send-query: product-ops request failed with HTTP 403",
        )
        secret_error = RuntimeError("Bearer do-not-serialize")
        redacted = stackctl._product_telemetry_log_sink_failure_reason(
            "send-query",
            secret_error,
        )
        self.assertNotIn("do-not-serialize", redacted)


if __name__ == "__main__":
    unittest.main()
