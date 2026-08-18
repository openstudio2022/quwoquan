"""Evidence contract for a terminal campaign with one applied article publish."""

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
from content.execution.campaign.submission_reconciliation_contract import (
    campaigns_root,
    canonical_digest,
    file_digest,
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
            "post-publish reconciliation requires plan/report/runtime objects",
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
        raise typed("IDENTITY_DRIFT", "post-publish campaign plan identity drifted")
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
        or not isinstance(report.get("lanes"), Mapping)
        or set(report["lanes"]) != set(active_carriers)
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign report is not one blocked post-publish terminal boundary",
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
        or not str(runtime.get("finishedAt") or "").strip()
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign runtime is not the bound frozen capsule snapshot",
        )
    return campaign, plan, report, runtime


def _terminal_lane_evidence(
    campaign: Path,
    plan: Mapping[str, Any],
    report: Mapping[str, Any],
    submissions: Mapping[str, Mapping[str, Any]],
    *,
    output_root: Path,
) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    distributed = plan["distributedRun"]
    report_lanes = report["lanes"]
    claim_bindings: dict[str, dict[str, str]] = {}
    execution_rows: list[dict[str, Any]] = []
    capsule_ref: str | None = None
    for carrier in plan["executionIds"]:
        execution_id = str(submissions[carrier]["executionId"])
        claim_path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(claim_path)
        lane = report_lanes.get(carrier)
        execution_root = output_root / "data/tasks" / execution_id
        if (
            not isinstance(claim, Mapping)
            or not isinstance(lane, Mapping)
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
            or lane.get("executionId") != execution_id
            or lane.get("status") != "blocked"
            or lane.get("phase") not in {"review", "submission"}
            or lane.get("cleanupStatus") != "cleaned"
            or not str(lane.get("error") or "").strip()
            or lane.get("finalizedCount") not in {None, 0}
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} is not one terminal non-finalized lane",
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
        try:
            same_root = (
                Path(str(claim.get("executionRoot") or "")).resolve()
                == execution_root.resolve()
            )
        except (OSError, RuntimeError):
            same_root = False
        if (
            not same_root
            or execution_root.is_symlink()
            or not execution_root.is_dir()
        ):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} execution root is missing or identity-drifted",
            )
        observed_capsule = str(claim.get("capsuleRef") or "")
        if not observed_capsule or (
            capsule_ref is not None and observed_capsule != capsule_ref
        ):
            raise typed(
                "CAMPAIGN_EVIDENCE_INVALID",
                "terminal executions do not share one frozen capsule",
            )
        capsule_ref = observed_capsule
        claim_bindings[carrier] = file_binding(
            claim_path, output_root=output_root, label=f"{carrier} terminal claim"
        )
        execution_rows.append(
            {
                "carrier": carrier,
                "executionId": execution_id,
                "executionRootRef": execution_root.relative_to(output_root).as_posix(),
                "executionRootExists": True,
            }
        )
    return claim_bindings, execution_rows


def _one_file(root: Path, pattern: str, *, label: str) -> Path:
    matches = sorted(path for path in root.glob(pattern) if path.is_file())
    if len(matches) != 1:
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            f"{label} requires exactly one file, observed={len(matches)}",
        )
    return matches[0]


def _canonical_manifest(
    object_ref: str,
    *,
    execution_id: str,
    publish_root: Path,
) -> tuple[str, str]:
    relative = Path(object_ref)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise typed("EXECUTION_EVIDENCE_INVALID", "article objectRef is unsafe")
    manifest_path = publish_root / "posts" / relative / "manifest.json"
    try:
        manifest_path.resolve().relative_to(publish_root.resolve())
    except ValueError as exc:
        raise typed("EXECUTION_EVIDENCE_INVALID", "article objectRef escaped publish") from exc
    manifest = read_json(manifest_path)
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema") != "quwoquan_data.post_object"
        or manifest.get("executionId") != execution_id
        or manifest.get("carrier") != "article"
    ):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "canonical article manifest is missing or execution-drifted",
        )
    return manifest_path.relative_to(publish_root).as_posix(), file_digest(manifest_path)


