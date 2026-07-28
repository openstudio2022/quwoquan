"""Fail-closed four-lane campaign orchestration behind ``task execute``."""
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
from core.runtime_policy import DEFAULT_RUNTIME_PROFILE_ID, load_runtime_policy
from core.schema import assert_valid
from content.execution.campaign_receipt import load_lane_receipt
from content.execution.campaign_process import (
    CAMPAIGN_CARRIERS,
    LaneRunner,
    run_phase,
)
from content.execution.campaign_submission import campaign_root, load_submissions
from content.execution.campaign_workspace import (
    CampaignRuntimePaths,
    DetachedClone,
    assert_frozen_main_tree,
    assert_frozen_revision,
    cleanup_clone,
    prepare_detached_clone,
    require_clean_main_tree,
)
from content.execution.identity import validate_execution_id


CAMPAIGN_SUBMISSION_POLL_SECONDS = 2
_REVIEW_STAGE = "review-only"
_PUBLISH_STAGE = "run"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _campaign_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return campaign_root(root_execution_id, root=runtime.campaigns_root)


def _plan_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return _campaign_path(runtime, root_execution_id) / "campaign_plan.json"


def _report_path(runtime: CampaignRuntimePaths, root_execution_id: str) -> Path:
    return _campaign_path(runtime, root_execution_id) / "campaign_report.json"


@contextmanager
def _controller_lock(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Iterator[None]:
    path = _campaign_path(runtime, root_execution_id) / ".controller.lock"
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


def _empty_lane(execution_id: str = "pending") -> dict[str, Any]:
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
        "error": None,
    }


def _write_report(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    status: str,
    phase: str,
    plan_digest: str | None,
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
        "gitCommitSha": git_commit_sha,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "lanes": lanes,
        "failure": failure,
        "startedAt": started_at,
        "updatedAt": _utc_now(),
    }
    assert_valid(
        payload,
        "execution",
        "content_campaign_report",
        label=f"campaign report:{root_execution_id}",
    )
    path = _report_path(runtime, root_execution_id)
    write_json(path, payload)
    return path


