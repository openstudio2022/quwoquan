# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.control_types import TargetSelector
from core.execution_branch import current_git_branch, stamp_execution_branch
from core.io import read_json
from content.execution import campaign_controller, campaign_submission
from content.execution.campaign_workspace import CampaignRuntimePaths
from content.execution.request import RuntimeExecutionRequest


ROOT_ID = "20260728--travel-homepage-scale--china--scale-001"
CARRIERS = ("homepage", "article", "image", "video")
FAKE_CLI = r'''#!/usr/bin/env python3
import fcntl
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
def value(flag):
    return args[args.index(flag) + 1]

execution_id = value("--execution-id")
root_id = value("--campaign-root-execution-id")
stage = value("--stage")
quota = int(value("--quota"))
count = int(value("--count"))
carrier = next(item for item in ("homepage", "article", "image", "video") if f"-{item}-" in execution_id)
phase = "review" if stage == "review-only" else "publish"
event_path = Path(os.environ["CAMPAIGN_EVENT_LOG"])
if (
    os.environ.get("QWQ_CAMPAIGN_ROOT_EXECUTION_ID") != root_id
    or not os.environ.get("QWQ_FROZEN_MAIN_BRANCH")
):
    raise SystemExit(32)

def event(kind):
    event_path.parent.mkdir(parents=True, exist_ok=True)
    with event_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps({
            "carrier": carrier,
            "phase": phase,
            "kind": kind,
            "at": time.monotonic(),
            "pid": os.getpid(),
        }) + "\n")
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

campaign = (
    Path(os.environ["QWQ_OUTPUT_ROOT"])
    / "data/local/workspace/content-campaign-submissions"
    / root_id
)
receipts = campaign / "receipts"
receipts.mkdir(parents=True, exist_ok=True)

# Own-lane publish gate only — never wait for sibling review receipts.
if phase == "publish":
    own_review = receipts / f"{carrier}-review.json"
    if not own_review.is_file():
        raise SystemExit(31)

event("start")
time.sleep(0.25)
if (
    phase == "review"
    and os.environ.get("DRIFT_CARRIER") == carrier
):
    (Path(os.environ["DRIFT_REPO"]) / "campaign-drift.txt").write_text(
        "drift",
        encoding="utf-8",
    )
if (
    phase == "review"
    and os.environ.get("FAIL_REVIEW_CARRIER") == carrier
):
    event("end")
    raise SystemExit(19)
if (
    phase == "publish"
    and os.environ.get("FAIL_PUBLISH_CARRIER") == carrier
):
    event("end")
    raise SystemExit(17)

qualified = quota
discards = []
if (
    phase == "review"
    and os.environ.get("SHORT_REVIEW_CARRIER") == carrier
):
    qualified = max(0, quota - 1)
    if qualified < quota:
        discards = [{
            "objectRef": f"{carrier}-discard-1",
            "issues": ["synthetic quality discard for shortfall proof"],
        }]
if (
    phase == "review"
    and os.environ.get("ZERO_REVIEW_CARRIER") == carrier
):
    qualified = 0
    discards = [{
        "objectRef": f"{carrier}-discard-all",
        "issues": ["synthetic zero-qualified discard"],
    }]

if phase == "review":
    status = (
        "qualified" if qualified >= quota else ("partial" if qualified > 0 else "blocked")
    )
    finalized = 0
else:
    review = json.loads((receipts / f"{carrier}-review.json").read_text(encoding="utf-8"))
    qualified = int(review["qualifiedCount"])
    discards = list(review["discards"])
    status = "finalized" if qualified >= quota else "partial"
    finalized = qualified

selected = qualified + len(discards)
payload = {
    "schema": "quwoquan_data.content_campaign_lane_receipt",
    "rootExecutionId": root_id,
    "executionId": execution_id,
    "carrier": carrier,
    "phase": phase,
    "status": status,
    "approvedQuota": quota,
    "qualifiedCount": qualified,
    "finalizedCount": finalized,
    "selectedCount": selected,
    "discardedCount": len(discards),
    "shortfallCount": max(0, quota - qualified),
    "discards": discards,
}
(receipts / f"{carrier}-{phase}.json").write_text(
    json.dumps(payload),
    encoding="utf-8",
)
event("end")
'''


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _create_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    inputs = (
        "quwoquan_data/schema",
        "quwoquan_data/control_plane",
        "quwoquan_data/prompts",
        "quwoquan_data/templates",
        "quwoquan_data/verticals/travel",
        "quwoquan_data/reference",
        "quwoquan_service/services/content-service/contracts/media/media_asset",
    )
    for relative in inputs:
        directory = repo / relative
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "source.txt").write_text(relative, encoding="utf-8")
    scripts = repo / "quwoquan_data/scripts"
    scripts.mkdir(parents=True)
    (scripts / "cli.py").write_text(FAKE_CLI, encoding="utf-8")
    (repo / "quwoquan_data/requirements.txt").write_text("", encoding="utf-8")
    catalog = repo / "quwoquan_data/reference/travel/entities/china"
    catalog.mkdir(parents=True)
    (catalog / "catalog.yaml").write_text("entities: [测试实体]\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.email", "campaign@example.invalid")
    _git(repo, "config", "user.name", "Campaign Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "frozen campaign")
    return repo


def _runtime(tmp_path: Path, repo: Path) -> CampaignRuntimePaths:
    output = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=repo,
        output_root=output,
        publish_root=tmp_path / "publish",
        campaigns_root=(
            output / "data/local/workspace/content-campaign-submissions"
        ),
        workspaces_root=(
            output / "data/local/cache/content-campaign-workspaces"
        ),
    )


