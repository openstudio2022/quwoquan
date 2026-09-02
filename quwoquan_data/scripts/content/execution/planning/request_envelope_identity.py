"""Cross-carrier identity checks for immutable campaign request envelopes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def assert_one_source_identity(
    payloads: Mapping[str, Mapping[str, Any]],
    *,
    predecessor_reconciliation_receipt: Mapping[str, Any] | None,
) -> None:
    identities = {
        json.dumps(
            {
                "sourceRevision": payload["sourceRevision"],
                "sourceDigest": payload["sourceDigest"],
                "entityCatalogDigest": payload["entityCatalogDigest"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for payload in payloads.values()
    }
    if len(identities) != 1:
        raise ValueError(
            "campaign envelope source identity changed while freezing carriers"
        )
    if predecessor_reconciliation_receipt is None:
        return
    reason = predecessor_reconciliation_receipt.get("reason")
    if reason in {
        "mixed_finalized_partial_terminal",
        "terminal_unpublished_source_drift",
        "terminal_unpublished_retryable_shortfall",
    }:
        observed_identity = predecessor_reconciliation_receipt.get(
            "observedSourceIdentity"
        )
        if not isinstance(observed_identity, Mapping):
            raise TypeError(
                "campaign mixed terminal reconciliation observed identity is invalid"
            )
        execution_evidence = predecessor_reconciliation_receipt.get(
            "executionEvidence"
        )
        if not isinstance(execution_evidence, Mapping):
            raise TypeError(
                "campaign mixed terminal reconciliation execution evidence is invalid"
            )
        if (
            predecessor_reconciliation_receipt.get("retryPolicy")
            != "active_workload_execution_with_retryOf"
            or execution_evidence.get("excludedFromRetryRelease") is not True
            or execution_evidence.get("eligibleForRelease") is not False
        ):
            raise ValueError(
                "campaign mixed terminal reconciliation does not exclude predecessor objects"
            )
        current = next(iter(payloads.values()))
        current_identity = {
            "sourceRevision": current["sourceRevision"],
            "sourceDigest": current["sourceDigest"],
            "entityCatalogDigest": current["entityCatalogDigest"],
        }
        if (
            reason
            in {
                "terminal_unpublished_source_drift",
                "terminal_unpublished_retryable_shortfall",
            }
            and current_identity != observed_identity
        ):
            raise ValueError(
                "campaign terminal unpublished retry source identity drifted"
            )
        return
    if reason not in {
        "source_drift",
        "claimed_execution_source_drift",
    }:
        return
    original_identity = predecessor_reconciliation_receipt.get(
        "originalSourceIdentity"
    )
    if not isinstance(original_identity, Mapping):
        raise TypeError(
            "campaign predecessor reconciliation original identity is invalid"
        )
    current = next(iter(payloads.values()))
    current_identity = {
        "sourceRevision": current["sourceRevision"],
        "sourceDigest": current["sourceDigest"],
        "entityCatalogDigest": current["entityCatalogDigest"],
    }
    if current_identity == dict(original_identity):
        raise ValueError(
            "campaign retry source identity did not leave the reconciled source"
        )


def assert_one_handoff_identity(
    payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    bindings = {
        json.dumps(
            payload["preAcquisitionHandoff"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for payload in payloads.values()
    }
    if len(bindings) != 1:
        raise ValueError(
            "campaign handoff identity changed while freezing carriers"
        )


__all__ = ["assert_one_handoff_identity", "assert_one_source_identity"]
