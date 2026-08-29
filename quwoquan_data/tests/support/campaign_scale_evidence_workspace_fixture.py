"""campaign scale evidence 合约测试的 runtime 回执与全量 workspace fixture。

由 test_campaign_scale_evidence__derived_* 场景组测试文件共享；
从原单体测试文件逐字下沉，不改变任何 fixture 逻辑。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from content.execution.campaign.source_pool_binding import (
    materialize_bound_scale_source_pool,
)
from content.release.canonical.campaign_scale_evidence import (
    write_campaign_scale_evidence,
)
from content.release.canonical.object_source_identity import (
    source_identity_digest,
    source_identity_set,
)
from support.campaign_scale_evidence_fixture import (
    CARRIERS,
    CATALOG_DIGEST,
    EXECUTION_BUNDLE_DOCUMENT,
    FENCING_TOKEN,
    GENERATION,
    RUN_ID,
    SESSION_ID,
    SOURCE_DIGEST,
    SOURCE_DIGEST_DOCUMENT,
    START,
    _digest,
    _execution_id,
    _file_digest,
    _job,
    _manifest,
    _publish_refs,
    _scale_pool_fixture,
    _signed,
    _target_set,
    _write,
    _write_ranked_release_videos,
    _write_semantic_pair,
    _write_sol_calibration_runs,
)
from support.capacity_calibration_fixture import (
    synthetic_capacity_source_binding,
    synthetic_governed_execution_authority,
)
from support.semantic_preflight_fixture import ready_semantic_preflight


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
            "cpuPercent": 12.5,
            "isCursorSdkBridge": False,
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
                "cpuPercent": 8.0,
                "isCursorSdkBridge": False,
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
        "hostCpuPercent": round(
            sum(float(row["cpuPercent"]) for row in processes), 3
        ),
        "cursorBridgeProcessCount": sum(
            1 for row in processes if row["isCursorSdkBridge"] is True
        ),
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
    active_carriers = list(pool_plan["activeCarriers"])
    workloads = dict(pool_plan["workloadTargets"])
    plan_stable: dict[str, object] = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": root_id,
        "executionMode": "central",
        "scale": "M100",
        "workloadMode": pool_plan["workloadMode"],
        "activeCarriers": active_carriers,
        "workloads": workloads,
        "gitBranch": "dev1.0",
        "gitCommitSha": "d" * 40,
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "executionBundle": dict(EXECUTION_BUNDLE_DOCUMENT),
        "entityCatalogDigest": CATALOG_DIGEST,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": terra_preflight_binding,
        "executionAuthority": synthetic_governed_execution_authority(),
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
        "format": "source-capsule-v2",
        "gitBranch": plan["gitBranch"],
        "gitCommitSha": plan["gitCommitSha"],
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "executionBundle": dict(EXECUTION_BUNDLE_DOCUMENT),
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
        "deliveryPendingCount": 0,
        "deliveryIntentRefs": [],
        "error": None,
    }
    _write(
        campaign_root / "campaign_report.json",
        {
            "schema": "quwoquan_data.content_campaign_report",
            "rootExecutionId": root_id,
            "activeCarriers": active_carriers,
            "workloads": workloads,
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
            "revisionAudits": [],
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
                "canonicalPublishRoot": "canonical-publish",
                "publishedRefs": refs,
                "publishDiscards": [],
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
                "reviewQualifiedCount": 100,
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
                "publishDiscards": [],
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
    object_source_identities = [
        {
            "executionId": execution_id,
            "sourceRevision": source_revision,
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
        }
        for execution_id in execution_ids.values()
    ]
    source_identities, source_identity_set_digest = source_identity_set(
        object_source_identities
    )
    source_identity_digest_value = source_identity_digest(
        object_source_identities[0]
    )
    milestone_post_refs = {
        "article": _publish_refs("article")["posts"],
        "image": _publish_refs("image")["posts"],
        "video": _publish_refs("video")["posts"][:10],
    }
    release_contents = [
        {
            "contentId": f"content-{carrier}-{index:03d}",
            "version": 1,
            "postRef": raw_ref,
            "executionId": execution_ids[carrier],
            "sourceIdentityDigest": source_identity_digest_value,
        }
        for carrier, refs in milestone_post_refs.items()
        for index, raw_ref in enumerate(refs)
    ]
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
            "researchAcceptedCount": 310,
            "commercialAcceptedCount": 0,
            "canonicalMerkle": "sha256:" + "e" * 64,
            "executionIds": list(execution_ids.values()),
            "sourceDigests": [SOURCE_DIGEST_DOCUMENT],
            "sourceIdentities": source_identities,
            "sourceIdentitySetDigest": source_identity_set_digest,
            "selectionScope": "milestone",
            "milestone": "M100",
            "milestoneTargets": {
                "homepage": 100,
                "article": 100,
                "image": 100,
                "video": 10,
            },
            "releaseMode": "research",
            "poolDigest": "sha256:" + "d" * 64,
            "counts": {
                "article": 100,
                "image": 100,
                "video": 10,
                "total": 210,
            },
            "contents": release_contents,
            "authors": [],
            "buildResult": "completed",
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
            "researchAcceptedCount": 310,
            "commercialAcceptedCount": 0,
            "carrierCounts": [
                {
                    "carrier": carrier,
                    "objectCount": 10 if carrier == "video" else 100,
                    "assetCount": 100 if carrier == "image" else 0,
                    "researchAcceptedCount": 10 if carrier == "video" else 100,
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
        count=10,
        execution_id=execution_ids["video"],
        source_revision=source_revision,
        refs=milestone_post_refs["video"],
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
                    for raw_ref in milestone_post_refs[carrier]
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
