# spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SUITES_PATH = ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"
WORKFLOW_PATH = ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
PLATFORM_WORKFLOW_PATH = ROOT / ".github/workflows/beta-device-platform.yml"
MATRIX_RUNNER_PATH = ROOT / "quwoquan_ops/ci/run_mobile_platform_matrix.sh"
GAMMA_RUNNER_PATH = ROOT / "quwoquan_app/scripts/gamma/run_local_gamma_device_uat.sh"
UAT_PATH = ROOT / (
    "quwoquan_app/test/user_acceptance/journeys/account_closure/"
    "account_closure_journey__user_acceptance_test.dart"
)


class AccountClosureGammaPatrolMatrixContractTest(unittest.TestCase):
    def test_release_profiles_schedule_registered_account_closure_journey(
        self,
    ) -> None:
        suites = json.loads(SUITES_PATH.read_text(encoding="utf-8"))
        journey = suites["uiJourneys"]["account_closure_patrol"]

        self.assertEqual(journey["runner"], "patrol")
        self.assertEqual(journey["tier"], "release")
        target = str(journey["target"]).strip()
        self.assertTrue(target)
        self.assertTrue((ROOT / "quwoquan_app" / target).is_file())

        for profile_name in ("nightly_full", "release_candidate"):
            profile = suites["profiles"][profile_name]
            self.assertIn("account_closure_patrol", profile["uiJourneys"])
            self.assertIn(
                "account-closure",
                profile["deviceMatrix"]["matrixKinds"],
            )

    def test_self_hosted_matrix_uses_unique_disposable_install_identity(
        self,
    ) -> None:
        workflow = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (WORKFLOW_PATH, PLATFORM_WORKFLOW_PATH, MATRIX_RUNNER_PATH)
        )
        gamma_runner = GAMMA_RUNNER_PATH.read_text(encoding="utf-8")

        self.assertIn(
            '[[ "$matrix_kind" == "account-closure" ]]',
            workflow,
        )
        self.assertIn(
            "resolve_patrol_target account_closure_patrol",
            workflow,
        )
        self.assertIn("run_local_gamma_device_uat.sh", workflow)
        self.assertIn(
            'closure_install_id="account-closure-',
            workflow,
        )
        self.assertIn("-{device}\"", workflow)
        self.assertIn(
            '--patrol-install-id "$closure_install_id"',
            workflow,
        )
        self.assertIn(
            'ACCOUNT_CLOSURE_DISPOSABLE_ACK:-}" != "true"',
            workflow,
        )
        self.assertIn(
            'ACCOUNT_CLOSURE_PROD_DEVICE_ID:-}"',
            workflow,
        )
        self.assertIn(
            '[[ "$ACCOUNT_CLOSURE_PROD_DEVICE_ID" != "$MOBILE_DEVICE_ID" ]]',
            workflow,
        )
        self.assertIn('--device-id "$MOBILE_DEVICE_ID"', workflow)
        self.assertIn(
            "prod_closure_selected_platform_seen",
            workflow,
        )
        self.assertIn("--account-closure-disposable-ack", workflow)
        self.assertIn("environment:", workflow)
        self.assertIn("'production'", workflow)
        self.assertIn("--patrol-install-id", gamma_runner)
        self.assertIn(
            'cmd+=(--patrol-install-id "$PATROL_INSTALL_ID")',
            gamma_runner,
        )

    def test_uat_proves_refresh_and_old_access_are_rejected(self) -> None:
        source = UAT_PATH.read_text(encoding="utf-8")

        self.assertIn("RefreshTokenCommand", source)
        self.assertIn("_FixedAccessTokenProvider", source)
        self.assertIn("USER.AUTH.account_deleted", source)
        self.assertIn("USER.AUTH.token_stale", source)
        self.assertIn("AuthSessionStatus.guest", source)


if __name__ == "__main__":
    unittest.main()
