from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "quwoquan_app/scripts/runtime/verify_content_page_funnel_coverage.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_content_page_funnel_coverage",
    SCRIPT,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载 {SCRIPT}")
coverage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage
SPEC.loader.exec_module(coverage)


class ContentPageFunnelCoverageTest(unittest.TestCase):
    def test_repository_content_funnels_are_closed(self) -> None:
        funnels = coverage.verify_content_page_funnels()

        self.assertEqual(
            {funnel.journey for funnel in funnels},
            {"content_share", "profile_interaction"},
        )

    def test_missing_failure_dimension_is_blocked(self) -> None:
        contract = yaml.safe_load(
            coverage.PAGE_CONTRACT.read_text(encoding="utf-8")
        )
        changed = False
        for page in contract["pages"]:
            for funnel in page["telemetry_descriptor"].get(
                "product_actions", []
            ):
                if funnel["journey"] == "content_share":
                    funnel["required_dimensions"].remove("traceId")
                    changed = True
        self.assertTrue(changed)

        with tempfile.TemporaryDirectory() as directory:
            contract_path = Path(directory) / "page_object_contract.yaml"
            contract_path.write_text(
                yaml.safe_dump(contract, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "required_dimensions"):
                coverage.verify_content_page_funnels(
                    page_contract=contract_path
                )


if __name__ == "__main__":
    unittest.main()
