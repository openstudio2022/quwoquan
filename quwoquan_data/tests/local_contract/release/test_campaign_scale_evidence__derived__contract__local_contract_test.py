from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from content.release.canonical import campaign_scale_cumulative, research_scale_promotion as research_scale_promotion_module
from content.execution.scale.semantic_promotion import (
    select_scale_calibration_refs,
    semantic_calibration_evidence_path,
)
from content.execution.campaign.source_pool_binding import (
    bound_scale_source_pool_snapshot_digest,
    materialize_bound_scale_source_pool,
)
from content.source.research.scale_source_pool import build_scale_source_pool_plan
from content.release.canonical.campaign_scale_evidence import (
    CampaignScaleEvidenceError,
    load_campaign_scale_evidence,
    write_campaign_scale_evidence,
)
from content.release.canonical.campaign_scale_source_pool import source_pool_lineage_fields
from content.release.canonical.handler import register_parser
from content.release.canonical.research_scale_promotion import (
    ResearchScalePromotionError,
    write_research_scale_promotion,
)
from content.release.canonical.research_scale_promotion_timing import (
    ResearchScalePromotionTimingError,
    validate_promotion_timing,
)
from content.release.canonical.research_scale_video_popularity import (
    ResearchScaleVideoPopularityError,
    collect_m100_video_popularity_observations,
)
from core.paths import campaign_scale_evidence_root, research_scale_promotions_root
from core.runtime_policy import runtime_profile_digest
from core.source_digest import SourceDigest
from support.semantic_preflight_fixture import ready_semantic_preflight
from quwoquan_data.tests.local_contract.source.test_scale_source_pool__milestone_readiness__contract__local_contract_test import (
    EVIDENCE_PAYLOADS,
    _candidate as _scale_pool_candidate,
)

CARRIERS = ("homepage", "article", "image", "video")
SOURCE_DIGEST = "sha256:" + "a" * 64
SOURCE_DIGEST_DOCUMENT = SourceDigest(SOURCE_DIGEST).to_document()
CATALOG_DIGEST = "sha256:" + "b" * 64
START = datetime(2026, 8, 5, tzinfo=timezone.utc)
RUN_ID = "scale-runtime-run-001"
GENERATION = 1
FENCING_TOKEN = "sha256:" + "f" * 64
SESSION_ID = "scale-runtime-session-001"


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _digest(payload: object, *, prefix: bool = True) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    value = hashlib.sha256(encoded).hexdigest()
    return "sha256:" + value if prefix else value


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _resign_evidence(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    payload["evidenceDigest"] = _digest(
        {key: value for key, value in payload.items() if key != "evidenceDigest"}
    )
    _write(path, payload)
    return payload


def _signed(payload: dict[str, object], *, digest_field: str) -> dict[str, object]:
    document = dict(payload)
    document[digest_field] = _digest(document)
    return document


def _resign_receipt(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    payload["receiptDigest"] = _digest(
        {key: value for key, value in payload.items() if key != "receiptDigest"}
    )
    _write(path, payload)
    return payload


def _write_ranked_release_videos(
    release: Path,
    *,
    count: int,
    execution_id: str,
    source_revision: str,
    refs: list[str] | None = None,
) -> None:
    output = release.parents[2]
    refs = refs or [f"video/work-{index:03d}" for index in range(count)]
    assert len(refs) == count
    _write(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": "research-release",
            "desiredRefs": {
                "creators": [],
                "entities": [],
                "posts": refs,
                "tags": [],
            },
        },
    )
    for index, ref in enumerate(refs):
        object_root = release / "payload/objects/posts" / ref
        asset_id = f"video-asset-{index:03d}"
        content_sha256 = "sha256:" + f"{index + 1:064x}"[-64:]
        review_id = "asset-review-" + f"{index + 1:064x}"[-64:]
        receipt_ref = (
            f"data/tasks/{execution_id}/evidence/asset_reviews/receipts/"
            f"{review_id}.json"
        )
        popularity_signals = {
            "playCount": 1_000 + index,
            "likeCount": 100 + index,
            "commentCount": 10 + index,
            "shareCount": 5 + index,
            "favoriteCount": 20 + index,
            "observedAt": "2026-08-05T00:00:00Z",
            "provider": "professional_video_fixture",
            "topic": "travel",
            "timeBucket": "2026-W32",
            "popularityScore": 1_135 + 5 * index,
            "popularityPercentile": round(index / max(count - 1, 1), 6),
            "rankingEligible": True,
            "ineligibleReason": "",
            "comparisonCandidateCount": max(count, 2),
        }
        review_stable = {
            "schema": "quwoquan_data.independent_asset_review_receipt",
            "reviewId": review_id,
            "assetKind": "video",
            "objectRef": ref,
            "sourceRevision": source_revision,
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
            "executionManifestRef": f"data/tasks/{execution_id}/execution_manifest.json",
            "authorExecution": {"executionId": execution_id},
            "reviewerExecution": {"executionId": execution_id},
            "reviewDecision": "accepted",
            "assetSnapshot": {
                "assetId": asset_id,
                "contentSha256": content_sha256,
                "popularitySignals": popularity_signals,
            },
        }
        review = {**review_stable, "receiptDigest": _digest(review_stable)}
        receipt_path = output / receipt_ref
        _write(receipt_path, review)
        _write(object_root / "manifest.json", {"contentType": "video"})
        _write(
            object_root / "rights.json",
            {
                "assets": [
                    {
                        "independentAssetReview": {
                            "assetKind": "video",
                            "acquisitionAssetId": asset_id,
                            "objectRef": ref,
                            "receiptRef": receipt_ref,
                            "receiptDigest": review["receiptDigest"],
                            "receiptFileSha256": _file_digest(receipt_path),
                            "sourceRevision": source_revision,
                            "sourceDigest": SOURCE_DIGEST,
                            "entityCatalogDigest": CATALOG_DIGEST,
                            "contentSha256": content_sha256,
                            "popularitySignalsDigest": _digest(popularity_signals),
                        }
                    }
                ]
            },
        )


def _single_video_popularity_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    release = tmp_path / "output/data/releases/research-release"
    execution_id = _execution_id("video")
    source_revision = _digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
        }
    )
    _write_ranked_release_videos(
        release,
        count=1,
        execution_id=execution_id,
        source_revision=source_revision,
    )
    rights_path = release / "payload/objects/posts/video/work-000/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    receipt_ref = rights["assets"][0]["independentAssetReview"]["receiptRef"]
    return release, rights_path, release.parents[2] / receipt_ref


def test_video_popularity_reads_digest_bound_execution_review(tmp_path: Path) -> None:
    release, _rights_path, _receipt_path = _single_video_popularity_fixture(tmp_path)

    observations = collect_m100_video_popularity_observations(
        release,
        expected_video_count=1,
    )

    assert observations[0]["assetId"] == "video-asset-000"
    assert observations[0]["rankingEligible"] is True


def test_video_popularity_rejects_legacy_object_local_review_ref(
    tmp_path: Path,
) -> None:
    release, rights_path, _receipt_path = _single_video_popularity_fixture(tmp_path)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["independentAssetReview"]["receiptRef"] = (
        "asset_reviews/receipts/review.json"
    )
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="must name execution evidence",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


def test_video_popularity_rejects_review_ref_traversal(tmp_path: Path) -> None:
    release, rights_path, _receipt_path = _single_video_popularity_fixture(tmp_path)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["independentAssetReview"]["receiptRef"] = (
        "data/tasks/execution/evidence/asset_reviews/receipts/../../review.json"
    )
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="must name execution evidence",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


def test_video_popularity_rejects_execution_review_digest_drift(
    tmp_path: Path,
) -> None:
    release, rights_path, receipt_path = _single_video_popularity_fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["assetSnapshot"]["popularitySignals"]["playCount"] += 1
    _write(receipt_path, receipt)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["independentAssetReview"]["receiptFileSha256"] = (
        _file_digest(receipt_path)
    )
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="execution review binding drift",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


def test_video_popularity_rejects_cross_execution_review_binding(
    tmp_path: Path,
) -> None:
    release, rights_path, receipt_path = _single_video_popularity_fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["reviewerExecution"]["executionId"] = _execution_id("video", 3)
    receipt["receiptDigest"] = _digest(
        {key: value for key, value in receipt.items() if key != "receiptDigest"}
    )
    _write(receipt_path, receipt)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    binding = rights["assets"][0]["independentAssetReview"]
    binding["receiptDigest"] = receipt["receiptDigest"]
    binding["receiptFileSha256"] = _file_digest(receipt_path)
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="execution review binding drift",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


@pytest.mark.parametrize(
    ("binding_field", "drifted_value"),
    (
        ("objectRef", "video/different-work"),
        ("contentSha256", "sha256:" + "f" * 64),
    ),
)
def test_video_popularity_rejects_review_object_or_content_drift(
    tmp_path: Path,
    binding_field: str,
    drifted_value: str,
) -> None:
    release, rights_path, _receipt_path = _single_video_popularity_fixture(tmp_path)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["independentAssetReview"][binding_field] = drifted_value
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="execution review binding drift",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


