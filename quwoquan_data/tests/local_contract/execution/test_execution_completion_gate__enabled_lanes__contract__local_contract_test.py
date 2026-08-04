from __future__ import annotations

import pytest

from core.control_types import ContentType, ExecutionStage, ExecutionStateStatus, StageStatus
from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from content.execution.agent import auto_research
from content.execution.context import ExecutionContext
from content.execution.controller import completion as execution_completion
from content.execution.controller import stage_download_build
from content.execution.recovery import download_repair
from content.execution.recovery import download_unresolved
from content.execution.recovery import post_recovery
from content.execution.recovery import stage_reset
from content.execution import target_integrity
from content.execution import source_ready_scope
from content.homepage import homepage
from core.io import write_json
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def _context(*, entity_ids: list[str] | None = None) -> ExecutionContext:
    resolved_entity_ids = entity_ids or ["测试实体乙"]
    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-099"
    return ExecutionContext(
        execution_id=execution_id,
        entity_ids=resolved_entity_ids,
        spec=ExecutionFixtureBuilder(
            execution_id,
            targets=tuple(
                {"name": entity_id, "entityType": "地点/景区"}
                for entity_id in resolved_entity_ids
            ),
        ).spec(),
        managed=True,
    )


def test_homepage_only_completion_ignores_disabled_article_and_image_lanes(monkeypatch):
    ctx = _context()
    monkeypatch.setattr(
        "content.execution.workspace.load_execution_manifest",
        lambda _execution_id: {"selectionPolicy": "frozen"},
    )
    monkeypatch.setattr(auto_research, "_download_auto_research_lanes", lambda _ctx: {"homepage"})
    from content.execution import readiness_audit

    monkeypatch.setattr(
        readiness_audit,
        "audit_execution_readiness",
        lambda *_args, **_kwargs: {
            "failedLaneCount": 0,
            "lanePassed": {
                ContentType.HOMEPAGE.value: 1,
                ContentType.ARTICLE.value: 0,
                ContentType.IMAGE.value: 0,
                ContentType.VIDEO.value: 0,
            },
            "targetCount": 1,
        },
    )

    assert execution_completion.execution_completion_issues(
        ctx,
        ExecutionFixtureBuilder(ctx.execution_id).state(),
    ) == []


def test_video_completion_accepts_video_lane_readiness(monkeypatch):
    execution_id = "20260716--travel-video-coverage--test-region-a--pilot-099"
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=["测试实体乙"],
        spec=ExecutionFixtureBuilder(execution_id).spec(),
        managed=True,
    )
    monkeypatch.setattr(
        "content.execution.workspace.load_execution_manifest",
        lambda _execution_id: {"selectionPolicy": "frozen"},
    )
    monkeypatch.setattr(
        auto_research,
        "_download_auto_research_lanes",
        lambda _ctx: {ContentType.VIDEO.value},
    )
    from content.execution import readiness_audit

    monkeypatch.setattr(
        readiness_audit,
        "audit_execution_readiness",
        lambda *_args, **_kwargs: {
            "failedLaneCount": 0,
            "lanePassed": {ContentType.VIDEO.value: 1},
            "targetCount": 1,
        },
    )

    assert execution_completion.execution_completion_issues(
        ctx,
        ExecutionFixtureBuilder(execution_id).state(),
    ) == []


def test_readiness_quota_projection_covers_every_content_type():
    from content.execution.readiness_audit import _quota_by_lane

    execution_id = "20260716--travel-video-coverage--test-region-a--pilot-100"
    spec = ExecutionFixtureBuilder(execution_id).spec()

    assert _quota_by_lane(spec) == {
        content_type.value: spec.content.quotas.for_type(content_type)
        for content_type in ContentType
    }
    assert _quota_by_lane(spec)[ContentType.VIDEO.value] == 1


