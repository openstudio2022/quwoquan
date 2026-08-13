# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""provider conformance evidence schema 与 readiness 语义的本地契约。

Python 1000 行硬顶治理：active candidate、两设备 remote UAT、source
coverage、attestation 晋升场景已按场景拆到同目录
test_provider_conformance_evidence_<facet>__contract__local_contract_test.py
兄弟文件；本文件保留 schema fail-closed、required cell 集合、readiness
profile 与 evidence loader 语义。测试逐字搬移。
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from quwoquan_ops.ci.render_provider_conformance_source import render as render_source
from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance


ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = (
    ROOT
    / "quwoquan_ops"
    / "environments"
    / "provider_conformance_evidence.schema.json"
)


class ProviderConformanceEvidenceContractTest(unittest.TestCase):
    def test_schema_is_evidence_only_and_fail_closed(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["environment"]["enum"],
            ["alpha", "beta", "gamma", "prod"],
        )
        self.assertEqual(
            schema["properties"]["testLayer"]["enum"],
            ["local_contract", "api_integration", "user_acceptance"],
        )
        self.assertNotIn("version", schema["required"])
        self.assertNotIn("version", schema["properties"])
        for required in (
            "adapterId",
            "capabilityId",
            "artifactRef",
            "artifactDigest",
            "artifactAttestation",
            "nonPromotable",
            "sourceTreeState",
            "commitReview",
            "candidateStatus",
            "candidateReceiptRef",
            "candidateReceiptDigest",
            "attestationAuthority",
            "testArtifactRef",
            "testArtifactDigest",
            "testSource",
            "testSourceDigest",
            "testCommand",
            "testTarget",
            "typedPort",
            "contractRef",
            "commit",
            "imageDigest",
            "configDigest",
            "contractGraphDigest",
            "assertionCount",
            "assertionIds",
            "observabilityRefs",
        ):
            self.assertIn(required, schema["required"])

    def test_adapter_digest_covers_directory_paths_and_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            first = source_root / "adapter.go"
            first.write_text("package adapter\n", encoding="utf-8")
            initial = provider_conformance.implementation_digest(source_root)

            first.write_text("package adapter\nconst Version = 2\n", encoding="utf-8")
            content_changed = provider_conformance.implementation_digest(source_root)
            first.rename(source_root / "renamed_adapter.go")
            path_changed = provider_conformance.implementation_digest(source_root)

        self.assertIsNotNone(initial)
        self.assertNotEqual(initial, content_changed)
        self.assertNotEqual(content_changed, path_changed)

    def test_message_transport_p95_refs_bind_recording_rules(self) -> None:
        refs = provider_conformance.required_metric_refs(
            provider_conformance.MESSAGE_TRANSPORT_CAPABILITY_ID
        )
        self.assertIn("promql://qwq_message_transport_publish_p95", refs)
        self.assertIn("promql://qwq_message_transport_consume_p95", refs)
        self.assertNotIn(
            "provider-conformance://runtime.message.transport/metrics/publish_p95",
            refs,
        )

    def test_release_cell_set_is_compiled_and_rejects_legacy_duplicates(
        self,
    ) -> None:
        compiled = {
            "providerConformanceCapabilityIds": [
                f"provider.capability.{index:02d}" for index in range(2)
            ]
        }
        expected = provider_conformance.expected_required_cell_keys(compiled)
        self.assertEqual(len(expected), 20)
        extended = provider_conformance.expected_required_cell_keys(
            {
                "providerConformanceCapabilityIds": [
                    *compiled["providerConformanceCapabilityIds"],
                    "provider.capability.02",
                ]
            }
        )
        self.assertEqual(len(extended), 30)
        evidence = []
        for capability_id, environment, layer in sorted(expected):
            item = {
                field: "value"
                for field in provider_conformance.REQUIRED_FIELDS
            }
            item.update(
                {
                    "schema": "provider-conformance-evidence",
                    "capabilityId": capability_id,
                    "environment": environment,
                    "testLayer": layer,
                }
            )
            evidence.append(item)
        self.assertEqual(
            provider_conformance.exact_required_cell_issues(
                evidence,
                compiled=compiled,
            ),
            [],
        )
        missing = provider_conformance.exact_required_cell_issues(
            evidence[:-1],
            compiled=compiled,
        )
        self.assertTrue(any("compiled required cells" in issue for issue in missing))
        duplicate = provider_conformance.exact_required_cell_issues(
            [*evidence, evidence[0]],
            compiled=compiled,
        )
        self.assertTrue(any("duplicate" in issue for issue in duplicate))
        legacy = dict(evidence[0])
        legacy.pop("candidateReceiptDigest")
        legacy_issues = provider_conformance.exact_required_cell_issues(
            [legacy, *evidence[1:]],
            compiled=compiled,
        )
        self.assertTrue(any("legacy" in issue for issue in legacy_issues))

    def test_empty_evidence_cannot_satisfy_release_readiness(self) -> None:
        report = {
            "schema": "provider-conformance-readiness",
            "evidenceCount": 0,
            "readiness": {},
            "issues": [],
        }
        for environment in ("gamma", "prod"):
            issues = provider_conformance.readiness_issues(
                report, environment=environment
            )
            self.assertTrue(any("zero Provider Conformance evidence" in issue for issue in issues))

    def test_online_readiness_projection_rejects_historical_version_field(self) -> None:
        report = {
            "schema": "provider-conformance-readiness",
            "version": 1,
            "evidenceCount": 1,
            "executableSourceCount": 1,
            "sourceCoverageIssues": [],
            "readiness": {},
            "issues": [],
        }
        with self.assertRaisesRegex(ValueError, "fields are not canonical"):
            render_source(report, validation_issues=[], environment="prod")

    def test_only_prod_remote_receipts_require_release_readiness(self) -> None:
        self.assertEqual(
            provider_conformance.execution_profile_for("prod", "user_acceptance"),
            "release",
        )
        self.assertIsNone(
            provider_conformance.execution_profile_for("prod", "api_integration")
        )
        self.assertEqual(
            provider_conformance.execution_profile_for("gamma", "user_acceptance"),
            "release",
        )
        self.assertFalse(
            provider_conformance.requires_release_readiness(
                "gamma",
                "user_acceptance",
            )
        )
        self.assertTrue(
            provider_conformance.requires_release_readiness(
                "prod",
                "user_acceptance",
            )
        )
        self.assertFalse(
            provider_conformance.requires_release_readiness(
                "beta",
                "user_acceptance",
            )
        )

    def test_release_assertions_do_not_change_nine_cell_base_semantics(self) -> None:
        base = {
            "assertionIds": sorted(provider_conformance.PUBLIC_ASSERTION_IDS),
        }
        release = {
            "assertionIds": sorted(
                provider_conformance.PUBLIC_ASSERTION_IDS
                | provider_conformance.RELEASE_ASSERTION_IDS
            ),
        }
        self.assertEqual(
            provider_conformance._assertion_semantics(base),
            provider_conformance._assertion_semantics(release),
        )

    def test_missing_fields_are_rejected_before_readiness(self) -> None:
        compiled, compile_issues = governance.load_and_compile()
        self.assertEqual(compile_issues, [])
        issues = provider_conformance.validate_evidence(
            [{"schema": "provider-conformance-evidence"}],
            registry=governance.load_registry(),
            compiled=compiled,
        )
        self.assertTrue(any("missing required fields" in issue for issue in issues))

    def test_evidence_loader_reads_only_disposable_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / ".qwq_output"
            evidence, issues = provider_conformance.load_evidence(output_root)
        self.assertEqual(evidence, [])
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