def _sample_measurements(
    *,
    execution_ids: dict[str, str],
    captured_at: datetime,
    index: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    controller_rss = 400 * 1024**2 + index
    non_video_rss = 700 * 1024**2 + index
    video_rss = 1536 * 1024**2 + index
    processes = [
        {
            "role": "controller",
            "carrier": None,
            "executionId": execution_ids["homepage"],
            "registrationPid": 100,
            "isRegisteredProcess": True,
            "pid": 100,
            "pgid": 100,
            "processIdentityDigest": "sha256:" + "1" * 64,
            "rssBytes": controller_rss,
            "openFdCount": 60 + index,
        }
    ]
    for offset, carrier in enumerate(CARRIERS, start=1):
        processes.append(
            {
                "role": "worker",
                "carrier": carrier,
                "executionId": execution_ids[carrier],
                "registrationPid": 100 + offset,
                "isRegisteredProcess": True,
                "pid": 100 + offset,
                "pgid": 100 + offset,
                "processIdentityDigest": "sha256:" + str(offset + 1) * 64,
                "rssBytes": video_rss if carrier == "video" else non_video_rss,
                "openFdCount": 10,
            }
        )
    queue_depth = 40 - min(index, 40)
    queues = [
        {
            "carrier": carrier,
            "executionId": execution_ids[carrier],
            "queueDepth": queue_depth if carrier == "homepage" else 0,
            "readyDepth": 1 if carrier == "homepage" and queue_depth else 0,
            "oldestReadyAt": (
                captured_at - timedelta(seconds=300)
            ).isoformat() if carrier == "homepage" and queue_depth else None,
            "successfulJobCount": 10,
            "terminalJobCount": 10,
            "observationWindowSeconds": 3600,
            "throughputPerHour": 10.0,
            "latencyP95Milliseconds": 1000,
            "providerThrottleCount": 0,
            "stuckJobCount": 0,
            "providerEvidenceDigest": "sha256:" + str(offset + 6) * 64,
        }
        for offset, carrier in enumerate(CARRIERS)
    ]
    temporary_bytes = 1024**3 + index * 1024**2
    terminal_bytes = 80 * 1024**2
    workspaces = [
        {
            "workspaceRef": "data/local/workspace/runtime-fixture",
            "kind": "execution",
            "bytes": temporary_bytes - terminal_bytes,
        },
        {
            "workspaceRef": "data/local/workspace/runtime-fixture-staging",
            "kind": "transaction_staging",
            "bytes": terminal_bytes,
        },
    ]
    raw = {
        "capturedAt": captured_at.isoformat(),
        "controllerRssBytes": controller_rss,
        "nonVideoWorkerMaxRssBytes": non_video_rss,
        "videoWorkerMaxRssBytes": video_rss,
        "totalRssBytes": sum(int(row["rssBytes"]) for row in processes),
        "temporaryWorkspaceBytes": temporary_bytes,
        "terminalResidualBytes": terminal_bytes,
        "openFdCount": sum(int(row["openFdCount"]) for row in processes),
        "queueDepth": queue_depth,
        "oldestReadyAgeSeconds": 300 if queue_depth else 0,
        "progressAgeSeconds": 60,
        "heartbeatAgeSeconds": 30,
    }
    return processes, queues, workspaces, raw


def _write_runtime_receipts(
    *,
    output: Path,
    campaign_root: Path,
    plan_path: Path,
    plan: dict[str, object],
    fault_cases: list[dict[str, object]],
) -> tuple[Path, Path, Path]:
    execution_ids = dict(plan["executionIds"])
    runtime_root = campaign_root / "runtime"
    session_root = runtime_root / "evidence" / SESSION_ID
    session_path = session_root / "session.json"
    snapshot_path = runtime_root / "snapshot.json"
    _write(snapshot_path, {"status": "completed", "runId": RUN_ID})
    provider_rows = [
        {
            "faultType": fault_type,
            "providerId": f"fixture_{fault_type}_v1",
            "configurationDigest": "sha256:" + f"{index + 1:x}" * 64,
        }
        for index, fault_type in enumerate(
            (
                "worker_termination",
                "lease_expiry",
                "redis_restart",
                "mongo_reconnect",
                "provider_timeout",
                "provider_rate_limit",
            )
        )
    ]
    hook_path = session_root / "provider-fault-hook-attestation.json"
    hook_stable: dict[str, object] = {
        "schema": "quwoquan_data.runtime_provider_fault_test_hook_attestation",
        "rootExecutionId": plan["rootExecutionId"],
        "runId": RUN_ID,
        "generation": GENERATION,
        "fencingToken": FENCING_TOKEN,
        "providerBindings": provider_rows[-2:],
        "issuedAt": (START - timedelta(minutes=1)).isoformat(),
        "expiresAt": (START + timedelta(hours=2)).isoformat(),
    }
    _write(hook_path, _signed(hook_stable, digest_field="attestationDigest"))
    controller = {
        "role": "controller",
        "carrier": None,
        "executionId": plan["rootExecutionId"],
        "pid": 100,
        "pgid": 100,
        "processIdentityDigest": "sha256:" + "1" * 64,
        "checkpointRef": snapshot_path.relative_to(output).as_posix(),
        "checkpointSha256": _file_digest(snapshot_path),
        "workspaceRef": runtime_root.relative_to(output).as_posix(),
    }
    workers: list[dict[str, object]] = []
    for offset, carrier in enumerate(CARRIERS, start=1):
        checkpoint = runtime_root / "lanes" / f"{carrier}.json"
        _write(checkpoint, {"carrier": carrier, "executionId": execution_ids[carrier]})
        workspace = output / "data/tasks" / execution_ids[carrier]
        workspace.mkdir(parents=True, exist_ok=True)
        workers.append(
            {
                "role": "worker",
                "carrier": carrier,
                "executionId": execution_ids[carrier],
                "pid": 100 + offset,
                "pgid": 100 + offset,
                "processIdentityDigest": "sha256:" + str(offset + 1) * 64,
                "checkpointRef": checkpoint.relative_to(output).as_posix(),
                "checkpointSha256": _file_digest(checkpoint),
                "workspaceRef": workspace.relative_to(output).as_posix(),
            }
        )
    session_stable: dict[str, object] = {
        "schema": "quwoquan_data.runtime_evidence_session",
        "sessionId": SESSION_ID,
        "rootExecutionId": plan["rootExecutionId"],
        "runId": RUN_ID,
        "generation": GENERATION,
        "fencingToken": FENCING_TOKEN,
        "campaignPlanRef": plan_path.relative_to(output).as_posix(),
        "campaignPlanSha256": _file_digest(plan_path),
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": plan["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
        "runtimeSnapshotRef": snapshot_path.relative_to(output).as_posix(),
        "runtimeSnapshotSha256": _file_digest(snapshot_path),
        "leaseHeartbeatAt": START.isoformat(),
        "leaseSeconds": 60,
        "controller": controller,
        "workers": workers,
        "queueEvidenceProvider": {
            "providerId": "fixture_reliabletask_observer_v1",
            "configurationDigest": "sha256:" + "9" * 64,
        },
        "faultProviders": provider_rows,
        "providerFaultTestHooksEnabled": True,
        "providerFaultTestHookAttestationRef": hook_path.relative_to(output).as_posix(),
        "providerFaultTestHookAttestationSha256": _file_digest(hook_path),
        "createdAt": START.isoformat(),
    }
    session = _signed(session_stable, digest_field="receiptDigest")
    _write(session_path, session)
    session_ref = session_path.relative_to(output).as_posix()
    samples_root = session_root / "samples"
    for index in range(63):
        captured_at = START + timedelta(minutes=index)
        processes, queues, workspaces, raw = _sample_measurements(
            execution_ids=execution_ids,
            captured_at=captured_at,
            index=index,
        )
        sample_id = f"sample-{index:03d}"
        stable: dict[str, object] = {
            "schema": "quwoquan_data.runtime_resource_sample_receipt",
            "sampleId": sample_id,
            "sessionRef": session_ref,
            "sessionDigest": session["receiptDigest"],
            "rootExecutionId": plan["rootExecutionId"],
            "runId": RUN_ID,
            "generation": GENERATION,
            "fencingToken": FENCING_TOKEN,
            "capturedAt": captured_at.isoformat(),
            "processMeasurements": processes,
            "queueMeasurements": queues,
            "workspaceMeasurements": workspaces,
            "rawSample": raw,
        }
        _write(
            samples_root / f"{sample_id}.json",
            _signed(stable, digest_field="receiptDigest"),
        )
    faults_root = session_root / "faults"
    binding_by_type = {str(row["faultType"]): row for row in provider_rows}
    for case in fault_cases:
        case_id = str(case["caseId"])
        case_root = faults_root / case_id
        event_path = case_root / "event.json"
        original_event = output / str(case["injectionEvidenceRef"])
        _write(event_path, json.loads(original_event.read_text()))
        binding = binding_by_type[str(case["faultType"])]
        request_stable: dict[str, object] = {
            "schema": "quwoquan_data.runtime_fault_request",
            "caseId": case_id,
            "sessionRef": session_ref,
            "sessionDigest": session["receiptDigest"],
            "rootExecutionId": plan["rootExecutionId"],
            "runId": RUN_ID,
            "generation": GENERATION,
            "fencingToken": FENCING_TOKEN,
            "faultType": case["faultType"],
            "carrier": case["carrier"],
            "executionId": case["executionId"],
            "jobId": case["jobId"],
            "providerId": binding["providerId"],
            "providerConfigurationDigest": binding["configurationDigest"],
            "requestedAt": case["faultEventAt"],
        }
        request = _signed(request_stable, digest_field="requestDigest")
        request_path = case_root / "request.json"
        _write(request_path, request)
        provider_ref = None
        provider_sha = None
        if case["faultType"] != "worker_termination":
            provider_path = case_root / "provider-evidence.json"
            _write(provider_path, {"caseId": case_id, "status": "triggered"})
            provider_ref = provider_path.relative_to(output).as_posix()
            provider_sha = _file_digest(provider_path)
        receipt_stable: dict[str, object] = {
            "schema": "quwoquan_data.runtime_fault_case_receipt",
            "caseId": case_id,
            "requestRef": request_path.relative_to(output).as_posix(),
            "requestDigest": request["requestDigest"],
            "sessionRef": session_ref,
            "sessionDigest": session["receiptDigest"],
            "rootExecutionId": plan["rootExecutionId"],
            "runId": RUN_ID,
            "generation": GENERATION,
            "fencingToken": FENCING_TOKEN,
            "faultType": case["faultType"],
            "carrier": case["carrier"],
            "executionId": case["executionId"],
            "jobId": case["jobId"],
            "actionStatus": "triggered",
            "actionResultCode": "DATA.RUNTIME_EVIDENCE.FIXTURE_TRIGGERED",
            "actionTriggeredAt": case["faultEventAt"],
            "faultEventAt": case["faultEventAt"],
            "eventRef": event_path.relative_to(output).as_posix(),
            "eventSha256": _file_digest(event_path),
            "queueEventEvidenceDigest": "sha256:" + "8" * 64,
            "providerEvidenceRef": provider_ref,
            "providerEvidenceSha256": provider_sha,
            "recordedAt": case["faultEventAt"],
        }
        _write(
            case_root / "receipt.json",
            _signed(receipt_stable, digest_field="receiptDigest"),
        )
    return session_path, samples_root, faults_root


def _execution_id(carrier: str, sequence: int = 2) -> str:
    return f"20260805--travel-{carrier}-m100--china--scale-{sequence:03d}"


def _target_set(execution_id: str) -> dict[str, object]:
    return {
        "executionId": execution_id,
        "selectionPolicy": "frozen",
        "sourceRef": "quwoquan_data/reference/travel/entities/china",
        "entityCatalogDigest": CATALOG_DIGEST,
        "targetCount": 1,
        "targetRefs": ["地点/景区/测试实体"],
        "targets": [{"name": "测试实体", "entityType": "地点/景区"}],
    }


def _manifest(execution_id: str, *, retry_of: str | None) -> dict[str, object]:
    target_set = _target_set(execution_id)
    return {
        "executionId": execution_id,
        "familyRef": {"ref": "content/travel/test", "sha256": "c" * 64},
        "sourceDigest": SOURCE_DIGEST_DOCUMENT,
        "modelBinding": {
            "provider": "codex_sdk",
            "authorModel": "gpt-5.6-terra",
            "authorModelFamily": "gpt",
            "authorModelParameters": [],
            "reviewerModel": "gpt-5.6-terra",
            "reviewerModelFamily": "gpt",
            "reviewerModelParameters": [],
        },
        "runtimeProfileId": "semantic_agent_local_calibrated",
        "runtimeProfileDigest": runtime_profile_digest(
            "semantic_agent_local_calibrated"
        ),
        "semanticSelectionId": "default",
        "semanticRuntime": "local",
        "requestRef": "0.plan/request.json",
        "targetSetRef": "0.plan/target_set.json",
        "targetSetDigest": _digest(target_set, prefix=False),
        "retryOf": retry_of,
    }


def _job(
    *,
    execution_id: str,
    carrier: str,
    index: int,
    fault: bool,
    manual: bool,
    fault_event: str = "failed",
) -> dict[str, object]:
    job_id = f"{carrier[:2]}-semantic-{index:02d}"
    started = START.isoformat()
    failed = (START + timedelta(seconds=10 + index)).isoformat()
    requeued = (START + timedelta(seconds=20 + index)).isoformat()
    leased_again = (START + timedelta(seconds=30 + index)).isoformat()
    completed = (START + timedelta(hours=1, minutes=1)).isoformat()
    timings: list[dict[str, str]] = [{"event": "leased", "at": started}]
    attempt = 1
    if fault:
        timings.extend(
            [
                {"event": fault_event, "at": failed},
                {"event": "revived" if manual else "requeued", "at": requeued},
                {"event": "leased", "at": leased_again},
            ]
        )
        attempt = 2
    timings.append({"event": "succeeded", "at": completed})
    source_revision = "sha256:" + hashlib.sha256(job_id.encode()).hexdigest()
    reliable_payload = {
        "schema": "quwoquan.object_job",
        "jobId": job_id,
        "executionId": execution_id,
        "ref": f"/{carrier}/{index}",
        "stage": "author",
        "partitionKey": carrier,
        "entityRef": f"/entity/地点/景区/测试实体-{index}",
        "carrier": carrier,
        "sourceRevision": source_revision,
        "idempotencyKey": f"{execution_id}|{job_id}|author",
    }
    return {
        "schema": "quwoquan.object_job",
        "jobId": job_id,
        "executionId": execution_id,
        "ref": f"/{carrier}/{index}",
        "stage": "author",
        "queueBackend": "reliabletask",
        "partitionKey": carrier,
        "contentObjectDir": f"posts/{carrier}/test-{index}",
        "state": "succeeded",
        "attempt": attempt,
        "maxAttempts": 3,
        "maxStartupFailures": 3,
        "maxWallClockSeconds": 7200,
        "stuckThreshold": 3,
        "permissions": ["read_ref_packet", "write_draft"],
        "failureFingerprints": [],
        "mutexKey": job_id,
        "lease": None,
        "leaseExpiresEpoch": 0,
        "deadlineEpoch": 0,
        "notBeforeEpoch": 0,
        "sameRunRetryable": False,
        "startupFailureCount": 0,
        "stuckDetected": False,
        "lastIssue": None,
        "resultEnvelopeRequired": False,
        "resultEnvelopeRef": None,
        "gateVerdicts": [],
        "timings": timings,
        "meta": {"sourceRevision": source_revision},
        "reliableTaskRef": {
            "taskType": "data.content_object.execute",
            "queue": "reliabletask.data.content_supply",
            "dedupeKey": reliable_payload["idempotencyKey"],
            "idempotencyKey": reliable_payload["idempotencyKey"],
            "partitionKey": carrier,
            "payloadAllowlist": "object_job",
            "payload": reliable_payload,
        },
        "contentType": carrier,
        "carrier": carrier,
        "createdAt": started,
        "updatedAt": completed,
    }


def _publish_refs(carrier: str) -> dict[str, list[str]]:
    if carrier == "homepage":
        return {
            "entities": [f"地点/景区/homepage-{index:03d}" for index in range(100)],
            "posts": [],
        }
    return {
        "entities": [],
        "posts": [f"{carrier}/测试/test-{index:03d}/001" for index in range(100)],
    }


def _write_semantic_pair(
    tasks: Path,
    *,
    execution_id: str,
    carrier: str,
    published_ref: str,
) -> None:
    object_root = tasks / execution_id / (
        Path("entities") / published_ref
        if carrier == "homepage"
        else Path("posts") / published_ref
    )
    object_ref = (
        f"/entity/{published_ref}"
        if carrier == "homepage"
        else f"{carrier}-object-000"
    )
    draft_dir = object_root / "4.draft"
    output_path = draft_dir / "result.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("calibrated semantic output", encoding="utf-8")
    output_sha = _file_digest(output_path)
    author_run_id = f"{carrier}-terra-author-run"
    reviewer_run_id = f"{carrier}-terra-reviewer-run"
    _write(
        draft_dir / "agent_result_envelope.json",
        {
            "schema": "quwoquan.agent_result_envelope",
            "executionId": execution_id,
            "jobId": f"{carrier}-calibration-author",
            "ref": object_ref,
            "stage": "author",
            "agent": {
                "agentId": f"{carrier}-author",
                "runId": author_run_id,
                "provider": "codex_sdk",
                "model": "gpt-5.6-terra",
                "promptSha256": "sha256:" + "1" * 64,
            },
            "files": [
                {
                    "path": "result.txt",
                    "sha256": output_sha,
                    "role": "calibration_output",
                }
            ],
            "gates": [
                {
                    "schema": "quwoquan.gate_verdict",
                    "gateId": "semantic_author_calibration",
                    "decision": "passed",
                    "final": True,
                    "inputHash": "sha256:" + "1" * 64,
                    "outputHash": output_sha,
                    "issues": [],
                    "failureFingerprint": None,
                    "retryable": False,
                }
            ],
        },
    )
    _write(
        object_root / "5.review/reviewer_result.json",
        {
            "schema": "quwoquan_data.reviewer_result",
            "stage": "5.review",
            "executionId": execution_id,
            "executionBinding": "frozen",
            "objectRef": object_ref,
            "provider": "codex_sdk",
            "model": "gpt-5.6-terra",
            "modelFamily": "gpt",
            "runId": reviewer_run_id,
            "verdict": "passed",
            "issues": [],
            "findings": ["independent calibration passed"],
            "resultHash": "sha256:" + "2" * 64,
        },
    )


def _write_sol_calibration_runs(
    tasks: Path,
    *,
    execution_id: str,
    carrier: str,
    published_refs: list[str],
    accepted_count: int,
) -> None:
    selected = select_scale_calibration_refs(
        carrier=carrier,
        object_refs=published_refs,
        accepted_count=accepted_count,
    )
    for index, object_ref in enumerate(selected):
        _write(
            semantic_calibration_evidence_path(
                tasks / execution_id,
                object_ref=object_ref,
            ),
            {
                "schema": "quwoquan_data.reviewer_result",
                "stage": "5.review",
                "executionId": execution_id,
                "executionBinding": "frozen",
                "objectRef": object_ref,
                "provider": "codex_sdk",
                "model": "gpt-5.6-sol",
                "modelFamily": "gpt",
                "runId": f"{carrier}-sol-calibration-run-{index:03d}",
                "verdict": "passed",
                "issues": [],
                "findings": ["independent sampled calibration passed"],
                "resultHash": "sha256:" + f"{index + 10:064x}"[-64:],
            },
        )


def _scale_pool_fixture(
    output: Path,
    *,
    source_revision: str,
) -> tuple[dict[str, object], dict[str, object], str, dict[str, dict[str, object]], str]:
    candidates: list[dict[str, object]] = []
    for carrier in ("homepage", "article"):
        candidates.extend(
            _scale_pool_candidate(carrier, index, provider=f"{carrier}-source")
            for index in range(180)
        )
    image_providers = (
        ["Pinterest"] * 80
        + ["图虫"] * 20
        + ["Pexels"] * 50
        + ["Wikimedia Commons"] * 30
    )
    candidates.extend(
        _scale_pool_candidate("image", index, provider=provider)
        for index, provider in enumerate(image_providers)
    )
    candidates.extend(
        _scale_pool_candidate("video", index, provider="Pexels Videos")
        for index in range(100)
    )
    for row in candidates:
        row.update(
            {
                "sourceRevision": source_revision,
                "sourceDigest": SOURCE_DIGEST,
                "entityCatalogDigest": CATALOG_DIGEST,
            }
        )
        readiness = row.get("videoReadiness")
        if isinstance(readiness, dict):
            index = int(str(row["candidateId"]).rsplit("-", 1)[-1])
            readiness["popularityPercentile"] = round(index / 99, 6)
            readiness["comparisonBucket"]["candidateCount"] = 100
    pool_plan = build_scale_source_pool_plan(
        pool_id="research-m100-pool-001",
        target_scale="M100",
        source_revision=source_revision,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
        created_at=START.isoformat(),
        candidates=candidates,
    )
    pool_plan_path = output / "data/local/workspace/scale-source-pools/m100/plan.json"
    _write(pool_plan_path, pool_plan)
    evidence_root = output / "data/local/workspace/scale-source-pools/m100/evidence"
    for relative, body in EVIDENCE_PAYLOADS.values():
        destination = evidence_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
    binding: dict[str, object] = {
        "poolId": pool_plan["poolId"],
        "targetScale": pool_plan["targetScale"],
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "planRef": pool_plan_path.relative_to(output).as_posix(),
        "planDigest": pool_plan["planDigest"],
        "planFileSha256": _file_digest(pool_plan_path),
    }
    selections: dict[str, dict[str, object]] = {}
    for carrier in CARRIERS:
        stable_selection = {
            "carrier": carrier,
            "candidateIds": [f"{carrier}-{index:05d}" for index in range(100)],
            "candidateCount": 100,
        }
        selections[carrier] = {
            **stable_selection,
            "selectionDigest": _digest(stable_selection),
        }
    evidence_ref = evidence_root.relative_to(output).as_posix()
    snapshot_digest = bound_scale_source_pool_snapshot_digest(
        binding,
        evidence_root_ref=evidence_ref,
        output_root=output,
        lane_selections=selections,
    )
    return pool_plan, binding, evidence_ref, selections, snapshot_digest


def _fixture(tmp_path: Path) -> dict[str, Path | str | dict[str, object]]:
    output = tmp_path / "output"
    tasks = output / "data/tasks"
    release_root = output / "data/releases"
    _terra_preflight_path, terra_preflight_binding = ready_semantic_preflight(
        "default",
        output_root=output,
    )
    root_id = _execution_id("homepage")
    execution_ids = {carrier: _execution_id(carrier) for carrier in CARRIERS}
    source_revision = _digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
        }
    )
    empty_external_digest = _digest(
        {
            "schema": "quwoquan_data.campaign_external_input_set",
            "refs": [],
        }
    )
    lane_external_inputs = {
        carrier: {
            "executionId": execution_ids[carrier],
            "externalInputRefs": [],
            "externalInputsDigest": empty_external_digest,
        }
        for carrier in CARRIERS
    }
    (
        pool_plan,
        pool_binding,
        pool_evidence_ref,
        pool_selections,
        source_pool_snapshot_digest,
    ) = _scale_pool_fixture(output, source_revision=source_revision)
    plan_stable: dict[str, object] = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": root_id,
        "executionMode": "central",
        "scale": "M100",
        "gitBranch": "dev1.0",
        "gitCommitSha": "d" * 40,
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": terra_preflight_binding,
        "scaleSourcePool": pool_binding,
        "sourcePoolEvidenceRootRef": pool_evidence_ref,
        "laneSourcePoolSelections": pool_selections,
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": _digest(
            {
                "schema": "quwoquan_data.campaign_external_input_lanes",
                "lanes": lane_external_inputs,
            }
        ),
        "submissionDigests": {
            carrier: "sha256:" + str(index + 1) * 64
            for index, carrier in enumerate(CARRIERS)
        },
        "executionIds": execution_ids,
        "frozenAt": START.isoformat(),
    }
    plan = {**plan_stable, "planDigest": _digest(plan_stable)}
    campaign_root = (
        output
        / "data/local/workspace/content-campaign-submissions"
        / root_id
    )
    plan_path = campaign_root / "campaign_plan.json"
    _write(plan_path, plan)
    capsule_stable = {
        "schema": "quwoquan_data.content_campaign_source_capsule",
        "format": "source-snapshot-v1",
        "gitCommitSha": plan["gitCommitSha"],
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "roots": ["quwoquan_data"],
        "laneExternalInputs": {
            carrier: {
                "rootRef": f"external-inputs/{carrier}",
                "externalInputRefs": [],
                "externalInputsDigest": empty_external_digest,
            }
            for carrier in CARRIERS
        },
        "externalInputsDigest": plan["externalInputsDigest"],
        "scaleSourcePool": pool_binding,
        "sourcePoolSnapshotRootRef": "scale-source-pool",
        "sourcePoolSnapshotDigest": source_pool_snapshot_digest,
        "laneSourcePoolSelections": pool_selections,
    }
    capsule_digest = _digest(capsule_stable)
    capsule_root = output / "data/local/workspace/content-campaign-workspaces/content-addressed-capsules" / capsule_digest.removeprefix("sha256:")
    materialize_bound_scale_source_pool(
        pool_binding,
        evidence_root_ref=pool_evidence_ref,
        output_root=output,
        destination=capsule_root / "scale-source-pool",
        lane_selections=pool_selections,
        expected_snapshot_digest=source_pool_snapshot_digest,
    )
    _write(
        capsule_root / ".qwq_campaign_capsule.json",
        {**capsule_stable, "capsuleDigest": capsule_digest, "treeDigest": "sha256:" + "c" * 64},
    )
    capsule_ref = capsule_root.relative_to(output).as_posix()
    report_lane = lambda carrier: {
        "executionId": execution_ids[carrier],
        "status": "finalized",
        "phase": "publish",
        "reviewReturnCode": 0,
        "publishReturnCode": 0,
        "sourceCapsuleRef": capsule_ref,
        "sourceCapsuleDigest": capsule_digest,
        "sourceCapsuleCommitSha": plan["gitCommitSha"],
        "sourceCapsuleSourceDigest": SOURCE_DIGEST,
        "sourceCapsuleReadOnly": True,
        "executionRootRef": f"data/tasks/{execution_ids[carrier]}",
        "cleanupStatus": "cleaned",
        "approvedQuota": 100,
        "qualifiedCount": 100,
        "finalizedCount": 100,
        "selectedCount": 100,
        "discardedCount": 0,
        "shortfallCount": 0,
        "error": None,
    }
    _write(
        campaign_root / "campaign_report.json",
        {
            "schema": "quwoquan_data.content_campaign_report",
            "rootExecutionId": root_id,
            "campaignRunId": f"{root_id}-run",
            "campaignGeneration": 1,
            "campaignFencingToken": FENCING_TOKEN,
            "status": "succeeded",
            "phase": "completed",
            "planDigest": plan["planDigest"],
            "gitBranch": plan["gitBranch"],
            "gitCommitSha": plan["gitCommitSha"],
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
            "lanes": {carrier: report_lane(carrier) for carrier in CARRIERS},
            "failure": None,
            "startedAt": START.isoformat(),
            "updatedAt": (START + timedelta(seconds=3720)).isoformat(),
        },
    )

    fault_cases: list[dict[str, object]] = []
    fault_types = (
        "worker_termination",
        "lease_expiry",
        "redis_restart",
        "mongo_reconnect",
        "provider_timeout",
        "provider_rate_limit",
    )
    fault_events = {
        "worker_termination": "reclaimed",
        "lease_expiry": "reclaimed",
        "redis_restart": "reclaimed",
        "mongo_reconnect": "failed",
        "provider_timeout": "failed",
        "provider_rate_limit": "failed",
    }
    fault_evidence_root = output / "data/raw-scale-evidence/fault-events"
    manual_written = False
    for carrier in CARRIERS:
        execution_id = execution_ids[carrier]
        retry_of = _execution_id("image", 1) if carrier == "image" else None
        target_set = _target_set(execution_id)
        _write(tasks / execution_id / "0.plan/target_set.json", target_set)
        _write(
            tasks / execution_id / "execution_manifest.json",
            _manifest(execution_id, retry_of=retry_of),
        )
        if retry_of:
            _write(tasks / retry_of / "0.plan/target_set.json", _target_set(retry_of))
            _write(
                tasks / retry_of / "execution_manifest.json",
                _manifest(retry_of, retry_of=None),
            )
        refs = _publish_refs(carrier)
        first_published_ref = (
            refs["entities"][0] if carrier == "homepage" else refs["posts"][0]
        )
        _write_semantic_pair(
            tasks,
            execution_id=execution_id,
            carrier=carrier,
            published_ref=first_published_ref,
        )
        published_refs = [
            f"entities/{ref}" for ref in refs["entities"]
        ] or [f"posts/{ref}" for ref in refs["posts"]]
        _write_sol_calibration_runs(
            tasks,
            execution_id=execution_id,
            carrier=carrier,
            published_refs=published_refs,
            accepted_count=100,
        )
        publish_path = tasks / execution_id / "publish_ref.json"
        _write(
            publish_path,
            {
                "schema": "quwoquan_data.execution_publish_ref",
                "executionId": execution_id,
                "canonicalPublishRoot": "quwoquan_data/publish",
                "publishedRefs": refs,
            },
        )
        _write(
            campaign_root / "receipts" / f"{carrier}-publish.json",
            {
                "schema": "quwoquan_data.content_campaign_lane_receipt",
                "rootExecutionId": root_id,
                "executionId": execution_id,
                "carrier": carrier,
                "phase": "publish",
                "status": "finalized",
                "approvedQuota": 10 if carrier == "video" else 100,
                "qualifiedCount": 100,
                "finalizedCount": 100,
                "selectedCount": 100,
                "discardedCount": 0,
                "shortfallCount": 0,
                "executionPublishRef": publish_path.relative_to(output).as_posix(),
                "executionPublishSha256": _file_digest(publish_path),
                "campaignRunId": f"{root_id}-run",
                "campaignGeneration": 1,
                "campaignFencingToken": "sha256:" + "f" * 64,
                "discards": [],
            },
        )
        for index in range(10):
            fault = index < 5
            fault_type = fault_types[len(fault_cases) % len(fault_types)]
            manual = fault and not manual_written
            manual_written = manual_written or manual
            job = _job(
                execution_id=execution_id,
                carrier=carrier,
                index=index,
                fault=fault,
                manual=manual,
                fault_event=fault_events[fault_type],
            )
            _write(
                tasks
                / execution_id
                / "_shared/object_queue"
                / f"{job['jobId']}.json",
                job,
            )
            if fault:
                fault_at = next(
                    row["at"]
                    for row in job["timings"]
                    if row["event"] == fault_events[fault_type]
                )
                case_id = f"case-{carrier}-{index}"
                event_path = fault_evidence_root / f"{case_id}.json"
                _write(
                    event_path,
                    {
                        "schema": "quwoquan_data.fault_injection_event",
                        "caseId": case_id,
                        "faultType": fault_type,
                        "carrier": carrier,
                        "executionId": execution_id,
                        "jobId": job["jobId"],
                        "triggeredAt": fault_at,
                    },
                )
                fault_cases.append(
                    {
                        "caseId": case_id,
                        "faultType": fault_type,
                        "carrier": carrier,
                        "executionId": execution_id,
                        "jobId": job["jobId"],
                        "faultEventAt": fault_at,
                        "injectionEvidenceRef": event_path.relative_to(output).as_posix(),
                        "injectionEvidenceSha256": _file_digest(event_path),
                    }
                )

    release = release_root / "research-release"
    image_assets = [
        {
            "assetId": f"professional-image-{index:03d}",
            "objectRef": f"posts/image/测试/test-{index:03d}/001",
            "acquisitionStatus": "acquired",
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
            "sourceUrl": (
                f"https://images.pinterest.example/original/{index:03d}.jpg"
                if index < 60
                else f"https://photo.tuchong.example/original/{index:03d}.jpg"
            ),
            "platform": "pinterest" if index < 60 else "tuchong",
            "creator": f"Professional Photographer {index:03d}",
            "capturedAt": "2026-08-05T00:00:00Z",
            "contentSha256": "sha256:" + f"{index + 1000:064x}"[-64:],
            "license": "unknown",
            "termsUrl": (
                "https://policy.pinterest.com/terms-of-service"
                if index < 60
                else "https://tuchong.com/info/terms"
            ),
            "authorizationProof": "",
            "rightsIssues": ["authorization_required"],
            "generated": False,
        }
        for index in range(100)
    ]
    authorization_ids = [str(row["assetId"]) for row in image_assets]
    _write(
        release / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": "research-release",
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "containsUnverifiedAssets": True,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 100,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": authorization_ids,
            "researchAcceptedCount": 400,
            "commercialAcceptedCount": 0,
            "canonicalMerkle": "sha256:" + "e" * 64,
            "executionIds": list(execution_ids.values()),
            "sourceRevision": source_revision,
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
            "sourceDigests": [SOURCE_DIGEST_DOCUMENT],
        },
    )
    _write(
        release / "payload/asset_admission.json",
        {
            "schema": "quwoquan_data.release_asset_admission",
            "releaseId": "research-release",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "containsUnverifiedAssets": True,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 100,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": authorization_ids,
            "researchAcceptedCount": 400,
            "commercialAcceptedCount": 0,
            "carrierCounts": [
                {
                    "carrier": carrier,
                    "objectCount": 100,
                    "assetCount": 100 if carrier == "image" else 0,
                    "researchAcceptedCount": 100,
                    "commercialAcceptedCount": 0,
                }
                for carrier in CARRIERS
            ],
            "articleMediaCoverage": {
                "articleCount": 100,
                "illustratedCount": 90,
                "textOnlyCount": 10,
                "illustratedRate": 0.9,
                "textOnlyRate": 0.1,
            },
            "sourceAssetCounts": [
                {
                    "displayName": "Pinterest",
                    "provider": "pinterest",
                    "plannedAssetCount": 60,
                    "discoveredAssetCount": 60,
                    "downloadedAssetCount": 60,
                    "acceptedAssetCount": 60,
                    "rejectedAssetCount": 0,
                    "verifiedAssetCount": 0,
                    "unverifiedAssetCount": 60,
                    "restrictedAssetCount": 0,
                    "unknownAssetCount": 0,
                },
                {
                    "displayName": "图虫",
                    "provider": "tuchong",
                    "plannedAssetCount": 40,
                    "discoveredAssetCount": 40,
                    "downloadedAssetCount": 40,
                    "acceptedAssetCount": 40,
                    "rejectedAssetCount": 0,
                    "verifiedAssetCount": 0,
                    "unverifiedAssetCount": 40,
                    "restrictedAssetCount": 0,
                    "unknownAssetCount": 0,
                },
            ],
            "assets": image_assets,
        },
    )
    _write_ranked_release_videos(
        release,
        count=100,
        execution_id=execution_ids["video"],
        source_revision=source_revision,
        refs=_publish_refs("video")["posts"],
    )
    for carrier in ("article", "image"):
        for raw_ref in _publish_refs(carrier)["posts"]:
            _write(
                release / "payload/objects/posts" / raw_ref / "manifest.json",
                {"contentType": carrier},
            )
    _write(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": "research-release",
            "desiredRefs": {
                "creators": [],
                "entities": _publish_refs("homepage")["entities"],
                "posts": [
                    raw_ref
                    for carrier in ("article", "image", "video")
                    for raw_ref in _publish_refs(carrier)["posts"]
                ],
                "tags": [],
            },
        },
    )

    session_path, samples_root, faults_root = _write_runtime_receipts(
        output=output,
        campaign_root=campaign_root,
        plan_path=plan_path,
        plan=plan,
        fault_cases=fault_cases,
    )
    calibration_preflight_path, _calibration_preflight_binding = (
        ready_semantic_preflight("sol_calibration", output_root=output)
    )
    return {
        "output": output,
        "tasks": tasks,
        "releaseRoot": release_root,
        "planPath": plan_path,
        "sessionPath": session_path,
        "samplesRoot": samples_root,
        "faultsRoot": faults_root,
        "calibrationPreflightReceiptPath": calibration_preflight_path,
        "campaignRoot": campaign_root,
        "plan": plan,
    }


