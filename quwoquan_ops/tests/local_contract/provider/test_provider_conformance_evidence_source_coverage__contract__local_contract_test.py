# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""三层测试源覆盖的本地契约。

由 test_provider_conformance_evidence__contract__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：source coverage 缺口必须保留进
release readiness、本地覆盖与 prod harness 隔离、静态 GATE_BLOCK 断言
与运行时 executor 委派一律拒绝。测试逐字搬移。
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance


class ProviderConformanceEvidenceContractTest(unittest.TestCase):
    def test_source_coverage_gaps_are_preserved_in_release_readiness(self) -> None:
        compiled, compile_issues = governance.load_and_compile()
        self.assertEqual(compile_issues, [])
        sources, discovery_issues = provider_conformance.discover_test_sources()
        self.assertEqual(discovery_issues, [])
        coverage = provider_conformance.source_coverage_issues(
            compiled=compiled,
            sources=sources,
        )
        self.assertEqual(
            coverage,
            [],
            "all compiled required Provider capabilities must have three-layer sources; "
            "first-party HTTP authority bindings are outside Provider Conformance",
        )
        with tempfile.TemporaryDirectory() as temporary:
            report, issues = provider_conformance.load_validate_and_derive(
                root=Path(temporary),
            )
        self.assertEqual(issues, [])
        self.assertEqual(report["sourceCoverageIssues"], coverage)
        readiness = provider_conformance.readiness_issues(
            report,
            environment="gamma",
        )
        for issue in coverage:
            self.assertIn(issue, readiness)

    def test_local_source_coverage_isolated_from_prod_harnesses(self) -> None:
        compiled, compile_issues = governance.load_and_compile()
        self.assertEqual(compile_issues, [])
        sources, discovery_issues = provider_conformance.discover_test_sources()
        self.assertEqual(discovery_issues, [])
        prod_only_key = next(
            (
                capability_id,
                prod_binding["adapter_id"],
                "user_acceptance",
            )
            for capability_id, prod_binding in compiled["selectedBindings"][
                "prod"
            ].items()
            if governance.requires_provider_conformance(prod_binding)
            and prod_binding["adapter_id"]
            != compiled["selectedBindings"]["alpha"][capability_id]["adapter_id"]
        )
        without_prod = dict(sources)
        without_prod.pop(prod_only_key)

        self.assertTrue(
            any(
                prod_only_key[0] in issue
                for issue in provider_conformance.source_coverage_issues(
                    compiled=compiled,
                    sources=without_prod,
                )
            )
        )
        self.assertEqual(
            provider_conformance.local_source_coverage_issues(
                compiled=compiled,
                environment="alpha",
                sources=without_prod,
            ),
            [],
        )

        alpha_binding = compiled["selectedBindings"]["alpha"][prod_only_key[0]]
        without_alpha = dict(sources)
        without_alpha.pop(
            (prod_only_key[0], alpha_binding["adapter_id"], "api_integration")
        )
        alpha_issues = provider_conformance.local_source_coverage_issues(
            compiled=compiled,
            environment="alpha",
            sources=without_alpha,
        )
        self.assertTrue(
            any("api_integration" in issue for issue in alpha_issues),
            alpha_issues,
        )

    def test_release_readiness_reports_missing_executable_source_coverage(self) -> None:
        compiled, compile_issues = governance.load_and_compile()
        self.assertEqual(compile_issues, [])

        issues = provider_conformance.source_coverage_issues(
            compiled=compiled,
            sources={},
        )

        capability_ids = set(compiled["providerConformanceCapabilityIds"])
        self.assertEqual(len(issues), len(capability_ids))
        for capability_id in capability_ids:
            self.assertTrue(
                any(issue.startswith(f"source_coverage.{capability_id}:") for issue in issues),
                capability_id,
            )
        for capability_id in {
            "chat.conversation.membership.read",
            "circle.membership.self.read",
            "integration.connector_grant.read",
        }:
            self.assertFalse(
                any(issue.startswith(f"source_coverage.{capability_id}:") for issue in issues),
                capability_id,
            )
        self.assertTrue(
            any(
                "infra.livekit_sfu/user_acceptance" in issue
                for issue in issues
            ),
            "prod Remote RTC evidence source is mandatory",
        )

    def test_remote_source_rejects_static_gate_block_assertion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "quwoquan_ops" / "tests" / "acceptance" / "api_integration"
            source_root.mkdir(parents=True)
            source = source_root / "remote_provider_test.py"
            source.write_text(
                "\n".join(
                    (
                        "# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003",
                        '# provider_conformance: {"adapterId":"ext.llm.protocol_fixture","capabilityId":"assistant.model.generation","testLayer":"api_integration","typedPort":"ModelCompletionPort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_session/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.model_generation"],"command":["python3","remote_provider_test.py"],"target":"real-provider","networkBoundary":"remote_protocol"}',
                        "result_path = 'QWQ_PROVIDER_CONFORMANCE_RESULT_PATH'",
                        "assert False, 'GATE_BLOCK'",
                    )
                ),
                encoding="utf-8",
            )
            roots = {
                **provider_conformance.TEST_LAYER_ROOTS,
                "api_integration": source_root,
            }
            with (
                mock.patch.object(provider_conformance, "ROOT", root),
                mock.patch.object(provider_conformance, "TEST_LAYER_ROOTS", roots),
                self.assertRaisesRegex(ValueError, "static should-block/GATE_BLOCK"),
            ):
                provider_conformance.load_test_source(source)

    def test_source_rejects_runtime_selected_executor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "quwoquan_ops" / "tests" / "local_contract"
            source_root.mkdir(parents=True)
            source = source_root / "delegated_provider_conformance.py"
            source.write_text(
                "\n".join(
                    (
                        "# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003",
                        '# provider_conformance: {"adapterId":"ext.llm.protocol_fixture","capabilityId":"assistant.model.generation","testLayer":"local_contract","typedPort":"ModelCompletionPort","contractRef":"quwoquan_service/services/assistant-service/contracts/assistant/assistant_session/operations.yaml","assertionIds":["provider.success","provider.validation","provider.auth","provider.network_dns","provider.timeout","provider.throttle","provider.retry","provider.idempotency","provider.callback_ordering","provider.redaction","provider.observability","provider.model_generation"],"command":["python3","delegated_provider_conformance.py"],"target":"delegated-provider","networkBoundary":"offline_harness"}',
                        "import os",
                        "result_path = os.environ['QWQ_PROVIDER_CONFORMANCE_RESULT_PATH']",
                        "command = os.environ['QWQ_PROVIDER_CONFORMANCE_EXECUTOR_COMMAND_JSON']",
                    )
                ),
                encoding="utf-8",
            )
            roots = {
                **provider_conformance.TEST_LAYER_ROOTS,
                "local_contract": source_root,
            }
            with (
                mock.patch.object(provider_conformance, "ROOT", root),
                mock.patch.object(provider_conformance, "TEST_LAYER_ROOTS", roots),
                self.assertRaisesRegex(
                    ValueError,
                    "runtime-selected executor",
                ),
            ):
                provider_conformance.load_test_source(source)


if __name__ == "__main__":
    unittest.main()
