"""Build the single canonical subprocess command for a campaign lane."""
from __future__ import annotations

from typing import Any


def audited_recovery_kwargs(
    recover_stage: str | None,
    recovery_reason: str | None,
) -> dict[str, str]:
    if bool(recover_stage) != bool(recovery_reason):
        raise ValueError("recover_stage and recovery_reason must be provided together")
    if recover_stage is None or recovery_reason is None:
        return {}
    return {
        "recover_stage": recover_stage,
        "recovery_reason": recovery_reason,
    }


def lane_argv(
    submission: dict[str, Any],
    *,
    stage: str,
    recover_stage: str | None = None,
    recovery_reason: str | None = None,
) -> list[str]:
    recovery = audited_recovery_kwargs(recover_stage, recovery_reason)
    argv = [
        "task",
        "execute",
        "--execution-id",
        str(submission["executionId"]),
        "--campaign-root-execution-id",
        str(submission["rootExecutionId"]),
        "--family",
        str(submission["familyRef"]),
        "--region-ref",
        str(submission["regionRef"]),
        "--selector",
        str(submission["selector"]),
        "--quota",
        str(submission["quota"]),
        "--count",
        str(submission["count"]),
        "--capacity-calibration-receipt",
        str(
            submission["capacityCalibration"]["calibrationReceiptRef"]
        ),
        "--stage",
        stage,
        "--semantic-selection-id",
        str(submission["semanticSelectionId"]),
    ]
    retry_of = str(submission.get("retryOf") or "").strip()
    if retry_of:
        argv.extend(["--retry-of", retry_of])
    semantic_preflight = submission.get("semanticPreflightReceipt")
    if isinstance(semantic_preflight, dict):
        argv.extend(
            [
                "--semantic-preflight-receipt",
                str(semantic_preflight["receiptRef"]),
            ]
        )
    topic = str(submission.get("topic") or "").strip()
    if topic:
        argv.extend(["--topic", topic])
    for provider in submission.get("sourceProviders") or []:
        argv.extend(["--source-provider", str(provider)])
    for name in submission.get("targetNames") or []:
        argv.extend(["--target", str(name)])
    if recovery:
        argv.extend(
            [
                "--recover-stage",
                recovery["recover_stage"],
                "--recovery-reason",
                recovery["recovery_reason"],
            ]
        )
    pool = submission.get("scaleSourcePool")
    selection = submission.get("sourcePoolSelection")
    if isinstance(pool, dict) and isinstance(selection, dict):
        argv.extend(
            [
                "--scale-source-pool-id", str(pool["poolId"]),
                "--scale-source-pool-target-scale", str(pool["targetScale"]),
                "--scale-source-pool-plan-ref", str(pool["planRef"]),
                "--scale-source-pool-plan-digest", str(pool["planDigest"]),
                "--scale-source-pool-plan-file-sha256", str(pool["planFileSha256"]),
                "--source-pool-source-revision", str(pool["sourceRevision"]),
                "--source-pool-source-digest", str(pool["sourceDigest"]),
                "--source-pool-entity-catalog-digest", str(pool["entityCatalogDigest"]),
                "--source-pool-evidence-root-ref", str(submission["sourcePoolEvidenceRootRef"]),
                "--source-pool-carrier", str(selection["carrier"]),
                "--source-pool-selection-digest", str(selection["selectionDigest"]),
            ]
        )
        for candidate_id in selection["candidateIds"]:
            argv.extend(["--source-pool-candidate-id", str(candidate_id)])
    return argv


__all__ = ["audited_recovery_kwargs", "lane_argv"]