def _wait_for_submissions(
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
        _write_report(
            runtime,
            root_execution_id,
            status="awaiting_submissions",
            phase="submission",
            plan_digest=None,
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


def _freeze_plan(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    submissions: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    commits = {str(row.get("gitCommitSha") or "") for row in submissions.values()}
    source_digests = {
        str((row.get("sourceDigest") or {}).get("digest") or "")
        for row in submissions.values()
    }
    catalog_digests = {
        str(row.get("entityCatalogDigest") or "") for row in submissions.values()
    }
    regions = {str(row.get("regionRef") or "") for row in submissions.values()}
    if len(commits) != 1 or len(source_digests) != 1 or len(catalog_digests) != 1:
        raise ValueError(
            "campaign lanes must share one commit, sourceDigest, "
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
        commit_sha=frozen_commit,
        source_digest=frozen_source,
    )
    stable = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": root_execution_id,
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
        "frozenAt": _utc_now(),
    }
    path = _plan_path(runtime, root_execution_id)
    if path.is_file():
        existing = read_json(path)
        digest = str(existing.get("planDigest") or "")
        digest_input = {key: value for key, value in existing.items() if key != "planDigest"}
        if digest != _sha256(digest_input):
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
    digest = _sha256(stable)
    plan = {**stable, "planDigest": digest}
    assert_valid(
        plan,
        "execution",
        "content_campaign_plan",
        label=f"campaign plan:{root_execution_id}",
    )
    write_json(path, plan)
    return plan, digest


def _apply_receipts(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    submissions: dict[str, dict[str, Any]],
    lanes: dict[str, dict[str, Any]],
    *,
    phase: str,
) -> None:
    for carrier in CAMPAIGN_CARRIERS:
        receipt = load_lane_receipt(
            root_execution_id,
            carrier,
            phase,
            root=runtime.campaigns_root,
        )
        if str(receipt.get("executionId") or "") != str(
            submissions[carrier]["executionId"]
        ):
            raise ValueError(f"{carrier} campaign receipt executionId drift")
        approved = int(receipt["approvedQuota"])
        qualified = int(receipt["qualifiedCount"])
        finalized = int(receipt["finalizedCount"])
        if approved != int(submissions[carrier]["quota"]) or qualified < approved:
            raise ValueError(
                f"{carrier} campaign quota barrier failed: "
                f"qualified={qualified} approvedQuota={approved}"
            )
        if phase == "publish" and finalized != qualified:
            raise ValueError(
                f"{carrier} campaign finalization differs from qualified closure"
            )
        lanes[carrier].update(
            {
                "approvedQuota": approved,
                "qualifiedCount": qualified,
                "finalizedCount": finalized,
                "status": (
                    "review_qualified"
                    if phase == "review"
                    else "finalized"
                ),
                "phase": phase,
            }
        )


def run_campaign(
    root_execution_id: str,
    *,
    submission_timeout_seconds: int | None = None,
    lane_timeout_seconds: float | None = None,
    runtime_paths: CampaignRuntimePaths | None = None,
    lane_runner: LaneRunner | None = None,
) -> Path:
    root_id = validate_execution_id(root_execution_id)
    runtime = runtime_paths or CampaignRuntimePaths.defaults()
    policy = load_runtime_policy(DEFAULT_RUNTIME_PROFILE_ID)
    effective_submission_timeout = (
        submission_timeout_seconds or policy.campaign_submission_timeout_seconds
    )
    effective_lane_timeout = (
        lane_timeout_seconds or policy.campaign_lane_timeout_seconds
    )
    started_at = _utc_now()
    lanes = {carrier: _empty_lane() for carrier in CAMPAIGN_CARRIERS}
    clones: dict[str, DetachedClone] = {}
    plan: dict[str, Any] | None = None
    plan_digest: str | None = None
    final_status = "blocked"
    final_phase = "submission"
    failure: str | None = None
    caught: Exception | None = None

    with _controller_lock(runtime, root_id):
        try:
            require_clean_main_tree(runtime.repo_root)
            submissions = _wait_for_submissions(
                runtime,
                root_id,
                timeout_seconds=effective_submission_timeout,
                lanes=lanes,
                started_at=started_at,
            )
            for carrier in CAMPAIGN_CARRIERS:
                lanes[carrier]["executionId"] = str(
                    submissions[carrier]["executionId"]
                )
            final_phase = "freeze"
            plan, plan_digest = _freeze_plan(runtime, root_id, submissions)
            _write_report(
                runtime,
                root_id,
                status="running",
                phase="clone",
                plan_digest=plan_digest,
                git_commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
                entity_catalog_digest=str(plan["entityCatalogDigest"]),
                lanes=lanes,
                started_at=started_at,
                failure=None,
            )
            final_phase = "clone"
            for carrier in CAMPAIGN_CARRIERS:
                clone = prepare_detached_clone(
                    runtime,
                    root_execution_id=root_id,
                    carrier=carrier,
                    commit_sha=str(plan["gitCommitSha"]),
                    source_digest=str(plan["sourceDigest"]),
                )
                clones[carrier] = clone
                lanes[carrier].update(
                    {
                        "status": "clone_ready",
                        "phase": "clone",
                        "cloneRef": clone.ref,
                        "cloneCommitSha": clone.commit_sha,
                        "cloneSourceDigest": clone.source_digest,
                        "cloneDetached": clone.detached,
                        "cleanupStatus": "pending",
                    }
                )
            assert_frozen_main_tree(
                runtime.repo_root,
                commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
            )
            final_phase = "review"
            review = run_phase(
                clones,
                submissions,
                stage=_REVIEW_STAGE,
                runtime=runtime,
                root_execution_id=root_id,
                timeout_seconds=effective_lane_timeout,
                worker_count=policy.campaign_lane_workers,
                lane_runner=lane_runner,
            )
            for carrier, (code, error) in review.items():
                lanes[carrier].update(
                    {
                        "reviewReturnCode": code,
                        "status": "reviewed" if code == 0 else "blocked",
                        "phase": "review",
                        "error": error,
                    }
                )
            if any(code != 0 for code, _error in review.values()):
                raise RuntimeError("one or more campaign lanes failed review")
            _apply_receipts(
                runtime,
                root_id,
                submissions,
                lanes,
                phase="review",
            )
            final_phase = "quota_barrier"
            assert_frozen_main_tree(
                runtime.repo_root,
                commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
            )
            _write_report(
                runtime,
                root_id,
                status="running",
                phase="quota_barrier",
                plan_digest=plan_digest,
                git_commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
                entity_catalog_digest=str(plan["entityCatalogDigest"]),
                lanes=lanes,
                started_at=started_at,
                failure=None,
            )
            final_phase = "publish"
            published = run_phase(
                clones,
                submissions,
                stage=_PUBLISH_STAGE,
                runtime=runtime,
                root_execution_id=root_id,
                timeout_seconds=effective_lane_timeout,
                worker_count=policy.campaign_lane_workers,
                lane_runner=lane_runner,
            )
            for carrier, (code, error) in published.items():
                lanes[carrier].update(
                    {
                        "publishReturnCode": code,
                        "status": "published" if code == 0 else "blocked",
                        "phase": "publish",
                        "error": error,
                    }
                )
            if any(code != 0 for code, _error in published.values()):
                raise RuntimeError("one or more campaign lanes failed publish")
            _apply_receipts(
                runtime,
                root_id,
                submissions,
                lanes,
                phase="publish",
            )
            assert_frozen_revision(
                runtime.repo_root,
                commit_sha=str(plan["gitCommitSha"]),
                source_digest=str(plan["sourceDigest"]),
            )
            final_status = "succeeded"
            final_phase = "completed"
        except Exception as exc:  # noqa: BLE001
            caught = exc
            failure = f"{type(exc).__name__}: {exc}"
        finally:
            cleanup_errors: list[str] = []
            for carrier, clone in clones.items():
                try:
                    cleanup_clone(clone)
                    lanes[carrier]["cleanupStatus"] = "cleaned"
                except OSError as exc:
                    lanes[carrier]["cleanupStatus"] = "failed"
                    cleanup_errors.append(f"{carrier}: {exc}")
            if cleanup_errors:
                final_status = "blocked"
                final_phase = "cleanup"
                failure = "; ".join(
                    item for item in (failure, *cleanup_errors) if item
                )
                if caught is None:
                    caught = RuntimeError(failure)
            _write_report(
                runtime,
                root_id,
                status=final_status,
                phase=final_phase,
                plan_digest=plan_digest,
                git_commit_sha=(
                    str(plan["gitCommitSha"]) if plan is not None else None
                ),
                source_digest=(
                    str(plan["sourceDigest"]) if plan is not None else None
                ),
                entity_catalog_digest=(
                    str(plan["entityCatalogDigest"]) if plan is not None else None
                ),
                lanes=lanes,
                started_at=started_at,
                failure=failure,
            )
    if caught is not None:
        raise caught
    return _report_path(runtime, root_id)


__all__ = [
    "CAMPAIGN_CARRIERS",
    "LaneRunner",
    "run_campaign",
]
