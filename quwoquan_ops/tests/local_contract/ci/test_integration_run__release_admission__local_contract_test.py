# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-001
"""`make integrate` 的 Data release 准入必须与 `qwq-data ship verify` 同一闭集（DEC-041：单一 production）。

回归背景：integrate 曾只接受 research/commercial，而 ship verify 只接受 production，
两端互斥使 Alpha 重建后永远无法自动导入 release（OPEN-006）。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import integration_run as subject


def _write_attestation(root: Path, release_id: str, release_class: str) -> Path:
    payload = {
        "schema": "quwoquan_data.release_attestation",
        "releaseId": release_id,
        "releaseClass": release_class,
        "productLifecycleState": release_class,
        "payloadSha256": "sha256:" + "a" * 64,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    local = root / "data/releases" / release_id / "attestations/release.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(encoded)
    handed = root / f"{release_id}.attestation.json"
    handed.write_bytes(encoded)
    return handed


class IntegrationRunReleaseAdmissionTest(unittest.TestCase):
    def test_production_attestation_is_admitted_with_matching_local_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attestation = _write_attestation(root, "20260907--pool-production-m10", "production")
            with mock.patch.object(subject, "OUTPUT_ROOT", root):
                release_id, release_class = subject._release_id(attestation)
        self.assertEqual(release_id, "20260907--pool-production-m10")
        self.assertEqual(release_class, subject.RELEASE_CLASS)
        self.assertEqual(release_class, "production")

    def test_retired_research_and_commercial_classes_are_rejected(self) -> None:
        for retired in ("research", "commercial"):
            with self.subTest(release_class=retired), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                attestation = _write_attestation(root, f"release-{retired}-001", retired)
                with mock.patch.object(subject, "OUTPUT_ROOT", root):
                    with self.assertRaises(subject.IntegrationRunError) as caught:
                        subject._release_id(attestation)
                self.assertEqual(caught.exception.code, "INTEGRATION_RUN.INPUT_INVALID")

    def test_release_absent_from_worktree_data_root_is_a_typed_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attestation = _write_attestation(root, "20260907--pool-production-m10", "production")
            with mock.patch.object(subject, "OUTPUT_ROOT", root / "elsewhere"):
                with self.assertRaises(subject.IntegrationRunError) as caught:
                    subject._release_id(attestation)
        self.assertEqual(caught.exception.code, "INTEGRATION_RUN.DATA_RELEASE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
