"""ReliableTask canonical publish-stage execution."""
from __future__ import annotations

from datetime import datetime, timezone

from core.paths import OUTPUT_ROOT
from governance.coverage.distribution import load_content_distribution_policy

from content.execution.queue.model import QueueJob


def _execute_publish(job: QueueJob) -> dict[str, object]:
    from content.execution.closure.pool_delivery import (
        validate_pool_delivery_intent_for_job,
    )

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
    release_class = load_content_distribution_policy().release_class.value
    return {
        "executionId": job.execution_id,
        "jobId": job.job_id,
        "canonicalObjectRef": transaction["canonicalObjectRef"],
        "canonicalObjectSha256": transaction["canonicalObjectSha256"],
        "objectTransactionId": transaction["transactionId"],
        "poolDeliveryIntentId": intent["intentId"],
        "resultEnvelopeRef": transaction["applyReportRef"],
        "acceptanceClass": f"{release_class}_canonical",
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
