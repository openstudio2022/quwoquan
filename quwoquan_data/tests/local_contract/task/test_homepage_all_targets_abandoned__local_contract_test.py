"""全放弃分区的采纳门收口语义（WP5 乐山单实体分区实测回归）。

单实体/小分区在 sourceScreen 无权威主源时会把全部 coverage 实体按
homepage lane reasoned 放弃；此后 build_homepage / build_validate 面对
空目标集不得再判 failed（会造成 managed 重试空转 → manual_required），
收口权交给 completion 的 reasoned-reject 语义。原始 spec 本就无目标的
配置错误仍必须保持 failed。
"""
from __future__ import annotations

from support.task_workflow_fixtures import *  # noqa: F401,F403


def _abandon_all(task_id: str, batch_id: str) -> None:
    run_mod.mark_abandoned_homepages(
        task_id,
        batch_id,
        [_EID],
        stage="download_fetch",
        reason="homepage lane sourceScreen retained no primary authority source",
    )


def test_build_validate_done_when_all_homepage_targets_reasoned_abandoned():
    task_id = _make_task()
    batch_id = "all_targets_abandoned_validate"
    ctx = _ctx(task_id, batch_id)
    _abandon_all(task_id, batch_id)

    result = run_mod._run_build_validate(ctx)

    assert result.status == "done"
    assert "reasoned 放弃" in result.message


def test_build_homepage_checkpoint_done_when_all_targets_reasoned_abandoned():
    task_id = _make_task()
    batch_id = "all_targets_abandoned_checkpoint"
    ctx = _ctx(task_id, batch_id)
    _abandon_all(task_id, batch_id)

    result = run_mod._checkpoint_build_homepage(ctx)

    assert result.status == "done"


def test_build_validate_still_fails_when_spec_has_no_coverage_targets():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec["scope"]["coverageTargets"] = []
    store.save_spec(spec)
    batch_id = "no_targets_config_error"
    ctx = _ctx(task_id, batch_id)
    ctx.spec["scope"]["coverageTargets"] = []

    result = run_mod._run_build_validate(ctx)

    assert result.status == "failed"
    assert any("为空" in issue for issue in result.issues)


def test_build_validate_still_fails_when_surviving_target_missing_homepage():
    # 仍有存活实体但主页未物化：不得被全放弃分支误放行。
    task_id = _make_task()
    batch_id = "surviving_target_still_validates"
    ctx = _ctx(task_id, batch_id)

    result = run_mod._run_build_validate(ctx)

    assert result.status == "failed"


_REASONED_POLICY = {"minBatchCompletionMode": "best_effort_with_reasoned_rejects"}


def _make_homepage_only_task() -> str:
    task_id = _make_task(workflow_policy=dict(_REASONED_POLICY))
    spec = store.load_spec(task_id)
    spec["content"]["quotas"] = {
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 0,
        "entityHomepagesPerTarget": 1,
        "routeArticles": 0,
    }
    store.save_spec(spec)
    return task_id


def _refless_infra_failure_run() -> dict:
    # bridge 基础设施失败快照：worker 未启动、refs 为空（乐山沙湾区实测形态）。
    return {
        "stage": "build_homepage",
        "jobCount": 1,
        "plannedJobCount": 1,
        "startedCount": 0,
        "finishedCount": 0,
        "infrastructureFailures": 1,
        "refs": [],
        "outcomes": [{"ref": None, "status": "error"}],
    }


def test_publish_done_when_all_homepage_targets_reasoned_abandoned():
    task_id = _make_homepage_only_task()
    batch_id = "all_abandoned_publish"
    ensure_batch_layout(task_id, batch_id, "publish")
    ctx = _ctx(task_id, batch_id)
    _abandon_all(task_id, batch_id)

    result = run_mod._run_publish(ctx)

    assert result.status == "done"
    assert "reasoned abandoned" in result.message


def test_publish_still_fails_without_reasoned_abandon():
    task_id = _make_homepage_only_task()
    batch_id = "no_abandon_publish_fails"
    ensure_batch_layout(task_id, batch_id, "publish")
    ctx = _ctx(task_id, batch_id)

    result = run_mod._run_publish(ctx)

    assert result.status == "failed"
    assert "无 approved 实体主页" in result.message


def test_completion_ignores_refless_stale_run_when_all_targets_abandoned():
    task_id = _make_homepage_only_task()
    batch_id = "stale_run_all_abandoned"
    ctx = _ctx(task_id, batch_id)
    _abandon_all(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["lastAgentRun"] = _refless_infra_failure_run()

    issues = run_mod._workflow_completion_issues(ctx, state)

    assert not any("lastAgentRun" in issue for issue in issues)


def test_completion_keeps_refless_stale_run_issues_without_abandon():
    task_id = _make_homepage_only_task()
    batch_id = "stale_run_targets_active"
    ctx = _ctx(task_id, batch_id)
    state = run_mod.load_workflow_state(task_id, batch_id)
    state["lastAgentRun"] = _refless_infra_failure_run()

    issues = run_mod._workflow_completion_issues(ctx, state)

    assert any("infrastructureFailures" in issue for issue in issues)
    assert any("no started workers" in issue for issue in issues)
