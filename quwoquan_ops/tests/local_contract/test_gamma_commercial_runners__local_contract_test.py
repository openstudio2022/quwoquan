from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
SUITES_PATH = ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"


class GammaCommercialRunnersLocalContractTest(unittest.TestCase):
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
            / "quwoquan_app/scripts/gamma/run_local_gamma_onboarding_author_impact_uat.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("health --target", api_runner)
        self.assertIn("run_local_gamma_t3.py", api_runner)
        self.assertIn("open_local_acceptance_session", api_runner)
        self.assertIn(
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


if __name__ == "__main__":
    unittest.main()
