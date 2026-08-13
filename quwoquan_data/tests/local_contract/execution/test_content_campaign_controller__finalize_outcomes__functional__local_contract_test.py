# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from content.execution.campaign import controller as campaign_controller
from content.execution.campaign import distributed as campaign_distributed
from content.execution.campaign import lane_execution as campaign_lane_execution
from content.execution.campaign import submission as campaign_submission
from content.execution.campaign.lane_claim import read_lane_claim
from content.execution.campaign.runtime import (
    read_lane_checkpoint,
    read_runtime_snapshot,
)
from core.io import read_json
from support.campaign_lanes_fixture import (  # noqa: F401
    CARRIERS,
    ROOT_ID,
    _assert_capsule_reused_and_lane_roots_isolated,
    _create_repo,
    _events,
    _execution_id,
    _git,
    _request,
    _restore_capsule_permissions_for_pytest_cleanup,
    _runtime,
    _semantic_preflight_kwargs,
    _submit_all,
)
from support.semantic_preflight_fixture import ready_semantic_preflight


def test_completed_campaign_restart_reuses_capsule_and_lane_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    first_events = tmp_path / "first-events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(first_events))
    first_report_path = campaign_controller.run_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        lane_timeout_seconds=5,
        runtime_paths=runtime,
    )
    first_report = read_json(first_report_path)
    first_capsule_refs = {
        lane["sourceCapsuleRef"] for lane in first_report["lanes"].values()
    }
    assert len(first_capsule_refs) == 1

    replay_events = tmp_path / "replay-events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(replay_events))
    second_report_path = campaign_controller.run_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        lane_timeout_seconds=5,
        runtime_paths=runtime,
    )
    second_report = read_json(second_report_path)
    assert second_report["status"] == "succeeded"
    assert {
        lane["sourceCapsuleRef"] for lane in second_report["lanes"].values()
    } == first_capsule_refs
    assert not replay_events.exists()
    snapshot = read_runtime_snapshot(runtime, ROOT_ID)
    assert snapshot is not None
    assert snapshot["generation"] == 2
    assert snapshot["status"] == "succeeded"
    for carrier in CARRIERS:
        checkpoint = read_lane_checkpoint(runtime, ROOT_ID, carrier)
        assert checkpoint is not None
        assert checkpoint["status"] == "recovered"
        assert checkpoint["phase"] == "publish"
    _assert_capsule_reused_and_lane_roots_isolated(runtime, second_report)


def test_one_lane_review_failure_does_not_block_sibling_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    event_log = tmp_path / "events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(event_log))
    monkeypatch.setenv("FAIL_REVIEW_CARRIER", "article")

    report_path = campaign_controller.run_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        lane_timeout_seconds=5,
        runtime_paths=runtime,
    )
    report = read_json(report_path)
    assert report["status"] == "succeeded_partial"
    assert report["lanes"]["article"]["status"] == "blocked"
    assert report["lanes"]["article"]["reviewReturnCode"] == 19
    for carrier in ("homepage", "image", "video"):
        assert report["lanes"][carrier]["publishReturnCode"] == 0
        assert report["lanes"][carrier]["finalizedCount"] == 1
    publish_carriers = {
        row["carrier"]
        for row in _events(event_log)
        if row["phase"] == "publish" and row["kind"] == "start"
    }
    assert publish_carriers == {"homepage", "image", "video"}
    _assert_capsule_reused_and_lane_roots_isolated(runtime, report)


def test_finalize_uses_frozen_capsule_after_live_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    monkeypatch.setenv(
        "CAMPAIGN_EVENT_LOG",
        str(tmp_path / "finalize-after-source-drift.ndjson"),
    )
    frozen = read_json(
        campaign_distributed.freeze_campaign(
            ROOT_ID,
            submission_timeout_seconds=2,
            runtime_paths=runtime,
        )
    )
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

    (repo / "quwoquan_data/schema/source.txt").write_text(
        "source changed after all lane claims settled",
        encoding="utf-8",
    )

    report = read_json(
        campaign_distributed.finalize_campaign(
            ROOT_ID,
            runtime_paths=runtime,
        )
    )
    assert report["status"] == "succeeded"
    assert report["phase"] == "completed"
    assert {
        lane["sourceCapsuleRef"] for lane in report["lanes"].values()
    } == {
        lane["sourceCapsuleRef"] for lane in frozen["lanes"].values()
    }
    assert {
        lane["sourceCapsuleDigest"] for lane in report["lanes"].values()
    } == {
        lane["sourceCapsuleDigest"] for lane in frozen["lanes"].values()
    }