def _request(
    carrier: str,
    *,
    count: int = 1,
    quota: int = 1,
) -> RuntimeExecutionRequest:
    return RuntimeExecutionRequest(
        family_ref=f"content/travel/{carrier}/{carrier}",
        region_ref="china",
        selector=(
            TargetSelector.SOURCE_READY_PRIORITY
            if carrier == "homepage"
            else TargetSelector.ALL
        ),
        count=count,
        quota=quota,
        topic=None,
        source_providers=(),
        target_names=(),
    )


def _execution_id(carrier: str, *, sequence: str = "001") -> str:
    if carrier == "homepage" and sequence == "001":
        return ROOT_ID
    return f"20260728--travel-{carrier}-scale--china--scale-{sequence}"


def _submit_all(
    repo: Path,
    runtime: CampaignRuntimePaths,
    monkeypatch: pytest.MonkeyPatch,
    *,
    root_id: str = ROOT_ID,
    count: int = 1,
    quota: int = 1,
) -> None:
    monkeypatch.setattr(campaign_submission.paths, "REPO_ROOT", repo)
    for carrier in CARRIERS:
        campaign_submission.write_submission(
            root_execution_id=root_id,
            execution_id=(
                root_id if carrier == "homepage" else _execution_id(carrier)
            ),
            request=_request(carrier, count=count, quota=quota),
            retry_of=None,
            repo_root=repo,
            root=runtime.campaigns_root,
        )


