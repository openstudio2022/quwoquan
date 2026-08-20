from __future__ import annotations

import json
import os
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


def _write_prod_runtime_package(deploy_root: Path) -> None:
    package = deploy_root / "prod-hosted" / "packages" / "app"
    package.mkdir(parents=True, exist_ok=True)
    (package / "app_runtime.yaml").write_text(
        "\n".join(  # noqa: FLY002 - fixture remains readable as YAML lines.
            [
                "schema: app-runtime-config",
                "runtime:",
                "  appRuntimeEnv: prod",
                "  gatewayBaseUrl: https://api.quwoquan.com",
                "  legalBaseUrl: https://quwoquan.com/legal",
                "  publicWebBaseUrl: https://quwoquan.com",
                "  appDownloadBaseUrl: https://cdn.quwoquan.com/download",
                "  realtimeBaseUrl: wss://api.quwoquan.com",
                "  mediaAvatarCdnBaseUrl: https://cdn.quwoquan.com/media/avatar",
                "  mediaImageCdnBaseUrl: https://cdn.quwoquan.com/media/image",
                "  mediaVideoCdnBaseUrl: https://cdn.quwoquan.com/media/video",
                "  mediaUploadBaseUrl: https://upload.quwoquan.com",
                "  rtcMediaConnectionUrl: wss://rtc.quwoquan.com",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (package / "report.json").write_text(
        json.dumps(
            {
                "status": "packaged",
                "env": "prod",
                "target": "prod-hosted",
            }
        )
        + "\n",
        encoding="utf-8",
    )


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

    def test_launcher_handoff_digest_must_be_embedded_in_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deploy_root = root / "deploy"
            _write_prod_runtime_package(deploy_root)
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
                env={
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
                },
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
        for job_name in ("android:", "ios:", "web:"):
            self.assertIn(job_name, workflow)
        self.assertNotIn("macos:", workflow)
        self.assertNotIn("flutter build", workflow)
        self.assertEqual(
            workflow.count("stackctl.py --output-format json package"),
            3,
        )
        for environment in ("alpha", "beta", "gamma", "prod"):
            self.assertIn(environment, workflow)
        for surface in ("android", "ios", "web"):
            self.assertIn(f"--app-platform {surface}", workflow)
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
