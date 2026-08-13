"""场景组：campaign release 四 lane 推导与 retry lineage 谱系。

从 test_campaign_release__selector__contract__local_contract_test.py
按场景拆出（本文件经 git mv 承接原文件历史）；测试逐字搬移。
"""
from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import (
    submission_reconciliation as campaign_submission_reconciliation,
)
from content.release.canonical import campaign_release, campaign_release_selection
from content.release.canonical.campaign_release import (
    CampaignReleaseError,
    CampaignReleaseRoots,
    build_campaign_release,
)

from support.campaign_release_selector_fixture import (
    CARRIERS,
    CATALOG_DIGEST,
    FENCE,
    RELEASE_ID,
    RUN_ID,
    SOURCE_DIGEST,
    _digest,
    _execution_id,
    _fixture,
    _write,
)


def test_campaign_release__derives_four_lanes_and_retry_lineage__local_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    captured: list[list[str]] = []

    def aggregate(**kwargs: object) -> dict[str, object]:
        execution_ids = list(kwargs["execution_ids"])
        captured.append(execution_ids)
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": execution_ids,
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": len(captured) > 1,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", aggregate)
    result = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=fixture["roots"],
    )
    attestation_path = Path(result["campaignSelectionAttestation"])
    first_bytes = attestation_path.read_bytes()
    attestation = json.loads(first_bytes)

    assert "execution_ids" not in inspect.signature(build_campaign_release).parameters
    assert captured == [[fixture["executionIds"][carrier] for carrier in CARRIERS]]
    assert attestation["executionIds"] == fixture["executionIds"]
    assert attestation["retryLineage"]["image"] == [
        fixture["executionIds"]["image"],
        fixture["olderImageId"],
    ]
    assert attestation["campaignRun"] == {
        "runId": RUN_ID,
        "generation": 3,
        "fencingToken": FENCE,
    }
    assert result["manifestDigest"] == attestation["manifestDigest"]
    digest_input = {
        key: value for key, value in attestation.items() if key != "selectionDigest"
    }
    assert attestation["selectionDigest"] == _digest(digest_input)
    rerun = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=fixture["roots"],
    )
    assert rerun["campaignSelectionDigest"] == result["campaignSelectionDigest"]
    assert attestation_path.read_bytes() == first_bytes


def test_retry_lineage_consumes_preserved_unadopted_post_publish_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    campaign_root = fixture["campaignRoot"]
    execution_ids = fixture["executionIds"]
    assert isinstance(roots, CampaignReleaseRoots)
    assert isinstance(campaign_root, Path)
    assert isinstance(execution_ids, dict)
    carrier = "article"
    current_id = execution_ids[carrier]
    predecessor_ids = {
        lane: _execution_id(lane, 200) for lane in CARRIERS
    }
    submission = json.loads(
        (campaign_root / "submissions" / f"{current_id}.json").read_text(
            encoding="utf-8"
        )
    )
    submission["retryOf"] = predecessor_ids[carrier]
    submission["predecessorReconciliation"] = {
        "receiptRef": "data/local/reconciliation/post-publish.json",
        "receiptDigest": "sha256:" + "3" * 64,
    }
    manifest_path = roots.tasks_root / current_id / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["retryOf"] = predecessor_ids[carrier]
    _write(manifest_path, manifest)
    plan = json.loads(
        (campaign_root / "campaign_plan.json").read_text(encoding="utf-8")
    )
    predecessor_rows: dict[str, dict[str, object]] = {}
    for lane in CARRIERS:
        current = json.loads(
            (
                campaign_root
                / "submissions"
                / f"{execution_ids[lane]}.json"
            ).read_text(encoding="utf-8")
        )
        predecessor_rows[lane] = {
            **current,
            "rootExecutionId": predecessor_ids["homepage"],
            "executionId": predecessor_ids[lane],
            "retryOf": _execution_id(lane, 199),
        }
    receipt = {
        "reason": "post_publish_partial_terminal",
        "rootExecutionId": predecessor_ids["homepage"],
        "observedSourceIdentity": {
            "sourceRevision": plan["sourceRevision"],
            "sourceDigest": submission["sourceDigest"],
            "entityCatalogDigest": plan["entityCatalogDigest"],
        },
        "submissions": predecessor_rows,
        "executionEvidence": {
            "lanes": [],
            "partialPublish": {
                "carrier": "article",
                "executionId": predecessor_ids["article"],
                "objectRef": "article/攻略/都江堰市/1",
                "researchAcceptedCount": 1,
                "finalizedObjectCount": 0,
            },
            "allLanesFinalizedCount": 0,
            "immutableReleaseEvidencePresent": False,
            "reviewedClosureAdoptionPresent": False,
            "evidenceDisposition": "preserved_unadopted",
            "excludedFromFinalized": True,
            "eligibleForRelease": False,
        },
    }
    receipt_path = roots.output_root / "data/local/reconciliation/post-publish.json"
    monkeypatch.setattr(
        campaign_release_selection,
        "load_reconciliation_reference",
        lambda *_args, **_kwargs: (receipt, receipt_path),
    )

    lineage = campaign_release_selection.retry_lineage(
        carrier,
        current_id,
        submission,
        plan,
        roots=roots,
    )

    assert lineage == [current_id, predecessor_ids[carrier]]
    receipt["executionEvidence"]["eligibleForRelease"] = True
    with pytest.raises(CampaignReleaseError) as caught:
        campaign_release_selection.retry_lineage(
            carrier,
            current_id,
            submission,
            plan,
            roots=roots,
        )
    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_RETRY_IDENTITY_DRIFT"


