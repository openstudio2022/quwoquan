"""campaign scale evidence 合约测试共享常量与构建器。

由 test_campaign_scale_evidence__derived_* 场景组测试文件共享；
从原单体测试文件逐字下沉，不改变任何 fixture 逻辑。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from content.execution.campaign.source_pool_binding import (
    bound_scale_source_pool_snapshot_digest,
)
from content.execution.scale.semantic_promotion import (
    select_scale_calibration_refs,
    semantic_calibration_evidence_path,
)
from content.source.research.scale_source_pool import build_scale_source_pool_plan
from core.runtime_policy import runtime_profile_digest
from core.source_digest import SourceDigest

from quwoquan_data.tests.local_contract.source.test_scale_source_pool__milestone_readiness__contract__local_contract_test import (
    EVIDENCE_PAYLOADS,
)
from quwoquan_data.tests.local_contract.source.test_scale_source_pool__milestone_readiness__contract__local_contract_test import (
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
