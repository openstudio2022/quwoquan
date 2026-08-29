# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import controller as campaign_controller
from content.execution.campaign import distributed as campaign_distributed
from content.execution.campaign import orchestrator as campaign_orchestrator
from content.execution.campaign import plan as campaign_plan
from content.execution.campaign import process as campaign_process
from content.execution.campaign.lane_claim import read_lane_claim
from content.execution.campaign.runtime import (
    read_lane_checkpoint,
    read_runtime_snapshot,
    runtime_events_path,
)
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.planning.execution_authority import (
    build_bounded_execution_authority,
)
from core.execution_branch import (
    current_git_branch,
    execution_branch_issues,
    stamp_execution_branch,
)
from core.io import read_json, write_json
from support.campaign_lanes_fixture import (  # noqa: F401
    CARRIERS,
    ROOT_ID,
    _assert_capsule_reused_and_lane_roots_isolated,
    _create_repo,
    _events,
    _git,
    _restore_capsule_permissions_for_pytest_cleanup,
    _runtime,
    _submit_all,
)


def test_default_runtime_paths_use_governed_workspace_and_cache() -> None:
    runtime = CampaignRuntimePaths.defaults()
    governed_workspace = (
        runtime.output_root / "data" / "local" / "workspace"
    ).resolve()
    governed_cache = (runtime.output_root / "data" / "local" / "cache").resolve()

    assert runtime.campaigns_root.parent == governed_workspace
    assert runtime.workspaces_root.parent == governed_cache
    assert runtime.acquisition_root.parent == governed_workspace


def test_run_phase_propagates_no_implicit_lane_timeout(monkeypatch) -> None:
    observed: list[float | None] = []

    def run_lane(_workspace, _submission, **kwargs):
        observed.append(kwargs["timeout_seconds"])
        return 0, None

    monkeypatch.setattr(campaign_process, "run_lane", run_lane)
    workspaces = {
        carrier: SimpleNamespace(carrier=carrier) for carrier in CARRIERS
    }
    submissions = {
        carrier: {"executionId": f"execution-{carrier}"} for carrier in CARRIERS
    }

    result = campaign_process.run_phase(
        workspaces,
        submissions,
        stage="review-only",
        runtime=SimpleNamespace(),
        root_execution_id=ROOT_ID,
        timeout_seconds=None,
        lane_runner=None,
        run_session=SimpleNamespace(),
    )

    assert observed == [None] * len(CARRIERS)
    assert set(result) == set(CARRIERS)


def test_run_phase_forwards_audited_recovery_into_each_lane(monkeypatch) -> None:
    """受审计恢复起点必须从 run_phase 一路到达车道进程。

    `_lane_argv` 与 CLI 两端都支持 `--recover-stage`/`--recovery-reason`，中间的
    run_phase → run_lane 一旦不透传，5.review 的 fallbackStage 就再也回不到上游
    阶段重跑，只能靠新建 executionId 绕过。
    """
    observed: list[tuple[str | None, str | None]] = []

    def run_lane(_workspace, _submission, **kwargs):
        observed.append((kwargs["recover_stage"], kwargs["recovery_reason"]))
        return 0, None

    monkeypatch.setattr(campaign_process, "run_lane", run_lane)
    workspaces = {carrier: SimpleNamespace(carrier=carrier) for carrier in CARRIERS}
    submissions = {
        carrier: {"executionId": f"execution-{carrier}"} for carrier in CARRIERS
    }

    campaign_process.run_phase(
        workspaces,
        submissions,
        stage="run",
        runtime=SimpleNamespace(),
        root_execution_id=ROOT_ID,
        timeout_seconds=None,
        lane_runner=None,
        run_session=SimpleNamespace(),
        recover_stage="build_homepage",
        recovery_reason="5.review fallbackStage",
    )

    assert observed == [("build_homepage", "5.review fallbackStage")] * len(CARRIERS)