def test_download_plan_availability_persists_frozen_target_failure(monkeypatch, tmp_path):
    ctx = _context(entity_ids=["测试实体甲"])
    persisted: dict[str, object] = {}
    monkeypatch.setattr(download_unresolved, "load_execution_state", lambda *_args: {})
    monkeypatch.setattr(download_unresolved, "_pending_download_repair_unresolved", lambda _ctx: {})
    monkeypatch.setattr(download_unresolved, "_download_plan_repair_exhausted_unresolved", lambda *_args: {})
    monkeypatch.setattr(download_unresolved, "_download_artifact_issues", lambda _ctx: {})
    monkeypatch.setattr(download_unresolved, "execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        download_unresolved,
        "write_json",
        lambda path, data: persisted.update({"path": path, "data": data}),
    )
    report = download_unresolved._write_download_availability(
        ctx,
        {"测试实体甲": {"homepage": ["homepage source needs repair"]}},
    )

    assert persisted["path"] == tmp_path / "_shared" / "source_unavailable_targets.json"
    assert persisted["data"] == report
    assert report["readyTargets"] == []
    assert report["ineligibleTargets"][0]["entityId"] == "测试实体甲"


def test_download_plan_availability_ignores_pre_fetch_artifact_gate(monkeypatch, tmp_path):
    ctx = _context(entity_ids=["计划就绪景区", "计划缺口景区"])
    artifact_issue = data_issue(
        DataIssueCode.SOURCE_MISSING,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref="计划就绪景区",
        lane=DataIssueLane.VIDEO,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="sources directory missing",
    )
    persisted: dict[str, object] = {}
    monkeypatch.setattr(download_unresolved, "_pending_download_repair_unresolved", lambda _ctx: {})
    monkeypatch.setattr(
        download_unresolved,
        "_download_plan_repair_exhausted_unresolved",
        lambda *_args: {"计划缺口景区": {"video": ["video research shortfall"]}},
    )
    monkeypatch.setattr(
        download_unresolved,
        "_download_artifact_issues",
        lambda _ctx: {
            "计划就绪景区": (artifact_issue,),
            "计划缺口景区": (artifact_issue,),
        },
    )
    monkeypatch.setattr(download_unresolved, "execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        download_unresolved,
        "write_json",
        lambda path, data: persisted.update({"path": path, "data": data}),
    )

    report = download_unresolved._write_download_availability(
        ctx,
        {"计划缺口景区": {"video": ["video research shortfall"]}},
        source="download_plan",
    )

    assert report["source"] == "download_plan"
    assert report["readyTargets"] == ["计划就绪景区"]
    assert report["readyTargetCount"] == 1
    assert [row["entityId"] for row in report["ineligibleTargets"]] == ["计划缺口景区"]


def test_download_availability_never_promotes_plan_only_target(monkeypatch, tmp_path):
    ctx = _context(entity_ids=["已抓取景区", "仅更新计划景区", "下载失败景区"])
    artifact_issue = data_issue(
        DataIssueCode.SOURCE_MISSING,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref="仅更新计划景区",
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="source unit has not been fetched",
    )
    failed_issue = data_issue(
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        stage=DataIssueStage.ENTITY_SOURCE_BUNDLE,
        ref="下载失败景区",
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="source unit was rejected",
    )
    persisted: dict[str, object] = {}
    monkeypatch.setattr(download_unresolved, "_pending_download_repair_unresolved", lambda _ctx: {})
    monkeypatch.setattr(download_unresolved, "_download_plan_repair_exhausted_unresolved", lambda *_args: {})
    monkeypatch.setattr(
        download_unresolved,
        "_download_artifact_issues",
        lambda _ctx: {
            "仅更新计划景区": (artifact_issue,),
            "下载失败景区": (failed_issue,),
        },
    )
    monkeypatch.setattr(download_unresolved, "execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        download_unresolved,
        "write_json",
        lambda path, data: persisted.update({"path": path, "data": data}),
    )
    report = download_unresolved._write_download_availability(ctx, {})

    assert report["readyTargets"] == ["已抓取景区"]
    assert [row["entityId"] for row in report["ineligibleTargets"]] == [
        "仅更新计划景区",
        "下载失败景区",
    ]
    assert report["readyTargetCount"] + report["ineligibleTargetCount"] == 3
    assert report["ineligibleTargets"][0]["blockers"] == [artifact_issue.as_dict()]


