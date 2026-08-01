"""Campaign plan freeze, report IO, and lane status aggregation helpers."""
from __future__ import annotations

import fcntl
import hashlib
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.io import read_json, write_json
from core.schema import assert_valid
from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_receipt import load_lane_receipt
from content.execution.campaign_submission import campaign_root, load_submissions
from content.execution.campaign_workspace import (
    CampaignRuntimePaths,
    assert_frozen_main_tree,
)


CAMPAIGN_SUBMISSION_POLL_SECONDS = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def campaign_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return campaign_root(root_execution_id, root=runtime.campaigns_root)


def plan_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return campaign_path(runtime, root_execution_id) / "campaign_plan.json"


def report_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return campaign_path(runtime, root_execution_id) / "campaign_report.json"


@contextmanager
def controller_lock(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Iterator[None]:
    path = campaign_path(runtime, root_execution_id) / ".controller.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                f"campaign controller already active: {root_execution_id}"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def empty_lane(execution_id: str = "pending") -> dict[str, Any]:
    return {
        "executionId": execution_id,
        "status": "pending",
        "phase": "submission",
        "reviewReturnCode": None,
        "publishReturnCode": None,
        "cloneRef": None,
        "cloneCommitSha": None,
        "cloneSourceDigest": None,
        "cloneDetached": None,
        "cleanupStatus": "not_created",
        "approvedQuota": None,
        "qualifiedCount": None,
        "finalizedCount": None,
        "selectedCount": None,
        "discardedCount": None,
        "shortfallCount": None,
        "error": None,
    }


def write_report(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    status: str,
    phase: str,
    plan_digest: str | None,
    git_branch: str | None,
    git_commit_sha: str | None,
    source_digest: str | None,
    entity_catalog_digest: str | None,
    lanes: dict[str, dict[str, Any]],
    started_at: str,
    failure: str | None,
) -> Path:
    payload = {
        "schema": "quwoquan_data.content_campaign_report",
        "rootExecutionId": root_execution_id,
        "status": status,
        "phase": phase,
        "planDigest": plan_digest,
        "gitBranch": git_branch,
        "gitCommitSha": git_commit_sha,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "lanes": lanes,
        "failure": failure,
        "startedAt": started_at,
        "updatedAt": utc_now(),
    }
    assert_valid(
        payload,
        "execution",
        "content_campaign_report",
        label=f"campaign report:{root_execution_id}",
    )
    path = report_path(runtime, root_execution_id)
    write_json(path, payload)
    return path


def wait_for_submissions(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    timeout_seconds: int,
    lanes: dict[str, dict[str, Any]],
    started_at: str,
) -> dict[str, dict[str, Any]]:
    if timeout_seconds < 1:
        raise ValueError("campaign submission timeout must be positive")
    deadline = time.monotonic() + timeout_seconds
    while True:
        submissions = load_submissions(
            root_execution_id,
            root=runtime.campaigns_root,
        )
        missing = set(CAMPAIGN_CARRIERS) - set(submissions)
        if not missing:
            return submissions
        write_report(
            runtime,
            root_execution_id,
            status="awaiting_submissions",
            phase="submission",
            plan_digest=None,
            git_branch=None,
            git_commit_sha=None,
            source_digest=None,
            entity_catalog_digest=None,
            lanes=lanes,
            started_at=started_at,
            failure=None,
        )
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "campaign submissions timed out; missing "
                + ", ".join(sorted(missing))
            )
        time.sleep(
            min(
                CAMPAIGN_SUBMISSION_POLL_SECONDS,
                max(0.0, deadline - time.monotonic()),
            )
        )