def test_distributed_lane_command_preserves_frozen_source_pool_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_revision = "sha256:" + "a" * 64
    source_digest = "sha256:" + "b" * 64
    entity_catalog_digest = "sha256:" + "c" * 64
    plan_digest = "sha256:" + "d" * 64
    plan_file_sha256 = "sha256:" + "e" * 64
    selection_digest = "sha256:" + "f" * 64
    fence_digest = "sha256:" + "9" * 64
    candidate_ids = ["candidate-qingchengshan", "candidate-dujiangyan"]
    submission = {
        "executionId": (
            "20260822--travel-article-workload-article-1--china-cultural-deep-tour"
            "--scale-003"
        ),
        "rootExecutionId": (
            "20260822--travel-article-workload-article-1--china-cultural-deep-tour"
            "--scale-003"
        ),
        "familyRef": "content/travel/article/base",
        "regionRef": "china/四川省",
        "selector": "source-ready-priority",
        "quota": 1,
        "count": 2,
        "executionAuthority": build_bounded_execution_authority(
            total_objects=1
        ),
        "semanticSelectionId": "cursor_auto",
        "targetNames": [],
        "gitBranch": "dev1.0",
        "gitCommitSha": "a" * 40,
        "sourceRevision": source_revision,
        "sourceDigest": {"digest": source_digest},
        "entityCatalogDigest": entity_catalog_digest,
        "scaleSourcePool": {
            "poolId": "m1-article-culture-china",
            "targetScale": "WORKLOAD",
            "planRef": "data/local/workspace/source-pool/plan.json",
            "planDigest": plan_digest,
            "planFileSha256": plan_file_sha256,
            "sourceRevision": source_revision,
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_catalog_digest,
        },
        "sourcePoolEvidenceRootRef": "data/local/workspace/source-pool/evidence",
        "sourcePoolSelection": {
            "carrier": "article",
            "candidateIds": candidate_ids,
            "candidateCount": 2,
            "selectionDigest": selection_digest,
        },
    }
    execution_root = tmp_path / "output/data/tasks/article"
    execution_root.mkdir(parents=True)
    capsule_path = tmp_path / "capsule"
    capsule = SimpleNamespace(
        path=capsule_path,
        lane_external_inputs={"article": {"externalInputRefs": []}},
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
        external_input_root=lambda _carrier: capsule_path / "external-inputs/article",
    )
    workspace = SimpleNamespace(
        carrier="article",
        path=capsule_path,
        capsule=capsule,
        execution_root=execution_root,
        ref="data/local/cache/content-campaign-workspaces/article",
    )
    runtime = SimpleNamespace(
        campaigns_root=tmp_path / "output/data/local/workspace/campaigns",
        output_root=tmp_path / "output",
        publish_root=tmp_path / "publish",
    )
    checkpoints: list[dict[str, object]] = []
    run_session = SimpleNamespace(
        run_id="campaign-run-source-pool",
        generation=1,
        fencing_token=fence_digest,
        plan_digest=fence_digest,
        lane_checkpoint=lambda **kwargs: checkpoints.append(kwargs),
    )
    commands: list[list[str]] = []

    def capture_command(
        command: list[str],
        _cwd: Path,
        _env: dict[str, str],
        _log_path: Path,
        _timeout_seconds: float | None,
    ) -> int:
        commands.append(command)
        return 0

    result = campaign_process.run_lane(
        workspace,
        submission,
        stage="run",
        runtime=runtime,
        root_execution_id=submission["rootExecutionId"],
        timeout_seconds=None,
        lane_runner=capture_command,
        run_session=run_session,
        observer_binary_binding=None,
        fleet_transport_binding=None,
    )

    assert result == (0, None)
    assert len(commands) == 1
    command = commands[0]

    def argument_values(flag: str) -> list[str]:
        return [
            command[index + 1]
            for index, value in enumerate(command[:-1])
            if value == flag
        ]

    assert argument_values("--quota") == ["1"]
    assert argument_values("--count") == ["2"]
    assert argument_values("--capacity-calibration-receipt") == []
    assert argument_values("--scale-source-pool-id") == [
        "m1-article-culture-china"
    ]
    assert argument_values("--scale-source-pool-target-scale") == ["WORKLOAD"]
    assert argument_values("--scale-source-pool-plan-ref") == [
        "data/local/workspace/source-pool/plan.json"
    ]
    assert argument_values("--scale-source-pool-plan-digest") == [plan_digest]
    assert argument_values("--scale-source-pool-plan-file-sha256") == [
        plan_file_sha256
    ]
    assert argument_values("--source-pool-source-revision") == [source_revision]
    assert argument_values("--source-pool-source-digest") == [source_digest]
    assert argument_values("--source-pool-entity-catalog-digest") == [
        entity_catalog_digest
    ]
    assert argument_values("--source-pool-evidence-root-ref") == [
        "data/local/workspace/source-pool/evidence"
    ]
    assert argument_values("--source-pool-carrier") == ["article"]
    assert argument_values("--source-pool-selection-digest") == [selection_digest]
    assert argument_values("--source-pool-candidate-id") == candidate_ids
    assert "--target" not in command
    assert checkpoints[-1]["status"] == "succeeded"


