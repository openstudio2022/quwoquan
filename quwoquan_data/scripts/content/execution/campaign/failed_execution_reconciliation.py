"""Create-once reconciliation for terminal campaign boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json, write_json
from core.schema import assert_valid
from core.source_digest import current_source_digest

from content.execution.campaign.failed_execution_reconciliation_cli import (
    register_reconcile_failed_campaign_parser,
)
from content.execution.campaign.failed_execution_reconciliation_common import (
    _ERROR_CODES,
    SCHEMA,
    _file_binding,
    _lock,
    _now,
    terminal_unpublished_receipt_path,
)
from content.execution.campaign.failed_execution_reconciliation_dispatch import (
    failed_campaign_evidence,
)
from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.campaign.runtime_process import _pid_alive
from content.execution.campaign.submission_reconciliation_contract import (
    campaigns_root,
    canonical_digest,
    file_digest,
    load_terminal_submission_documents,
    predecessor_campaign_root_execution_id,
    reconciliation_receipt_path,
    resolve_ref,
    source_identity,
    submission_evidence,
    typed,
)
from content.execution.identity import parse_execution_id
from content.execution.workspace import entity_catalog_digest


def _source_drift_successor(
    plan: Mapping[str, Any],
    report: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> bool:
    distributed = plan.get("distributedRun")
    if not isinstance(distributed, Mapping):
        return False
    failure = (
        "ValueError: campaign sourceDigest drift: "
        f"frozen={plan.get('sourceDigest')} current="
    )
    return (
        report.get("status") == "blocked"
        and report.get("phase") == "freeze"
        and report.get("planDigest") is None
        and report.get("sourceDigest") is None
        and report.get("entityCatalogDigest") is None
        and str(report.get("failure") or "").startswith(failure)
        and runtime.get("status") == "blocked"
        and runtime.get("phase") == "freeze"
        and runtime.get("planDigest") is None
        and runtime.get("lanes") == {}
        and bool(runtime.get("finishedAt"))
        and runtime.get("failure") == report.get("failure")
        and runtime.get("runId") == report.get("campaignRunId")
        and runtime.get("generation") == report.get("campaignGeneration")
        and runtime.get("fencingToken") == report.get("campaignFencingToken")
        and int(runtime.get("generation") or 0)
        == int(distributed.get("campaignGeneration") or 0) + 1
        and runtime.get("runId") != distributed.get("campaignRunId")
    )
def _terminalize_dead_source_drift_claims(
    root_id: str,
    *,
    output_root: Path,
) -> None:
    campaign = campaigns_root(output_root) / root_id
    plan = read_json(campaign / "campaign_plan.json")
    report = read_json(campaign / "campaign_report.json")
    runtime = read_json(campaign / "runtime/snapshot.json")
    if not all(isinstance(item, Mapping) for item in (plan, report, runtime)):
        return
    if not _source_drift_successor(plan, report, runtime):
        return
    distributed = plan["distributedRun"]
    for carrier in CAMPAIGN_CARRIERS:
        path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(path)
        if not isinstance(claim, dict) or claim.get("status") not in {
            "active",
            "starting",
            "running",
        }:
            continue
        execution_root = Path(str(claim.get("executionRoot") or ""))
        if (
            claim.get("rootExecutionId") != root_id
            or claim.get("carrier") != carrier
            or claim.get("planDigest") != plan.get("planDigest")
            or claim.get("campaignRunId") != distributed.get("campaignRunId")
            or claim.get("campaignGeneration")
            != distributed.get("campaignGeneration")
            or claim.get("campaignFencingToken")
            != distributed.get("campaignFencingToken")
            or _pid_alive(claim.get("pid"))
            or _pid_alive(claim.get("pgid"))
            or execution_root.exists()
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} source-drift claim is still live or identity-drifted",
            )
        now = _now()
        claim.update(
            {
                "status": "failed",
                "phase": "completed",
                "returnCode": (
                    claim["returnCode"]
                    if isinstance(claim.get("returnCode"), int)
                    and claim["returnCode"] != 0
                    else 130
                ),
                "error": str(claim.get("error") or "").strip()
                or "DATA.CAMPAIGN.LANE_PROCESS_GONE_AFTER_SOURCE_DRIFT",
                "terminationOwner": claim.get("terminationOwner")
                or "external_or_kernel",
                "updatedAt": now,
                "finishedAt": now,
            }
        )
        assert_valid(
            claim,
            "execution",
            "content_campaign_lane_claim",
            label=f"source-drift terminal campaign lane claim:{carrier}",
        )
        write_json(path, claim)
def _failed_campaign_evidence(
    root_id: str,
    *,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign = campaigns_root(output_root) / root_id
    plan_path = campaign / "campaign_plan.json"
    report_path = campaign / "campaign_report.json"
    runtime_path = campaign / "runtime/snapshot.json"
    plan = read_json(plan_path)
    report = read_json(report_path)
    runtime = read_json(runtime_path)
    if not all(isinstance(item, Mapping) for item in (plan, report, runtime)):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "campaign evidence must be objects")
    frozen_boundary = (
        runtime.get("status") == "frozen"
        and bool(runtime.get("finishedAt"))
    )
    interrupted_successor = (
        runtime.get("status") == "interrupted"
        and runtime.get("phase") == "controller"
        and bool(runtime.get("finishedAt"))
        and runtime.get("planDigest") is None
        and runtime.get("lanes") == {}
        and runtime.get("failure")
        == "ValueError: campaign plan is immutable and already differs"
        and int(runtime.get("generation") or 0)
        == int(report.get("campaignGeneration") or 0) + 1
        and runtime.get("runId") != report.get("campaignRunId")
    )
    source_drift_successor = _source_drift_successor(plan, report, runtime)
    if (
        plan.get("rootExecutionId") != root_id
        or report.get("rootExecutionId") != root_id
        or runtime.get("rootExecutionId") != root_id
        or not (frozen_boundary or interrupted_successor or source_drift_successor)
        or (
            not source_drift_successor
            and report.get("phase") != "capsule"
        )
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign did not stop at one frozen capsule boundary",
        )
    shared = (
        ("planDigest", "planDigest"),
        ("campaignRunId", "runId"),
        ("campaignGeneration", "generation"),
        ("campaignFencingToken", "fencingToken"),
    )
    if frozen_boundary and any(
        report.get(left) != runtime.get(right) for left, right in shared
    ):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "campaign runtime identity drifted")
    distributed = plan.get("distributedRun")
    if not isinstance(distributed, Mapping):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "distributed campaign binding is missing")
    claims: dict[str, dict[str, str]] = {}
    capsule_ref: str | None = None
    report_lanes = report.get("lanes")
    if not isinstance(report_lanes, Mapping):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "campaign report lanes are invalid")
    for carrier in CAMPAIGN_CARRIERS:
        claim_path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(claim_path)
        lane = report_lanes.get(carrier)
        terminal_failed = (
            isinstance(claim, Mapping)
            and claim.get("status") == "failed"
            and bool(claim.get("finishedAt"))
            and (
                claim.get("returnCode") != 0
                or bool(str(claim.get("error") or "").strip())
            )
        )
        stale_interrupted = (
            isinstance(claim, Mapping)
            and claim.get("status") in {"active", "starting", "running"}
            and isinstance(claim.get("returnCode"), int)
            and claim.get("returnCode") != 0
            and claim.get("terminationOwner") == "lane_process"
            and not _pid_alive(claim.get("pid"))
            and not _pid_alive(claim.get("pgid"))
        )
        successor_lane = (
            source_drift_successor
            and isinstance(lane, Mapping)
            and lane.get("status") == "pending"
            and lane.get("phase") == "submission"
            and lane.get("executionRootRef") is None
            and lane.get("cleanupStatus") == "not_created"
        )
        if (
            not isinstance(claim, Mapping)
            or not isinstance(lane, Mapping)
            or claim.get("rootExecutionId") != root_id
            or claim.get("carrier") != carrier
            or claim.get("planDigest") != plan.get("planDigest")
            or claim.get("campaignRunId") != distributed.get("campaignRunId")
            or claim.get("campaignGeneration")
            != distributed.get("campaignGeneration")
            or claim.get("campaignFencingToken")
            != distributed.get("campaignFencingToken")
            or not (terminal_failed or stale_interrupted)
            or (terminal_failed and claim.get("phase") != "completed")
            or (
                stale_interrupted
                and claim.get("phase") not in {"review-only", "run"}
            )
            or not isinstance(claim.get("returnCode"), int)
            or (
                not successor_lane
                and (
                    lane.get("status") != "capsule_ready"
                    or lane.get("phase") != "capsule"
                )
            )
            or lane.get("reviewReturnCode") is not None
            or lane.get("publishReturnCode") is not None
            or any(
                lane.get(field) is not None
                for field in (
                    "approvedQuota",
                    "qualifiedCount",
                    "finalizedCount",
                    "selectedCount",
                    "discardedCount",
                    "shortfallCount",
                )
            )
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} is not a terminal pre-execution failure",
            )
        observed_capsule_ref = str(claim.get("capsuleRef") or "")
        if not observed_capsule_ref or (
            capsule_ref is not None and observed_capsule_ref != capsule_ref
        ):
            raise typed(
                "CAMPAIGN_EVIDENCE_INVALID",
                "campaign claims do not share one frozen capsule",
            )
        capsule_ref = observed_capsule_ref
        claims[carrier] = _file_binding(
            claim_path,
            output_root=output_root,
            label=f"{carrier} failed claim",
        )
    return (
        {
            "plan": _file_binding(
                plan_path,
                output_root=output_root,
                label="campaign plan",
            ),
            "report": _file_binding(
                report_path,
                output_root=output_root,
                label="campaign report",
            ),
            "runtimeSnapshot": _file_binding(
                runtime_path,
                output_root=output_root,
                label="campaign runtime snapshot",
            ),
            "claims": claims,
        },
        dict(plan if source_drift_successor else report),
    )
def validate_failed_campaign_reconciliation_receipt(
    path: Path,
    *,
    output_root: Path,
) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise typed("RECEIPT_INVALID", "failed campaign receipt must be an object")
    try:
        assert_valid(
            payload,
            "execution",
            "campaign_failed_execution_reconciliation_receipt",
            label=f"failed campaign reconciliation:{path}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed("RECEIPT_INVALID", str(exc)) from exc
    stable = {key: value for key, value in payload.items() if key != "receiptDigest"}
    if payload.get("receiptDigest") != canonical_digest(stable):
        raise typed("DIGEST_DRIFT", "failed campaign receipt digest drifted")
    root_id = str(payload["rootExecutionId"])
    submissions = load_terminal_submission_documents(
        root_id,
        output_root=output_root,
        require_all=True,
    )
    rows, original = submission_evidence(
        submissions,
        output_root=output_root,
        root_execution_id=root_id,
    )
    reason = payload["reason"]
    if reason == "terminal_unpublished_source_drift":
        expected_path = terminal_unpublished_receipt_path(
            root_id,
            payload["observedSourceIdentity"]["sourceRevision"],
            output_root=output_root,
        )
        if path.resolve() != expected_path.resolve():
            raise typed(
                "ROOT_DRIFT",
                "terminal unpublished receipt is not at its observed identity path",
            )
    campaign_evidence, execution_evidence, report = failed_campaign_evidence(
        reason,
        root_id,
        submissions,
        original,
        output_root=output_root,
        fallback=lambda value: _failed_campaign_evidence(
            value,
            output_root=output_root,
        ),
    )
    if (
        payload.get("submissions") != rows
        or payload.get("originalSourceIdentity") != original
        or payload.get("campaignEvidence") != campaign_evidence
        or payload.get("executionEvidence") != execution_evidence
        or report.get("sourceDigest") != original["sourceDigest"]["digest"]
        or report.get("entityCatalogDigest") != original["entityCatalogDigest"]
        or (
            reason == "terminal_unpublished_source_drift"
            and payload.get("observedSourceIdentity") == original
        )
    ):
        raise typed("DIGEST_DRIFT", "failed campaign reconciliation evidence drifted")
    blocker = payload.get("blockerEvidence")
    blocker_path = resolve_ref(
        blocker.get("ref"),
        output_root=output_root,
        label="failed campaign blocker evidence",
    )
    if file_digest(blocker_path) != blocker.get("sha256"):
        raise typed("DIGEST_DRIFT", "failed campaign blocker evidence drifted")
    if (
        payload["reason"] == "controller_interrupted_before_claim"
        and blocker != campaign_evidence["runtimeSnapshot"]
    ):
        raise typed("DIGEST_DRIFT", "controller blocker is not the runtime snapshot")
    if (
        payload["reason"] == "post_publish_partial_terminal"
        and blocker != execution_evidence["partialPublish"]["executionState"]
    ):
        raise typed("DIGEST_DRIFT", "post-publish blocker is not article state")
    if payload["reason"] == "mixed_finalized_partial_terminal":
        failed_lane = next(
            row
            for row in execution_evidence["lanes"]
            if row.get("terminalStatus") == "failed"
        )
        if blocker != failed_lane["claim"]:
            raise typed(
                "DIGEST_DRIFT",
                "mixed terminal blocker is not the failed lane claim",
            )
    if (
        payload["reason"] == "terminal_unpublished_source_drift"
        and blocker != campaign_evidence["report"]
    ):
        raise typed(
            "DIGEST_DRIFT",
            "terminal unpublished blocker is not the campaign report",
        )
    return payload
def reconcile_failed_campaign(
    root_execution_id: str,
    *,
    blocker_evidence: Path | None = None,
    reason: str = "source_drift",
    repo_root: Path | None = None,
    output_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    source_repo = (repo_root or paths.REPO_ROOT).resolve()
    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    root_id = predecessor_campaign_root_execution_id(root_execution_id)
    if root_id != root_execution_id:
        raise typed("IDENTITY_DRIFT", "rootExecutionId must be the homepage lane")
    if reason not in _ERROR_CODES:
        raise typed("REASON_INVALID", f"unsupported failed campaign reason: {reason}")
    receipt_path = reconciliation_receipt_path(
        root_id,
        output_root=resolved_output,
    )
    if reason != "terminal_unpublished_source_drift" and receipt_path.is_file():
        existing_payload = read_json(receipt_path)
        if not isinstance(existing_payload, Mapping) or existing_payload.get(
            "reason"
        ) != reason:
            raise typed("CREATE_ONCE_COLLISION", "existing failed receipt reason differs")
    with _lock(receipt_path):
        if reason == "source_drift":
            _terminalize_dead_source_drift_claims(
                root_id,
                output_root=resolved_output,
            )
    submissions = load_terminal_submission_documents(
        root_id,
        output_root=resolved_output,
        require_all=True,
    )
    rows, original = submission_evidence(
        submissions,
        output_root=resolved_output,
        root_execution_id=root_id,
    )
    campaign_evidence, execution_evidence, report = failed_campaign_evidence(
        reason,
        root_id,
        submissions,
        original,
        output_root=resolved_output,
        fallback=lambda value: _failed_campaign_evidence(
            value,
            output_root=resolved_output,
        ),
    )
    observed_source = current_source_digest(repo_root=source_repo).to_document()
    representative = submissions["homepage"]
    discovery = (
        source_repo
        / "quwoquan_data/reference"
        / parse_execution_id(root_id).vertical
        / "entities"
        / str(representative["regionRef"])
    )
    observed = source_identity(
        observed_source,
        catalog_digest=entity_catalog_digest(
            discovery.relative_to(source_repo).as_posix()
        ),
    )
    if reason in {"source_drift", "claimed_execution_source_drift"} and observed == original:
        raise typed("REASON_INVALID", "failed campaign source identity has not drifted")
    if reason == "terminal_unpublished_source_drift" and observed == original:
        raise typed(
            "REASON_INVALID",
            "terminal unpublished campaign source identity has not drifted",
        )
    if reason == "terminal_unpublished_source_drift":
        receipt_path = terminal_unpublished_receipt_path(
            root_id,
            observed["sourceRevision"],
            output_root=resolved_output,
        )
    existing_payload = read_json(receipt_path) if receipt_path.is_file() else None
    if isinstance(existing_payload, Mapping) and existing_payload.get("reason") != reason:
        raise typed("CREATE_ONCE_COLLISION", "existing failed receipt reason differs")
    if reason == "controller_interrupted_before_claim":
        blocker = campaign_evidence["runtimeSnapshot"]
        if blocker_evidence is not None:
            blocker_path = blocker_evidence.expanduser()
            if not blocker_path.is_absolute():
                blocker_path = source_repo / blocker_path
            if _file_binding(
                blocker_path.resolve(),
                output_root=resolved_output,
                label="failed campaign blocker evidence",
            ) != blocker:
                raise typed("BLOCKER_INVALID", "controller blocker must be its snapshot")
    else:
        if blocker_evidence is None:
            raise typed("BLOCKER_INVALID", f"{reason} requires blocker evidence")
        blocker_path = blocker_evidence.expanduser()
        if not blocker_path.is_absolute():
            blocker_path = source_repo / blocker_path
        blocker = _file_binding(
            blocker_path.resolve(),
            output_root=resolved_output,
            label="failed campaign blocker evidence",
        )
        if (
            reason == "post_publish_partial_terminal"
            and blocker != execution_evidence["partialPublish"]["executionState"]
        ):
            raise typed("BLOCKER_INVALID", "post-publish blocker must be article state")
        if reason == "mixed_finalized_partial_terminal":
            failed_lane = next(
                row
                for row in execution_evidence["lanes"]
                if row.get("terminalStatus") == "failed"
            )
            if blocker != failed_lane["claim"]:
                raise typed(
                    "BLOCKER_INVALID",
                    "mixed terminal blocker must be the failed lane claim",
                )
        if (
            reason == "terminal_unpublished_source_drift"
            and blocker != campaign_evidence["report"]
        ):
            raise typed(
                "BLOCKER_INVALID",
                "terminal unpublished blocker must be the campaign report",
            )
    if report.get("sourceDigest") != original["sourceDigest"]["digest"]:
        raise typed("IDENTITY_DRIFT", "campaign report source digest drifted")
    stable = {
        "schema": SCHEMA,
        "rootExecutionId": root_id,
        "decision": "superseded",
        "reason": reason,
        "errorCode": _ERROR_CODES[reason],
        "originalSourceIdentity": original,
        "observedSourceIdentity": observed,
        "submissions": rows,
        "campaignEvidence": campaign_evidence,
        "executionEvidence": execution_evidence,
        "blockerEvidence": blocker,
        "retryPolicy": "new_four_lane_execution_with_retryOf",
        "recordedAt": _now(),
    }
    receipt = {**stable, "receiptDigest": canonical_digest(stable)}
    assert_valid(
        receipt,
        "execution",
        "campaign_failed_execution_reconciliation_receipt",
        label=f"failed campaign reconciliation:{root_id}",
    )
    with _lock(receipt_path):
        if receipt_path.is_file():
            existing = validate_failed_campaign_reconciliation_receipt(
                receipt_path,
                output_root=resolved_output,
            )
            if (
                existing.get("rootExecutionId") != root_id
                or existing.get("reason") != reason
                or existing.get("blockerEvidence") != blocker
            ):
                raise typed("CREATE_ONCE_COLLISION", "existing failed receipt differs")
            return existing, receipt_path
        write_json(receipt_path, receipt)
    validate_failed_campaign_reconciliation_receipt(
        receipt_path,
        output_root=resolved_output,
    )
    return receipt, receipt_path
__all__ = ["reconcile_failed_campaign", "register_reconcile_failed_campaign_parser", "validate_failed_campaign_reconciliation_receipt"]
