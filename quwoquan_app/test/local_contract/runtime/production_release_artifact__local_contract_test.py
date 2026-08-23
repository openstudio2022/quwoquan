from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
import zipfile
from importlib import util
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parents[3]
ROOT = APP.parent
VERIFIER = APP / "scripts/runtime/architecture/verify_production_release_artifact.py"


def _load_verifier_module():
    spec = util.spec_from_file_location("verify_production_release_artifact", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class ProductionReleaseArtifactContractTest(unittest.TestCase):
    def test_ios_bundle_rejects_unembedded_rpath_framework(self) -> None:
        verifier = _load_verifier_module()
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "Runner.app"
            app.mkdir()
            executable = app / "Runner"
            executable.write_bytes(b"\xcf\xfa\xed\xfeproduction")
            otool = subprocess.CompletedProcess(
                ["otool"],
                0,
                stdout=(
                    f"{executable}:\n"
                    "\t@rpath/Missing.framework/Missing "
                    "(compatibility version 1.0.0, current version 1.0.0)\n"
                ),
                stderr="",
            )
            with mock.patch.object(verifier.subprocess, "run", return_value=otool):
                missing = verifier.missing_ios_rpath_dependencies(app)
            self.assertEqual(
                missing,
                ["Runner -> @rpath/Missing.framework/Missing"],
            )

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

    def test_release_artifact_keeps_runtime_configuration_external(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "app-release.apk"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("classes.dex", b"production-only")
                archive.writestr(
                    "assets/qwq_runtime/runtime-config-trust.json",
                    json.dumps(
                        {
                            "schema": "app-runtime-config-trust",
                            "schemaVersion": "1",
                            "buildProfile": "prod",
                            "signatureAlgorithm": "ed25519",
                            "trustedPublicKeys": {"prod-key": "public-key"},
                        }
                    ),
                )
            entries = dict(_load_verifier_module().iter_artifact_entries(artifact))
            executable = entries["classes.dex"]
            for retired in (
                b"APP_RUNTIME_ENV=",
                b"CLOUD_GATEWAY_BASE_URL=",
                b"APP_LAUNCH_POLICY=",
                b"QWQ_LAUNCH_TARGET=",
                b"effectiveLaunchManifestDigest",
            ):
                self.assertNotIn(retired, executable)
            self.assertNotIn(
                "assets/qwq_runtime/runtime-config-package.json",
                entries,
            )
            self.assertIn(
                "assets/qwq_runtime/runtime-config-trust.json",
                entries,
            )

    def test_release_pipeline_compiles_exactly_five_build_products(self) -> None:
        workflow = (ROOT / ".github/workflows/app_pipeline.yml").read_text(
            encoding="utf-8"
        )
        build_products = re.findall(r"- buildProductId: ([a-z0-9-]+)", workflow)
        self.assertEqual(
            build_products,
            [
                "android-nonprod-apk",
                "android-prod-apk",
                "ios-nonprod-app",
                "ios-prod-app",
                "web-shared",
            ],
        )
        self.assertEqual(workflow.count("--kind app-artifact"), 1)
        self.assertIn('--build-product-id "${{ matrix.buildProductId }}"', workflow)
        for retired in (
            "--app-platform",
            "--app-build-mode",
            "--distribution-class",
            "QWQ_ANDROID_ALPHA_GOOGLE_SERVICES_JSON",
            "QWQ_ANDROID_BETA_GOOGLE_SERVICES_JSON",
            "QWQ_ANDROID_GAMMA_GOOGLE_SERVICES_JSON",
        ):
            self.assertNotIn(retired, workflow)
        self.assertIn("QWQ_ANDROID_NONPROD_GOOGLE_SERVICES_JSON", workflow)
        self.assertIn("QWQ_ANDROID_PROD_GOOGLE_SERVICES_JSON", workflow)
        self.assertIn("collect_stackctl_app_shard.py", workflow)
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