def test_finalize_terminally_blocks_without_consuming_corrupted_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    frozen = read_json(
        campaign_distributed.freeze_campaign(
            ROOT_ID,
            submission_timeout_seconds=2,
            runtime_paths=runtime,
        )
    )
    capsule_ref = frozen["lanes"]["homepage"]["sourceCapsuleRef"]
    capsule_root = runtime.output_root / capsule_ref
    capsule_root.chmod(capsule_root.stat().st_mode | 0o200)
    (capsule_root / "post-freeze-drift.txt").write_text(
        "immutable capsule was modified",
        encoding="utf-8",
    )
    capsule_root.chmod(capsule_root.stat().st_mode & ~0o222)
    monkeypatch.setattr(
        campaign_distributed,
        "prepare_distributed_workspace",
        lambda *_args, **_kwargs: pytest.fail("corrupted capsule was consumed"),
    )

    report = read_json(
        campaign_distributed.finalize_campaign(
            ROOT_ID,
            runtime_paths=runtime,
        )
    )

    assert report["status"] == "blocked"
    assert report["phase"] == "completed"
    assert report["failure"].startswith(
        "DATA.CONTRACT.INVALID: campaign capsule integrity failure:"
    )
    assert "campaign capsule tree digest drift" in report["failure"]
    for lane in report["lanes"].values():
        assert lane["status"] == "blocked"
        assert lane["phase"] == "capsule"
        assert lane["sourceCapsuleReadOnly"] is False
        assert lane["cleanupStatus"] == "failed"
        assert lane["error"] == report["failure"]
    assert not (
        runtime.campaigns_root / ROOT_ID / "copy_ready_receipt.json"
    ).exists()


def test_quota_shortfall_publishes_partial_qualified_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch, count=2, quota=2)
    event_log = tmp_path / "events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(event_log))
    monkeypatch.setenv("SHORT_REVIEW_CARRIER", "image")

    report_path = campaign_controller.run_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        lane_timeout_seconds=5,
        runtime_paths=runtime,
    )
    report = read_json(report_path)
    assert report["status"] == "succeeded_partial"
    image = report["lanes"]["image"]
    assert image["status"] == "partial"
    assert image["qualifiedCount"] == 1
    assert image["finalizedCount"] == 1
    assert image["shortfallCount"] == 1
    assert image["discardedCount"] == 1
    for carrier in ("homepage", "article", "video"):
        assert report["lanes"][carrier]["finalizedCount"] == 2
        assert report["lanes"][carrier]["status"] == "finalized"
    assert any(row["phase"] == "publish" for row in _events(event_log))
    _assert_capsule_reused_and_lane_roots_isolated(runtime, report)


def test_zero_qualified_lane_stays_blocked_without_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    event_log = tmp_path / "events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(event_log))
    monkeypatch.setenv("ZERO_REVIEW_CARRIER", "video")

    report_path = campaign_controller.run_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        lane_timeout_seconds=5,
        runtime_paths=runtime,
    )
    report = read_json(report_path)
    assert report["status"] == "succeeded_partial"
    assert report["lanes"]["video"]["status"] == "blocked"
    assert report["lanes"]["video"]["qualifiedCount"] == 0
    publish_carriers = {
        row["carrier"] for row in _events(event_log) if row["phase"] == "publish"
    }
    assert "video" not in publish_carriers
    for carrier in ("homepage", "article", "image"):
        assert report["lanes"][carrier]["finalizedCount"] == 1
    _assert_capsule_reused_and_lane_roots_isolated(runtime, report)


