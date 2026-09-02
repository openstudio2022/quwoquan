"""HOTL contract, CLI, feature owner, and gate wiring local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md#gwt-003.t1
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "quwoquan_ops/cli") not in sys.path:
    sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.hotl_admission import ContractError, load_contract  # noqa: E402
from lib.objective_execution import contract as objective_contract_module  # noqa: E402
from lib.objective_execution.contract import admission_readback, admission_readback_contract  # noqa: E402
from lib.hotl_admission import contract as contract_module  # noqa: E402
from lib.hotl_admission.contract import validate_contract  # noqa: E402


def current_input() -> dict[str, Any]:
    return {
        "subject": {"subject_id": "subject-1", "scope_id": "scope-1", "action_id": "hotl-expansion"},
        "risk_tier": "R1", "requested_write_concurrency": 1,
        "authority_readback": None, "role_responsibility_proof": None,
        "cohort_proof": None, "checkpoint_policy": None, "control_proofs": [],
        "commercial_authority_readback": None, "activation_receipt": None,
    }


def run_cli(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/cli/hotl_admission.py", *args],
        cwd=ROOT, input=input_text, text=True, capture_output=True, check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(ROOT / ".qwq_output/env/repo/local/hotl-admission/cache/bytecode")},
    )


def test_contract_closed_sets_threshold_immutable_kinds_and_sources_are_frozen() -> None:
    contract = load_contract()
    assert contract["schema_id"] == "hotl-admission-contract"
    assert contract["schema_version"] == 1
    assert contract["closed_sets"]["risk_tier"] == ["R0", "R1", "R2", "R3", "R4"]
    assert contract["closed_sets"]["status"] == ["blocked", "not_admitted", "eligible_for_activation", "admitted"]
    assert "s4_readback" not in contract["schemas"]
    assert admission_readback_contract()["schema"] == "admission_readback"
    assert contract["admission_policy"]["coverage_threshold_basis_points"] == 9000
    assert isinstance(contract["admission_policy"]["coverage_threshold_basis_points"], int)
    assert contract["admission_policy"]["future_candidate_decision_kinds"] == ["routine_execution"]
    assert contract["admission_policy"]["allowed_authority_decision_kinds"] == ["delivery_authorization"]
    assert contract["admission_policy"]["objective_admission"] == {
        "dynamic_inspect_required": True,
        "readback_contract_required": True,
        "requested_concurrency_must_not_exceed_readback": True,
        "duplicated_admission_facts": "forbidden",
    }
    assert contract["admission_policy"]["current_fallback"] == {
        "status": "not_admitted", "allowed_mode": "manual",
        "checkpoint_reduction_allowed": False, "max_write_concurrency": 1,
        "grant_executable": False, "mutation_allowed": False,
    }
    immutable = set(contract["admission_policy"]["immutable_decision_kinds"])
    assert {"problem_acceptance", "product_scope", "experience_direction", "solution_risk", "delivery_authorization", "quality_uat_acceptance", "integration_acceptance", "artifact_acceptance", "nonproduction_acceptance", "commercial_readiness", "production_campaign_approval", "channel_publication", "outcome_acceptance", "knowledge_landing"} <= immutable
    assert contract["admission_policy"]["human_wait_sources"] == ["decision_requested", "decision_recorded"]
    assert contract["objective_admission_source"].endswith("#admission.readback_contract")
    priorities = contract["blocker_priority"]
    assert priorities[:3] == [
        "CANONICAL_CONTRACT_INVALID", "INPUT_CONTRACT_INVALID",
        "RISK_TIER_NOT_ELIGIBLE",
    ]
    objective_index = priorities.index("OBJECTIVE_ADMISSION_BLOCKED")
    assert priorities[objective_index:objective_index + 3] == [
        "OBJECTIVE_ADMISSION_BLOCKED", "EVALUATION_IDENTITY_FAILED",
        "REQUESTED_WRITE_CONCURRENCY_EXCEEDED",
    ]
    assert contract["errors"]["HOTL.CANONICAL_CONTRACT_INVALID"] == {
        "terminal": "blocked", "recovery": "repair_canonical_hotl_contract",
    }
    assert contract["errors"]["HOTL.OBJECTIVE_ADMISSION_BLOCKED"]["terminal"] == "blocked"
    assert contract["errors"]["HOTL.EVALUATION_IDENTITY_FAILED"] == {
        "terminal": "blocked",
        "recovery": "repair_evidence_fingerprint_contract_or_serializer",
    }
    start = priorities.index("CONTROL_ACK_READBACK_FAILED")
    assert priorities[start:start + 8] == [
        "CONTROL_ACK_READBACK_FAILED", "CONTROL_ACK_MISSING",
        "CONTROL_ACK_NOT_EXACT", "CONTROL_EFFECT_READBACK_FAILED",
        "CONTROL_EFFECT_READBACK_MISSING", "CONTROL_EFFECT_NOT_APPLIED",
        "CONTROL_EFFECT_NOT_INDEPENDENT", "CONTROL_IDENTITY_DRIFTED",
    ]
    raw = (ROOT / "quwoquan_ops/policies/hotl_admission_contract.yaml").read_text(encoding="utf-8")
    hotl_source_texts = [
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "quwoquan_ops/cli/lib/hotl_admission/contract.py",
            "quwoquan_ops/cli/lib/hotl_admission/evaluator.py",
        )
    ]
    contract_validation_source = hotl_source_texts[0][
        hotl_source_texts[0].index("def validate_contract"):
        hotl_source_texts[0].index("def _load_yaml_mapping")
    ]
    assert "load_objective_admission_readback_contract" not in hotl_source_texts[0]
    assert "objective_admission_readback_contract(" not in contract_validation_source
    assert all("_EMERGENCY_S4_FALLBACK" not in source for source in hotl_source_texts)
    assert "_EMERGENCY_FALLBACK" not in hotl_source_texts[1]
    hotl_string_literals = {
        node.value
        for source in hotl_source_texts
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    objective_descriptor = admission_readback_contract()
    forbidden_s4_values = {
        objective_descriptor["stage"],
        objective_descriptor["statuses"]["blocked"]["fallback_reason"],
        objective_descriptor["statuses"]["blocked"]["terminal"],
    }
    assert forbidden_s4_values.isdisjoint(hotl_string_literals)
    assert "allowed_local_branches" not in raw
    assert "pull_request_branch_prefixes" not in raw
    objective_descriptor = admission_readback_contract()
    duplicated_values = [
        descriptor["reason"]
        for descriptor in objective_descriptor["statuses"].values()
        if descriptor["reason_policy"] == "fixed"
    ] + [objective_descriptor["statuses"]["blocked"]["terminal"]]
    assert all(value not in raw for value in duplicated_values)


def test_contract_validation_rejects_schema_threshold_and_branch_policy_drift() -> None:
    contract = load_contract()
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["admission_policy"]["coverage_threshold_basis_points"] = 0.90
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["schemas"]["inspection_input"]["required_fields"].append("extra")
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["schemas"]["subject"]["required_fields"].remove("scope_id")
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    subject_fields = broken["schemas"]["subject"]["required_fields"]
    subject_fields[subject_fields.index("scope_id")] = "scope"
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["schemas"]["authority_readback"]["required_fields"].remove("decision_kind")
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["admission_policy"]["objective_admission"]["allowed_local_branches"] = ["dev1.0"]
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["admission_policy"]["objective_admission"]["reason"] = "fixture"
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["admission_policy"]["objective_admission"]["terminal"] = "blocked"
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["admission_policy"]["allowed_authority_decision_kinds"] = ["routine_execution"]
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["admission_policy"]["current_fallback"]["max_write_concurrency"] = 2
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["admission_policy"]["current_fallback"]["max_write_concurrency"] = True
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["admission_policy"]["current_fallback"]["unexpected"] = False
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["schemas"]["s4_readback"] = {
        "required_fields": list(admission_readback_contract()["statuses"]),
    }
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    broken["blocker_priority"].remove("AUTHORITY_READBACK_FAILED")
    with pytest.raises(ContractError):
        validate_contract(broken)
    broken = yaml.safe_load(yaml.safe_dump(contract))
    left = broken["blocker_priority"].index("CONTROL_ACK_READBACK_FAILED")
    right = broken["blocker_priority"].index("CONTROL_ACK_MISSING")
    broken["blocker_priority"][left], broken["blocker_priority"][right] = (
        broken["blocker_priority"][right], broken["blocker_priority"][left],
    )
    with pytest.raises(ContractError):
        validate_contract(broken)


def test_contract_loader_wraps_yaml_file_and_unicode_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_path = contract_module.CONTRACT_PATH
    try:
        malformed = tmp_path / "malformed.yaml"
        malformed.write_text("schema_id: [unterminated", encoding="utf-8")
        monkeypatch.setattr(contract_module, "CONTRACT_PATH", malformed)
        contract_module._load_contract_cached.cache_clear()
        with pytest.raises(ContractError):
            contract_module.load_contract()

        missing = tmp_path / "missing.yaml"
        monkeypatch.setattr(contract_module, "CONTRACT_PATH", missing)
        contract_module._load_contract_cached.cache_clear()
        with pytest.raises(ContractError):
            contract_module.load_contract()

        undecodable = tmp_path / "undecodable.yaml"
        undecodable.write_bytes(b"\xff\xfe\xfd")
        monkeypatch.setattr(contract_module, "CONTRACT_PATH", undecodable)
        contract_module._load_contract_cached.cache_clear()
        with pytest.raises(ContractError):
            contract_module.load_contract()
    finally:
        monkeypatch.setattr(contract_module, "CONTRACT_PATH", original_path)
        contract_module._load_contract_cached.cache_clear()


def test_objective_descriptor_loader_failure_is_inspect_only_and_uses_emergency_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location
    from lib.hotl_admission import evaluator as evaluator_module

    def descriptor_failure() -> dict[str, Any]:
        raise OSError("Objective descriptor loader failed")

    actual_provider = evaluator_module.inspect_admission
    actual_emergency_fallback = (
        evaluator_module.objective_emergency_blocked_s4_fallback
    )
    provider_call_count = 0
    emergency_fallback_call_count = 0

    def provider() -> dict[str, Any]:
        nonlocal provider_call_count
        provider_call_count += 1
        return actual_provider()

    def emergency_fallback() -> dict[str, Any]:
        nonlocal emergency_fallback_call_count
        emergency_fallback_call_count += 1
        return actual_emergency_fallback()

    monkeypatch.setattr(
        objective_contract_module, "admission_readback_contract", descriptor_failure,
    )
    monkeypatch.setattr(evaluator_module, "inspect_admission", provider)
    monkeypatch.setattr(
        evaluator_module, "objective_emergency_blocked_s4_fallback",
        emergency_fallback,
    )
    contract_module._load_contract_cached.cache_clear()

    loaded = load_contract()
    assert loaded["schema_id"] == "hotl-admission-contract"

    cli_spec = spec_from_file_location(
        "hotl_admission_cli_objective_descriptor_failure",
        ROOT / "quwoquan_ops/cli/hotl_admission.py",
    )
    assert cli_spec is not None and cli_spec.loader is not None
    cli = module_from_spec(cli_spec)
    cli_spec.loader.exec_module(cli)

    assert cli.main(["contract"]) == 0
    contract_output = capsys.readouterr()
    assert json.loads(contract_output.out)["schema_id"] == "hotl-admission-contract"
    assert "Traceback" not in contract_output.out + contract_output.err

    inspection_input = tmp_path / "inspection.json"
    inspection_input.write_text(json.dumps(current_input()), encoding="utf-8")
    assert cli.main(["inspect", "--input", str(inspection_input)]) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert provider_call_count == 1
    assert emergency_fallback_call_count == 1
    assert result["status"] == "blocked"
    assert result["result"] == "typed_blocker"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert "Objective descriptor loader failed" in result["detail"]
    assert result["s4_readback"] == objective_contract_module.emergency_blocked_admission_fallback()
    assert "Traceback" not in captured.out + captured.err


def test_cli_invalid_input_uses_canonical_fallback_and_contract_failure_is_minimal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location

    cli_spec = spec_from_file_location("hotl_admission_cli_contract_failure", ROOT / "quwoquan_ops/cli/hotl_admission.py")
    assert cli_spec is not None and cli_spec.loader is not None
    cli = module_from_spec(cli_spec)
    cli_spec.loader.exec_module(cli)

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text('{"subject":', encoding="utf-8")
    invalid_schema = current_input()
    del invalid_schema["subject"]["scope_id"]
    invalid_input = tmp_path / "invalid-input.json"
    invalid_input.write_text(json.dumps(invalid_schema), encoding="utf-8")
    for input_path in (invalid_json, invalid_input):
        assert cli.main(["inspect", "--input", str(input_path)]) == 2
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["status"] == "blocked"
        assert result["error_code"] == "HOTL.CONTRACT_INVALID"
        assert result["blockers"] == ["INPUT_CONTRACT_INVALID"]
        assert result["max_write_concurrency"] == 1
        assert result["mutation_allowed"] is False
        assert "Traceback" not in captured.out + captured.err

    malformed_contract = load_contract()
    malformed_contract["schemas"]["subject"]["required_fields"].remove("scope_id")
    malformed_path = tmp_path / "malformed-contract.yaml"
    malformed_path.write_text(yaml.safe_dump(malformed_contract, sort_keys=False), encoding="utf-8")
    original_path = contract_module.CONTRACT_PATH
    admission_fields = {
        "status", "allowed_mode", "checkpoint_reduction_allowed",
        "max_write_concurrency", "grant_executable", "mutation_allowed",
        "activation_required", "s4_readback", "subject", "risk_tier",
        "evaluation_digest", "evaluation_fingerprint_ref",
        "evaluation_bytes_sha256",
    }
    try:
        monkeypatch.setattr(contract_module, "CONTRACT_PATH", malformed_path)
        inspection_input = tmp_path / "inspection.json"
        inspection_input.write_text(json.dumps(current_input()), encoding="utf-8")
        for argv in (["contract"], ["inspect", "--input", str(inspection_input)]):
            contract_module._load_contract_cached.cache_clear()
            assert cli.main(argv) == 2
            captured = capsys.readouterr()
            result = json.loads(captured.out)
            assert result == {
                "result": "typed_blocker",
                "error_code": "HOTL.CANONICAL_CONTRACT_INVALID",
                "terminal": "blocked",
                "recovery": "repair_canonical_hotl_contract",
                "detail": result["detail"],
                "blockers": ["CANONICAL_CONTRACT_INVALID"],
            }
            assert "subject.required_fields drifted" in result["detail"]
            assert admission_fields.isdisjoint(result)
            assert "Traceback" not in captured.out + captured.err
    finally:
        monkeypatch.setattr(contract_module, "CONTRACT_PATH", original_path)
        contract_module._load_contract_cached.cache_clear()


@pytest.mark.parametrize(
    ("failure_kind", "expected_detail"),
    [
        ("validation", "stage must be S4"),
        ("provider", "Objective admission provider unavailable"),
    ],
)
def test_cli_s4_failure_returns_objective_typed_blocker_and_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], failure_kind: str, expected_detail: str,
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location

    valid = admission_readback(
        "admitted", branch_policy_digest="sha256:" + "a" * 64,
    )
    malformed = dict(valid)
    malformed["stage"] = "S3"
    readbacks = iter((malformed, valid))
    provider_call_count = 0

    def provider() -> dict[str, Any]:
        nonlocal provider_call_count
        provider_call_count += 1
        if failure_kind == "provider":
            raise OSError("Objective admission provider unavailable")
        return next(readbacks)

    monkeypatch.setattr(
        "lib.hotl_admission.evaluator.inspect_admission", provider,
    )
    cli_spec = spec_from_file_location(
        "hotl_admission_cli_malformed_s4", ROOT / "quwoquan_ops/cli/hotl_admission.py",
    )
    assert cli_spec is not None and cli_spec.loader is not None
    cli = module_from_spec(cli_spec)
    cli_spec.loader.exec_module(cli)
    inspection_input = tmp_path / "inspection.json"
    inspection_input.write_text(json.dumps(current_input()), encoding="utf-8")

    assert cli.main(["inspect", "--input", str(inspection_input)]) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert provider_call_count == 1
    assert result["status"] == "blocked"
    assert result["result"] == "typed_blocker"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert expected_detail in result["detail"]
    assert result["max_write_concurrency"] == 1
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False
    assert result["s4_readback"] == admission_readback("blocked")
    assert "Traceback" not in captured.out + captured.err


def test_cli_canonical_blocked_s4_is_typed_and_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location
    from lib.hotl_admission import evaluator as evaluator_module

    blocked_s4 = admission_readback(
        "blocked", detail="canonical branch policy unavailable",
    )
    provider_call_count = 0

    def provider() -> dict[str, Any]:
        nonlocal provider_call_count
        provider_call_count += 1
        return dict(blocked_s4)

    monkeypatch.setattr(evaluator_module, "inspect_admission", provider)
    cli_spec = spec_from_file_location(
        "hotl_admission_cli_canonical_blocked_s4",
        ROOT / "quwoquan_ops/cli/hotl_admission.py",
    )
    assert cli_spec is not None and cli_spec.loader is not None
    cli = module_from_spec(cli_spec)
    cli_spec.loader.exec_module(cli)
    inspection_input = tmp_path / "blocked-s4.json"
    inspection_input.write_text(json.dumps(current_input()), encoding="utf-8")

    assert cli.main(["inspect", "--input", str(inspection_input)]) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert provider_call_count == 1
    assert result["status"] == "blocked"
    assert result["result"] == "typed_blocker"
    assert result["error_code"] == "HOTL.OBJECTIVE_ADMISSION_BLOCKED"
    assert result["blockers"] == ["OBJECTIVE_ADMISSION_BLOCKED"]
    assert result["detail"] == blocked_s4["reason"]
    assert result["s4_readback"] == blocked_s4
    assert "Traceback" not in captured.out + captured.err


@pytest.mark.parametrize(
    "dependency_name",
    ["canonical_json_bytes", "canonical_digest", "fingerprint_ref"],
)
def test_cli_evidence_fingerprint_dependency_failure_is_typed_blocked_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str], dependency_name: str,
) -> None:
    from importlib.util import module_from_spec, spec_from_file_location
    from lib.hotl_admission import evaluator as evaluator_module

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(f"{dependency_name} dependency failed")

    expected_s4 = evaluator_module.inspect_admission()
    provider_call_count = 0

    def provider() -> dict[str, Any]:
        nonlocal provider_call_count
        provider_call_count += 1
        return dict(expected_s4)

    monkeypatch.setattr(evaluator_module, "inspect_admission", provider)
    monkeypatch.setattr(evaluator_module, dependency_name, fail)
    cli_spec = spec_from_file_location(
        f"hotl_admission_cli_{dependency_name}_failure",
        ROOT / "quwoquan_ops/cli/hotl_admission.py",
    )
    assert cli_spec is not None and cli_spec.loader is not None
    cli = module_from_spec(cli_spec)
    cli_spec.loader.exec_module(cli)
    inspection_input = tmp_path / f"{dependency_name}.json"
    inspection_input.write_text(json.dumps(current_input()), encoding="utf-8")

    assert cli.main(["inspect", "--input", str(inspection_input)]) == 2
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert provider_call_count == 1
    assert result["status"] == "blocked"
    assert result["result"] == "typed_blocker"
    assert result["error_code"] == "HOTL.EVALUATION_IDENTITY_FAILED"
    assert result["blockers"] == ["EVALUATION_IDENTITY_FAILED"]
    assert dependency_name in result["detail"]
    assert "dependency failed" in result["detail"]
    assert result["max_write_concurrency"] == 1
    assert result["grant_executable"] is False
    assert result["mutation_allowed"] is False
    assert "Traceback" not in captured.out + captured.err

def test_cli_contract_and_inspect_are_deterministic_and_invalid_input_has_no_traceback() -> None:
    first = run_cli("contract")
    second = run_cli("contract")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["schema_id"] == "hotl-admission-contract"

    payload = json.dumps(current_input(), ensure_ascii=False, sort_keys=True)
    first = run_cli("inspect", "--input", "-", input_text=payload)
    second = run_cli("inspect", "--input", "-", input_text=payload)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["status"] == "not_admitted"
    assert first.stderr == ""

    invalid = run_cli("inspect", "--input", "-", input_text='{"subject":')
    assert invalid.returncode != 0
    parsed = json.loads(invalid.stdout)
    assert parsed["status"] == "blocked"
    assert parsed["error_code"] == "HOTL.CONTRACT_INVALID"
    assert "INPUT_CONTRACT_INVALID" in parsed["blockers"]
    assert "Traceback" not in invalid.stdout + invalid.stderr


def test_feature_spec_open_dependencies_cli_surface_and_gate_are_wired() -> None:
    story = ROOT / "specs/feature-tree/runtime/development-workflow-governance/hotl-expansion-control/spec.md"
    assert story.exists()
    text = story.read_text(encoding="utf-8")
    assert all(f"<a id=\"req-00{index}\"></a>" in text for index in (1, 2, 3))
    assert all(f"<a id=\"gwt-00{index}\"></a>" in text for index in (1, 2, 3))
    for dependency in (
        "human-agent-delivery-interaction/spec.md#open-001", "human-agent-delivery-interaction/spec.md#open-002",
        "human-agent-delivery-interaction/spec.md#open-003", "objective-execution/spec.md#open-001",
        "objective-execution/spec.md#open-002", "gray-release-to-prod/spec.md#open-003",
        "gray-release-to-prod/spec.md#open-004", "gray-release-to-prod/spec.md#open-005",
    ):
        assert dependency in text
    cli = (ROOT / "quwoquan_ops/cli/hotl_admission.py").read_text(encoding="utf-8")
    parser_region = cli[cli.index("def build_parser"):cli.index("def _emit")]
    assert parser_region.count("add_parser(") == 2
    assert 'add_parser("contract")' in parser_region
    assert 'add_parser("inspect")' in parser_region
    gate = subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/gate/verify_hotl_admission.py"], cwd=ROOT,
        text=True, capture_output=True, check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(ROOT / ".qwq_output/env/repo/local/hotl-admission/cache/bytecode")},
    )
    assert gate.returncode == 0, gate.stderr
    assert "current fail-closed admission verified" in gate.stdout
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    repo_gate = (ROOT / "quwoquan_ops/gate/gate_repo.sh").read_text(encoding="utf-8")
    assert "verify-hotl-admission: prepare-test-python" in makefile
    assert "python3 -B quwoquan_ops/gate/verify_hotl_admission.py" in repo_gate
    assert "test_hotl_admission__contract__local_contract_test.py" in makefile
    assert "test_hotl_admission__evaluator__local_contract_test.py" in makefile


def _load_hotl_gate_module(name: str):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        name, ROOT / "quwoquan_ops/gate/verify_hotl_admission.py",
    )
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hotl_gate_contract_loader_failure_is_minimal_canonical_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_hotl_gate_module("verify_hotl_contract_failure")
    monkeypatch.setattr(
        module,
        "load_contract",
        lambda: (_ for _ in ()).throw(OSError("HOTL contract unavailable")),
    )

    assert module.main() == 1
    captured = capsys.readouterr()
    assert "code=HOTL.CANONICAL_CONTRACT_INVALID" in captured.err
    assert "terminal=blocked" in captured.err
    assert "recovery=repair_canonical_hotl_contract" in captured.err
    assert "HOTL contract unavailable" in captured.err
    assert captured.err.count("recovery=") == 1
    assert "status=" not in captured.err
    assert "allowed_mode=" not in captured.err
    assert "max_write_concurrency=" not in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_hotl_gate_objective_admission_failure_projects_canonical_recovery(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_hotl_gate_module("verify_hotl_objective_failure")
    contract = load_contract()
    from lib.objective_execution.contract import admission_readback

    blocked_s4 = admission_readback("blocked", detail="first Objective admission failure")
    readback = dict(contract["admission_policy"]["current_fallback"])
    readback.update({
        "status": "blocked",
        "detail": "first Objective admission failure",
        "error_code": "HOTL.OBJECTIVE_ADMISSION_BLOCKED",
        "blockers": ["OBJECTIVE_ADMISSION_BLOCKED"],
        "activation_required": True,
        "s4_readback": blocked_s4,
    })
    monkeypatch.setattr(module, "inspect", lambda _payload: dict(readback))

    assert module.main() == 1
    captured = capsys.readouterr()
    assert "code=HOTL.OBJECTIVE_ADMISSION_BLOCKED" in captured.err
    assert "terminal=blocked" in captured.err
    assert "recovery=keep_single_writer_and_reinspect_dynamic_s4" in captured.err
    assert "first Objective admission failure" in captured.err
    assert captured.err.count("recovery=") == 1
    assert "Traceback" not in captured.out + captured.err


def test_hotl_gate_current_blockers_emit_unique_canonical_recovery_tokens() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/gate/verify_hotl_admission.py"],
        cwd=ROOT, text=True, capture_output=True, check=False,
        env={
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(
                ROOT / ".qwq_output/env/repo/local/hotl-admission/cache/bytecode"
            ),
        },
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    lines = [
        line for line in completed.stdout.splitlines()
        if "EXPECTED_BLOCKER" in line
    ]
    assert lines
    assert all(line.count("recovery=") == 1 for line in lines)
    # 当前 lane 生命周期政策下动态 S4 为 admitted，write expansion blocker 不得在场。
    assert not any("blocker=WRITE_EXPANSION_NOT_ADMITTED" in line for line in lines)
    assert any("blocker=AUTHORITY_PROVIDER_UNAVAILABLE" in line for line in lines)
    assert all("code=HOTL." in line and "terminal=" in line for line in lines)
    assert "Traceback" not in completed.stdout + completed.stderr
