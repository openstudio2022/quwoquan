from __future__ import annotations

import unittest

from quwoquan_ops.ci.release_evidence_reader import RELEASE_CLOSURE_PATHS
from quwoquan_ops.ci.render_delivery_release_evidence import canonical_digest, render


class DeliveryReleaseEvidenceTest(unittest.TestCase):
    def _user_acceptance_source(self) -> dict:
        source = {
            "gitSha": "a" * 40,
            "treeDigest": "sha1:" + "b" * 40,
            "repository": "owner/repo",
            "workflowRunId": "remote-uat-run",
        }
        observation = {
            "source": source,
            "generatedAt": "2026-07-27T23:50:00Z",
            "jobs": {
                "android_remote_patrol": "success",
                "ios_remote_patrol": "success",
            },
            "candidateMaterial": {
                "images": {"content-service": "sha256:" + "1" * 64},
                "configurationPackages": {
                    environment: {"content-service": "sha256:" + "2" * 64}
                    for environment in ("alpha", "beta", "gamma", "prod")
                },
                "applicationPackages": {
                    environment: {
                        "android": "sha256:" + "3" * 64,
                        "ios": "sha256:" + "4" * 64,
                    }
                    for environment in ("alpha", "beta", "gamma", "prod")
                },
                "contractGraphDigest": "sha256:" + "5" * 64,
            },
        }
        return {
            "schema": "qwq.three-layer-case-results",
            "status": "passed",
            "generatedAt": "2026-07-27T23:50:00Z",
            "source": source,
            "layers": {
                "user_acceptance": {
                    "status": "passed",
                    "artifactDigest": canonical_digest(observation),
                    **observation,
                }
            },
        }

    def _render(self, **overrides: object) -> dict:
        values = {
            "source_git_sha": "a" * 40,
            "source_tree_digest": "sha1:" + "b" * 40,
            "repository": "owner/repo",
            "workflow_run_id": "12345",
            "job_results": {
                "topology": "success",
                "search": "success",
                "service": "success",
            },
            "requirements": {
                "local_contract": ["topology", "service"],
                "api_integration": ["search"],
                "user_acceptance": [],
            },
            "generated_at": "2026-07-28T00:00:00Z",
            "user_acceptance_source": self._user_acceptance_source(),
            "user_acceptance_transport_digest": "sha256:" + "c" * 64,
            "evidence_files": {
                label: {
                    "path": path,
                    "digest": "sha256:" + f"{index + 10:064x}",
                }
                for index, (label, path) in enumerate(
                    sorted(RELEASE_CLOSURE_PATHS.items())
                )
            },
        }
        values.update(overrides)
        return render(**values)

    def test_real_success_results_create_three_immutable_layers(self) -> None:
        payload = self._render()
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(
            set(payload["layers"]),
            {"local_contract", "api_integration", "user_acceptance"},
        )
        for evidence in payload["layers"].values():
            self.assertRegex(evidence["artifactDigest"], r"^sha256:[0-9a-f]{64}$")
            self.assertEqual(evidence["status"], "passed")
        self.assertEqual(
            payload["layers"]["user_acceptance"]["sourceEvidence"][
                "transportDigest"
            ],
            "sha256:" + "c" * 64,
        )
        self.assertEqual(
            set(payload["evidence"]["files"]),
            set(RELEASE_CLOSURE_PATHS),
        )

    def test_missing_green_matrix_exact_file_binding_is_rejected(self) -> None:
        files = {
            label: {
                "path": path,
                "digest": "sha256:" + f"{index + 20:064x}",
            }
            for index, (label, path) in enumerate(
                sorted(RELEASE_CLOSURE_PATHS.items())
            )
        }
        files.pop("green-matrix")
        with self.assertRaisesRegex(ValueError, "file set is incomplete"):
            self._render(evidence_files=files)

    def test_skipped_or_failed_result_cannot_be_promoted(self) -> None:
        with self.assertRaisesRegex(ValueError, "api_integration is not passed"):
            self._render(
                job_results={
                    "topology": "success",
                    "service": "success",
                    "search": "skipped",
                }
            )

    def test_fake_job_alias_cannot_replace_remote_user_acceptance(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot combine"):
            self._render(
                requirements={
                    "local_contract": ["topology"],
                    "api_integration": ["search"],
                    "user_acceptance": ["search"],
                },
            )

    def test_missing_remote_user_acceptance_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires immutable real Remote"):
            self._render(user_acceptance_source=None)

    def test_tampered_remote_user_acceptance_is_rejected(self) -> None:
        source = self._user_acceptance_source()
        source["layers"]["user_acceptance"]["jobs"]["ios_remote_patrol"] = "failure"
        with self.assertRaisesRegex(ValueError, "no real successful jobs"):
            self._render(user_acceptance_source=source)


if __name__ == "__main__":
    unittest.main()
