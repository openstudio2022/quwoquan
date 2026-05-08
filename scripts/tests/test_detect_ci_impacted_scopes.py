from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "detect_ci_impacted_scopes.py"


def run_detect(*paths: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPT)]
    for path in paths:
        command.extend(["--changed-file", path])
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


class DetectCiImpactedScopesTest(unittest.TestCase):
    def test_app_only_change_skips_other_scopes(self) -> None:
        result = run_detect("quwoquan_app/lib/ui/chat/pages/chat_page.dart")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("app=true", result.stdout)
        self.assertIn("service=false", result.stdout)
        self.assertIn("portal=false", result.stdout)
        self.assertIn("topology=false", result.stdout)

    def test_metadata_change_impacts_service_app_and_portal(self) -> None:
        result = run_detect(
            "quwoquan_service/contracts/metadata/user/user_profile/storage.yaml"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=true", result.stdout)
        self.assertIn("app=true", result.stdout)
        self.assertIn("portal=true", result.stdout)
        self.assertIn("topology=false", result.stdout)

    def test_workflow_change_impacts_all_scopes(self) -> None:
        result = run_detect(".github/workflows/delivery-gate.yml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=true", result.stdout)
        self.assertIn("app=true", result.stdout)
        self.assertIn("portal=true", result.stdout)
        self.assertIn("topology=true", result.stdout)

    def test_doc_only_change_does_not_trigger_scopes(self) -> None:
        result = run_detect("specs/feature-tree/runtime/runtime-client-foundation/spec.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=false", result.stdout)
        self.assertIn("app=false", result.stdout)
        self.assertIn("portal=false", result.stdout)
        self.assertIn("topology=false", result.stdout)

    def test_missing_diff_defaults_to_all_impacted(self) -> None:
        result = run_detect()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=true", result.stdout)
        self.assertIn("app=true", result.stdout)
        self.assertIn("portal=true", result.stdout)
        self.assertIn("topology=true", result.stdout)


if __name__ == "__main__":
    unittest.main()