def test_detached_branch_fallback_requires_campaign_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    branch = _git(repo, "branch", "--show-current")
    _git(repo, "checkout", "--detach")

    assert current_git_branch(cwd=repo) == ""
    monkeypatch.setenv("QWQ_FROZEN_MAIN_BRANCH", branch)
    assert current_git_branch(cwd=repo) == ""
    monkeypatch.setenv("QWQ_CAMPAIGN_ROOT_EXECUTION_ID", ROOT_ID)
    write_json(
        repo / ".qwq_campaign_capsule.json",
        {
            "format": "source-capsule-v2",
            "gitBranch": branch,
            "gitCommitSha": _git(repo, "rev-parse", "HEAD"),
        },
    )
    assert current_git_branch(cwd=repo) == branch
    monkeypatch.setenv("QWQ_FROZEN_MAIN_BRANCH", "dev1.0")
    assert current_git_branch(cwd=repo) == ""
    monkeypatch.setenv("QWQ_FROZEN_MAIN_BRANCH", branch)
    spec = {"executionPolicy": {}}
    stamp_execution_branch(spec, cwd=repo)
    assert spec["executionPolicy"] == {
        "executionBranch": branch,
        "gitCommitSha": _git(repo, "rev-parse", "HEAD"),
    }


def test_capsule_captured_dev_branch_remains_a_typed_branch_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capsule = tmp_path / "capsule"
    policy = capsule / "quwoquan_ops/policies/branch_policy.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("allowed_local_branches:\n  - main\n", encoding="utf-8")
    write_json(
        capsule / ".qwq_campaign_capsule.json",
        {
            "format": "source-capsule-v2",
            "gitBranch": "dev1.0",
            "gitCommitSha": "a" * 40,
        },
    )
    monkeypatch.setenv("QWQ_CAMPAIGN_ROOT_EXECUTION_ID", ROOT_ID)
    monkeypatch.setenv("QWQ_FROZEN_MAIN_BRANCH", "dev1.0")

    assert current_git_branch(cwd=capsule) == "dev1.0"
    assert execution_branch_issues(cwd=capsule) == [
        "当前 git 分支 'dev1.0' 不在正式分支 allowlist ['main']；"
        "商业执行只允许 mainline（临时 feature 分支绑定已废止）"
    ]


