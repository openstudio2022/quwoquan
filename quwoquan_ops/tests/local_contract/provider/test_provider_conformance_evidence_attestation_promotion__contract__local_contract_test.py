# spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003
"""attestation 与晋升身份的本地契约。

由 test_provider_conformance_evidence__contract__local_contract_test.py
（Python 1000 行硬顶治理）按场景拆出：attestation 绑定执行报告字节、
CI authority 缺失不得静默接受、脏工作树/本地 key 不可晋升、reviewed
clean CI 身份可晋升、attestation key 不来自仓库配置。测试逐字搬移。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from quwoquan_ops.cli.lib import external_provider_governance as governance
from quwoquan_ops.cli.lib import provider_conformance


class ProviderConformanceEvidenceContractTest(unittest.TestCase):
    def test_attestation_is_bound_to_execution_report_bytes(self) -> None:
        raw = b'{"case_results":[],"exit_code":0}'
        signature = provider_conformance.sign_execution_report(
            raw, key="local-contract-attestation-key"
        )
        self.assertRegex(signature, r"^hmac-sha256:[a-f0-9]{64}$")
        self.assertNotEqual(
            signature,
            provider_conformance.sign_execution_report(
                raw + b" ", key="local-contract-attestation-key"
            ),
        )

    def test_ci_attestation_cannot_be_silently_accepted_without_authority(self) -> None:
        report = {
            field: "value"
            for field in provider_conformance.EXECUTION_REPORT_REQUIRED_FIELDS
        }
        report.update(
            {
                "schema": provider_conformance.EXECUTION_REPORT_SCHEMA,
                "exitCode": 0,
                "testSource": None,
                "testCommand": "python3 provider-test.py",
                "commit": "a" * 40,
                "attestationAuthority": "ci",
                "nonPromotable": False,
                "sourceTreeState": "clean",
                "commitReview": "reviewed",
                "candidateStatus": "active_immutable",
                "candidateReceiptRef": ".qwq_output/env/prod/runs/readback.json",
                "candidateReceiptDigest": "sha256:" + "1" * 64,
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            raw = json.dumps(report, sort_keys=True).encode("utf-8")
            path.write_bytes(raw)
            evidence = {
                **report,
                "artifactDigest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "artifactAttestation": "hmac-sha256:" + "2" * 64,
            }
            with mock.patch.dict(os.environ, {}, clear=True):
                issues = provider_conformance._validate_execution_report(
                    artifact_path=path,
                    evidence=evidence,
                    expected_source=None,
                )
        self.assertTrue(
            any("CI attestation authority is unavailable" in issue for issue in issues)
        )

    def test_dirty_worktree_and_local_key_cannot_be_promoted(self) -> None:
        commit = "a" * 40
        with (
            mock.patch.dict(
                os.environ,
                {"QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "developer-key"},
                clear=True,
            ),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="dirty",
            ),
        ):
            identity = provider_conformance.evidence_identity(
                commit=commit,
                candidate_receipt_bound=True,
                candidate_receipt_ref=".qwq_output/env/alpha/runs/startup.json",
                candidate_receipt_digest="sha256:" + "9" * 64,
            )
            attestation = provider_conformance.attest_execution_report(
                b"local execution report",
                identity=identity,
            )

        self.assertEqual(
            identity,
            {
                "nonPromotable": True,
                "sourceTreeState": "dirty",
                "commitReview": "unreviewed",
                "candidateStatus": "active_immutable",
                "candidateReceiptRef": ".qwq_output/env/alpha/runs/startup.json",
                "candidateReceiptDigest": "sha256:" + "9" * 64,
                "attestationAuthority": "local",
            },
        )
        self.assertRegex(attestation, r"^local-sha256:[a-f0-9]{64}$")
        self.assertFalse(
            provider_conformance.evidence_is_promotable(
                {**identity, "commit": commit},
                require_runtime_authority=False,
            )
        )
        non_promotable_cell = {
            **identity,
            "status": "passed",
            "commit": commit,
            "imageDigest": "sha256:" + "1" * 64,
            "contractGraphDigest": "sha256:" + "2" * 64,
            "adapterDigest": "sha256:" + "3" * 64,
            "configDigest": "sha256:" + "4" * 64,
            "assertionIds": sorted(provider_conformance.PUBLIC_ASSERTION_IDS),
            "typedPort": "ExamplePort",
            "contractRef": "example/operations.yaml",
            "environment": "alpha",
        }
        with mock.patch.object(
            provider_conformance,
            "ci_attestation_authority_available",
            return_value=True,
        ):
            self.assertFalse(
                provider_conformance._cells_share_release(
                    [non_promotable_cell],
                    expected_environments=["alpha"],
                    require_adapter_digest=True,
                )
            )
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="dirty",
            ),
        ):
            no_key_identity = provider_conformance.evidence_identity(
                commit=commit,
                candidate_receipt_bound=False,
            )
            self.assertRegex(
                provider_conformance.attest_execution_report(
                    b"no CI key local report",
                    identity=no_key_identity,
                ),
                r"^local-sha256:[a-f0-9]{64}$",
            )

        forged_local_key_identity = {
            "nonPromotable": False,
            "sourceTreeState": "clean",
            "commitReview": "reviewed",
            "candidateStatus": "active_immutable",
            "candidateReceiptRef": "",
            "candidateReceiptDigest": "",
            "attestationAuthority": "ci",
            "commit": commit,
        }
        with (
            mock.patch.dict(
                os.environ,
                {"QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "developer-key"},
                clear=True,
            ),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="clean",
            ),
        ):
            self.assertFalse(
                provider_conformance.evidence_is_promotable(
                    forged_local_key_identity,
                )
            )
        with (
            mock.patch.dict(
                os.environ,
                {
                    "GITHUB_ACTIONS": "true",
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_AUTHORITY": "ci",
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "forged-local-key",
                    "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT": commit,
                },
                clear=True,
            ),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="clean",
            ),
        ):
            spoofed_context = provider_conformance.evidence_identity(
                commit=commit,
                candidate_receipt_bound=False,
            )
            self.assertTrue(spoofed_context["nonPromotable"])
            self.assertEqual(spoofed_context["candidateStatus"], "unverified")
            self.assertFalse(
                provider_conformance.evidence_is_promotable(
                    {**spoofed_context, "commit": commit},
                )
            )

    def test_local_candidate_readiness_accepts_nonpromotable_checksum_only(self) -> None:
        compiled, compile_issues = governance.load_and_compile()
        self.assertEqual(compile_issues, [])
        capability_ids = provider_conformance.provider_conformance_capability_ids(
            compiled
        )
        candidate_receipt_ref = (
            ".qwq_output/env/alpha/local/alpha-local/process/startup_attempt.json"
        )
        evidence: list[dict[str, object]] = []
        selected = compiled["selectedBindings"]["alpha"]
        for capability_index, capability_id in enumerate(sorted(capability_ids)):
            adapter_id = selected[capability_id]["adapter_id"]
            for layer in provider_conformance.LAYERS:
                evidence.append(
                    {
                        "status": "passed",
                        "capabilityId": capability_id,
                        "adapterId": adapter_id,
                        "environment": "alpha",
                        "testLayer": layer,
                        "candidateStatus": "active_immutable",
                        "candidateReceiptRef": candidate_receipt_ref,
                        "candidateReceiptDigest": "sha256:" + "9" * 64,
                        "commit": "a" * 40,
                        "imageDigest": "sha256:" + "1" * 64,
                        "contractGraphDigest": "sha256:" + "2" * 64,
                        "adapterDigest": "sha256:"
                        + f"{capability_index + 1:064x}",
                        "configDigest": "sha256:"
                        + f"{capability_index + 101:064x}",
                        "assertionIds": sorted(
                            provider_conformance.PUBLIC_ASSERTION_IDS
                        ),
                        "typedPort": f"Capability{capability_index}Port",
                        "contractRef": f"contracts/{capability_id}.yaml",
                        "attestationAuthority": "local",
                        "artifactAttestation": "local-sha256:" + "3" * 64,
                        "nonPromotable": True,
                        "sourceTreeState": "dirty",
                        "commitReview": "unreviewed",
                    }
                )

        with (
            mock.patch.object(
                provider_conformance,
                "_binding_preflight_ready",
                return_value=True,
            ),
            mock.patch.object(
                provider_conformance,
                "ci_attestation_authority_available",
                return_value=False,
            ),
        ):
            issues = provider_conformance.local_functional_readiness_issues(
                compiled=compiled,
                evidence=evidence,
                environment="alpha",
            )

        self.assertEqual(issues, [])
        first_capability_cells = [
            item
            for item in evidence
            if item["capabilityId"] == min(capability_ids)
        ]
        self.assertFalse(
            provider_conformance._cells_share_release(
                first_capability_cells,
                expected_environments=["alpha"],
                require_adapter_digest=True,
            ),
            "local functional evidence must never become release evidence",
        )
        evidence[0]["nonPromotable"] = False
        with mock.patch.object(
            provider_conformance,
            "_binding_preflight_ready",
            return_value=True,
        ):
            blocked = provider_conformance.local_functional_readiness_issues(
                compiled=compiled,
                evidence=evidence,
                environment="alpha",
            )
        self.assertTrue(
            any("three-layer local closure" in issue for issue in blocked),
            blocked,
        )

    def test_reviewed_clean_ci_identity_is_promotable(self) -> None:
        commit = "b" * 40
        with (
            mock.patch.dict(
                os.environ,
                {
                    "GITHUB_ACTIONS": "true",
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_AUTHORITY": "ci",
                    "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY": "ci-owned-key",
                    "QWQ_PROVIDER_CONFORMANCE_REVIEWED_COMMIT": commit,
                },
                clear=True,
            ),
            mock.patch.object(
                provider_conformance,
                "current_source_tree_state",
                return_value="clean",
            ),
        ):
            identity = provider_conformance.evidence_identity(
                commit=commit,
                candidate_receipt_bound=True,
                candidate_receipt_ref=".qwq_output/env/alpha/runs/startup.json",
                candidate_receipt_digest="sha256:" + "9" * 64,
            )
            self.assertFalse(identity["nonPromotable"])
            self.assertEqual(identity["attestationAuthority"], "ci")
            self.assertTrue(
                provider_conformance.evidence_is_promotable(
                    {**identity, "commit": commit},
                )
            )
            promotable_cell = {
                **identity,
                "status": "passed",
                "commit": commit,
                "imageDigest": "sha256:" + "1" * 64,
                "contractGraphDigest": "sha256:" + "2" * 64,
                "adapterDigest": "sha256:" + "3" * 64,
                "configDigest": "sha256:" + "4" * 64,
                "assertionIds": sorted(provider_conformance.PUBLIC_ASSERTION_IDS),
                "typedPort": "ExamplePort",
                "contractRef": "example/operations.yaml",
                "environment": "alpha",
            }
            self.assertTrue(
                provider_conformance._cells_share_release(
                    [promotable_cell],
                    expected_environments=["alpha"],
                    require_adapter_digest=True,
                )
            )

    def test_attestation_key_is_not_defined_by_repository_config(self) -> None:
        self.assertNotIn(
            "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY",
            governance.load_bindings(),
        )
        value = os.environ.get("QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY")
        if value is not None:
            self.assertTrue(value)


if __name__ == "__main__":
    unittest.main()
