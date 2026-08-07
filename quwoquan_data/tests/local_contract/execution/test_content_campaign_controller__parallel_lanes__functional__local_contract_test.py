# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import controller as campaign_controller
from content.execution.campaign import distributed as campaign_distributed
from content.execution.campaign import orchestrator as campaign_orchestrator
from content.execution.campaign import process as campaign_process
from content.execution.campaign import submission as campaign_submission
from content.execution.campaign.external_input_runtime import (
    execution_external_input_envelope_path,
    load_execution_external_input_envelope,
)
from content.execution.campaign.lane_claim import read_lane_claim
from content.execution.campaign.runtime import (
    CampaignFenceError,
    CampaignLeaseTakeoverError,
    assert_campaign_fence,
    campaign_run_session,
    read_lane_checkpoint,
    read_runtime_snapshot,
    runtime_events_path,
    runtime_snapshot_path,
)
from content.execution.campaign.runtime_process import (
    begin_stale_controller_termination,
)
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.queue.reliabletask.transport import (
    FrozenReliableTaskFleetBinding,
    ReliableTaskFleetTransport,
)
from content.execution.request import RuntimeExecutionRequest
from content.execution.runtime_evidence.reliabletask_process import (
    ReliableTaskObserverBinaryBinding,
)
from core.control_types import TargetSelector
from core.execution_branch import current_git_branch, stamp_execution_branch
from core.io import read_json, write_json
from support.semantic_preflight_fixture import ready_semantic_preflight

