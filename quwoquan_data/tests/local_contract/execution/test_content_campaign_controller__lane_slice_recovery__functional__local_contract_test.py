# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import signal
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import distributed as campaign_distributed
from content.execution.campaign import lane_execution as campaign_lane_execution
from content.execution.campaign import orchestrator as campaign_orchestrator
from content.execution.campaign import plan as campaign_plan
from content.execution.campaign.workspace import CampaignRuntimePaths
from core.io import write_json
from support.capacity_calibration_fixture import (
    synthetic_capacity_source_binding,
    synthetic_governed_execution_authority,
)
from support.campaign_lanes_fixture import (  # noqa: F401
    CARRIERS,
    ROOT_ID,
    _restore_capsule_permissions_for_pytest_cleanup,
)


def test_semantic_campaign_does_not_bind_pool_delivery_observer() -> None:
    assert not hasattr(campaign_orchestrator, "resolve_campaign_observer_binary")
    assert not hasattr(campaign_distributed, "resolve_campaign_observer_binary")
    assert not hasattr(campaign_orchestrator, "resolve_campaign_fleet_transport")
    assert not hasattr(campaign_distributed, "resolve_campaign_fleet_transport")


def test_four_reviewed_lanes_with_frozen_delivery_intents_close_partial() -> None:
    lanes = {}
    for carrier in CARRIERS:
        lane = campaign_plan.empty_lane(f"execution-{carrier}")
        lane.update(
            {
                "status": "delivery_pending",
                "phase": "publish",
                "approvedQuota": 1,
                "qualifiedCount": 1,
                "finalizedCount": 0,
                "deliveryPendingCount": 1,
                "deliveryIntentRefs": [f"intents/{carrier}.json"],
                "publishReturnCode": 10,
                "error": "DATA.POOL.DELIVERY_UNAVAILABLE",
            }
        )
        lanes[carrier] = lane

    assert campaign_plan.aggregate_status(lanes) == "succeeded_partial"
    assert sum(lane["qualifiedCount"] for lane in lanes.values()) == 4
    assert sum(lane["deliveryPendingCount"] for lane in lanes.values()) == 4
    assert sum(lane["finalizedCount"] for lane in lanes.values()) == 0


def test_only_typed_execution_checkpoints_are_resumable_lane_slices(
    tmp_path: Path,
) -> None:
    state = tmp_path / "_shared/execution_state.json"
    state.parent.mkdir(parents=True)
    write_json(
        state,
        {
            "status": "waiting_agent",
            "waitingCheckpoint": "post_author",
            "controllerYield": None,
        },
    )
    assert campaign_lane_execution._execution_has_resumable_checkpoint(tmp_path) is True
    write_json(
        state,
        {
            "status": "repairing",
            "waitingCheckpoint": "post_review",
            "controllerYield": {
                "stage": "download_plan",
                "reason": "mismatched stage",
            },
        },
    )
    assert campaign_lane_execution._execution_has_resumable_checkpoint(tmp_path) is False

    write_json(
        state,
        {"status": "manual_required", "waitingCheckpoint": None},
    )
    assert campaign_lane_execution._execution_has_resumable_checkpoint(tmp_path) is False

    write_json(
        state,
        {
            "status": "repairing",
            "waitingCheckpoint": "download_plan",
            "controllerYield": {
                "stage": "download_plan",
                "reason": "managed slice completed",
            },
        },
    )
    assert campaign_lane_execution._execution_has_resumable_checkpoint(tmp_path) is True


def test_campaign_lane_argv_binds_audited_stage_recovery() -> None:
    submission = {
        "executionId": "20260810--travel-homepage-m1--china--scale-005",
        "rootExecutionId": "20260810--travel-homepage-m1--china--scale-005",
        "familyRef": "travel-homepage-m1",
        "regionRef": "china/四川省",
        "selector": "named-targets",
        "quota": 1,
        "count": 1,
        "executionAuthority": synthetic_governed_execution_authority(),
        "semanticSelectionId": "cursor_auto",
        "targetNames": ["都江堰"],
    }

    argv = campaign_lane_execution._lane_argv(
        submission,
        stage="review-only",
        recover_stage="build_homepage",
        recovery_reason="retry failed author against the frozen writing pack",
    )

    recover_index = argv.index("--recover-stage")
    assert argv[recover_index + 1] == "build_homepage"
    assert argv[recover_index + 2 :] == [
        "--recovery-reason",
        "retry failed author against the frozen writing pack",
    ]


