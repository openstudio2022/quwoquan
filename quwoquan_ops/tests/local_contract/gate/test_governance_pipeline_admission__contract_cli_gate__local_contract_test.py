"""Governance pipeline contract, CLI, gate, metrics, and OPEN honesty contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-003.t2
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.governance_pipeline_admission import contract as contract_module  # noqa: E402
from lib.governance_pipeline_admission import load_contract  # noqa: E402
from lib.governance_pipeline_admission.contract import (  # noqa: E402
    ContractError,
    validate_contract,
    validate_named_evidence_plan_binding,
)


def run(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/cli/governance_pipeline_admission.py", *args],
        cwd=ROOT, input=input_text, text=True, capture_output=True, check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(ROOT / ".qwq_output/env/repo/local/governance-pipeline/cache/bytecode")},
    )


def test_contract_owns_real_sources_required_evidence_and_zero_mutation() -> None:
    contract = load_contract()
    assert contract["closed_sets"]["admission_status"] == ["blocked", "not_admitted", "eligible_observe_only", "observe_only"]
    serialized = yaml.safe_dump(contract, sort_keys=False)
    assert "production_ready" in contract["schemas"]["inspection_result"]["required_fields"]
    assert "commercial_ready" in contract["schemas"]["inspection_result"]["required_fields"]
    assert "admitted" not in contract["closed_sets"]["admission_status"]
    hosted = contract["hosted_authority_source"]
    assert hosted["service_contract_refs"]
    assert hosted["adapter_implementation_refs"]
    assert hosted["service_implementation_refs"]
    assert hosted["portal_implementation_refs"]
    assert "status" not in hosted
    assert contract["activation_authority_source"] == {"provider_ref": None, "local_inspect_may_activate": False}
    assert all(value is False for value in contract["authority_boundaries"].values())
    assert contract["admission_policy"]["current_max_write_concurrency"] == 1
    assert contract["admission_policy"]["objective_s4_upper_bound"] == 1
    assert contract["admission_policy"]["observe_only_requires_all_evidence_layers"] is True
    assert "handoff_freshness" in contract["evidence_layers"]
    assert set(contract["layer_admission"]) == set(contract["evidence_layers"])
    assert len(contract["evidence_layers"]) == 26
    assert next(iter(contract["evidence_layers"])) == "owner_manifest"
    assert contract["schemas"]["evidence_bundle_receipts"]["required_fields"][0] == "owner_manifest"
    assert contract["layer_admission"]["owner_manifest"]["provider_id"] == "feature_context_owner_identity_v4"
    assert contract["current_repository_evidence"]["provider_adapters"]["owner_manifest"]["provider_id"] == "feature_context_owner_identity_v4"
    assert "feature_context_manifest_v2" not in serialized
    assert contract["layer_admission"]["prod"]["provider_kinds"] == ["authenticated_external"]
    assert contract["layer_admission"]["portal_test"]["release_evidence_eligible"] is False
    assert contract["human_calibration_policy"]["owner_contract_version"] == 2
    assert contract["human_calibration_policy"]["governance_may_recompute_human_semantics"] is False
    assert contract["layer_admission"]["human_calibration"]["provider_id"] == "human_calibration_readback_v2"
    assert contract["admission_policy"]["external_effects"]["unknown_outcome"] == "pending"
    assert contract["admission_policy"]["external_effects"]["retry_unknown"] is False
    assert "production_ready_claim: false" in serialized
    assert "commercial_ready_claim: false" in serialized
    assert "hotl_admitted_claim: false" in serialized


def test_contract_rejects_status_concurrency_activation_and_metric_drift() -> None:
    contract = load_contract()
    for mutate in (
        lambda value: value["closed_sets"]["admission_status"].append("production_ready"),
        lambda value: value["admission_policy"].update(objective_s4_upper_bound=2),
        lambda value: value["admission_policy"]["activation"].update(provider_available=True),
        lambda value: value["hosted_authority_source"].update(service_contract_refs=[]),
        lambda value: value["observation_metrics"]["definitions"][0]["dimensions"].append("prompt"),
        lambda value: value["current_repository_evidence"]["named_evidence_plan_binding"]["subject"].update(candidate_id="forged"),
    ):
        broken = yaml.safe_load(yaml.safe_dump(contract))
        mutate(broken)
        with pytest.raises(ContractError):
            validate_contract(broken)



def test_required_named_evidence_cross_contract_closure(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = load_contract()
    registry = yaml.safe_load(
        (ROOT / ".agents/skills/review/references/registry.yaml").read_text(encoding="utf-8")
    )
    required_ids = [
        descriptor["evidence_id"]
        for descriptor in contract["current_repository_evidence"]["named_evidence_layers"].values()
    ]
    assert required_ids == ["portal-test", "portal-build"]
    assert len(required_ids) == len(set(required_ids))
    for evidence_id in required_ids:
        assert registry["evidence"][evidence_id]["segment"] == "POST"
        assert registry["evidence"][evidence_id]["required"] is True

    duplicate = yaml.safe_load(yaml.safe_dump(contract))
    duplicate["current_repository_evidence"]["named_evidence_layers"]["portal_build"]["evidence_id"] = "portal-test"
    with pytest.raises(ContractError, match="unique"):
        validate_contract(duplicate)

    missing = yaml.safe_load(yaml.safe_dump(registry))
    missing["evidence"].pop("portal-build")
    monkeypatch.setattr(contract_module.yaml, "safe_load", lambda _raw: missing)
    with pytest.raises(ContractError, match="portal-build"):
        validate_contract(contract)

def test_named_evidence_requires_current_exact_plan_and_governance_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = load_contract()
    binding = contract["current_repository_evidence"]["named_evidence_plan_binding"]
    assert binding["registry_ref"] == ".agents/skills/review/references/registry.yaml"
    assert binding["subject"] == {
        "subject_id": "current-repository",
        "candidate_id": "working-tree",
        "scope_id": "governance-pipeline",
    }
    current = {
        "ref": "evidence-fingerprint-v1:sha256:" + "1" * 64,
        "digest": "sha256:" + "1" * 64,
    }
    plan = {
        "workflow": binding["workflow"],
        "segment": binding["segment"],
        "deliverable": binding["deliverable"],
        "scope": binding["scope"],
        "owner_identity": {
            "ref": "current-owner-manifest.json",
            "target": binding["owner_manifest_target"],
            "resolved_owner": binding["owner_manifest_target"],
            "scope": binding["scope"],
        },
        "candidate_evidence_identity": {"ref": "candidate.json"},
        "fingerprint_receipt": dict(current),
    }
    receipt = {
        "plan_fingerprint_ref": current["ref"],
        "plan_fingerprint_digest": current["digest"],
        "evidence_class": "reusable",
        "admission_eligible": True,
        "evidence": [{"id": "portal-test", "exit_code": 0}],
        "terminal": {
            "status": "PASS",
            "code": "EVIDENCE.PASSED",
            "failed_evidence": None,
        },
    }
    subject = dict(binding["subject"])
    monkeypatch.setattr(
        "review_dispatch.validate_current_review_plan",
        lambda value, registry, phase: current,
    )
    monkeypatch.setattr(
        "handoff_consumer.validate_named_evidence_ref_payload",
        lambda value, plan, registry, label, **_kwargs: value,
    )
    assert validate_named_evidence_plan_binding(
        plan=plan, receipt=receipt, subject=subject,
        expected_owner_identity_ref="current-owner-manifest.json",
        expected_candidate_evidence_ref="candidate.json", contract=contract,
    ) is receipt

    other_plan_receipt = dict(receipt)
    other_plan_receipt["plan_fingerprint_ref"] = (
        "evidence-fingerprint-v1:sha256:" + "2" * 64
    )
    other_plan_receipt["plan_fingerprint_digest"] = "sha256:" + "2" * 64
    with pytest.raises(ContractError, match="different exact Review plan"):
        validate_named_evidence_plan_binding(
            plan=plan, receipt=other_plan_receipt, subject=subject,
            expected_owner_identity_ref="current-owner-manifest.json",
            expected_candidate_evidence_ref="candidate.json", contract=contract,
        )

    other_candidate = dict(subject)
    other_candidate["candidate_id"] = "another-fresh-candidate"
    with pytest.raises(ContractError, match="candidate_id mismatch"):
        validate_named_evidence_plan_binding(
            plan=plan, receipt=receipt, subject=other_candidate,
            expected_owner_identity_ref="current-owner-manifest.json",
            expected_candidate_evidence_ref="candidate.json", contract=contract,
        )


def test_observation_metric_contract_is_complete_shape_only_and_no_prompt_pii() -> None:
    contract = load_contract()
    metrics = contract["observation_metrics"]
    ids = {item["metric_id"] for item in metrics["definitions"]}
    assert ids == {
        "governance_edit_latency_ms", "governance_idle_latency_ms", "governance_scope_latency_ms",
        "governance_release_latency_ms", "governance_cache_hit_ratio", "governance_deferred_age_ms",
        "governance_commit_freshness_ms", "governance_hosted_mismatch_total",
        "governance_authority_wait_ms", "governance_authority_transfer_total", "governance_authority_timeout_total",
        "governance_review_incomplete_total", "governance_handoff_stale_total",
        "governance_objective_pending_total", "governance_objective_revoke_total",
    }
    forbidden = set(metrics["forbidden_dimensions"])
    assert all(not (set(item["dimensions"]) & forbidden) for item in metrics["definitions"])
    assert all(item["sensitive_fields"] == [] for item in metrics["definitions"])
    evaluator = (ROOT / "quwoquan_ops/cli/lib/governance_pipeline_admission/evaluator.py").read_text(encoding="utf-8")
    assert "observation_metrics" in evaluator
    assert "prometheus" not in evaluator.lower()
    assert "emit_metric" not in evaluator


def test_cli_contract_is_deterministic_and_invalid_json_is_typed_without_traceback() -> None:
    left = run("contract")
    right = run("contract")
    assert left.returncode == right.returncode == 0
    assert left.stdout == right.stdout
    assert json.loads(left.stdout)["schema_id"] == "governance-pipeline-admission-contract"
    invalid = run("inspect", "--input", "-", input_text='{"subject":')
    assert invalid.returncode == 2
    result = json.loads(invalid.stdout)
    assert result["status"] == "blocked"
    assert result["error_code"] == "GPA.INPUT_CONTRACT_INVALID"
    assert result["blockers"] == ["INPUT_CONTRACT_INVALID"]
    assert result["production_ready"] is False
    assert result["commercial_ready"] is False
    assert result["hotl_admitted"] is False
    assert result["mutation_allowed"] is False
    assert "Traceback" not in invalid.stdout + invalid.stderr


def test_contract_loader_failure_is_minimal_typed_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    malformed = tmp_path / "contract.yaml"
    malformed.write_text("schema_id: [", encoding="utf-8")
    original = contract_module.CONTRACT_PATH
    try:
        monkeypatch.setattr(contract_module, "CONTRACT_PATH", malformed)
        contract_module._load_cached.cache_clear()
        with pytest.raises(ContractError):
            contract_module.load_contract()
    finally:
        monkeypatch.setattr(contract_module, "CONTRACT_PATH", original)
        contract_module._load_cached.cache_clear()


def test_gate_reports_expected_terminal_without_wrapping_external_blocker_as_pass() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/gate/verify_governance_pipeline_admission.py"],
        cwd=ROOT, text=True, capture_output=True, check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(ROOT / ".qwq_output/env/repo/local/governance-pipeline/cache/bytecode")},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "EVALUATOR_SELF_CHECK_ONLY_NON_ADMISSION" in completed.stdout
    assert "no bundle supplied" in completed.stdout
    assert "GATE_PASS" not in completed.stdout
    assert "production_ready=true" not in completed.stdout
    assert "commercial_ready=true" not in completed.stdout
    assert "hotl_admitted=true" not in completed.stdout
    assert "Traceback" not in completed.stdout + completed.stderr


def test_gate_with_structurally_blocked_bundle_fails() -> None:
    from lib.governance_pipeline_admission import assemble_evidence_bundle
    contract = load_contract()
    path = assemble_evidence_bundle(
        contract, run_id=f"gate-{uuid4().hex}", refs={"named_evidence": {}, "external": {}},
    )
    completed = subprocess.run(
        [sys.executable, "-B", "quwoquan_ops/gate/verify_governance_pipeline_admission.py", "--evidence-bundle", str(path)],
        cwd=ROOT, text=True, capture_output=True, check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(ROOT / ".qwq_output/env/repo/local/governance-pipeline/cache/bytecode")},
    )
    assert completed.returncode == 1
    assert "GATE_BLOCK" in completed.stderr
    assert "GPA.EVIDENCE_IDENTITY_BLOCKED" in completed.stderr


def test_story_preserves_external_open_and_binds_current_owner_evidence() -> None:
    story = (ROOT / "specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md").read_text(encoding="utf-8")
    assert all(f'<a id="gwt-00{index}"></a>' in story for index in (1, 2, 3))
    assert all(f'<a id="open-00{index}"></a>' in story for index in (1, 2, 3))
    assert "owner manifest exact ref" in story
    assert "固定 current pointer" in story
    assert "不得声明" in story or "不证明" in story
