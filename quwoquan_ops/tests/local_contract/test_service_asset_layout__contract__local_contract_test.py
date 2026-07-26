from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = ROOT / "quwoquan_ops/gate/verify_service_architecture.py"


class ServiceAssetLayoutContractTest(unittest.TestCase):
    def test_object_first_service_architecture_gate_passes(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFIER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn("[verify-service-architecture] OK", result.stdout)

    def test_service_identity_is_derived_without_asset_registry(self) -> None:
        self.assertFalse(
            (ROOT / "quwoquan_service/service_asset_profiles.json").exists()
        )
        services = ROOT / "quwoquan_service/services"
        for service in (path for path in services.iterdir() if path.is_dir()):
            self.assertTrue((service / "internal").is_dir(), service.name)
            self.assertTrue((service / "build/Dockerfile").is_file(), service.name)

    def test_go_service_images_share_buildkit_compile_caches(self) -> None:
        services = ROOT / "quwoquan_service/services"
        go_dockerfiles = []
        for dockerfile in services.glob("*/build/Dockerfile"):
            source = dockerfile.read_text(encoding="utf-8")
            if "go build" not in source:
                continue
            go_dockerfiles.append(dockerfile)
            self.assertIn(
                "id=quwoquan-go-mod,target=/go/pkg/mod",
                source,
                dockerfile,
            )
            self.assertIn(
                "id=quwoquan-go-build,target=/root/.cache/go-build",
                source,
                dockerfile,
            )
        self.assertTrue(go_dockerfiles)


if __name__ == "__main__":
    unittest.main()
