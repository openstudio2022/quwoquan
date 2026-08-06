"""Campaign plan freeze, report IO, and lane status aggregation helpers."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign_external_inputs import (
    external_inputs_digest,
    payload_digest,
)
from content.execution.campaign_process import CAMPAIGN_CARRIERS
from content.execution.campaign_receipt import load_lane_receipt
from content.execution.campaign_submission import campaign_root, load_submissions
from content.execution.campaign_workspace import (
    CampaignRuntimePaths,
    assert_frozen_main_tree,
)
from content.execution.reviewed_closure_adoption_campaign_contract import (
    CAMPAIGN_ADOPTION_FIELD,
    validate_adoption_target_identity,
    validate_campaign_adoption_binding,
)
from content.execution.semantic_preflight_admission import (
    validate_semantic_preflight_binding,
)

if TYPE_CHECKING:
    from content.execution.campaign_runtime import CampaignRunSession


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


def empty_lane(execution_id: str = "pending") -> dict[str, Any]:
    return {
        "executionId": execution_id,
        "status": "pending",
        "phase": "submission",
        "reviewReturnCode": None,
        "publishReturnCode": None,
        "sourceCapsuleRef": None,
        "sourceCapsuleDigest": None,
        "sourceCapsuleCommitSha": None,
        "sourceCapsuleSourceDigest": None,
        "sourceCapsuleReadOnly": None,
        "executionRootRef": None,
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
    from content.execution.campaign_runtime import read_runtime_snapshot

    runtime_snapshot = read_runtime_snapshot(runtime, root_execution_id) or {}
    payload = {
        "schema": "quwoquan_data.content_campaign_report",
        "rootExecutionId": root_execution_id,
        "campaignRunId": runtime_snapshot.get("runId"),
        "campaignGeneration": runtime_snapshot.get("generation"),
        "campaignFencingToken": runtime_snapshot.get("fencingToken"),
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
    run_session: CampaignRunSession | None = None,
) -> dict[str, dict[str, Any]]:
    if timeout_seconds < 1:
        raise ValueError("campaign submission timeout must be positive")
    deadline = time.monotonic() + timeout_seconds
    while True:
        if run_session is not None:
            run_session.campaign_checkpoint(phase="submission")
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
                "campaign submissions timed out; missing " + ", ".join(sorted(missing))
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
    *,
    execution_mode: str = "central",
    distributed_run: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    if execution_mode not in {"central", "distributed"}:
        raise ValueError(f"campaign execution mode is invalid: {execution_mode}")
    if execution_mode == "central" and distributed_run is not None:
        raise ValueError("central campaign plan forbids distributedRun")
    if execution_mode == "distributed":
        if not isinstance(distributed_run, Mapping):
            raise ValueError("distributed campaign plan requires distributedRun")
        if (
            not str(distributed_run.get("campaignRunId") or "").strip()
            or int(distributed_run.get("campaignGeneration") or 0) < 1
            or not str(distributed_run.get("campaignFencingToken") or "").startswith(
                "sha256:"
            )
        ):
            raise ValueError("distributed campaign run identity is incomplete")
    branches = {str(row.get("gitBranch") or "") for row in submissions.values()}
    commits = {str(row.get("gitCommitSha") or "") for row in submissions.values()}
    source_digests = {
        str((row.get("sourceDigest") or {}).get("digest") or "")
        for row in submissions.values()
    }
    catalog_digests = {
        str(row.get("entityCatalogDigest") or "") for row in submissions.values()
    }
    source_revisions = {
        str(row.get("sourceRevision") or "") for row in submissions.values()
    }
    regions = {str(row.get("regionRef") or "") for row in submissions.values()}
    semantic_selections = {
        str(row.get("semanticSelectionId") or "") for row in submissions.values()
    }
    semantic_preflights = {
        json.dumps(
            row.get("semanticPreflightReceipt"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in submissions.values()
    }
    selected_semantic = next(iter(semantic_selections), "")
    if selected_semantic != "not_applicable" and semantic_preflights == {"null"}:
        raise ValueError(
            "campaign selected semantic Provider requires one fresh "
            "preflight/soak receipt"
        )
    if (
        len(branches) != 1
        or not next(iter(branches))
        or len(commits) != 1
        or len(source_digests) != 1
        or len(catalog_digests) != 1
        or len(source_revisions) != 1
        or not next(iter(source_revisions))
        or len(semantic_selections) != 1
        or not next(iter(semantic_selections))
        or len(semantic_preflights) != 1
    ):
        raise ValueError(
            "campaign lanes must share one branch, commit, sourceRevision, "
            "sourceDigest, and entityCatalogDigest"
        )
    if len(regions) != 1:
        raise ValueError("campaign lanes must share one regionRef")
    if str(submissions["homepage"].get("executionId") or "") != root_execution_id:
        raise ValueError("homepage submission executionId must equal campaign root")
    adoption_values = [
        submissions[carrier].get(CAMPAIGN_ADOPTION_FIELD)
        for carrier in CAMPAIGN_CARRIERS
    ]
    reviewed_closure_adoption: dict[str, Any] | None = None
    if any(value is not None for value in adoption_values):
        if any(value is None for value in adoption_values):
            raise ValueError(
                "campaign cannot mix generate and reviewed-closure adoption lanes"
            )
        serialized = {
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            for value in adoption_values
        }
        if len(serialized) != 1:
            raise ValueError("campaign adoption bindings must be byte-identical")
        reviewed_closure_adoption = dict(adoption_values[0])
        binding = validate_campaign_adoption_binding(
            reviewed_closure_adoption,
            output_root=runtime.output_root,
        )
        validate_adoption_target_identity(
            {
                "sourceRevision": next(iter(source_revisions)),
                "sourceDigest": submissions["homepage"]["sourceDigest"],
                "entityCatalogDigest": next(iter(catalog_digests)),
            },
            binding=binding,
        )
        if any(
            submissions[carrier].get("externalInputRefs")
            for carrier in CAMPAIGN_CARRIERS
        ):
            raise ValueError(
                "reviewed closure adoption cannot masquerade as acquisition inputs"
            )
    frozen_commit = next(iter(commits))
    frozen_source = next(iter(source_digests))
    lane_external_inputs: dict[str, dict[str, Any]] = {}
    for carrier in CAMPAIGN_CARRIERS:
        refs = list(submissions[carrier].get("externalInputRefs") or [])
        digest = external_inputs_digest(refs)
        if submissions[carrier].get("externalInputsDigest") != digest:
            raise ValueError(
                "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_DIGEST_DRIFT: "
                f"{carrier} submission externalInputsDigest drift"
            )
        lane_external_inputs[carrier] = {
            "executionId": str(submissions[carrier]["executionId"]),
            "externalInputRefs": refs,
            "externalInputsDigest": digest,
        }
    aggregate_external_digest = payload_digest(
        {
            "schema": "quwoquan_data.campaign_external_input_lanes",
            "lanes": lane_external_inputs,
        }
    )
    assert_frozen_main_tree(
        runtime.repo_root,
        git_branch=next(iter(branches)),
        commit_sha=frozen_commit,
        source_digest=frozen_source,
    )
    stable = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": root_execution_id,
        "executionMode": execution_mode,
        "gitBranch": next(iter(branches)),
        "gitCommitSha": frozen_commit,
        "sourceRevision": next(iter(source_revisions)),
        "sourceDigest": frozen_source,
        "entityCatalogDigest": next(iter(catalog_digests)),
        "semanticSelectionId": next(iter(semantic_selections)),
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": aggregate_external_digest,
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
    if distributed_run is not None:
        stable["distributedRun"] = {
            "campaignRunId": str(distributed_run["campaignRunId"]),
            "campaignGeneration": int(distributed_run["campaignGeneration"]),
            "campaignFencingToken": str(distributed_run["campaignFencingToken"]),
        }
    semantic_preflight = submissions["homepage"].get("semanticPreflightReceipt")
    if semantic_preflight is not None:
        validate_semantic_preflight_binding(
            semantic_preflight,
            semantic_selection_id=next(iter(semantic_selections)),
            output_root=runtime.output_root,
        )
        stable["semanticPreflightReceipt"] = dict(semantic_preflight)
    if reviewed_closure_adoption is not None:
        stable[CAMPAIGN_ADOPTION_FIELD] = reviewed_closure_adoption
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
            else status
            if status in {"partial", "blocked"}
            else "reviewed"
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


def load_publish_for_lane(
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
            "publish",
            root=runtime.campaigns_root,
        )
    except (OSError, ValueError):
        return None
    if str(receipt.get("executionId") or "") != expected_execution_id:
        raise ValueError(f"{carrier} campaign publish receipt executionId drift")
    if int(receipt["approvedQuota"]) != expected_quota:
        raise ValueError(f"{carrier} campaign publish receipt approvedQuota drift")
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
    "empty_lane",
    "freeze_plan",
    "load_publish_for_lane",
    "load_review_for_lane",
    "plan_path",
    "report_path",
    "sha256_payload",
    "utc_now",
    "wait_for_submissions",
    "write_report",
]
