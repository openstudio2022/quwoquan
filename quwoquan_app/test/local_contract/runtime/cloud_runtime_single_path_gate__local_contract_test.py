#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-005
"""Cloud single-path governance must derive owners from canonical App paths."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = (
    REPO_ROOT
    / "quwoquan_app/scripts/runtime/cloud/verify_cloud_runtime_single_path.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_cloud_runtime_single_path_under_test",
        VERIFIER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CloudRuntimeSinglePathGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.app_root = Path(self.temp_directory.name) / "quwoquan_app"

    def write(self, relative_path: str, source: str) -> Path:
        path = self.app_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    @staticmethod
    def owner_source(method: str) -> str:
        return f"""
final class CanonicalOwner {{
  const CanonicalOwner(this.client);
  final contracts.GeneratedCloudOperationClient client;
  void invoke() => this.client.{method}();
}}
"""

    @staticmethod
    def upgrade_owner_source(identifier: str) -> str:
        return f"""
final operation = appCloudOperationContracts[
  AppCloudOperationIds.{identifier}
]!;
final path = operation.pathTemplate;
final isUpgrade = operation.responseBodyKind == 'upgrade';
"""

    @staticmethod
    def upgrade_executor_source() -> str:
        return """
final class WebSocketTransport {
  Object connect(Uri endpoint) => WebSocketChannel.connect(endpoint);
}
"""

    def test_canonical_object_adapter_is_the_method_owner(self) -> None:
        owner = self.write(
            "lib/service/foo_service/bar/baz/adapters/foo_remote.dart",
            self.owner_source("fooRead"),
        )

        report = self.verifier._analyze_method_owners(
            self.app_root,
            {"fooRead"},
        )

        self.assertEqual(report.canonical_owners["fooRead"], (owner,))
        self.assertEqual(report.missing, frozenset())
        self.assertEqual(report.legacy_only, frozenset())

    def test_legacy_only_reference_does_not_satisfy_owner_coverage(self) -> None:
        legacy = self.write(
            "lib/cloud/remote/foo/foo_remote.dart",
            self.owner_source("fooRead"),
        )

        report = self.verifier._analyze_method_owners(
            self.app_root,
            {"fooRead"},
        )

        self.assertNotIn("fooRead", report.canonical_owners)
        self.assertEqual(report.legacy_only, frozenset({"fooRead"}))
        self.assertEqual(report.legacy_references["fooRead"], (legacy,))

    def test_method_with_no_reference_is_reported_missing(self) -> None:
        report = self.verifier._analyze_method_owners(
            self.app_root,
            {"fooRead"},
        )

        self.assertEqual(report.missing, frozenset({"fooRead"}))
        self.assertEqual(report.legacy_only, frozenset())

    def test_duplicate_canonical_owners_are_reported_with_both_paths(self) -> None:
        first = self.write(
            "lib/service/foo_service/bar/first/adapters/first_remote.dart",
            self.owner_source("fooRead"),
        )
        second = self.write(
            "lib/service/foo_service/bar/second/adapters/second_remote.dart",
            self.owner_source("fooRead"),
        )

        report = self.verifier._analyze_method_owners(
            self.app_root,
            {"fooRead"},
        )

        self.assertEqual(report.duplicates["fooRead"], (first, second))

    def test_non_adapter_and_di_calls_do_not_become_business_owners(self) -> None:
        self.write(
            "lib/service/foo_service/bar/baz/application/not_an_owner.dart",
            self.owner_source("fooRead"),
        )
        self.write(
            "lib/runtime/di/foo_dependencies.dart",
            self.owner_source("fooRead"),
        )

        report = self.verifier._analyze_method_owners(
            self.app_root,
            {"fooRead"},
        )

        self.assertEqual(report.canonical_owners, {})
        self.assertEqual(report.missing, frozenset({"fooRead"}))

    def test_upgrade_uses_canonical_descriptor_owner_and_websocket_executor(
        self,
    ) -> None:
        identifier = "realtimeConnectionWebSocketUpgrade"
        owner = self.write(
            "lib/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart",
            self.upgrade_owner_source(identifier),
        )
        executor = self.write(
            "lib/service/realtime_gateway/realtime/connection/adapters/websocket_transport.dart",
            self.upgrade_executor_source(),
        )

        report = self.verifier._analyze_upgrade_owners(
            self.app_root,
            {identifier},
        )
        failures: list[str] = []
        self.verifier._check_upgrade_owners(report, failures)

        self.assertEqual(report.canonical_owners[identifier], (owner,))
        self.assertEqual(report.executors[identifier], (executor,))
        self.assertEqual(report.missing, frozenset())
        self.assertEqual(report.missing_executors, frozenset())
        self.assertEqual(failures, [])

    def test_dummy_generated_client_call_does_not_own_upgrade(self) -> None:
        identifier = "realtimeConnectionWebSocketUpgrade"
        self.write(
            "lib/service/realtime_gateway/realtime/connection/adapters/dummy_remote.dart",
            self.owner_source(identifier),
        )

        upgrade_report = self.verifier._analyze_upgrade_owners(
            self.app_root,
            {identifier},
        )
        method_report = self.verifier._analyze_method_owners(
            self.app_root,
            set(),
        )

        self.assertEqual(upgrade_report.missing, frozenset({identifier}))
        self.assertEqual(method_report.non_ready, frozenset({identifier}))

    def test_upgrade_without_protocol_executor_is_reported(self) -> None:
        identifier = "realtimeConnectionWebSocketUpgrade"
        self.write(
            "lib/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart",
            self.upgrade_owner_source(identifier),
        )
        report = self.verifier._analyze_upgrade_owners(
            self.app_root,
            {identifier},
        )
        failures: list[str] = []

        self.verifier._check_upgrade_owners(report, failures)

        self.assertEqual(report.missing_executors, frozenset({identifier}))
        self.assertTrue(
            any("protocol-specific WebSocket executor" in item for item in failures)
        )

    def test_typed_upgrade_descriptor_reference_is_a_canonical_owner(self) -> None:
        identifier = "realtimeConnectionWebSocketUpgrade"
        owner = self.write(
            "lib/service/realtime_gateway/realtime/connection/adapters/realtime_config.dart",
            f"""