def test_lane_runner_resumes_controller_yields_in_one_create_once_claim(
    monkeypatch,
    tmp_path,
) -> None:
    return_codes = iter((10, 0))
    spawned: list[int] = []

    class FakeProcess:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pid = 8000 + len(spawned)
            self.return_code = next(return_codes)
            spawned.append(self.pid)

        def wait(self, timeout=None):
            del timeout
            return self.return_code

    checkpoints: list[dict[str, object]] = []
    session = SimpleNamespace(
        process_termination_timeout_seconds=1,
        lane_checkpoint=lambda **kwargs: checkpoints.append(kwargs),
    )
    workspace = SimpleNamespace(
        carrier="article",
        ref="data/local/cache/capsule/article",
        execution_root=tmp_path / "execution",
    )
    workspace.execution_root.mkdir()
    state = workspace.execution_root / "_shared/execution_state.json"
    state.parent.mkdir()
    write_json(
        state,
        {
            "status": "waiting_agent",
            "waitingCheckpoint": "post_author",
            "controllerYield": None,
        },
    )
    monkeypatch.setattr(campaign_lane_execution.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(campaign_lane_execution.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        campaign_lane_execution,
        "_process_group_rss_bytes",
        lambda _pgid: 64 * 1024**2,
    )
    monkeypatch.setattr(
        campaign_lane_execution,
        "_execution_heartbeat_at",
        lambda _root: "2026-08-07T08:00:00+00:00",
    )

    code = campaign_lane_execution._default_lane_runner(
        ["python", "cli.py"],
        tmp_path,
        {},
        tmp_path / "lane.log",
        None,
        run_session=session,
        workspace=workspace,
        execution_id="20260807--travel-article-m100--china--scale-001",
        stage="review-only",
    )

    assert code == 0
    assert len(spawned) == 2
    yield_checkpoint = next(
        checkpoint
        for checkpoint in checkpoints
        if checkpoint.get("return_code") == campaign_lane_execution._LANE_SLICE_YIELD_CODE
    )
    assert yield_checkpoint["process_evidence"]["terminationOwner"] == "controller_yield"
    evidence = checkpoints[-1]["process_evidence"]
    assert evidence["sliceCount"] == 2
    assert evidence["resumeCount"] == 1
    assert evidence["maxRssBytes"] == 64 * 1024**2
    assert evidence["terminationOwner"] == "lane_process"
    assert "resuming create-once lane checkpoint" in (
        tmp_path / "lane.log"
    ).read_text(encoding="utf-8")


def test_lane_runner_stops_identical_checkpoint_resume_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    return_codes = iter((10, 10, 10, 0))
    spawned: list[int] = []

    class FakeProcess:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pid = 8500 + len(spawned)
            self.return_code = next(return_codes)
            spawned.append(self.pid)

        def wait(self, timeout=None):
            del timeout
            return self.return_code

    session = SimpleNamespace(
        process_termination_timeout_seconds=1,
        lane_checkpoint=lambda **_kwargs: None,
    )
    workspace = SimpleNamespace(
        carrier="homepage",
        ref="data/local/cache/capsule/homepage",
        execution_root=tmp_path / "execution",
    )
    state = workspace.execution_root / "_shared/execution_state.json"
    state.parent.mkdir(parents=True)
    write_json(
        state,
        {
            "status": "waiting_agent",
            "waitingCheckpoint": "build_homepage",
            "completed": ["download_plan", "download_fetch", "build_prepare"],
            "retryCounts": {},
            "reactRewinds": {"build_validate": 1},
            "controllerYield": None,
        },
    )
    monkeypatch.setattr(campaign_lane_execution.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(campaign_lane_execution.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        campaign_lane_execution,
        "_process_group_rss_bytes",
        lambda _pgid: 0,
    )
    monkeypatch.setattr(
        campaign_lane_execution,
        "_execution_heartbeat_at",
        lambda _root: "2026-08-07T08:00:00+00:00",
    )

    log_path = tmp_path / "lane.log"
    code = campaign_lane_execution._default_lane_runner(
        ["python", "cli.py"],
        tmp_path,
        {},
        log_path,
        30,
        run_session=session,
        workspace=workspace,
        execution_id="20260807--travel-homepage-m1--china--scale-013",
        stage="review-only",
    )

    assert code == 1
    assert len(spawned) == 3
    assert "terminal no-progress checkpoint loop checkpoint=build_homepage" in (
        log_path.read_text(encoding="utf-8")
    )


def test_lane_runner_does_not_resume_non_yield_from_stale_waiting_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    return_codes = iter((1, 0))
    spawned: list[int] = []

    class FakeProcess:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pid = 9000 + len(spawned)
            self.return_code = next(return_codes)
            spawned.append(self.pid)

        def wait(self, timeout=None):
            del timeout
            return self.return_code

    checkpoints: list[dict[str, object]] = []
    session = SimpleNamespace(
        process_termination_timeout_seconds=1,
        lane_checkpoint=lambda **kwargs: checkpoints.append(kwargs),
    )
    workspace = SimpleNamespace(
        carrier="video",
        ref="data/local/cache/capsule/video",
        execution_root=tmp_path / "execution",
    )
    state = workspace.execution_root / "_shared/execution_state.json"
    state.parent.mkdir(parents=True)
    write_json(
        state,
        {
            "status": "waiting_agent",
            "waitingCheckpoint": "post_review",
            "controllerYield": None,
        },
    )
    monkeypatch.setattr(campaign_lane_execution.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(campaign_lane_execution.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        campaign_lane_execution,
        "_process_group_rss_bytes",
        lambda _pgid: 32 * 1024**2,
    )
    monkeypatch.setattr(
        campaign_lane_execution,
        "_execution_heartbeat_at",
        lambda _root: "2026-08-07T08:00:00+00:00",
    )

    log_path = tmp_path / "lane.log"
    code = campaign_lane_execution._default_lane_runner(
        ["python", "cli.py"],
        tmp_path,
        {},
        log_path,
        30,
        run_session=session,
        workspace=workspace,
        execution_id="20260807--travel-video-m100--china--scale-001",
        stage="review-only",
    )

    assert code == 1
    assert len(spawned) == 1
    assert "resuming create-once lane checkpoint" not in log_path.read_text(
        encoding="utf-8"
    )
    assert checkpoints[-1]["return_code"] == 1
    evidence = checkpoints[-1]["process_evidence"]
    assert evidence["sliceCount"] == 1
    assert evidence["resumeCount"] == 0
    assert evidence["terminationOwner"] == "lane_process"


def test_sigkill_termination_evidence_does_not_falsely_claim_oom() -> None:
    owner, signal_name = campaign_lane_execution._termination_owner(-signal.SIGKILL)

    assert owner == "external_or_kernel"
    assert signal_name == "SIGKILL"


def test_process_evidence_sampling_timeout_does_not_become_lane_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def sampling_timeout(*_args, **_kwargs):
        raise campaign_lane_execution.subprocess.TimeoutExpired(["ps"], 0.01)

    monkeypatch.setattr(campaign_lane_execution.subprocess, "run", sampling_timeout)

    assert campaign_lane_execution._process_group_rss_bytes(1234) == 0


def test_lane_runner_continues_when_process_evidence_sample_times_out(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeProcess:
        pid = 9100

        def __init__(self, *_args, **_kwargs) -> None:
            self.wait_calls = 0

        def wait(self, timeout=None):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise campaign_lane_execution.subprocess.TimeoutExpired(
                    ["python", "cli.py"], timeout
                )
            return 0

    checkpoints: list[dict[str, object]] = []
    session = SimpleNamespace(
        process_termination_timeout_seconds=1,
        lane_checkpoint=lambda **kwargs: checkpoints.append(kwargs),
    )
    workspace = SimpleNamespace(
        carrier="video",
        ref="data/local/cache/capsule/video",
        execution_root=tmp_path / "execution",
    )
    workspace.execution_root.mkdir()
    monkeypatch.setattr(campaign_lane_execution.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(campaign_lane_execution.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        campaign_lane_execution.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            campaign_lane_execution.subprocess.TimeoutExpired(["ps"], 0.01)
        ),
    )
    monkeypatch.setattr(
        campaign_lane_execution,
        "terminate_lane_process",
        lambda *_args, **_kwargs: pytest.fail(
            "diagnostic process sampling must never terminate the lane"
        ),
    )

    code = campaign_lane_execution._default_lane_runner(
        ["python", "cli.py"],
        tmp_path,
        {},
        tmp_path / "lane.log",
        None,
        run_session=session,
        workspace=workspace,
        execution_id="20260814--travel-video-workload-video-15--china--scale-002",
        stage="review-only",
    )

    assert code == 0
    assert checkpoints[-1]["status"] == "running"
    assert checkpoints[-1]["return_code"] == 0
    assert checkpoints[-1]["process_evidence"]["maxRssBytes"] == 0


def test_lane_without_deadline_does_not_report_monitor_timeout_as_campaign_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    execution_id = "20260814--travel-video-workload-video-15--china--scale-002"
    execution_root = tmp_path / "output" / "data" / "tasks" / execution_id
    execution_root.mkdir(parents=True)
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    workspace = SimpleNamespace(
        carrier="video",
        path=capsule,
        ref="data/local/cache/content-campaign-workspaces/capsule",
        execution_root=execution_root,
        capsule=SimpleNamespace(git_branch="main", commit_sha="a" * 40),
    )
    runtime = CampaignRuntimePaths(
        repo_root=tmp_path,
        output_root=tmp_path / "output",
        publish_root=tmp_path / "publish",
        campaigns_root=tmp_path / "campaigns",
        workspaces_root=tmp_path / "workspaces",
    )
    checkpoints: list[dict[str, object]] = []
    session = SimpleNamespace(
        run_id="campaign-run",
        generation=1,
        fencing_token="sha256:" + "1" * 64,
        plan_digest="sha256:" + "2" * 64,
        lane_checkpoint=lambda **kwargs: checkpoints.append(kwargs),
    )

    def monitor_failed(*_args, **_kwargs):
        raise campaign_lane_execution.subprocess.TimeoutExpired(["ps"], 0.01)

    monkeypatch.setattr(
        campaign_lane_execution,
        "_verify_workspace_external_inputs",
        lambda _workspace: None,
    )
    code, error = campaign_lane_execution.run_lane(
        workspace,
        {
            "executionId": execution_id,
            "sourceDigest": {"digest": "sha256:" + "3" * 64},
            "sourceRevision": "sha256:" + "4" * 64,
            "entityCatalogDigest": "sha256:" + "5" * 64,
            "semanticSelectionId": "cursor_grok",
            "rootExecutionId": execution_id,
            "familyRef": "content/travel/video/video",
            "regionRef": "china",
            "selector": "source-ready-priority",
            "quota": 15,
            "count": 27,
            "executionAuthority": synthetic_governed_execution_authority(),
        },
        stage="review-only",
        runtime=runtime,
        root_execution_id=execution_id,
        timeout_seconds=None,
        lane_runner=monitor_failed,
        run_session=session,
        observer_binary_binding=None,
        fleet_transport_binding=None,
    )

    assert code == 2
    assert error is not None
    assert "after Nones" not in error
    assert checkpoints[-1]["status"] == "failed"
    assert checkpoints[-1]["return_code"] == 2


@pytest.mark.parametrize("terminal_source", ("execution_state", "command_packet"))
def test_failed_lane_prefers_typed_terminal_cause_over_truncated_log_tail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    terminal_source: str,
) -> None:
    execution_id = "20260807--travel-video-m1--china--scale-001"
    execution_root = tmp_path / "output" / "data" / "tasks" / execution_id
    shared = execution_root / "_shared"
    shared.mkdir(parents=True)
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    workspace = SimpleNamespace(
        carrier="video",
        path=capsule,
        ref="data/local/cache/content-campaign-workspaces/capsule",
        execution_root=execution_root,
        capsule=SimpleNamespace(git_branch="main", commit_sha="a" * 40),
    )
    runtime = CampaignRuntimePaths(
        repo_root=tmp_path,
        output_root=tmp_path / "output",
        publish_root=tmp_path / "publish",
        campaigns_root=tmp_path / "campaigns",
        workspaces_root=tmp_path / "workspaces",
    )
    checkpoints: list[dict[str, object]] = []
    session = SimpleNamespace(
        run_id="campaign-run",
        generation=1,
        fencing_token="sha256:" + ("1" * 64),
        plan_digest="sha256:" + ("2" * 64),
        lane_checkpoint=lambda **kwargs: checkpoints.append(kwargs),
    )
    missing_contract = (
        capsule
        / "quwoquan_service/services/recommendation-service/contracts/"
        "recommendation/recommendation_feature_profile_view/projections/"
        "intersection_reason.yaml"
    )
    issue_record = {
        "code": "DATA.INTERNAL.UNEXPECTED",
        "stage": "post_review",
        "ref": "",
        "lane": "all",
        "recovery": "stop",
        "message": "execution stage raised an unexpected exception",
        "attrs": {
            "errorType": "FileNotFoundError",
            "errorMessage": f"IntersectionReason metadata is required: {missing_contract}",
            "errorLocation": "intersection_signal.py:49:contract_field_names",
        },
    }

    def failed_lane_runner(_command, _cwd, _env, log_path, _timeout):
        if terminal_source == "execution_state":
            write_json(
                shared / "execution_state.json",
                {
                    "executionId": execution_id,
                    "status": "manual_required",
                    "lastFailedStage": "post_review",
                    "nextAction": "post_review raised FileNotFoundError",
                    "failedIssueRecords": [issue_record],
                },
            )
        else:
            write_json(
                shared / "command_packets" / "post_review.json",
                {
                    "executionId": execution_id,
                    "stage": "post_review",
                    "outputs": {
                        "status": "failed",
                        "message": "post_review raised FileNotFoundError",
                        "issueRecords": [issue_record],
                    },
                },
            )
        lines = [
            (
                "[task execute] FAILED at 'post_review': "
                "post_review raised FileNotFoundError"
            ),
            *[f"[post] Materialized tail line {index}" for index in range(15)],
        ]
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert lines[0] not in lines[-12:]
        return 1

    monkeypatch.setattr(
        campaign_lane_execution,
        "_verify_workspace_external_inputs",
        lambda _workspace: None,
    )
    code, error = campaign_lane_execution.run_lane(
        workspace,
        {
            "executionId": execution_id,
            "gitBranch": "main",
            "gitCommitSha": "a" * 40,
            "sourceDigest": {"digest": "sha256:" + ("3" * 64)},
            "sourceRevision": "sha256:" + ("4" * 64),
            "entityCatalogDigest": "sha256:" + ("5" * 64),
            "semanticSelectionId": "cursor_auto",
            "rootExecutionId": ROOT_ID,
            "familyRef": "content/travel/video/video",
            "regionRef": "china",
            "selector": "source-ready-priority",
                "quota": 1,
                "count": 1,
                "executionAuthority": synthetic_governed_execution_authority(),
        },
        stage="review-only",
        runtime=runtime,
        root_execution_id=ROOT_ID,
        timeout_seconds=30,
        lane_runner=failed_lane_runner,
        run_session=session,
        observer_binary_binding=None,
        fleet_transport_binding=None,
    )

    assert code == 1
    assert error is not None
    assert error.startswith("post_review raised FileNotFoundError")
    assert "DATA.INTERNAL.UNEXPECTED" in error
    assert str(missing_contract) in error
    assert "Materialized tail line" not in error
    assert checkpoints[-1]["error"] == error