def test_real_subprocess_lanes_overlap_and_publish_only_after_own_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    event_log = tmp_path / "events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(event_log))
    monkeypatch.setenv("SLOW_REVIEW_CARRIER", "video")
    report_updates: list[dict[str, object]] = []
    write_report = campaign_orchestrator.write_report

    def recording_write_report(*args, **kwargs):
        report_updates.append(json.loads(json.dumps(kwargs)))
        return write_report(*args, **kwargs)

    monkeypatch.setattr(
        campaign_orchestrator,
        "write_report",
        recording_write_report,
    )

    report_path = campaign_controller.run_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        lane_timeout_seconds=5,
        runtime_paths=runtime,
    )

    report = read_json(report_path)
    assert report["status"] == "succeeded"
    assert report["phase"] == "completed"
    assert report["planDigest"].startswith("sha256:")
    assert report["campaignRunId"]
    assert report["campaignGeneration"] == 1
    assert report["campaignFencingToken"].startswith("sha256:")
    assert report["gitBranch"] == _git(repo, "branch", "--show-current")
    review_events = [row for row in _events(event_log) if row["phase"] == "review"]
    publish_events = [row for row in _events(event_log) if row["phase"] == "publish"]
    review_starts = {
        row["carrier"]: row["at"] for row in review_events if row["kind"] == "start"
    }
    review_ends = {
        row["carrier"]: row["at"] for row in review_events if row["kind"] == "end"
    }
    assert set(review_starts) == set(CARRIERS)
    assert max(review_starts.values()) < min(review_ends.values())
    # Own-lane ordering only: each publish starts after that carrier's review end.
    publish_starts = {
        row["carrier"]: row["at"] for row in publish_events if row["kind"] == "start"
    }
    assert set(publish_starts) == set(CARRIERS)
    for carrier in CARRIERS:
        assert publish_starts[carrier] >= review_ends[carrier]
    assert min(publish_starts.values()) < review_ends["video"]
    assert len({row["pid"] for row in review_events}) == 4
    for lane in report["lanes"].values():
        assert lane["reviewReturnCode"] == 0
        assert lane["publishReturnCode"] == 0
        assert lane["qualifiedCount"] == 1
        assert lane["finalizedCount"] == 1
    capsule_progress = {
        sum(
            1
            for lane in update["lanes"].values()
            if lane["status"] == "capsule_ready"
        )
        for update in report_updates
        if update["status"] == "running" and update["phase"] == "capsule"
    }
    assert {1, 2, 3, 4} <= capsule_progress
    assert any(
        update["status"] == "running"
        and update["phase"] == "publish"
        and any(
            int(lane.get("finalizedCount") or 0) > 0
            for lane in update["lanes"].values()
        )
        for update in report_updates
    )
    runtime_snapshot = read_runtime_snapshot(runtime, ROOT_ID)
    assert runtime_snapshot is not None
    assert runtime_snapshot["status"] == "succeeded"
    assert runtime_snapshot["phase"] == "completed"
    assert runtime_snapshot["generation"] == 1
    assert set(runtime_snapshot["lanes"]) == set(CARRIERS)
    assert all(
        set(row)
        == {
            "executionId",
            "phase",
            "status",
            "pid",
            "pgid",
            "returnCode",
            "updatedAt",
        }
        for row in runtime_snapshot["lanes"].values()
    )
    runtime_events = _events(runtime_events_path(runtime, ROOT_ID))
    assert runtime_events[0]["eventType"] == "campaign_started"
    assert runtime_events[-1]["eventType"] == "campaign_finished"
    _assert_capsule_reused_and_lane_roots_isolated(runtime, report)


def test_repeated_freeze_reuses_existing_plan_without_fencing_lanes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)

    first_report = campaign_distributed.freeze_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        runtime_paths=runtime,
    )
    first_snapshot = read_runtime_snapshot(runtime, ROOT_ID)

    second_report = campaign_distributed.freeze_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        runtime_paths=runtime,
    )

    assert second_report == first_report
    assert read_runtime_snapshot(runtime, ROOT_ID) == first_snapshot
    assert first_snapshot["status"] == "frozen"


