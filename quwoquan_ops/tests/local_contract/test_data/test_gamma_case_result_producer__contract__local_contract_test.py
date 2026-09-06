"""Gamma raw CaseResult producer uses the canonical runtime contract suite.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""

from __future__ import annotations

from pathlib import Path


def test_gamma_case_result_producer_has_single_canonical_contract_suite() -> None:
    root = Path(__file__).resolve().parents[4]
    canonical_suite = (
        root
        / "quwoquan_app/test/local_contract/runtime/"
        "readiness_case_result__local_contract_test.py"
    )
    retired_suite = (
        root
        / "quwoquan_app/test/local_contract/runtime/"
        "gamma_readiness_case_result__local_contract_test.py"
    )
    assert canonical_suite.is_file()
    assert not retired_suite.exists()

    source = (
        root / "quwoquan_app/scripts/gamma/gamma_case_result.py"
    ).read_text(encoding="utf-8")
    assert "quwoquan.test.case-result" not in source
    assert '"gate_block"' not in source
    assert "validate_readiness_case_result" in source
    assert "build_readiness_result_bundle" in source
    assert "write_create_once_json" in source
