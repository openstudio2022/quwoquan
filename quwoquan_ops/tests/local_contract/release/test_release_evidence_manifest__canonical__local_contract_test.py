# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.prod import collect_mainline_image_descriptors as image_collector
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors as evidence_collector
from quwoquan_ops.ci import release_evidence_reader as finalizer
from quwoquan_ops.cli.prod import load_prod_plane_images
from quwoquan_ops.tests.support.release_evidence_manifest_fixture_test_support import (
    APP_EVIDENCE_REF,
    DIGEST,
    ReleaseEvidenceManifestFixtureMixin,
)




class ReleaseEvidenceManifestCanonicalContractTest(
    ReleaseEvidenceManifestFixtureMixin, unittest.TestCase
):
    def test_named_readers_accept_explicit_diagnostic_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._build_input(Path(temporary))
            manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))

            self.assertIs(
                finalizer.validate_frozen_diagnostic_snapshot(
                    manifest, artifact_dir=artifact, allowed_statuses={"build-input"}
                ),
                manifest,
            )
            self.assertIs(
                finalizer.validate_historical_release_snapshot(
                    manifest, artifact_dir=artifact, allowed_statuses={"build-input"}
                ),
                manifest,
            )

    def test_named_readers_reject_tampered_or_formal_envelopes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = self._build_input(Path(temporary))
            manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
            for field in ("promotable", "formalAuthority"):
                drifted = json.loads(json.dumps(manifest))
                drifted[field] = True
                for reader in (
                    finalizer.validate_frozen_diagnostic_snapshot,
                    finalizer.validate_historical_release_snapshot,
                ):
                    with self.subTest(field=field, reader=reader.__name__), self.assertRaises(
                        ValueError
                    ):
                        reader(drifted)

    def test_generic_reader_and_writer_surfaces_are_absent(self) -> None:
        for name in (
            "validate",
            "validate_manifest",
            "validate_manifest_files",
            "seal_manifest",
            "finalize",
            "release_verdict",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(finalizer, name))
