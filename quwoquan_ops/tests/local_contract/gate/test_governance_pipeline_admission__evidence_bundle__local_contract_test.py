"""Governance evidence bundle producer/adapters anti-forgery contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/governance-pipeline-observe-only/spec.md#gwt-003.t1
"""
from __future__ import annotations

import copy
import json
import os
import sys
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.candidate_evidence import build_candidate_evidence  # noqa: E402
import evidence_runner  # noqa: E402
import review_dispatch  # noqa: E402
from lib.governance_pipeline_admission import (  # noqa: E402
    adapters,
    assemble_evidence_bundle,
    current_repository_input,
    inspect,
    load_contract,
    subject_fingerprint,
    subject_fingerprint_receipt,
)
from lib.governance_pipeline_admission import evidence as evidence_module  # noqa: E402
from lib.governance_pipeline_admission.contract import (  # noqa: E402
    ContractError,
    EvidenceAdapterError,
)
from lib.governance_pipeline_admission.evidence import (  # noqa: E402
    _assert_layer_policy,
    _named_receipts,
)
from lib.governance_pipeline_admission.read_only_local_readiness import (
    verify_explicit_receipt_read_only,  # noqa: E402
)
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


def run_id(tmp_path: Path, prefix: str) -> str:
    digest = __import__("hashlib").sha256(str(tmp_path).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{tmp_path.name}-{digest}"


def test_bundle_producer_freezes_exact_refs_and_managed_drift_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    contract = load_contract()
    raw_ref = write_receipt(tmp_path, "external.json", {"opaque": "provider-owned"})
    refs = empty_refs()
    refs["external"]["prod"] = raw_ref
    path = assemble_evidence_bundle(contract, run_id=run_id(tmp_path, "tests"), refs=refs)
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
        payload = current_repository_input(contract, evidence_bundle=path)
        result = inspect(payload)
        assert result["blockers"][0] == "EVIDENCE_STALE"
    finally:
        managed.write_bytes(original)


def test_bundle_run_root_rejects_root_and_intermediate_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = load_contract()
    outside = tmp_path / "outside"
    outside.mkdir()
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    monkeypatch.setattr(evidence_module, "REPO_ROOT", fake_repo)
    root = fake_repo / contract["current_repository_evidence"]["evidence_bundle_root"]
    root.parent.mkdir(parents=True)
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ContractError, match="run root is unsafe"):
        evidence_module._canonical_run_root_fd(contract, create=True)

    root.unlink()
    root.mkdir()
    root_fd = evidence_module._canonical_run_root_fd(contract, create=False)
    try:
        (root / "middle").symlink_to(outside, target_is_directory=True)
        with pytest.raises(ContractError, match="run directory is unsafe"):
            evidence_module._run_directory_fd(root_fd, "middle", create=False)
    finally:
        os.close(root_fd)


def test_bundle_run_root_rejects_in_repo_redirect_and_replacement_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = load_contract()
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir()
    monkeypatch.setattr(evidence_module, "REPO_ROOT", fake_repo)
    root = fake_repo / contract["current_repository_evidence"]["evidence_bundle_root"]
    root.parent.mkdir(parents=True)
    redirect = fake_repo / ".qwq_output/env/repo/runs/redirect"
    redirect.mkdir(parents=True)
    root.symlink_to(redirect, target_is_directory=True)
    with pytest.raises(ContractError, match="run root is unsafe"):
        evidence_module._canonical_run_root_fd(contract, create=True)

    root.unlink()
    root.mkdir()
    root_fd = evidence_module._canonical_run_root_fd(contract, create=False)
    run_fd = evidence_module._run_directory_fd(root_fd, "replace-race", create=True)
    try:
        root_stat = os.fstat(root_fd)
        run_stat = os.fstat(run_fd)
        file_stat = evidence_module._write_bundle_create_once(run_fd, b"{}")
    finally:
        os.close(run_fd)
        os.close(root_fd)
    moved = root.with_name(root.name + "-moved")
    root.rename(moved)
    root.mkdir()
    with pytest.raises(ContractError, match="run root was replaced"):
        evidence_module._verify_bundle_binding(
            contract, run_id="replace-race", root_stat=root_stat,
            run_stat=run_stat, file_stat=file_stat, exact_bytes=b"{}",
        )


