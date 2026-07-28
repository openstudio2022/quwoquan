# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.prod import collect_release_artifact_descriptors as collector
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact as finalizer
from quwoquan_ops.cli import stackctl


DIGEST = "sha256:" + ("a" * 64)


class ReleaseArtifactCollectionContractTest(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict[str, object]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def _fixture(self, root: Path) -> tuple[Path, dict[str, Path]]:
        artifact = root / "artifact"
        self._write_json(
            artifact / "manifest.json",
            {
                "schema": "mainline-release-artifact",
                "status": "component-ready",
                "requiredImages": [],
                "imageRepositories": {},
                "versions": {"imageVersion": "1.20260727.1"},
                "images": {},
                "releaseFiles": {},
                "releaseFileDigests": {},
            },
        )
        sources = {
            "publicWeb": self._write_json(
                root / "sources/web.json",
                {"schema": "qwq.public-web.release.v1"},
            ),
            "androidOfficialRelease": self._write_json(
                root / "sources/android.json",
                {"schema": "qwq.android.official-release.v1"},
            ),
            "opsPortal": self._write_json(
                root / "sources/portal.json",
                {"schema": "qwq.ops_portal_package.v1"},
            ),
            "contractGraph": self._write_json(
                root / "sources/contract-graph.json",
                {
                    "sources": [],
                    "documents": [],
                    "objects": [],
                    "operations": [],
                    "projections": [],
                },
            ),
            "providerBindings": self._write_json(
                root / "sources/providers.json",
                {"schema": "compiled-external-provider-bindings"},
            ),
            "testEvidence": self._write_json(
                root / "sources/test-evidence.json",
                {
                    "schema": "qwq.three-layer-case-results.v1",
                    "status": "passed",
                    "layers": {
                        layer: {"status": "passed", "artifactDigest": DIGEST}
                        for layer in (
                            "local_contract",
                            "api_integration",
                            "user_acceptance",
                        )
                    },
                },
            ),
        }
        return artifact, sources

    def test_collects_exactly_six_real_artifacts_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            descriptors = root / "descriptors"
            first = collector.collect(
                artifact_dir=artifact,
                descriptors_dir=descriptors,
                sources=sources,
            )
            second = collector.collect(
                artifact_dir=artifact,
                descriptors_dir=descriptors,
                sources=sources,
            )
            self.assertEqual(first, second)
            self.assertEqual(set(first), set(collector.ARTIFACT_SCHEMAS))
            for artifact_id, descriptor in first.items():
                self.assertEqual(
                    descriptor["schema"], collector.ARTIFACT_SCHEMAS[artifact_id]
                )
                self.assertRegex(descriptor["sha256"], r"^sha256:[0-9a-f]{64}$")
            finalized = finalizer.finalize(artifact, None, descriptors)
            self.assertEqual(finalized["status"], "deployable")
            self.assertEqual(set(finalized["artifacts"]), set(collector.ARTIFACT_SCHEMAS))

    def test_rejects_failed_or_incomplete_test_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            self._write_json(
                sources["testEvidence"],
                {
                    "schema": "qwq.three-layer-case-results.v1",
                    "status": "blocked",
                    "layers": {},
                },
            )
            with self.assertRaisesRegex(ValueError, "status must be passed"):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                )

    def test_stackctl_is_the_whole_app_assembly_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            args = stackctl.build_parser().parse_args(
                [
                    "package",
                    "--env",
                    "prod",
                    "--target",
                    "prod-hosted",
                    "--kind",
                    "release-manifest",
                    "--release-artifact-dir",
                    str(artifact),
                    "--public-web-manifest",
                    str(sources["publicWeb"]),
                    "--android-release-manifest",
                    str(sources["androidOfficialRelease"]),
                    "--ops-portal-provenance",
                    str(sources["opsPortal"]),
                    "--contract-graph",
                    str(sources["contractGraph"]),
                    "--provider-bindings",
                    str(sources["providerBindings"]),
                    "--test-evidence",
                    str(sources["testEvidence"]),
                    "--report-dir",
                    str(root / "report"),
                ]
            )
            result = stackctl.command_package(args)
            self.assertEqual(result["exitCode"], 0, result)
            manifest = json.loads(
                (artifact / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "deployable")

    def test_rejects_schema_drift_and_non_component_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact, sources = self._fixture(root)
            self._write_json(sources["publicWeb"], {"schema": "placeholder"})
            with self.assertRaisesRegex(ValueError, "publicWeb schema mismatch"):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                )
            self._write_json(
                artifact / "manifest.json",
                {"schema": "mainline-release-artifact", "status": "deployable"},
            )
            with self.assertRaisesRegex(ValueError, "must be component-ready"):
                collector.collect(
                    artifact_dir=artifact,
                    descriptors_dir=root / "descriptors",
                    sources=sources,
                )


if __name__ == "__main__":
    unittest.main()
