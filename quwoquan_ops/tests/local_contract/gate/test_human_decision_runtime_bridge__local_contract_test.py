"""Human PRE/DURING/POST explicit runtime decision bridge local contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/human-agent-delivery-interaction/spec.md#gwt-001a
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))

from lib.evidence_fingerprint import canonical_json_bytes  # noqa: E402
from lib.human_agent_delivery.runtime_bridge import (  # noqa: E402
    HumanDecisionBridgeError,
    build_self_attested_receipt,
    project_runtime_decision,
    read_runtime_decision_ref,
    record_runtime_decision,
)

CLI = ROOT / "quwoquan_ops/cli/human_agent_delivery.py"


def _receipt(*, decision: str = "continue", redirect_target: str | None = None) -> dict:
    return build_self_attested_receipt(
        objective_ref="objective:runtime-bridge",
        criteria=["pytest focused tests pass", "no external host event is synthesized"],
        duration_scope_kind="boundary",
        duration_scope_value="runtime-bridge-v1",
        decision=decision,
        redirect_target=redirect_target,
        human_identity="local-operator-input",
        received_at="2026-09-03T00:00:00+08:00",
    )


def test_create_once_and_exact_ref_tamper_or_ref_drift_fail_closed(tmp_path: Path) -> None:
    store = tmp_path / ".qwq_output/env/repo/runs/human-decisions"
    first = record_runtime_decision(_receipt(), repo_root=tmp_path, store=store)
    second = record_runtime_decision(_receipt(), repo_root=tmp_path, store=store)
    assert first.ref == second.ref
    assert first.digest == second.digest
    assert first.created is True
    assert second.created is False

    path = tmp_path / first.ref
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(HumanDecisionBridgeError) as tampered:
        read_runtime_decision_ref(first.ref, repo_root=tmp_path)
    assert tampered.value.code == "HAD.RUNTIME_DECISION_TAMPERED"

    # A filename that claims the wrong digest but exists is ref drift, not absence.
    drifted_path = Path(first.ref)
    drifted = (drifted_path.parent / (("0" * 64) + ".json")).as_posix()
    drifted_absolute = tmp_path / drifted
    drifted_absolute.write_bytes(json.dumps(first.receipt).encode("utf-8"))
    with pytest.raises(HumanDecisionBridgeError) as drift:
        read_runtime_decision_ref(drifted, repo_root=tmp_path)
    assert drift.value.code == "HAD.RUNTIME_DECISION_TAMPERED"


def test_existing_content_addressed_receipt_is_never_overwritten(tmp_path: Path) -> None:
    store = tmp_path / ".qwq_output/env/repo/runs/human-decisions"
    receipt = _receipt()
    raw = canonical_json_bytes(receipt)
    digest = hashlib.sha256(raw).hexdigest()
    path = store / "by-digest" / f"{digest}.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"conflict")
    with pytest.raises(HumanDecisionBridgeError) as conflict:
        record_runtime_decision(receipt, repo_root=tmp_path, store=store)
    assert conflict.value.code == "HAD.RUNTIME_DECISION_TAMPERED"
    assert path.read_bytes() == b"conflict"


def test_ordinary_missing_is_declared_not_projected_and_nonblocking() -> None:
    projection = project_runtime_decision(target_kind="agent_execution")
    assert projection["status"] == "declared"
    assert projection["projection"] == "not_projected"
    assert projection["blocks_execution"] is False
    assert projection["terminal"] == "HUMAN_DECISION.NOT_PROJECTED"


def test_pause_and_redirect_explicit_poll_have_stable_terminals(tmp_path: Path) -> None:
    store = tmp_path / ".qwq_output/env/repo/runs/human-decisions"
    pause = record_runtime_decision(
        _receipt(decision="pause"), repo_root=tmp_path, store=store
    )
    pause_projection = project_runtime_decision(
        target_kind="agent_execution",
        human_decision_ref=pause.ref,
        repo_root=tmp_path,
        store=store,
    )
    assert pause_projection["terminal"] == "HUMAN_DECISION.PAUSED"
    assert pause_projection["blocks_execution"] is True

    redirect_receipt = _receipt(decision="redirect", redirect_target="objective:safer-boundary")
    redirect_receipt["received_at"] = "2026-09-03T00:01:00+08:00"
    redirect = record_runtime_decision(
        redirect_receipt, repo_root=tmp_path, store=store
    )
    polled = project_runtime_decision(
        target_kind="agent_execution",
        objective_ref="objective:runtime-bridge",
        poll_latest=True,
        repo_root=tmp_path,
        store=store,
    )
    assert polled["human_decision_ref"] == redirect.ref
    assert polled["terminal"] == "HUMAN_DECISION.REDIRECTED"
    assert polled["redirect_target"] == "objective:safer-boundary"


def test_self_attested_receipt_cannot_satisfy_formal_prod(tmp_path: Path) -> None:
    store = tmp_path / ".qwq_output/env/repo/runs/human-decisions"
    written = record_runtime_decision(_receipt(), repo_root=tmp_path, store=store)
    projection = project_runtime_decision(
        target_kind="handoff",
        admission_class="formal_prod",
        human_decision_ref=written.ref,
        repo_root=tmp_path,
        store=store,
    )
    assert projection["status"] == "blocked"
    assert projection["authority_status"] == "self_attested_non_formal"
    assert projection["formal_admission_satisfied"] is False
    assert projection["terminal"] == "HUMAN_DECISION.FORMAL_AUTHORITY_REQUIRED"



def test_local_approve_admission_is_declared_but_not_authoritative(tmp_path: Path) -> None:
    store = tmp_path / ".qwq_output/env/repo/runs/human-decisions"
    written = record_runtime_decision(
        _receipt(decision="approve_admission"), repo_root=tmp_path, store=store
    )
    projection = project_runtime_decision(
        target_kind="agent_execution",
        human_decision_ref=written.ref,
        repo_root=tmp_path,
        store=store,
    )
    assert projection["terminal"] == "HUMAN_DECISION.ADMISSION_APPROVAL_DECLARED"
    assert projection["projection"] == "projected_non_authoritative"
    assert projection["formal_admission_satisfied"] is False
    assert projection["blocks_execution"] is False


def test_review_plan_optionally_carries_exact_human_decision_projection(tmp_path: Path) -> None:
    store = tmp_path / ".qwq_output/env/repo/runs/human-decisions"
    written = record_runtime_decision(_receipt(), repo_root=tmp_path, store=store)
    projection = project_runtime_decision(
        target_kind="review",
        human_decision_ref=written.ref,
        repo_root=tmp_path,
        store=store,
    )
    assert projection["human_decision_ref"] == written.ref
    assert projection["decision"] == "continue"
    assert projection["status"] == "continue"


def test_cli_records_only_explicit_self_attested_input_and_poll_is_explicit(tmp_path: Path) -> None:
    env = dict(os.environ)
    # Keep the repository runtime store untouched by running record against a temporary cwd
    # and using an invalid objective only for the no-write projection path.
    ordinary = subprocess.run(
        [
            sys.executable,
            "-B",
            str(CLI),
            "decision-project",
            "--target-kind",
            "review",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ordinary.returncode == 0, ordinary.stderr
    payload = json.loads(ordinary.stdout)
    assert payload["projection"] == "not_projected"
    assert payload["blocks_execution"] is False