final descriptor = AppCloudOperationUpgradeDescriptors.{identifier};
""",
        )
        self.write(
            "lib/service/realtime_gateway/realtime/connection/adapters/websocket_transport.dart",
            self.upgrade_executor_source(),
        )

        report = self.verifier._analyze_upgrade_owners(
            self.app_root,
            {identifier},
        )
        failures: list[str] = []
        self.verifier._check_upgrade_owners(report, failures)

        self.assertEqual(report.canonical_owners[identifier], (owner,))
        self.assertEqual(failures, [])

    def test_generated_surface_separates_json_methods_and_upgrades(self) -> None:
        methods, upgrades, domains = self.verifier._parse_generated_surface(
            """
final class GeneratedCloudOperationClient {
  Future<void> fooRead() => throw UnimplementedError();
}
const appCloudOperationContracts = <String, CloudOperationContract>{
  "realtime.connection.WebSocketUpgrade": CloudOperationContract(
    domain: "realtime",
    responseBodyKind: "upgrade",
  ),
};
abstract final class AppCloudOperationUpgradeDescriptors {
  static final CloudOperationUpgradeDescriptor<FooRequest>
      realtimeConnectionWebSocketUpgrade = descriptor;
}
"""
        )

        self.assertEqual(methods, frozenset({"fooRead"}))
        self.assertEqual(
            upgrades,
            frozenset({"realtimeConnectionWebSocketUpgrade"}),
        )
        self.assertEqual(domains, frozenset({"realtime"}))

    def test_generated_method_metadata_accepts_dart_formatter_wrapping(self) -> None:
        metadata = self.verifier._parse_generated_method_metadata(
            """
abstract final class AppCloudOperationIds {
  static const String
  circleGatheringPlanCommitGatheringPlanProposal =
      "circle.circle_management.gathering_plan.CommitGatheringPlanProposal";
}
const appCloudOperationContracts = <String, CloudOperationContract>{
  "circle.circle_management.gathering_plan.CommitGatheringPlanProposal":
      CloudOperationContract(
        canonicalOperationId:
            "circle.circle_management.gathering_plan.CommitGatheringPlanProposal",
        domain: "circle",
        transport: "json",
      ),
};
""",
            {"circleGatheringPlanCommitGatheringPlanProposal"},
        )

        self.assertEqual(
            metadata["circleGatheringPlanCommitGatheringPlanProposal"],
            self.verifier.GeneratedMethodMetadata(
                "circle.circle_management.gathering_plan.CommitGatheringPlanProposal",
                "circle",
                "json",
            ),
        )

    def test_wrapped_commercial_blocker_only_exempts_blocked_method(self) -> None:
        blocked_method = "circleGatheringPlanCommitGatheringPlanProposal"
        ready_method = "circleGatheringPlanCreateGatheringPlan"
        generated_source = """
