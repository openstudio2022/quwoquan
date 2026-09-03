# spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-002

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib.storage_contract_view import StorageContractViewError

ROOT = Path(__file__).resolve().parents[4]
GATE_PATH = ROOT / "quwoquan_ops/gate/verify_runtime_log_governance.py"
SPEC = importlib.util.spec_from_file_location("verify_runtime_log_governance", GATE_PATH)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


class CandidateOwnedElasticsearchGovernanceTest(unittest.TestCase):
    def test_runtime_log_storage_uses_the_exact_canonical_view_keyset(self) -> None:
        issues: list[str] = []
        expected_payload = {
            key: object()
            for key in GATE.RUNTIME_LOG_STORAGE_KEYS
        }

        with mock.patch.object(
            GATE,
            "load_storage_contract_view",
            return_value=expected_payload,
        ) as loader:
            payload = GATE._load_storage(GATE.STORAGE, issues)

        self.assertIs(payload, expected_payload)
        self.assertEqual(issues, [])
        loader.assert_called_once_with(
            GATE.STORAGE,
            expected_keys=GATE.RUNTIME_LOG_STORAGE_KEYS,
        )

    def test_runtime_log_storage_view_drift_is_a_gate_failure(self) -> None:
        issues: list[str] = []

        with mock.patch.object(
            GATE,
            "load_storage_contract_view",
            side_effect=StorageContractViewError("keyset drifted"),
        ):
            payload = GATE._load_storage(GATE.STORAGE, issues)

        self.assertEqual(payload, {})
        self.assertEqual(len(issues), 1)
        self.assertIn("canonical storage view", issues[0])
        self.assertIn("keyset drifted", issues[0])

    def test_data_runtime_uses_data_owned_run_manifest_writer(self) -> None:
        issues: list[str] = []

        GATE._require_text(
            ROOT / "quwoquan_data/scripts/core/runtime_observability.py",
            ('"repo"', "write_data_run_manifest"),
            issues,
        )

        self.assertEqual(issues, [])
    def test_environment_config_cannot_persist_a_resolved_es_endpoint(self) -> None:
        issues: list[str] = []
        configs = {
            environment: {"overrides": {}}
            for environment in ("alpha", "beta", "gamma", "prod")
        }
        configs["gamma"] = {
            "overrides": {
                "sys.product-ops-service.elasticsearch.endpoint": (
                    "http://elasticsearch:9200"
                )
            }
        }

        GATE._verify_candidate_owned_environment_elasticsearch_config(
            issues,
            configs=configs,
        )

        self.assertEqual(len(issues), 1)
        self.assertIn("Product Ops gamma environment config must not own", issues[0])
        self.assertIn("candidate-owned Provider Binding endpoint", issues[0])

    def test_current_environment_configs_leave_es_endpoint_to_candidate(self) -> None:
        issues: list[str] = []

        GATE._verify_candidate_owned_environment_elasticsearch_config(issues)

        self.assertEqual(issues, [])

    def test_retired_backend_scan_includes_portal_javascript_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            portal_source = Path(temporary) / "controlPlane.test.mjs"
            stale_source = "s" + "ls_raw"
            portal_source.write_text(
                f"const source = '{stale_source}';\n",
                encoding="utf-8",
            )

            scanner = getattr(GATE, "_find_" + "s" + "ls_matches")
            matches = scanner((Path(temporary),))

        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].endswith("controlPlane.test.mjs:1"))

    def test_workspace_compose_endpoint_and_image_are_rejected(self) -> None:
        issues: list[str] = []

        GATE._verify_candidate_owned_local_elasticsearch_runtime(
            issues,
            startup_text="""COMPOSE_FILES+=("$ROOT/quwoquan_service/services/product-ops-service/deploy/local-elasticsearch.compose.yaml")
export PRODUCT_OPS_ELASTICSEARCH_ENDPOINT="${PRODUCT_OPS_ELASTICSEARCH_ENDPOINT:-http://elasticsearch:9200}"
export LOCAL_GAMMA_ELASTICSEARCH_IMAGE="mutable"
export QWQ_COMPOSE_ELASTICSEARCH_IMAGE="mutable"
""",
            resolver_text=(
                'PRODUCT_OPS_ELASTICSEARCH_ENDPOINT = "http://elasticsearch:9200"'
            ),
            candidate_manifest_text="{}",
            stackctl_text="",
        )

        joined = "\n".join(issues)
        self.assertIn("candidate-owned QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE", joined)
        self.assertIn("must not resolve workspace Compose", joined)
        self.assertIn("must not synthesize an Elasticsearch endpoint", joined)
        self.assertIn("stackctl must pass the candidate-owned", joined)
        self.assertIn("observability-log-sink", joined)
        self.assertIn("composeRef", joined)
        self.assertIn("composeDigest", joined)

    def test_candidate_owned_single_track_is_accepted(self) -> None:
        issues: list[str] = []

        GATE._verify_candidate_owned_local_elasticsearch_runtime(
            issues,
            startup_text="QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE",
            resolver_text="load_candidate_manifest(observabilityLogSink)",
            candidate_manifest_text="""packages/runtime-shared/observability-log-sink/
"composeRef"
"composeDigest"
""",
            stackctl_text="QWQ_OBSERVABILITY_LOG_SINK_COMPOSE_FILE",
        )

        self.assertEqual(issues, [])


class ProductOpsServicekitRuntimeLogWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main_source = GATE.PRODUCT_OPS_MAIN.read_text(encoding="utf-8")
        cls.product_bootstrap_source = GATE.PRODUCT_OPS_BOOTSTRAP.read_text(
            encoding="utf-8"
        )
        cls.servicekit_bootstrap_source = GATE.SERVICEKIT_BOOTSTRAP.read_text(
            encoding="utf-8"
        )
        cls.observability_source = GATE.SERVICEKIT_OBSERVABILITY.read_text(
            encoding="utf-8"
        )

    def verify(self, **overrides: str) -> list[str]:
        sources = {
            "main_text": self.main_source,
            "product_bootstrap_text": self.product_bootstrap_source,
            "servicekit_bootstrap_text": self.servicekit_bootstrap_source,
            "observability_text": self.observability_source,
        }
        sources.update(overrides)
        issues: list[str] = []
        GATE._verify_product_ops_servicekit_runtime_log_wiring(issues, **sources)
        return issues

    def test_current_product_ops_entrypoint_uses_shared_observability_stack(
        self,
    ) -> None:
        self.assertNotIn("NewRuntimeLogExportWriter", self.main_source)
        self.assertNotIn("NewProcessTraceLogger", self.main_source)

        self.assertEqual(self.verify(), [])

    def test_direct_manual_runtime_log_bootstrap_does_not_replace_servicekit_path(
        self,
    ) -> None:
        manual_main = """func main() {
    robs.NewRuntimeLogExportWriter()
    robs.NewProcessTraceLogger()
}
"""

        issues = self.verify(main_text=manual_main)

        self.assertEqual(len(issues), 1)
        self.assertIn("servicekit.RunStandalone/newModule", issues[0])

    def test_shared_stack_requires_each_runtime_log_constructor(self) -> None:
        for fragment in (
            "robs.NewRuntimeLogExportWriter",
            "robs.NewProcessTraceLogger",
        ):
            with self.subTest(fragment=fragment):
                issues = self.verify(
                    observability_text=self.observability_source.replace(
                        fragment,
                        "robs.RemovedRuntimeLogConstructor",
                    )
                )

                self.assertEqual(len(issues), 1)
                self.assertIn(fragment, issues[0])

    def test_servicekit_bootstrap_must_apply_observability_http_wrapper(self) -> None:
        issues = self.verify(
            servicekit_bootstrap_text=self.servicekit_bootstrap_source.replace(
                "observability.WrapHTTPHandler",
                "observability.BypassHTTPHandler",
            )
        )

        self.assertEqual(len(issues), 1)
        self.assertIn("route HTTP through", issues[0])

    def test_observability_wrapper_must_connect_process_logger(self) -> None:
        issues = self.verify(
            observability_text=self.observability_source.replace(
                "stack.ProcessLogger, stack.ExceptionLogger",
                "stack.ExceptionLogger",
            )
        )

        self.assertEqual(len(issues), 1)
        self.assertIn("WrapHTTPHandler", issues[0])


