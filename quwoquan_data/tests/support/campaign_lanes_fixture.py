# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""content campaign controller 并行 lane 测试的共享 FAKE_CLI 与 helper。

由 test_content_campaign_controller__* 场景文件按名导入；autouse fixture
`_restore_capsule_permissions_for_pytest_cleanup` 需要在各测试模块中显式
import 以保持原有的按模块 autouse 语义。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from content.execution.campaign import submission as campaign_submission
from content.execution.campaign.external_input_runtime import (
    execution_external_input_envelope_path,
    load_execution_external_input_envelope,
)
from content.execution.campaign.runtime import read_lane_checkpoint
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.campaign.request_envelope import workload_intent
from content.execution.identity import build_execution_id
from content.execution.request import RuntimeExecutionRequest
from core.control_types import TargetSelector
from core.io import read_json
from support.capacity_calibration_fixture import synthetic_capacity_source_binding
from support.semantic_preflight_fixture import ready_semantic_preflight

ROOT_ID = "20260728--travel-homepage-workload-homepage-1--china--scale-001"
CARRIERS = ("homepage", "article", "image", "video")


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
identity_body = execution_id.split("--", 2)[1]
carrier = next(
    item
    for item in ("homepage", "article", "image", "video")
    if identity_body.startswith(f"travel-{item}-")
)
phase = "review" if stage == "review-only" else "publish"
event_path = Path(os.environ["CAMPAIGN_EVENT_LOG"])
external_input_envelope = (
    Path(os.environ["QWQ_OUTPUT_ROOT"])
    / "data/tasks"
    / execution_id
    / "0.plan/campaign_external_input_envelope.json"
)
reliabletask_env_keys = (
    "QWQ_RELIABLETASK_OBSERVER_BINARY_REF",
    "QWQ_RELIABLETASK_OBSERVER_BINARY_SHA256",
    "QWQ_RELIABLETASK_FLEET_TARGET",
    "QWQ_RELIABLETASK_FLEET_MONGO_URI",
    "QWQ_RELIABLETASK_FLEET_REDIS_ADDR",
    "QWQ_RELIABLETASK_FLEET_PLAN_DIGEST",
    "QWQ_RELIABLETASK_FLEET_BINDING_DIGEST",
)
# Campaign subprocesses stay transport-neutral in both stages.  The stage=run
# handler validates its frozen pool-delivery preflight before transport or drain.
reliabletask_binding_invalid = any(
    os.environ.get(key) for key in reliabletask_env_keys
)
if (
    os.environ.get("QWQ_CAMPAIGN_ROOT_EXECUTION_ID") != root_id
    or not os.environ.get("QWQ_FROZEN_MAIN_BRANCH")
    or reliabletask_binding_invalid
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
        "canonicalPublishRoot": "canonical-publish",
        "publishedRefs": published_refs,
        "publishDiscards": [],
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
if phase == "publish":
    payload["reviewQualifiedCount"] = qualified
    payload["publishDiscards"] = []
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
    intersection_reason = (
        repo
        / "quwoquan_service/services/recommendation-service/contracts"
        / "recommendation/recommendation_feature_profile_view/projections"
        / "intersection_reason.yaml"
    )
    intersection_reason.parent.mkdir(parents=True, exist_ok=True)
    intersection_reason.write_text(
        "schema: quwoquan.contract.test_projection\n",
        encoding="utf-8",
    )
    ui_config = (
        repo
        / "quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml"
    )
    ui_config.parent.mkdir(parents=True, exist_ok=True)
    ui_config.write_text(
        "schema: quwoquan.contract.ui_config\n",
        encoding="utf-8",
    )
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
        "allowed_local_branches:\n  - main\n",
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
    execution_bundle_spec = feature_root / "multi-carrier-release/spec.md"
    execution_bundle_spec.parent.mkdir(parents=True)
    execution_bundle_spec.write_text(
        "# Multi-carrier release\n",
        encoding="utf-8",
    )
    catalog = repo / "quwoquan_data/reference/travel/entities/china"
    catalog.mkdir(parents=True)
    (catalog / "catalog.yaml").write_text("entities: [测试实体]\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
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
        capacity_calibration=synthetic_capacity_source_binding(),
        topic=None,
        source_providers=(),
        target_names=(),
    )


def _execution_id(carrier: str, *, sequence: str = "001") -> str:
    if carrier == "homepage" and sequence == "001":
        return ROOT_ID
    return (
        f"20260728--travel-{carrier}-workload-{carrier}-1--china--scale-{sequence}"
    )


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


def _submit_active(
    repo: Path,
    runtime: CampaignRuntimePaths,
    monkeypatch: pytest.MonkeyPatch,
    *,
    workloads: dict[str, int],
) -> str:
    """Submit an exact carrier subset without synthesizing inactive lanes."""

    active = tuple(
        carrier for carrier in CARRIERS if carrier in workloads
    )
    intent = workload_intent(
        scale="M1000",
        workload_mode="explicit",
        workloads=workloads,
    )
    execution_ids = {
        carrier: build_execution_id(
            run_date="20260728",
            vertical="travel",
            content_type=carrier,
            intent=intent,
            scope="china",
            phase="scale",
            sequence=index,
        )
        for index, carrier in enumerate(active, start=1)
    }
    root_id = execution_ids[active[0]]
    monkeypatch.setattr(campaign_submission.paths, "REPO_ROOT", repo)
    semantic_preflight = _semantic_preflight_kwargs(runtime)
    for carrier in active:
        quota = int(workloads[carrier])
        campaign_submission.write_submission(
            root_execution_id=root_id,
            execution_id=execution_ids[carrier],
            request=_request(carrier, count=quota, quota=quota),
            retry_of=None,
            repo_root=repo,
            root=runtime.campaigns_root,
            active_carriers=active,
            workloads=workloads,
            **semantic_preflight,
        )
    return root_id


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
    assert capsule_manifest["gitBranch"] == "main"
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
