from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[4] / "quwoquan_ops" / "ci" / "detect_ci_impacted_scopes.py"


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
            "quwoquan_service/services/user-service/contracts/account/user_account/storage.yaml"
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

    def test_l1_spec_change_triggers_its_owned_app_scope(self) -> None:
        result = run_detect("specs/feature-tree/runtime/runtime-client-foundation/spec.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=false", result.stdout)
        self.assertIn("app=true", result.stdout)
        self.assertIn("portal=false", result.stdout)
        self.assertIn("topology=false", result.stdout)

    def test_spec_change_triggers_scopes_by_feature_ownership(self) -> None:
        result = run_detect(
            "specs/feature-tree/runtime/runtime-client-foundation/unified-app-page-access/spec.md"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=false", result.stdout)
        self.assertIn("app=true", result.stdout)
        self.assertIn("portal=false", result.stdout)
        self.assertIn("topology=false", result.stdout)

    def test_product_ops_spec_change_triggers_service_and_portal(self) -> None:
        result = run_detect(
            "specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=true", result.stdout)
        self.assertIn("app=true", result.stdout)
        self.assertIn("portal=true", result.stdout)
        self.assertIn("topology=false", result.stdout)

    def test_platform_spec_change_triggers_service_and_portal(self) -> None:
        result = run_detect(
            "specs/feature-tree/platform-ops-governance/config-and-reliability-governance/spec.md"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=true", result.stdout)
        self.assertIn("app=false", result.stdout)
        self.assertIn("portal=true", result.stdout)
        self.assertIn("topology=false", result.stdout)

    def test_missing_diff_defaults_to_all_impacted(self) -> None:
        result = run_detect()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=true", result.stdout)
        self.assertIn("app=true", result.stdout)
        self.assertIn("portal=true", result.stdout)
        self.assertIn("topology=true", result.stdout)

    def test_required_scope_policy_overrides_diff_without_skipped_inference(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--changed-file",
                "quwoquan_service/services/chat-service/cmd/api/bootstrap.go",
                "--required-scope",
                "app",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("service=true", result.stdout)
        self.assertIn("app=true", result.stdout)

    def test_scope_receipt_binds_identity_paths_and_required_state(self) -> None:
        paths = [
            "quwoquan_app/lib/runtime/bootstrap.dart",
            "quwoquan_service/services/chat-service/cmd/api/bootstrap.go",
        ]
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "scope.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--base-sha",
                    "a" * 40,
                    "--head-sha",
                    "b" * 40,
                    "--scope-receipt",
                    str(receipt),
                    *[
                        value
                        for path in paths
                        for value in ("--changed-file", path)
                    ],
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(
            payload,
            {
                "schema": "ci-impacted-scope-receipt",
                "baseSha": "a" * 40,
                "headSha": "b" * 40,
                "changedPathsDigest": "sha256:"
                + hashlib.sha256(
                    json.dumps(
                        paths,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "scopes": {
                    "app": "required",
                    "data": "not_required",
                    "portal": "not_required",
                    "service": "required",
                    "topology": "not_required",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
