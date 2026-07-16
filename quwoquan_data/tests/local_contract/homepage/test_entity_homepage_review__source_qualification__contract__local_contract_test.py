"""Homepage review exposes execution-owned source qualification explicitly."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.homepage.homepage_review import _entity_review_payload  # noqa: E402


def test_entity_homepage_review__source_qualification__contract__local_contract() -> None:
    payload = _entity_review_payload(
        issues=[],
        source_paths=["1.download/sources/普陀山__wikipedia/source.md"],
        base_draft_exists=True,
    )

    assert payload["decision"] == "approved"
    assert payload["checks"]["sourceQualification"] == {"passed": True, "issues": []}


def test_entity_homepage_review__missing_source__contract__local_contract() -> None:
    payload = _entity_review_payload(
        issues=["base draft source missing"],
        source_paths=[],
        base_draft_exists=False,
    )

    assert payload["decision"] == "revision_needed"
    assert payload["fallbackStage"] == "needs_source_repair"
    assert payload["checks"]["sourceQualification"]["passed"] is False
