from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.ci import consume_released_release_evidence as consumer
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli.prod.finalize_mainline_release_artifact import (
    RELEASE_CLOSURE_PATHS,
)
from quwoquan_ops.tests.support.release_evidence_manifest_fixture_test_support import (
    ReleaseEvidenceManifestFixtureMixin,
)

DIGEST = "sha256:" + ("a" * 64)
OTHER_DIGEST = "sha256:" + ("b" * 64)
SOURCE_SHA = "c" * 40
REF = f"ghcr.io/owner/repo/release-artifact@{DIGEST}"
ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_REQUIRED_STATUSES = {
    ".github/workflows/app-env-device-matrix-self-hosted.yml": {
        "qualified",
        "released",
    },
    ".github/workflows/beta-device-platform.yml": {"qualified", "released"},
    ".github/workflows/prod-sim-manual-admission.yml": {"main-admitted"},
}


def _selected_required_statuses(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    return {
        *re.findall(r"\bREQUIRED_STATUS=([a-z][a-z-]*)\b", source),
        *re.findall(r"--require-status\s+([a-z][a-z-]*)\b", source),
    }


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
        "releaseCompositionId": DIGEST,
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


class ConsumeReleasedReleaseEvidenceTest(
    ReleaseEvidenceManifestFixtureMixin, unittest.TestCase
):
    def test_active_workflow_statuses_compose_with_canonical_consumer(self) -> None:
        selected_by_workflow = {
            path: _selected_required_statuses(ROOT / path)
            for path in WORKFLOW_REQUIRED_STATUSES
        }
        self.assertEqual(selected_by_workflow, WORKFLOW_REQUIRED_STATUSES)
        selected = set().union(*selected_by_workflow.values())
        self.assertEqual(selected, set(consumer.CONSUMABLE_STATUSES))
        self.assertNotIn("candidate-ready", selected)
        self.assertNotIn("deployable", selected)
        self.assertIs(consumer.validate_manifest, finalizer.validate_manifest)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, qualified = self._candidate_manifest(root)
            main_admitted = self._deployable_manifest(root, artifact, qualified)
            prod_receipts = root / "prod-receipts"
            prod = self._receipt(
                root, main_admitted, kind="environment", environment="prod"
            )
            self._write_json(
                prod_receipts / "prod.json",
                json.loads(prod.read_text(encoding="utf-8")),
            )
            rollout = self._receipt(
                root, main_admitted, kind="rollout", environment="prod"
            )
            rollback = self._receipt(
                root,
                main_admitted,
                kind="rollback",
                environment="prod",
                status="not_triggered",
            )
            released = finalizer.finalize(
                artifact,
                None,
                environment_receipts_dir=prod_receipts,
                rollout_receipt_path=rollout,
                rollback_receipt_path=rollback,
            )
            manifests = {
                str(manifest["status"]): manifest
                for manifest in (qualified, main_admitted, released)
            }
            self.assertEqual(set(manifests), selected)
            for required_status in selected:
                consumer.validate_manifest(
                    manifests[required_status],
                    allowed_statuses={required_status},
                )

    def test_one_reference_derives_candidate_producer_and_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_fixture(root)
            with (
                mock.patch.object(consumer, "validate_manifest"),
                mock.patch.object(consumer, "validate_manifest_files"),
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
                mock.patch.object(consumer, "validate_manifest"),
                mock.patch.object(
                    consumer,
                    "validate_manifest_files",
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
                mock.patch.object(consumer, "validate_manifest"),
                mock.patch.object(consumer, "validate_manifest_files"),
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
                mock.patch.object(consumer, "validate_manifest"),
                mock.patch.object(consumer, "validate_manifest_files"),
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
