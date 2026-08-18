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


def _receipt(
    predecessor_ids: dict[str, str],
    submissions: dict[str, dict[str, object]],
    plan: dict[str, object],
) -> dict[str, object]:
    active = tuple(submissions)
    qualified = tuple(
        carrier for carrier in active if carrier in {"homepage", "article"}
    ) or (active[0],)
    lanes = [
        {
            "carrier": carrier,
            "executionId": predecessor_ids[carrier],
            "terminalStatus": "failed",
            "claim": {"ref": f"{carrier}-claim", "sha256": "x"},
            "reportStatus": "blocked",
            "reviewReceiptPresent": carrier in qualified,
            "reviewReceipt": (
                {"ref": f"{carrier}-review", "sha256": "y"}
                if carrier in qualified
                else None
            ),
            "reviewStatus": (
                "qualified" if carrier in qualified else None
            ),
            "reviewQualifiedCount": (
                1 if carrier in qualified else 0
            ),
            "observedFinalizedCount": 0,
            "publishReceiptPresent": False,
            "publishRefPresent": False,
            "objectTransactionEvidencePresent": False,
            "evidenceDisposition": "failed_unpublished",
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
        }
        for carrier in active
    ]
    representative = active[0]
    identity = {
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": submissions[representative]["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
    }
    original_identity = {
        **identity,
        "sourceRevision": "sha256:" + "9" * 64,
        "sourceDigest": {
            **submissions[representative]["sourceDigest"],
            "digest": "sha256:" + "8" * 64,
        },
    }
    return {
        "reason": "terminal_unpublished_source_drift",
        "rootExecutionId": predecessor_ids[representative],
        "originalSourceIdentity": original_identity,
        "observedSourceIdentity": identity,
        "submissions": {
            carrier: {
                **submissions[carrier],
                "rootExecutionId": predecessor_ids[representative],
                "executionId": predecessor_ids[carrier],
            }
            for carrier in active
        },
        "executionEvidence": {
            "lanes": lanes,
            "observedFinalizedCount": 0,
            "reviewQualifiedLaneCount": len(qualified),
            "campaignPublishReceiptsPresent": False,
            "campaignPublishRefsPresent": False,
            "objectTransactionEvidencePresent": False,
            "immutableReleaseEvidencePresent": False,
            "reviewedClosureAdoptionPresent": False,
            "evidenceDisposition": "failed_unpublished",
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
        },
    }


def _retry_fixture(
    tmp_path: Path,
    *,
    active: tuple[str, ...] = CARRIERS,
) -> tuple[
    CampaignReleaseRoots,
    Path,
    dict[str, str],
    dict[str, dict[str, object]],
    dict[str, object],
    dict[str, object],
]:
    fixture = _fixture(
        tmp_path,
        active_carriers=active,
        workloads={carrier: 1 for carrier in active},
        intent=(
            "workload-" + "-".join(f"{carrier}-1" for carrier in active)
        ),
    )
    roots = fixture["roots"]
    campaign_root = fixture["campaignRoot"]
    execution_ids = fixture["executionIds"]
    assert isinstance(roots, CampaignReleaseRoots)
    assert isinstance(campaign_root, Path)
    assert isinstance(execution_ids, dict)
    plan = json.loads(
        (campaign_root / "campaign_plan.json").read_text(encoding="utf-8")
    )
    predecessor_ids = {carrier: _execution_id(carrier, 200) for carrier in active}
    reference = {
        "predecessorRootExecutionId": predecessor_ids[active[0]],
        "receiptRef": "data/local/reconciliation/terminal-unpublished.json",
        "receiptDigest": "sha256:" + "4" * 64,
    }
    submissions: dict[str, dict[str, object]] = {}
    for carrier in active:
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
    receipt = _receipt(predecessor_ids, submissions, plan)
    predecessor_rows = receipt["submissions"]
    assert isinstance(predecessor_rows, dict)
    for carrier in active:
        _write(
            campaign_root.parent
            / predecessor_ids[active[0]]
            / "submissions"
            / f"{predecessor_ids[carrier]}.json",
            predecessor_rows[carrier],
        )
    return roots, campaign_root, execution_ids, submissions, plan, receipt


def test_retry_lineage_stops_at_terminal_unpublished_without_carrying_old_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots, _campaign_root, execution_ids, submissions, plan, receipt = _retry_fixture(
        tmp_path
    )
    receipt_path = roots.output_root / "data/local/reconciliation/terminal-unpublished.json"
    loader = lambda *_args, **_kwargs: (receipt, receipt_path)
    monkeypatch.setattr(campaign_release_selection, "load_reconciliation_reference", loader)
    monkeypatch.setattr(
        campaign_release_selection_mixed,
        "load_reconciliation_reference",
        loader,
    )

    campaign_release_selection_mixed.validate_reconciliation_retry_set(
        submissions,
        plan,
        roots=roots,
    )
    for carrier in CARRIERS:
        lineage = campaign_release_selection.retry_lineage(
            carrier,
            execution_ids[carrier],
            submissions[carrier],
            plan,
            roots=roots,
        )
        assert lineage == [execution_ids[carrier], receipt["submissions"][carrier]["executionId"]]

    receipt["executionEvidence"]["lanes"][0]["observedFinalizedCount"] = 1
    with pytest.raises(CampaignReleaseError) as caught:
        campaign_release_selection.retry_lineage(
            "homepage",
            execution_ids["homepage"],
            submissions["homepage"],
            plan,
            roots=roots,
        )
    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_RETRY_IDENTITY_DRIFT"


def test_terminal_unpublished_requires_exact_active_workload_retry_of(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    roots, _campaign_root, _execution_ids, submissions, plan, receipt = _retry_fixture(
        tmp_path
    )
    receipt_path = roots.output_root / "data/local/reconciliation/terminal-unpublished.json"
    monkeypatch.setattr(
        campaign_release_selection_mixed,
        "load_reconciliation_reference",
        lambda *_args, **_kwargs: (receipt, receipt_path),
    )
    submissions["video"]["retryOf"] = _execution_id("video", 199)

    with pytest.raises(CampaignReleaseError) as caught:
        campaign_release_selection_mixed.validate_reconciliation_retry_set(
            submissions,
            plan,
            roots=roots,
        )

    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_RETRY_IDENTITY_DRIFT"


def test_video_only_terminal_unpublished_retry_uses_active_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = ("video",)
    roots, _campaign, execution_ids, submissions, plan, receipt = _retry_fixture(
        tmp_path,
        active=active,
    )
    receipt_path = roots.output_root / "data/local/reconciliation/video-only.json"
    loader = lambda *_args, **_kwargs: (receipt, receipt_path)
    monkeypatch.setattr(campaign_release_selection, "load_reconciliation_reference", loader)
    monkeypatch.setattr(
        campaign_release_selection_mixed,
        "load_reconciliation_reference",
        loader,
    )

    campaign_release_selection_mixed.validate_reconciliation_retry_set(
        submissions,
        plan,
        roots=roots,
    )
    lineage = campaign_release_selection.retry_lineage(
        "video",
        execution_ids["video"],
        submissions["video"],
        plan,
        roots=roots,
    )

    assert receipt["rootExecutionId"] == receipt["submissions"]["video"]["rootExecutionId"]
    assert lineage == [execution_ids["video"], receipt["submissions"]["video"]["executionId"]]