def test_campaign_release__keeps_prior_source_epoch_as_retry_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)
    predecessor_id = fixture["olderImageId"]
    predecessor_root = roots.tasks_root / predecessor_id
    target_path = predecessor_root / "0.plan/target_set.json"
    manifest_path = predecessor_root / "execution_manifest.json"
    target = json.loads(target_path.read_text(encoding="utf-8"))
    target["entityCatalogDigest"] = "sha256:" + "8" * 64
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceDigest"] = {
        "algorithm": "sha256",
        "digest": "sha256:" + "9" * 64,
        "inputs": ["quwoquan_data/reference/travel"],
    }
    manifest["targetSetDigest"] = _digest(target, prefix=False)
    _write(target_path, target)
    _write(manifest_path, manifest)

    def aggregate(**kwargs: object) -> dict[str, object]:
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": False,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", aggregate)
    result = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=roots,
    )
    attestation = json.loads(
        Path(result["campaignSelectionAttestation"]).read_text(encoding="utf-8")
    )

    assert attestation["sourceDigest"] == SOURCE_DIGEST
    assert attestation["entityCatalogDigest"] == CATALOG_DIGEST
    assert attestation["retryLineage"]["image"] == [
        fixture["executionIds"]["image"],
        predecessor_id,
    ]


def test_campaign_release__rejects_retry_target_scope_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)
    predecessor_root = roots.tasks_root / fixture["olderImageId"]
    target_path = predecessor_root / "0.plan/target_set.json"
    manifest_path = predecessor_root / "execution_manifest.json"
    target = json.loads(target_path.read_text(encoding="utf-8"))
    target["targets"][0]["name"] = "另一个实体"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["targetSetDigest"] = _digest(target, prefix=False)
    _write(target_path, target)
    _write(manifest_path, manifest)

    monkeypatch.setattr(
        campaign_release,
        "build_aggregate_release",
        lambda **_kwargs: pytest.fail("aggregate must not run"),
    )
    with pytest.raises(CampaignReleaseError) as caught:
        build_campaign_release(
            root_execution_id=str(fixture["rootId"]),
            release_id=RELEASE_ID,
            roots=roots,
        )

    assert caught.value.code == "DATA.CAMPAIGN.RELEASE_RETRY_IDENTITY_DRIFT"
    assert "retry target scope drift" in str(caught.value)


