from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.release.canonical import (
    campaign_release_selection,
    campaign_release_selection_mixed,
)
from content.release.canonical.campaign_release import (
    CampaignReleaseError,
    CampaignReleaseRoots,
)
from support.campaign_release_selector_fixture import (
    CARRIERS,
    _execution_id,
    _fixture,
    _write,
)


def _mixed_receipt(
    predecessor_ids: dict[str, str],
    submissions: dict[str, dict[str, object]],
    plan: dict[str, object],
    *,
    failed_carrier: str = "article",
) -> dict[str, object]:
    lanes: list[dict[str, object]] = []
    for carrier in CARRIERS:
        common: dict[str, object] = {
            "carrier": carrier,
            "executionId": predecessor_ids[carrier],
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
        }
        if carrier == failed_carrier:
            common.update(
                {
                    "terminalStatus": "failed",
                    "reportStatus": "blocked",
                    "observedFinalizedCount": 0,
                    "publishReceiptPresent": False,
                    "publishRefPresent": False,
                    "objectTransactionEvidencePresent": False,
                    "evidenceDisposition": "failed_unpublished",
                }
            )
        else:
            common.update(
                {
                    "terminalStatus": "finalized",
                    "reportStatus": "finalized",
                    "observedFinalizedCount": 1,
                    "publishSelectionFinalizedCount": 1,
                    "publishReceipt": {"ref": f"{carrier}-receipt", "sha256": "x"},
                    "publishRef": {"ref": f"{carrier}-publish", "sha256": "y"},
                    "canonicalManifests": [
                        {
                            "objectKind": "entities"
                            if carrier == "homepage"
                            else "posts",
                            "objectRef": f"old-{carrier}",
                        }
                    ],
                    "evidenceDisposition": "preserved_unadopted",
                }
            )
        lanes.append(common)
    return {
        "reason": "mixed_finalized_partial_terminal",
        "rootExecutionId": predecessor_ids["homepage"],
        "observedSourceIdentity": {
            "sourceRevision": plan["sourceRevision"],
            "sourceDigest": submissions["homepage"]["sourceDigest"],
            "entityCatalogDigest": plan["entityCatalogDigest"],
        },
        "submissions": {
            carrier: {
                **submissions[carrier],
                "rootExecutionId": predecessor_ids["homepage"],
                "executionId": predecessor_ids[carrier],
            }
            for carrier in CARRIERS
        },
        "executionEvidence": {
            "lanes": lanes,
            "observedFinalizedCount": 3,
            "immutableReleaseEvidencePresent": False,
            "reviewedClosureAdoptionPresent": False,
            "evidenceDisposition": "preserved_unadopted",
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
        },
    }


@pytest.mark.parametrize("failed_carrier", ("article", "video"))
def test_retry_lineage_stops_at_mixed_terminal_without_carrying_old_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_carrier: str,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    campaign_root = fixture["campaignRoot"]
    execution_ids = fixture["executionIds"]
    assert isinstance(roots, CampaignReleaseRoots)
    assert isinstance(campaign_root, Path)
    assert isinstance(execution_ids, dict)
    plan = json.loads(
        (campaign_root / "campaign_plan.json").read_text(encoding="utf-8")
    )
    predecessor_ids = {carrier: _execution_id(carrier, 200) for carrier in CARRIERS}
    submissions: dict[str, dict[str, object]] = {}
    reference = {
        "predecessorRootExecutionId": predecessor_ids["homepage"],
        "receiptRef": "data/local/reconciliation/mixed.json",
        "receiptDigest": "sha256:" + "3" * 64,
    }
    for carrier in CARRIERS:
        current_id = execution_ids[carrier]
        path = campaign_root / "submissions" / f"{current_id}.json"
        submission = json.loads(path.read_text(encoding="utf-8"))
        submission["retryOf"] = predecessor_ids[carrier]
        submission["predecessorReconciliation"] = reference
        submissions[carrier] = submission
        manifest_path = roots.tasks_root / current_id / "execution_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["retryOf"] = predecessor_ids[carrier]
        _write(manifest_path, manifest)
    receipt = _mixed_receipt(
        predecessor_ids,
        submissions,
        plan,
        failed_carrier=failed_carrier,
    )
    for carrier, row in receipt["submissions"].items():
        _write(
            campaign_root.parent
            / predecessor_ids["homepage"]
            / "submissions"
            / f"{predecessor_ids[carrier]}.json",
            row,
        )
    receipt_path = roots.output_root / "data/local/reconciliation/mixed.json"
    monkeypatch.setattr(
        campaign_release_selection_mixed,
        "load_reconciliation_reference",
        lambda *_args, **_kwargs: (receipt, receipt_path),
    )
    monkeypatch.setattr(
        campaign_release_selection,
        "load_reconciliation_reference",
        lambda *_args, **_kwargs: (receipt, receipt_path),
    )

    for carrier in CARRIERS:
        lineage = campaign_release_selection.retry_lineage(
            carrier,
            execution_ids[carrier],
            submissions[carrier],
            plan,
            roots=roots,
        )
        assert lineage == [execution_ids[carrier], predecessor_ids[carrier]]
        assert all("old-" not in execution_id for execution_id in lineage)

    receipt["executionEvidence"]["eligibleForRelease"] = True
    with pytest.raises(CampaignReleaseError) as caught:
        campaign_release_selection.retry_lineage(
            "homepage",
            execution_ids["homepage"],
            submissions["homepage"],
            plan,
            roots=roots,
        )
    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_RETRY_IDENTITY_DRIFT"
