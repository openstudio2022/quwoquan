from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution import campaign_submission_reconciliation as reconciliation
from content.execution import recipe_request
from content.execution.campaign_external_inputs import payload_digest
from core.io import read_json, write_json
from core.schema import assert_valid
from support.semantic_preflight_fixture import ready_semantic_preflight

CARRIERS = ("homepage", "article", "image", "video")
ROOT_ID = "20260805--travel-homepage-m3--china--scale-001"
SOURCE_DIGEST = "sha256:" + "a" * 64
CATALOG_DIGEST = "sha256:" + "b" * 64
OBSERVED_SOURCE_DIGEST = "sha256:" + "c" * 64


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _source_document(digest: str) -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "digest": digest,
        "inputs": ["quwoquan_data/scripts"],
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    output_root = tmp_path / "output"
    _preflight_path, semantic_preflight_binding = ready_semantic_preflight(
        "default",
        output_root=output_root,
    )
    campaigns_root = (
        output_root / "data/local/workspace/content-campaign-submissions"
    )
    campaign_root = campaigns_root / ROOT_ID
    source_revision = reconciliation.content_source_revision(
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
    )
    empty_external = payload_digest(
        {"schema": "quwoquan_data.campaign_external_input_set", "refs": []}
    )
    for carrier in CARRIERS:
        execution_id = (
            f"20260805--travel-{carrier}-m3--china--scale-001"
        )
        stable: dict[str, object] = {
            "schema": "quwoquan_data.content_execution_submission",
            "rootExecutionId": ROOT_ID,
            "executionId": execution_id,
            "operation": f"{carrier}.generate",
            "carrier": carrier,
            "familyRef": f"content/travel/{carrier}/{carrier}",
            "regionRef": "china",
            "selector": (
                "source-ready-priority"
                if carrier in {"homepage", "video"}
                else "priority"
            ),
            "semanticSelectionId": "default",
            "semanticPreflightReceipt": semantic_preflight_binding,
            "quota": 3,
            "count": 6,
            "topic": None,
            "targetNames": ["乌镇", "成都大熊猫繁育研究基地", "西湖"],
            "sourceProviders": [],
            "retryOf": None,
            "gitBranch": "dev1.0",
            "gitCommitSha": "d" * 40,
            "sourceRevision": source_revision,
            "sourceDigest": _source_document(SOURCE_DIGEST),
            "entityCatalogDigest": CATALOG_DIGEST,
            "externalInputRefs": [],
            "externalInputsDigest": empty_external,
        }
        submission = {
            **stable,
            "requestDigest": payload_digest(stable),
            "submittedAt": "2026-08-05T00:00:00+00:00",
        }
        write_json(
            campaign_root / "submissions" / f"{execution_id}.json",
            submission,
        )
    blocker = output_root / "data/local/cache/semantic-agent/preflight.json"
    write_json(
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
    return output_root, campaigns_root, blocker


def _patch_observed_identity(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_digest: str = OBSERVED_SOURCE_DIGEST,
) -> None:
    monkeypatch.setattr(
        reconciliation,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: _source_document(source_digest)
        ),
    )
    monkeypatch.setattr(
        reconciliation,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )


