"""Hosted release receipt readback requires its exact ledger schema.

spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
"""

from __future__ import annotations

import argparse
import copy
from unittest import mock

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.prod import hosted_release_ledger


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _args(receipt_id: str) -> argparse.Namespace:
    return argparse.Namespace(
        service="mainline",
        receipt_id=receipt_id,
        purpose="last-good",
        image_digest=_digest("1"),
        config_digest=_digest("2"),
        contract_graph_digest=_digest("3"),
        adapter_digest=_digest("4"),
    )


def _receipt() -> dict[str, object]:
    request: dict[str, object] = {
        "schema": hosted_release_ledger.REQUEST_SCHEMA,
        "service": "mainline",
        "fromCandidateDigest": _digest("a"),
        "toCandidateDigest": _digest("b"),
        "step": "100",
        "stage": "100",
        "triggerStage": "100",
        "fromReleaseEvidenceRef": "ghcr.io/owner/repo/release-artifact@" + _digest("a"),
        "toReleaseEvidenceRef": "ghcr.io/owner/repo/release-artifact@" + _digest("b"),
        "fromImageTransportTag": "transport-a",
        "toImageTransportTag": "transport-b",
        "decision": "continue",
        "rollbackOutcome": "not_triggered",
        "rollbackEvidence": {"triggered": False},
        "artifactDigest": _digest("5"),
        "environmentAcceptanceRef": "prod/fact.json",
        "environmentAcceptanceDigest": _digest("6"),
        "environmentAcceptanceFactId": _digest("7"),
        "gammaPredecessorFactId": _digest("8"),
        "gammaPredecessorDigest": _digest("9"),
        "engineeringEligibilityRef": "prod/engineering.json",
        "engineeringEligibilityDigest": _digest("d"),
        "durableApprovalRef": "prod/approval.json",
        "durableApprovalDigest": _digest("e"),
        "imageDigest": _digest("1"),
        "configDigest": _digest("2"),
        "contractGraphDigest": _digest("3"),
        "adapterDigest": _digest("4"),
        "expectedGeneration": 0,
        "sloReadback": {"sampleCount": 100},
        "postChecks": [],
        "lastGoodCandidateDigest": _digest("b"),
        "verifiedAt": "2026-08-30T00:00:00Z",
    }
    hosted_release_ledger._validate_request(request)
    receipt = {
        **{key: value for key, value in request.items() if key != "schema"},
        "schema": hosted_release_ledger.RECEIPT_SCHEMA,
        "authority": hosted_release_ledger.AUTHORITY,
        "committedGeneration": 1,
    }
    receipt_id = hosted_release_ledger._receipt_id(receipt)
    receipt["receiptId"] = receipt_id
    return receipt


def test_schema_specific_validator_accepts_exact_release_receipt() -> None:
    receipt = _receipt()
    with mock.patch.object(
        stackctl,
        "_run_hosted_release_ledger",
        return_value={"receipt": receipt},
    ):
        result = stackctl.command_hosted_release_receipt(
            _args(str(receipt["receiptId"]))
        )
    assert result["exitCode"] == 0


@pytest.mark.parametrize(
    "mutation",
    ("schema", "extra-field", "generation"),
)
def test_schema_specific_validator_rejects_generic_or_wrong_receipt(
    mutation: str,
) -> None:
    receipt = copy.deepcopy(_receipt())
    if mutation == "schema":
        receipt["schema"] = "generic-receipt"
    elif mutation == "extra-field":
        receipt["runtimePassed"] = True
    else:
        receipt["committedGeneration"] = 9
    with mock.patch.object(
        stackctl,
        "_run_hosted_release_ledger",
        return_value={"receipt": receipt},
    ):
        result = stackctl.command_hosted_release_receipt(
            _args(str(_receipt()["receiptId"]))
        )
    assert result["exitCode"] == 2
    detail = " ".join(result["details"])
    assert "schema" in detail or "generation" in detail
