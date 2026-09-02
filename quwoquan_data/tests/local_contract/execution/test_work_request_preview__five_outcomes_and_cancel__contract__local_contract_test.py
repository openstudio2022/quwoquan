# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-005.t2
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.source import pre_acquisition_handoff as handoff_api
from content.execution.planning import (
    work_request_contract,
    work_request_dependencies,
)
from content.execution.planning.work_request import WorkRequestCommandWriter
from content.execution.planning.work_request_contract import WorkRequestPreviewQuery
from core import paths
from core.source_digest import content_source_revision

DIGEST = "sha256:" + "a" * 64


def _handoff_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "vertical": "travel",
        "regionRef": "china",
        "lifecycle": "research",
        "scopeType": "region",
        "scope": "china",
        "primaryTopicRef": None,
        "relatedTopicRefs": [],
        "scale": "M1",
        "workloadTargets": {"homepage": 1},
        "sourceSelection": {
            "homepage": {"mode": "site_primary", "providers": ["wikipedia"]},
        },
    }
    document.update(overrides)
    return document


def _install_handoff(
    monkeypatch: pytest.MonkeyPatch,
    documents: dict[str, dict[str, object]],
) -> None:
    """Serve fake confirmed handoffs keyed by file name."""

    def _load(path: Path) -> dict[str, object]:
        return dict(documents[Path(path).name])

    monkeypatch.setattr(handoff_api, "load_pre_acquisition_handoff", _load)


def _intent(tmp_path: Path, **overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "intentText": "生成一个区域主页",
        "mode": "fresh",
        "capacityCalibrationReceiptRef": str(tmp_path / "capacity.json"),
        "preAcquisitionHandoffRef": str(tmp_path / "handoff.json"),
        "scaleSourcePoolPlanRef": str(tmp_path / "pool.json"),
        "sourcePoolEvidenceRootRef": str(tmp_path / "evidence"),
    }
    document.update(overrides)
    return document


