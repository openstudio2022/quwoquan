from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VERIFIER = (
    ROOT
    / "quwoquan_app"
    / "scripts"
    / "runtime"
    / "verify_app_generated_manifest.py"
)
MANIFEST = (
    ROOT
    / "quwoquan_app"
    / "tool"
    / "cloud_codegen"
    / "generated_manifest.json"
)


class AppGeneratedManifestContractTest(unittest.TestCase):
    def test_fixed_graph_clean_rebuild_is_byte_exact(self) -> None:
        result = subprocess.run(
            ["python3", str(VERIFIER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout}\nstderr={result.stderr}",
        )
        self.assertIn("clean rebuild", result.stdout)

    def test_manifest_owns_operation_route_and_surface_outputs(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        outputs = {item["path"] for item in manifest["outputs"]}

        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/generated/"
            "operation_contracts.g.dart",
            outputs,
        )
        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/rtc/"
            "call_session_dtos.g.dart",
            outputs,
        )
        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/content/"
            "preview_track_manifest_contracts.g.dart",
            outputs,
        )
        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/travel/"
            "travel_operation_contracts.g.dart",
            outputs,
        )
        self.assertIn(
            "packages/quwoquan_cloud_contracts/lib/src/generated/requests/"
            "travel/travel_operation_contracts.g.requests.g.dart",
            outputs,
        )
        for domain in ("tag", "integration", "notification"):
            self.assertIn(
                "packages/quwoquan_cloud_contracts/lib/src/"
                f"{domain}/{domain}_operation_contracts.g.dart",
                outputs,
            )
            self.assertIn(
                "packages/quwoquan_cloud_contracts/lib/src/generated/requests/"
                f"{domain}/{domain}_operation_contracts.g.requests.g.dart",
                outputs,
            )
        self.assertIn(
            "lib/app/navigation/generated/app_route_paths.g.dart",
            outputs,
        )
        self.assertIn(
            "lib/app/navigation/generated/app_ui_surfaces.g.dart",
            outputs,
        )


if __name__ == "__main__":
    unittest.main()
