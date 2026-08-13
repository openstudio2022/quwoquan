from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
PROFILES = ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"


class AppEnvDeviceMatrixWorkflowContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.profiles = json.loads(PROFILES.read_text(encoding="utf-8"))

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
            "inputs.validation_profile == 'release_candidate') && 20 || 2",
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
