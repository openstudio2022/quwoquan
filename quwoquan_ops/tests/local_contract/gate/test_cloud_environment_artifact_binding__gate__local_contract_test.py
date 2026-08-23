from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from quwoquan_ops.gate import verify_cloud_environment_artifact_binding as gate


class CloudEnvironmentArtifactBindingGateTest(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        self.assertEqual(gate.collect_issues(), [])

    def test_baked_environment_facts_and_missing_entry_validation_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fragment_relatives = [
                path.relative_to(gate.ROOT)
                for pattern in gate.COMPOSE_FRAGMENTS_GLOBS
                for path in sorted(gate.ROOT.glob(pattern))
            ]
            for relative in (
                *gate.RUNTIME_DOCKERFILES,
                *gate.GO_ENTRYPOINTS,
                gate.PYTHON_ENTRYPOINT,
                gate.BUILDER,
                *fragment_relatives,
            ):
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
                    1,
                ),
                encoding="utf-8",
            )
            fragment = root / fragment_relatives[0]
            fragment.write_text(
                fragment.read_text(encoding="utf-8").replace(
                    gate.IDENTITY_MOUNT_MARKER, ":/etc/quwoquan/removed:ro", 1
                ),
                encoding="utf-8",
            )
            issues = gate.collect_issues(root)
        self.assertTrue(
            any("environment runtime facts are baked" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("startup does not validate" in issue for issue in issues),
            issues,
        )
        self.assertTrue(
            any("does not mount the artifact identity file" in issue for issue in issues),
            issues,
        )


if __name__ == "__main__":
    unittest.main()