def _write_evidence(
    fixture: dict[str, object],
    *,
    calibration_preflight_receipt_path: Path | None = None,
) -> tuple[dict[str, object], Path]:
    return write_campaign_scale_evidence(
        evidence_id="scale-evidence-1",
        release_id="research-release",
        campaign_plan_path=fixture["planPath"],
        runtime_session_path=fixture["sessionPath"],
        calibration_preflight_receipt_path=(
            calibration_preflight_receipt_path
            or fixture["calibrationPreflightReceiptPath"]
        ),
        tasks_root=fixture["tasks"],
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )


def test_cumulative_scale_context_binds_predecessor_and_current_execution_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    release_root = output / "data/releases"
    predecessor_release = release_root / "predecessor-release"
    source_revision = _digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
        }
    )
    predecessor_ids = {carrier: _execution_id(carrier) for carrier in CARRIERS}
    current_ids = {
        carrier: _execution_id(carrier).replace("-m100--", "-m1000--")
        for carrier in CARRIERS
    }
    predecessor_header = {
        "schema": "quwoquan_data.release",
        "releaseId": "predecessor-release",
        "sourceOwner": "qwq_data",
        "releaseKind": "content",
        "releaseClass": "research",
        "productLifecycleState": "research",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 0,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 4,
        "commercialAcceptedCount": 0,
        "canonicalMerkle": "sha256:" + "e" * 64,
        "executionIds": list(predecessor_ids.values()),
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "sourceDigests": [SOURCE_DIGEST_DOCUMENT],
    }
    _write(predecessor_release / "payload/release.json", predecessor_header)
    _write(
        predecessor_release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": "predecessor-release",
            "desiredRefs": {
                "entities": ["地点/景区/predecessor"],
                "posts": [
                    "article/predecessor/001",
                    "image/predecessor/001",
                    "video/predecessor/001",
                ],
                "creators": [],
                "tags": [],
            },
        },
    )
    manifest_digest = campaign_scale_cumulative.payload_digest(predecessor_release)
    predecessor_reference = {
        "promotionId": "promotion-m100",
        "releaseId": "predecessor-release",
        "manifestDigest": manifest_digest,
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "targetScale": "M100",
        "receiptRef": "data/local/workspace/promotions/promotion-m100.json",
        "receiptDigest": "sha256:" + "c" * 64,
    }
    monkeypatch.setattr(
        campaign_scale_cumulative,
        "load_predecessor_promotion",
        lambda *_args, **_kwargs: (
            predecessor_reference,
            {carrier: 1 for carrier in CARRIERS},
        ),
    )
    plan = {
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "executionIds": current_ids,
    }
    current_header = {
        **predecessor_header,
        "releaseId": "current-release",
        "executionIds": [*predecessor_ids.values(), *current_ids.values()],
    }

    scale, predecessor, counts, carried_ids, release_ids, refs = (
        campaign_scale_cumulative.scale_context(
            target_scale="M1000",
            predecessor_promotion_path=output / predecessor_reference["receiptRef"],
            plan=plan,
            header=current_header,
            release_root=release_root,
            output_root=output,
        )
    )

    assert scale == "M1000"
    assert predecessor == predecessor_reference
    assert counts == {carrier: 1 for carrier in CARRIERS}
    assert carried_ids == sorted(predecessor_ids.values())
    assert release_ids == sorted(current_header["executionIds"])
    assert {carrier: len(refs[carrier]) for carrier in CARRIERS} == {
        carrier: 1 for carrier in CARRIERS
    }

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="predecessor carried plus current four lanes",
    ):
        campaign_scale_cumulative.scale_context(
            target_scale="M1000",
            predecessor_promotion_path=output / predecessor_reference["receiptRef"],
            plan=plan,
            header={**current_header, "executionIds": list(current_ids.values())},
            release_root=release_root,
            output_root=output,
        )