def freeze_plan(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    submissions: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    branches = {str(row.get("gitBranch") or "") for row in submissions.values()}
    commits = {str(row.get("gitCommitSha") or "") for row in submissions.values()}
    source_digests = {
        str((row.get("sourceDigest") or {}).get("digest") or "")
        for row in submissions.values()
    }
    catalog_digests = {
        str(row.get("entityCatalogDigest") or "") for row in submissions.values()
    }
    regions = {str(row.get("regionRef") or "") for row in submissions.values()}
    if (
        len(branches) != 1
        or not next(iter(branches))
        or len(commits) != 1
        or len(source_digests) != 1
        or len(catalog_digests) != 1
    ):
        raise ValueError(
            "campaign lanes must share one branch, commit, sourceDigest, "
            "and entityCatalogDigest"
        )
    if len(regions) != 1:
        raise ValueError("campaign lanes must share one regionRef")
    if str(submissions["homepage"].get("executionId") or "") != root_execution_id:
        raise ValueError("homepage submission executionId must equal campaign root")
    frozen_commit = next(iter(commits))
    frozen_source = next(iter(source_digests))
    assert_frozen_main_tree(
        runtime.repo_root,
        git_branch=next(iter(branches)),
        commit_sha=frozen_commit,
        source_digest=frozen_source,
    )
    stable = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": root_execution_id,
        "gitBranch": next(iter(branches)),
        "gitCommitSha": frozen_commit,
        "sourceDigest": frozen_source,
        "entityCatalogDigest": next(iter(catalog_digests)),
        "submissionDigests": {
            carrier: str(submissions[carrier]["requestDigest"])
            for carrier in CAMPAIGN_CARRIERS
        },
        "executionIds": {
            carrier: str(submissions[carrier]["executionId"])
            for carrier in CAMPAIGN_CARRIERS
        },
        "frozenAt": utc_now(),
    }
    path = plan_path(runtime, root_execution_id)
    if path.is_file():
        existing = read_json(path)
        digest = str(existing.get("planDigest") or "")
        digest_input = {
            key: value for key, value in existing.items() if key != "planDigest"
        }
        if digest != sha256_payload(digest_input):
            raise ValueError("campaign planDigest drift")
        stable_keys = set(stable) - {"frozenAt"}
        if any(existing.get(key) != stable[key] for key in stable_keys):
            raise ValueError("campaign plan is immutable and already differs")
        assert_valid(
            existing,
            "execution",
            "content_campaign_plan",
            label=f"campaign plan:{root_execution_id}",
        )
        return existing, digest
    digest = sha256_payload(stable)
    plan = {**stable, "planDigest": digest}
    assert_valid(
        plan,
        "execution",
        "content_campaign_plan",
        label=f"campaign plan:{root_execution_id}",
    )
    write_json(path, plan)
    return plan, digest


def apply_receipt_fields(
    lanes: dict[str, dict[str, Any]],
    carrier: str,
    receipt: dict[str, Any],
    *,
    phase: str,
) -> None:
    status = str(receipt.get("status") or "")
    if phase == "review":
        lane_status = (
            "review_qualified"
            if status == "qualified"
            else status if status in {"partial", "blocked"} else "reviewed"
        )
    elif status == "finalized":
        lane_status = "finalized"
    elif status == "partial":
        lane_status = "partial"
    else:
        lane_status = "blocked"
    lanes[carrier].update(
        {
            "approvedQuota": int(receipt["approvedQuota"]),
            "qualifiedCount": int(receipt["qualifiedCount"]),
            "finalizedCount": int(receipt["finalizedCount"]),
            "selectedCount": int(receipt["selectedCount"]),
            "discardedCount": int(receipt["discardedCount"]),
            "shortfallCount": int(receipt["shortfallCount"]),
            "status": lane_status,
            "phase": phase,
        }
    )


def load_review_for_lane(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
    *,
    expected_execution_id: str,
    expected_quota: int,
) -> dict[str, Any] | None:
    try:
        receipt = load_lane_receipt(
            root_execution_id,
            carrier,
            "review",
            root=runtime.campaigns_root,
        )
    except (OSError, ValueError):
        return None
    if str(receipt.get("executionId") or "") != expected_execution_id:
        raise ValueError(f"{carrier} campaign receipt executionId drift")
    if int(receipt["approvedQuota"]) != expected_quota:
        raise ValueError(f"{carrier} campaign receipt approvedQuota drift")
    return receipt


def aggregate_status(lanes: dict[str, dict[str, Any]]) -> str:
    finalized_or_partial = 0
    milestone_met = 0
    for carrier in CAMPAIGN_CARRIERS:
        lane = lanes[carrier]
        qualified = int(lane.get("qualifiedCount") or 0)
        finalized = int(lane.get("finalizedCount") or 0)
        approved = int(lane.get("approvedQuota") or 0)
        status = str(lane.get("status") or "")
        if finalized > 0 and status in {"finalized", "partial", "published"}:
            finalized_or_partial += 1
            if approved > 0 and finalized >= approved and qualified >= approved:
                milestone_met += 1
    if finalized_or_partial == 0:
        return "blocked"
    if milestone_met == len(CAMPAIGN_CARRIERS):
        return "succeeded"
    return "succeeded_partial"


__all__ = [
    "CAMPAIGN_SUBMISSION_POLL_SECONDS",
    "aggregate_status",
    "apply_receipt_fields",
    "campaign_path",
    "controller_lock",
    "empty_lane",
    "freeze_plan",
    "load_review_for_lane",
    "plan_path",
    "report_path",
    "sha256_payload",
    "utc_now",
    "wait_for_submissions",
    "write_report",
]
