from __future__ import annotations

from pathlib import Path

from quwoquan_ops.tests.local_contract.observability.test_observability_contract__local_contract_test import (
    test_repo_gate_materializes_real_canonical_observability_before_validation as _assert_repo_gate_run,
)


def test_coverage_materializes_a_real_repo_gate_run(tmp_path: Path) -> None:
    _assert_repo_gate_run(tmp_path)
