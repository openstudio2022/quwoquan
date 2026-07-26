"""Homepage author evidence cannot bypass deterministic materialization."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution import reliabletask_worker  # noqa: E402


def _homepage_job() -> SimpleNamespace:
    return SimpleNamespace(
        carrier=SimpleNamespace(value="homepage"),
        ref="/entity/地点/景区/测试实体甲",
        execution_id="20260722--travel-homepage-generate--test-region-a--pilot-901",
        job_id="homepage-job",
        content_object_dir="entities/地点/景区/测试实体甲",
    )


def _article_job() -> SimpleNamespace:
    return SimpleNamespace(
        carrier=SimpleNamespace(value="article"),
        ref="测试文章",
        execution_id="20260722--travel-article-generate--test-region-a--pilot-901",
        job_id="article-job",
        content_object_dir="posts/article/攻略/测试文章/1",
    )


def test_failed_homepage_materialization_invalidates_author_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    envelope_path = tmp_path / "agent_result_envelope.json"
    envelope_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        reliabletask_worker,
        "_validate_author_envelope",
        lambda _job, _path: None,
    )

    from content.homepage import homepage_release

    monkeypatch.setattr(
        homepage_release,
        "materialize_entity_page",
        lambda *_args: ["base draft fidelity below policy"],
    )

    assert reliabletask_worker._existing_author_envelope_is_reusable(
        _homepage_job(),
        envelope_path,
    ) is False
    assert not envelope_path.exists()


def test_materialized_homepage_may_reuse_author_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    envelope_path = tmp_path / "agent_result_envelope.json"
    envelope_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        reliabletask_worker,
        "_validate_author_envelope",
        lambda _job, _path: None,
    )

    from content.homepage import homepage_release

    monkeypatch.setattr(
        homepage_release,
        "materialize_entity_page",
        lambda *_args: [],
    )

    assert reliabletask_worker._existing_author_envelope_is_reusable(
        _homepage_job(),
        envelope_path,
    ) is True
    assert envelope_path.is_file()


def test_post_repair_newer_than_author_envelope_requires_fresh_agent_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    task_root = tmp_path / "task"
    job = _article_job()
    envelope_path = task_root / job.content_object_dir / "4.draft" / "agent_result_envelope.json"
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_text("{}", encoding="utf-8")
    repair_path = task_root / job.content_object_dir / "5.review" / "repair_report.json"
    repair_path.parent.mkdir(parents=True)
    repair_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(reliabletask_worker, "execution_root", lambda _execution_id: task_root)
    monkeypatch.setattr(
        reliabletask_worker,
        "_validate_author_envelope",
        lambda _job, _path: None,
    )

    assert reliabletask_worker._existing_author_envelope_is_reusable(
        job,
        envelope_path,
    ) is False
    assert not envelope_path.exists()


def test_homepage_repair_uses_frozen_job_prompt_not_pending_prompt_scan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    job = _homepage_job()
    task_root = tmp_path / "task"
    draft_dir = task_root / job.content_object_dir / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "prompt.md").write_text("只依据冻结来源重写正文。", encoding="utf-8")
    (draft_dir / "author_job_packet.json").write_text(
        '{"executionId":"20260722--travel-homepage-generate--test-region-a--pilot-901",'
        '"objectRef":"/entity/地点/景区/测试实体甲",'
        '"promptRef":"4.draft/prompt.md"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(reliabletask_worker, "execution_root", lambda _execution_id: task_root)

    checkpoint, prompt = reliabletask_worker._author_prompt(SimpleNamespace(), job)

    assert checkpoint == "build_homepage"
    assert prompt == "只依据冻结来源重写正文。"


def test_homepage_repair_feedback_is_appended_only_after_typed_contract_validation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from core.data_issue import (
        DataIssueCode,
        DataIssueLane,
        DataIssueStage,
        DataRecoveryAction,
        data_issue,
    )
    from content.execution.stage_reports import build_repair_report

    job = _homepage_job()
    task_root = tmp_path / "task"
    object_dir = task_root / job.content_object_dir
    draft_dir = object_dir / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "prompt.md").write_text("保留冻结正文。", encoding="utf-8")
    (draft_dir / "author_job_packet.json").write_text(
        '{"executionId":"20260722--travel-homepage-generate--test-region-a--pilot-901",'
        '"objectRef":"/entity/地点/景区/测试实体甲",'
        '"promptRef":"4.draft/prompt.md"}',
        encoding="utf-8",
    )
    repair_path = object_dir / "5.review" / "repair_report.json"
    repair_path.parent.mkdir(parents=True)
    repair_path.write_text(
        json.dumps(
            build_repair_report(
                execution_id=job.execution_id,
                command="homepage",
                ref=job.ref,
                failed_stage=DataIssueStage.BUILD_HOMEPAGE.value,
                failed_gate="homepage_materialization",
                issues=(
                    data_issue(
                        DataIssueCode.QUALITY_FAILED,
                        stage=DataIssueStage.BUILD_HOMEPAGE,
                        lane=DataIssueLane.HOMEPAGE,
                        recovery=DataRecoveryAction.RETRY_AGENT,
                        ref=job.ref,
                        message="标题层级不符合页面合同",
                    ),
                ),
                fallback_stage=DataIssueStage.BUILD_HOMEPAGE.value,
                rerun_chain=["author", "materialize"],
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(reliabletask_worker, "execution_root", lambda _execution_id: task_root)

    checkpoint, prompt = reliabletask_worker._author_prompt(SimpleNamespace(), job)

    assert checkpoint == "build_homepage"
    assert prompt.startswith("保留冻结正文。")
    assert "[DATA.QUALITY.FAILED] 标题层级不符合页面合同" in prompt


def test_homepage_repair_feedback_rejects_untyped_recovery_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    job = _homepage_job()
    task_root = tmp_path / "task"
    object_dir = task_root / job.content_object_dir
    draft_dir = object_dir / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "prompt.md").write_text("冻结正文。", encoding="utf-8")
    (draft_dir / "author_job_packet.json").write_text(
        '{"executionId":"20260722--travel-homepage-generate--test-region-a--pilot-901",'
        '"objectRef":"/entity/地点/景区/测试实体甲",'
        '"promptRef":"4.draft/prompt.md"}',
        encoding="utf-8",
    )
    repair_path = object_dir / "5.review" / "repair_report.json"
    repair_path.parent.mkdir(parents=True)
    repair_path.write_text(
        json.dumps(
            {
                "schema": "quwoquan_data.repair_report",
                "executionId": job.execution_id,
                "command": "homepage",
                "ref": job.ref,
                "failedStage": "build_homepage",
                "failedGate": "homepage_materialization",
                "issues": [
                    {
                        "code": "DATA.QUALITY.FAILED",
                        "stage": "build_homepage",
                        "lane": "homepage",
                        "recovery": "stop",
                        "message": "不可被 Author 修复的状态",
                        "ref": job.ref,
                        "attrs": {},
                    }
                ],
                "fallbackStage": "build_homepage",
                "rerunChain": ["author", "materialize"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(reliabletask_worker, "execution_root", lambda _execution_id: task_root)

    with pytest.raises(ValueError, match="issue contract invalid"):
        reliabletask_worker._author_prompt(SimpleNamespace(), job)


def test_homepage_finalization_uses_bound_entity_ref_not_prompt_text(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from content.execution.agent.outcome import AgentRunOutcome, ManagedAgentJobOutcome
    from content.execution.controller import homepage_author_finalization
    from core.control_types import AgentProvider

    entity = "测试实体甲"
    draft_dir = tmp_path / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "page.md").write_text("# 测试实体甲\n\n正文。", encoding="utf-8")
    (draft_dir / "draft_meta.json").write_text("{}", encoding="utf-8")
    stale_repair_path = draft_dir.parent / "5.review" / "repair_report.json"
    stale_repair_path.parent.mkdir(parents=True)
    stale_repair_path.write_text("{}", encoding="utf-8")
    captured: dict[str, str] = {}
    from content.homepage import homepage_review, homepage_release

    monkeypatch.setattr(homepage_review, "_entity_draft_dir", lambda *_args: draft_dir)
    monkeypatch.setattr(homepage_release, "materialize_entity_page", lambda *_args: [])
    monkeypatch.setattr(
        homepage_author_finalization,
        "_write_homepage_author_evidence",
        lambda _ctx, **kwargs: captured.update(
            {
                "domain": str(kwargs["domain"]),
                "etype": str(kwargs["etype"]),
                "entity": str(kwargs["entity"]),
            }
        ),
    )
    from core import schema

    monkeypatch.setattr(schema, "assert_valid", lambda *_args, **_kwargs: None)

    target = SimpleNamespace(name=entity, entity_type="地点/景区")
    ctx = SimpleNamespace(
        execution_id="20260722--travel-homepage-generate--test-region-a--pilot-901",
        spec=SimpleNamespace(scope=SimpleNamespace(coverage_targets=(target,))),
        model="grok-4.5",
    )
    outcome = ManagedAgentJobOutcome(
        outcome=AgentRunOutcome.finished(
            provider=AgentProvider.CURSOR_SDK,
            run_id="cursor-run-001",
        ),
        job_index=0,
        lane="homepage",
        ref="/entity/地点/景区/测试实体甲",
    )

    finalized = homepage_author_finalization._finalize_managed_homepage_outputs(
        ctx,
        ["提示词可以没有对象文本标记"],
        [outcome],
    )

    assert finalized[0].succeeded
    assert finalized[0].gate_issues == ()
    assert captured == {"domain": "地点", "etype": "景区", "entity": entity}
    assert not stale_repair_path.exists()


def test_homepage_finalization_writes_typed_repair_report_for_materialization_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from content.execution.agent.outcome import AgentRunOutcome, ManagedAgentJobOutcome
    from content.execution.controller import homepage_author_finalization
    from content.homepage import homepage_release, homepage_review
    from core.control_types import AgentProvider
    from core import schema

    entity = "测试实体甲"
    draft_dir = tmp_path / "4.draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "page.md").write_text("# 测试实体甲\n\n正文。", encoding="utf-8")
    (draft_dir / "draft_meta.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(homepage_review, "_entity_draft_dir", lambda *_args: draft_dir)
    monkeypatch.setattr(
        homepage_release,
        "materialize_entity_page",
        lambda *_args: ["标题层级不符合页面合同"],
    )
    monkeypatch.setattr(
        homepage_author_finalization,
        "_write_homepage_author_evidence",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(schema, "assert_valid", lambda *_args, **_kwargs: None)
    target = SimpleNamespace(name=entity, entity_type="地点/景区")
    ctx = SimpleNamespace(
        execution_id="20260722--travel-homepage-generate--test-region-a--pilot-901",
        spec=SimpleNamespace(scope=SimpleNamespace(coverage_targets=(target,))),
        model="grok-4.5",
    )
    outcome = ManagedAgentJobOutcome(
        outcome=AgentRunOutcome.finished(
            provider=AgentProvider.CURSOR_SDK,
            run_id="cursor-run-001",
        ),
        job_index=0,
        lane="homepage",
        ref="/entity/地点/景区/测试实体甲",
    )

    finalized = homepage_author_finalization._finalize_managed_homepage_outputs(
        ctx,
        ["冻结提示词"],
        [outcome],
    )

    repair_report = json.loads(
        (draft_dir.parent / "5.review" / "repair_report.json").read_text(encoding="utf-8")
    )
    assert finalized[0].gate_issues == ("标题层级不符合页面合同",)
    assert repair_report["schema"] == "quwoquan_data.repair_report"
    assert repair_report["ref"] == outcome.ref
    assert repair_report["issues"][0]["code"] == "DATA.QUALITY.FAILED"
    assert repair_report["issues"][0]["stage"] == "build_homepage"
    assert repair_report["issues"][0]["recovery"] == "retry_agent"