def test_four_copied_sessions_claim_independent_lanes_and_finalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    event_log = tmp_path / "distributed-events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(event_log))

    frozen_report = campaign_distributed.freeze_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        runtime_paths=runtime,
    )
    frozen = read_json(frozen_report)
    plan = read_json(
        runtime.campaigns_root / ROOT_ID / "campaign_plan.json"
    )
    assert frozen["phase"] == "capsule"
    assert plan["executionMode"] == "distributed"
    assert plan["distributedRun"]["campaignRunId"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(
                campaign_distributed.run_campaign_lane,
                ROOT_ID,
                carrier,
                lane_timeout_seconds=5,
                runtime_paths=runtime,
            )
            for carrier in CARRIERS
        ]
        for future in futures:
            future.result()

    report_path = campaign_distributed.finalize_campaign(
        ROOT_ID,
        runtime_paths=runtime,
    )
    report = read_json(report_path)
    assert report["status"] == "succeeded"
    assert report["phase"] == "completed"
    assert report["campaignRunId"] == plan["distributedRun"]["campaignRunId"]
    assert report["campaignGeneration"] == plan["distributedRun"][
        "campaignGeneration"
    ]
    review_events = [
        row for row in _events(event_log) if row["phase"] == "review"
    ]
    starts = {
        row["carrier"]: row["at"] for row in review_events if row["kind"] == "start"
    }
    ends = {
        row["carrier"]: row["at"] for row in review_events if row["kind"] == "end"
    }
    assert set(starts) == set(CARRIERS)
    assert max(starts.values()) < min(ends.values())
    capsule_refs: set[str] = set()
    execution_roots: set[Path] = set()
    for carrier in CARRIERS:
        claim = read_lane_claim(runtime, ROOT_ID, carrier)
        assert claim is not None
        assert claim["status"] == "completed"
        assert claim["executionId"] == plan["executionIds"][carrier]
        assert claim["campaignRunId"] == plan["distributedRun"]["campaignRunId"]
        assert claim["capsuleRef"] == frozen["lanes"][carrier][
            "sourceCapsuleRef"
        ]
        capsule_refs.add(str(claim["capsuleRef"]))
        execution_root = Path(str(claim["executionRoot"]))
        assert execution_root.parent == runtime.output_root / "data/tasks"
        execution_roots.add(execution_root)
        assert report["lanes"][carrier]["finalizedCount"] == 1
    assert len(capsule_refs) == 1
    assert len(execution_roots) == len(CARRIERS)
    capsule_path = runtime.output_root / next(iter(capsule_refs))
    assert capsule_path.is_dir()
    assert not capsule_path.stat().st_mode & 0o222
    runtime_snapshot = read_runtime_snapshot(runtime, ROOT_ID)
    assert runtime_snapshot is not None
    assert runtime_snapshot["status"] == "succeeded"
    assert runtime_snapshot["phase"] == "completed"
    assert runtime_snapshot["runId"] == plan["distributedRun"]["campaignRunId"]
    assert set(runtime_snapshot["lanes"]) == set(CARRIERS)
    for carrier in CARRIERS:
        checkpoint = read_lane_checkpoint(runtime, ROOT_ID, carrier)
        assert checkpoint is not None
        assert checkpoint["runId"] == plan["distributedRun"]["campaignRunId"]
        assert checkpoint["generation"] == plan["distributedRun"][
            "campaignGeneration"
        ]
        assert checkpoint["fencingToken"] == plan["distributedRun"][
            "campaignFencingToken"
        ]
        assert checkpoint["executionId"] == plan["executionIds"][carrier]
        assert checkpoint["phase"] == "run"
        assert checkpoint["status"] == "succeeded"
        assert checkpoint["returnCode"] == 0
    assert (runtime.campaigns_root / ROOT_ID / "copy_ready_receipt.json").is_file()