def test_campaign_release_accepts_audited_submission_only_predecessor_for_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    roots = fixture["roots"]
    assert isinstance(roots, CampaignReleaseRoots)
    predecessor_image_id = str(fixture["olderImageId"])
    shutil.rmtree(roots.tasks_root / predecessor_image_id)
    predecessor_root_id = _execution_id("homepage", 200)
    predecessor_campaign = roots.campaigns_root / predecessor_root_id
    current_campaign = fixture["campaignRoot"]
    assert isinstance(current_campaign, Path)
    current_submissions = {
        carrier: json.loads(
            (
                current_campaign
                / "submissions"
                / f"{fixture['executionIds'][carrier]}.json"
            ).read_text(encoding="utf-8")
        )
        for carrier in CARRIERS
    }
    for carrier in CARRIERS:
        current = current_submissions[carrier]
        predecessor_id = _execution_id(carrier, 200)
        stable = {
            key: value
            for key, value in current.items()
            if key not in {"requestDigest", "submittedAt", "predecessorReconciliation"}
        }
        stable.update(
            {
                "rootExecutionId": predecessor_root_id,
                "executionId": predecessor_id,
                "retryOf": None,
            }
        )
        _write(
            predecessor_campaign / "submissions" / f"{predecessor_id}.json",
            {
                **stable,
                "requestDigest": _digest(stable),
                "submittedAt": "2026-08-05T00:00:00+00:00",
            },
        )
    blocker = roots.output_root / "data/local/cache/preflight.json"
    _write(
        blocker,
        {
            "ready": False,
            "semanticAgentStartup": {
                "provider": "codex_sdk",
                "checked": True,
                "ready": False,
                "issues": ["capacity rejected"],
            },
        },
    )
    source_document = current_submissions["image"]["sourceDigest"]
    monkeypatch.setattr(
        campaign_submission_reconciliation,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(source_document)),
    )
    monkeypatch.setattr(
        campaign_submission_reconciliation,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )
    _receipt, receipt_path = (
        campaign_submission_reconciliation.reconcile_submission_only_campaign(
            predecessor_root_id,
            reason="provider_rejected",
            blocker_evidence=blocker,
            repo_root=tmp_path,
            output_root=roots.output_root,
        )
    )
    reference = campaign_submission_reconciliation.reconciliation_reference(
        receipt_path,
        output_root=roots.output_root,
    )
    image_path = (
        current_campaign / "submissions" / f"{fixture['executionIds']['image']}.json"
    )
    image = json.loads(image_path.read_text(encoding="utf-8"))
    image_stable = {
        key: value
        for key, value in image.items()
        if key not in {"requestDigest", "submittedAt"}
    }
    image_stable["predecessorReconciliation"] = reference
    image = {
        **image_stable,
        "requestDigest": _digest(image_stable),
        "submittedAt": image["submittedAt"],
    }
    _write(image_path, image)
    plan_path = current_campaign / "campaign_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["submissionDigests"]["image"] = image["requestDigest"]
    plan_stable = {key: value for key, value in plan.items() if key != "planDigest"}
    plan["planDigest"] = _digest(plan_stable)
    _write(plan_path, plan)
    runtime_path = current_campaign / "runtime/snapshot.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    runtime["planDigest"] = plan["planDigest"]
    _write(runtime_path, runtime)

    def aggregate(**kwargs: object) -> dict[str, object]:
        release = Path(kwargs["release_root"]) / str(kwargs["release_id"])
        _write(release / "payload/release.json", {"releaseId": RELEASE_ID})
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": RELEASE_ID,
            "releaseRoot": str(release),
            "executionIds": list(kwargs["execution_ids"]),
            "canonicalMerkle": "sha256:" + "e" * 64,
            "idempotent": False,
        }

    monkeypatch.setattr(campaign_release, "build_aggregate_release", aggregate)
    result = build_campaign_release(
        root_execution_id=str(fixture["rootId"]),
        release_id=RELEASE_ID,
        roots=roots,
    )
    attestation = json.loads(
        Path(result["campaignSelectionAttestation"]).read_text(encoding="utf-8")
    )

    assert attestation["retryLineage"]["image"] == [
        fixture["executionIds"]["image"],
        predecessor_image_id,
    ]
    assert set(attestation["executionIds"].values()) == set(
        fixture["executionIds"].values()
    )