abstract final class AppCloudOperationIds {
  static const String
  circleGatheringPlanCommitGatheringPlanProposal =
      "circle.circle_management.gathering_plan.CommitGatheringPlanProposal";
  static const String
  circleGatheringPlanCreateGatheringPlan =
      "circle.circle_management.gathering_plan.CreateGatheringPlan";
}
const appCloudOperationContracts = <String, CloudOperationContract>{
  "circle.circle_management.gathering_plan.CommitGatheringPlanProposal":
      CloudOperationContract(
        canonicalOperationId:
            "circle.circle_management.gathering_plan.CommitGatheringPlanProposal",
        commercialStatus:
            "blocked",
      ),
  "circle.circle_management.gathering_plan.CreateGatheringPlan":
      CloudOperationContract(
        canonicalOperationId:
            "circle.circle_management.gathering_plan.CreateGatheringPlan",
        commercialStatus:
            "ready",
      ),
};
"""

        blocked_methods = self.verifier._commercially_blocked_methods(
            generated_source
        )
        report = self.verifier._analyze_method_owners(
            self.app_root,
            {blocked_method, ready_method},
            blocked_methods,
        )

        self.assertEqual(blocked_methods, frozenset({blocked_method}))
        self.assertEqual(report.missing, frozenset({ready_method}))

    def test_graphql_method_uses_specialized_client_and_canonical_owner(
        self,
    ) -> None:
        canonical_id = "gateway.persisted_query_execution.SearchPage"
        self.write(
            "lib/runtime/transport/graphql_read/generated/search_page.g.dart",
            f"""
const canonicalOperationId = '{canonical_id}';
final class GeneratedSearchPageGraphQLClient {{}}
""",
        )
        self.write(
            "lib/service/api_edge/graphql_read/persisted_query_execution/adapters/search_remote.dart",
            "final GeneratedSearchPageGraphQLClient client;\n",
        )
        failures: list[str] = []

        owned = self.verifier._check_graphql_method_owners(
            self.app_root,
            {
                "gatewayPersistedQueryExecutionSearchPage": self.verifier.GeneratedMethodMetadata(
                    canonical_id,
                    "gateway",
                    "graphql",
                )
            },
            failures,
        )

        self.assertEqual(owned, 1)
        self.assertEqual(failures, [])

    def test_legacy_path_blocks_even_without_generated_method_call(self) -> None:
        legacy = self.write(
            "lib/cloud/services/foo/foo_models.dart",
            "final class FooModels {}\n",
        )
        report = self.verifier._analyze_method_owners(self.app_root, set())
        failures: list[str] = []

        self.verifier._check_adapter_owners(report, failures)

        self.assertTrue(
            any(str(legacy) in failure for failure in failures),
            failures,
        )

    def test_composition_is_required_for_each_generated_domain(self) -> None:
        failures: list[str] = []
        expected, present = self.verifier._check_domain_compositions(
            self.app_root,
            {"foo"},
            failures,
        )
        self.assertEqual((expected, present), (1, 0))
        self.assertTrue(any("foo_dependencies.dart" in item for item in failures))

        self.write(
            "lib/runtime/di/foo_dependencies.dart",
            """
final class FooProductionComposition {
  static Object build(GeneratedCloudOperationClient client) => Object();
}
""",
        )
        failures = []
        expected, present = self.verifier._check_domain_compositions(
            self.app_root,
            {"foo"},
            failures,
        )
        self.assertEqual((expected, present), (1, 1))
        self.assertEqual(failures, [])

    def test_central_provider_remote_construction_is_reported(self) -> None:
        provider = self.write(
            "lib/runtime/di/app_providers_example.dart",
            """
// RemoteIgnored()
const ignored = 'RemoteAlsoIgnored()';
final value = RemoteFooAdapter();
""",
        )

        observed = self.verifier._collect_provider_remote_constructions(
            self.app_root
        )

        self.assertEqual(observed[provider], (("RemoteFooAdapter", 4),))


if __name__ == "__main__":
    unittest.main()
