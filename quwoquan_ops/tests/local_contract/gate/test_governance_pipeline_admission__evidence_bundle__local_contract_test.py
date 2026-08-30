"""Governance evidence bundle producer/adapters anti-forgery contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-003.t1
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.governance_pipeline_admission import (  # noqa: E402
    assemble_evidence_bundle, current_repository_input, inspect, load_contract,
    subject_fingerprint, subject_fingerprint_receipt,
)
from lib.governance_pipeline_admission import adapters  # noqa: E402
from lib.governance_pipeline_admission.contract import ContractError  # noqa: E402
from lib.governance_pipeline_admission.evidence import _assert_layer_policy, _named_receipts  # noqa: E402
from lib.governance_pipeline_admission.read_only_local_readiness import verify_explicit_receipt_read_only  # noqa: E402
from lib.objective_execution.contract import admission_readback  # noqa: E402
from lib.human_agent_delivery import summarize_calibration_sessions  # noqa: E402
from lib.human_agent_delivery.calibration import _canonical_bytes  # noqa: E402

RUN_ROOT = ROOT / ".qwq_output/env/repo/runs/governance-pipeline/tests"


def write_receipt(case: Path, name: str, value: object) -> str:
    path = RUN_ROOT / case.name / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))
    return path.relative_to(ROOT).as_posix()


def empty_refs() -> dict[str, Any]:
    return {"named_evidence": {}, "external": {}}


def test_bundle_producer_freezes_exact_refs_and_managed_drift_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = load_contract()
    raw_ref = write_receipt(tmp_path, "external.json", {"opaque": "provider-owned"})
    refs = empty_refs()
    refs["external"]["prod"] = raw_ref
    path = assemble_evidence_bundle(contract, run_id=f"tests/{tmp_path.name}".replace("/", "-"), refs=refs)
    bundle = json.loads(path.read_text())
    frozen = bundle["receipts"]["external"]["prod"]
    assert frozen["receipt_ref"] == raw_ref
    assert frozen["exact_bytes_base64"]
    assert bundle["subject_fingerprint"] == bundle["subject_fingerprint_receipt"]["digest"]
    managed = ROOT / "quwoquan_ops/cli/lib/governance_pipeline_admission/adapters.py"
    original = managed.read_bytes()
    monkeypatch.setattr(adapters, "REPO_ROOT", ROOT)
    try:
        managed.write_bytes(original + b"\n")
        with pytest.raises(ContractError, match="managed source fingerprint stale"):
            current_repository_input(contract, evidence_bundle=path)
    finally:
        managed.write_bytes(original)


def test_locally_resigned_external_receipt_is_rejected_without_real_verifier(tmp_path: Path) -> None:
    contract = load_contract()
    ref = write_receipt(tmp_path, "commercial.json", {"passed": True, "provider_kind": "authenticated_external"})
    refs = empty_refs()
    refs["external"]["commercial"] = ref
    path = assemble_evidence_bundle(contract, run_id=f"forged-{tmp_path.name}", refs=refs)
    payload = current_repository_input(contract, evidence_bundle=path)
    item = payload["evidence"]["commercial"]
    assert item["status"] == "failed"
    assert item["schema_valid"] is False
    assert "external verifier unavailable" in item["detail"]
    result = inspect(payload)
    assert result["status"] == "blocked"
    assert result["blockers"][0] == "EVIDENCE_SCHEMA_INVALID"


@pytest.mark.parametrize(
    ("layer", "provider", "release"),
    [
        ("portal_test", "local_runtime", False),
        ("hosted_authority_code", "hosted_code", False),
        ("hosted_authority_integration", "authenticated_external", True),
        ("commercial", "authenticated_external", True),
        ("prod", "authenticated_external", True),
        ("hotl_inspect", "local_runtime", False),
    ],
)
def test_per_layer_provider_matrix_is_exact(layer: str, provider: str, release: bool) -> None:
    policy = load_contract()["layer_admission"][layer]
    assert provider in policy["provider_kinds"]
    assert policy["release_evidence_eligible"] is release
    if release:
        assert policy["interface"] == "external"


def test_forged_named_workspace_or_toolchain_receipt_is_rejected(tmp_path: Path) -> None:
    contract = load_contract()
    forged = {
        "schema_version": 1, "plan_fingerprint_ref": "forged", "plan_fingerprint_digest": "sha256:" + "0" * 64,
        "execution_fingerprint": {}, "result_fingerprint": {}, "evidence": [],
        "terminal": {"status": "PASS", "code": "EVIDENCE.PASSED", "failed_evidence": None},
        "captured_by": "caller", "started_at": "2026-08-30T00:00:00+00:00", "finished_at": "2026-08-30T00:01:00+00:00",
    }
    ref = write_receipt(tmp_path, "named.json", forged)
    refs = empty_refs()
    refs["named_evidence"]["portal-test"] = ref
    path = assemble_evidence_bundle(contract, run_id=f"named-{tmp_path.name}", refs=refs)
    bundle = json.loads(path.read_text())
    subject = {"candidate_id": "working-tree", "scope_id": "governance-pipeline"}
    projected = _named_receipts(
        bundle, contract, subject=subject,
        now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    assert projected["portal_test"]["status"] == "failed"
    assert projected["portal_test"]["schema_valid"] is False


def test_stale_and_bad_timestamp_are_rejected() -> None:
    contract = load_contract()
    subject = {"candidate_id": "c", "scope_id": "s"}
    readback = adapters._readback(
        result="present", provider_kind="local_runtime", release=False,
        receipt_ref=".qwq_output/x", raw=b"x", provider_timestamp="2000-01-01T00:00:00+00:00",
        candidate_id="c", scope_id="s", verifier_id=contract["layer_admission"]["objective_readback"]["verifier_id"],
    )
    checked = _assert_layer_policy(readback, layer="objective_readback", subject=subject, contract=contract, now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    assert checked["fresh"] is False
    bad = copy.deepcopy(readback)
    bad["provider_timestamp"] = "2026-08-30T00:00:00"
    checked = _assert_layer_policy(bad, layer="objective_readback", subject=subject, contract=contract, now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    assert checked["fresh"] is False


def snapshot(root: Path) -> list[tuple[str, int, int]]:
    if not root.exists():
        return []
    return sorted((path.relative_to(root).as_posix(), path.stat().st_mode, path.stat().st_size) for path in root.rglob("*"))


def test_local_readiness_adapter_never_creates_or_chmods_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = tmp_path / "must-remain-absent"
    monkeypatch.setenv("QWQ_LOCAL_READINESS_ROOT", str(state))
    receipt = tmp_path / "by-fingerprint" / ("0" * 64 + ".json")
    receipt.parent.mkdir()
    receipt.write_text("{}", encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(ContractError):
        verify_explicit_receipt_read_only(
            level="scope", receipt_path=receipt, exact_bytes=b"{}", paths=["AGENTS.md"],
            mode="workspace", owner_manifest_path=tmp_path / "manifest.json", repo_root=ROOT,
        )
    assert snapshot(tmp_path) == before
    assert not state.exists()


def test_objective_and_hosted_source_adapter_local_boundaries() -> None:
    contract = load_contract()
    objective = adapters.produce_objective_bytes()
    readback = adapters.objective_readback(
        raw=objective, receipt_ref=".qwq_output/objective.json", candidate_id="c", scope_id="s", contract=contract,
    )
    assert readback["provider_kind"] == "local_runtime"
    hosted = adapters.produce_hosted_source_bytes(contract)
    source = adapters.verify_hosted_source(
        raw=hosted, receipt_ref=".qwq_output/hosted.json", candidate_id="c", scope_id="s", contract=contract,
    )
    assert source["result"] in {"code_pass", "code_absent"}
    tampered = json.loads(hosted)
    tampered["snapshots"][0]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ContractError, match="source bytes drifted"):
        adapters.verify_hosted_source(raw=canonical_json_bytes(tampered), receipt_ref=".qwq_output/hosted.json", candidate_id="c", scope_id="s", contract=contract)


def test_hotl_and_handoff_adapter_negative_boundaries() -> None:
    contract = load_contract()
    unsafe_hotl = canonical_json_bytes({
        "provider_timestamp": "2026-08-30T00:00:00+00:00",
        "readback": {"allowed_mode": "hotl", "mutation_allowed": True, "grant_executable": True, "max_write_concurrency": 2},
    })
    readback = adapters.verify_hotl(raw=unsafe_hotl, receipt_ref=".qwq_output/hotl.json", candidate_id="c", scope_id="s", contract=contract)
    assert readback["result"] == "absent"
    with pytest.raises(Exception):
        adapters.verify_handoff(raw=b"{}", receipt_ref=".qwq_output/handoff.json", candidate_id="c", scope_id="s", contract=contract)


def test_human_readback_consumes_exact_owner_v2_and_rejects_v1_or_digest_drift() -> None:
    contract = load_contract()
    from lib.human_agent_delivery import load_contract as load_human_contract
    human = load_human_contract(); model = human["calibration_model"]
    dimensions = human["closed_sets"]["human_calibration_observation_dimension"]
    sessions = []
    for principal, responsibilities in model["principal_responsibility_mapping"].items():
        sessions.append({
            "schema_version": 2, "contract_version": model["contract_version"],
            "role_model_version": model["role_model_version"], "observation_model_version": model["observation_model_version"],
            "session_id": f"calibration-{principal.replace('_', '-')}", "principal_class": principal,
            "participant_ref": f"participant-{principal.replace('_', '-')}",
            "scope": {"decision_unit_id": "decision-unit-governance", "task_id": f"task-{principal}", "evidence_fingerprint": "sha256:" + "a" * 64, "responsibility_classes": responsibilities},
            "started_at": "2026-08-30T00:00:00+00:00", "completed_at": "2026-08-30T00:30:00+00:00",
            "source_assurance": {"source_kind": "human_participant", "authentication_provider_ref": "provider", "participant_authenticated": True, "consent_obtained": True, "consent_recorded_at": "2026-08-29T23:59:00+00:00", "direct_identifiers_removed": True, "free_text_excluded": True, "observer_attested": True},
            "separation_policy": "role-record-only",
            "observations": [{"observation_id": f"observation-{index+1}", "dimension": dimension, "observed_at": "2026-08-30T00:10:00+00:00", "outcome": "demonstrated", "responsibility_classes": responsibilities} for index, dimension in enumerate(dimensions)],
        })
    now = __import__("datetime").datetime(2026, 8, 30, 1, 0, tzinfo=__import__("datetime").timezone.utc)
    payload = summarize_calibration_sessions(sessions, now=now)
    by_id = {item["session_id"]: _canonical_bytes(item) for item in sessions}
    session_bytes = {ref["ref"]: by_id[ref["session_id"]] for ref in payload["session_refs"]}
    raw = canonical_json_bytes(payload)
    def verifier(request: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider_id": "human_calibration_readback_v2", "provider_kind": "authenticated_external",
            "authenticated": True, "exact_bytes_verified": True, "release_evidence_eligible": True,
            "candidate_id": "c", "scope_id": "s", "evidence_fingerprint": "sha256:" + "a" * 64,
            "result": "calibrated", "provider_timestamp": payload["generated_at"],
            "receipt_bytes_sha256": "sha256:" + __import__("hashlib").sha256(raw).hexdigest(),
            "verifier_id": "governance.human_calibration.v2",
        }
    readback, exact = adapters.verify_human_readback(
        raw=raw, receipt_ref=".qwq_output/human.json", candidate_id="c", scope_id="s",
        evidence_fingerprint="sha256:" + "a" * 64, session_bytes_by_ref=session_bytes,
        provider_timestamp=payload["generated_at"], verifier=verifier, contract=contract,
    )
    assert exact["status"] == "calibrated"
    assert readback["provider_kind"] == "authenticated_external"
    assert readback["release_evidence_eligible"] is True
    v1 = {"schema_version": 1, "status": "observed"}
    with pytest.raises(ContractError, match="HAD.CALIBRATION_CONTRACT_INCOMPATIBLE"):
        adapters.verify_human_readback(raw=canonical_json_bytes(v1), receipt_ref=".qwq_output/human.json", candidate_id="c", scope_id="s", evidence_fingerprint="sha256:" + "a" * 64, session_bytes_by_ref={}, provider_timestamp=payload["generated_at"], verifier=verifier, contract=contract)
    drift = dict(session_bytes); first = next(iter(drift)); drift[first] += b" "
    with pytest.raises(ContractError, match="HAD.CALIBRATION_CONTRACT_INCOMPATIBLE"):
        adapters.verify_human_readback(raw=canonical_json_bytes(payload), receipt_ref=".qwq_output/human.json", candidate_id="c", scope_id="s", evidence_fingerprint="sha256:" + "a" * 64, session_bytes_by_ref=drift, provider_timestamp=payload["generated_at"], verifier=verifier, contract=contract)


def test_review_gate_block_finding_is_defensively_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = load_contract()
    consolidation = {"terminal": {"status": "PASS", "codes": []}, "reviewer_results": [], "findings": [{"severity": "GATE_BLOCK"}]}
    monkeypatch.setattr("review_consolidator.consolidate", lambda *_args, **_kwargs: consolidation)
    with pytest.raises(ContractError, match="GATE_BLOCK finding"):
        adapters.verify_review(
            plan_raw=b"{}", plan_ref="p", evidence_raw=canonical_json_bytes({"finished_at": "2026-08-30T00:00:00+00:00"}), evidence_ref="e",
            consolidation_raw=canonical_json_bytes(consolidation), consolidation_ref="c", candidate_id="c", scope_id="s", contract=contract,
        )