def _events(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _assert_clones_cleaned(
    runtime: CampaignRuntimePaths,
    report: dict[str, object],
) -> None:
    lanes = report["lanes"]
    assert isinstance(lanes, dict)
    for carrier in CARRIERS:
        lane = lanes[carrier]
        assert lane["cloneDetached"] is True
        assert lane["cleanupStatus"] == "cleaned"
        assert not (
            runtime.output_root / str(lane["cloneRef"])
        ).exists()


def test_default_runtime_paths_use_governed_workspace_and_cache() -> None:
    runtime = CampaignRuntimePaths.defaults()
    governed_workspace = (
        runtime.output_root / "data" / "local" / "workspace"
    ).resolve()
    governed_cache = (
        runtime.output_root / "data" / "local" / "cache"
    ).resolve()

    assert runtime.campaigns_root.parent == governed_workspace
    assert runtime.workspaces_root.parent == governed_cache


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
    assert current_git_branch(cwd=repo) == branch
    spec = {"executionPolicy": {}}
    stamp_execution_branch(spec, cwd=repo)
    assert spec["executionPolicy"] == {
        "executionBranch": branch,
        "gitCommitSha": _git(repo, "rev-parse", "HEAD"),
    }


def test_real_subprocess_lanes_overlap_and_publish_only_after_own_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    _submit_all(repo, runtime, monkeypatch)
    event_log = tmp_path / "events.ndjson"
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(event_log))

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
    assert report["gitBranch"] == _git(repo, "branch", "--show-current")
    review_events = [
        row for row in _events(event_log) if row["phase"] == "review"
    ]
    publish_events = [
        row for row in _events(event_log) if row["phase"] == "publish"
    ]
    review_starts = {
        row["carrier"]: row["at"]
        for row in review_events
        if row["kind"] == "start"
    }
    review_ends = {
        row["carrier"]: row["at"]
        for row in review_events
        if row["kind"] == "end"
    }
    assert set(review_starts) == set(CARRIERS)
    assert max(review_starts.values()) < min(review_ends.values())
    # Own-lane ordering only: each publish starts after that carrier's review end.
    publish_starts = {
        row["carrier"]: row["at"]
        for row in publish_events
        if row["kind"] == "start"
    }
    assert set(publish_starts) == set(CARRIERS)
    for carrier in CARRIERS:
        assert publish_starts[carrier] >= review_ends[carrier]
    assert len({row["pid"] for row in review_events}) == 4
    for lane in report["lanes"].values():
        assert lane["reviewReturnCode"] == 0
        assert lane["publishReturnCode"] == 0
        assert lane["qualifiedCount"] == 1
        assert lane["finalizedCount"] == 1
    _assert_clones_cleaned(runtime, report)


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
    _assert_clones_cleaned(runtime, report)


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
    _assert_clones_cleaned(runtime, report)


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
        row["carrier"]
        for row in _events(event_log)
        if row["phase"] == "publish"
    }
    assert "video" not in publish_carriers
    for carrier in ("homepage", "article", "image"):
        assert report["lanes"][carrier]["finalizedCount"] == 1
    _assert_clones_cleaned(runtime, report)


def test_submission_collision_and_cross_lane_mismatch_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    monkeypatch.setattr(campaign_submission.paths, "REPO_ROOT", repo)
    article_id = _execution_id("article")
    campaign_submission.write_submission(
        root_execution_id=ROOT_ID,
        execution_id=article_id,
        request=_request("article"),
        retry_of=None,
        repo_root=repo,
        root=runtime.campaigns_root,
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
        )

    campaign_submission.write_submission(
        root_execution_id=ROOT_ID,
        execution_id=ROOT_ID,
        request=_request("homepage"),
        retry_of=None,
        repo_root=repo,
        root=runtime.campaigns_root,
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
        )
    monkeypatch.setenv("CAMPAIGN_EVENT_LOG", str(tmp_path / "events.ndjson"))
    with pytest.raises(ValueError, match="must share one branch, commit"):
        campaign_controller.run_campaign(
            ROOT_ID,
            submission_timeout_seconds=1,
            lane_timeout_seconds=2,
            runtime_paths=runtime,
        )
    report = read_json(
        runtime.campaigns_root / ROOT_ID / "campaign_report.json"
    )
    assert report["status"] == "blocked"
    assert report["phase"] == "freeze"


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
    report = read_json(
        runtime.campaigns_root / ROOT_ID / "campaign_report.json"
    )
    assert report["status"] == "blocked"
    _assert_clones_cleaned(runtime, report)


def test_timeout_and_publish_failure_are_lane_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeout_case = tmp_path / "timeout"
    timeout_case.mkdir()
    repo = _create_repo(timeout_case)
    runtime = _runtime(timeout_case, repo)
    monkeypatch.setattr(campaign_submission.paths, "REPO_ROOT", repo)
    campaign_submission.write_submission(
        root_execution_id=ROOT_ID,
        execution_id=ROOT_ID,
        request=_request("homepage"),
        retry_of=None,
        repo_root=repo,
        root=runtime.campaigns_root,
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
        lane["reviewReturnCode"]
        for lane in lane_timeout_report["lanes"].values()
    } == {124}
    _assert_clones_cleaned(runtime, lane_timeout_report)

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
    _assert_clones_cleaned(runtime, report)
