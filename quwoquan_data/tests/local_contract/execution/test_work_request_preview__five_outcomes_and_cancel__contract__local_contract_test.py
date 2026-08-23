# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-001.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t1
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.controller.execute import (
    pre_acquisition_handoff as handoff_api,
)
from content.execution.planning import work_request_contract
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
    monkeypatch.setattr(work_request_contract, "_dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "_canonical_ref", lambda path: path.name
    )
    _install_handoff(
        monkeypatch,
        {
            "handoff.json": _handoff_document(),
            "handoff-2.json": _handoff_document(
                scale="M2", workloadTargets={"homepage": 2}
            ),
            "handoff-broken.json": _handoff_document(workloadTargets={}),
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

    monkeypatch.setattr(work_request_contract, "_dependency_bindings", unavailable)
    blocked = preview_query.preview(_intent(tmp_path))
    assert blocked["outcome"] == "blocked"
    assert blocked["error"]["code"] == "DATA.WORK_REQUEST.DEPENDENCY_UNAVAILABLE"

    monkeypatch.setattr(work_request_contract, "_dependency_bindings", _dependencies)
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
    monkeypatch.setattr(work_request_contract, "_dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "_canonical_ref", lambda path: path.name
    )
    _install_handoff(monkeypatch, {"handoff.json": _handoff_document()})
    query = WorkRequestPreviewQuery()

    for field in ("vertical", "regionRef", "topic", "lifecycle", "workloads"):
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
        "predecessorReconciliationReceiptRef",
    ]


def test_undeclared_source_provider_fails_closed_at_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(work_request_contract, "_dependency_bindings", _dependencies)
    monkeypatch.setattr(
        work_request_contract, "_canonical_ref", lambda path: path.name
    )
    _install_handoff(monkeypatch, {"handoff.json": _handoff_document()})
    query = WorkRequestPreviewQuery()

    undeclared = query.preview(
        _intent(tmp_path, sourceProviders=["__undeclared_provider__"])
    )

    assert undeclared["outcome"] == "needs_input"
    assert any(
        issue.startswith("undeclaredSourceProvider:")
        for issue in undeclared["missingFields"]
    )


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
        work_request_contract,
        "current_source_definition_snapshot",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: {"digest": source_digest}
        ),
    )
    monkeypatch.setattr(
        work_request_contract,
        "current_execution_bundle_identity",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: {"digest": execution_digest}
        ),
    )
    monkeypatch.setattr(
        work_request_contract, "entity_catalog_digest", lambda _ref: catalog_digest
    )
    monkeypatch.setattr(
        work_request_contract,
        "validate_scale_source_pool_evidence",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        work_request_contract, "CARRIER_POLICY_PATH", carrier_policy
    )
    monkeypatch.setattr(
        work_request_contract, "DISTRIBUTION_POLICY_PATH", distribution
    )
    monkeypatch.setattr(
        work_request_contract, "carrier_policy_digest", lambda: DIGEST
    )
    monkeypatch.setattr(
        work_request_contract,
        "bind_external_input_refs",
        lambda *_args, **_kwargs: [{"refDigest": "sha256:" + "e" * 64}],
    )
    intent = _intent(
        tmp_path,
        externalInputRefsByCarrier={"homepage": [{"kind": "image"}]},
        acquisitionRootRef=str(tmp_path),
    )
    bindings = work_request_contract._dependency_bindings(
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
    changed = work_request_contract._dependency_bindings(
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
        work_request_contract._dependency_bindings(
            intent,
            scale="M1",
            workload_mode="explicit",
            workloads={"homepage": 1},
            vertical="travel",
            region_ref="china",
        )


def test_preview_digest_uses_portable_governed_dependency_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)
    (tmp_path / "quwoquan_data/reference/travel/entities/china").mkdir(
        parents=True
    )
    monkeypatch.setattr(work_request_contract, "_dependency_bindings", _dependencies)
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
