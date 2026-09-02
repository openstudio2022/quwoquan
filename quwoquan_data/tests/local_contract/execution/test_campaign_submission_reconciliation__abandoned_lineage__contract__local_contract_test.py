from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import submission_reconciliation as reconciliation
from content.execution.campaign import failed_execution_reconciliation
from content.execution.planning.recipe import request as recipe_request
from content.execution.planning.recipe import request_retry_scope
from content.execution.source_pool.external_inputs import payload_digest
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
            "scale": "M3",
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
            "schema": "quwoquan_data.semantic_provider_preflight_receipt",
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
    # Retry re-freezes the lanes the campaign actually declared active, which is not
    # always four, so the policy is named for the active workload rather than a lane count.
    assert receipt["retryPolicy"] == "active_workload_execution_with_retryOf"
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
        request_retry_scope,
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
        "executionMode": "central",
        "scale": "M3",
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


def test_failed_campaign_reconciliation_terminalizes_dead_source_drift_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaigns_root, blocker = _fixture(tmp_path)
    _patch_observed_identity(monkeypatch)
    monkeypatch.setattr(
        failed_execution_reconciliation,
        "current_source_definition_snapshot",
        reconciliation.current_source_digest,
    )
    monkeypatch.setattr(
        failed_execution_reconciliation,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )
    campaign = campaigns_root / ROOT_ID
    plan_digest = "sha256:" + "e" * 64
    run_id = "frozen-run"
    token = "sha256:" + "f" * 64
    write_json(
        campaign / "campaign_plan.json",
        {
            "rootExecutionId": ROOT_ID,
            "planDigest": plan_digest,
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
            "distributedRun": {
                "campaignRunId": run_id,
                "campaignGeneration": 1,
                "campaignFencingToken": token,
            },
        },
    )
    successor_failure = (
        "ValueError: campaign sourceDigest drift: "
        f"frozen={SOURCE_DIGEST} current={OBSERVED_SOURCE_DIGEST}"
    )
    successor_lanes = {
        carrier: {
            "executionId": f"20260805--travel-{carrier}-m3--china--scale-001",
            "status": "pending",
            "phase": "submission",
            "reviewReturnCode": None,
            "publishReturnCode": None,
            "executionRootRef": None,
            "cleanupStatus": "not_created",
            "approvedQuota": None,
            "qualifiedCount": None,
            "finalizedCount": None,
            "selectedCount": None,
            "discardedCount": None,
            "shortfallCount": None,
            "error": None,
        }
        for carrier in CARRIERS
    }
    write_json(
        campaign / "campaign_report.json",
        {
            "rootExecutionId": ROOT_ID,
            "campaignRunId": "successor-run",
            "campaignGeneration": 2,
            "campaignFencingToken": "sha256:" + "1" * 64,
            "status": "blocked",
            "phase": "freeze",
            "planDigest": None,
            "sourceDigest": None,
            "entityCatalogDigest": None,
            "lanes": successor_lanes,
            "failure": successor_failure,
        },
    )
    write_json(
        campaign / "runtime/snapshot.json",
        {
            "rootExecutionId": ROOT_ID,
            "runId": "successor-run",
            "generation": 2,
            "fencingToken": "sha256:" + "1" * 64,
            "status": "blocked",
            "phase": "freeze",
            "planDigest": None,
            "lanes": {},
            "finishedAt": "2026-08-08T04:12:35Z",
            "failure": successor_failure,
        },
    )
    for carrier in CARRIERS:
        execution_id = f"20260805--travel-{carrier}-m3--china--scale-001"
        dead = carrier == "video"
        write_json(
            campaign / "claims" / f"{carrier}.json",
            {
                "schema": "quwoquan_data.content_campaign_lane_claim",
                "rootExecutionId": ROOT_ID,
                "planDigest": plan_digest,
                "campaignRunId": run_id,
                "campaignGeneration": 1,
                "campaignFencingToken": token,
                "carrier": carrier,
                "executionId": execution_id,
                "claimId": "sha256:" + str(CARRIERS.index(carrier) + 2) * 64,
                "claimAttempt": 1,
                "status": "running" if dead else "failed",
                "phase": "review-only" if dead else "completed",
                "capsuleRef": "data/local/cache/content-campaign-workspaces/capsule",
                "executionRoot": str(output_root / "data/tasks" / execution_id),
                "pid": 999_999 if dead else 123,
                "pgid": 999_999 if dead else 123,
                "returnCode": None if dead else 130,
                "error": None if dead else "controller terminated",
                "terminationOwner": None if dead else "lane_process",
                "terminationSignal": None,
                "acquiredAt": "2026-08-08T03:45:39Z",
                "heartbeatAt": "2026-08-08T03:55:26Z",
                "updatedAt": "2026-08-08T03:55:26Z",
                "finishedAt": None if dead else "2026-08-08T03:55:29Z",
            },
        )

    receipt, _path = failed_execution_reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    video_claim = read_json(campaign / "claims/video.json")
    assert video_claim["status"] == "failed"
    assert video_claim["phase"] == "completed"
    assert video_claim["returnCode"] == 130
    assert video_claim["terminationOwner"] == "external_or_kernel"
    assert receipt["decision"] == "superseded"
