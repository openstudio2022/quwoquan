from __future__ import annotations

import unittest
from unittest.mock import patch

from quwoquan_ops.ci.render_provider_conformance_source import render as render_source
from quwoquan_ops.ci.render_provider_release_evidence import render


class ProviderReleaseEvidenceTest(unittest.TestCase):
    def _source_evidence(self, evidence_count: int) -> dict:
        return {
            "ref": "oci://ghcr.io/owner/repo/provider-evidence@sha256:" + "e" * 64,
            "digest": "sha256:" + "e" * 64,
            "files": {
                f"evidence/raw/provider/env/prod/runs/run-{index}/provider-conformance.evidence.json": (
                    "sha256:" + f"{index + 1:064x}"
                )
                for index in range(evidence_count)
            },
        }

    def _capability(self, *, required: bool, ready: bool, prod: bool) -> dict:
        payload = {
            "state": "enabled",
            "required": required,
            "adapter_id": "ext.provider.canonical",
            "local_substitute": not prod,
            "adapter_preflight_ready": ready,
            "adapter_ready": ready,
            "evidence_ready": ready,
            "matrix_selected_adapters_ready": ready,
            "capability_ready": ready,
        }
        if prod:
            payload["prod_remote_release_ready"] = ready
        return payload

    def _readiness(self, prod: dict[str, dict]) -> dict[str, dict]:
        return {
            environment: {
                "fixture.capability": self._capability(
                    required=True,
                    ready=True,
                    prod=False,
                )
            }
            for environment in ("alpha", "beta", "gamma")
        } | {"prod": prod}

    def _manifest(self) -> dict:
        return {
            "candidateId": None,
            "source": {
                "gitSha": "a" * 40,
                "treeDigest": "sha1:" + "b" * 40,
                "repository": "owner/repo",
                "workflowRunId": "123",
            },
            "images": {
                "service": {"digest": "sha256:" + "c" * 64},
            },
        }

    def test_optional_unready_capability_does_not_block_required_ready(self) -> None:
        conformance = {
            "schema": "provider-conformance-source",
            "evidenceCount": 2,
            "sourceEvidence": self._source_evidence(2),
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": self._readiness(
                {
                    "required.capability": {
                        **self._capability(required=True, ready=True, prod=True),
                    },
                    "optional.capability": {
                        **self._capability(required=False, ready=False, prod=True),
                    },
                }
            ),
        }
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ):
            payload = render(
                manifest=self._manifest(),
                contract_graph_digest="sha256:" + "d" * 64,
                conformance=conformance,
                generated_at="2026-07-28T00:00:00Z",
            )
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["evidenceCount"], 2)

    def test_required_unready_capability_blocks(self) -> None:
        conformance = {
            "schema": "provider-conformance-source",
            "evidenceCount": 1,
            "sourceEvidence": self._source_evidence(1),
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": self._readiness(
                {
                    "required.capability": {
                        **self._capability(required=True, ready=False, prod=True),
                    }
                }
            ),
        }
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ), self.assertRaisesRegex(ValueError, "not ready"):
            render(
                manifest=self._manifest(),
                contract_graph_digest="sha256:" + "d" * 64,
                conformance=conformance,
                generated_at="2026-07-28T00:00:00Z",
            )

    def test_old_or_versioned_provider_source_is_rejected(self) -> None:
        conformance = {
            "schema": "provider-conformance-readiness",
            "version": 1,
            "evidenceCount": 1,
            "issues": [],
            "sourceCoverageIssues": [],
            "readiness": {"prod": {}},
        }
        with patch(
            "quwoquan_ops.ci.render_provider_release_evidence.validate_manifest"
        ), self.assertRaisesRegex(ValueError, "fields are not canonical"):
            render(
                manifest=self._manifest(),
                contract_graph_digest="sha256:" + "d" * 64,
                conformance=conformance,
                generated_at="2026-07-28T00:00:00Z",
            )

    def test_source_projection_drops_repository_report_identity(self) -> None:
        report = {
            "schema": "provider-conformance-readiness",
            "evidenceCount": 1,
            "executableSourceCount": 4,
            "sourceCoverageIssues": [],
            "readiness": self._readiness(
                {
                    "required.capability": self._capability(
                        required=True,
                        ready=True,
                        prod=True,
                    )
                }
            ),
            "issues": [],
        }
        with patch(
            "quwoquan_ops.ci.render_provider_conformance_source.readiness_issues",
            return_value=[],
        ):
            payload = render_source(
                report,
                validation_issues=[],
                environment="prod",
                source_evidence=self._source_evidence(1),
            )
        self.assertEqual(payload["schema"], "provider-conformance-source")
        self.assertNotIn("version", payload)
        self.assertNotIn("executableSourceCount", payload)


if __name__ == "__main__":
    unittest.main()