def test_download_availability_does_not_overwrite_research_plan(monkeypatch, tmp_path):
    ctx = _context(entity_ids=["测试实体甲"])
    plan_path = tmp_path / "_shared" / "auto_research_plan.json"
    plan_path.parent.mkdir(parents=True)
    research_plan = {
        "sourceAvailability": {
            "readyTargets": ["测试实体甲"],
            "readyTargetCount": 1,
            "ineligibleTargets": [],
            "ineligibleTargetCount": 0,
        }
    }
    from core.io import read_json, write_json

    write_json(plan_path, research_plan)
    monkeypatch.setattr(download_unresolved, "_pending_download_repair_unresolved", lambda _ctx: {})
    monkeypatch.setattr(download_unresolved, "_download_plan_repair_exhausted_unresolved", lambda *_args: {})
    monkeypatch.setattr(download_unresolved, "_download_artifact_issues", lambda _ctx: {})
    monkeypatch.setattr(download_unresolved, "execution_root", lambda _execution_id: tmp_path)

    report = download_unresolved._write_download_availability(ctx, {})

    assert read_json(plan_path) == research_plan
    assert read_json(tmp_path / "_shared" / "source_unavailable_targets.json") == report


def test_download_fetch_resumes_an_audited_absorbed_homepage_shortfall(monkeypatch):
    ctx = _context(entity_ids=["可用景区甲", "缺源景区乙"])
    availability = {
        "readyTargets": ["可用景区甲"],
        "readyTargetCount": 1,
        "ineligibleTargets": [{"entityId": "缺源景区乙"}],
        "ineligibleTargetCount": 1,
    }
    calls: list[str] = []
    monkeypatch.setattr(
        download_unresolved,
        "_write_download_availability",
        lambda _ctx, _unresolved, *, source: calls.append(source) or availability,
    )
    from content.execution import spec_contract

    monkeypatch.setattr(spec_contract, "approved_quota", lambda _execution_id: 1)

    result = stage_download_build._run_download_fetch(ctx)

    assert result.status is StageStatus.DONE
    assert "过采候选源缺口已吸收为丢弃池" in result.message
    assert calls == ["download_fetch_resume"]


def test_homepage_runtime_spec_projects_only_audited_ready_targets(monkeypatch, tmp_path):
    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-102"
    spec = ExecutionFixtureBuilder(
        execution_id,
        targets=(
            {"name": "可用景区甲", "entityType": "地点/景区"},
            {"name": "缺源景区乙", "entityType": "地点/景区"},
            {"name": "可用博物馆丙", "entityType": "地点/博物馆"},
        ),
        approved_quota=2,
    ).spec_payload()
    availability_path = tmp_path / "_shared" / "source_unavailable_targets.json"
    availability_path.parent.mkdir(parents=True)
    write_json(
        availability_path,
        {
            "schema": "quwoquan.content.source.source_availability",
            "executionId": execution_id,
            "readyTargets": ["可用景区甲", "可用博物馆丙"],
            "readyTargetCount": 2,
            "ineligibleTargets": [{"entityId": "缺源景区乙"}],
            "ineligibleTargetCount": 1,
        },
    )
    monkeypatch.setattr(
        source_ready_scope, "execution_root", lambda _execution_id: tmp_path
    )

    runtime_spec = homepage.homepage_runtime_spec(execution_id, spec)

    assert [
        target["name"] for target in spec["scope"]["coverageTargets"]
    ] == ["可用景区甲", "缺源景区乙", "可用博物馆丙"]
    assert [
        target["name"] for target in runtime_spec["scope"]["coverageTargets"]
    ] == ["可用景区甲", "可用博物馆丙"]


