from __future__ import annotations

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
        self.assertIn("data=false", result.stdout)

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
        self.assertIn("data=true", result.stdout)

    def test_ops_change_impacts_data_and_all_hosted_scopes(self) -> None:
        result = run_detect("quwoquan_ops/ci/detect_ci_impacted_scopes.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        for scope in ("service", "app", "portal", "topology", "data"):
            self.assertIn(f"{scope}=true", result.stdout)

    def test_data_script_change_keeps_complete_data_and_hosted_closure(self) -> None:
        result = run_detect("quwoquan_data/scripts/content/release/publish.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        for scope in ("service", "app", "portal", "topology", "data"):
            self.assertIn(f"{scope}=true", result.stdout)

    def test_docs_only_change_keeps_every_scope_not_required(self) -> None:
        result = run_detect("docs/ci/delivery-gate.md")
        self.assertEqual(result.returncode, 0, result.stderr)
        for scope in ("service", "app", "portal", "topology", "data"):
            self.assertIn(f"{scope}=false", result.stdout)

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
        self.assertIn("data=true", result.stdout)

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

    def test_scope_receipt_is_canonical_evidence_fingerprint(self) -> None:
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
                    *[value for path in paths for value in ("--changed-file", path)],
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(receipt.read_text(encoding="utf-8"))

        from quwoquan_ops.cli.lib.evidence_fingerprint import (
            validate_evidence_fingerprint,
        )

        validated = validate_evidence_fingerprint(payload)
        self.assertEqual(validated["digest_payload"]["git"]["head_sha"], "b" * 40)
        self.assertEqual(
            validated["digest_payload"]["git"]["merge_base_sha"], "a" * 40
        )
        self.assertRegex(
            validated["digest_payload"]["workspace"]["tracked_digest"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertRegex(
            validated["digest_payload"]["execution"]["generator_digest"],
            r"^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            validated["captured_metadata"]["changed_paths_digest"],
            validated["digest_payload"]["workspace"]["tracked_digest"],
        )
        self.assertEqual(
            validated["captured_metadata"]["planner_digest"],
            validated["digest_payload"]["execution"]["generator_digest"],
        )
        self.assertEqual(
            validated["captured_metadata"]["scope_states"],
            {
                "service": "required",
                "app": "required",
                "portal": "not_required",
                "topology": "not_required",
                "data": "not_required",
            },
        )
        self.assertEqual(
            validated["captured_metadata"]["planner_version"], "impact-planner-v2"
        )

    def test_receipt_requires_lowercase_exact_shas(self) -> None:
        for base_sha, head_sha in (
            ("a" * 39, "b" * 40),
            ("A" * 40, "b" * 40),
            ("a" * 40, "HEAD"),
            ("a" * 40, "b" * 64),
        ):
            with tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--base-sha",
                        base_sha,
                        "--head-sha",
                        head_sha,
                        "--scope-receipt",
                        str(Path(directory) / "scope.json"),
                        "--changed-file",
                        "quwoquan_app/lib/runtime/bootstrap.dart",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact SHA", result.stderr)

    def test_malformed_changed_paths_fail_closed(self) -> None:
        for path in (
            "../quwoquan_app/lib/main.dart",
            "quwoquan_app/../quwoquan_data/file.py",
            "/tmp/quwoquan_app/lib/main.dart",
            "C:/repo/quwoquan_app/lib/main.dart",
            "quwoquan_app//lib/main.dart",
            "quwoquan_app/lib/main.dart\nignored",
        ):
            result = run_detect(path)
            self.assertNotEqual(result.returncode, 0, path)
            self.assertIn("detect_ci_impacted_scopes: FAIL", result.stderr)

        from quwoquan_ops.ci.impact_planner_core import normalize_changed_path

        with self.assertRaises(ValueError):
            normalize_changed_path("quwoquan_app/lib/main.dart\x00ignored")

    def test_dot_segment_is_canonicalized_and_nfc_paths_share_identity(self) -> None:
        dotted = run_detect("./quwoquan_app/lib/main.dart")
        self.assertEqual(dotted.returncode, 0, dotted.stderr)
        self.assertIn("app=true", dotted.stdout)

        from quwoquan_ops.ci.impact_planner_core import classify_impacts

        composed = classify_impacts(["docs/café.md"])
        decomposed = classify_impacts(["docs/cafe\u0301.md"])
        self.assertEqual(composed["paths"], decomposed["paths"])
        self.assertEqual(composed["path_digest"], decomposed["path_digest"])

    def test_delivery_impact_plan_is_versioned_and_validated(self) -> None:
        from quwoquan_ops.ci.impact_planner_core import (
            build_delivery_impact_plan,
            validate_delivery_impact_plan,
        )

        plan = build_delivery_impact_plan(
            ["quwoquan_app/lib/runtime/shell/startup/app_bootstrap.dart"],
            source_sha="b" * 40,
            base_sha="a" * 40,
        )
        validated = validate_delivery_impact_plan(
            plan, expected_source_sha="b" * 40
        )
        self.assertEqual(validated["schema"], "delivery-impact-plan")
        self.assertEqual(validated["schema_version"], 1)
        self.assertEqual(validated["states"]["device"], "required")
        self.assertRegex(validated["changed_paths_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(validated["plan_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_device_impact_is_narrow_and_manual_force_is_explicit(self) -> None:
        from quwoquan_ops.ci.impact_planner_core import build_delivery_impact_plan

        not_required_paths = (
            "docs/ci/readme.md",
            "quwoquan_service/services/chat-service/cmd/api/main.go",
            "quwoquan_app/lib/service/chat_service/chat/message/presentation/message_bubble.dart",
            "quwoquan_app/lib/design_system/components/primary_button.dart",
        )
        required_paths = (
            "quwoquan_app/lib/runtime/shell/startup/app_bootstrap.dart",
            "quwoquan_app/lib/runtime/platform/permissions/microphone_permission_guard.dart",
            "quwoquan_app/android/app/src/main/AndroidManifest.xml",
            "quwoquan_app/ios/Runner/Runner.entitlements",
            "quwoquan_app/vendor/plugins/flutter_webrtc/pubspec.yaml",
            "quwoquan_app/scripts/device/dev_launch.sh",
            ".github/workflows/beta-device-platform.yml",
            "quwoquan_ops/environments/beta/runtime.yaml",
        )
        for changed_path in not_required_paths:
            plan = build_delivery_impact_plan(
                [changed_path], source_sha="b" * 40, base_sha="a" * 40
            )
            self.assertEqual(plan["states"]["device"], "not_required", changed_path)
        for changed_path in required_paths:
            plan = build_delivery_impact_plan(
                [changed_path], source_sha="b" * 40, base_sha="a" * 40
            )
            self.assertEqual(plan["states"]["device"], "required", changed_path)
        forced = build_delivery_impact_plan(
            ["docs/ci/readme.md"], source_sha="b" * 40, base_sha="a" * 40,
            force_device=True,
        )
        self.assertEqual(forced["states"]["device"], "required")

    def test_coverage_governance_path_triggers_contract_closure(self) -> None:
        from quwoquan_ops.ci.impact_planner_core import build_delivery_impact_plan

        plan = build_delivery_impact_plan(
            ["quwoquan_ops/policies/gates/canonical_coverage_baseline.json"],
            source_sha="b" * 40, base_sha="a" * 40,
        )
        self.assertEqual(plan["states"]["coverage_service"], "required")
        self.assertEqual(plan["states"]["coverage_app"], "required")

    def test_plan_digest_or_source_tampering_fails_closed(self) -> None:
        from quwoquan_ops.ci.impact_planner_core import (
            ImpactPlannerError, build_delivery_impact_plan, validate_delivery_impact_plan,
        )

        plan = build_delivery_impact_plan(
            ["quwoquan_app/lib/main.dart"], source_sha="b" * 40, base_sha="a" * 40
        )
        plan["changed_paths_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(ImpactPlannerError):
            validate_delivery_impact_plan(plan, expected_source_sha="b" * 40)


if __name__ == "__main__":
    unittest.main()
