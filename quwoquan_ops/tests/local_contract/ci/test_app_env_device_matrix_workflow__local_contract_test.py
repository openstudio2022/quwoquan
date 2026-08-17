from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
PROFILES = ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"


class AppEnvDeviceMatrixWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.profiles = json.loads(PROFILES.read_text(encoding="utf-8"))

    def run_summary(
        self,
        *,
        enabled: bool,
        debug_skip_requested: bool = False,
        stack: str = "success",
        android: str = "success",
        ios: str = "success",
        aggregate: str = "success",
    ) -> tuple[subprocess.CompletedProcess[str], str]:
        summary_section = self.workflow.split(
            "      - id: summary\n", maxsplit=1
        )[1].split("\n\n  attest_nightly_receipt:", maxsplit=1)[0]
        script = textwrap.dedent(
            summary_section.split("        run: |\n", maxsplit=1)[1]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "github-output"
            env = {
                **os.environ,
                "SELF_HOSTED_ENABLED": str(enabled).lower(),
                "DEBUG_SKIP_REQUESTED": str(debug_skip_requested).lower(),
                "STACK": stack,
                "ANDROID": android,
                "IOS": ios,
                "AGGREGATE": aggregate,
                "TEARDOWN": "skipped",
                "FORMAL_RUNTIME_STARTED": "false",
                "MANAGED_RUNTIME_STARTED": "false",
                "ALLOW_MISSING": "false",
                "SUMMARY_REPO_DIR": str(ROOT),
                "GITHUB_OUTPUT": str(output),
            }
            result = subprocess.run(
                ["bash", "-c", script],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            return result, output.read_text(encoding="utf-8") if output.exists() else ""

    def test_required_path_missing_enablement_variable_fails_closed(self) -> None:
        result, output = self.run_summary(enabled=False)

        self.assertEqual(result.returncode, 2)
        self.assertIn("ENABLE_SELF_HOSTED_MOBILE_MATRIX must equal true", result.stdout)
        self.assertNotIn("result=success", output)

    def test_explicit_standalone_manual_debug_can_report_skipped(self) -> None:
        self.assertIn("allow_disabled_mobile_matrix_debug:", self.workflow)
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && "
            "inputs.allow_disabled_mobile_matrix_debug == true",
            self.workflow,
        )
        result, output = self.run_summary(
            enabled=False,
            debug_skip_requested=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "result=skipped\n")

    def test_missing_ios_platform_fails_closed(self) -> None:
        result, output = self.run_summary(enabled=True, ios="skipped")

        self.assertEqual(result.returncode, 1)
        self.assertIn("ios expected success, got skipped", result.stderr)
        self.assertNotIn("result=success", output)

    def test_dual_platform_success_is_aggregated(self) -> None:
        result, output = self.run_summary(enabled=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "result=success\n")
        self.assertIn("device matrix gate passed", result.stdout)

    def test_nightly_schedule_resolves_to_strict_full_profile(self) -> None:
        self.assertIn("- cron: '0 18 * * *'", self.workflow)
        self.assertIn(
            'if [ "$EVENT_NAME" = "schedule" ]; then PROFILE="nightly_full"; fi',
            self.workflow,
        )
        nightly = self.profiles["profiles"]["nightly_full"]
        self.assertTrue(nightly["readinessBlocking"])
        self.assertTrue(nightly["deviceMatrix"]["requireAllPlatforms"])
        self.assertEqual(nightly["deviceMatrix"]["envs"], ["gamma"])

    def test_full_profile_has_bounded_managed_runtime_and_attestations(self) -> None:
        self.assertIn(
            "inputs.validation_profile == 'nightly_full' || "
            "inputs.validation_profile == 'release_candidate') && 20 || 10",
            self.workflow,
        )
        self.assertIn("name: Start stackctl-managed Gamma full runtime", self.workflow)
        self.assertIn(
            "steps.defaults.outputs.profile == 'nightly_full'",
            self.workflow,
        )
        self.assertIn(
            "name: Verify OIDC, manifest and complete artifact closure",
            self.workflow,
        )
        self.assertIn(
            "echo \"QWQ_RELEASE_ATTESTATION=${{ steps.release.outputs.pilot_release_path }}\"",
            self.workflow,
        )
        self.assertIn(
            "echo \"QWQ_ROLLBACK_RELEASE_ATTESTATION=${{ steps.release.outputs.pilot_rollback_path }}\"",
            self.workflow,
        )
        self.assertIn(
            'for attestation in "$QWQ_RELEASE_ATTESTATION" '
            '"$QWQ_ROLLBACK_RELEASE_ATTESTATION"',
            self.workflow,
        )
        self.assertIn(
            '[[ -z "$attestation" || ! -s "$attestation" ]]',
            self.workflow,
        )
        self.assertIn("--env gamma", self.workflow)
        self.assertIn(
            '--release-attestation "$QWQ_RELEASE_ATTESTATION"',
            self.workflow,
        )
        self.assertIn(
            '--rollback-release-attestation "$QWQ_ROLLBACK_RELEASE_ATTESTATION"',
            self.workflow,
        )
        self.assertIn("echo \"started=true\" >> \"$GITHUB_OUTPUT\"", self.workflow)

    def test_android_and_ios_are_independent_required_jobs(self) -> None:
        self.assertIn("android_device_matrix:\n    name: Android device matrix", self.workflow)
        self.assertIn("ios_device_matrix:\n    name: iOS device matrix", self.workflow)
        self.assertEqual(
            self.workflow.count("needs: beta_stack\n    if: ${{ needs.beta_stack.result == 'success' }}"),
            2,
        )
        self.assertIn(
            "needs: [beta_stack, android_device_matrix, ios_device_matrix]",
            self.workflow,
        )
        self.assertIn(
            "always() && vars.ENABLE_SELF_HOSTED_MOBILE_MATRIX == 'true'",
            self.workflow,
        )
        self.assertIn(
            "name: Require successful dual-platform job aggregation",
            self.workflow,
        )
        self.assertIn('test "$AGGREGATE" = success', self.workflow)
        self.assertIn("--has-android true", self.workflow)
        self.assertIn("--has-ios true", self.workflow)

    def test_managed_runtime_teardown_is_always_run_and_gate_visible(self) -> None:
        self.assertIn(
            "always() && (needs.beta_stack.outputs.formal_runtime_started == 'true' "
            "|| needs.beta_stack.outputs.managed_runtime_started == 'true')",
            self.workflow,
        )
        self.assertIn(
            "timeout-minutes: ${{ needs.beta_stack.outputs.managed_runtime_started == 'true' && 10 || 1 }}",
            self.workflow,
        )
        self.assertIn("name: Inspect and doctor the managed Gamma runtime after soak", self.workflow)
        self.assertIn("name: Verify and teardown only the Gamma runtime started here", self.workflow)
        self.assertIn("--target gamma-local", self.workflow)
        self.assertIn("--workload full", self.workflow)
        self.assertIn(
            'if [ "$MANAGED_RUNTIME_STARTED" = true ]; then test "$TEARDOWN" = success; fi',
            self.workflow,
        )
        self.assertIn(
            'if [ "$VALIDATION_PROFILE" = nightly_full ] && '
            '[ "$calendar_lead_time_seconds" -gt 7200 ]',
            self.workflow,
        )


if __name__ == "__main__":
    unittest.main()
