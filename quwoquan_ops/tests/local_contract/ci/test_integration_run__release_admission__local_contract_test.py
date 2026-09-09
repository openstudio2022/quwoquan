# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001
"""lane acceptance 消费当前无类别 Data attestation 与本树 exact release。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import integration_run as subject
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import release_attestation_payload


def _write_attestation(root: Path, release_id: str, **extra: object) -> Path:
    payload = release_attestation_payload(release_id, "sha256:" + "a" * 64)
    payload.update(extra)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    local = root / "data/releases" / release_id / "attestations/release.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(encoded)
    handed = root / f"{release_id}.attestation.json"
    handed.write_bytes(encoded)
    return handed


class IntegrationRunReleaseAdmissionTest(unittest.TestCase):
    def test_category_free_attestation_is_admitted_with_exact_local_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attestation = _write_attestation(root, "release-m1-candidate")
            with mock.patch.object(subject, "OUTPUT_ROOT", root):
                self.assertEqual(subject._release_id(attestation), "release-m1-candidate")

    def test_all_retired_release_category_fields_are_rejected(self) -> None:
        for field in ("releaseClass", "productLifecycleState", "readinessPhase"):
            for value in ("research", "commercial", "production"):
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    attestation = _write_attestation(root, "release-m1-candidate", **{field: value})
                    with mock.patch.object(subject, "OUTPUT_ROOT", root):
                        with self.assertRaises(subject.IntegrationRunError) as caught:
                            subject._release_id(attestation)
                    self.assertEqual(caught.exception.code, "INTEGRATION_RUN.INPUT_INVALID")

    def test_release_absent_from_worktree_data_root_is_a_typed_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attestation = _write_attestation(root, "release-m1-candidate")
            with mock.patch.object(subject, "OUTPUT_ROOT", root / "elsewhere"):
                with self.assertRaises(subject.IntegrationRunError) as caught:
                    subject._release_id(attestation)
        self.assertEqual(caught.exception.code, "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
