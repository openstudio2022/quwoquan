"""Evidence contract for a terminal campaign with no finalized objects."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

from content.execution.campaign.failed_execution_reconciliation_claimed import (
    _dead_process,
    _process_group_alive,
)
from content.execution.campaign.failed_execution_reconciliation_common import (
    file_binding,
)
from content.execution.campaign.submission_reconciliation_contract import (
    campaigns_root,
    canonical_digest,
    frozen_plan_workload,
    frozen_submission_workload,
    typed,
)


def _campaign_documents(
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    original: Mapping[str, Any],
    *,
    output_root: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    campaign = campaigns_root(output_root) / root_execution_id
    plan = read_json(campaign / "campaign_plan.json")
    report = read_json(campaign / "campaign_report.json")
    runtime = read_json(campaign / "runtime/snapshot.json")
    if not all(isinstance(row, dict) for row in (plan, report, runtime)):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "terminal unpublished reconciliation requires plan/report/runtime objects",
        )
    stable_plan = {key: value for key, value in plan.items() if key != "planDigest"}
    distributed = plan.get("distributedRun")
    source_digest = (original.get("sourceDigest") or {}).get("digest")
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
        raise typed("IDENTITY_DRIFT", "terminal unpublished plan identity drifted")
    lanes = report.get("lanes")
    if (
        report.get("rootExecutionId") != root_execution_id
        or report.get("status") != "blocked"
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
        or not str(report.get("failure") or "").strip()
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign report is not one terminal unpublished boundary",
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
            "campaign runtime is not the bound frozen terminal snapshot",
        )
    return campaign, plan, report, runtime


def _review_receipt(
    campaign: Path,
    root_execution_id: str,
    execution_id: str,
    carrier: str,
    *,
    output_root: Path,
) -> tuple[Mapping[str, Any] | None, dict[str, str] | None]:
    path = campaign / "receipts" / f"{carrier}-review.json"
    if not path.exists() and not path.is_symlink():
        return None, None
    receipt = read_json(path)
    try:
        assert_valid(
            receipt,
            "execution",
            "content_campaign_lane_receipt",
            label=f"terminal unpublished review receipt:{carrier}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed("EXECUTION_EVIDENCE_INVALID", str(exc)) from exc
    if (
        not isinstance(receipt, Mapping)
        or receipt.get("rootExecutionId") != root_execution_id
        or receipt.get("executionId") != execution_id
        or receipt.get("carrier") != carrier
        or receipt.get("phase") != "review"
        or receipt.get("status") not in {"qualified", "partial", "blocked"}
        or receipt.get("finalizedCount") != 0
        or receipt.get("selectedCount")
        != int(receipt.get("qualifiedCount") or 0)
        + int(receipt.get("discardedCount") or 0)
        or receipt.get("discardedCount") != len(receipt.get("discards") or [])
        or receipt.get("shortfallCount")
        != max(
            0,
            int(receipt.get("approvedQuota") or 0)
            - int(receipt.get("qualifiedCount") or 0),
        )
    ):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} review receipt is not one exact non-finalized review",
        )
    qualified = int(receipt["qualifiedCount"])
    quota = int(receipt["approvedQuota"])
    expected_status = "qualified" if qualified >= quota else (
        "partial" if qualified > 0 else "blocked"
    )
    if receipt.get("status") != expected_status:
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} review status/count drifted",
        )
    return receipt, file_binding(
        path,
        output_root=output_root,
        label=f"{carrier} terminal unpublished review receipt",
    )


def _prepared_object_transactions(
    execution_root: Path,
    execution_id: str,
    carrier: str,
    *,
    output_root: Path,
) -> list[dict[str, Any]]:
    root = execution_root / "evidence/object-transactions"
    if not root.exists() and not root.is_symlink():
        return []
    if root.is_symlink() or not root.is_dir():
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} object transaction root is unsafe",
        )
    rows: list[dict[str, Any]] = []
    for transaction_root in sorted(root.iterdir()):
        package_path = transaction_root / "object_transaction_package.json"
        manifest_path = transaction_root / "object/manifest.json"
        if (
            transaction_root.is_symlink()
            or not transaction_root.is_dir()
            or any(path.is_symlink() for path in transaction_root.rglob("*"))
            or not package_path.is_file()
            or not manifest_path.is_file()
            or any(
                path.name in {"apply_report.json", "publish_ref.json"}
                for path in transaction_root.rglob("*")
            )
        ):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} object transaction is not prepared-only evidence",
            )
        package = read_json(package_path)
        manifest = read_json(manifest_path)
        try:
            assert_valid(
                package,
                "release",
                "object_transaction_package",
                label=f"{carrier} prepared object transaction",
            )
        except (FileNotFoundError, TypeError, ValueError) as exc:
            raise typed("EXECUTION_EVIDENCE_INVALID", str(exc)) from exc
        target = package.get("target") if isinstance(package, Mapping) else None
        expected_object_ref = (
            f"{manifest.get('contentType')}/{manifest.get('publishAngle')}/"
            f"{manifest.get('publishTitle')}/{manifest.get('publishSeq')}"
            if isinstance(manifest, Mapping)
            else ""
        )
        if (
            not isinstance(package, Mapping)
            or package.get("executionId") != execution_id
            or package.get("transactionId") != transaction_root.name
            or not isinstance(target, Mapping)
            or target.get("objectKind") != "posts"
            or target.get("objectSchema") != "quwoquan_data.post_object"
            or target.get("packageObjectRef") != "object"
            or target.get("objectRef") != expected_object_ref
            or not isinstance(manifest, Mapping)
            or manifest.get("executionId") != execution_id
            or manifest.get("schema") != "quwoquan_data.post_object"
        ):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} prepared object transaction identity drifted",
            )
        rows.append(
            {
                "transactionId": transaction_root.name,
                "package": file_binding(
                    package_path,
                    output_root=output_root,
                    label=f"{carrier} prepared object transaction package",
                ),
                "objectManifest": file_binding(
                    manifest_path,
                    output_root=output_root,
                    label=f"{carrier} prepared object transaction manifest",
                ),
                "state": "prepared_unapplied",
            }
        )
    return rows


def _lane_evidence(
    campaign: Path,
    plan: Mapping[str, Any],
    report: Mapping[str, Any],
    submissions: Mapping[str, Mapping[str, Any]],
    carrier: str,
    *,
    output_root: Path,
) -> dict[str, Any]:
    execution_id = str(submissions[carrier]["executionId"])
    claim_path = campaign / "claims" / f"{carrier}.json"
    claim = read_json(claim_path)
    distributed = plan["distributedRun"]
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
        or claim.get("status") != "failed"
        or claim.get("phase") != "completed"
        or not isinstance(claim.get("returnCode"), int)
        or not str(claim.get("finishedAt") or "").strip()
        or not (
            int(claim["returnCode"]) != 0
            or str(claim.get("error") or "").strip()
        )
    ):
        raise typed(
            "CAMPAIGN_NOT_TERMINAL_FAILED",
            f"{carrier} claim is not terminal failed",
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
    execution_root = output_root / "data/tasks" / execution_id
    try:
        same_root = Path(str(claim.get("executionRoot") or "")).resolve() == (
            execution_root.resolve()
        )
    except (OSError, RuntimeError):
        same_root = False
    lane = report["lanes"].get(carrier)
    if (
        not same_root
        or execution_root.is_symlink()
        or not execution_root.is_dir()
        or not isinstance(lane, Mapping)
        or lane.get("executionId") != execution_id
        or lane.get("status") != "blocked"
        or lane.get("phase") not in {"submission", "review", "publish"}
        or lane.get("sourceCapsuleRef") != claim.get("capsuleRef")
        or lane.get("executionRootRef")
        != execution_root.relative_to(output_root).as_posix()
        or lane.get("cleanupStatus") != "cleaned"
        or lane.get("finalizedCount") not in {None, 0}
        or not str(lane.get("error") or "").strip()
        or (
            lane.get("publishReturnCode") is not None
            and (
                not isinstance(lane.get("publishReturnCode"), int)
                or int(lane["publishReturnCode"]) == 0
            )
        )
    ):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} report lane is not cleaned terminal unpublished",
        )
    review, review_binding = _review_receipt(
        campaign,
        str(plan["rootExecutionId"]),
        execution_id,
        carrier,
        output_root=output_root,
    )
    count_fields = (
        "approvedQuota",
        "qualifiedCount",
        "selectedCount",
        "discardedCount",
        "shortfallCount",
    )
    if review is not None:
        if (
            lane.get("reviewReturnCode") != 0
            or any(lane.get(key) != review.get(key) for key in count_fields)
            or (
                int(review["qualifiedCount"]) > 0
                and (
                    not isinstance(lane.get("publishReturnCode"), int)
                    or int(lane["publishReturnCode"]) == 0
                )
            )
        ):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} report/review receipt binding drifted",
            )
    elif (
        lane.get("reviewReturnCode") is not None
        and (
            not isinstance(lane.get("reviewReturnCode"), int)
            or int(lane["reviewReturnCode"]) == 0
        )
    ) or any(lane.get(key) not in {None, 0} for key in count_fields):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} reports review evidence that is absent",
        )
    forbidden = (
        campaign / "receipts" / f"{carrier}-publish.json",
        execution_root / "publish_ref.json",
        execution_root / "0.plan/reviewed_closure_adoption.json",
    )
    if any(path.exists() or path.is_symlink() for path in forbidden):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{carrier} unexpectedly has publish or adoption evidence",
        )
    prepared_transactions = _prepared_object_transactions(
        execution_root,
        execution_id,
        carrier,
        output_root=output_root,
    )
    qualified_count = int(review.get("qualifiedCount") or 0) if review else 0
    return {
        "carrier": carrier,
        "executionId": execution_id,
        "executionRootRef": execution_root.relative_to(output_root).as_posix(),
        "executionRootExists": True,
        "terminalStatus": "failed",
        "claim": file_binding(
            claim_path,
            output_root=output_root,
            label=f"{carrier} terminal unpublished claim",
        ),
        "reportStatus": "blocked",
        "reviewReceiptPresent": review_binding is not None,
        "reviewReceipt": review_binding,
        "reviewStatus": review.get("status") if review else None,
        "reviewQualifiedCount": qualified_count,
        "observedFinalizedCount": 0,
        "publishReceiptPresent": False,
        "publishRefPresent": False,
        "preparedObjectTransactions": prepared_transactions,
        "objectTransactionAppliedEvidencePresent": False,
        "evidenceDisposition": "failed_unpublished",
        "excludedFromRetryRelease": True,
        "eligibleForRelease": False,
    }


def _assert_no_release(
    campaign: Path,
    execution_ids: set[str],
    *,
    output_root: Path,
) -> None:
    receipts = campaign / "receipts"
    if receipts.exists() and any(receipts.glob("*-publish.json")):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "terminal unpublished campaign already has a publish receipt",
        )
    selections = campaign / "release_selections"
    if selections.exists() and any(selections.iterdir()):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "terminal unpublished campaign already has release selection evidence",
        )
    release_root = output_root / "data/releases"
    for header_path in sorted(release_root.glob("*/payload/release.json")):
        header = read_json(header_path)
        if not isinstance(header, Mapping):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"release header is unreadable while proving absence: {header_path}",
            )
        if execution_ids.intersection(str(item) for item in header.get("executionIds") or []):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                "terminal unpublished campaign execution already entered a release",
            )


def terminal_unpublished_source_drift_evidence(
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    original_source_identity: Mapping[str, Any],
    *,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Bind partial review qualification without publish/finalize/release credit."""

    campaign, plan, report, _runtime = _campaign_documents(
        root_execution_id,
        submissions,
        original_source_identity,
        output_root=output_root,
    )
    execution_ids = {
        str(submissions[carrier]["executionId"])
        for carrier in plan["executionIds"]
    }
    _assert_no_release(campaign, execution_ids, output_root=output_root)
    lanes = [
        _lane_evidence(
            campaign,
            plan,
            report,
            submissions,
            carrier,
            output_root=output_root,
        )
        for carrier in plan["executionIds"]
    ]
    qualified_lanes = sum(row["reviewQualifiedCount"] > 0 for row in lanes)
    prepared_transaction_count = sum(
        len(row["preparedObjectTransactions"]) for row in lanes
    )
    if qualified_lanes < 1:
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "terminal unpublished partial requires a review-qualified active lane",
        )
    campaign_evidence = {
        "plan": file_binding(
            campaign / "campaign_plan.json",
            output_root=output_root,
            label="terminal unpublished campaign plan",
        ),
        "report": file_binding(
            campaign / "campaign_report.json",
            output_root=output_root,
            label="terminal unpublished campaign report",
        ),
        "runtimeSnapshot": file_binding(
            campaign / "runtime/snapshot.json",
            output_root=output_root,
            label="terminal unpublished campaign runtime",
        ),
        "claims": {row["carrier"]: row["claim"] for row in lanes},
    }
    return (
        campaign_evidence,
        {
            "lanes": lanes,
            "observedFinalizedCount": 0,
            "reviewQualifiedLaneCount": qualified_lanes,
            "campaignPublishReceiptsPresent": False,
            "campaignPublishRefsPresent": False,
            "preparedObjectTransactionCount": prepared_transaction_count,
            "objectTransactionAppliedEvidencePresent": False,
            "immutableReleaseEvidencePresent": False,
            "reviewedClosureAdoptionPresent": False,
            "evidenceDisposition": "failed_unpublished",
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
        },
        report,
    )


__all__ = ["terminal_unpublished_source_drift_evidence"]
