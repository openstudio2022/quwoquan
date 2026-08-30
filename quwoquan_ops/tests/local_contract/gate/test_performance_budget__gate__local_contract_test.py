from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCAFFOLD = ROOT / "quwoquan_ops/gate/scaffold"
if str(SCAFFOLD) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD))


def test_performance_budget_static_contract_accepts_current_wiring() -> None:
    gate = importlib.import_module("verify_performance_budget")
    failures = gate.Failures()
    gate._verify_static_contract(failures)
    assert failures.items == []


def test_performance_budget_static_contract_rejects_missing_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    gate = importlib.import_module("verify_performance_budget")
    artifact_gate = tmp_path / "artifact_gate.py"
    evidence_test = tmp_path / "evidence_test.py"
    artifact_gate.write_text("# intentionally incomplete\n", encoding="utf-8")
    evidence_test.write_text("# intentionally incomplete\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ARTIFACT_GATE", artifact_gate)
    monkeypatch.setattr(gate, "EVIDENCE_TEST", evidence_test)

    failures = gate.Failures()
    gate._verify_static_contract(failures)
    assert any("missing tested field" in issue for issue in failures.items)