def test_locally_resigned_external_receipt_is_rejected_without_real_verifier(tmp_path: Path) -> None:
    contract = load_contract()
    ref = write_receipt(tmp_path, "commercial.json", {"passed": True, "provider_kind": "authenticated_external"})
    refs = empty_refs()
    refs["candidate_evidence"] = _write_current_candidate_evidence()
    refs["external"]["commercial"] = ref
    path = assemble_evidence_bundle(contract, run_id=run_id(tmp_path, "forged"), refs=refs)
    payload = current_repository_input(contract, evidence_bundle=path)
    item = payload["evidence"]["commercial"]
    assert item["status"] == "failed"
    assert item["schema_valid"] is True
    assert item["fresh"] is True
    assert item["fingerprint_match"] is False
    assert "external verifier unavailable" in item["detail"]
    result = inspect(payload)
    assert result["status"] == "blocked"
    assert result["blockers"][0] == "EVIDENCE_FINGERPRINT_MISMATCH"



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
    path = assemble_evidence_bundle(contract, run_id=run_id(tmp_path, "named"), refs=refs)
    bundle = json.loads(path.read_text())
    subject = {
        "subject_id": "current-repository",
        "candidate_id": "working-tree",
        "scope_id": "governance-pipeline",
    }
    projected = _named_receipts(
        bundle, contract, subject=subject,
        now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    assert projected["portal_test"]["status"] == "failed"
    assert projected["portal_test"]["schema_valid"] is True
    assert projected["portal_test"]["fingerprint_match"] is False


@pytest.mark.parametrize("missing", ("review_plan", "candidate_evidence"))
def test_named_receipt_requires_exact_plan_and_candidate(
    tmp_path: Path, missing: str,
) -> None:
    contract = load_contract()
    refs = empty_refs()
    refs["candidate_evidence"] = _write_current_candidate_evidence()
    refs["review_plan"] = write_receipt(tmp_path, "review-plan.json", {})
    refs["named_evidence"]["portal-test"] = write_receipt(
        tmp_path, "named.json", {},
    )
    refs[missing] = None
    path = assemble_evidence_bundle(
        contract, run_id=run_id(tmp_path, f"missing-{missing}"), refs=refs,
    )
    bundle = json.loads(path.read_text())
    subject = {
        "subject_id": "current-repository",
        "candidate_id": "working-tree",
        "scope_id": "governance-pipeline",
    }
    projected = _named_receipts(
        bundle, contract, subject=subject, now=datetime.now(timezone.utc),
    )
    item = projected["portal_test"]
    assert item["status"] == "failed"
    assert item["schema_valid"] is True
    assert item["fresh"] is True
    assert item["fingerprint_match"] is False
    assert "missing" in item["detail"]


def _write_current_candidate_evidence(*paths: str) -> str:
    import subprocess
    changed = list(paths) or ["quwoquan_ops/policies/governance_pipeline_admission_contract.yaml"]
    command = [sys.executable, "quwoquan_ops/cli/feature_tree.py", "candidate-evidence"]
    for path in changed:
        command.extend(["--changed-path", path])
    return subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _governance_review_fixture(
    *, changed_paths: list[str], run_id_value: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    contract = load_contract()
    scope = contract["current_repository_evidence"]["named_evidence_plan_binding"]["scope"]
    candidate_ref = _write_current_candidate_evidence(*changed_paths)
    registry = copy.deepcopy(
        __import__("yaml").safe_load(
            (ROOT / ".agents/skills/review/references/registry.yaml").read_text()
        )
    )
    registry["workflows"]["dev"]["baseline_evidence"] = ""
    registry["evidence"] = {
        "portal-test": {
            "command": "printf portal-test", "segment": "POST",
            "required": True, "timeout_seconds": 300, "covers": [],
        },
        "portal-build": {
            "command": "printf portal-build", "segment": "POST",
            "required": True, "timeout_seconds": 300, "covers": [],
        },
    }
    source = evidence_runner._workspace_source_classification(ROOT)
    source["repository_clean"] = False
    with (
        mock.patch.object(
            review_dispatch, "_checklist_evidence",
            return_value=["portal-test", "portal-build"],
        ),
        mock.patch.object(
            evidence_runner,
            "_workspace_source_classification",
            return_value=source,
        ),
    ):
        plan = review_dispatch.build_plan(
            registry, "dev", "POST", "implementation", changed_paths,
            candidate_evidence_ref=candidate_ref,
            scope=scope,
        )
        receipt = evidence_runner.run_plan(
            plan, registry=registry, cwd=ROOT, run_id=run_id_value,
            plan_bytes=canonical_json_bytes(plan), plan_ref=".qwq_output/test-fixture-plan.json",
        )
    evidence_runner.validate_named_evidence_receipt(receipt)
    return plan, receipt, candidate_ref


def test_governance_named_layers_reject_feedback_only_receipt(
    tmp_path: Path,
) -> None:
    plan, receipt, candidate_ref = _governance_review_fixture(
        changed_paths=[
            "quwoquan_ops/cli/lib/governance_pipeline_admission/adapters.py"
        ],
        run_id_value="governance-feedback-only",
    )
    assert receipt["evidence_class"] == "feedback_only"
    plan_ref = write_receipt(tmp_path, "review-plan-feedback.json", plan)
    named_ref = write_receipt(tmp_path, "named-feedback.json", receipt)
    refs = empty_refs()
    refs.update({"candidate_evidence": candidate_ref, "review_plan": plan_ref})
    refs["named_evidence"] = {
        "portal-test": named_ref,
        "portal-build": named_ref,
    }
    path = assemble_evidence_bundle(
        load_contract(), run_id=run_id(tmp_path, "feedback-only"), refs=refs,
    )
    payload = current_repository_input(load_contract(), evidence_bundle=path)
    for layer in ("review_terminal", "portal_test", "portal_build"):
        item = payload["evidence"][layer]
        assert item["status"] == "failed"
        assert item["schema_valid"] is True
        assert item["fresh"] is True
        assert "REVIEW.EVIDENCE_FEEDBACK_ONLY" in item["detail"]


def test_current_repository_rejects_fresh_named_receipts_from_other_exact_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_plan, _current_receipt, candidate_ref = _governance_review_fixture(
        changed_paths=[
            "quwoquan_ops/cli/lib/governance_pipeline_admission/adapters.py"
        ],
        run_id_value="governance-current-plan",
    )
    other_plan, other_receipt, other_candidate_ref = _governance_review_fixture(
        changed_paths=[
            "quwoquan_ops/cli/lib/governance_pipeline_admission/contract.py"
        ],
        run_id_value="governance-other-plan",
    )
    assert candidate_ref == current_plan["candidate_evidence_identity"]["ref"]
    assert other_receipt["plan_fingerprint_ref"] == other_plan["fingerprint_receipt"]["ref"]
    assert other_receipt["plan_fingerprint_ref"] != current_plan["fingerprint_receipt"]["ref"]
    evidence_runner.validate_named_evidence_receipt(other_receipt)

    plan_ref = write_receipt(tmp_path, "review-plan.json", current_plan)
    named_ref = write_receipt(tmp_path, "named-other-plan.json", other_receipt)
    refs = empty_refs()
    refs.update({"candidate_evidence": candidate_ref, "review_plan": plan_ref})
    refs["named_evidence"] = {
        "portal-test": named_ref,
        "portal-build": named_ref,
    }
    path = assemble_evidence_bundle(
        load_contract(), run_id=run_id(tmp_path, "other-plan"), refs=refs,
    )
    payload = current_repository_input(load_contract(), evidence_bundle=path)
    for layer in ("review_terminal", "portal_test", "portal_build"):
        item = payload["evidence"][layer]
        assert item["status"] == "failed"
        assert item["schema_valid"] is True
        assert item["fresh"] is True
        assert item["fingerprint_match"] is False
        assert "different exact Review plan" in item["detail"]
    result = inspect(payload)
    assert result["status"] == "blocked"
    assert result["blockers"][0] == "EVIDENCE_FINGERPRINT_MISMATCH"


def test_external_readback_shape_is_schema_but_identity_drift_is_fingerprint() -> None:
    contract = load_contract()
    now = datetime.now(timezone.utc)
    subject = {
        "subject_id": "current-repository",
        "candidate_id": "working-tree",
        "scope_id": "governance-pipeline",
        "evidence_fingerprint": subject_fingerprint(contract),
    }
    raw = canonical_json_bytes({"provider": "opaque"})
    with pytest.raises(EvidenceAdapterError) as shape_error:
        adapters.verify_external(
            layer="commercial", raw=raw, receipt_ref=".qwq_output/external.json",
            verifier=lambda _request: {}, subject=subject,
            verification_time=now, contract=contract,
        )
    assert shape_error.value.schema_valid is False
    assert shape_error.value.fingerprint_match is True

    def verifier(request: dict[str, Any]) -> dict[str, Any]:
        policy = contract["layer_admission"]["commercial"]
        return {
            "provider_id": policy["provider_id"],
            "provider_kind": "authenticated_external",
            "authenticated": True,
            "exact_bytes_verified": True,
            "release_evidence_eligible": True,
            "candidate_id": "other-candidate",
            "scope_id": subject["scope_id"],
            "evidence_fingerprint": subject["evidence_fingerprint"],
            "result": "closed",
            "provider_timestamp": now.isoformat(timespec="seconds"),
            "receipt_bytes_sha256": request["receipt_bytes_sha256"],
            "verifier_id": policy["verifier_id"],
        }

    with pytest.raises(EvidenceAdapterError) as identity_error:
        adapters.verify_external(
            layer="commercial", raw=raw, receipt_ref=".qwq_output/external.json",
            verifier=verifier, subject=subject, verification_time=now,
            contract=contract,
        )
    assert identity_error.value.schema_valid is True
    assert identity_error.value.fingerprint_match is False


def test_bundle_consumption_uses_one_timezone_aware_verification_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = load_contract()
    path = assemble_evidence_bundle(
        contract, run_id=run_id(tmp_path, "single-clock"), refs=empty_refs(),
    )
    fixed = datetime(2026, 9, 1, 4, 30, 0, tzinfo=timezone.utc)
    seen: list[datetime] = []
    original_absent = evidence_module._absent
    def capture_absent(*args: Any, **kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs["verification_time"])
        return original_absent(*args, **kwargs)
    monkeypatch.setattr(evidence_module, "_absent", capture_absent)
    payload = current_repository_input(
        contract, evidence_bundle=path, verification_time=fixed,
    )
    assert seen and set(seen) == {fixed}
    assert {item["verified_at"] for item in payload["evidence"].values()} == {
        fixed.isoformat(timespec="seconds")
    }
    with pytest.raises(ContractError, match="timezone-aware"):
        current_repository_input(
            contract, evidence_bundle=path,
            verification_time=datetime(2026, 9, 1, 4, 30, 0),
        )


def test_failed_adapter_dimensions_reach_evaluator_with_exact_precedence() -> None:
    contract = load_contract()
    now = datetime.now(timezone.utc)
    for detail, expected, dimensions in (
        ("receipt stale: source changed", "EVIDENCE_STALE", (True, False, True)),
        ("provider identity mismatch", "EVIDENCE_FINGERPRINT_MISMATCH", (True, True, False)),
        ("receipt JSON invalid", "EVIDENCE_SCHEMA_INVALID", (False, True, True)),
    ):
        payload = current_repository_input(contract, verification_time=now)
        payload["evidence"]["local_scope_ready"] = evidence_module._failed(
            ContractError(detail), verification_time=now,
        )
        item = payload["evidence"]["local_scope_ready"]
        assert (item["schema_valid"], item["fresh"], item["fingerprint_match"]) == dimensions
        assert inspect(payload)["blockers"][0] == expected


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
            mode="workspace", candidate_evidence_path=tmp_path / "candidate.json", repo_root=ROOT,
        )
    assert snapshot(tmp_path) == before
    assert not state.exists()


def test_objective_and_hosted_source_adapter_local_boundaries() -> None:
    contract = load_contract()
    objective = adapters.produce_objective_bytes()
    readback = adapters.objective_readback(
        raw=objective, receipt_ref=".qwq_output/objective.json", candidate_id="c", scope_id="s",
        verification_time=datetime.now(timezone.utc), contract=contract,
    )
    assert readback["provider_kind"] == "local_runtime"
    hosted = adapters.produce_hosted_source_bytes(contract)
    source = adapters.verify_hosted_source(
        raw=hosted, receipt_ref=".qwq_output/hosted.json", candidate_id="c", scope_id="s",
        verification_time=datetime.now(timezone.utc), contract=contract,
    )
    assert source["result"] in {"code_pass", "code_absent"}
    tampered = json.loads(hosted)
    tampered["snapshots"][0]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ContractError, match="source bytes drifted"):
        adapters.verify_hosted_source(
            raw=canonical_json_bytes(tampered), receipt_ref=".qwq_output/hosted.json",
            candidate_id="c", scope_id="s", verification_time=datetime.now(timezone.utc),
            contract=contract,
        )