def _article_partial_publish(
    execution_id: str,
    report_lane: Mapping[str, Any],
    *,
    output_root: Path,
    publish_root: Path,
) -> dict[str, Any]:
    execution_root = output_root / "data/tasks" / execution_id
    state_path = execution_root / "_shared/execution_state.json"
    state = read_json(state_path)
    publish_report_path = _one_file(
        execution_root / "evidence/reliabletask/publish",
        "*/report.json",
        label="article publish report",
    )
    publish_report = read_json(publish_report_path)
    publish_ref_path = execution_root / "publish_ref.json"
    publish_ref = read_json(publish_ref_path)
    package_path = _one_file(
        execution_root / "evidence/object-transactions",
        "*/object_transaction_package.json",
        label="applied article object transaction",
    )
    package = read_json(package_path)
    if not all(
        isinstance(row, Mapping)
        for row in (state, publish_report, publish_ref, package)
    ):
        raise typed("EXECUTION_EVIDENCE_INVALID", "article publish evidence is invalid")
    target = package.get("target")
    transaction_id = str(package.get("transactionId") or "")
    object_ref = str(target.get("objectRef") or "") if isinstance(target, Mapping) else ""
    transaction_root = output_root / "data/local/workspace/object-transactions" / transaction_id
    audit_path = transaction_root / "audit_report.json"
    apply_path = transaction_root / "apply_report.json"
    completion_path = transaction_root / "apply_completion.json"
    pointer_path = transaction_root / "pointer.json"
    audit = read_json(audit_path)
    applied = read_json(apply_path)
    completion = read_json(completion_path)
    pointer = read_json(pointer_path)
    if not all(isinstance(row, Mapping) for row in (audit, applied, completion, pointer)):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "article transaction apply journal is incomplete",
        )
    published_refs = publish_ref.get("publishedRefs")
    throughput = state.get("throughput")
    after = audit.get("afterCanonical")
    if (
        package.get("schema") != "quwoquan_data.object_transaction_package"
        or package.get("executionId") != execution_id
        or not isinstance(target, Mapping)
        or target.get("objectKind") != "posts"
        or not transaction_id
        or not object_ref
        or audit.get("transactionId") != transaction_id
        or audit.get("executionId") != execution_id
        or audit.get("objectRef") != object_ref
        or audit.get("objectClosureDigest") != package.get("objectClosureDigest")
        or audit.get("packageSha256") != file_digest(package_path)
        or not isinstance(after, Mapping)
        or applied.get("schema") != "quwoquan_data.object_transaction_apply"
        or applied.get("status") != "applied"
        or applied.get("transactionId") != transaction_id
        or applied.get("executionId") != execution_id
        or applied.get("objectRef") != object_ref
        or applied.get("objectClosureDigest") != package.get("objectClosureDigest")
        or applied.get("afterMerkle") != after.get("merkleRoot")
        or completion.get("transactionId") != transaction_id
        or completion.get("afterMerkle") != applied.get("afterMerkle")
        or completion.get("fenceToken") != applied.get("fenceToken")
        or pointer.get("transactionId") != transaction_id
        or pointer.get("executionId") != execution_id
        or pointer.get("state") != "applied"
        or pointer.get("afterMerkle") != applied.get("afterMerkle")
        or pointer.get("activeMerkle") != applied.get("afterMerkle")
        or pointer.get("fenceToken") != applied.get("fenceToken")
        or publish_report.get("executionId") != execution_id
        or publish_report.get("stage") != "publish"
        or publish_report.get("passed") is not True
        or publish_report.get("objectTransactionResultCount") != 1
        or publish_report.get("researchAcceptedCount") != 1
        or publish_report.get("finalizedObjectCount") != 0
        or publish_report.get("duplicatePublishCount") != 0
        or publish_report.get("missingObjectCount") != 0
        or report_lane.get("qualifiedCount") != 1
        or report_lane.get("finalizedCount") != 0
        or not isinstance(report_lane.get("publishReturnCode"), int)
        or int(report_lane["publishReturnCode"]) == 0
        or state.get("executionId") != execution_id
        or state.get("status") != "manual_required"
        or "publish" not in (state.get("completed") or [])
        or not isinstance(throughput, Mapping)
        or throughput.get("objectTransactionResultCount") != 1
        or throughput.get("researchAcceptedCount") != 1
        or throughput.get("finalizedObjectCount") != 0
        or not state.get("completionGateIssues")
        or publish_ref.get("executionId") != execution_id
        or not isinstance(published_refs, Mapping)
        or published_refs.get("posts") != [object_ref]
    ):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "article evidence does not prove one applied non-finalized publish",
        )
    canonical_ref, canonical_sha = _canonical_manifest(
        object_ref,
        execution_id=execution_id,
        publish_root=publish_root,
    )
    return {
        "carrier": "article",
        "executionId": execution_id,
        "executionState": file_binding(
            state_path, output_root=output_root, label="article execution state"
        ),
        "publishReport": file_binding(
            publish_report_path,
            output_root=output_root,
            label="article publish report",
        ),
        "publishRef": file_binding(
            publish_ref_path, output_root=output_root, label="article publish ref"
        ),
        "transactionId": transaction_id,
        "objectRef": object_ref,
        "objectTransactionPackage": file_binding(
            package_path,
            output_root=output_root,
            label="article object transaction package",
        ),
        "auditReport": file_binding(
            audit_path, output_root=output_root, label="article transaction audit"
        ),
        "applyReport": file_binding(
            apply_path, output_root=output_root, label="article transaction apply"
        ),
        "applyCompletion": file_binding(
            completion_path,
            output_root=output_root,
            label="article transaction completion",
        ),
        "pointer": file_binding(
            pointer_path, output_root=output_root, label="article transaction pointer"
        ),
        "canonicalManifestRef": canonical_ref,
        "canonicalManifestSha256": canonical_sha,
        "afterMerkle": applied["afterMerkle"],
        "researchAcceptedCount": 1,
        "finalizedObjectCount": 0,
    }


