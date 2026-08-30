"""Evidence contract for finalized active lanes plus one failed active lane."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json

from content.execution.campaign.failed_execution_reconciliation_claimed import (
    _dead_process,
    _process_group_alive,
)
from content.execution.campaign.failed_execution_reconciliation_common import (
    file_binding,
)
from content.execution.campaign.failed_execution_reconciliation_mixed_manifest import (
    canonical_manifests,
)
from content.execution.campaign.submission_reconciliation_contract import (
    campaigns_root,
    canonical_digest,
    frozen_plan_workload,
    frozen_submission_workload,
    typed,
)
from content.release.canonical.campaign_release_contract import (
    CampaignReleaseError,
    CampaignReleaseRoots,
)
from content.release.canonical.campaign_release_publish import validate_lane_publish


def _campaign_documents(
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    original: Mapping[str, Any],
    *,
    output_root: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], str]:
    campaign = campaigns_root(output_root) / root_execution_id
    plan = read_json(campaign / "campaign_plan.json")
    report = read_json(campaign / "campaign_report.json")
    runtime = read_json(campaign / "runtime/snapshot.json")
    if not all(isinstance(row, dict) for row in (plan, report, runtime)):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "mixed terminal reconciliation requires plan/report/runtime objects",
        )
    stable_plan = {key: value for key, value in plan.items() if key != "planDigest"}
    source_digest = (original.get("sourceDigest") or {}).get("digest")
    distributed = plan.get("distributedRun")
    active_carriers, _workloads, plan_execution_ids, _root = frozen_plan_workload(
        plan,
        root_execution_id=root_execution_id,
    )
    submission_carriers, _submission_workloads, _submission_root = (
        frozen_submission_workload(
            submissions,
            root_execution_id=root_execution_id,
        )
    )
    expected_ids = {
        carrier: str(submissions[carrier]["executionId"])
        for carrier in active_carriers
    }
    expected_digests = {
        carrier: str(submissions[carrier]["requestDigest"])
        for carrier in active_carriers
    }
    if (
        plan.get("rootExecutionId") != root_execution_id
        or plan.get("planDigest") != canonical_digest(stable_plan)
        or plan.get("sourceRevision") != original.get("sourceRevision")
        or plan.get("sourceDigest") != source_digest
        or plan.get("entityCatalogDigest") != original.get("entityCatalogDigest")
        or active_carriers != submission_carriers
        or plan_execution_ids != expected_ids
        or plan.get("executionIds") != expected_ids
        or plan.get("submissionDigests") != expected_digests
        or not isinstance(distributed, Mapping)
        or "reviewedClosureAdoption" in plan
        or any("reviewedClosureAdoption" in row for row in submissions.values())
    ):
        raise typed("IDENTITY_DRIFT", "mixed terminal campaign plan identity drifted")
    lanes = report.get("lanes")
    failed_carriers = [
        carrier
        for carrier in active_carriers
        if isinstance(lanes, Mapping)
        and isinstance(lanes.get(carrier), Mapping)
        and lanes[carrier].get("status") == "blocked"
    ]
    failed_carrier = failed_carriers[0] if len(failed_carriers) == 1 else ""
    failed_lane = lanes.get(failed_carrier) if isinstance(lanes, Mapping) else None
    failed_error = (
        str(failed_lane.get("error") or "").strip()
        if isinstance(failed_lane, Mapping)
        else ""
    )
    expected_failure = (
        f"{failed_carrier}:{failed_error}"
        if failed_carrier and failed_error
        else ""
    )
    if (
        report.get("rootExecutionId") != root_execution_id
        or report.get("status") != "succeeded_partial"
        or report.get("phase") != "completed"
        or report.get("planDigest") != plan.get("planDigest")
        or report.get("campaignRunId") != distributed.get("campaignRunId")
        or report.get("campaignGeneration")
        != distributed.get("campaignGeneration")
        or report.get("campaignFencingToken")
        != distributed.get("campaignFencingToken")
        or report.get("sourceDigest") != source_digest
        or report.get("entityCatalogDigest") != original.get("entityCatalogDigest")
        or not isinstance(lanes, Mapping)
        or set(lanes) != set(active_carriers)
        or not expected_failure
        or report.get("failure") != expected_failure
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign report is not one mixed finalized partial terminal boundary",
        )
    if (
        runtime.get("rootExecutionId") != root_execution_id
        or runtime.get("status") != "frozen"
        or runtime.get("phase") != "capsule"
        or runtime.get("planDigest") != plan.get("planDigest")
        or runtime.get("runId") != distributed.get("campaignRunId")
        or runtime.get("generation") != distributed.get("campaignGeneration")
        or runtime.get("fencingToken") != distributed.get("campaignFencingToken")
        or runtime.get("lanes") != {}
        or runtime.get("failure") not in {None, ""}
        or not str(runtime.get("finishedAt") or "").strip()
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign runtime is not the bound frozen mixed terminal snapshot",
        )
    return campaign, plan, report, runtime, failed_carrier


def _execution_root(
    claim: Mapping[str, Any], execution_id: str, *, output_root: Path, carrier: str
) -> Path:
    root = output_root / "data/tasks" / execution_id
    try:
        same_root = Path(str(claim.get("executionRoot") or "")).resolve() == root.resolve()
    except (OSError, RuntimeError):
        same_root = False
    if not same_root or root.is_symlink() or not root.is_dir():
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} execution root is missing or identity-drifted",
        )
    return root


def _terminal_claim(
    campaign: Path,
    plan: Mapping[str, Any],
    carrier: str,
    execution_id: str,
    *,
    output_root: Path,
    finalized: bool,
) -> tuple[Mapping[str, Any], Path, dict[str, str]]:
    path = campaign / "claims" / f"{carrier}.json"
    claim = read_json(path)
    distributed = plan["distributedRun"]
    expected_status = "completed" if finalized else "failed"
    expected_return = 0 if finalized else None
    if (
        not isinstance(claim, Mapping)
        or claim.get("rootExecutionId") != plan.get("rootExecutionId")
        or claim.get("carrier") != carrier
        or claim.get("executionId") != execution_id
        or claim.get("planDigest") != plan.get("planDigest")
        or claim.get("campaignRunId") != distributed.get("campaignRunId")
        or claim.get("campaignGeneration")
        != distributed.get("campaignGeneration")
        or claim.get("campaignFencingToken")
        != distributed.get("campaignFencingToken")
        or claim.get("status") != expected_status
        or claim.get("phase") != "completed"
        or not isinstance(claim.get("returnCode"), int)
        or not str(claim.get("finishedAt") or "").strip()
        or (
            expected_return is not None
            and (claim.get("returnCode") != expected_return or claim.get("error") is not None)
        )
        or (
            expected_return is None
            and (
                int(claim["returnCode"]) == 0
                or not str(claim.get("error") or "").strip()
            )
        )
    ):
        raise typed(
            "CAMPAIGN_NOT_TERMINAL_FAILED",
            f"{carrier} claim is not the expected mixed terminal outcome",
        )
    _dead_process(claim.get("pid"), carrier=carrier, label="pid")
    pgid = claim.get("pgid")
    if (
        isinstance(pgid, bool)
        or not isinstance(pgid, int)
        or pgid < 2
        or _process_group_alive(pgid)
    ):
        raise typed(
            "CAMPAIGN_NOT_TERMINAL_FAILED",
            f"{carrier} claim pgid is invalid or still live",
        )
    root = _execution_root(
        claim, execution_id, output_root=output_root, carrier=carrier
    )
    return claim, root, file_binding(
        path, output_root=output_root, label=f"{carrier} terminal claim"
    )


def _finalized_lane(
    campaign: Path,
    plan: Mapping[str, Any],
    report: Mapping[str, Any],
    runtime: Mapping[str, Any],
    submissions: Mapping[str, Mapping[str, Any]],
    carrier: str,
    *,
    roots: CampaignReleaseRoots,
) -> dict[str, Any]:
    execution_id = str(submissions[carrier]["executionId"])
    claim, execution_root, claim_binding = _terminal_claim(
        campaign,
        plan,
        carrier,
        execution_id,
        output_root=roots.output_root,
        finalized=True,
    )
    lane = report["lanes"].get(carrier)
    if (
        not isinstance(lane, Mapping)
        or lane.get("executionId") != execution_id
        or lane.get("status") != "finalized"
        or lane.get("phase") != "publish"
        or lane.get("reviewReturnCode") != 0
        or lane.get("publishReturnCode") != 0
        or lane.get("cleanupStatus") != "cleaned"
        or lane.get("qualifiedCount") != 1
        or lane.get("finalizedCount") != 1
        or lane.get("approvedQuota") != 1
        or lane.get("shortfallCount") != 0
        or lane.get("error") is not None
        or lane.get("sourceCapsuleRef") != claim.get("capsuleRef")
    ):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} report lane is not one exact finalized closure",
        )
    try:
        selection = validate_lane_publish(
            str(plan["rootExecutionId"]),
            carrier,
            plan,
            submissions[carrier],
            runtime,
            roots=roots,
        )
    except (CampaignReleaseError, FileNotFoundError, TypeError, ValueError) as exc:
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} finalized publish binding is invalid: {exc}",
        ) from exc
    publish_path = execution_root / "publish_ref.json"
    publish = read_json(publish_path)
    if not isinstance(publish, Mapping):
        raise typed("EXECUTION_EVIDENCE_INVALID", f"{carrier} publish_ref is invalid")
    receipt_path = campaign / "receipts" / f"{carrier}-publish.json"
    return {
        "carrier": carrier,
        "executionId": execution_id,
        "executionRootRef": execution_root.relative_to(roots.output_root).as_posix(),
        "executionRootExists": True,
        "terminalStatus": "finalized",
        "claim": claim_binding,
        "reportStatus": "finalized",
        "observedFinalizedCount": 1,
        "publishReceipt": file_binding(
            receipt_path,
            output_root=roots.output_root,
            label=f"{carrier} publish receipt",
        ),
        "publishRef": file_binding(
            publish_path,
            output_root=roots.output_root,
            label=f"{carrier} publish ref",
        ),
        "canonicalManifests": canonical_manifests(
            publish,
            carrier=carrier,
            execution_id=execution_id,
            source_digest=submissions[carrier]["sourceDigest"],
            publish_root=roots.publish_root,
        ),
        "publishSelectionFinalizedCount": selection["finalizedCount"],
        "evidenceDisposition": "preserved_unadopted",
        "excludedFromRetryRelease": True,
        "eligibleForRelease": False,
    }


def _failed_lane(
    campaign: Path,
    plan: Mapping[str, Any],
    report: Mapping[str, Any],
    submissions: Mapping[str, Mapping[str, Any]],
    carrier: str,
    *,
    output_root: Path,
) -> dict[str, Any]:
    execution_id = str(submissions[carrier]["executionId"])
    _claim, execution_root, claim_binding = _terminal_claim(
        campaign,
        plan,
        carrier,
        execution_id,
        output_root=output_root,
        finalized=False,
    )
    lane = report["lanes"].get(carrier)
    if (
        not isinstance(lane, Mapping)
        or lane.get("executionId") != execution_id
        or lane.get("status") != "blocked"
        or lane.get("phase") != "submission"
        or lane.get("reviewReturnCode") is not None
        or not isinstance(lane.get("publishReturnCode"), int)
        or int(lane["publishReturnCode"]) == 0
        or lane.get("cleanupStatus") != "cleaned"
        or lane.get("qualifiedCount") not in {None, 0}
        or lane.get("finalizedCount") not in {None, 0}
        or not str(lane.get("error") or "").strip()
    ):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} report lane is not one exact failed submission closure",
        )
    receipt_root = campaign / "receipts"
    forbidden = (
        receipt_root / f"{carrier}-review.json",
        receipt_root / f"{carrier}-publish.json",
        execution_root / "publish_ref.json",
    )
    if any(path.exists() or path.is_symlink() for path in forbidden):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"failed {carrier} unexpectedly has review or publish evidence",
        )
    transactions = execution_root / "evidence/object-transactions"
    if transactions.exists() and any(transactions.rglob("*")):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"failed {carrier} unexpectedly has object transaction evidence",
        )
    return {
        "carrier": carrier,
        "executionId": execution_id,
        "executionRootRef": execution_root.relative_to(output_root).as_posix(),
        "executionRootExists": True,
        "terminalStatus": "failed",
        "claim": claim_binding,
        "reportStatus": "blocked",
        "observedFinalizedCount": 0,
        "publishReceiptPresent": False,
        "publishRefPresent": False,
        "objectTransactionEvidencePresent": False,
        "evidenceDisposition": "failed_unpublished",
        "excludedFromRetryRelease": True,
        "eligibleForRelease": False,
    }


def _assert_no_release_or_adoption(
    campaign: Path,
    execution_ids: Mapping[str, str],
    *,
    output_root: Path,
) -> None:
    selections = campaign / "release_selections"
    if selections.exists() and any(selections.iterdir()):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "mixed terminal campaign already has release selection evidence",
        )
    for execution_id in execution_ids.values():
        adoption = (
            output_root
            / "data/tasks"
            / execution_id
            / "0.plan/reviewed_closure_adoption.json"
        )
        if adoption.exists() or adoption.is_symlink():
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                "mixed terminal campaign already has adoption evidence",
            )


def mixed_finalized_partial_terminal_evidence(
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    original_source_identity: Mapping[str, Any],
    *,
    output_root: Path,
    publish_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Bind preserved finalized objects without adopting or releasing them."""

    campaign, plan, report, runtime, failed_carrier = _campaign_documents(
        root_execution_id,
        submissions,
        original_source_identity,
        output_root=output_root,
    )
    execution_ids = {
        carrier: str(submissions[carrier]["executionId"])
        for carrier in plan["executionIds"]
    }
    _assert_no_release_or_adoption(
        campaign, execution_ids, output_root=output_root
    )
    roots = CampaignReleaseRoots(
        output_root=output_root.resolve(),
        campaigns_root=campaigns_root(output_root).resolve(),
        tasks_root=(output_root / "data/tasks").resolve(),
        publish_root=(publish_root or paths.PUBLISH_ROOT).resolve(),
        release_root=(output_root / "data/releases").resolve(),
    )
    lanes: list[dict[str, Any]] = []
    claims: dict[str, dict[str, str]] = {}
    for carrier in plan["executionIds"]:
        row = (
            _finalized_lane(
                campaign,
                plan,
                report,
                runtime,
                submissions,
                carrier,
                roots=roots,
            )
            if carrier != failed_carrier
            else _failed_lane(
                campaign,
                plan,
                report,
                submissions,
                carrier,
                output_root=output_root,
            )
        )
        lanes.append(row)
        claims[carrier] = row["claim"]
    campaign_evidence = {
        "plan": file_binding(
            campaign / "campaign_plan.json",
            output_root=output_root,
            label="mixed terminal campaign plan",
        ),
        "report": file_binding(
            campaign / "campaign_report.json",
            output_root=output_root,
            label="mixed terminal campaign report",
        ),
        "runtimeSnapshot": file_binding(
            campaign / "runtime/snapshot.json",
            output_root=output_root,
            label="mixed terminal campaign runtime",
        ),
        "claims": claims,
    }
    return (
        campaign_evidence,
        {
            "lanes": lanes,
            "observedFinalizedCount": sum(
                int(row.get("observedFinalizedCount") or 0) for row in lanes
            ),
            "immutableReleaseEvidencePresent": False,
            "reviewedClosureAdoptionPresent": False,
            "evidenceDisposition": "preserved_unadopted",
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
        },
        report,
    )


__all__ = ["mixed_finalized_partial_terminal_evidence"]
