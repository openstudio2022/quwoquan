from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


APP = Path(__file__).resolve().parents[3]
ROOT = APP.parent
VERIFIER = APP / "scripts/runtime/verify_production_release_artifact.py"


class ProductionReleaseArtifactContractTest(unittest.TestCase):
    def test_accepts_clean_production_zip_and_emits_sbom_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "app-release.aab"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("base/manifest/AndroidManifest.xml", "<manifest />")
                archive.writestr("base/dex/classes.dex", b"production-only")
            report = root / "report.json"

            result = _run(artifact, report)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(payload["provenance"]["runtimeEnvironment"], "prod")
            self.assertEqual(payload["sbom"]["spdxVersion"], "SPDX-2.3")
            self.assertEqual(len(payload["sbom"]["files"]), 2)

    def test_rejects_test_only_marker_in_production_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "app-release.aab"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("base/lib/arm64-v8a/libapp.so", b"quwoquan_cloud_mock")
            report = root / "report.json"

            result = _run(artifact, report)

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertIn("quwoquan_cloud_mock", "\n".join(payload["findings"]))

    def test_launcher_handoff_digest_must_be_embedded_in_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff = root / "handoff.json"
            generated = subprocess.run(
                [
                    "python3",
                    "scripts/device/build_launcher_handoff.py",
                    "--env",
                    "prod",
                    "--target",
                    "prod-hosted",
                    "--launch-mode",
                    "release_package",
                ],
                cwd=APP,
                check=True,
                capture_output=True,
                text=True,
            )
            handoff.write_text(generated.stdout, encoding="utf-8")
            digest = json.loads(generated.stdout)[
                "effectiveLaunchManifestDigest"
            ]
            artifact = root / "app-release.aab"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("base/dex/classes.dex", digest.encode("ascii"))
            report = root / "report.json"

            result = _run(artifact, report, handoff=handoff)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["provenance"]["effectiveLaunchManifestDigest"],
                digest,
            )

    def test_release_pipeline_builds_and_scans_all_supported_release_artifacts(self) -> None:
        workflow = (ROOT / ".github/workflows/app_pipeline.yml").read_text(
            encoding="utf-8"
        )
        for job_name, command in (
            ("android:", "flutter build appbundle --release"),
            ("ios:", "flutter build ipa --release"),
            ("macos:", "flutter build macos --release"),
            ("web:", "--kind web"),
        ):
            self.assertIn(job_name, workflow)
            self.assertIn(command, workflow)
        for environment in ("alpha", "beta", "gamma", "prod"):
            self.assertIn(environment, workflow)
        for surface in ("android", "ios", "web", "macos"):
            self.assertIn(f"--surface {surface}", workflow)
        self.assertIn("verify_production_release_artifact.py", workflow)
        self.assertIn("apksigner", workflow)
        self.assertIn("codesign --verify --deep --strict", workflow)
        self.assertIn("${env_name}-ios-launcher-handoff.json", workflow)
        self.assertIn("QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST", workflow)
        self.assertIn("app_candidate_evidence.Dockerfile", workflow)
        self.assertIn("app_evidence_ref", workflow)
        self.assertIn("critical_path_seconds", workflow)
        self.assertNotIn("refs/tags", workflow)
        self.assertNotIn("workflow_dispatch", workflow)


def _run(
    artifact: Path,
    report: Path,
    *,
    handoff: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
            "python3",
            str(VERIFIER),
            "--platform",
            "android",
            "--artifact",
            str(artifact),
            "--report",
            str(report),
        ]
    if handoff is not None:
        command.extend(["--launcher-handoff", str(handoff)])
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QWQ_APP_RUNTIME_ENV": "prod"},
    )


if __name__ == "__main__":
    unittest.main()