def _dependencies(
    _intent: object,
    *,
    scale: str,
    workload_mode: str,
    workloads: object,
    **_kwargs: object,
) -> dict[str, object]:
    workload_map = dict(workloads)
    return {
        "source": {
            "algorithm": "sha256",
            "digest": "sha256:" + "b" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "c" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": "sha256:" + "d" * 64,
        "sourcePool": {
            "poolId": "pool-preview",
            "targetScale": "WORKLOAD" if workload_mode == "explicit" else scale,
            "workloadMode": workload_mode,
            "activeCarriers": list(workload_map),
            "workloadTargets": workload_map,
            "sourceRevision": "sha256:" + "e" * 64,
            "sourceDigest": "sha256:" + "b" * 64,
            "entityCatalogDigest": "sha256:" + "d" * 64,
            "planDigest": "sha256:" + "f" * 64,
        },
        "dependencies": {"sourcePool": {"ref": "pool.json", "digest": DIGEST}},
        "dependencySetDigest": DIGEST,
    }


def test_preview_modify_needs_input_blocked_and_cancel_are_mutually_exclusive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(work_request_contract, "dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "canonical_dependency_ref", lambda path: path.name
    )
    _install_handoff(
        monkeypatch,
        {
            "handoff.json": _handoff_document(),
            "handoff-2.json": _handoff_document(
                scale="M2", workloadTargets={"homepage": 2}
            ),
            "handoff-broken.json": _handoff_document(
                workloadTargets={}, sourceSelection={}
            ),
        },
    )
    preview_query = WorkRequestPreviewQuery()
    first = preview_query.preview(_intent(tmp_path))
    modified = preview_query.preview(
        _intent(
            tmp_path,
            preAcquisitionHandoffRef=str(tmp_path / "handoff-2.json"),
        )
    )
    broken = preview_query.preview(
        _intent(
            tmp_path,
            preAcquisitionHandoffRef=str(tmp_path / "handoff-broken.json"),
        )
    )

    assert first["outcome"] == "preview"
    assert first["normalizedRequest"]["scale"] == "M1"
    assert first["normalizedRequest"]["workloads"] == {"homepage": 1}
    assert first["normalizedRequest"]["scopeType"] == "region"
    assert first["normalizedRequest"]["sourcePool"]["targetScale"] == "WORKLOAD"
    assert modified["outcome"] == "preview"
    assert modified["requestDigest"] != first["requestDigest"]
    # Demand facts live only in the confirmed handoff: a handoff without a
    # usable workload is an unavailable dependency, never a silent default.
    assert broken["outcome"] == "blocked"
    assert broken["error"]["code"] == "DATA.WORK_REQUEST.DEPENDENCY_UNAVAILABLE"

    def unavailable(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise FileNotFoundError("source-ready evidence is missing")

    monkeypatch.setattr(work_request_contract, "dependency_bindings", unavailable)
    blocked = preview_query.preview(_intent(tmp_path))
    assert blocked["outcome"] == "blocked"
    assert blocked["error"]["code"] == "DATA.WORK_REQUEST.DEPENDENCY_UNAVAILABLE"

    monkeypatch.setattr(work_request_contract, "dependency_bindings", _dependencies)
    canceled = WorkRequestCommandWriter(output_root=tmp_path / "output").cancel(
        _intent(tmp_path),
        preview_digest=str(first["requestDigest"]),
    )
    assert canceled["outcome"] == "canceled"
    assert not (tmp_path / "output/workspace/content-campaign-envelopes").exists()


def test_demand_facts_are_owned_by_handoff_not_by_caller_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(work_request_contract, "dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "canonical_dependency_ref", lambda path: path.name
    )
    _install_handoff(monkeypatch, {"handoff.json": _handoff_document()})
    query = WorkRequestPreviewQuery()

    for field in (
        "vertical",
        "regionRef",
        "topic",
        "lifecycle",
        "workloads",
        "sourceProviders",
    ):
        rejected = query.preview(_intent(tmp_path, **{field: "anything"}))
        assert rejected["outcome"] == "needs_input"
        assert f"unknown:{field}" in rejected["missingFields"]

    derived = query.preview(_intent(tmp_path))
    assert derived["outcome"] == "preview"
    assert derived["normalizedRequest"]["vertical"] == "travel"
    assert derived["normalizedRequest"]["regionRef"] == "china"
    assert derived["normalizedRequest"]["lifecycle"] == "research"


def test_fresh_retry_conflict_and_unknown_carrier_remain_needs_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_handoff(
        monkeypatch,
        {
            "handoff.json": _handoff_document(),
            "handoff-unknown-region.json": _handoff_document(
                regionRef="__unknown_region__", scope="unknown-region"
            ),
        },
    )
    query = WorkRequestPreviewQuery()
    conflict = query.preview(
        _intent(
            tmp_path,
            predecessorExecutionIdsByCarrier={"homepage": "old"},
        )
    )
    unknown = query.preview(
        _intent(tmp_path, externalInputRefsByCarrier={"podcast": []})
    )
    unknown_region = query.preview(
        _intent(
            tmp_path,
            preAcquisitionHandoffRef=str(
                tmp_path / "handoff-unknown-region.json"
            ),
        )
    )
    inactive_external = query.preview(
        _intent(
            tmp_path,
            externalInputRefsByCarrier={"video": []},
        )
    )
    malformed_external = query.preview(
        _intent(
            tmp_path,
            externalInputRefsByCarrier={"homepage": {}},
        )
    )
    retry_without_lineage = query.preview(_intent(tmp_path, mode="retry"))
    retired_reconciliation = query.preview(
        _intent(
            tmp_path,
            mode="retry",
            predecessorExecutionIdsByCarrier={"homepage": "old"},
            predecessorReconciliationReceiptRef=str(
                tmp_path / "reconciliation.json"
            ),
        )
    )

    assert conflict["outcome"] == "needs_input"
    assert "freshRetryConflict" in conflict["missingFields"]
    assert unknown["outcome"] == "needs_input"
    assert unknown["missingFields"] == ["unknownCarrier:podcast"]
    assert unknown_region["outcome"] == "needs_input"
    assert unknown_region["missingFields"] == [
        "unknownRegionRef:__unknown_region__"
    ]
    assert inactive_external["outcome"] == "needs_input"
    assert inactive_external["missingFields"] == [
        "externalInputInactiveCarrier:video"
    ]
    assert malformed_external["outcome"] == "needs_input"
    assert malformed_external["missingFields"] == [
        "externalInputRefsByCarrier:homepage"
    ]
    assert retry_without_lineage["outcome"] == "needs_input"
    assert retry_without_lineage["missingFields"] == [
        "predecessorExecutionIdsByCarrier",
    ]
    assert retired_reconciliation["outcome"] == "needs_input"
    assert retired_reconciliation["missingFields"] == [
        "unknown:predecessorReconciliationReceiptRef"
    ]


def test_every_unsettled_compile_outcome_carries_recovery_and_reentry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(work_request_contract, "dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "canonical_dependency_ref", lambda path: path.name
    )
    _install_handoff(
        monkeypatch,
        {
            "handoff.json": _handoff_document(),
            "handoff-broken.json": _handoff_document(
                workloadTargets={}, sourceSelection={}
            ),
        },
    )
    query = WorkRequestPreviewQuery()
    handoff_ref = str(tmp_path / "handoff.json")

    settled = query.preview(_intent(tmp_path))
    assert settled["outcome"] == "preview"
    assert settled["nextAction"] == "none"
    assert settled["reentryRef"] is None

    needs_input = query.preview(_intent(tmp_path, mode="retry"))
    assert needs_input["outcome"] == "needs_input"
    assert needs_input["nextAction"] == "supply_input"
    assert needs_input["reentryRef"] == {
        "requestDigest": needs_input["requestDigest"],
        "preAcquisitionHandoffRef": handoff_ref,
    }

    blocked = query.preview(
        _intent(
            tmp_path,
            preAcquisitionHandoffRef=str(tmp_path / "handoff-broken.json"),
        )
    )
    assert blocked["outcome"] == "blocked"
    # 依赖不可读时意图本身没问题，恢复动作指向修证据而不是改意图。
    assert blocked["nextAction"] == "repair_evidence"
    assert blocked["reentryRef"]["preAcquisitionHandoffRef"] == str(
        tmp_path / "handoff-broken.json"
    )

    writer = WorkRequestCommandWriter(output_root=tmp_path / "output")
    canceled = writer.cancel(
        _intent(tmp_path), preview_digest=str(settled["requestDigest"])
    )
    assert canceled["outcome"] == "canceled"
    assert canceled["nextAction"] == "recompile_intent"
    assert canceled["reentryRef"]["requestDigest"] == settled["requestDigest"]

    drifted = writer.confirm(
        _intent(tmp_path), preview_digest="sha256:" + "0" * 64
    )
    assert drifted["error"]["code"] == "DATA.WORK_REQUEST.PREVIEW_DRIFT"
    assert drifted["nextAction"] == "recompile_intent"


def test_undeclared_handoff_stays_absent_in_the_reentry_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 意图不完整正是 needs_input 存在的理由，所以「没声明 handoff」是合法缺席；
    # 它必须与「声明了一个空 ref」区分开，不能被写成空字符串带进重入引用。
    _install_handoff(monkeypatch, {"handoff.json": _handoff_document()})
    intent = _intent(tmp_path)
    del intent["preAcquisitionHandoffRef"]

    result = WorkRequestPreviewQuery().preview(intent)

    assert result["outcome"] == "needs_input"
    assert "preAcquisitionHandoffRef" in result["missingFields"]
    assert result["reentryRef"]["preAcquisitionHandoffRef"] is None


def test_source_providers_are_projected_from_the_handoff_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(work_request_contract, "dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "canonical_dependency_ref", lambda path: path.name
    )
    _install_handoff(
        monkeypatch,
        {
            "handoff.json": _handoff_document(),
            "handoff-empty-providers.json": _handoff_document(
                sourceSelection={
                    "homepage": {"mode": "site_primary", "providers": []}
                }
            ),
        },
    )
    query = WorkRequestPreviewQuery()

    projected = query.preview(_intent(tmp_path))
    empty = query.preview(
        _intent(
            tmp_path,
            preAcquisitionHandoffRef=str(tmp_path / "handoff-empty-providers.json"),
        )
    )

    assert projected["outcome"] == "preview"
    assert projected["normalizedRequest"]["sourceSelection"] == {
        "homepage": {"mode": "site_primary", "providers": ["wikipedia"]}
    }
    assert empty["outcome"] == "blocked"
    assert "SOURCE_SELECTION_INVALID" in empty["error"]["message"]


def test_dependency_set_binds_source_revision_and_external_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_digest = "sha256:" + "b" * 64
    execution_digest = "sha256:" + "c" * 64
    catalog_digest = "sha256:" + "d" * 64
    source_revision = content_source_revision(
        source_digest=source_digest,
        entity_catalog_digest=catalog_digest,
    )
    entity_root = tmp_path / "quwoquan_data/reference/travel/entities/china"
    entity_root.mkdir(parents=True)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    (evidence_root / "candidate.json").write_text("{}\n", encoding="utf-8")
    capacity = tmp_path / "capacity.json"
    handoff = tmp_path / "handoff.json"
    pool = tmp_path / "pool.json"
    distribution = tmp_path / "distribution.yaml"
    carrier_policy = tmp_path / "carrier-policy.yaml"
    for path in (capacity, handoff, distribution, carrier_policy):
        path.write_text("stable\n", encoding="utf-8")
    plan = {
        "poolId": "pool-1",
        "targetScale": "WORKLOAD",
        "workloadMode": "explicit",
        "activeCarriers": ["homepage"],
        "workloadTargets": {"homepage": 1},
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": catalog_digest,
        "planDigest": DIGEST,
    }
    pool.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        work_request_dependencies,
        "current_source_definition_snapshot",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: {"digest": source_digest}
        ),
    )
    monkeypatch.setattr(
        work_request_dependencies,
        "current_execution_bundle_identity",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: {"digest": execution_digest}
        ),
    )
    monkeypatch.setattr(
        work_request_dependencies, "entity_catalog_digest", lambda _ref: catalog_digest
    )
    monkeypatch.setattr(
        work_request_dependencies,
        "validate_scale_source_pool_evidence",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        work_request_dependencies, "CARRIER_POLICY_PATH", carrier_policy
    )
    monkeypatch.setattr(
        work_request_dependencies, "DISTRIBUTION_POLICY_PATH", distribution
    )
    monkeypatch.setattr(
        work_request_dependencies, "carrier_policy_digest", lambda: DIGEST
    )
    monkeypatch.setattr(
        work_request_dependencies,
        "bind_external_input_refs",
        lambda *_args, **_kwargs: [{"refDigest": "sha256:" + "e" * 64}],
    )
    intent = _intent(
        tmp_path,
        externalInputRefsByCarrier={"homepage": [{"kind": "image"}]},
        acquisitionRootRef=str(tmp_path),
    )
    bindings = work_request_dependencies.dependency_bindings(
        intent,
        scale="M1",
        workload_mode="explicit",
        workloads={"homepage": 1},
        vertical="travel",
        region_ref="china",
    )

    assert bindings["dependencies"]["sourceDefinition"]["digest"] == source_digest
    assert bindings["dependencies"]["executionBundle"]["digest"] == execution_digest
    assert "externalInputs:homepage" in bindings["dependencies"]

    capacity.write_text("changed\n", encoding="utf-8")
    changed = work_request_dependencies.dependency_bindings(
        intent,
        scale="M1",
        workload_mode="explicit",
        workloads={"homepage": 1},
        vertical="travel",
        region_ref="china",
    )
    assert changed["dependencySetDigest"] != bindings["dependencySetDigest"]

    plan["sourceRevision"] = "sha256:" + "f" * 64
    pool.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="identity or workload binding drift"):
        work_request_dependencies.dependency_bindings(
            intent,
            scale="M1",
            workload_mode="explicit",
            workloads={"homepage": 1},
            vertical="travel",
            region_ref="china",
        )


