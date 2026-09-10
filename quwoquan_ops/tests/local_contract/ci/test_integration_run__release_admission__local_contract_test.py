# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001
"""Data release 准入沿用当前无类别 schema，并要求本工作树持有 exact bytes。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import integration_run as subject
from quwoquan_ops.tests.support.deployment_candidate_manifest_test_support import (
    release_attestation_payload,
)


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
    def test_attestation_is_admitted_with_matching_local_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attestation = _write_attestation(root, "release-candidate")
            with mock.patch.object(subject, "OUTPUT_ROOT", root):
                self.assertEqual(subject._release_id(attestation), "release-candidate")

    def test_all_retired_release_classes_are_rejected(self) -> None:
        for retired in ("research", "commercial", "production"):
            with self.subTest(release_class=retired), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                attestation = _write_attestation(root, "release-candidate", releaseClass=retired)
                with mock.patch.object(subject, "OUTPUT_ROOT", root):
                    with self.assertRaises(subject.IntegrationRunError) as caught:
                        subject._release_id(attestation)
                self.assertEqual(caught.exception.code, "INTEGRATION_RUN.INPUT_INVALID")

    def test_release_absent_from_worktree_data_root_is_a_typed_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attestation = _write_attestation(root, "release-candidate")
            with mock.patch.object(subject, "OUTPUT_ROOT", root / "elsewhere"):
                with self.assertRaises(subject.IntegrationRunError) as caught:
                    subject._release_id(attestation)
        self.assertEqual(caught.exception.code, "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE")

    def test_local_attestation_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attestation = _write_attestation(root, "release-candidate")
            local = root / "data/releases/release-candidate/attestations/release.json"
            local.write_bytes(local.read_bytes() + b"\n")
            with mock.patch.object(subject, "OUTPUT_ROOT", root):
                with self.assertRaises(subject.IntegrationRunError) as caught:
                    subject._release_id(attestation)
        self.assertEqual(caught.exception.code, "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
