from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from quwoquan_ops.gate import verify_cloud_environment_artifact_binding as gate


class CloudEnvironmentArtifactBindingGateTest(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        self.assertEqual(gate.collect_issues(), [])

    def test_cross_environment_platform_image_and_missing_entry_validation_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (*gate.RUNTIME_DOCKERFILES, *gate.GO_ENTRYPOINTS, gate.PYTHON_ENTRYPOINT, gate.BUILDER):
                source = gate.ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            platform = root / gate.PLATFORM_DOCKERFILE
            platform.write_text(
                platform.read_text(encoding="utf-8")
                + "\nCOPY quwoquan_ops/external/ /app/quwoquan_ops/external/\n",
                encoding="utf-8",
            )
            entrypoint = root / gate.GO_ENTRYPOINTS[0]
            entrypoint.write_text(
                entrypoint.read_text(encoding="utf-8").replace(
                    "artifactidentity.LoadAndValidate(",
                    "artifactidentity.RemovedValidation(",
                ),
                encoding="utf-8",
            )
            issues = gate.collect_issues(root)
        self.assertTrue(
            any("cross-environment runtime facts" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("startup does not validate" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