def test_homepage_pending_entities_skip_absorbed_ineligible_targets(monkeypatch, tmp_path):
    from content.execution.controller import homepage_authoring

    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-105"
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=["可用景区甲", "缺源景区乙", "可用博物馆丙"],
        spec=ExecutionFixtureBuilder(
            execution_id,
            targets=(
                {"name": "可用景区甲", "entityType": "地点/景区"},
                {"name": "缺源景区乙", "entityType": "地点/景区"},
                {"name": "可用博物馆丙", "entityType": "地点/博物馆"},
            ),
            approved_quota=2,
        ).spec(),
        managed=True,
    )
    availability_path = tmp_path / "_shared" / "source_unavailable_targets.json"
    availability_path.parent.mkdir(parents=True)
    write_json(
        availability_path,
        {
            "schema": "quwoquan.content.source.source_availability",
            "executionId": execution_id,
            "readyTargets": ["可用景区甲", "可用博物馆丙"],
            "readyTargetCount": 2,
            "ineligibleTargets": [{"entityId": "缺源景区乙"}],
            "ineligibleTargetCount": 1,
        },
    )
    monkeypatch.setattr(
        source_ready_scope, "execution_root", lambda _execution_id: tmp_path
    )
    from content.homepage import homepage_release_validation

    monkeypatch.setattr(
        homepage_release_validation,
        "validate_entity_page",
        lambda *_args, **_kwargs: ["missing page"],
    )
    monkeypatch.setattr(
        homepage_authoring,
        "_homepage_independent_review_issues",
        lambda *_args, **_kwargs: [],
    )

    pending = homepage_authoring._homepage_pending_entities(ctx)

    assert pending == ["可用景区甲", "可用博物馆丙"]


@pytest.mark.parametrize("carrier", ["article", "video"])
def test_source_ready_runtime_spec_projects_absorbed_ready_targets(
    monkeypatch,
    tmp_path,
    carrier,
):
    execution_id = f"20260716--travel-{carrier}-m100--test-region-a--pilot-104"
    spec = ExecutionFixtureBuilder(
        execution_id,
        targets=(
            {"name": "可用景区甲", "entityType": "地点/景区"},
            {"name": "缺源景区乙", "entityType": "地点/景区"},
            {"name": "可用博物馆丙", "entityType": "地点/博物馆"},
        ),
        approved_quota=2,
    ).spec_payload()
    availability_path = tmp_path / "_shared" / "source_unavailable_targets.json"
    availability_path.parent.mkdir(parents=True)
    write_json(
        availability_path,
        {
            "schema": "quwoquan.content.source.source_availability",
            "executionId": execution_id,
            "readyTargets": ["可用景区甲", "可用博物馆丙"],
            "readyTargetCount": 2,
            "ineligibleTargets": [{"entityId": "缺源景区乙"}],
            "ineligibleTargetCount": 1,
        },
    )
    monkeypatch.setattr(
        source_ready_scope, "execution_root", lambda _execution_id: tmp_path
    )

    runtime_spec = source_ready_scope.source_ready_runtime_spec(execution_id, spec)

    assert [
        target["name"] for target in runtime_spec["scope"]["coverageTargets"]
    ] == ["可用景区甲", "可用博物馆丙"]


def test_homepage_runtime_spec_rejects_an_incomplete_availability_partition(
    monkeypatch,
    tmp_path,
):
    execution_id = "20260716--travel-homepage-coverage--test-region-a--pilot-103"
    spec = ExecutionFixtureBuilder(
        execution_id,
        targets=(
            {"name": "可用景区甲", "entityType": "地点/景区"},
            {"name": "缺源景区乙", "entityType": "地点/景区"},
        ),
        approved_quota=1,
    ).spec_payload()
    availability_path = tmp_path / "_shared" / "source_unavailable_targets.json"
    availability_path.parent.mkdir(parents=True)
    write_json(
        availability_path,
        {
            "schema": "quwoquan.content.source.source_availability",
            "executionId": execution_id,
            "readyTargets": ["可用景区甲"],
            "readyTargetCount": 1,
            "ineligibleTargets": [],
            "ineligibleTargetCount": 0,
        },
    )
    monkeypatch.setattr(
        source_ready_scope, "execution_root", lambda _execution_id: tmp_path
    )

    with pytest.raises(ValueError, match="partition the frozen target set"):
        homepage.homepage_runtime_spec(execution_id, spec)