def test_campaign_scale_evidence_records_m100_as_zero_carried_cumulative_baseline(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    evidence, path = _write_evidence(fixture)

    loaded, _resource, _fault = load_campaign_scale_evidence(
        path,
        output_root=fixture["output"],
    )
    assert loaded == evidence
    assert evidence["targetScale"] == "M100"
    assert evidence["predecessorCarriedExecutionIds"] == []
    assert evidence["releaseExecutionIds"] == sorted(
        fixture["plan"]["executionIds"].values()
    )
    assert [row["predecessorCarriedCount"] for row in evidence["lanes"]] == [0] * 4
    assert [row["newFinalizedCount"] for row in evidence["lanes"]] == [100] * 4
    assert [row["totalUniqueFinalizedCount"] for row in evidence["lanes"]] == [
        100
    ] * 4
    assert evidence["scaleStartedAt"] == START.isoformat()
    assert evidence["scaleCompletedAt"] == (
        START + timedelta(hours=1, minutes=2)
    ).isoformat()
    assert evidence["wallClockBudgetSeconds"] is None
    assert evidence["wallClockSeconds"] == 3720


def test_campaign_scale_source_pool_blocks_predecessor_candidate_reuse(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    evidence, evidence_path = _write_evidence(fixture)
    promotion, promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-source-pool-lineage",
        campaign_evidence_path=evidence_path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )
    assert promotion["sourcePoolDigest"] == evidence["sourcePoolDigest"]
    assert evidence["predecessorSourcePoolDigests"] == []

    current_pool = json.loads(json.dumps(evidence["sourcePool"]))
    current_pool["poolId"] = "research-m1000-pool-001"
    current_pool["targetScale"] = "M1000"
    with pytest.raises(CampaignScaleEvidenceError, match="POOL_SHORTFALL.*reused"):
        source_pool_lineage_fields(
            source_pool_fields={
                "sourcePool": current_pool,
                "sourcePoolDigest": _digest(current_pool),
            },
            target_scale="M1000",
            predecessor_promotion_path=promotion_path,
            output_root=fixture["output"],
        )


def test_cumulative_scale_wall_clock_uses_predecessor_promotion_and_hard_budgets(
    tmp_path: Path,
) -> None:
    predecessor_path = tmp_path / "predecessor-promotion.json"
    _write(predecessor_path, {"recordedAt": START.isoformat()})
    plan = {"frozenAt": (START - timedelta(days=30)).isoformat()}

    at_budget = campaign_scale_cumulative.scale_timing_fields(
        target_scale="M1000",
        plan=plan,
        predecessor_promotion_path=predecessor_path,
        resource={
            "allSemanticJobsTerminalAt": (START + timedelta(days=2)).isoformat(),
            "terminalResidualSampleAt": (START + timedelta(days=3)).isoformat(),
        },
    )

    assert at_budget == {
        "scaleStartedAt": START.isoformat(),
        "scaleCompletedAt": (START + timedelta(days=3)).isoformat(),
        "wallClockBudgetSeconds": 259200,
        "wallClockSeconds": 259200,
    }
    with pytest.raises(
        CampaignScaleEvidenceError,
        match="DATA.SCALE.ATTAINMENT_SHORTFALL",
    ):
        campaign_scale_cumulative.scale_timing_fields(
            target_scale="M1000",
            plan=plan,
            predecessor_promotion_path=predecessor_path,
            resource={
                "terminalResidualSampleAt": (
                    START + timedelta(seconds=259201)
                ).isoformat()
            },
        )
    with pytest.raises(
        CampaignScaleEvidenceError,
        match="DATA.SCALE.M10000_WALL_CLOCK_BUDGET_EXCEEDED",
    ):
        campaign_scale_cumulative.scale_timing_fields(
            target_scale="M10000",
            plan=plan,
            predecessor_promotion_path=predecessor_path,
            resource={
                "terminalResidualSampleAt": (
                    START + timedelta(seconds=604801)
                ).isoformat()
            },
        )


def test_promotion_timing_revalidates_campaign_projection_and_typed_budgets() -> None:
    m1000_completed = START + timedelta(seconds=259200)
    evidence = {
        "targetScale": "M1000",
        "scaleStartedAt": START.isoformat(),
        "scaleCompletedAt": m1000_completed.isoformat(),
        "wallClockBudgetSeconds": 259200,
        "wallClockSeconds": 259200,
    }

    assert validate_promotion_timing(
        target_scale="M1000",
        evidence=evidence,
        resource_evidence={"terminalResidualSampleAt": m1000_completed.isoformat()},
    ) == {
        "scaleStartedAt": START.isoformat(),
        "scaleCompletedAt": m1000_completed.isoformat(),
        "wallClockBudgetSeconds": 259200,
        "wallClockSeconds": 259200,
    }

    exceeded = START + timedelta(seconds=259201)
    with pytest.raises(
        ResearchScalePromotionTimingError,
        match="DATA.SCALE.ATTAINMENT_SHORTFALL",
    ):
        validate_promotion_timing(
            target_scale="M1000",
            evidence={
                **evidence,
                "scaleCompletedAt": exceeded.isoformat(),
                "wallClockSeconds": 259201,
            },
            resource_evidence={"terminalResidualSampleAt": exceeded.isoformat()},
        )

    m10000_exceeded = START + timedelta(seconds=604801)
    with pytest.raises(
        ResearchScalePromotionTimingError,
        match="DATA.SCALE.M10000_WALL_CLOCK_BUDGET_EXCEEDED",
    ):
        validate_promotion_timing(
            target_scale="M10000",
            evidence={
                **evidence,
                "targetScale": "M10000",
                "scaleCompletedAt": m10000_exceeded.isoformat(),
                "wallClockBudgetSeconds": 604800,
                "wallClockSeconds": 604801,
            },
            resource_evidence={
                "terminalResidualSampleAt": m10000_exceeded.isoformat()
            },
        )


def test_promotion_writer_preserves_typed_wall_clock_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)

    def block_timing(**_kwargs: object) -> dict[str, object]:
        raise ResearchScalePromotionTimingError(
            "DATA.SCALE.M10000_WALL_CLOCK_BUDGET_EXCEEDED: governed timing blocker"
        )

    monkeypatch.setattr(
        research_scale_promotion_module,
        "validate_promotion_timing",
        block_timing,
    )
    with pytest.raises(
        ResearchScalePromotionError,
        match="DATA.SCALE.M10000_WALL_CLOCK_BUDGET_EXCEEDED",
    ):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-wall-clock-blocked",
            campaign_evidence_path=path,
            release_root=fixture["releaseRoot"],
            output_root=fixture["output"],
        )


