# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t7
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/work-request-compilation/spec.md#gwt-002.t8
"""GWT-002：四类 scope、输入缺口与来源闭集都由 confirmed handoff 单轨判定。"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from content.execution.controller.execute import (
    pre_acquisition_handoff as handoffs,
)
from content.execution.planning import work_request_contract
from content.execution.planning.work_request_contract import WorkRequestPreviewQuery
from core.source_digest import ExecutionBundleIdentity, SourceDefinitionSnapshot

CATALOG = "sha256:" + "c" * 64
KNOWN_TOPIC = "Topic/旅行"
UNMAPPABLE_TOPIC = "Topic/__不在_canonical_taxonomy_的主题__"
TARGETS = {"homepage": 1}
SELECTION = {"homepage": {"mode": "site_primary", "providers": ["wikipedia"]}}


def _handoff_kwargs(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "handoff_id": "gwt002",
        "handoff_revision": 1,
        "supersedes_handoff": None,
        "scale": "M1",
        "vertical": "travel",
        "lifecycle": "research",
        "scope_type": "region",
        "region_ref": "china",
        "primary_topic_ref": None,
        "related_topic_refs": (),
        "source_selection": SELECTION,
        "run_date": "20260827",
        "campaign_sequence": 1,
        "campaign_retry_of": None,
        "source_digest": SourceDefinitionSnapshot(
            digest="sha256:" + "a" * 64
        ).to_document(),
        "execution_bundle": ExecutionBundleIdentity(
            digest="sha256:" + "d" * 64
        ).to_document(),
        "entity_catalog_digest": CATALOG,
        "workload_targets": TARGETS,
    }
    document.update(overrides)
    return document


def _revision_count(output_root: Path) -> int:
    root = output_root / "data/local/workspace/content-pre-acquisition-handoffs"
    return len(list(root.rglob("revision-*.json"))) if root.is_dir() else 0


# t1 四类 scope 各按自身条件必填判定，互斥维度不存在通过路径。
def test_four_scope_types_each_require_exactly_their_own_dimensions(
    tmp_path: Path,
) -> None:
    accepted = {
        "vertical": {"scope_type": "vertical", "region_ref": None},
        "region": {"scope_type": "region", "region_ref": "china"},
        "topic": {
            "scope_type": "topic",
            "region_ref": None,
            "primary_topic_ref": KNOWN_TOPIC,
        },
        "region_topic": {
            "scope_type": "region_topic",
            "region_ref": "china",
            "primary_topic_ref": KNOWN_TOPIC,
        },
    }
    for name, overrides in accepted.items():
        handoff = handoffs.build_pre_acquisition_handoff(
            **_handoff_kwargs(**overrides),
            output_root=tmp_path / f"ok-{name}",
        )
        assert handoff["scopeType"] == overrides["scope_type"]

    mutually_exclusive = (
        # vertical scope 携带 region 或 topic
        {"scope_type": "vertical", "region_ref": "china"},
        {
            "scope_type": "vertical",
            "region_ref": None,
            "primary_topic_ref": KNOWN_TOPIC,
        },
        # region scope 携带 topic
        {
            "scope_type": "region",
            "region_ref": "china",
            "primary_topic_ref": KNOWN_TOPIC,
        },
        # topic scope 携带 region
        {
            "scope_type": "topic",
            "region_ref": "china",
            "primary_topic_ref": KNOWN_TOPIC,
        },
        # region_topic 缺任一维度
        {"scope_type": "region_topic", "region_ref": "china"},
        {
            "scope_type": "region_topic",
            "region_ref": None,
            "primary_topic_ref": KNOWN_TOPIC,
        },
    )
    for index, overrides in enumerate(mutually_exclusive):
        with pytest.raises(handoffs.PreAcquisitionHandoffError) as failure:
            handoffs.build_pre_acquisition_handoff(
                **_handoff_kwargs(**overrides),
                output_root=tmp_path / f"reject-{index}",
            )
        assert "PRE_ACQUISITION_SCOPE_INVALID" in str(failure.value)


# t2/t3 缺 vertical 只能显式要求确认，确认前 handoff revision 数为零。
def test_missing_vertical_never_silently_defaults_and_writes_no_revision(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "missing-vertical"

    with pytest.raises(handoffs.PreAcquisitionHandoffError) as failure:
        handoffs.write_pre_acquisition_handoff(
            **_handoff_kwargs(vertical=""),
            output_root=output_root,
        )

    message = str(failure.value)
    assert "PRE_ACQUISITION_VERTICAL_REQUIRED" in message
    assert "silent defaults are forbidden" in message
    assert _revision_count(output_root) == 0


# t4 无法映射 canonical taxonomy 的相关主题点名判否，不合成自由文本主题身份。
def test_unmappable_related_topic_is_named_and_never_synthesized(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "unknown-topic"

    with pytest.raises(handoffs.PreAcquisitionHandoffError) as failure:
        handoffs.write_pre_acquisition_handoff(
            **_handoff_kwargs(related_topic_refs=(UNMAPPABLE_TOPIC,)),
            output_root=output_root,
        )

    message = str(failure.value)
    assert "PRE_ACQUISITION_TOPIC_UNKNOWN" in message
    assert UNMAPPABLE_TOPIC in message
    assert _revision_count(output_root) == 0

    with pytest.raises(handoffs.PreAcquisitionHandoffError) as invalid:
        handoffs.build_pre_acquisition_handoff(
            **_handoff_kwargs(
                scope_type="topic",
                region_ref=None,
                primary_topic_ref="西湖游玩攻略",
            ),
            output_root=output_root,
        )
    assert "PRE_ACQUISITION_TOPIC_INVALID" in str(invalid.value)


# t5 闭集之外的来源在 handoff 冻结即点名 fail closed，不推迟到执行阶段。
def test_provider_outside_the_registry_closure_fails_closed_and_is_named(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "undeclared-provider"

    with pytest.raises(handoffs.PreAcquisitionHandoffError) as failure:
        handoffs.write_pre_acquisition_handoff(
            **_handoff_kwargs(
                source_selection={
                    "homepage": {
                        "mode": "site_primary",
                        "providers": ["__undeclared_provider__"],
                    }
                }
            ),
            output_root=output_root,
        )

    message = str(failure.value)
    assert "PRE_ACQUISITION_SOURCE_SELECTION_UNDECLARED" in message
    assert "__undeclared_provider__" in message
    assert _revision_count(output_root) == 0


# t6 跨 lane 借用另一 lane 的闭集同样判否。
def test_provider_borrowed_from_another_lane_closure_is_rejected(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "cross-lane-provider"

    # `adobe_stock` 属 image lane 闭集，homepage lane 不得借用。
    with pytest.raises(handoffs.PreAcquisitionHandoffError) as cross_lane:
        handoffs.write_pre_acquisition_handoff(
            **_handoff_kwargs(
                source_selection={
                    "homepage": {
                        "mode": "site_primary",
                        "providers": ["adobe_stock"],
                    }
                }
            ),
            output_root=output_root,
        )

    message = str(cross_lane.value)
    assert "PRE_ACQUISITION_SOURCE_SELECTION_UNDECLARED" in message
    assert "adobe_stock" in message
    assert _revision_count(output_root) == 0


# t8 对同一 demand 字段的独立调用方输入路径为零，`sourceProviders` 只作为逐载体投影。
def test_work_request_accepts_no_independent_demand_input_path() -> None:
    demand_fields = (
        "vertical",
        "regionRef",
        "scopeType",
        "scope",
        "primaryTopicRef",
        "relatedTopicRefs",
        "lifecycle",
        "workloads",
        "workloadTargets",
        "sourceProviders",
        "sourceSelection",
    )

    leaked = sorted(
        field
        for field in demand_fields
        if field in work_request_contract._ALLOWED_INPUTS
    )
    assert leaked == []
    assert "preAcquisitionHandoffRef" in work_request_contract._REQUIRED_INPUTS

    from content.execution.campaign import request_envelope

    writer_signature = inspect.signature(request_envelope.write_scale_envelopes)
    assert "source_providers" not in writer_signature.parameters


# t7 confirmed handoff 的 ref+digest 是 WorkRequest 派生 demand 的唯一输入。
def test_work_request_projects_demand_only_from_the_confirmed_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = {
        "vertical": "travel",
        "regionRef": "china",
        "lifecycle": "research",
        "scopeType": "region",
        "scope": "china",
        "primaryTopicRef": None,
        "relatedTopicRefs": [],
        "scale": "M1",
        "workloadTargets": dict(TARGETS),
        "sourceSelection": {
            carrier: dict(row) for carrier, row in SELECTION.items()
        },
    }
    monkeypatch.setattr(
        handoffs, "load_pre_acquisition_handoff", lambda _path: dict(document)
    )
    monkeypatch.setattr(
        work_request_contract,
        "dependency_bindings",
        lambda _intent, **_kwargs: {
            "source": {"digest": "sha256:" + "a" * 64},
            "executionBundle": {"digest": "sha256:" + "d" * 64},
            "entityCatalogDigest": CATALOG,
            "sourcePool": {
                "poolId": "pool-gwt002",
                "targetScale": "WORKLOAD",
                "workloadMode": "explicit",
                "activeCarriers": ["homepage"],
                "workloadTargets": dict(TARGETS),
                "sourceRevision": "sha256:" + "0" * 64,
                "planDigest": "sha256:" + "4" * 64,
            },
            "dependencies": {"sourcePool": {"ref": "pool.json", "digest": CATALOG}},
            "dependencySetDigest": CATALOG,
        },
    )
    monkeypatch.setattr(
        work_request_contract, "canonical_dependency_ref", lambda path: Path(path).name
    )

    preview = WorkRequestPreviewQuery().preview(
        {
            "mode": "fresh",
            "preAcquisitionHandoffRef": str(tmp_path / "handoff.json"),
            "scaleSourcePoolPlanRef": str(tmp_path / "pool.json"),
            "sourcePoolEvidenceRootRef": str(tmp_path / "evidence"),
        }
    )

    assert preview["outcome"] == "preview"
    normalized = preview["normalizedRequest"]
    assert normalized["vertical"] == "travel"
    assert normalized["scopeType"] == "region"
    assert normalized["lifecycle"] == "research"
    assert normalized["workloads"] == dict(TARGETS)
    assert normalized["sourceSelection"] == {
        "homepage": {"mode": "site_primary", "providers": ["wikipedia"]}
    }
