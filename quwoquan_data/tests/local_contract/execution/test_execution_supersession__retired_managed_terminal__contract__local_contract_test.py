"""退役 managed 轨 execution 的唯一合法历史终态出路。

退役轨 execution_state 是 AI 自报投影而非 receipt-derived 事实：其 `succeeded`
不具备当前 receipt authority，其 manifest 已不满足现行契约、永远不可 resume。
supersession 必须能只读承载这种冻结历史形状并 create-once 终结它；同时当前轨
`succeeded` 的终态保护不得因此被打开。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from content.execution.execution_supersession import supersede_execution
from content.execution.execution_terminal import load_terminal_execution_evidence
from core.io import write_json
from core.source_digest import current_source_digest

EXECUTION_ID = "20260827--travel-homepage-retired--sichuan--pilot-009"


def _drifted_source_document() -> dict[str, object]:
    document = current_source_digest().to_document()
    drifted = dict(document)
    drifted["digest"] = "sha256:" + hashlib.sha256(b"retired-managed-drift").hexdigest()
    return drifted


def _retired_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "schema": "quwoquan.content.execution_state",
        "executionId": EXECUTION_ID,
        "completed": ["0.plan", "sources"],
        "status": "succeeded",
        "updatedAt": "2026-08-27T12:00:00Z",
    }
    state.update(overrides)
    return state


def _execution_root(tmp_path: Path, *, state: dict[str, object]) -> Path:
    root = tmp_path / "tasks" / EXECUTION_ID
    write_json(
        root / "execution_manifest.json",
        {
            "schema": "historical-fixture",
            "executionId": EXECUTION_ID,
            "sourceDigest": _drifted_source_document(),
        },
    )
    write_json(root / "0.plan/request.json", {"topic": "travel"})
    write_json(
        root / "0.plan/target_set.json",
        {"executionId": EXECUTION_ID, "targetCount": 1},
    )
    write_json(root / "_shared/execution_state.json", state)
    return root


def test_retired_managed_succeeded_state_reaches_a_frozen_superseded_terminal(
    tmp_path: Path,
) -> None:
    root = _execution_root(tmp_path, state=_retired_state())
    state_bytes = (root / "_shared/execution_state.json").read_bytes()
    manifest_bytes = (root / "execution_manifest.json").read_bytes()

    receipt, path = supersede_execution(
        EXECUTION_ID,
        reason="source_drift",
        executions_root=tmp_path / "tasks",
    )

    assert receipt["decision"] == "superseded"
    assert receipt["previousStatus"] == "succeeded"
    assert receipt["stateEvidence"] == "settled_retired_managed_snapshot"
    assert receipt["evidenceDisposition"] == "protected_read_only"
    assert (root / "_shared/execution_state.json").read_bytes() == state_bytes
    assert (root / "execution_manifest.json").read_bytes() == manifest_bytes

    terminal = load_terminal_execution_evidence(root)
    assert terminal is not None
    assert terminal.decision == "superseded"
    assert terminal.path == path

    replay, replay_path = supersede_execution(
        EXECUTION_ID,
        reason="source_drift",
        executions_root=tmp_path / "tasks",
    )
    assert replay == receipt
    assert replay_path == path


def test_bytes_outside_the_frozen_retired_shape_fail_closed(tmp_path: Path) -> None:
    _execution_root(
        tmp_path,
        state=_retired_state(poolDelta=1),
    )
    with pytest.raises(ValueError, match="schema violation"):
        supersede_execution(
            EXECUTION_ID,
            reason="source_drift",
            executions_root=tmp_path / "tasks",
        )


def test_current_track_succeeded_state_stays_terminal_protected(
    tmp_path: Path,
) -> None:
    receipt_body = json.dumps({"stage": "ship"}, ensure_ascii=False).encode("utf-8")
    root = _execution_root(
        tmp_path,
        state={
            "schema": "quwoquan.content.execution_state_projection",
            "executionId": EXECUTION_ID,
            "completed": ["0.plan"],
            "status": "succeeded",
            "latestStage": "ship",
            "next": "END",
            "latestReceiptRef": "_shared/receipts/010-ship.json",
            "latestReceiptDigest": "sha256:" + hashlib.sha256(receipt_body).hexdigest(),
            "updatedAt": "2026-08-27T12:00:00Z",
        },
    )
    (root / "_shared/receipts").mkdir(parents=True, exist_ok=True)
    (root / "_shared/receipts/010-ship.json").write_bytes(receipt_body)

    with pytest.raises(ValueError, match="not supersession-eligible"):
        supersede_execution(
            EXECUTION_ID,
            reason="source_drift",
            executions_root=tmp_path / "tasks",
        )