def _assert_no_release_or_adoption(
    campaign: Path,
    execution_ids: Mapping[str, str],
    *,
    output_root: Path,
) -> None:
    release_selections = campaign / "release_selections"
    if release_selections.exists() and any(release_selections.iterdir()):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "post-publish partial campaign already has release selection evidence",
        )
    receipts = campaign / "receipts"
    if receipts.exists() and any(receipts.glob("*-publish.json")):
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "post-publish partial campaign already has finalized lane receipt",
        )
    for execution_id in execution_ids.values():
        if (
            output_root
            / "data/tasks"
            / execution_id
            / "0.plan/reviewed_closure_adoption.json"
        ).exists():
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                "post-publish partial campaign already has adoption evidence",
            )


def post_publish_partial_terminal_evidence(
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    original_source_identity: Mapping[str, Any],
    *,
    output_root: Path,
    publish_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Bind an applied article transaction without claiming finalization/release."""

    campaign, plan, report, _runtime = _campaign_documents(
        root_execution_id,
        submissions,
        original_source_identity,
        output_root=output_root,
    )
    claim_bindings, execution_rows = _terminal_lane_evidence(
        campaign,
        plan,
        report,
        submissions,
        output_root=output_root,
    )
    execution_ids = {
        carrier: str(submissions[carrier]["executionId"])
        for carrier in plan["executionIds"]
    }
    if "article" not in execution_ids:
        raise typed(
            "EXECUTION_EVIDENCE_INVALID",
            "post-publish partial requires an active article lane",
        )
    _assert_no_release_or_adoption(
        campaign, execution_ids, output_root=output_root
    )
    partial_publish = _article_partial_publish(
        execution_ids["article"],
        report["lanes"]["article"],
        output_root=output_root,
        publish_root=(publish_root or paths.PUBLISH_ROOT).resolve(),
    )
    campaign_evidence = {
        "plan": file_binding(
            campaign / "campaign_plan.json",
            output_root=output_root,
            label="post-publish campaign plan",
        ),
        "report": file_binding(
            campaign / "campaign_report.json",
            output_root=output_root,
            label="post-publish campaign report",
        ),
        "runtimeSnapshot": file_binding(
            campaign / "runtime/snapshot.json",
            output_root=output_root,
            label="post-publish campaign runtime",
        ),
        "claims": claim_bindings,
    }
    return (
        campaign_evidence,
        {
            "lanes": execution_rows,
            "partialPublish": partial_publish,
            "allLanesFinalizedCount": 0,
            "immutableReleaseEvidencePresent": False,
            "reviewedClosureAdoptionPresent": False,
            "evidenceDisposition": "preserved_unadopted",
            "excludedFromFinalized": True,
            "eligibleForRelease": False,
        },
        report,
    )


__all__ = ["post_publish_partial_terminal_evidence"]
