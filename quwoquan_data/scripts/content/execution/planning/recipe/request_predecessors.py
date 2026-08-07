"""Predecessor target resolution for recipe retry/execute."""
from __future__ import annotations

from pathlib import Path


def submission_only_predecessor_target_names(
    retry_of: str | None,
) -> tuple[str, ...] | None:
    if not retry_of:
        return None
    from content.execution.campaign.submission_reconciliation import (
        load_reconciled_predecessor_submission,
    )

    row = load_reconciled_predecessor_submission(retry_of)
    if row is None:
        return None
    targets = row.get("targetNames")
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(name, str) or not name.strip() for name in targets)
        or len(set(targets)) != len(targets)
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "reconciled predecessor targetNames are invalid"
        )
    return tuple(targets)


def terminal_campaign_predecessor_target_names(
    retry_of: str | None,
    *,
    output_root: Path | None = None,
) -> tuple[str, ...] | None:
    """Read targets from a fully evidenced blocked campaign terminal."""
    if not retry_of:
        return None
    from core import paths
    from core.io import read_json
    from content.execution.campaign.submission_reconciliation_contract import (
        campaigns_root,
        load_terminal_submission_documents,
        predecessor_campaign_root_execution_id,
    )
    from content.execution.identity import parse_execution_id

    resolved_output = (output_root or paths.OUTPUT_ROOT).resolve()
    root_id = predecessor_campaign_root_execution_id(retry_of)
    campaign = campaigns_root(resolved_output) / root_id
    plan_path = campaign / "campaign_plan.json"
    report_path = campaign / "campaign_report.json"
    snapshot_path = campaign / "runtime/snapshot.json"
    if not report_path.is_file() and not snapshot_path.is_file():
        return None
    if not report_path.is_file() or not snapshot_path.is_file():
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal campaign evidence is incomplete"
        )
    report = read_json(report_path)
    snapshot = read_json(snapshot_path)
    if (
        not isinstance(report, dict)
        or report.get("schema") != "quwoquan_data.content_campaign_report"
        or report.get("rootExecutionId") != root_id
        or report.get("status") != "blocked"
        or not isinstance(snapshot, dict)
        or snapshot.get("schema")
        != "quwoquan_data.content_campaign_runtime_snapshot"
        or snapshot.get("rootExecutionId") != root_id
        or snapshot.get("status") != "blocked"
        or not str(snapshot.get("finishedAt") or "").strip()
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal campaign evidence is invalid"
        )
    from content.execution.campaign.plan import sha256_payload
    from content.execution.campaign.process import CAMPAIGN_CARRIERS

    submissions = load_terminal_submission_documents(
        root_id,
        output_root=resolved_output,
    )
    if set(submissions) != set(CAMPAIGN_CARRIERS):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal submissions are incomplete"
        )
    lanes = report.get("lanes")
    snapshot_lanes = snapshot.get("lanes")
    if (
        not isinstance(lanes, dict)
        or set(lanes) != set(CAMPAIGN_CARRIERS)
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal lane evidence is incomplete"
        )

    phases = (report.get("phase"), snapshot.get("phase"))
    if phases == ("freeze", "freeze"):
        if plan_path.exists() or any(
            not isinstance(row, dict)
            or row.get("status") != "pending"
            or row.get("phase") != "submission"
            or row.get("executionRootRef") is not None
            for row in lanes.values()
        ):
            raise SystemExit(
                f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                "predecessor created lane evidence before freeze failure"
            )
    elif phases == ("completed", "completed"):
        if (
            not plan_path.is_file()
            or not isinstance(snapshot_lanes, dict)
            or set(snapshot_lanes) != set(CAMPAIGN_CARRIERS)
        ):
            raise SystemExit(
                f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                "predecessor completed campaign plan is missing"
            )
        plan = read_json(plan_path)
        stable_plan = (
            {key: value for key, value in plan.items() if key != "planDigest"}
            if isinstance(plan, dict)
            else {}
        )
        execution_ids = {
            carrier: str(submissions[carrier].get("executionId") or "")
            for carrier in CAMPAIGN_CARRIERS
        }
        submission_digests = {
            carrier: str(submissions[carrier].get("requestDigest") or "")
            for carrier in CAMPAIGN_CARRIERS
        }
        plan_digest = str(plan.get("planDigest") or "") if isinstance(plan, dict) else ""
        representative = submissions["homepage"]
        source_document = representative.get("sourceDigest")
        if (
            not isinstance(plan, dict)
            or plan.get("schema") != "quwoquan_data.content_campaign_plan"
            or plan.get("rootExecutionId") != root_id
            or plan_digest != sha256_payload(stable_plan)
            or report.get("planDigest") != plan_digest
            or snapshot.get("planDigest") != plan_digest
            or plan.get("executionIds") != execution_ids
            or plan.get("submissionDigests") != submission_digests
            or not isinstance(source_document, dict)
            or plan.get("sourceDigest") != source_document.get("digest")
            or plan.get("sourceRevision") != representative.get("sourceRevision")
            or plan.get("entityCatalogDigest")
            != representative.get("entityCatalogDigest")
        ):
            raise SystemExit(
                f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                "predecessor completed campaign plan evidence is invalid"
            )
        for carrier in CAMPAIGN_CARRIERS:
            execution_id = execution_ids[carrier]
            report_lane = lanes[carrier]
            snapshot_lane = snapshot_lanes[carrier]
            execution_ref = f"data/tasks/{execution_id}"
            execution_root = (resolved_output / execution_ref).resolve()
            if (
                not isinstance(report_lane, dict)
                or report_lane.get("executionId") != execution_id
                or report_lane.get("status") != "blocked"
                or report_lane.get("phase") != "review"
                or not isinstance(report_lane.get("reviewReturnCode"), int)
                or report_lane.get("reviewReturnCode") == 0
                or report_lane.get("publishReturnCode") is not None
                or report_lane.get("executionRootRef") != execution_ref
                or report_lane.get("cleanupStatus") != "cleaned"
                or not str(report_lane.get("error") or "").strip()
                or not isinstance(snapshot_lane, dict)
                or snapshot_lane.get("executionId") != execution_id
                or snapshot_lane.get("status") != "failed"
                or snapshot_lane.get("phase") != "review-only"
                or snapshot_lane.get("returnCode")
                != report_lane.get("reviewReturnCode")
                or resolved_output not in execution_root.parents
                or not execution_root.is_dir()
                or not (
                    execution_root
                    / "0.plan/campaign_external_input_envelope.json"
                ).is_file()
            ):
                raise SystemExit(
                    f"[task execute] GATE_BLOCK retryOf={retry_of}: "
                    f"predecessor completed {carrier} review evidence is invalid"
                )
    else:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal campaign phase is invalid"
        )

    target_sets = {
        tuple(str(name) for name in submissions[carrier].get("targetNames") or [])
        for carrier in CAMPAIGN_CARRIERS
    }
    if len(target_sets) != 1:
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal targetNames drift across lanes"
        )
    carrier = parse_execution_id(retry_of).content_type.value
    row = submissions.get(carrier)
    targets = row.get("targetNames") if isinstance(row, dict) else None
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(name, str) or not name.strip() for name in targets)
        or len(set(targets)) != len(targets)
    ):
        raise SystemExit(
            f"[task execute] GATE_BLOCK retryOf={retry_of}: "
            "predecessor terminal targetNames are invalid"
        )
    return tuple(targets)