def test_retry_terminal_binding_closes_blocked_receipt_and_state_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    tasks_root = output_root / "data" / "tasks"
    execution_id = "20260901--travel-homepage-workload--china--scale-001"
    execution_root = tasks_root / execution_id
    receipt_path = execution_root / "_shared/receipts/002-sources.json"
    state_path = execution_root / "_shared/execution_state.json"
    receipt_path.parent.mkdir(parents=True)
    receipt = {
        "executionId": execution_id,
        "sequence": 2,
        "stage": "sources",
        "verdict": "blocked",
        "next": "sources",
        "recordedAt": "2026-09-01T00:00:02Z",
    }
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    receipt_digest = work_request_dependencies.file_digest(receipt_path)
    state = {
        "schema": "quwoquan.content.execution_state_projection",
        "executionId": execution_id,
        "completed": ["0.plan"],
        "status": "manual_required",
        "latestStage": "sources",
        "next": "sources",
        "latestReceiptRef": "_shared/receipts/002-sources.json",
        "latestReceiptDigest": receipt_digest,
        "updatedAt": "2026-09-01T00:00:02Z",
    }
    state_path.write_text(
        json.dumps(state, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(paths, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tasks_root)

    def validate(
        candidate_execution_id: str,
        candidate_receipt: Path,
        *,
        verify_current_workflow: bool,
    ) -> dict[str, object]:
        assert candidate_execution_id == execution_id
        assert candidate_receipt == receipt_path
        assert verify_current_workflow is False
        return dict(receipt)

    monkeypatch.setattr(
        work_request_dependencies,
        "validate_stage_receipt_authority",
        validate,
    )
    rows = work_request_dependencies._predecessor_terminal_dependency_rows(
        {"predecessorExecutionIdsByCarrier": {"homepage": execution_id}},
        {"homepage": 1},
    )

    assert rows == {
        "predecessorTerminalReceipt:homepage": {
            "ref": (
                f"data/tasks/{execution_id}/_shared/receipts/"
                "002-sources.json"
            ),
            "digest": receipt_digest,
        },
        "predecessorExecutionState:homepage": {
            "ref": f"data/tasks/{execution_id}/_shared/execution_state.json",
            "digest": work_request_dependencies.file_digest(state_path),
        },
    }

    receipt["verdict"] = "pass"
    with pytest.raises(ValueError, match="requires canonical workflow_drift"):
        work_request_dependencies._predecessor_terminal_dependency_rows(
            {"predecessorExecutionIdsByCarrier": {"homepage": execution_id}},
            {"homepage": 1},
        )

    receipt["verdict"] = "blocked"
    state["latestReceiptDigest"] = "sha256:" + "0" * 64
    state_path.write_text(
        json.dumps(state, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="current receipt-derived projection"):
        work_request_dependencies._predecessor_terminal_dependency_rows(
            {"predecessorExecutionIdsByCarrier": {"homepage": execution_id}},
            {"homepage": 1},
        )


def test_preview_digest_uses_portable_governed_dependency_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)
    (tmp_path / "quwoquan_data/reference/travel/entities/china").mkdir(
        parents=True
    )
    monkeypatch.setattr(work_request_contract, "dependency_bindings", _dependencies)
    _install_handoff(monkeypatch, {"handoff.json": _handoff_document()})
    relative_refs = {
        "capacityCalibrationReceiptRef": "quwoquan_data/capacity.json",
        "preAcquisitionHandoffRef": "quwoquan_data/handoff.json",
        "scaleSourcePoolPlanRef": "quwoquan_data/pool.json",
        "sourcePoolEvidenceRootRef": "quwoquan_data/evidence",
    }
    absolute_refs = {
        key: str(tmp_path / value) for key, value in relative_refs.items()
    }
    base = {
        "mode": "fresh",
    }

    relative = WorkRequestPreviewQuery().preview({**base, **relative_refs})
    absolute = WorkRequestPreviewQuery().preview({**base, **absolute_refs})

    assert relative["outcome"] == "preview"
    assert absolute["outcome"] == "preview"
    assert relative["requestDigest"] == absolute["requestDigest"]
    assert relative["normalizedRequest"]["scaleSourcePoolPlanRef"] == (
        "quwoquan_data/pool.json"
    )


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t2
WORKFLOW_DRIFT_EXECUTION_ID = "20260901--travel-article-workflow-drift--china--scale-016"


def _workflow_drift_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, dict[str, object]]:
    output_root = tmp_path / "output"
    tasks_root = output_root / "data/tasks"
    root = tasks_root / WORKFLOW_DRIFT_EXECUTION_ID
    receipt_path = root / "_shared/receipts/006-4.draft.json"
    state_path = root / "_shared/execution_state.json"
    supersession_path = root / "_shared/reconciliation/supersession-workflow.json"
    receipt_path.parent.mkdir(parents=True)
    supersession_path.parent.mkdir(parents=True)
    receipt = {
        "executionId": WORKFLOW_DRIFT_EXECUTION_ID,
        "sequence": 6,
        "stage": "4.draft",
        "verdict": "pass",
        "next": "5.review",
        "recordedAt": "2026-09-01T00:00:06Z",
    }
    receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    receipt_digest = work_request_dependencies.file_digest(receipt_path)
    state = {
        "schema": "quwoquan.content.execution_state_projection",
        "executionId": WORKFLOW_DRIFT_EXECUTION_ID,
        "completed": [
            "0.plan", "sources", "1.download", "2.quality", "3.compose", "4.draft"
        ],
        "status": "running",
        "latestStage": "4.draft",
        "next": "5.review",
        "latestReceiptRef": "_shared/receipts/006-4.draft.json",
        "latestReceiptDigest": receipt_digest,
        "updatedAt": receipt["recordedAt"],
    }
    state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
    supersession = {
        "decision": "superseded",
        "reason": "workflow_drift",
        "receiptDigest": "sha256:" + "9" * 64,
    }
    supersession_path.write_text(json.dumps(supersession) + "\n", encoding="utf-8")
    monkeypatch.setattr(paths, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tasks_root)
    monkeypatch.setattr(
        work_request_dependencies,
        "validate_stage_receipt_authority",
        lambda _execution_id, _path, *, verify_current_workflow: dict(receipt),
    )
    return root, receipt_path, state_path, supersession


def test_retry_accepts_only_workflow_drift_supersession_and_binds_both_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _receipt_path, state_path, supersession = _workflow_drift_predecessor(
        tmp_path, monkeypatch
    )
    supersession_path = root / "_shared/reconciliation/supersession-workflow.json"
    terminal = SimpleNamespace(
        decision="superseded",
        receipt=supersession,
        path=supersession_path,
    )
    monkeypatch.setattr(
        work_request_dependencies,
        "load_terminal_execution_evidence",
        lambda _root: terminal,
    )

    rows = work_request_dependencies._predecessor_terminal_dependency_rows(
        {"predecessorExecutionIdsByCarrier": {"article": WORKFLOW_DRIFT_EXECUTION_ID}},
        {"article": 1},
    )

    assert rows["predecessorTerminalReceipt:article"] == {
        "ref": (
            f"data/tasks/{WORKFLOW_DRIFT_EXECUTION_ID}/_shared/reconciliation/"
            "supersession-workflow.json"
        ),
        "digest": work_request_dependencies.file_digest(supersession_path),
    }
    assert rows["predecessorExecutionState:article"]["digest"] == (
        work_request_dependencies.file_digest(state_path)
    )

    terminal.receipt["reason"] = "source_drift"
    with pytest.raises(ValueError, match="requires canonical workflow_drift"):
        work_request_dependencies._predecessor_terminal_dependency_rows(
            {"predecessorExecutionIdsByCarrier": {"article": WORKFLOW_DRIFT_EXECUTION_ID}},
            {"article": 1},
        )


def test_retry_workflow_drift_rejects_missing_receipt_and_state_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _receipt_path, state_path, supersession = _workflow_drift_predecessor(
        tmp_path, monkeypatch
    )
    supersession_path = root / "_shared/reconciliation/supersession-workflow.json"
    monkeypatch.setattr(
        work_request_dependencies,
        "load_terminal_execution_evidence",
        lambda _root: None,
    )
    with pytest.raises(ValueError, match="requires canonical workflow_drift"):
        work_request_dependencies._predecessor_terminal_dependency_rows(
            {"predecessorExecutionIdsByCarrier": {"article": WORKFLOW_DRIFT_EXECUTION_ID}},
            {"article": 1},
        )

    terminal = SimpleNamespace(
        decision="superseded",
        receipt=supersession,
        path=supersession_path,
    )
    monkeypatch.setattr(
        work_request_dependencies,
        "load_terminal_execution_evidence",
        lambda _root: terminal,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["latestReceiptDigest"] = "sha256:" + "0" * 64
    state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="current receipt-derived projection"):
        work_request_dependencies._predecessor_terminal_dependency_rows(
            {"predecessorExecutionIdsByCarrier": {"article": WORKFLOW_DRIFT_EXECUTION_ID}},
            {"article": 1},
        )



def test_retry_workflow_drift_rechecks_terminal_evidence_for_toctou(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _receipt_path, _state_path, supersession = _workflow_drift_predecessor(
        tmp_path, monkeypatch
    )
    supersession_path = root / "_shared/reconciliation/supersession-workflow.json"
    valid = SimpleNamespace(
        decision="superseded",
        receipt=supersession,
        path=supersession_path,
    )
    calls = 0

    def changing_terminal(_root: Path) -> object | None:
        nonlocal calls
        calls += 1
        return valid if calls == 1 else None

    monkeypatch.setattr(
        work_request_dependencies,
        "load_terminal_execution_evidence",
        changing_terminal,
    )
    with pytest.raises(ValueError, match="changed during validation"):
        work_request_dependencies._predecessor_terminal_dependency_rows(
            {"predecessorExecutionIdsByCarrier": {"article": WORKFLOW_DRIFT_EXECUTION_ID}},
            {"article": 1},
        )
    assert calls == 2