ROOT_ID = "20260728--travel-homepage-scale--china--scale-001"
CARRIERS = ("homepage", "article", "image", "video")


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
    assert campaign_process._execution_has_resumable_checkpoint(tmp_path) is True
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
    assert campaign_process._execution_has_resumable_checkpoint(tmp_path) is False

    write_json(
        state,
        {"status": "manual_required", "waitingCheckpoint": None},
    )
    assert campaign_process._execution_has_resumable_checkpoint(tmp_path) is False

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
    assert campaign_process._execution_has_resumable_checkpoint(tmp_path) is True


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
    monkeypatch.setattr(campaign_process.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(campaign_process.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        campaign_process,
        "_process_group_rss_bytes",
        lambda _pgid: 64 * 1024**2,
    )
    monkeypatch.setattr(
        campaign_process,
        "_execution_heartbeat_at",
        lambda _root: "2026-08-07T08:00:00+00:00",
    )

    code = campaign_process._default_lane_runner(
        ["python", "cli.py"],
        tmp_path,
        {},
        tmp_path / "lane.log",
        30,
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
        if checkpoint.get("return_code") == campaign_process._LANE_SLICE_YIELD_CODE
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
    monkeypatch.setattr(campaign_process.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(campaign_process.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        campaign_process,
        "_process_group_rss_bytes",
        lambda _pgid: 32 * 1024**2,
    )
    monkeypatch.setattr(
        campaign_process,
        "_execution_heartbeat_at",
        lambda _root: "2026-08-07T08:00:00+00:00",
    )

    log_path = tmp_path / "lane.log"
    code = campaign_process._default_lane_runner(
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
    owner, signal_name = campaign_process._termination_owner(-signal.SIGKILL)

    assert owner == "external_or_kernel"
    assert signal_name == "SIGKILL"


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
        campaign_process,
        "_verify_workspace_external_inputs",
        lambda _workspace: None,
    )
    code, error = campaign_process._run_lane(
        workspace,
        {
            "executionId": execution_id,
            "gitBranch": "dev1.0",
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


FAKE_CLI = r"""#!/usr/bin/env python3
import fcntl
import hashlib
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
external_input_envelope = (
    Path(os.environ["QWQ_OUTPUT_ROOT"])
    / "data/tasks"
    / execution_id
    / "0.plan/campaign_external_input_envelope.json"
)
if (
    os.environ.get("QWQ_CAMPAIGN_ROOT_EXECUTION_ID") != root_id
    or not os.environ.get("QWQ_FROZEN_MAIN_BRANCH")
    or os.environ.get("QWQ_RELIABLETASK_OBSERVER_BINARY_REF")
    != "data/local/cache/reliabletask-observer-binaries/"
    + "f" * 64
    + "/data-content-worker"
    or os.environ.get("QWQ_RELIABLETASK_OBSERVER_BINARY_SHA256")
    != "sha256:" + "e" * 64
    or os.environ.get("QWQ_RELIABLETASK_FLEET_TARGET")
    != "test-data-execution-fleet"
    or os.environ.get("QWQ_RELIABLETASK_FLEET_MONGO_URI")
    != "mongodb://127.0.0.1:27117/quwoquan"
    or os.environ.get("QWQ_RELIABLETASK_FLEET_REDIS_ADDR")
    != "127.0.0.1:6389"
    or not os.environ.get("QWQ_RELIABLETASK_FLEET_PLAN_DIGEST")
    or not os.environ.get("QWQ_RELIABLETASK_FLEET_BINDING_DIGEST")
    or not external_input_envelope.is_file()
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
delay = 0.25
if (
    phase == "review"
    and os.environ.get("SLOW_REVIEW_CARRIER") == carrier
):
    delay = 1.0
time.sleep(delay)
if (
    phase == "review"
    and os.environ.get("DRIFT_CARRIER") == carrier
):
    (Path(os.environ["DRIFT_REPO"]) / "quwoquan_data/prompts/source.txt").write_text(
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

publish_binding = {}
if phase == "publish":
    output_root = Path(os.environ["QWQ_OUTPUT_ROOT"])
    execution_root_path = output_root / "data/tasks" / execution_id
    publish_path = execution_root_path / "publish_ref.json"
    if carrier == "homepage":
        published_refs = {
            "entities": [
                f"地点/景区/{carrier}-fixture-{index:03d}"
                for index in range(finalized)
            ],
            "posts": [],
        }
    else:
        published_refs = {
            "entities": [],
            "posts": [
                f"{carrier}/测试/{carrier}-fixture-{index:03d}/001"
                for index in range(finalized)
            ],
        }
    publish_document = {
        "schema": "quwoquan_data.execution_publish_ref",
        "executionId": execution_id,
        "canonicalPublishRoot": "quwoquan_data/publish",
        "publishedRefs": published_refs,
    }
    publish_bytes = (
        json.dumps(publish_document, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    publish_path.write_bytes(publish_bytes)
    deadline = time.monotonic() + 1.0
    plan = json.loads((campaign / "campaign_plan.json").read_text(encoding="utf-8"))
    while True:
        if plan.get("executionMode") == "distributed":
            claim = json.loads(
                (campaign / "claims" / f"{carrier}.json").read_text(
                    encoding="utf-8"
                )
            )
            runtime_identity = (
                claim["campaignRunId"],
                int(claim["campaignGeneration"]),
                claim["campaignFencingToken"],
            )
            ready = (
                claim.get("planDigest") == plan.get("planDigest")
                and claim.get("executionId") == execution_id
                and claim.get("phase") == "run"
                and claim.get("status") == "running"
            )
        else:
            snapshot = json.loads(
                (campaign / "runtime/snapshot.json").read_text(encoding="utf-8")
            )
            checkpoint = json.loads(
                (campaign / "runtime/lanes" / f"{carrier}.json").read_text(
                    encoding="utf-8"
                )
            )
            runtime_identity = (
                snapshot["runId"],
                int(snapshot["generation"]),
                snapshot["fencingToken"],
            )
            ready = (
                snapshot.get("status") == "active"
                and snapshot.get("phase") in {"review", "publish"}
                and checkpoint.get("executionId") == execution_id
                and checkpoint.get("phase") == "run"
                and checkpoint.get("status") == "running"
                and (
                    checkpoint.get("runId"),
                    int(checkpoint.get("generation") or 0),
                    checkpoint.get("fencingToken"),
                )
                == runtime_identity
            )
        if ready:
            break
        if time.monotonic() >= deadline:
            raise SystemExit(33)
        time.sleep(0.05)
    publish_binding = {
        "executionPublishRef": publish_path.relative_to(output_root).as_posix(),
        "executionPublishSha256": (
            "sha256:" + hashlib.sha256(publish_bytes).hexdigest()
        ),
        "campaignRunId": runtime_identity[0],
        "campaignGeneration": runtime_identity[1],
        "campaignFencingToken": runtime_identity[2],
    }

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
    **publish_binding,
}
(receipts / f"{carrier}-{phase}.json").write_text(
    json.dumps(payload),
    encoding="utf-8",
)
event("end")
"""


@pytest.fixture(autouse=True)
def _restore_capsule_permissions_for_pytest_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Production capsules stay read-only; pytest still has to remove its tmp tree."""
    binding = ReliableTaskObserverBinaryBinding(
        ref=(
            "data/local/cache/reliabletask-observer-binaries/"
            + "f" * 64
            + "/data-content-worker"
        ),
        sha256="sha256:" + "e" * 64,
    )
    monkeypatch.setattr(
        campaign_orchestrator,
        "resolve_campaign_observer_binary",
        lambda runtime, root_execution_id, plan_digest: binding,
    )
    monkeypatch.setattr(
        campaign_distributed,
        "resolve_campaign_observer_binary",
        lambda runtime, root_execution_id, plan_digest: binding,
    )
    fleet_transport = ReliableTaskFleetTransport(
        target="test-data-execution-fleet",
        mongo_uri="mongodb://127.0.0.1:27117/quwoquan",
        redis_addr="127.0.0.1:6389",
    )
    monkeypatch.setattr(
        campaign_orchestrator,
        "resolve_campaign_fleet_transport",
        lambda runtime, root_execution_id, plan_digest: (
            FrozenReliableTaskFleetBinding.create(
                root_execution_id=root_execution_id,
                plan_digest=plan_digest,
                transport=fleet_transport,
            )
        ),
    )
    monkeypatch.setattr(
        campaign_distributed,
        "resolve_campaign_fleet_transport",
        lambda runtime, root_execution_id, plan_digest: (
            FrozenReliableTaskFleetBinding.create(
                root_execution_id=root_execution_id,
                plan_digest=plan_digest,
                transport=fleet_transport,
            )
        ),
    )
    monkeypatch.setenv(
        "QWQ_RELIABLETASK_OBSERVER_BINARY_REF",
        "data/local/cache/reliabletask-observer-binaries/"
        + "a" * 64
        + "/data-content-worker",
    )
    monkeypatch.setenv(
        "QWQ_RELIABLETASK_OBSERVER_BINARY_SHA256",
        "sha256:" + "b" * 64,
    )
    yield
    for manifest in tmp_path.rglob(".qwq_campaign_capsule.json"):
        capsule = manifest.parent
        for path in sorted(capsule.rglob("*"), reverse=True):
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | 0o700)
        capsule.chmod(capsule.stat().st_mode | 0o700)


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
    (repo / "quwoquan_data/requirements-cursor.txt").write_text(
        "-r requirements.txt\ncursor-sdk==1.0.26\n",
        encoding="utf-8",
    )
    branch_policy = repo / "quwoquan_ops/policies/branch_policy.yaml"
    branch_policy.parent.mkdir(parents=True)
    branch_policy.write_text(
        "allowed_local_branches:\n  - dev1.0\n",
        encoding="utf-8",
    )
    feature_root = (
        repo
        / "specs/feature-tree/discovery-content/object-homepage-coverage-scaling"
    )
    feature_root.mkdir(parents=True)
    (feature_root / "spec.md").write_text(
        "# Object homepage coverage scaling\n",
        encoding="utf-8",
    )
    (feature_root / "design.md").write_text(
        "# Object homepage coverage scaling design\n",
        encoding="utf-8",
    )
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
        campaigns_root=(output / "data/local/workspace/content-campaign-submissions"),
        workspaces_root=(output / "data/local/cache/content-campaign-workspaces"),
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


def _semantic_preflight_kwargs(
    runtime: CampaignRuntimePaths,
    selection: str = "default",
) -> dict[str, Path]:
    path, _binding = ready_semantic_preflight(
        selection,
        output_root=runtime.output_root,
    )
    return {
        "semantic_preflight_receipt": path,
        "semantic_preflight_output_root": runtime.output_root,
    }


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
    semantic_preflight = _semantic_preflight_kwargs(runtime)
    for carrier in CARRIERS:
        campaign_submission.write_submission(
            root_execution_id=root_id,
            execution_id=(root_id if carrier == "homepage" else _execution_id(carrier)),
            request=_request(carrier, count=count, quota=quota),
            retry_of=None,
            repo_root=repo,
            root=runtime.campaigns_root,
            **semantic_preflight,
        )


def _events(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _assert_capsule_reused_and_lane_roots_isolated(
    runtime: CampaignRuntimePaths,
    report: dict[str, object],
) -> None:
    lanes = report["lanes"]
    assert isinstance(lanes, dict)
    capsule_refs = {
        str(lanes[carrier]["sourceCapsuleRef"]) for carrier in CARRIERS
    }
    assert len(capsule_refs) == 1
    capsule = runtime.output_root / next(iter(capsule_refs))
    assert capsule.is_dir()
    assert (capsule / ".qwq_campaign_capsule.json").is_file()
    assert not (capsule / ".qwq_output").exists()
    assert (capsule / "quwoquan_data/requirements-cursor.txt").is_file()
    assert (
        capsule / "quwoquan_ops/policies/branch_policy.yaml"
    ).is_file()
    feature_root = (
        capsule
        / "specs/feature-tree/discovery-content/object-homepage-coverage-scaling"
    )
    assert (feature_root / "spec.md").is_file()
    assert (feature_root / "design.md").is_file()
    capsule_manifest = read_json(capsule / ".qwq_campaign_capsule.json")
    assert capsule_manifest["sourceRevision"].startswith("sha256:")
    assert set(capsule_manifest["laneExternalInputs"]) == set(CARRIERS)
    assert capsule.stat().st_mode & 0o222 == 0
    execution_roots: set[str] = set()
    for carrier in CARRIERS:
        lane = lanes[carrier]
        assert lane["sourceCapsuleReadOnly"] is True
        assert lane["sourceCapsuleDigest"] == capsule_manifest["capsuleDigest"]
        assert lane["executionRootRef"] == (
            f"data/tasks/{lane['executionId']}"
        )
        assert lane["cleanupStatus"] == "cleaned"
        checkpoint = read_lane_checkpoint(runtime, ROOT_ID, carrier)
        assert checkpoint is not None
        assert checkpoint["capsuleRef"] == next(iter(capsule_refs))
        assert int(checkpoint["pid"] or 0) == int(checkpoint["pgid"] or 0)
        execution_root = Path(str(checkpoint["executionRoot"]))
        assert execution_root.is_dir()
        assert execution_root.parent == runtime.output_root / "data/tasks"
        envelope = load_execution_external_input_envelope(
            execution_external_input_envelope_path(execution_root)
        )
        assert envelope["carrier"] == carrier
        assert envelope["externalInputRefs"] == []
        assert envelope["capsuleDigest"] == capsule_manifest["capsuleDigest"]
        execution_roots.add(str(execution_root))
    assert len(execution_roots) == 4


def test_default_runtime_paths_use_governed_workspace_and_cache() -> None:
    runtime = CampaignRuntimePaths.defaults()
    governed_workspace = (
        runtime.output_root / "data" / "local" / "workspace"
    ).resolve()
    governed_cache = (runtime.output_root / "data" / "local" / "cache").resolve()

    assert runtime.campaigns_root.parent == governed_workspace
    assert runtime.workspaces_root.parent == governed_cache
    assert runtime.acquisition_root.parent == governed_workspace


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
    assert (runtime.campaigns_root / ROOT_ID / "copy_ready_receipt.json").is_file()


def test_killed_controller_is_reconciled_and_old_generation_is_fenced(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    ready_path = tmp_path / "controller-ready.json"
    orphan_cli = tmp_path / "orphan/quwoquan_data/scripts/cli.py"
    orphan_cli.parent.mkdir(parents=True)
    orphan_cli.write_text(
        "import time\ntime.sleep(120)\n",
        encoding="utf-8",
    )
    lane_execution = _execution_id("article")
    scripts_root = Path(__file__).resolve().parents[3] / "scripts"
    child_code = f"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from content.execution.campaign.runtime import campaign_run_session
from content.execution.campaign.workspace import CampaignRuntimePaths

runtime = CampaignRuntimePaths(
    repo_root=Path({json.dumps(str(runtime.repo_root))}),
    output_root=Path({json.dumps(str(runtime.output_root))}),
    publish_root=Path({json.dumps(str(runtime.publish_root))}),
    campaigns_root=Path({json.dumps(str(runtime.campaigns_root))}),
    workspaces_root=Path({json.dumps(str(runtime.workspaces_root))}),
)
with campaign_run_session(runtime, {json.dumps(ROOT_ID)}, lease_seconds=60) as session:
    lane_root = Path({json.dumps(str(tmp_path / "orphan-lane-root"))})
    lane_root.mkdir(parents=True, exist_ok=True)
    lane = subprocess.Popen(
        [sys.executable, {json.dumps(str(orphan_cli))}, "--execution-id", {json.dumps(lane_execution)}],
        start_new_session=True,
    )
    session.lane_checkpoint(
        carrier="article",
        execution_id={json.dumps(lane_execution)},
        phase="review-only",
        status="running",
        capsule_ref="test-capsule",
        execution_root=lane_root,
        pid=lane.pid,
        pgid=os.getpgid(lane.pid),
    )
    Path({json.dumps(str(ready_path))}).write_text(json.dumps({{
        "runId": session.run_id,
        "generation": session.generation,
        "fencingToken": session.fencing_token,
        "lanePid": lane.pid,
    }}), encoding="utf-8")
    while True:
        time.sleep(1)
"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(scripts_root)
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", child_code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not ready_path.is_file() and time.monotonic() < deadline:
        if child.poll() is not None:
            stdout, stderr = child.communicate()
            raise AssertionError(
                f"controller child exited early rc={child.returncode}: {stdout} {stderr}"
            )
        time.sleep(0.05)
    assert ready_path.is_file()
    first = json.loads(ready_path.read_text(encoding="utf-8"))
    os.kill(child.pid, signal.SIGKILL)
    child.wait(timeout=5)
    killed_snapshot = read_runtime_snapshot(runtime, ROOT_ID)
    assert killed_snapshot is not None
    assert killed_snapshot["status"] == "active"

    with campaign_run_session(runtime, ROOT_ID, lease_seconds=60) as restarted:
        assert restarted.generation == int(first["generation"]) + 1
        assert restarted.run_id != first["runId"]
        with pytest.raises(CampaignFenceError, match="DATA.CAMPAIGN.FENCED"):
            assert_campaign_fence(
                runtime,
                ROOT_ID,
                run_id=str(first["runId"]),
                generation=int(first["generation"]),
                fencing_token=str(first["fencingToken"]),
            )
        restarted.finish(status="blocked", phase="test", failure=None)

    reconciled = read_runtime_snapshot(runtime, ROOT_ID)
    assert reconciled is not None
    assert reconciled["generation"] == 2
    assert reconciled["status"] == "blocked"
    reconciled_lane = read_lane_checkpoint(runtime, ROOT_ID, "article")
    assert reconciled_lane is not None
    assert reconciled_lane["status"] == "interrupted"
    assert reconciled_lane["termination"] in {"terminated", "killed"}
    lane_pid = int(first["lanePid"])
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        observed = subprocess.run(
            ["ps", "-p", str(lane_pid), "-o", "stat="],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not observed or observed.startswith("Z"):
            break
        time.sleep(0.05)
    assert not observed or observed.startswith("Z")
    event_types = {
        row["eventType"] for row in _events(runtime_events_path(runtime, ROOT_ID))
    }
    assert "stale_generation_reconciled" in event_types


def _spawn_live_stall_controller(
    tmp_path: Path,
    runtime: CampaignRuntimePaths,
    *,
    label: str,
    stall: bool = True,
) -> tuple[subprocess.Popen[str], dict[str, object]]:
    ready_path = tmp_path / f"{label}-controller-ready.json"
    controller_cli = tmp_path / label / "quwoquan_data/scripts/cli.py"
    controller_cli.parent.mkdir(parents=True)
    controller_cli.write_text(
        f"""
import json
import time
from pathlib import Path
from content.execution.campaign.runtime import campaign_run_session
from content.execution.campaign.workspace import CampaignRuntimePaths

runtime = CampaignRuntimePaths(
    repo_root=Path({json.dumps(str(runtime.repo_root))}),
    output_root=Path({json.dumps(str(runtime.output_root))}),
    publish_root=Path({json.dumps(str(runtime.publish_root))}),
    campaigns_root=Path({json.dumps(str(runtime.campaigns_root))}),
    workspaces_root=Path({json.dumps(str(runtime.workspaces_root))}),
)
with campaign_run_session(runtime, {json.dumps(ROOT_ID)}, lease_seconds=1) as session:
    Path({json.dumps(str(ready_path))}).write_text(json.dumps({{
        "runId": session.run_id,
        "generation": session.generation,
        "fencingToken": session.fencing_token,
    }}), encoding="utf-8")
    while True:
        time.sleep(1)
""",
        encoding="utf-8",
    )
    scripts_root = Path(__file__).resolve().parents[3] / "scripts"
    child = subprocess.Popen(
        [
            sys.executable,
            "-B",
            str(controller_cli),
            "campaign",
            "run",
            "--root-execution-id",
            ROOT_ID,
        ],
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(scripts_root),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not ready_path.is_file() and time.monotonic() < deadline:
        if child.poll() is not None:
            stdout, stderr = child.communicate()
            raise AssertionError(
                f"live-stall controller exited early rc={child.returncode}: "
                f"{stdout} {stderr}"
            )
        time.sleep(0.05)
    assert ready_path.is_file()
    initial = json.loads(ready_path.read_text(encoding="utf-8"))
    if stall:
        os.kill(child.pid, signal.SIGSTOP)
        time.sleep(1.25)
    return child, initial


def _force_stop_controller(child: subprocess.Popen[str]) -> None:
    if child.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(child.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait(timeout=5)


def test_fresh_live_controller_lease_blocks_takeover_without_signalling(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    child, _first = _spawn_live_stall_controller(
        tmp_path,
        runtime,
        label="fresh-controller",
        stall=False,
    )
    try:
        with (
            pytest.raises(
                CampaignLeaseTakeoverError,
                match="DATA.CAMPAIGN.LEASE_ACTIVE",
            ),
            campaign_run_session(
                runtime,
                ROOT_ID,
                lease_seconds=1,
                process_termination_timeout_seconds=0.2,
            ),
        ):
            raise AssertionError("fresh controller lease must remain authoritative")
        assert child.poll() is None
    finally:
        _force_stop_controller(child)


def test_expired_live_controller_is_identity_checked_terminated_and_fenced(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    child, first = _spawn_live_stall_controller(
        tmp_path,
        runtime,
        label="live-stall",
    )
    try:
        stalled = read_runtime_snapshot(runtime, ROOT_ID)
        assert stalled is not None
        assert stalled["pid"] == child.pid
        assert stalled["pgid"] == child.pid
        assert stalled["controllerProcessIdentity"].startswith("sha256:")

        with campaign_run_session(
            runtime,
            ROOT_ID,
            lease_seconds=1,
            process_termination_timeout_seconds=0.2,
        ) as restarted:
            assert restarted.generation == int(first["generation"]) + 1
            with pytest.raises(CampaignFenceError, match="DATA.CAMPAIGN.FENCED"):
                assert_campaign_fence(
                    runtime,
                    ROOT_ID,
                    run_id=str(first["runId"]),
                    generation=int(first["generation"]),
                    fencing_token=str(first["fencingToken"]),
                )
            restarted.finish(status="blocked", phase="test", failure=None)

        child.wait(timeout=5)
        assert child.returncode == -signal.SIGKILL
        takeover_events = [
            row
            for row in _events(runtime_events_path(runtime, ROOT_ID))
            if row["eventType"] == "stale_controller_takeover"
        ]
        assert len(takeover_events) == 1
        assert takeover_events[0]["controllerTermination"] == "killed"
    finally:
        _force_stop_controller(child)


def test_live_controller_identity_drift_blocks_takeover_without_signalling(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    child, _first = _spawn_live_stall_controller(
        tmp_path,
        runtime,
        label="live-stall-identity-drift",
    )
    try:
        snapshot_path = runtime_snapshot_path(runtime, ROOT_ID)
        snapshot = read_json(snapshot_path)
        snapshot["controllerProcessIdentity"] = "sha256:" + ("0" * 64)
        write_json(snapshot_path, snapshot)

        with (
            pytest.raises(
                CampaignLeaseTakeoverError,
                match="DATA.CAMPAIGN.TAKEOVER_IDENTITY_MISMATCH",
            ),
            campaign_run_session(
                runtime,
                ROOT_ID,
                lease_seconds=1,
                process_termination_timeout_seconds=0.2,
            ),
        ):
            raise AssertionError("identity-drifted controller must not be replaced")
        assert child.poll() is None
    finally:
        _force_stop_controller(child)


@pytest.mark.parametrize(
    ("pid", "pgid"),
    ((1, 1), (os.getpid(), os.getpgrp()), (os.getpid(), os.getpgrp() + 1)),
)
def test_controller_takeover_never_signals_unsafe_process_groups(
    monkeypatch: pytest.MonkeyPatch,
    pid: int,
    pgid: int,
) -> None:
    signalled: list[int] = []
    monkeypatch.setattr(os, "killpg", lambda group, _signal: signalled.append(group))
    snapshot = {
        "rootExecutionId": ROOT_ID,
        "runId": "unsafe-controller",
        "generation": 1,
        "fencingToken": "sha256:" + ("1" * 64),
        "controllerProcessIdentity": "sha256:" + ("2" * 64),
        "hostname": subprocess.check_output(["hostname"], text=True).strip(),
        "pid": pid,
        "pgid": pgid,
    }

    with pytest.raises(
        CampaignLeaseTakeoverError,
        match="DATA.CAMPAIGN.TAKEOVER_PROCESS_GROUP_UNSAFE",
    ):
        begin_stale_controller_termination(snapshot, root_execution_id=ROOT_ID)
    assert signalled == []


def test_sigterm_unwinds_controller_and_stops_owned_lane_process_group(
    tmp_path: Path,
) -> None:
    repo = _create_repo(tmp_path)
    runtime = _runtime(tmp_path, repo)
    ready_path = tmp_path / "sigterm-controller-ready.json"
    lane_cli = tmp_path / "sigterm/quwoquan_data/scripts/cli.py"
    lane_cli.parent.mkdir(parents=True)
    lane_cli.write_text("import time\ntime.sleep(120)\n", encoding="utf-8")
    lane_execution = _execution_id("video")
    scripts_root = Path(__file__).resolve().parents[3] / "scripts"
    child_code = f"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from content.execution.campaign.runtime import campaign_run_session
from content.execution.campaign.workspace import CampaignRuntimePaths

runtime = CampaignRuntimePaths(
    repo_root=Path({json.dumps(str(runtime.repo_root))}),
    output_root=Path({json.dumps(str(runtime.output_root))}),
    publish_root=Path({json.dumps(str(runtime.publish_root))}),
    campaigns_root=Path({json.dumps(str(runtime.campaigns_root))}),
    workspaces_root=Path({json.dumps(str(runtime.workspaces_root))}),
)
with campaign_run_session(runtime, {json.dumps(ROOT_ID)}, lease_seconds=60) as session:
    lane_root = Path({json.dumps(str(tmp_path / "sigterm-lane-root"))})
    lane_root.mkdir(parents=True, exist_ok=True)
    lane = subprocess.Popen(
        [sys.executable, {json.dumps(str(lane_cli))}, "--execution-id", {json.dumps(lane_execution)}],
        start_new_session=True,
    )
    session.lane_checkpoint(
        carrier="video",
        execution_id={json.dumps(lane_execution)},
        phase="review-only",
        status="running",
        capsule_ref="test-capsule",
        execution_root=lane_root,
        pid=lane.pid,
        pgid=os.getpgid(lane.pid),
    )
    Path({json.dumps(str(ready_path))}).write_text(
        json.dumps({{"lanePid": lane.pid}}), encoding="utf-8"
    )
    while True:
        time.sleep(1)
"""
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(scripts_root),
    }
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", child_code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + 10
    while not ready_path.is_file() and time.monotonic() < deadline:
        if child.poll() is not None:
            stdout, stderr = child.communicate()
            raise AssertionError(
                f"controller child exited early rc={child.returncode}: "
                f"{stdout} {stderr}"
            )
        time.sleep(0.05)
    assert ready_path.is_file()
    lane_pid = int(json.loads(ready_path.read_text(encoding="utf-8"))["lanePid"])

    os.kill(child.pid, signal.SIGTERM)
    child.wait(timeout=10)
    assert child.returncode != 0
    snapshot = read_runtime_snapshot(runtime, ROOT_ID)
    assert snapshot is not None
    assert snapshot["status"] == "interrupted"
    assert "CampaignControllerTerminated" in str(snapshot["failure"])
    checkpoint = read_lane_checkpoint(runtime, ROOT_ID, "video")
    assert checkpoint is not None
    assert checkpoint["status"] == "interrupted"
    assert checkpoint["termination"] in {"terminated", "killed"}
    observed = subprocess.run(
        ["ps", "-p", str(lane_pid), "-o", "stat="],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert not observed or observed.startswith("Z")


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
    argv = campaign_process._lane_argv(submission, stage="plan-only")
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
