# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""Predecessor binding for a `retryOf` that only closes a lane shortfall.

`REQ-001` requires the next sequence to declare `retryOf` per lane and to bind
the reconciliation receipt exactly, failing closed on byte drift; it also states
that `quota` is a cumulative milestone target rather than a publish permit, that
a `partial` lane must publish every qualified object, and that the shortfall is
written as typed evidence.  `GWT-001` repeats the `partial` terminal state, and
`REQ-004` requires milestone promotion to reach `shortfallCount=0`.

Together those make a narrower successor scope admissible only when the
predecessor lane really is terminal, unpublished and excluded from the retry
release: retrying a lane that was already eligible for release would re-credit
objects that are already counted.  Any other reconciliation reason keeps the
exact-scope binding.

The reconciliation loader is replaced with a typed double so the shortfall
admission predicate is exercised on its own; the double raises on any reference
it was not given.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from content.execution.campaign import submission_reconciliation
from content.execution.campaign.submission_envelope import (
    validate_predecessor_reconciliation,
)
from core.control_types import TargetSelector

CARRIER = "article"
RETRY_OF = "20260728--travel-article-workload-article-1--china--scale-001"
ROOT_ID = "20260728--travel-homepage-workload-homepage-1--china--scale-001"
SOURCE_REVISION = "sha256:" + "b" * 64
SOURCE = {"digest": "sha256:" + "a" * 64}
EXECUTION_BUNDLE = {"digest": "sha256:" + "e" * 64}
ENTITY_CATALOG_DIGEST = "sha256:" + "c" * 64
BINDING = {
    "predecessorRootExecutionId": ROOT_ID,
    "receiptRef": "data/local/workspace/reconciliation/receipt.json",
    "receiptDigest": "sha256:" + "d" * 64,
}
PREDECESSOR_QUOTA = 10
PREDECESSOR_COUNT = 40


def _request(*, quota: int, count: int, **overrides: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "family_ref": "content/travel/article/article",
        "region_ref": "china",
        "selector": TargetSelector.ALL,
        "quota": quota,
        "count": count,
        "topic": None,
        "target_names": (),
        "source_providers": (),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _predecessor_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "executionId": RETRY_OF,
        "familyRef": "content/travel/article/article",
        "regionRef": "china",
        "selector": TargetSelector.ALL.value,
        "quota": PREDECESSOR_QUOTA,
        "count": PREDECESSOR_COUNT,
        "topic": None,
        "targetNames": [],
        "sourceProviders": [],
    }
    row.update(overrides)
    return row


def _shortfall_lane(**overrides: Any) -> dict[str, Any]:
    lane = {
        "carrier": CARRIER,
        "executionId": RETRY_OF,
        "terminalStatus": "failed",
        "evidenceDisposition": "failed_unpublished",
        "excludedFromRetryRelease": True,
        "eligibleForRelease": False,
    }
    lane.update(overrides)
    return lane


def _shortfall_receipt(
    *,
    submission_overrides: dict[str, Any] | None = None,
    lane_overrides: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    receipt = {
        "rootExecutionId": ROOT_ID,
        "reason": "terminal_unpublished_retryable_shortfall",
        "retryPolicy": "active_workload_execution_with_retryOf",
        "receiptDigest": BINDING["receiptDigest"],
        "submissions": {CARRIER: _predecessor_row(**(submission_overrides or {}))},
        "executionEvidence": {
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
            "lanes": [_shortfall_lane(**(lane_overrides or {}))],
        },
    }
    receipt.update(overrides)
    return receipt


@pytest.fixture(name="bind_receipt")
def _bind_receipt(monkeypatch: pytest.MonkeyPatch):
    def bind(receipt: dict[str, Any]) -> None:
        def _load(
            reference: Any,
            *,
            output_root: Path | None = None,
        ) -> tuple[dict[str, Any], Path]:
            if dict(reference) != BINDING:
                raise AssertionError(
                    "reconciliation double received an unexpected reference: "
                    f"{dict(reference)}"
                )
            return receipt, Path(str(BINDING["receiptRef"]))

        monkeypatch.setattr(
            submission_reconciliation,
            "load_reconciliation_reference",
            _load,
        )

    return bind


def _validate(request: SimpleNamespace) -> None:
    validate_predecessor_reconciliation(
        BINDING,
        carrier=CARRIER,
        retry_of=RETRY_OF,
        request=request,
        source_revision=SOURCE_REVISION,
        source=SOURCE,
        execution_bundle=EXECUTION_BUNDLE,
        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
    )


def test_a_shortfall_retry_may_narrow_the_successor_scope(bind_receipt) -> None:
    """The retry only has to close the remaining milestone gap."""

    bind_receipt(_shortfall_receipt())

    _validate(_request(quota=3, count=12))


def test_a_shortfall_retry_may_reuse_the_full_predecessor_scope(
    bind_receipt,
) -> None:
    """Narrowing is permitted, not required."""

    bind_receipt(_shortfall_receipt())

    _validate(_request(quota=PREDECESSOR_QUOTA, count=PREDECESSOR_COUNT))


def test_a_shortfall_retry_may_not_widen_the_quota(bind_receipt) -> None:
    """A retry closes a gap; it never enlarges the frozen object floor."""

    bind_receipt(_shortfall_receipt())

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=PREDECESSOR_QUOTA + 1, count=PREDECESSOR_COUNT))