def test_hotl_and_handoff_adapter_negative_boundaries() -> None:
    contract = load_contract()
    unsafe_hotl = canonical_json_bytes({
        "provider_timestamp": "2026-08-30T00:00:00+00:00",
        "readback": {"allowed_mode": "hotl", "mutation_allowed": True, "grant_executable": True, "max_write_concurrency": 2},
    })
    readback = adapters.verify_hotl(
        raw=unsafe_hotl, receipt_ref=".qwq_output/hotl.json", candidate_id="c",
        scope_id="s", verification_time=datetime.now(timezone.utc), contract=contract,
    )
    assert readback["result"] == "absent"
    with pytest.raises(Exception):
        adapters.verify_handoff(
            raw=b"{}", receipt_ref=".qwq_output/handoff.json", candidate_id="c",
            scope_id="s", verification_time=datetime.now(timezone.utc), contract=contract,
        )


def test_human_readback_consumes_exact_owner_v2_and_rejects_v1_or_digest_drift() -> None:
    contract = load_contract()
    from lib.human_agent_delivery import load_contract as load_human_contract
    human = load_human_contract(); model = human["calibration_model"]
    dimensions = human["closed_sets"]["human_calibration_observation_dimension"]
    sessions = []
    for principal, responsibilities in model["principal_responsibility_mapping"].items():
        sessions.append({
            "schema_version": human["schema_version"], "contract_version": model["contract_version"],
            "role_model_version": model["role_model_version"], "observation_model_version": model["observation_model_version"],
            "session_id": f"calibration-{principal.replace('_', '-')}", "principal_class": principal,
            "participant_ref": f"participant-{principal.replace('_', '-')}",
            "scope": {"decision_unit_id": "decision-unit-governance", "task_id": f"task-{principal}", "evidence_fingerprint": "sha256:" + "a" * 64, "responsibility_classes": responsibilities},
            "started_at": "2026-08-30T00:00:00+00:00", "completed_at": "2026-08-30T00:30:00+00:00",
            "source_assurance": {"source_kind": "human_participant", "authentication_provider_ref": "provider", "participant_authenticated": True, "consent_obtained": True, "consent_recorded_at": "2026-08-29T23:59:00+00:00", "direct_identifiers_removed": True, "free_text_excluded": True, "observer_attested": True},
            "separation_policy": "role-record-only",
            "observations": [{"observation_id": f"observation-{index+1}", "dimension": dimension, "observed_at": "2026-08-30T00:10:00+00:00", "outcome": "demonstrated", "responsibility_classes": responsibilities} for index, dimension in enumerate(dimensions)],
        })
    datetime_module = __import__("datetime")
    now = datetime_module.datetime(2026, 8, 30, 1, 0, tzinfo=datetime_module.timezone.utc)
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
        provider_timestamp=payload["generated_at"], verification_time=now,
        verifier=verifier, contract=contract,
    )
    assert exact["status"] == "calibrated"
    assert readback["provider_kind"] == "authenticated_external"
    assert readback["release_evidence_eligible"] is True
    v1 = {"schema_version": 1, "status": "observed"}
    with pytest.raises(ContractError, match="HAD.CALIBRATION_CONTRACT_INCOMPATIBLE"):
        adapters.verify_human_readback(raw=canonical_json_bytes(v1), receipt_ref=".qwq_output/human.json", candidate_id="c", scope_id="s", evidence_fingerprint="sha256:" + "a" * 64, session_bytes_by_ref={}, provider_timestamp=payload["generated_at"], verification_time=now, verifier=verifier, contract=contract)
    drift = dict(session_bytes); first = next(iter(drift)); drift[first] += b" "
    with pytest.raises(ContractError, match="HAD.CALIBRATION_CONTRACT_INCOMPATIBLE"):
        adapters.verify_human_readback(raw=canonical_json_bytes(payload), receipt_ref=".qwq_output/human.json", candidate_id="c", scope_id="s", evidence_fingerprint="sha256:" + "a" * 64, session_bytes_by_ref=drift, provider_timestamp=payload["generated_at"], verification_time=now, verifier=verifier, contract=contract)

    stale_time = datetime_module.datetime.fromisoformat(payload["fresh_until"]) + datetime_module.timedelta(seconds=1)
    generated_at = datetime_module.datetime.fromisoformat(payload["generated_at"])
    assert (stale_time - generated_at).total_seconds() < contract["layer_admission"]["human_calibration"]["max_age_seconds"]
    with pytest.raises(ContractError, match="readback is stale"):
        adapters.verify_human_readback(
            raw=raw, receipt_ref=".qwq_output/human.json", candidate_id="c", scope_id="s",
            evidence_fingerprint="sha256:" + "a" * 64, session_bytes_by_ref=session_bytes,
            provider_timestamp=payload["generated_at"], verification_time=stale_time,
            verifier=verifier, contract=contract,
        )