def test_campaign_scale_evidence_derives_real_soak_faults_and_retry_chain(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    evidence, path = _write_evidence(fixture)

    assert path == (
        campaign_scale_evidence_root(output_root=fixture["output"])
        / "research-release/scale-evidence-1/campaign-scale.json"
    )
    assert evidence["status"] == "passed"
    assert evidence["targetScale"] == "M100"
    assert evidence["predecessorCarriedExecutionIds"] == []
    assert evidence["releaseExecutionIds"] == sorted(
        fixture["plan"]["executionIds"].values()
    )
    assert "predecessorPromotion" not in evidence
    assert [row["predecessorCarriedCount"] for row in evidence["lanes"]] == [0] * 4
    assert [row["newFinalizedCount"] for row in evidence["lanes"]] == [100] * 4
    assert [row["totalUniqueFinalizedCount"] for row in evidence["lanes"]] == [
        100
    ] * 4
    calibration_binding = evidence["calibrationPreflightReceipt"]
    assert calibration_binding["receiptRef"] == (
        fixture["calibrationPreflightReceiptPath"]
        .relative_to(fixture["output"])
        .as_posix()
    )
    calibration_receipt = json.loads(
        fixture["calibrationPreflightReceiptPath"].read_text(encoding="utf-8")
    )
    assert calibration_binding["receiptId"] == calibration_receipt["receiptId"]
    assert calibration_binding["selectionDigest"] == calibration_receipt[
        "selectionDigest"
    ]
    assert calibration_receipt["semanticSelectionId"] == "sol_calibration"
    assert calibration_receipt["provider"] == "codex_sdk"
    assert calibration_receipt["model"] == "gpt-5.6-sol"
    assert calibration_receipt["executionAdmissionReady"] is True
    assert evidence["duplicateAssetCount"] == 0
    assert evidence["crossLaneWriteCount"] == 0
    image_lane = next(row for row in evidence["lanes"] if row["carrier"] == "image")
    assert image_lane["retryChain"] == [
        _execution_id("image"),
        _execution_id("image", 1),
    ]
    assert [
        row["semanticCalibration"]["authorModel"] for row in evidence["lanes"]
    ] == ["gpt-5.6-terra"] * 4
    assert [
        row["semanticCalibration"]["reviewerModel"] for row in evidence["lanes"]
    ] == ["gpt-5.6-terra"] * 4
    assert [
        row["semanticCalibration"]["calibrationModel"] for row in evidence["lanes"]
    ] == ["gpt-5.6-sol"] * 4
    assert [
        row["semanticCalibration"]["selectionPolicy"]["requiredSampleCount"]
        for row in evidence["lanes"]
    ] == [10] * 4
    assert [
        len(row["semanticCalibration"]["calibrationRuns"])
        for row in evidence["lanes"]
    ] == [10] * 4
    resource = json.loads((path.parent / "resource-soak.json").read_text())
    fault = json.loads((path.parent / "fault-injection.json").read_text())
    assert resource["durationSeconds"] == 3720
    assert resource["fourLaneOverlapSampleCount"] == 62
    assert resource["fourLaneOverlapDurationSeconds"] == 3660
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 3660
    assert resource["allSemanticJobsTerminal"] is True
    assert resource["allSemanticJobsTerminalAt"] == (
        START + timedelta(hours=1, minutes=1)
    ).isoformat()
    assert resource["terminalResidualSampleAt"] == (
        START + timedelta(hours=1, minutes=2)
    ).isoformat()
    assert resource["terminalResidualMeasuredAfterAllJobs"] is True
    assert resource["observedPeaks"]["controllerP95RssBytes"] < 512 * 1024**2
    assert resource["observedPeaks"]["totalP95RssBytes"] < 8 * 1024**3
    assert resource["observedPeaks"]["terminalResidualBytes"] == 80 * 1024**2
    assert resource["budgets"]["maxTemporaryWorkspaceBytes"] == (
        2 * resource["releasePayloadBytes"] + 2 * 1024**3
    )
    assert [
        row["semanticJobCount"] for row in resource["semanticJobsByLane"]
    ] == [10] * 4
    assert [
        row["semanticJobSucceededCount"]
        for row in resource["semanticJobsByLane"]
    ] == [10] * 4
    assert [
        row["semanticJobTerminalCount"]
        for row in resource["semanticJobsByLane"]
    ] == [10] * 4
    assert fault["recoveryEligibleCount"] == 20
    assert fault["automaticRecoveredCount"] == 19
    assert fault["automaticRecoveryRate"] == 0.95
    assert {row["faultType"] for row in fault["casesByFaultType"]} == {
        "worker_termination",
        "lease_expiry",
        "redis_restart",
        "mongo_reconnect",
        "provider_timeout",
        "provider_rate_limit",
    }
    assert all(
        row["recoveryEligibleCount"] >= 1 for row in fault["casesByFaultType"]
    )

    promotion, promotion_path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-1",
        campaign_evidence_path=path,
        release_root=fixture["releaseRoot"],
        output_root=fixture["output"],
    )
    assert promotion["targetScale"] == "M100"
    assert promotion["scaleStartedAt"] == START.isoformat()
    assert promotion["scaleCompletedAt"] == (
        START + timedelta(hours=1, minutes=2)
    ).isoformat()
    assert promotion["wallClockBudgetSeconds"] is None
    assert promotion["wallClockSeconds"] == 3720
    assert promotion["nextScaleEligible"] == "M1000"
    assert promotion["campaignEvidenceDigest"] == evidence["evidenceDigest"]
    assert promotion["carrierCounts"][-1]["targetCount"] == 10
    assert promotion["carrierCounts"][-1]["qualifiedCount"] == 100
    assert promotion["carrierCounts"][-1]["shortfallCount"] == 0
    assert promotion["statistics"]["objectPassRate"] == {
        "numerator": 400,
        "denominator": 400,
        "rate": 1.0,
    }
    assert promotion["statistics"]["illustratedRate"] == {
        "numerator": 90,
        "denominator": 100,
        "rate": 0.9,
    }
    assert promotion["statistics"]["automaticRecoveryRate"] == {
        "statistical": True,
        "nonBlocking": False,
        "status": "MEASURED",
        "eligibleCount": 20,
        "automaticCount": 19,
        "targetRate": 0.95,
        "rate": 0.95,
    }
    assert promotion["statistics"]["videoPopularity"]["statistical"] is True
    assert promotion["statistics"]["videoPopularity"]["nonBlocking"] is False
    assert promotion["statistics"]["videoPopularity"]["rankingCoverage"] == {
        "numerator": 100,
        "denominator": 100,
        "rate": 1.0,
    }
    assert promotion["statistics"]["videoPopularity"]["signalAvailability"] == [
        {"signal": signal, "numerator": 100, "denominator": 100, "rate": 1.0}
        for signal in ("play", "like", "comment", "share", "favorite")
    ]
    assert promotion["professionalImageSourceMix"]["acceptedImageAssetCount"] == 100
    assert promotion["professionalImageSourceMix"]["largestProvider"] == "pinterest"
    assert promotion["professionalImageSourceMix"]["pinterestAcceptedAssetCount"] == 60
    assert promotion["professionalImageSourceMix"]["tuchongAcceptedAssetCount"] == 40
    assert promotion["statistics"]["firstPassRate"] == {
        "numerator": 3,
        "denominator": 4,
        "rate": 0.75,
    }
    assert promotion["statistics"]["discardRate"] == {
        "numerator": 0,
        "denominator": 400,
        "rate": 0.0,
    }
    assert promotion["fourLaneOverlapDurationSeconds"] == 3660
    assert promotion["fourLaneLongestContinuousOverlapSeconds"] == 3660
    assert promotion["allSemanticJobsTerminalAt"] == resource[
        "allSemanticJobsTerminalAt"
    ]
    assert promotion["terminalResidualSampleAt"] == resource[
        "terminalResidualSampleAt"
    ]
    assert promotion_path == (
        research_scale_promotions_root(output_root=fixture["output"])
        / "research-release/promotion-1/research-m100.json"
    )
    assert promotion_path.is_file()

    repeated, repeated_path = _write_evidence(fixture)
    assert repeated == evidence
    assert repeated_path == path


