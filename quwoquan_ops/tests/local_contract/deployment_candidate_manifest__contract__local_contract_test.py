from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from quwoquan_ops.cli.lib import deployment_candidate_manifest as subject


class DeploymentCandidateManifestContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.candidate = self.root / "candidate"
        self.app = self.candidate / "packages/app"
        self.shared = self.candidate / "packages/runtime-shared"
        self.legal = self.candidate / "packages/legal-static"
        self.app.mkdir(parents=True)
        self.shared.mkdir(parents=True)
        legal_current = self.legal / "current"
        (legal_current / "public/legal").mkdir(parents=True)
        for relative in (
            "release_metadata.json",
            "checksums.json",
            "public/legal/manifest.json",
        ):
            (legal_current / relative).write_text("{}\n", encoding="utf-8")
        digest = "sha256:" + "a" * 64
        self.snapshot = {
            "baselineId": "sha256:" + "b" * 64,
            "sourceRevision": "c" * 40,
            "workspaceStatusDigest": "sha256:" + "d" * 64,
        }
        (self.app / "environment_runtime.yaml").write_text(
            json.dumps(
                {
                    "schema": "environment-runtime-package",
                    "environment": "alpha",
                    "target": "alpha-local",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.app / "report.json").write_text(
            json.dumps({"runtimeConfigDigest": digest}) + "\n",
            encoding="utf-8",
        )
        (self.app / "package-fingerprint.json").write_text(
            json.dumps(
                {
                    "includeServices": True,
                    "deploymentInputs": {"digest": digest},
                    "packageContent": {"digest": digest},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.shared / "oci-images.json").write_text(
            json.dumps(
                {
                    "buildInputDigest": digest,
                    "imageDigest": "sha256:" + "e" * 64,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.release = self.root / "candidate-release.json"
        self.rollback = self.root / "rollback-release.json"
        for path, release_id, release_digest in (
            (self.release, "west-lake-canonical-20260729", "8" * 64),
            (self.rollback, "pilot-002", "5" * 64),
        ):
            path.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.release_attestation",
                        "releaseId": release_id,
                        "payloadSha256": "sha256:" + release_digest,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "app_deployment_package_dir",
                return_value=self.app,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "runtime_shared_deployment_package_dir",
                return_value=self.shared,
            )
        )
        self.patches.enter_context(
            mock.patch.object(
                subject,
                "legal_static_deployment_package_dir",
                return_value=self.legal,
            )
        )

    def test_full_candidate_binds_package_oci_runtime_and_both_releases(self) -> None:
        path = subject.write_candidate_manifest(
            "alpha",
            "alpha-local",
            package_snapshot=self.snapshot,
            release_attestation=str(self.release),
            rollback_release_attestation=str(self.rollback),
        )
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema"], subject.CANDIDATE_MANIFEST_SCHEMA)
        self.assertEqual(payload["baselineId"], self.snapshot["baselineId"])
        self.assertEqual(
            payload["release"]["candidate"]["releaseId"],
            "west-lake-canonical-20260729",
        )
        self.assertEqual(payload["release"]["rollback"]["releaseId"], "pilot-002")
        subject.validate_candidate_manifest(
            payload,
            expected_environment="alpha",
            expected_target="alpha-local",
            require_full=True,
        )

    def test_full_candidate_rejects_missing_release_binding(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate release attestation is required"):
            subject.write_candidate_manifest(
                "alpha",
                "alpha-local",
                package_snapshot=self.snapshot,
            )


if __name__ == "__main__":
    unittest.main()