def test_submission_only_reconciliation_writes_one_typed_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _campaigns_root, blocker = _fixture(tmp_path)
    _patch_observed_identity(monkeypatch)

    receipt, path = reconciliation.reconcile_submission_only_campaign(
        ROOT_ID,
        reason="provider_rejected",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert_valid(
        receipt,
        "execution",
        "campaign_submission_reconciliation_receipt",
        label="submission-only reconciliation",
    )
    assert receipt["decision"] == "abandoned"
    assert receipt["reason"] == "provider_rejected"
    assert receipt["originalSourceIdentity"]["sourceDigest"]["digest"] == SOURCE_DIGEST
    assert (
        receipt["observedSourceIdentity"]["sourceDigest"]["digest"]
        == OBSERVED_SOURCE_DIGEST
    )
    assert receipt["blockerEvidence"]["sha256"] == _file_sha256(blocker)
    assert [row["carrier"] for row in receipt["executionEvidence"]["lanes"]] == list(
        CARRIERS
    )
    assert all(
        row["executionRootExists"] is False
        for row in receipt["executionEvidence"]["lanes"]
    )
    assert receipt["submissions"]["homepage"]["targetNames"] == [
        "乌镇",
        "成都大熊猫繁育研究基地",
        "西湖",
    ]
    assert path.name == "submission-only-abandonment.json"
    first_bytes = path.read_bytes()

    repeated, repeated_path = reconciliation.reconcile_submission_only_campaign(
        ROOT_ID,
        reason="provider_rejected",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )
    assert repeated == receipt
    assert repeated_path == path
    assert repeated_path.read_bytes() == first_bytes
    with pytest.raises(ValueError, match="already abandoned"):
        reconciliation.assert_campaign_not_reconciled(
            ROOT_ID,
            output_root=output_root,
        )


def test_submission_only_reconciliation_records_expired_ready_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _campaigns_root, _provider_blocker = _fixture(tmp_path)
    _patch_observed_identity(monkeypatch, source_digest=SOURCE_DIGEST)
    expired = output_root / "data/local/cache/semantic-agent/expired.json"
    write_json(
        expired,
        {
            "schema": "quwoquan_data.semantic_preflight_receipt",
            "ready": True,
            "validUntil": "2020-01-01T00:00:00Z",
        },
    )

    receipt, _path = reconciliation.reconcile_submission_only_campaign(
        ROOT_ID,
        reason="semantic_preflight_expired",
        blocker_evidence=expired,
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert receipt["reason"] == "semantic_preflight_expired"
    assert receipt["errorCode"] == (
        "DATA.CAMPAIGN.SUBMISSION_ONLY_SEMANTIC_PREFLIGHT_EXPIRED"
    )
    assert receipt["originalSourceIdentity"] == receipt["observedSourceIdentity"]


def test_partial_submission_reconciliation_freezes_missing_carrier_absence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaigns_root, blocker = _fixture(tmp_path)
    _patch_observed_identity(monkeypatch)
    homepage_submission = (
        campaigns_root
        / ROOT_ID
        / "submissions"
        / f"{ROOT_ID}.json"
    )
    homepage_submission.unlink()

    receipt, _path = reconciliation.reconcile_submission_only_campaign(
        ROOT_ID,
        reason="source_drift",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert set(receipt["submissions"]) == {"article", "image", "video"}
    assert receipt["missingSubmissions"] == ["homepage"]
    assert len(receipt["executionEvidence"]["lanes"]) == 4


def test_terminal_reconciliation_accepts_digest_valid_pre_hard_cut_evidence_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaigns_root, blocker = _fixture(tmp_path)
    _patch_observed_identity(monkeypatch)
    submissions = campaigns_root / ROOT_ID / "submissions"
    for path in submissions.glob("*.json"):
        payload = read_json(path)
        payload.pop("semanticSelectionId")
        payload.pop("semanticPreflightReceipt")
        stable = {
            key: value
            for key, value in payload.items()
            if key not in {"requestDigest", "submittedAt"}
        }
        payload["requestDigest"] = payload_digest(stable)
        write_json(path, payload)

    receipt, _path = reconciliation.reconcile_submission_only_campaign(
        ROOT_ID,
        reason="source_drift",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert receipt["decision"] == "abandoned"
    assert receipt["retryPolicy"] == "new_four_lane_execution_with_retryOf"
    assert set(receipt["submissions"]) == set(CARRIERS)


def test_submission_only_reconciliation_refuses_execution_or_untyped_provider_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _campaigns_root, blocker = _fixture(tmp_path)
    _patch_observed_identity(monkeypatch)
    execution_root = (
        output_root
        / "data/tasks/20260805--travel-video-m3--china--scale-001"
    )
    execution_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="execution evidence exists"):
        reconciliation.reconcile_submission_only_campaign(
            ROOT_ID,
            reason="provider_rejected",
            blocker_evidence=blocker,
            repo_root=tmp_path,
            output_root=output_root,
        )

    execution_root.rmdir()
    write_json(blocker, {"ready": False})
    with pytest.raises(ValueError, match="provider rejection evidence"):
        reconciliation.reconcile_submission_only_campaign(
            ROOT_ID,
            reason="provider_rejected",
            blocker_evidence=blocker,
            repo_root=tmp_path,
            output_root=output_root,
        )


def test_source_drift_reconciliation_requires_changed_observed_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _campaigns_root, blocker = _fixture(tmp_path)
    _patch_observed_identity(monkeypatch, source_digest=SOURCE_DIGEST)

    with pytest.raises(ValueError, match="source_drift requires identity drift"):
        reconciliation.reconcile_submission_only_campaign(
            ROOT_ID,
            reason="source_drift",
            blocker_evidence=blocker,
            repo_root=tmp_path,
            output_root=output_root,
        )


def test_reconciled_predecessor_targets_are_read_without_fake_target_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _campaigns_root, blocker = _fixture(tmp_path)
    _patch_observed_identity(monkeypatch)
    receipt, path = reconciliation.reconcile_submission_only_campaign(
        ROOT_ID,
        reason="provider_rejected",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    row = reconciliation.load_reconciled_predecessor_submission(
        "20260805--travel-homepage-m3--china--scale-001",
        output_root=output_root,
    )
    assert row is not None
    assert row["targetNames"] == receipt["submissions"]["homepage"]["targetNames"]
    assert reconciliation.reconciliation_reference(
        path,
        output_root=output_root,
    ) == {
        "predecessorRootExecutionId": ROOT_ID,
        "receiptRef": path.relative_to(output_root).as_posix(),
        "receiptDigest": receipt["receiptDigest"],
    }
    assert not (output_root / "data/tasks").exists()


def test_retry_target_names_use_reconciliation_when_target_set_never_existed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = ("乌镇", "成都大熊猫繁育研究基地", "西湖")
    monkeypatch.setattr(
        recipe_request,
        "submission_only_predecessor_target_names",
        lambda _retry_of: names,
    )

    assert recipe_request.retry_target_names(
        "20260805--travel-homepage-m3--china--scale-001",
        count=6,
        quota=3,
        requested_target_names=(),
        load_frozen_target_set=lambda _execution_id: (_ for _ in ()).throw(
            FileNotFoundError("never created")
        ),
    ) == names


def test_retry_target_names_use_terminal_freeze_campaign_submissions(
    tmp_path: Path,
) -> None:
    output_root, campaigns_root, _blocker = _fixture(tmp_path)
    campaign = campaigns_root / ROOT_ID
    write_json(
        campaign / "campaign_report.json",
        {
            "schema": "quwoquan_data.content_campaign_report",
            "rootExecutionId": ROOT_ID,
            "status": "blocked",
            "phase": "freeze",
            "lanes": {
                carrier: {
                    "status": "pending",
                    "phase": "submission",
                    "executionRootRef": None,
                }
                for carrier in CARRIERS
            },
        },
    )
    write_json(
        campaign / "runtime/snapshot.json",
        {
            "schema": "quwoquan_data.content_campaign_runtime_snapshot",
            "rootExecutionId": ROOT_ID,
            "status": "blocked",
            "phase": "freeze",
            "finishedAt": "2026-08-06T01:27:28Z",
        },
    )

    assert recipe_request.terminal_campaign_predecessor_target_names(
        "20260805--travel-homepage-m3--china--scale-001",
        output_root=output_root,
    ) == ("乌镇", "成都大熊猫繁育研究基地", "西湖")


def test_retry_target_names_use_completed_review_failure_campaign_submissions(
    tmp_path: Path,
) -> None:
    output_root, campaigns_root, _blocker = _fixture(tmp_path)
    campaign = campaigns_root / ROOT_ID
    submissions = {
        carrier: read_json(
            campaign
            / "submissions"
            / f"20260805--travel-{carrier}-m3--china--scale-001.json"
        )
        for carrier in CARRIERS
    }
    lane_external_inputs = {
        carrier: {
            "executionId": submissions[carrier]["executionId"],
            "externalInputRefs": submissions[carrier]["externalInputRefs"],
            "externalInputsDigest": submissions[carrier]["externalInputsDigest"],
        }
        for carrier in CARRIERS
    }
    stable_plan = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": ROOT_ID,
        "gitBranch": "dev1.0",
        "gitCommitSha": "d" * 40,
        "sourceRevision": submissions["homepage"]["sourceRevision"],
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "semanticSelectionId": "default",
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": payload_digest(
            {
                "schema": "quwoquan_data.campaign_external_input_lanes",
                "lanes": lane_external_inputs,
            }
        ),
        "submissionDigests": {
            carrier: submissions[carrier]["requestDigest"]
            for carrier in CARRIERS
        },
        "executionIds": {
            carrier: submissions[carrier]["executionId"]
            for carrier in CARRIERS
        },
        "frozenAt": "2026-08-06T02:34:42Z",
        "semanticPreflightReceipt": submissions["homepage"][
            "semanticPreflightReceipt"
        ],
    }
    plan = {**stable_plan, "planDigest": payload_digest(stable_plan)}
    write_json(campaign / "campaign_plan.json", plan)
    report_lanes: dict[str, object] = {}
    snapshot_lanes: dict[str, object] = {}
    for carrier in CARRIERS:
        execution_id = submissions[carrier]["executionId"]
        execution_root = output_root / "data/tasks" / execution_id
        write_json(
            execution_root / "0.plan/campaign_external_input_envelope.json",
            {"executionId": execution_id},
        )
        report_lanes[carrier] = {
            "executionId": execution_id,
            "status": "blocked",
            "phase": "review",
            "reviewReturnCode": 1,
            "publishReturnCode": None,
            "executionRootRef": f"data/tasks/{execution_id}",
            "cleanupStatus": "cleaned",
            "error": "ModuleNotFoundError: quwoquan_ops",
        }
        snapshot_lanes[carrier] = {
            "executionId": execution_id,
            "status": "failed",
            "phase": "review-only",
            "returnCode": 1,
        }
    write_json(
        campaign / "campaign_report.json",
        {
            "schema": "quwoquan_data.content_campaign_report",
            "rootExecutionId": ROOT_ID,
            "status": "blocked",
            "phase": "completed",
            "planDigest": plan["planDigest"],
            "lanes": report_lanes,
        },
    )
    write_json(
        campaign / "runtime/snapshot.json",
        {
            "schema": "quwoquan_data.content_campaign_runtime_snapshot",
            "rootExecutionId": ROOT_ID,
            "status": "blocked",
            "phase": "completed",
            "planDigest": plan["planDigest"],
            "finishedAt": "2026-08-06T02:35:24Z",
            "lanes": snapshot_lanes,
        },
    )

    assert recipe_request.terminal_campaign_predecessor_target_names(
        "20260805--travel-homepage-m3--china--scale-001",
        output_root=output_root,
    ) == ("乌镇", "成都大熊猫繁育研究基地", "西湖")

    plan["planDigest"] = "sha256:" + "0" * 64
    write_json(campaign / "campaign_plan.json", plan)
    with pytest.raises(SystemExit, match="campaign plan evidence is invalid"):
        recipe_request.terminal_campaign_predecessor_target_names(
            "20260805--travel-homepage-m3--china--scale-001",
            output_root=output_root,
        )