class RuntimeLogHTTPRouteOwnershipTest(unittest.TestCase):
    @staticmethod
    def _product_routes() -> str:
        return """eventrecordhttp.NewOperationsHandler(
    eventrecordhttp.OperationsDependencies{Telemetry: service.telemetry},
).Register(mux)
"""

    @staticmethod
    def _adapter() -> str:
        return """func (s *OperationsHandler) Register(mux *http.ServeMux) {
    register("GetRuntimeLogSummary", s.handleGetRuntimeLogSummary)
    register("GetRuntimeLogDrilldown", s.handleGetRuntimeLogDrilldown)
    register("ReportRuntimeLogBatch", s.handleReportRuntimeLogBatch)
}
func mustEventRecordOperationRoute(operationID string) (string, string) {
    canonicalID := "ops.event_record." + operationID
    for _, descriptor := range operationsecurity.ForDomain("ops") {
        return descriptor.Method, descriptor.PathTemplate
    }
    return "", ""
}
"""

    @staticmethod
    def _operations() -> dict[str, dict[str, object]]:
        return {
            GATE._rel(GATE.EVENT_RECORD_OPERATIONS): {
                "api_routes": [
                    {
                        "method": method,
                        "path": path,
                        "operation": operation,
                    }
                    for operation, (method, path) in (
                        GATE.RUNTIME_LOG_ROUTES.items()
                    )
                ]
            }
        }

    def test_current_tree_uses_typed_object_adapter_and_unique_contract_routes(
        self,
    ) -> None:
        issues: list[str] = []

        GATE._verify_runtime_log_http_registration(issues)

        self.assertEqual(issues, [])

    def test_composition_must_not_copy_runtime_log_path_literals(self) -> None:
        issues: list[str] = []

        GATE._verify_runtime_log_http_registration(
            issues,
            product_routes_text=(
                self._product_routes()
                + 'mux.HandleFunc("/ops/runtime-logs", handler)\n'
            ),
            adapter_text=self._adapter(),
            operation_documents=self._operations(),
        )

        self.assertEqual(len(issues), 1)
        self.assertIn("must not duplicate canonical runtime-log path", issues[0])

    def test_object_adapter_must_register_every_runtime_log_operation(self) -> None:
        issues: list[str] = []

        GATE._verify_runtime_log_http_registration(
            issues,
            product_routes_text=self._product_routes(),
            adapter_text=self._adapter().replace(
                '    register("GetRuntimeLogDrilldown", s.handleGetRuntimeLogDrilldown)\n',
                "",
            ),
            operation_documents=self._operations(),
        )

        self.assertEqual(len(issues), 1)
        self.assertIn("must register GetRuntimeLogDrilldown", issues[0])

    def test_object_adapter_must_not_copy_a_contract_path_literal(self) -> None:
        issues: list[str] = []

        GATE._verify_runtime_log_http_registration(
            issues,
            product_routes_text=self._product_routes(),
            adapter_text=(
                self._adapter()
                + 'const runtimeLogPath = "/ops/runtime-logs/summary"\n'
            ),
            operation_documents=self._operations(),
        )

        self.assertEqual(len(issues), 1)
        self.assertIn("must resolve /ops/runtime-logs/summary", issues[0])
        self.assertIn("generated operation descriptor", issues[0])

    def test_runtime_log_contract_path_cannot_have_a_second_owner(self) -> None:
        issues: list[str] = []
        operations = self._operations()
        operations["services/other/contracts/other/operations.yaml"] = {
            "api_routes": [
                {
                    "method": "POST",
                    "path": "/ops/runtime-logs",
                    "operation": "CopyRuntimeLogBatch",
                }
            ]
        }

        GATE._verify_runtime_log_http_registration(
            issues,
            product_routes_text=self._product_routes(),
            adapter_text=self._adapter(),
            operation_documents=operations,
        )

        self.assertEqual(len(issues), 1)
        self.assertIn("must have exactly one canonical owner", issues[0])
        self.assertIn("CopyRuntimeLogBatch", issues[0])


if __name__ == "__main__":
    unittest.main()