def _real_review_exact_fixture(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], bytes, str, bytes, str, bytes]:
    from lib.agent_governance_contract import contract_schema_version
    import handoff_consumer
    import review_consolidator

    plan, evidence, _candidate_ref = _governance_review_fixture(
        changed_paths=["README.md"],
        run_id_value="governance-review-positive",
    )
    evidence["source"]["repository_clean"] = True
    evidence["evidence_class"] = "reusable"
    evidence["admission_eligible"] = True
    evidence_raw = canonical_json_bytes(evidence)
    evidence_ref = ".qwq_output/evidence.json"
    identity = handoff_consumer.named_evidence_identity_from_raw(evidence_ref, evidence_raw, evidence)
    timestamp = evidence["finished_at"]
    result = {
        "schema_version": contract_schema_version("review_result"),
        "role": "developer", "status": "completed",
        "plan_fingerprint_ref": plan["fingerprint_receipt"]["ref"],
        "plan_fingerprint_digest": plan["fingerprint_receipt"]["digest"],
        "evidence_receipt_ref": evidence_ref,
        "evidence_receipt_canonical_bytes_sha256": identity["canonical_bytes_sha256"],
        "evidence_run_id": identity["run_id"], "evidence_generation_id": identity["generation_id"],
        "execution_fingerprint_ref": identity["execution_fingerprint_ref"],
        "execution_fingerprint_digest": identity["execution_fingerprint_digest"],
        "result_fingerprint_ref": identity["result_fingerprint_ref"],
        "result_fingerprint_digest": identity["result_fingerprint_digest"],
        "assembled_input_byte_count": 1, "assembled_input_digest": "sha256:" + "3" * 64,
        "assembled_input_compression": {"mode": "full", "applied": False, "changes": [], "attempts": []},
        "started_at": timestamp, "finished_at": timestamp, "findings": [],
    }
    result_ref = ".qwq_output/review.json"; result_raw = canonical_json_bytes(result)
    monkeypatch.setattr(review_consolidator.review_dispatch, "validate_current_review_plan", lambda *_args, **_kwargs: plan["fingerprint_receipt"] )
    monkeypatch.setattr(review_consolidator.handoff_consumer, "validate_named_evidence_ref_payload", lambda receipt, **_kwargs: receipt)
    consolidation = review_consolidator.consolidate(
        plan, [(evidence_ref, evidence)], [(result_ref, result)],
        generated_at="2026-08-30T00:01:00+00:00",
        exact_bytes_by_ref={evidence_ref: evidence_raw, result_ref: result_raw},
    )
    return plan, evidence_raw, evidence_ref, result_raw, result_ref, canonical_json_bytes(consolidation)