def test_submission_collision_and_cross_lane_mismatch_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    monkeypatch.setattr(campaign_submission.paths, "REPO_ROOT", repo)
    article_id = _execution_id("article")
    preflight = _semantic_preflight_kwargs(runtime)
    campaign_submission.write_submission(
        root_execution_id=ROOT_ID,
        execution_id=article_id,
        request=_request("article"),
        retry_of=None,
        repo_root=repo,
        root=runtime.campaigns_root,
        **preflight,
    )
    other_root = "20260728--travel-homepage-scale--china--scale-002"
    with pytest.raises(ValueError, match="already belongs to campaign"):
        campaign_submission.write_submission(
            root_execution_id=other_root,
            execution_id=article_id,
            request=_request("article"),
            retry_of=None,
            repo_root=repo,
            root=runtime.campaigns_root,
            **preflight,
        )

    campaign_submission.write_submission(
        root_execution_id=ROOT_ID,
        execution_id=ROOT_ID,
        request=_request("homepage"),
        retry_of=None,
        repo_root=repo,
        root=runtime.campaigns_root,
        **preflight,
    )
    (repo / "quwoquan_data/prompts/source.txt").write_text(
        "changed source",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "drifted frozen source")
    for carrier in ("image", "video"):
        campaign_submission.write_submission(
            root_execution_id=ROOT_ID,
            execution_id=_execution_id(carrier),
            request=_request(carrier),
            retry_of=None,
            repo_root=repo,
            root=runtime.campaigns_root,
            **preflight,
        )
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(tmp_path / "events.ndjson"))
    with pytest.raises(ValueError, match="must share one branch, commit"):
        campaign_controller.run_campaign(
            ROOT_ID,
            submission_timeout_seconds=1,
            lane_timeout_seconds=2,
            runtime_paths=runtime,
        )
    report = read_json(runtime.campaigns_root / ROOT_ID / "campaign_report.json")
    assert report["status"] == "blocked"
    assert report["phase"] == "freeze"


def test_cursor_auto_first_submission_and_retry_reach_lane_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    root_id = "20260728--travel-homepage-scale--china--scale-002"
    article_id = _execution_id("article", sequence="002")
    predecessor = _execution_id("article", sequence="001")
    monkeypatch.setattr(campaign_submission.paths, "REPO_ROOT", repo)
    preflight_path, preflight_binding = ready_semantic_preflight(
        "cursor_auto",
        output_root=runtime.output_root,
    )

    with pytest.raises(ValueError, match="SEMANTIC_PREFLIGHT_REQUIRED"):
        campaign_submission.write_submission(
            root_execution_id=root_id,
            execution_id=article_id,
            request=_request("article"),
            retry_of=predecessor,
            semantic_selection_id="default",
            repo_root=repo,
            root=runtime.campaigns_root,
        )
    first_path = campaign_submission.write_submission(
        root_execution_id=(
            "20260728--travel-homepage-scale--china--scale-001"
        ),
        execution_id=_execution_id("article", sequence="001"),
        request=_request("article"),
        retry_of=None,
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=runtime.output_root,
        repo_root=repo,
        root=runtime.campaigns_root,
    )
    assert read_json(first_path)["retryOf"] is None
    path = campaign_submission.write_submission(
        root_execution_id=root_id,
        execution_id=article_id,
        request=_request("article"),
        retry_of=predecessor,
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=runtime.output_root,
        repo_root=repo,
        root=runtime.campaigns_root,
    )
    submission = read_json(path)
    assert submission["semanticSelectionId"] == "cursor_auto"
    assert submission["semanticPreflightReceipt"] == preflight_binding
    argv = campaign_lane_execution._lane_argv(submission, stage="plan-only")
    selection_index = argv.index("--semantic-selection-id")
    assert argv[selection_index + 1] == "cursor_auto"
    receipt_index = argv.index("--semantic-preflight-receipt")
    assert argv[receipt_index + 1] == preflight_binding["receiptRef"]


def test_main_tree_drift_during_review_still_blocks_and_cleans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    event_log = tmp_path / "events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(event_log))
    monkeypatch.setenv("DRIFT_CARRIER", "video")
    monkeypatch.setenv("DRIFT_REPO", str(repo))
    with pytest.raises(ValueError):
        campaign_controller.run_campaign(
            ROOT_ID,
            submission_timeout_seconds=2,
            lane_timeout_seconds=5,
            runtime_paths=runtime,
        )
    report = read_json(runtime.campaigns_root / ROOT_ID / "campaign_report.json")
    assert report["status"] == "blocked"
    _assert_capsule_reused_and_lane_roots_isolated(runtime, report)