def test_m100_promotion_blocks_unranked_video(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    release = fixture["releaseRoot"] / "research-release"
    rights_path = next((release / "payload/objects/posts/video").rglob("rights.json"))
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    receipt_ref = rights["assets"][0]["independentAssetReview"]["receiptRef"]
    receipt_path = fixture["output"] / receipt_ref
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    signals = receipt["assetSnapshot"]["popularitySignals"]
    signals.update(
        {
            "favoriteCount": None,
            "popularityScore": None,
            "popularityPercentile": None,
            "rankingEligible": False,
            "ineligibleReason": "incomplete_popularity_signals",
        }
    )
    receipt["receiptDigest"] = _digest(
        {key: value for key, value in receipt.items() if key != "receiptDigest"}
    )
    _write(receipt_path, receipt)
    rights["assets"][0]["independentAssetReview"].update(
        {
            "receiptDigest": receipt["receiptDigest"],
            "receiptFileSha256": _file_digest(receipt_path),
            "popularitySignalsDigest": _digest(signals),
        }
    )
    _write(rights_path, rights)
    _evidence, path = _write_evidence(fixture)

    with pytest.raises(
        ResearchScalePromotionError,
        match="DATA.SCALE.ATTAINMENT_SHORTFALL",
    ):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-unranked-video",
            campaign_evidence_path=path,
            release_root=fixture["releaseRoot"],
            output_root=fixture["output"],
        )


