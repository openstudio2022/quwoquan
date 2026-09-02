"""Objective execution gate companion local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/objective-execution/spec.md#gwt-003.t3
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def test_objective_execution_gate_passes_current_single_track_policy() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/gate/verify_objective_execution.py"],
        cwd=ROOT, text=True, capture_output=True, check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert completed.returncode == 0, completed.stderr
    assert "contract/admission/CLI single-track verified" in completed.stdout


def test_thin_cli_projection_inspect_is_zero_mutation(tmp_path: Path) -> None:
    payload = '{"grant_projection_id":"projection-1","authenticated_authority":false,"executable":false}'
    completed = subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/cli/objective_execution.py", "projection-inspect"],
        cwd=ROOT, input=payload, text=True, capture_output=True, check=True,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert '"mutation_performed":false' in completed.stdout
    assert not (tmp_path / "journal").exists()


def test_gate_and_make_target_execute_both_behavior_suites() -> None:
    gate = (ROOT / "quwoquan_ops/gate/gate_repo.sh").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "python3 -B quwoquan_ops/gate/verify_objective_execution.py" in gate
    for path in (
        "quwoquan_ops/tests/local_contract/gate/test_objective_execution__journal_authority__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/gate/test_objective_execution__journal_security__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/gate/test_objective_execution__executor_admission__local_contract_test.py",
        "quwoquan_ops/tests/local_contract/gate/test_objective_execution__gate__local_contract_test.py",
    ):
        assert path in makefile
    assert "verify-objective-execution: prepare-test-python" in makefile


def test_gate_contract_loader_failure_is_canonical_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "verify_objective_execution_contract_failure",
        ROOT / "quwoquan_ops/gate/verify_objective_execution.py",
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "load_contract",
        lambda: (_ for _ in ()).throw(ValueError("descriptor invalid")),
    )

    assert module.main() == 1
    captured = capsys.readouterr()
    assert "code=OEX.CONTRACT_INVALID" in captured.err
    assert "terminal=blocked" in captured.err
    assert "recovery=repair_canonical_contract" in captured.err
    assert "descriptor invalid" in captured.err
    assert "emergency_contract_invalid_terminal" not in captured.err
    assert captured.err.count("recovery=") == 1
    assert "Traceback" not in captured.out + captured.err


def test_gate_blocked_admission_preserves_terminal_reason_and_recovery(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location
    from lib.objective_execution.contract import admission_readback, load_contract

    spec = spec_from_file_location(
        "verify_objective_execution_admission_failure",
        ROOT / "quwoquan_ops/gate/verify_objective_execution.py",
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    blocked = admission_readback("blocked", detail="first branch policy failure")
    monkeypatch.setattr(module, "inspect_admission", lambda: dict(blocked))

    assert module.main() == 1
    captured = capsys.readouterr()
    contract_descriptor = load_contract()["errors"]["OEX.ADMISSION_BLOCKED"]
    assert "code=OEX.ADMISSION_BLOCKED" in captured.err
    assert f"terminal={contract_descriptor['terminal']}" in captured.err
    assert f"reason={blocked['reason']}" in captured.err
    assert f"recovery={contract_descriptor['recovery']}" in captured.err
    assert captured.err.count("recovery=") == 1
    assert "Traceback" not in captured.out + captured.err


def test_gate_contract_failure_uses_objective_owned_emergency_helper(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "verify_objective_execution_owned_emergency",
        ROOT / "quwoquan_ops/gate/verify_objective_execution.py",
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    helper_calls: list[str] = []

    def emergency(detail: str) -> dict[str, str]:
        helper_calls.append(detail)
        return {
            "result": "typed_blocker",
            "code": "OEX.CONTRACT_INVALID",
            "terminal": "blocked",
            "recovery": "objective_owned_emergency_recovery",
            "detail": detail,
        }

    monkeypatch.setattr(module, "emergency_contract_invalid_terminal", emergency)
    monkeypatch.setattr(
        module,
        "load_contract",
        lambda: (_ for _ in ()).throw(OSError("canonical contract unreadable")),
    )

    assert module.main() == 1
    captured = capsys.readouterr()
    assert helper_calls == ["canonical contract unreadable"]
    assert "recovery=objective_owned_emergency_recovery" in captured.err
    assert captured.err.count("recovery=") == 1
    assert "Traceback" not in captured.out + captured.err


def test_gate_loaded_contract_projects_canonical_error_descriptors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location
    from lib.objective_execution.contract import load_contract

    spec = spec_from_file_location(
        "verify_objective_execution_canonical_projection",
        ROOT / "quwoquan_ops/gate/verify_objective_execution.py",
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = load_contract()
    descriptor = contract["errors"]["OEX.CONTRACT_INVALID"]
    monkeypatch.setattr(module, "load_contract", lambda: contract)
    monkeypatch.setattr(
        module,
        "admission_readback_contract",
        lambda: (_ for _ in ()).throw(RuntimeError("descriptor projection failed")),
    )

    assert module.main() == 1
    captured = capsys.readouterr()
    assert "code=OEX.CONTRACT_INVALID" in captured.err
    assert f"terminal={descriptor['terminal']}" in captured.err
    assert f"recovery={descriptor['recovery']}" in captured.err
    assert "descriptor projection failed" in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_gate_malformed_admission_is_contract_invalid_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "verify_objective_execution_malformed_admission",
        ROOT / "quwoquan_ops/gate/verify_objective_execution.py",
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "inspect_admission", lambda: {"status": "admitted"})

    assert module.main() == 1
    captured = capsys.readouterr()
    assert "code=OEX.CONTRACT_INVALID" in captured.err
    assert "code=OEX.ADMISSION_BLOCKED" not in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_gate_derives_admitted_values_from_public_descriptor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from copy import deepcopy
    from importlib.util import module_from_spec, spec_from_file_location
    from lib.objective_execution.contract import load_contract

    spec = spec_from_file_location(
        "verify_objective_execution_descriptor_derived_admission",
        ROOT / "quwoquan_ops/gate/verify_objective_execution.py",
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = deepcopy(load_contract())
    descriptor = contract["admission"]["readback_contract"]
    descriptor["statuses"]["admitted"]["write_concurrency"] = 7
    admission = {
        "status": "admitted",
        "stage": descriptor["stage"],
        "write_concurrency": 7,
        "persistent_lane_allowed": True,
        "branch_policy_digest": "sha256:" + "a" * 64,
        "reason": descriptor["statuses"]["admitted"]["reason"],
        "terminal": descriptor["statuses"]["admitted"]["terminal"],
    }
    monkeypatch.setattr(module, "load_contract", lambda: contract)
    monkeypatch.setattr(module, "admission_readback_contract", lambda: descriptor)
    monkeypatch.setattr(module, "inspect_admission", lambda: admission)
    monkeypatch.setattr(module, "validate_admission_readback", lambda value: dict(value))

    assert module.main() == 0
    captured = capsys.readouterr()
    assert "single-track verified" in captured.out
    assert captured.err == ""


def test_gate_source_does_not_duplicate_canonical_recovery_values() -> None:
    from lib.objective_execution.contract import load_contract

    source = (
        ROOT / "quwoquan_ops/gate/verify_objective_execution.py"
    ).read_text(encoding="utf-8")
    for descriptor in load_contract()["errors"].values():
        assert descriptor["recovery"] not in source
    assert "repair_canonical_contract" not in source
    assert "repair_branch_policy_or_keep_single_writer" not in source
    assert "temporary_branch_allowed" not in source
    assert "write_concurrency=2" not in source
