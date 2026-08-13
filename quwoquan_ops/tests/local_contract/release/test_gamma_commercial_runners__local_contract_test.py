from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from quwoquan_ops.cli import stackctl


ROOT = Path(__file__).resolve().parents[4]
SUITES_PATH = ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"


class GammaCommercialRunnersLocalContractTest(unittest.TestCase):
    def test_service_verify_reports_are_partitioned_by_service_and_profile(
        self,
    ) -> None:
        assistant = stackctl._service_verify_report_action(
            "verify",
            "assistant-service",
            stackctl.VerificationProfile.INTEGRATION,
        )
        user = stackctl._service_verify_report_action(
            "verify",
            "user-service",
            stackctl.VerificationProfile.INTEGRATION,
        )

        self.assertEqual(
            assistant,
            "verify-assistant-service-integration",
        )
        self.assertEqual(user, "verify-user-service-integration")
        self.assertNotEqual(assistant, user)

    def test_reliabletask_runner_owns_real_gamma_dependencies_and_receipt(self) -> None:
        suites = json.loads(SUITES_PATH.read_text(encoding="utf-8"))
        case = suites["smokeCases"]["reliabletask_gamma_api_integration"]
        runner = ROOT / case["path"]
        source = runner.read_text(encoding="utf-8")

        self.assertEqual(case["runner"], "bash")
        self.assertIn("stackctl.py", source)
        self.assertIn("health --target gamma-local --scope full", source)
        self.assertIn("--profile gamma-local --format json", source)
        self.assertIn('TEST_MONGO_URI="$mongo_uri"', source)
        self.assertIn('TEST_REDIS_ADDR="$redis_addr"', source)
        self.assertIn("test-runtime-api-integration", source)
        self.assertIn('"status": "passed" if int(exit_code) == 0 else "failed"', source)
        self.assertNotIn("|| true", source)

    def test_onboarding_impact_runners_execute_api_and_both_device_journeys(
        self,
    ) -> None:
        suites = json.loads(SUITES_PATH.read_text(encoding="utf-8"))
        case = suites["smokeCases"][
            "onboarding_author_impact_gamma_api_integration"
        ]
        api_runner = (ROOT / case["path"]).read_text(encoding="utf-8")
        device_runner = (
            ROOT
            / "quwoquan_app/scripts/tools/gamma/onboarding_author_impact_uat.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("health --target", api_runner)
        self.assertIn("run_local_gamma_release_consumer_api.py", api_runner)
        self.assertIn("QWQ_TEST_DATA_ACCESS_TOKEN", api_runner)
        self.assertNotIn("open_reference_acceptance_session", api_runner)
        self.assertIn(
            "test/api_integration/service/content_service/content/content_behavior_fact/"
            "onboarding_interest_gamma__api_integration_test.dart",
            api_runner,
        )
        self.assertIn(
            "test/api_integration/service/content_service/content/post/"
            "author_impact_gamma__api_integration_test.dart",
            api_runner,
        )
        self.assertNotIn(
            "onboarding_author_impact_gamma__api_integration_test.dart",
            api_runner,
        )
        self.assertIn(
            "interest_onboarding__user_acceptance_test.dart",
            device_runner,
        )
        self.assertIn("profile_journey__user_acceptance_test.dart", device_runner)
        self.assertIn('"patrolAuthorImpactJourney"', device_runner)
        self.assertNotIn("|| true", api_runner)
        self.assertNotIn("|| true", device_runner)

    def test_release_profile_executes_gamma_commercial_api_runners(
        self,
    ) -> None:
        report_dir = ROOT / ".qwq_output/test-gamma-commercial-profile"
        commands = stackctl._selected_profile_commands(
            "gamma",
            "gamma-local",
            stackctl.VerificationProfile.RELEASE,
            report_dir,
        )
        command_by_name = {command["name"]: command for command in commands}

        reliabletask = command_by_name[
            "gamma-local-reliabletask-api-integration"
        ]
        self.assertEqual(
            reliabletask["argv"],
            [
                "bash",
                "quwoquan_ops/cli/gamma/"
                "run_reliabletask_gamma_api_integration.sh",
                "--reuse-stack",
            ],
        )
        self.assertTrue(reliabletask["stopOnFailure"])
        self.assertEqual(
            reliabletask["env"]["QWQ_RUN_ROOT"],
            str(report_dir / "reliabletask-gamma-api-integration"),
        )

        onboarding = command_by_name[
            "gamma-local-onboarding-author-impact-api-integration"
        ]
        self.assertEqual(
            onboarding["argv"],
            [
                "bash",
                "quwoquan_app/scripts/gamma/"
                "run_local_gamma_onboarding_author_impact_api_uat.sh",
            ],
        )
        self.assertTrue(onboarding["stopOnFailure"])
        self.assertEqual(
            onboarding["env"]["QWQ_RUN_ROOT"],
            str(report_dir / "onboarding-author-impact-gamma-api-integration"),
        )

        integration_names = {
            command["name"]
            for command in stackctl._selected_profile_commands(
                "gamma",
                "gamma-local",
                stackctl.VerificationProfile.INTEGRATION,
                report_dir,
            )
        }
        self.assertNotIn(
            "gamma-local-reliabletask-api-integration",
            integration_names,
        )
        self.assertNotIn(
            "gamma-local-onboarding-author-impact-api-integration",
            integration_names,
        )

    def test_assistant_service_profile_runs_only_generated_learning_remote_evidence(
        self,
    ) -> None:
        report_dir = ROOT / ".qwq_output/test-gamma-assistant-profile"
        commands = stackctl._selected_profile_commands(
            "gamma",
            "gamma-local",
            stackctl.VerificationProfile.INTEGRATION,
            report_dir,
            service="assistant-service",
        )
        self.assertEqual(
            [command["name"] for command in commands],
            [
                "gamma-local-health-preflight",
                "gamma-local-assistant-learning-remote-api-integration",
            ],
        )
        assistant = commands[1]
        self.assertEqual(
            assistant["argv"],
            [
                "bash",
                "quwoquan_app/scripts/gamma/"
                "run_local_gamma_assistant_learning_api_uat.sh",
            ],
        )
        self.assertTrue(assistant["stopOnFailure"])
        runner = (ROOT / assistant["argv"][1]).read_text(encoding="utf-8")
        self.assertIn("QWQ_TEST_DATA_ACCESS_TOKEN", runner)
        self.assertNotIn("open_reference_acceptance_session", runner)
        self.assertIn(
            "assistant_learning_remote_roundtrip__api_integration_test.dart",
            runner,
        )
        self.assertIn("events.assistant.learning_facts", runner)
        self.assertIn("assistant_learning_fact_outbox", runner)
        self.assertIn('"durableOutboxRelay"', runner)
        self.assertNotIn("|| true", runner)

    def test_user_service_profile_runs_profile_proposal_remote_evidence(
        self,
    ) -> None:
        report_dir = ROOT / ".qwq_output/test-gamma-user-profile"
        commands = stackctl._selected_profile_commands(
            "gamma",
            "gamma-local",
            stackctl.VerificationProfile.INTEGRATION,
            report_dir,
            service="user-service",
        )
        self.assertEqual(
            [command["name"] for command in commands],
            [
                "gamma-local-health-preflight",
                "gamma-local-profile-proposal-remote-api-integration",
            ],
        )
        proposal = commands[1]
        self.assertEqual(
            proposal["argv"],
            [
                "bash",
                "quwoquan_app/scripts/gamma/"
                "run_local_gamma_profile_proposal_api_uat.sh",
            ],
        )
        self.assertTrue(proposal["stopOnFailure"])
        runner = (ROOT / proposal["argv"][1]).read_text(encoding="utf-8")
        self.assertIn("QWQ_TEST_DATA_ACCESS_TOKEN", runner)
        self.assertNotIn("open_reference_acceptance_session", runner)
        self.assertIn(
            "profile_update_proposal_remote_roundtrip__api_integration_test.dart",
            runner,
        )
        self.assertIn("events.user.profile_update_proposal", runner)
        self.assertIn("profile_update_proposals_outbox", runner)
        self.assertIn('"durableOutboxRelay"', runner)
        self.assertNotIn("|| true", runner)


if __name__ == "__main__":
    unittest.main()
