from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "quwoquan_ops" / "gate" / "scaffold" / "verify_test_specs.py"


def _load_gate():
    script_dir = str(SCRIPT.parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    spec = importlib.util.spec_from_file_location("verify_test_specs_contract", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载门禁：{SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_planned_file_must_exist(tmp_path: Path) -> None:
    gate = _load_gate()
    gate.ROOT = tmp_path
    acceptance = tmp_path / "specs" / "feature-tree" / "demo" / "acceptance.yaml"
    acceptance.parent.mkdir(parents=True)
    acceptance.write_text("version: 2\n", encoding="utf-8")

    failures = gate.FailureCollector()
    gate.validate_test_ref(
        acceptance,
        "gwt_acceptance.GWT1",
        {"file": "tests/missing__contract__local_contract_test.py"},
        failures,
        bucket_name="planned",
    )

    assert failures.failures == [
        "specs/feature-tree/demo/acceptance.yaml gwt_acceptance.GWT1 "
        "planned file missing: tests/missing__contract__local_contract_test.py"
    ]


def test_planned_existing_file_is_accepted(tmp_path: Path) -> None:
    gate = _load_gate()
    gate.ROOT = tmp_path
    acceptance = tmp_path / "specs" / "feature-tree" / "demo" / "acceptance.yaml"
    acceptance.parent.mkdir(parents=True)
    acceptance.write_text("version: 2\n", encoding="utf-8")
    relative_test_file = (
        "quwoquan_ops/tests/local_contract/"
        "test_existing__contract__local_contract_test.py"
    )
    test_file = tmp_path / relative_test_file
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_contract():\n    assert True\n", encoding="utf-8")

    failures = gate.FailureCollector()
    gate.validate_test_ref(
        acceptance,
        "gwt_acceptance.GWT1",
        {"file": relative_test_file},
        failures,
        bucket_name="planned",
    )

    assert failures.failures == []


def test_indexed_acceptance_disappearance_is_not_silenced(tmp_path: Path) -> None:
    gate = _load_gate()
    gate.ROOT = tmp_path
    missing = tmp_path / "specs" / "feature-tree" / "removed" / "acceptance.yaml"
    failures = gate.FailureCollector()

    assert gate.load_yaml(missing, failures) == {}
    assert len(failures.failures) == 1
    assert "cannot be parsed as YAML" in failures.failures[0]
