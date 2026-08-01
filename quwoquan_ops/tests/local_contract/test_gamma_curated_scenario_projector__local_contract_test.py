from __future__ import annotations

import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.nonprod_business_data import (
    NONPROD_PAGING_BOUNDARY,
    NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC,
    NONPROD_REFERENCE_CIRCLE_CHAT,
    NONPROD_REFERENCE_CONTENT_INTERACTION,
    NONPROD_REFERENCE_IDENTITY,
    NONPROD_RELIABILITY_RECOVERY,
)


ROOT = Path(__file__).resolve().parents[3]


class GammaCuratedScenarioProjectorRetirementContractTest(unittest.TestCase):
    def test_static_gamma_projector_and_seed_support_are_retired(self) -> None:
        self.assertFalse((ROOT / "quwoquan_ops/tests/support/environment_seeds").exists())
        self.assertFalse(
            (
                ROOT
                / "quwoquan_app/configs/gamma/app_gamma_seed_manifest.json"
            ).exists()
        )

    def test_gamma_media_bundle_is_retired(self) -> None:
        self.assertFalse(
            (
                ROOT
                / "quwoquan_service/services/content-service/environments/gamma/"
                "resources/artifacts/media/gamma_curated_media_bundle.json"
            ).exists()
        )

    def test_typed_recipes_replace_static_gamma_projection(self) -> None:
        self.assertEqual(
            {
                NONPROD_REFERENCE_IDENTITY.dataset_id,
                NONPROD_REFERENCE_CONTENT_INTERACTION.dataset_id,
                NONPROD_REFERENCE_CIRCLE_CHAT.dataset_id,
                NONPROD_REFERENCE_ASSISTANT_NOTIFICATION_RTC.dataset_id,
                NONPROD_PAGING_BOUNDARY.dataset_id,
                NONPROD_RELIABILITY_RECOVERY.dataset_id,
            },
            {
                "nonprod_reference_identity",
                "nonprod_reference_content_interaction",
                "nonprod_reference_circle_chat",
                "nonprod_reference_assistant_notification_rtc",
                "nonprod_paging_boundary",
                "nonprod_reliability_recovery",
            },
        )


if __name__ == "__main__":
    unittest.main()
