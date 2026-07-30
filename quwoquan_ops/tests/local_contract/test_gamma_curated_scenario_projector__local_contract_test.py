from __future__ import annotations

import json
import unittest
from pathlib import Path

from quwoquan_ops.tests.support.environment_seeds import (
    sync_gamma_curated_scenarios as projector,
)


ROOT = Path(__file__).resolve().parents[3]


class GammaCuratedScenarioProjectorContractTest(unittest.TestCase):
    def test_manifest_is_read_only_and_all_derived_domains_are_current(self) -> None:
        manifest_path = ROOT / projector.MANIFEST_RELATIVE_PATH
        before = manifest_path.read_bytes()
        specs = projector.load_projection_specs(root=ROOT)
        outputs = projector.build_projection_outputs(root=ROOT)
        self.assertEqual(
            {spec.domain for spec in specs},
            projector.EXPECTED_DERIVED_DOMAINS,
        )
        self.assertEqual(projector.stale_destinations(outputs, root=ROOT), ())
        self.assertEqual(manifest_path.read_bytes(), before)

    def test_entity_projection_uses_manifest_selection(self) -> None:
        manifest = json.loads(
            (ROOT / projector.MANIFEST_RELATIVE_PATH).read_text(encoding="utf-8")
        )
        entry = next(item for item in manifest["seedRefs"] if item["domain"] == "entity")
        expected_homepages = entry["curation"]["homepageIds"]
        expected_picker = entry["curation"]["pickerHomepageIds"]
        output = next(
            item
            for item in projector.build_projection_outputs(root=ROOT)
            if item.spec.domain == "entity"
        )
        payload = json.loads(output.raw)
        actual_homepages = [
            item["homepageId"]
            for item in payload["seedSets"]["entity_homepage_core"]["homepages"]
        ]
        self.assertEqual(set(actual_homepages), set(expected_homepages))
        self.assertEqual(len(actual_homepages), len(expected_homepages))
        self.assertEqual(
            payload["seedSets"]["entity_picker_core"]["candidateHomepageIds"],
            expected_picker,
        )

    def test_media_bundle_and_manifest_writer_are_retired(self) -> None:
        self.assertFalse(
            (
                ROOT
                / "quwoquan_service/services/content-service/environments/gamma/"
                "resources/artifacts/media/gamma_curated_media_bundle.json"
            ).exists()
        )
        source = Path(projector.__file__).read_text(encoding="utf-8")
        self.assertNotIn("GAMMA_MEDIA_BUNDLE", source)
        self.assertNotIn("write_json(GAMMA_MANIFEST", source)


if __name__ == "__main__":
    unittest.main()