def test_review_exact_inputs_have_real_positive_path(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = load_contract()
    plan, evidence_raw, evidence_ref, result_raw, result_ref, consolidation_raw = _real_review_exact_fixture(monkeypatch)
    readback = adapters.verify_review(
        plan_raw=canonical_json_bytes(plan), plan_ref="plan.json",
        evidence_raw=evidence_raw, evidence_ref=evidence_ref,
        reviewer_result_pairs=[(result_ref, result_raw)],
        consolidation_raw=consolidation_raw, consolidation_ref="consolidation.json",
        candidate_id="c", scope_id="s", verification_time=datetime.now(timezone.utc),
        contract=contract,
    )
    assert readback["result"] == "pass"
    assert readback["receipt_ref"] == "consolidation.json"


def test_review_exact_result_ref_drift_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = load_contract()
    plan, evidence_raw, evidence_ref, result_raw, _result_ref, consolidation_raw = _real_review_exact_fixture(monkeypatch)
    with pytest.raises(ContractError, match="exact validation failed"):
        adapters.verify_review(
            plan_raw=canonical_json_bytes(plan), plan_ref="plan.json",
            evidence_raw=evidence_raw, evidence_ref=evidence_ref,
            reviewer_result_pairs=[(".qwq_output/review-renamed.json", result_raw)],
            consolidation_raw=consolidation_raw, consolidation_ref="consolidation.json",
            candidate_id="c", scope_id="s", verification_time=datetime.now(timezone.utc),
            contract=contract,
        )


def test_review_nonpass_never_projects_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    contract = load_contract()
    plan, evidence_raw, evidence_ref, result_raw, result_ref, consolidation_raw = _real_review_exact_fixture(monkeypatch)
    consolidation = json.loads(consolidation_raw)
    consolidation["terminal"] = {"status": "PR_WARN", "codes": []}
    monkeypatch.setattr(
        "review_consolidator.consolidate", lambda *_args, **_kwargs: consolidation
    )
    with pytest.raises(ContractError, match="非 PASS"):
        adapters.verify_review(
            plan_raw=canonical_json_bytes(plan), plan_ref="plan.json",
            evidence_raw=evidence_raw, evidence_ref=evidence_ref,
            reviewer_result_pairs=[(result_ref, result_raw)],
            consolidation_raw=canonical_json_bytes(consolidation),
            consolidation_ref="consolidation.json", candidate_id="c", scope_id="s",
            verification_time=datetime.now(timezone.utc), contract=contract,
        )
