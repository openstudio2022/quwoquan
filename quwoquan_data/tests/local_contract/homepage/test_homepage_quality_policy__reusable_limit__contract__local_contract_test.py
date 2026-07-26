"""Homepage fidelity limits come from the reusable vertical policy, never code literals."""
from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.homepage.quality_policy import homepage_source_fidelity_limit  # noqa: E402
from governance.content_supply_policy import load_content_supply_policy  # noqa: E402


def test_homepage_source_fidelity_limit__uses_execution_vertical_policy__local_contract() -> None:
    execution_id = "20260722--travel-homepage-generate--test-region-a--pilot-001"

    assert homepage_source_fidelity_limit(execution_id) == (
        load_content_supply_policy("travel").homepage_max_source_fidelity
    )
