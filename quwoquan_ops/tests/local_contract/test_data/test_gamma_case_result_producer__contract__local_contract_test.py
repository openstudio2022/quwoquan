"""Gamma raw CaseResult producer migrated to canonical App runtime contract.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""

from __future__ import annotations

from pathlib import Path


def test_gamma_case_result_producer_has_single_canonical_contract_suite() -> None:
    root = Path(__file__).resolve().parents[4]
    suite = (
        root
        / "quwoquan_app/test/local_contract/runtime/"
        "gamma_readiness_case_result__local_contract_test.py"
    )
    assert suite.is_file()
    source = (
        root / "quwoquan_app/scripts/gamma/gamma_case_result.py"
    ).read_text(encoding="utf-8")
    assert "quwoquan.test.case-result" not in source
    assert '"gate_block"' not in source
    assert "validate_readiness_case_result" in source
    assert "write_create_once_json" in source