def test_a_shortfall_retry_may_not_widen_the_candidate_count(bind_receipt) -> None:
    """The candidate range stays inside the predecessor's frozen range."""

    bind_receipt(_shortfall_receipt())

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=PREDECESSOR_COUNT + 1))


def test_a_shortfall_retry_requires_a_positive_object_floor(bind_receipt) -> None:
    """A zero quota is not an active workload."""

    bind_receipt(_shortfall_receipt())

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=0, count=12))


def test_the_candidate_count_may_not_drop_below_the_object_floor(
    bind_receipt,
) -> None:
    """`count` is the candidate range and never smaller than the floor."""

    bind_receipt(_shortfall_receipt())

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=5, count=4))


def test_a_lane_still_eligible_for_release_may_not_be_retried_narrower(
    bind_receipt,
) -> None:
    """Re-crediting an already releasable lane would double-count objects."""

    bind_receipt(
        _shortfall_receipt(lane_overrides={"eligibleForRelease": True})
    )

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_lane_not_excluded_from_the_retry_release_fails_closed(
    bind_receipt,
) -> None:
    """The lane must be excluded from the retry release to justify a shortfall."""

    bind_receipt(
        _shortfall_receipt(lane_overrides={"excludedFromRetryRelease": False})
    )

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_non_terminal_lane_may_not_carry_a_shortfall_retry(bind_receipt) -> None:
    """Only a terminal failed lane can be superseded by a new sequence."""

    bind_receipt(
        _shortfall_receipt(lane_overrides={"terminalStatus": "partial"})
    )

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_published_evidence_disposition_may_not_carry_a_shortfall_retry(
    bind_receipt,
) -> None:
    """`failed_unpublished` is the only disposition that leaves nothing behind."""

    bind_receipt(
        _shortfall_receipt(lane_overrides={"evidenceDisposition": "published"})
    )

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_shortfall_receipt_without_this_carrier_lane_fails_closed(
    bind_receipt,
) -> None:
    """The retry binds this lane's evidence, never a sibling lane's."""

    bind_receipt(
        _shortfall_receipt(lane_overrides={"carrier": "image"})
    )

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_lane_row_for_a_different_predecessor_execution_fails_closed(
    bind_receipt,
) -> None:
    """Lineage is exact: the lane row must name the `retryOf` execution."""

    bind_receipt(
        _shortfall_receipt(
            lane_overrides={
                "executionId": (
                    "20260728--travel-article-workload-article-1--china--scale-009"
                )
            }
        )
    )

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_shortfall_receipt_without_execution_evidence_fails_closed(
    bind_receipt,
) -> None:
    """Absent evidence is a failure, not an implicitly admissible retry."""

    bind_receipt(_shortfall_receipt(executionEvidence=None))

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_foreign_retry_policy_may_not_admit_a_narrower_scope(
    bind_receipt,
) -> None:
    """The retry policy is part of the shortfall admission, not decoration."""

    bind_receipt(_shortfall_receipt(retryPolicy="operator_manual"))

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_shortfall_retry_may_not_change_the_target_identity(
    bind_receipt,
) -> None:
    """A narrower scope is still the same family/region/selector/topic."""

    bind_receipt(_shortfall_receipt())

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(
            _request(quota=3, count=12, region_ref="japan"),
        )


def test_a_shortfall_retry_may_not_change_the_selector(bind_receipt) -> None:
    """The frozen selector is part of the predecessor scope."""

    bind_receipt(_shortfall_receipt())

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(
            _request(
                quota=3,
                count=12,
                selector=TargetSelector.SOURCE_READY_PRIORITY,
            ),
        )


def test_a_missing_predecessor_submission_row_fails_closed(bind_receipt) -> None:
    """The retry must bind a real predecessor submission for this carrier."""

    receipt = _shortfall_receipt()
    receipt["submissions"] = {}
    bind_receipt(receipt)

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_source_drift_receipt_still_requires_the_exact_scope(
    bind_receipt,
) -> None:
    """Only the shortfall reason relaxes the exact quota/count binding."""

    bind_receipt(
        _shortfall_receipt(
            reason="source_drift",
            retryPolicy="active_workload_execution_with_retryOf",
        )
    )

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=3, count=12))


def test_a_source_drift_receipt_admits_an_identical_scope(bind_receipt) -> None:
    """An exact-scope retry stays valid for other reconciliation reasons."""

    bind_receipt(_shortfall_receipt(reason="source_drift"))

    _validate(_request(quota=PREDECESSOR_QUOTA, count=PREDECESSOR_COUNT))


def test_a_source_drift_receipt_without_real_drift_fails_closed(
    bind_receipt,
) -> None:
    """No source identity drift means no supersession is admissible."""

    bind_receipt(
        _shortfall_receipt(
            reason="source_drift",
            originalSourceIdentity={
                "sourceRevision": SOURCE_REVISION,
                "sourceDigest": dict(SOURCE),
                "executionBundle": dict(EXECUTION_BUNDLE),
                "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
            },
        )
    )

    with pytest.raises(ValueError, match="SUBMISSION_RECONCILIATION_DRIFT"):
        _validate(_request(quota=PREDECESSOR_QUOTA, count=PREDECESSOR_COUNT))