def test_inactive_homepage_artifact_prune_uses_frozen_execution_targets(monkeypatch, tmp_path):
    from core import entity_artifacts

    ctx = _context(entity_ids=["测试实体甲"])
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        entity_artifacts,
        "prune_inactive_entity_artifacts",
        lambda execution_id, *, active_entity_names: calls.append(
            (execution_id, list(active_entity_names))
        )
        or [{"entity": "历史对象", "artifacts": ["entities/地点/景区/历史对象"]}],
    )
    result = target_integrity.prune_non_target_homepage_artifacts(
        ctx,
        reason="contract test",
    )

    assert calls == [(ctx.execution_id, ["测试实体甲"])]
    assert result[0]["entity"] == "历史对象"


def test_audited_stage_recovery_clears_retry_and_react_ledgers(monkeypatch):
    ctx = _context()
    state = ExecutionFixtureBuilder(ctx.execution_id).state(
        status=ExecutionStateStatus.MANUAL_REQUIRED,
        completed=(ExecutionStage.DOWNLOAD_PLAN,),
        failed_objects=("测试实体乙: image gates failed",),
        retry_counts={ExecutionStage.DOWNLOAD_FETCH: 2},
        infrastructure_retry_counts={ExecutionStage.DOWNLOAD_FETCH: 1},
        react_rewinds={ExecutionStage.DOWNLOAD_FETCH: 2},
    )
    monkeypatch.setattr(stage_reset, "load_execution_state", lambda *_args: state)
    monkeypatch.setattr(stage_reset, "save_execution_state", lambda updated: updated.freeze())
    monkeypatch.setattr(
        stage_reset.store,
        "load_spec",
        lambda _execution_id: ctx.spec.to_dict(),
    )
    monkeypatch.setattr(post_recovery, "_purge_stale_author_queue", lambda *_args, **_kwargs: None)

    result = stage_reset.reset_stage_retries(
        ctx.execution_id,
        stage=ExecutionStage.DOWNLOAD_FETCH.value,
        reason="canonical download workspace reader fixed",
        reset_react_rewinds=True,
    )

    assert result["status"] == "repairing"
    assert result["retryCounts"] == {}
    assert result["infrastructureRetryCounts"] == {}
    assert result["reactRewinds"] == {}
    assert state.failed_objects == []


def test_audited_homepage_recovery_requeues_only_dead_entity_author_jobs(monkeypatch):
    from content.execution.queue import management as queue_management
    from content.post import object_index as content_object

    ctx = _context(entity_ids=["测试实体甲", "测试实体乙"])
    state = ExecutionFixtureBuilder(ctx.execution_id).state(
        status=ExecutionStateStatus.MANUAL_REQUIRED,
        completed=(ExecutionStage.BUILD_PREPARE,),
        failed_objects=("测试实体乙: fidelity gate failed",),
    )
    monkeypatch.setattr(stage_reset, "load_execution_state", lambda *_args: state)
    monkeypatch.setattr(stage_reset, "save_execution_state", lambda updated: updated.freeze())
    monkeypatch.setattr(
        stage_reset.store,
        "load_spec",
        lambda _execution_id: ctx.spec.to_dict(),
    )
    monkeypatch.setattr(content_object, "iter_content_refs", lambda *_args: [])
    monkeypatch.setattr(post_recovery, "_purge_stale_author_queue", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        queue_management,
        "dead_jobs",
        lambda _execution_id: [
            {"ref": "/entity/地点/景区/测试实体乙", "stage": "author"},
            {"ref": "/post/article/测试帖子", "stage": "author"},
            {"ref": "/entity/地点/景区/测试实体甲", "stage": "publish"},
        ],
    )
    requeued: list[str] = []
    monkeypatch.setattr(
        queue_management,
        "requeue_refs",
        lambda _execution_id, refs, _stage, *, reason: requeued.extend(refs) or list(refs),
    )

    result = stage_reset.reset_stage_retries(
        ctx.execution_id,
        stage=ExecutionStage.BUILD_HOMEPAGE.value,
        reason="homepage fidelity guidance fixed",
    )

    assert requeued == ["/entity/地点/景区/测试实体乙"]
    assert result["requeuedHomepageRefs"] == ["/entity/地点/景区/测试实体乙"]