def test_timeout_and_publish_failure_are_lane_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeout_case = tmp_path / "timeout"
    timeout_case.mkdir()
    repo = _create_repo(timeout_case)
    runtime = _runtime(timeout_case, repo)
    monkeypatch.setattr(campaign_submission.paths, "REPO_ROOT", repo)
    preflight = _semantic_preflight_kwargs(runtime)
    campaign_submission.write_submission(
        root_execution_id=ROOT_ID,
        execution_id=ROOT_ID,
        request=_request("homepage"),
        retry_of=None,
        repo_root=repo,
        root=runtime.campaigns_root,
        **preflight,
    )
    with pytest.raises(TimeoutError):
        campaign_controller.run_campaign(
            ROOT_ID,
            submission_timeout_seconds=1,
            lane_timeout_seconds=2,
            runtime_paths=runtime,
        )
    timeout_report = read_json(
        runtime.campaigns_root / ROOT_ID / "campaign_report.json"
    )
    assert timeout_report["status"] == "blocked"
    assert timeout_report["phase"] == "submission"

    lane_timeout_case = tmp_path / "lane-timeout"
    lane_timeout_case.mkdir()
    repo = _create_repo(lane_timeout_case)
    runtime = _runtime(lane_timeout_case, repo)
    _submit_all(repo, runtime, monkeypatch)
    monkeypatch.setenv(
        "CAMPAIGN_EVENT_LOG",
        str(lane_timeout_case / "events.ndjson"),
    )
    # All lanes time out → no publishable content → blocked + raise.
    with pytest.raises(RuntimeError, match="no publishable"):
        campaign_controller.run_campaign(
            ROOT_ID,
            submission_timeout_seconds=2,
            lane_timeout_seconds=0.05,
            runtime_paths=runtime,
        )
    lane_timeout_report = read_json(
        runtime.campaigns_root / ROOT_ID / "campaign_report.json"
    )
    assert lane_timeout_report["status"] == "blocked"
    assert {
        lane["reviewReturnCode"] for lane in lane_timeout_report["lanes"].values()
    } == {124}
    _assert_capsule_reused_and_lane_roots_isolated(runtime, lane_timeout_report)

    failure_case = tmp_path / "failure"
    failure_case.mkdir()
    repo = _create_repo(failure_case)
    runtime = _runtime(failure_case, repo)
    _submit_all(repo, runtime, monkeypatch)
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(failure_case / "events.ndjson"))
    monkeypatch.setenv("FAIL_PUBLISH_CARRIER", "article")
    report_path = campaign_controller.run_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        lane_timeout_seconds=5,
        runtime_paths=runtime,
    )
    report = read_json(report_path)
    assert report["status"] == "succeeded_partial"
    assert report["lanes"]["article"]["publishReturnCode"] == 17
    assert report["lanes"]["article"]["status"] == "blocked"
    for carrier in ("homepage", "image", "video"):
        assert report["lanes"][carrier]["finalizedCount"] == 1
    _assert_capsule_reused_and_lane_roots_isolated(runtime, report)


def test_terminal_failed_lane_claim_can_retry_same_frozen_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(tmp_path / "events.ndjson"))
    monkeypatch.setenv("FAIL_PUBLISH_CARRIER", "article")

    campaign_distributed.freeze_campaign(
        ROOT_ID,
        submission_timeout_seconds=2,
        runtime_paths=runtime,
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            carrier: pool.submit(
                campaign_distributed.run_campaign_lane,
                ROOT_ID,
                carrier,
                lane_timeout_seconds=5,
                runtime_paths=runtime,
            )
            for carrier in CARRIERS
        }
        for carrier, future in futures.items():
            if carrier == "article":
                with pytest.raises(RuntimeError, match="run exited with code 17"):
                    future.result()
            else:
                future.result()
    first_report = read_json(
        campaign_distributed.finalize_campaign(
            ROOT_ID,
            runtime_paths=runtime,
        )
    )
    assert first_report["lanes"]["article"]["status"] == "blocked"
    failed_claim = read_lane_claim(runtime, ROOT_ID, "article")
    assert failed_claim is not None
    assert failed_claim["status"] == "failed"
    assert failed_claim["claimAttempt"] == 1

    monkeypatch.delenv("FAIL_PUBLISH_CARRIER")
    campaign_distributed.run_campaign_lane(
        ROOT_ID,
        "article",
        lane_timeout_seconds=5,
        runtime_paths=runtime,
    )
    recovered_claim = read_lane_claim(runtime, ROOT_ID, "article")
    assert recovered_claim is not None
    assert recovered_claim["status"] == "completed"
    assert recovered_claim["claimAttempt"] == 2
    assert recovered_claim["claimId"] != failed_claim["claimId"]

    recovered_report = read_json(
        campaign_distributed.finalize_campaign(
            ROOT_ID,
            runtime_paths=runtime,
        )
    )
    assert recovered_report["status"] == "succeeded"
    assert recovered_report["lanes"]["article"]["finalizedCount"] == 1