def test_campaign_scale_evidence_blocks_lane_receipt_identity_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipt = fixture["campaignRoot"] / "receipts/image-publish.json"
    payload = json.loads(receipt.read_text())
    payload["executionId"] = _execution_id("image", 1)
    _write(receipt, payload)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="publish receipt identity drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_terra_capacity_as_sol_calibration(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    terra_receipt_path, _terra_binding = ready_semantic_preflight(
        "default",
        output_root=fixture["output"],
    )

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="Sol calibration preflight receipt is not promotable.*expected selection",
    ):
        _write_evidence(
            fixture,
            calibration_preflight_receipt_path=terra_receipt_path,
        )


def test_campaign_scale_loader_rejects_missing_sol_preflight_binding(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["calibrationPreflightReceipt"]
    _write(path, payload)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match=r"(?s)schema violation:.*calibrationPreflightReceipt",
    ):
        load_campaign_scale_evidence(path, output_root=fixture["output"])


def test_campaign_scale_loader_rejects_sol_preflight_file_digest_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    receipt_path = fixture["calibrationPreflightReceiptPath"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["validUntil"] = "2099-01-01T00:00:00Z"
    _write(receipt_path, receipt)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="bound Sol calibration preflight receipt is invalid.*file digest drift",
    ):
        load_campaign_scale_evidence(path, output_root=fixture["output"])


