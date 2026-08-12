"""M1000 cannot start until Alpha executes the exact M100 100-sample matrix.

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t2
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from content.execution.campaign.m100_alpha_acceptance import (
    M100AlphaAcceptanceError,
    _digest,
    _validate_app_uat,
)


def _receipt() -> tuple[dict[str, object], dict[str, object], str]:
    distribution = {"homepage": 25, "article": 25, "image": 40, "video": 10}
    cases = []
    evidence = []
    for carrier, count in distribution.items():
        for ordinal in range(1, count + 1):
            sample_id = f"m100-{carrier}-{ordinal:03d}"
            object_id = f"{carrier}-{ordinal:03d}"
            cases.append(
                {
                    "sampleId": sample_id,
                    "carrier": carrier,
                    "sourceReadback": (
                        "entityRefs"
                        if carrier == "homepage"
                        else f"feedQueries.typed_{carrier}"
                    ),
                    "objectId": object_id,
                    "ordinal": ordinal,
                }
            )
            evidence.append(
                {
                    "sampleId": sample_id,
                    "carrier": carrier,
                    "sourceObjectId": object_id,
                    "readObjectId": f"read-{object_id}",
                    "statusCode": 200,
                    "returnedObjectId": f"read-{object_id}",
                    "returnedContentType": "" if carrier == "homepage" else carrier,
                    "responseDigest": "sha256:" + f"{len(evidence) + 1:064x}",
                    "responseBytes": 64,
                }
            )
    plan = {
        "releaseId": "release-m100",
        "stratifiedSamples": {
            "milestone": "M100",
            "selection": "lexicographic_prefix_v1",
            "sampleCount": 100,
            "distribution": distribution,
            "cases": cases,
        },
    }
    plan_digest = _digest(plan)
    readiness = {
        "releaseId": "release-m100",
        "manifestDigest": "sha256:" + "1" * 64,
        "appUatEnvelopeDigest": "sha256:" + "2" * 64,
        "appUatEnvelope": {"releaseId": "release-m100"},
    }
    readiness_digest = _digest(readiness)
    sample_execution = {
        "milestone": "M100",
        "executedSampleCount": 100,
        "distribution": distribution,
        "appUatPlanDigest": plan_digest,
        "readinessReceiptDigest": readiness_digest,
        "samples": evidence,
    }
    sample_digest = _digest(sample_execution)
    receipt = {
        "schema": "quwoquan_ops.app_content_uat_receipt",
        "status": "passed",
        "targets": ["alpha-local"],
        "releaseId": readiness["releaseId"],
        "manifestDigest": readiness["manifestDigest"],
        "appUatEnvelopeDigest": readiness["appUatEnvelopeDigest"],
        "readinessReceiptDigests": [readiness_digest],
        "skipped": 0,
        "appUatPlan": plan,
        "appUatPlanDigest": plan_digest,
        "preflights": [
            {
                "target": "alpha-local",
                "environment": "alpha",
                "status": "passed",
                "exitCode": 0,
                "launchPolicy": "test_live",
                "contentBindingState": "bound",
                "releaseId": readiness["releaseId"],
                "manifestDigest": readiness["manifestDigest"],
                "readinessReceiptDigest": readiness_digest,
                "appUatEnvelope": readiness["appUatEnvelope"],
                "appUatPlan": plan,
                "appUatPlanDigest": plan_digest,
            }
        ],
        "runtimeBindings": {
            "alpha-local": {
                "environment": "alpha",
                "contentBindingState": "bound",
                "releaseId": readiness["releaseId"],
                "manifestDigest": readiness["manifestDigest"],
                "readinessPhase": "research",
            }
        },
        "runs": [
            {
                "suite": "release-bound-search-and-video-page",
                "exitCode": 0,
                "executedSampleCount": 100,
                "sampleExecution": sample_execution,
                "sampleExecutionDigest": sample_digest,
            }
        ],
        "executed": 1,
        "executedSamples": 100,
        "sampleExecutionDigests": [sample_digest],
    }
    return receipt, readiness, readiness_digest


def test_m100_alpha_acceptance__requires_exact_executed_samples__local_contract() -> None:
    receipt, readiness, readiness_digest = _receipt()

    _validate_app_uat(
        receipt,
        readiness=readiness,
        readiness_digest=readiness_digest,
    )


def test_m100_alpha_acceptance__plan_copy_without_reads_is_blocked__local_contract() -> None:
    receipt, readiness, readiness_digest = _receipt()
    invalid = deepcopy(receipt)
    invalid["executedSamples"] = 0
    invalid["runs"][0]["sampleExecution"] = {}

    with pytest.raises(M100AlphaAcceptanceError, match="exactly 100 executed"):
        _validate_app_uat(
            invalid,
            readiness=readiness,
            readiness_digest=readiness_digest,
        )
