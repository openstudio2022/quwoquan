from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.ci import consume_released_release_evidence as consumer
from quwoquan_ops.ci.release_evidence_reader import RELEASE_CLOSURE_PATHS

DIGEST = "sha256:" + ("a" * 64)
OTHER_DIGEST = "sha256:" + ("b" * 64)
SOURCE_SHA = "c" * 40
REF = f"ghcr.io/owner/repo/release-artifact@{DIGEST}"


def write_fixture(root: Path, *, status: str = "released") -> None:
    closure = {}
    for label, relative in RELEASE_CLOSURE_PATHS.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"label": label}) + "\n", encoding="utf-8")
        closure[label] = {"path": relative, "digest": DIGEST}
    provider_path = "evidence/provider.json"
    (root / provider_path).write_text(
        json.dumps(
            {
                "sourceEvidence": {
                    "ref": f"oci://ghcr.io/owner/repo/provider-evidence@{OTHER_DIGEST}",
                    "digest": OTHER_DIGEST,
                    "files": {"evidence/raw/provider/cell.json": DIGEST},
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "release-evidence-manifest",
        "status": status,
        "candidateId": DIGEST,
        "artifactDigest": OTHER_DIGEST,
        "source": {
            "gitSha": SOURCE_SHA,
            "treeDigest": DIGEST,
            "repository": "owner/repo",
            "workflowRunId": "98765",
        },
        "testEvidence": {"evidence": {"files": closure}},
        "providerEvidence": {
            "path": provider_path,
            "digest": DIGEST,
        },
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest) + "\n",
        encoding="utf-8",
    )


class ConsumeReleasedReleaseEvidenceTest(unittest.TestCase):
    def test_one_reference_derives_candidate_producer_and_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture(root)
            with (
                mock.patch.object(consumer, "validate_historical_release_snapshot"),
                mock.patch.object(consumer, "validate_historical_release_snapshot"),
            ):
                outputs = consumer.derive(
                    artifact_root=root,
                    release_evidence_ref=REF,
                    repository="owner/repo",
                    require_status="released",
                )
            self.assertEqual(outputs["candidate_digest"], DIGEST)
            self.assertEqual(outputs["artifact_digest"], OTHER_DIGEST)
            self.assertEqual(outputs["source_git_sha"], SOURCE_SHA)
            self.assertEqual(outputs["producer_workflow_run_id"], "98765")
            self.assertEqual(
                outputs["pilot_release_path"],
                str((root / RELEASE_CLOSURE_PATHS["pilot-release"]).resolve()),
            )
            self.assertEqual(outputs["pilot_rollback_digest"], DIGEST)
            self.assertEqual(outputs["content_lifecycle_alpha_digest"], DIGEST)
            self.assertEqual(outputs["green_matrix_digest"], DIGEST)
            self.assertEqual(outputs["provider_source_digest"], OTHER_DIGEST)

    def test_missing_or_mutable_reference_blocks_before_fetch(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(consumer, "fetch") as fetch,
        ):
            for invalid in ("", "ghcr.io/owner/repo/release-artifact:latest"):
                with self.assertRaisesRegex(ValueError, "immutable"):
                    consumer.consume(
                        release_evidence_ref=invalid,
                        repository="owner/repo",
                        artifact_root=Path(temporary),
                        require_status="released",
                    )
            fetch.assert_not_called()

    def test_tampered_closure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture(root)
            with (
                mock.patch.object(consumer, "validate_historical_release_snapshot"),
                mock.patch.object(
                    consumer,
                    "validate_historical_release_snapshot",
                    side_effect=ValueError("pilot-release digest mismatch"),
                ),
                self.assertRaisesRegex(ValueError, "digest mismatch"),
            ):
                consumer.derive(
                    artifact_root=root,
                    release_evidence_ref=REF,
                    repository="owner/repo",
                    require_status="released",
                )

    def test_derived_identity_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture(root)
            with (
                mock.patch.object(consumer, "validate_historical_release_snapshot"),
                mock.patch.object(consumer, "validate_historical_release_snapshot"),
            ):
                for field, expected in (
                    ("expected_candidate", OTHER_DIGEST),
                    ("expected_artifact_digest", DIGEST),
                    ("expected_source_sha", "d" * 40),
                ):
                    with self.assertRaisesRegex(ValueError, "caller expectation"):
                        consumer.derive(
                            artifact_root=root,
                            release_evidence_ref=REF,
                            repository="owner/repo",
                            require_status="released",
                            **{field: expected},
                        )

    def test_oidc_or_signer_verification_failure_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def materialize(_: str, output: Path) -> None:
                write_fixture(output)

            with (
                mock.patch.object(consumer, "fetch", side_effect=materialize),
                mock.patch.object(consumer, "validate_historical_release_snapshot"),
                mock.patch.object(consumer, "validate_historical_release_snapshot"),
                mock.patch.object(
                    consumer,
                    "verify_oci_supply_chain",
                    side_effect=RuntimeError("signed provenance verification failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "signed provenance"),
            ):
                consumer.consume(
                    release_evidence_ref=REF,
                    repository="owner/repo",
                    artifact_root=root,
                    require_status="released",
                )


if __name__ == "__main__":
    unittest.main()
