"""ReliableTask canonical publish-stage execution."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.io import read_json
from core.paths import OUTPUT_ROOT

from content.execution.queue.model import QueueJob
from content.execution.workspace import execution_root


def validate_pool_delivery_intent_for_job(job: QueueJob) -> dict[str, object]:
    """Validate the legacy ReliableTask routing envelope against one neutral intent."""

    from content.execution.closure.pool_delivery import (
        validate_pool_delivery_intent_document,
    )

    metadata = job.metadata_document()
    raw_ref = str(metadata.get("poolDeliveryIntentRef") or "").strip()
    expected_digest = str(metadata.get("poolDeliveryIntentDigest") or "").strip()
    if not raw_ref or not expected_digest:
        raise ValueError("ReliableTask publish job lacks pool delivery intent binding")
    root = execution_root(job.execution_id).resolve()
    path = (root / raw_ref).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("pool delivery intent ref escapes execution root") from exc
    raw_parts = Path(raw_ref).parts
    if any(
        (root / Path(*raw_parts[:index])).is_symlink()
        for index in range(1, len(raw_parts) + 1)
    ):
        raise ValueError("pool delivery intent ref cannot traverse symlinks")
    validated = validate_pool_delivery_intent_document(read_json(path), root=root)
    if validated.get("intentId") != expected_digest:
        raise ValueError("pool delivery intent digest binding mismatch")
    carrier = job.carrier.value if job.carrier is not None else ""
    if (
        validated["executionId"] != job.execution_id
        or validated["objectRef"] != job.ref
        or validated["carrier"] != carrier
        or job.content_object_dir != validated["contentObjectDir"]
        or metadata.get("sourceRevision") != validated["transactionInputDigest"]
    ):
        raise ValueError("pool delivery intent job routing drift")
    return validated


def _execute_publish(job: QueueJob) -> dict[str, object]:
    intent = validate_pool_delivery_intent_for_job(job)
    carrier = job.carrier.value if job.carrier else ""
    if carrier == "homepage":
        from content.execution.controller.publish import publish_homepage_object

        transaction = publish_homepage_object(
            job.execution_id,
            job.ref,
            pool_delivery_intent=intent,
        )
    else:
        from content.release.canonical.post_promotion import promote_post_object

        if not job.content_object_dir:
            raise ValueError(f"ReliableTask publish job 缺 contentObjectDir：{job.job_id}")
        transaction = promote_post_object(
            job.execution_id,
            job.content_object_dir,
            pool_delivery_intent=intent,
        )
    if transaction.get("transactionId") != intent["transactionId"]:
        raise ValueError("pool delivery transaction identity drift")
    from content.execution.queue.reliabletask.projection import (
        record_reliabletask_completion,
    )

    record_reliabletask_completion(
        job.execution_id,
        job.job_id,
        evidence_path=OUTPUT_ROOT / transaction["applyReportRef"],
        evidence_root=OUTPUT_ROOT,
    )
    return {
        "executionId": job.execution_id,
        "jobId": job.job_id,
        "canonicalObjectRef": transaction["canonicalObjectRef"],
        "canonicalObjectSha256": transaction["canonicalObjectSha256"],
        "objectTransactionId": transaction["transactionId"],
        "poolDeliveryIntentId": intent["intentId"],
        "resultEnvelopeRef": transaction["applyReportRef"],
        "acceptanceClass": "canonical_pool",
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
