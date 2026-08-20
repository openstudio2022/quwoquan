"""prod-sim exact Release 启动边界的 local_contract。"""

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-004

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "quwoquan_app/scripts/device/launch_release_artifact.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("launch_release_artifact", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LaunchReleaseArtifactTest(unittest.TestCase):
    def test_ios_release_simulator_fails_before_manifest_consumption(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            missing_manifest = Path(directory) / "does-not-exist.json"
            with self.assertRaisesRegex(
                ValueError,
                "APP.LAUNCH.ios_release_simulator_unsupported",
            ):
                module._load_inputs(missing_manifest, "ios")


if __name__ == "__main__":
    unittest.main()
