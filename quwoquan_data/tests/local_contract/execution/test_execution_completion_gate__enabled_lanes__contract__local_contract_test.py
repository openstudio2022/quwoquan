from __future__ import annotations

from core.control_types import ExecutionStage, ExecutionStateStatus
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
from content.execution.recovery import download_repair
from content.execution.recovery import download_unresolved
from content.execution.recovery import post_recovery
from content.execution.recovery import stage_reset
from content.execution import target_integrity
from support.execution_manifest_fixture import ExecutionFixtureBuilder


def _context(*, entity_ids: list[str] | None = None) -> ExecutionContext:
    resolved_entity_ids = entity_ids or ["东钱湖"]
    execution_id = "20260716--travel-homepage-coverage--cn-zhejiang--canary-099"
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
            "lanePassed": {"homepage": 1, "article": 0, "image": 0},
            "targetCount": 1,
        },
    )

    assert execution_completion.execution_completion_issues(
        ctx,
        ExecutionFixtureBuilder(ctx.execution_id).state(),
    ) == []


def test_download_plan_availability_persists_frozen_target_failure(monkeypatch, tmp_path):
    ctx = _context(entity_ids=["普陀山"])
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
    monkeypatch.setattr(auto_research, "_sync_auto_research_availability", lambda *_args: None)

    report = download_unresolved._write_download_availability(
        ctx,
        {"普陀山": {"homepage": ["homepage source needs repair"]}},
    )

    assert persisted["path"] == tmp_path / "_shared" / "source_unavailable_targets.json"
    assert persisted["data"] == report
    assert report["readyTargets"] == []
    assert report["ineligibleTargets"][0]["entityId"] == "普陀山"


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
    monkeypatch.setattr(auto_research, "_sync_auto_research_availability", lambda *_args: None)

    report = download_unresolved._write_download_availability(ctx, {})

    assert report["readyTargets"] == ["已抓取景区"]
    assert [row["entityId"] for row in report["ineligibleTargets"]] == [
        "仅更新计划景区",
        "下载失败景区",
    ]
    assert report["readyTargetCount"] + report["ineligibleTargetCount"] == 3
    assert report["ineligibleTargets"][0]["blockers"] == [artifact_issue.as_dict()]


def test_inactive_homepage_artifact_prune_uses_frozen_execution_targets(monkeypatch, tmp_path):
    from core import entity_artifacts

    ctx = _context(entity_ids=["普陀山"])
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

    assert calls == [(ctx.execution_id, ["普陀山"])]
    assert result[0]["entity"] == "历史对象"


def test_audited_stage_recovery_clears_retry_and_react_ledgers(monkeypatch):
    ctx = _context()
    state = ExecutionFixtureBuilder(ctx.execution_id).state(
        status=ExecutionStateStatus.MANUAL_REQUIRED,
        completed=(ExecutionStage.DOWNLOAD_PLAN,),
        failed_objects=("东钱湖: image gates failed",),
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