def test_campaign_scale_evidence_rejects_cross_session_sample_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    sample_path = min(fixture["samplesRoot"].glob("*.json"))
    sample = json.loads(sample_path.read_text())
    sample["runId"] = "different-runtime-run"
    _write(sample_path, sample)
    _resign_receipt(sample_path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="resource sample/session identity drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_duplicate_sample_timestamp(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    sample_paths = sorted(fixture["samplesRoot"].glob("*.json"))
    first = json.loads(sample_paths[0].read_text())
    second = json.loads(sample_paths[1].read_text())
    second["capturedAt"] = first["capturedAt"]
    second["rawSample"]["capturedAt"] = first["capturedAt"]
    second["queueMeasurements"][0]["oldestReadyAt"] = first[
        "queueMeasurements"
    ][0]["oldestReadyAt"]
    _write(sample_paths[1], second)
    _resign_receipt(sample_paths[1])

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="duplicate identity or timestamp",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_runtime_session_source_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    session_path = fixture["sessionPath"]
    session = json.loads(session_path.read_text())
    session["sourceDigest"] = "sha256:" + "0" * 64
    _write(session_path, session)
    _resign_receipt(session_path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="runtime session campaign identity drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_cross_session_fault_receipt(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    receipt_path = min(fixture["faultsRoot"].glob("*/receipt.json"))
    receipt = json.loads(receipt_path.read_text())
    receipt["generation"] = 2
    _write(receipt_path, receipt)
    _resign_receipt(receipt_path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="fault case/session identity drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_rejects_auto_model_binding_at_manifest_contract(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    manifest_path = fixture["tasks"] / _execution_id("image") / "execution_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["modelBinding"].update(
        {
            "provider": "cursor_sdk",
            "authorModel": "auto",
            "authorModelFamily": "auto",
            "reviewerModel": "auto",
            "reviewerModelFamily": "auto",
        }
    )
    _write(manifest_path, manifest)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="schema violation",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_blocks_same_author_reviewer_run(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    object_root = (
        fixture["tasks"]
        / _execution_id("video")
        / "posts/video/测试/test-000/001"
    )
    author = json.loads(
        (object_root / "4.draft/agent_result_envelope.json").read_text()
    )
    reviewer_path = object_root / "5.review/reviewer_result.json"
    reviewer = json.loads(reviewer_path.read_text())
    reviewer["runId"] = author["agent"]["runId"]
    _write(reviewer_path, reviewer)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="DATA.AGENT.SCALE_CALIBRATION_REQUIRED",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_blocks_missing_sol_calibration_sample(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    carrier = "article"
    refs = [
        f"posts/{ref}"
        for ref in _publish_refs(carrier)["posts"]
    ]
    selected = select_scale_calibration_refs(
        carrier=carrier,
        object_refs=refs,
        accepted_count=100,
    )
    semantic_calibration_evidence_path(
        fixture["tasks"] / _execution_id(carrier),
        object_ref=selected[0],
    ).unlink()

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="DATA.AGENT.SCALE_CALIBRATION_REQUIRED",
    ):
        _write_evidence(fixture)


def test_zero_recovery_denominator_blocks_promotion(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for receipt_path in fixture["faultsRoot"].glob("*/receipt.json"):
        payload = json.loads(receipt_path.read_text())
        payload.update(
            {
                "actionStatus": "failed",
                "actionResultCode": "DATA.RUNTIME_EVIDENCE.FIXTURE_FAILED",
                "faultEventAt": None,
                "eventRef": None,
                "eventSha256": None,
                "queueEventEvidenceDigest": None,
            }
        )
        _write(receipt_path, payload)
        _resign_receipt(receipt_path)

    evidence, path = _write_evidence(fixture)
    fault = json.loads((path.parent / "fault-injection.json").read_text())
    assert evidence["status"] == "passed"
    assert fault["status"] == "passed"
    assert fault["automaticRecoveryStatus"] == "NOT_EXERCISED"
    assert fault["automaticRecoveryRate"] is None

    with pytest.raises(
        ResearchScalePromotionError,
        match="automatic recovery hard gate failed",
    ):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-statistical-recovery",
            campaign_evidence_path=path,
            release_root=fixture["releaseRoot"],
            output_root=fixture["output"],
        )


def test_low_automatic_recovery_rate_blocks_promotion(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for receipt_path in fixture["faultsRoot"].glob("*/receipt.json"):
        if receipt_path.parent.name.endswith("-0"):
            continue
        payload = json.loads(receipt_path.read_text())
        payload.update(
            {
                "actionStatus": "failed",
                "actionResultCode": "DATA.RUNTIME_EVIDENCE.FIXTURE_FAILED",
                "faultEventAt": None,
                "eventRef": None,
                "eventSha256": None,
                "queueEventEvidenceDigest": None,
            }
        )
        _write(receipt_path, payload)
        _resign_receipt(receipt_path)

    evidence, path = _write_evidence(fixture)
    fault = json.loads((path.parent / "fault-injection.json").read_text())

    assert evidence["status"] == "passed"
    assert fault["status"] == "passed"
    assert fault["recoveryEligibleCount"] == 4
    assert fault["automaticRecoveredCount"] == 3
    assert fault["automaticRecoveryRate"] == 0.75

    with pytest.raises(
        ResearchScalePromotionError,
        match="automatic recovery hard gate failed",
    ):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-low-statistical-recovery",
            campaign_evidence_path=path,
            release_root=fixture["releaseRoot"],
            output_root=fixture["output"],
        )


def test_resource_soak_requires_one_continuous_four_lane_hour(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    video_queue = (
        fixture["tasks"]
        / _execution_id("video")
        / "_shared/object_queue"
    )
    shortened_terminal = (START + timedelta(minutes=30)).isoformat()
    for job_path in video_queue.glob("*.json"):
        job = json.loads(job_path.read_text())
        job["timings"][-1]["at"] = shortened_terminal
        job["updatedAt"] = shortened_terminal
        _write(job_path, job)

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["fourLaneOverlapSampleCount"] > 1
    assert resource["fourLaneOverlapDurationSeconds"] == 1800
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 1800
    assert resource["status"] == "failed"
    assert evidence["status"] == "failed"


def test_resource_soak_requires_observation_window_to_cover_four_lane_hour(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    shifted_start = START + timedelta(hours=1, seconds=30)
    for index, receipt_path in enumerate(
        sorted(fixture["samplesRoot"].glob("*.json"))
    ):
        payload = json.loads(receipt_path.read_text())
        captured_at = shifted_start + timedelta(minutes=index)
        payload["capturedAt"] = captured_at.isoformat()
        payload["rawSample"]["capturedAt"] = captured_at.isoformat()
        payload["queueMeasurements"][0]["oldestReadyAt"] = (
            captured_at - timedelta(seconds=300)
        ).isoformat() if payload["rawSample"]["queueDepth"] else None
        _write(receipt_path, payload)
        _resign_receipt(receipt_path)

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["fourLaneOverlapSampleCount"] == 1
    assert resource["fourLaneOverlapDurationSeconds"] == 30
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 30
    assert resource["status"] == "failed"
    assert evidence["status"] == "failed"
    with pytest.raises(ResearchScalePromotionError, match="evidence is not passed"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-observation-window-blocked",
            campaign_evidence_path=path,
            release_root=fixture["releaseRoot"],
            output_root=fixture["output"],
        )


def test_resource_soak_rejects_sampling_gap_inside_four_lane_hour(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    sorted(fixture["samplesRoot"].glob("*.json"))[30].unlink()

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["maxSampleGapSeconds"] == 120
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 3660
    assert resource["status"] == "failed"
    assert evidence["status"] == "failed"


def test_resource_soak_requires_residual_sample_after_every_job_terminal(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for path in sorted(fixture["samplesRoot"].glob("*.json"))[61:]:
        path.unlink()

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["durationSeconds"] == 3600
    assert resource["fourLaneLongestContinuousOverlapSeconds"] == 3600
    assert resource["allSemanticJobsTerminal"] is True
    assert resource["terminalResidualMeasuredAfterAllJobs"] is False
    assert resource["status"] == "failed"
    assert evidence["status"] == "failed"


def test_resource_soak_requires_residual_sample_strictly_after_all_jobs(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    for path in sorted(fixture["samplesRoot"].glob("*.json"))[62:]:
        path.unlink()

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert resource["allSemanticJobsTerminalAt"] == resource[
        "terminalResidualSampleAt"
    ]
    assert resource["terminalResidualMeasuredAfterAllJobs"] is False
    assert resource["status"] == "failed"
    assert evidence["status"] == "failed"


def test_resource_soak_counts_non_terminal_semantic_job_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    job_path = (
        fixture["tasks"]
        / _execution_id("article")
        / "_shared/object_queue/ar-semantic-09.json"
    )
    job = json.loads(job_path.read_text())
    job["state"] = "failed"
    _write(job_path, job)

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())
    article = resource["semanticJobsByLane"][1]

    assert article["semanticJobCount"] == 10
    assert article["semanticJobSucceededCount"] == 9
    assert article["semanticJobTerminalCount"] == 9
    assert resource["allSemanticJobsTerminal"] is False
    assert resource["allSemanticJobsTerminalAt"] is None
    assert resource["status"] == "failed"
    assert evidence["status"] == "failed"


def test_resource_soak_enforces_hard_rss_and_terminal_cleanup_budgets(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    sample_path = max(fixture["samplesRoot"].glob("*.json"))
    payload = json.loads(sample_path.read_text())
    other_rss = sum(
        int(row["rssBytes"])
        for row in payload["processMeasurements"]
        if row["carrier"] != "video"
    )
    video = next(
        row for row in payload["processMeasurements"] if row["carrier"] == "video"
    )
    video["rssBytes"] = 11 * 1024**3 - other_rss
    payload["rawSample"]["videoWorkerMaxRssBytes"] = video["rssBytes"]
    payload["rawSample"]["totalRssBytes"] = 11 * 1024**3
    payload["rawSample"]["terminalResidualBytes"] = 101 * 1024**2
    staging = next(
        row
        for row in payload["workspaceMeasurements"]
        if row["kind"] == "transaction_staging"
    )
    execution = next(
        row
        for row in payload["workspaceMeasurements"]
        if row["kind"] == "execution"
    )
    staging["bytes"] = 101 * 1024**2
    execution["bytes"] = (
        payload["rawSample"]["temporaryWorkspaceBytes"] - staging["bytes"]
    )
    _write(sample_path, payload)
    _resign_receipt(sample_path)

    evidence, path = _write_evidence(fixture)
    resource = json.loads((path.parent / "resource-soak.json").read_text())

    assert evidence["status"] == "failed"
    assert resource["status"] == "failed"
    assert set(resource["budgetBreaches"]) == {
        "totalMaxRssBytes",
        "terminalResidualBytes",
    }


def test_campaign_loader_rederives_resource_evidence_after_valid_resign(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    resource_path = path.parent / "resource-soak.json"
    resource = json.loads(resource_path.read_text())
    resource["fourLaneOverlapDurationSeconds"] += 60
    _write(resource_path, resource)
    resigned_resource = _resign_evidence(resource_path)
    campaign = json.loads(path.read_text())
    campaign["resourceSoakEvidenceDigest"] = resigned_resource["evidenceDigest"]
    campaign["fourLaneOverlapDurationSeconds"] = resigned_resource[
        "fourLaneOverlapDurationSeconds"
    ]
    _write(path, campaign)
    _resign_evidence(path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="resource soak derived evidence drift",
    ):
        load_campaign_scale_evidence(path, output_root=fixture["output"])


def test_campaign_loader_rederives_aggregate_after_valid_resign(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    campaign = json.loads(path.read_text())
    campaign["articleIllustratedRate"] = 0.95
    _write(path, campaign)
    _resign_evidence(path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="campaign aggregate derived evidence drift",
    ):
        load_campaign_scale_evidence(path, output_root=fixture["output"])


def test_campaign_loader_rederives_fault_evidence_after_valid_resign(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    fault_path = path.parent / "fault-injection.json"
    fault = json.loads(fault_path.read_text())
    fault["automaticRecoveredCount"] = 20
    fault["manualRecoveredCount"] = 0
    fault["automaticRecoveryRate"] = 1.0
    for case in fault["cases"]:
        if case["outcome"] == "manual":
            case["outcome"] = "automatic"
    _write(fault_path, fault)
    resigned_fault = _resign_evidence(fault_path)
    campaign = json.loads(path.read_text())
    campaign["faultInjectionEvidenceDigest"] = resigned_fault["evidenceDigest"]
    _write(path, campaign)
    _resign_evidence(path)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="create-once fault_injection_evidence collision",
    ):
        load_campaign_scale_evidence(path, output_root=fixture["output"])


def test_fault_injection_rejects_typed_event_digest_drift(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    receipt_path = min(fixture["faultsRoot"].glob("*/receipt.json"))
    receipt = json.loads(receipt_path.read_text())
    event_path = fixture["output"] / receipt["eventRef"]
    event = json.loads(event_path.read_text())
    event["faultType"] = "provider_timeout"
    _write(event_path, event)

    with pytest.raises(
        CampaignScaleEvidenceError,
        match="fault injection event digest drift",
    ):
        _write_evidence(fixture)


def test_campaign_scale_evidence_marks_cross_lane_write_failed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    publish_path = fixture["tasks"] / _execution_id("article") / "publish_ref.json"
    publish = json.loads(publish_path.read_text())
    publish["publishedRefs"]["posts"][-1] = "image/测试/cross-lane/001"
    _write(publish_path, publish)

    evidence, _ = _write_evidence(fixture)

    assert evidence["status"] == "failed"
    assert evidence["crossLaneWriteCount"] == 1


def test_promotion_rechecks_subordinate_evidence_digest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _evidence, path = _write_evidence(fixture)
    resource_path = path.parent / "resource-soak.json"
    resource = json.loads(resource_path.read_text())
    resource["fourLaneOverlapSampleCount"] = 60
    _write(resource_path, resource)

    with pytest.raises(ResearchScalePromotionError, match="evidenceDigest drift"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-tampered",
            campaign_evidence_path=path,
            release_root=fixture["releaseRoot"],
            output_root=fixture["output"],
        )


def test_release_cli_exposes_canonical_campaign_scale_evidence_writer() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    register_parser(commands)

    parsed = parser.parse_args(
        [
            "release",
            "campaign-scale-evidence",
            "--evidence-id",
            "evidence-1",
            "--release-id",
            "research-release",
            "--target-scale",
            "M1000",
            "--predecessor-promotion",
            "/tmp/m100-promotion.json",
            "--campaign-plan",
            "/tmp/campaign-plan.json",
            "--runtime-session",
            "/tmp/runtime-session.json",
            "--calibration-preflight-receipt",
            "/tmp/sol-calibration-preflight.json",
        ]
    )

    assert parsed.release_command == "campaign-scale-evidence"
    assert parsed.evidence_id == "evidence-1"
    assert parsed.target_scale == "M1000"
    assert parsed.predecessor_promotion == "/tmp/m100-promotion.json"
    assert parsed.runtime_session == "/tmp/runtime-session.json"
    assert parsed.calibration_preflight_receipt == (
        "/tmp/sol-calibration-preflight.json"
    )

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "release",
                "campaign-scale-evidence",
                "--evidence-id",
                "handwritten-raw",
                "--release-id",
                "research-release",
                "--campaign-plan",
                "/tmp/campaign-plan.json",
                "--resource-samples",
                "/tmp/handwritten-samples.json",
                "--fault-cases",
                "/tmp/handwritten-faults.json",
            ]
        )
