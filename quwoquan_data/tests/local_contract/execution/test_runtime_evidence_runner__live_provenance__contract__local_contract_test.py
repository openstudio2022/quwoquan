from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from content.execution.campaign.runtime import (
    CampaignFenceError,
    lane_checkpoint_path,
    runtime_root,
    runtime_snapshot_path,
)
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.runtime_evidence.contract import (
    CARRIERS,
    FaultProviderBinding,
    ProcessObservation,
    ProviderBinding,
    RuntimeEvidenceError,
    RuntimeEvidenceIdentity,
    canonical_digest,
    create_runtime_evidence_session,
    session_root,
)
from content.execution.runtime_evidence.fault_adapters import unavailable_fault_adapter
from content.execution.runtime_evidence.faults import (
    CampaignWorkerTerminator,
    FaultActionResult,
    FaultActionTarget,
    finalize_fault_cases,
    inject_fault,
)
from content.execution.runtime_evidence.sampling import (
    FaultQueueEvent,
    QueueObservation,
    capture_resource_sample,
    finalize_resource_samples,
)
from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid
from support.capacity_calibration_fixture import (
    synthetic_capacity_source_binding,
    synthetic_governed_execution_authority,
)
from support.semantic_preflight_fixture import ready_semantic_preflight

ROOT_ID = "20260805--travel-homepage-p3--china--scale-901"
RUN_ID = "p3-runtime-evidence-run"
FENCING_TOKEN = "sha256:" + "f" * 64
IDENTITY = RuntimeEvidenceIdentity(ROOT_ID, RUN_ID, 7, FENCING_TOKEN)
EXECUTION_IDS = {
    carrier: (
        ROOT_ID
        if carrier == "homepage"
        else f"20260805--travel-{carrier}-p3--china--scale-901"
    )
    for carrier in CARRIERS
}
FAULT_TYPES = (
    "worker_termination",
    "lease_expiry",
    "redis_restart",
    "mongo_reconnect",
    "provider_timeout",
    "provider_rate_limit",
)
QUEUE_FAULT_EVENT_TIMEOUT_SECONDS = (
    active_runtime_policy().runtime_evidence.queue_fault_event_timeout_seconds
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output,
        publish_root=tmp_path / "publish",
        campaigns_root=output / "data/local/workspace/content-campaign-submissions",
        workspaces_root=output / "data/local/cache/content-campaign-workspaces",
    )


class FakeInspector:
    def __init__(self, rows: Mapping[int, ProcessObservation]) -> None:
        self.rows = dict(rows)

    def observe(self, pid: int) -> ProcessObservation:
        try:
            return self.rows[pid]
        except KeyError as exc:
            raise RuntimeEvidenceError(f"missing fake process: {pid}") from exc

    def observe_group(self, pgid: int) -> tuple[ProcessObservation, ...]:
        rows = tuple(row for row in self.rows.values() if row.pgid == pgid)
        if not rows:
            raise RuntimeEvidenceError(f"missing fake process group: {pgid}")
        return tuple(sorted(rows, key=lambda row: row.pid))


class FakeQueueProvider:
    def __init__(self, after_sample: Callable[[], None] | None = None) -> None:
        self.binding = ProviderBinding(
            "governed-test-queue",
            canonical_digest({"provider": "governed-test-queue", "version": 1}),
        )
        self.job_ids = {
            EXECUTION_IDS[carrier]: f"job-{carrier}-0001" for carrier in CARRIERS
        }
        self.after_sample = after_sample

    def sample(self, execution_ids: Mapping[str, str]) -> tuple[QueueObservation, ...]:
        observed = (_now() - timedelta(seconds=5)).isoformat()
        rows = tuple(
            QueueObservation(
                carrier=carrier,
                execution_id=str(execution_ids[carrier]),
                pending_job_timestamps=(observed,),
                ready_job_timestamps=(observed,),
                evidence_digest=canonical_digest(
                    {"carrier": carrier, "observed": observed}
                ),
                successful_job_count=2,
                terminal_job_count=3,
                observation_window_seconds=120,
                latency_milliseconds=(1000, 2000),
                provider_throttle_count=1,
                stuck_job_count=1,
            )
            for carrier in CARRIERS
        )
        if self.after_sample is not None:
            self.after_sample()
        return rows

    def assert_job_target(self, *, execution_id: str, job_id: str) -> None:
        if self.job_ids.get(execution_id) != job_id:
            raise RuntimeEvidenceError("fake queue job identity drift")

    def wait_for_fault_event(
        self,
        *,
        execution_id: str,
        job_id: str,
        fault_type: str,
        after: str,
        timeout_seconds: float,
    ) -> FaultQueueEvent:
        self.assert_job_target(execution_id=execution_id, job_id=job_id)
        event_at = max(_now(), datetime.fromisoformat(after) + timedelta(microseconds=1))
        return FaultQueueEvent(
            event_at=event_at.isoformat(),
            evidence_digest=canonical_digest(
                {
                    "executionId": execution_id,
                    "jobId": job_id,
                    "faultType": fault_type,
                    "eventAt": event_at.isoformat(),
                }
            ),
        )


class FakeFaultProvider:
    def __init__(
        self,
        binding: FaultProviderBinding,
        evidence_root: Path,
    ) -> None:
        self.binding = binding
        self.evidence_root = evidence_root
        self.call_count = 0

    def trigger(self, target: FaultActionTarget) -> FaultActionResult:
        self.call_count += 1
        evidence = self.evidence_root / f"{target.fault_type}-{self.call_count}.json"
        write_json(
            evidence,
            {
                "providerId": self.binding.provider_id,
                "faultType": target.fault_type,
                "executionId": target.execution_id,
                "jobId": target.job_id,
            },
        )
        return FaultActionResult(
            result_code="DATA.RUNTIME_EVIDENCE.TEST_ACTION_TRIGGERED",
            triggered_at=_now().isoformat(),
            provider_evidence_path=evidence,
        )


@dataclass(frozen=True)
class Fixture:
    runtime: CampaignRuntimePaths
    plan_path: Path
    inspector: FakeInspector
    queue: FakeQueueProvider
    worker_binding: FaultProviderBinding
    hook_attestation: Path


def _fixture(tmp_path: Path) -> Fixture:
    runtime = _runtime(tmp_path)
    _preflight_path, preflight_binding = ready_semantic_preflight(
        "default",
        output_root=runtime.output_root,
    )
    campaign = runtime_root(runtime, ROOT_ID).parent
    source_digest = "sha256:" + "a" * 64
    entity_digest = "sha256:" + "b" * 64
    source_revision = canonical_digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_digest,
        }
    )
    empty_inputs_digest = canonical_digest(
        {"schema": "quwoquan_data.campaign_external_input_set", "refs": []}
    )
    lane_inputs = {
        carrier: {
            "executionId": EXECUTION_IDS[carrier],
            "externalInputRefs": [],
            "externalInputsDigest": empty_inputs_digest,
        }
        for carrier in CARRIERS
    }
    stable_plan: dict[str, Any] = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": ROOT_ID,
        "executionMode": "central",
        "scale": "M100",
        "workloadMode": "milestone_preset",
        "activeCarriers": list(CARRIERS),
        "workloads": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "gitBranch": "dev1.0",
        "gitCommitSha": "1" * 40,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "7" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": entity_digest,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": preflight_binding,
        "executionAuthority": synthetic_governed_execution_authority(),
        "laneExternalInputs": lane_inputs,
        "externalInputsDigest": canonical_digest(
            {
                "schema": "quwoquan_data.campaign_external_input_lanes",
                "lanes": lane_inputs,
            }
        ),
        "submissionDigests": {
            carrier: "sha256:" + str(index + 1) * 64
            for index, carrier in enumerate(CARRIERS)
        },
        "executionIds": EXECUTION_IDS,
        "frozenAt": _now().isoformat(),
    }
    plan_path = campaign / "campaign_plan.json"
    write_json(plan_path, {**stable_plan, "planDigest": canonical_digest(stable_plan)})
    capsule = runtime.output_root / "data/local/cache/runtime-evidence-capsule"
    write_json(capsule / "manifest.json", {"capsule": "frozen"})
    observations: dict[int, ProcessObservation] = {}
    controller_pid = 9100
    observations[controller_pid] = ProcessObservation(
        pid=controller_pid,
        pgid=9000,
        command=f"python quwoquan_data/scripts/cli.py task execute {ROOT_ID}",
        start_token="controller-start",
        rss_bytes=100 * 1024**2,
        cpu_percent=12.5,
        open_fd_count=20,
    )
    snapshot = {
        "schema": "quwoquan_data.content_campaign_runtime_snapshot",
        **IDENTITY.as_document(),
        "status": "active",
        "phase": "run",
        "pid": controller_pid,
        "pgid": 9000,
        "hostname": "test-host",
        "leaseSeconds": 600,
        "heartbeatAt": _now().isoformat(),
        "updatedAt": _now().isoformat(),
        "lanes": {},
    }
    write_json(runtime_snapshot_path(runtime, ROOT_ID), snapshot)
    for index, carrier in enumerate(CARRIERS, start=1):
        execution_id = EXECUTION_IDS[carrier]
        pid = 9200 + index
        execution_root = runtime.output_root / "data/tasks" / execution_id
        write_json(execution_root / "payload.bin.json", {"carrier": carrier})
        updated_at = _now().isoformat()
        write_json(
            execution_root / "_shared/execution_state.json",
            {"executionId": execution_id, "updatedAt": updated_at},
        )
        write_json(
            lane_checkpoint_path(runtime, ROOT_ID, carrier),
            {
                "schema": "quwoquan_data.content_campaign_lane_checkpoint",
                **IDENTITY.as_document(),
                "carrier": carrier,
                "executionId": execution_id,
                "phase": "run",
                "status": "running",
                "capsuleRef": capsule.relative_to(runtime.output_root).as_posix(),
                "executionRoot": str(execution_root),
                "pid": pid,
                "pgid": pid,
                "updatedAt": updated_at,
            },
        )
        observations[pid] = ProcessObservation(
            pid=pid,
            pgid=pid,
            command=(
                "python quwoquan_data/scripts/cli.py task execute " + execution_id
            ),
            start_token=f"{carrier}-start",
            rss_bytes=(100 + index * 10) * 1024**2,
            cpu_percent=5.0 + index,
            open_fd_count=10 + index,
        )
    staging = (
        runtime.output_root
        / "data/local/workspace/object-transactions"
        / f"{EXECUTION_IDS['image']}--post-test"
        / "staging"
    )
    write_json(staging / "residual.json", {"residual": True})
    hook = runtime.output_root / "data/local/cache/runtime-provider-hook.json"
    return Fixture(
        runtime=runtime,
        plan_path=plan_path,
        inspector=FakeInspector(observations),
        queue=FakeQueueProvider(),
        worker_binding=FaultProviderBinding(
            "fake-worker-terminator",
            canonical_digest({"provider": "fake-worker-terminator"}),
            "worker_termination",
        ),
        hook_attestation=hook,
    )


def _session(
    fixture: Fixture,
    *,
    session_id: str,
    all_faults: bool,
) -> tuple[dict[str, Any], tuple[FaultProviderBinding, ...]]:
    bindings = [fixture.worker_binding]
    if all_faults:
        bindings.extend(
            FaultProviderBinding(
                f"governed-{fault_type}",
                canonical_digest({"provider": fault_type}),
                fault_type,
            )
            for fault_type in FAULT_TYPES
            if fault_type != "worker_termination"
        )
        hook_stable = {
            "schema": "quwoquan_data.runtime_provider_fault_test_hook_attestation",
            **IDENTITY.as_document(),
            "providerBindings": [
                binding.as_document()
                for binding in bindings
                if binding.fault_type
                in {"provider_timeout", "provider_rate_limit"}
            ],
            "issuedAt": (_now() - timedelta(seconds=1)).isoformat(),
            "expiresAt": (_now() + timedelta(minutes=10)).isoformat(),
        }
        write_json(
            fixture.hook_attestation,
            {
                **hook_stable,
                "attestationDigest": canonical_digest(hook_stable),
            },
        )
    document, _path = create_runtime_evidence_session(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id=session_id,
        campaign_plan_path=fixture.plan_path,
        inspector=fixture.inspector,
        queue_evidence_provider=fixture.queue.binding,
        fault_providers=bindings,
        provider_fault_test_hook_attestation=(
            fixture.hook_attestation if all_faults else None
        ),
    )
    return document, tuple(bindings)


def test_resource_samples_are_observed_create_once_and_raw_consumer_ready(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    session, _bindings = _session(
        fixture, session_id="resource-live-001", all_faults=False
    )
    first, first_path = capture_resource_sample(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id="resource-live-001",
        sample_id="sample-001",
        inspector=fixture.inspector,
        queue_provider=fixture.queue,
    )
    second, _second_path = capture_resource_sample(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id="resource-live-001",
        sample_id="sample-002",
        inspector=fixture.inspector,
        queue_provider=fixture.queue,
    )
    replay, replay_path = capture_resource_sample(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id="resource-live-001",
        sample_id="sample-001",
        inspector=fixture.inspector,
        queue_provider=fixture.queue,
    )

    assert replay == first
    assert replay_path == first_path
    assert first["sessionDigest"] == session["receiptDigest"]
    assert first["rawSample"]["controllerRssBytes"] == 100 * 1024**2
    assert first["rawSample"]["nonVideoWorkerMaxRssBytes"] == 130 * 1024**2
    assert first["rawSample"]["videoWorkerMaxRssBytes"] == 140 * 1024**2
    assert first["rawSample"]["queueDepth"] == 4
    assert first["rawSample"]["terminalResidualBytes"] > 0
    assert all(
        row["throughputPerHour"] == 60.0
        and row["latencyP95Milliseconds"] == 2000
        and row["providerThrottleCount"] == 1
        and row["stuckJobCount"] == 1
        for row in first["queueMeasurements"]
    )
    assert second["capturedAt"] != first["capturedAt"]

    video_worker = next(
        row for row in session["workers"] if row["carrier"] == "video"
    )
    child_pid = int(video_worker["pid"]) + 1000
    fixture.inspector.rows[child_pid] = ProcessObservation(
        pid=child_pid,
        pgid=int(video_worker["pgid"]),
        command="ffmpeg -i input.mp4 output.mp4",
        start_token="video-child-start",
        rss_bytes=60 * 1024**2,
        cpu_percent=18.0,
        open_fd_count=7,
    )
    third, _third_path = capture_resource_sample(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id="resource-live-001",
        sample_id="sample-child-003",
        inspector=fixture.inspector,
        queue_provider=fixture.queue,
    )
    assert third["rawSample"]["videoWorkerMaxRssBytes"] == 200 * 1024**2
    assert third["rawSample"]["totalRssBytes"] == (
        first["rawSample"]["totalRssBytes"] + 60 * 1024**2
    )
    assert third["rawSample"]["openFdCount"] == (
        first["rawSample"]["openFdCount"] + 7
    )
    assert len({row["pid"] for row in third["processMeasurements"]}) == len(
        third["processMeasurements"]
    )

    worker_pid = int(session["workers"][0]["pid"])
    original = fixture.inspector.rows[worker_pid]
    fixture.inspector.rows[worker_pid] = ProcessObservation(
        pid=original.pid,
        pgid=original.pgid,
        command=original.command + " --reused",
        start_token=original.start_token,
        rss_bytes=original.rss_bytes,
        cpu_percent=original.cpu_percent,
        open_fd_count=original.open_fd_count,
    )
    with pytest.raises(RuntimeEvidenceError, match="process identity changed"):
        capture_resource_sample(
            runtime=fixture.runtime,
            identity=IDENTITY,
            session_id="resource-live-001",
            sample_id="sample-003",
            inspector=fixture.inspector,
            queue_provider=fixture.queue,
        )

    snapshot_path = runtime_snapshot_path(fixture.runtime, ROOT_ID)
    snapshot = read_json(snapshot_path)
    snapshot["status"] = "completed"
    write_json(snapshot_path, snapshot)
    raw, raw_path = finalize_resource_samples(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id="resource-live-001",
    )
    assert raw_path.name == "resource-soak-samples.json"
    assert len(raw["samples"]) == 3
    assert_valid(raw, "release", "resource_soak_samples", label="raw samples")


def test_resource_sample_rechecks_fence_after_live_queue_observation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    session_id = "resource-generation-switch-001"
    sample_id = "sample-generation-switch-001"
    _session(fixture, session_id=session_id, all_faults=False)
    snapshot_path = runtime_snapshot_path(fixture.runtime, ROOT_ID)

    def switch_generation() -> None:
        snapshot = read_json(snapshot_path)
        snapshot["generation"] = IDENTITY.generation + 1
        snapshot["fencingToken"] = "sha256:" + "e" * 64
        write_json(snapshot_path, snapshot)

    fixture.queue.after_sample = switch_generation
    sample_path = (
        session_root(fixture.runtime, IDENTITY, session_id)
        / "samples"
        / f"{sample_id}.json"
    )

    with pytest.raises(CampaignFenceError, match="stale controller generation"):
        capture_resource_sample(
            runtime=fixture.runtime,
            identity=IDENTITY,
            session_id=session_id,
            sample_id=sample_id,
            inspector=fixture.inspector,
            queue_provider=fixture.queue,
        )
    assert not sample_path.exists()


def test_resource_sample_rechecks_lease_after_live_queue_observation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    session_id = "resource-lease-expiry-001"
    sample_id = "sample-lease-expiry-001"
    _session(fixture, session_id=session_id, all_faults=False)
    snapshot_path = runtime_snapshot_path(fixture.runtime, ROOT_ID)

    def expire_lease() -> None:
        snapshot = read_json(snapshot_path)
        snapshot["leaseSeconds"] = 1
        snapshot["heartbeatAt"] = (_now() - timedelta(seconds=2)).isoformat()
        write_json(snapshot_path, snapshot)

    fixture.queue.after_sample = expire_lease
    sample_path = (
        session_root(fixture.runtime, IDENTITY, session_id)
        / "samples"
        / f"{sample_id}.json"
    )

    with pytest.raises(RuntimeEvidenceError, match="lease is stale"):
        capture_resource_sample(
            runtime=fixture.runtime,
            identity=IDENTITY,
            session_id=session_id,
            sample_id=sample_id,
            inspector=fixture.inspector,
            queue_provider=fixture.queue,
        )
    assert not sample_path.exists()


def test_six_typed_faults_are_provider_bound_and_project_existing_raw_schema(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _document, bindings = _session(
        fixture, session_id="fault-live-001", all_faults=True
    )
    providers = {
        binding.fault_type: FakeFaultProvider(
            binding,
            fixture.runtime.output_root / "data/local/cache/provider-evidence",
        )
        for binding in bindings
    }
    first_receipt: dict[str, Any] | None = None
    for index, fault_type in enumerate(FAULT_TYPES):
        carrier = CARRIERS[index % len(CARRIERS)]
        execution_id = EXECUTION_IDS[carrier]
        receipt, _path = inject_fault(
            runtime=fixture.runtime,
            identity=IDENTITY,
            session_id="fault-live-001",
            case_id=f"case-{index:03d}",
            fault_type=fault_type,
            carrier=carrier,
            execution_id=execution_id,
            job_id=fixture.queue.job_ids[execution_id],
            inspector=fixture.inspector,
            queue_provider=fixture.queue,
            providers=providers,
            queue_event_timeout_seconds=QUEUE_FAULT_EVENT_TIMEOUT_SECONDS,
        )
        assert receipt["actionStatus"] == "triggered"
        assert receipt["queueEventEvidenceDigest"].startswith("sha256:")
        first_receipt = first_receipt or receipt
    assert first_receipt is not None
    replay, _path = inject_fault(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id="fault-live-001",
        case_id="case-000",
        fault_type="worker_termination",
        carrier="homepage",
        execution_id=EXECUTION_IDS["homepage"],
        job_id=fixture.queue.job_ids[EXECUTION_IDS["homepage"]],
        inspector=fixture.inspector,
        queue_provider=fixture.queue,
        providers=providers,
        queue_event_timeout_seconds=QUEUE_FAULT_EVENT_TIMEOUT_SECONDS,
    )
    assert replay == first_receipt
    assert providers["worker_termination"].call_count == 1
    with pytest.raises(
        RuntimeEvidenceError,
        match="FAULT_CASE_CREATE_ONCE_COLLISION",
    ):
        inject_fault(
            runtime=fixture.runtime,
            identity=IDENTITY,
            session_id="fault-live-001",
            case_id="case-000",
            fault_type="lease_expiry",
            carrier="homepage",
            execution_id=EXECUTION_IDS["homepage"],
            job_id=fixture.queue.job_ids[EXECUTION_IDS["homepage"]],
            inspector=fixture.inspector,
            queue_provider=fixture.queue,
            providers=providers,
            queue_event_timeout_seconds=QUEUE_FAULT_EVENT_TIMEOUT_SECONDS,
        )

    snapshot_path = runtime_snapshot_path(fixture.runtime, ROOT_ID)
    snapshot = read_json(snapshot_path)
    snapshot["status"] = "completed"
    write_json(snapshot_path, snapshot)
    raw, raw_path = finalize_fault_cases(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id="fault-live-001",
    )
    assert raw_path.name == "fault-injection-cases.json"
    assert {row["faultType"] for row in raw["cases"]} == set(FAULT_TYPES)
    assert_valid(raw, "release", "fault_injection_cases", label="raw faults")
    for row in raw["cases"]:
        event = read_json(fixture.runtime.output_root / row["injectionEvidenceRef"])
        assert event["triggeredAt"] == row["faultEventAt"]


def test_provider_evidence_outside_output_root_terminalizes_failed_case(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _document, bindings = _session(
        fixture, session_id="fault-evidence-boundary-001", all_faults=True
    )
    binding = next(
        row for row in bindings if row.fault_type == "lease_expiry"
    )
    provider = FakeFaultProvider(binding, tmp_path / "outside-output")
    execution_id = EXECUTION_IDS["article"]
    arguments = {
        "runtime": fixture.runtime,
        "identity": IDENTITY,
        "session_id": "fault-evidence-boundary-001",
        "case_id": "outside-proof-001",
        "fault_type": "lease_expiry",
        "carrier": "article",
        "execution_id": execution_id,
        "job_id": fixture.queue.job_ids[execution_id],
        "inspector": fixture.inspector,
        "queue_provider": fixture.queue,
        "providers": {"lease_expiry": provider},
        "queue_event_timeout_seconds": QUEUE_FAULT_EVENT_TIMEOUT_SECONDS,
    }

    receipt, receipt_path = inject_fault(**arguments)

    assert receipt_path.is_file()
    assert receipt["actionStatus"] == "failed"
    assert receipt["actionResultCode"] == (
        "DATA.RUNTIME_EVIDENCE.FAULT_PROVIDER_FAILED.RuntimeEvidenceError"
    )
    assert receipt["providerEvidenceRef"] is None
    assert receipt["providerEvidenceSha256"] is None
    replay, replay_path = inject_fault(**arguments)
    assert replay_path == receipt_path
    assert replay == receipt
    assert provider.call_count == 1


def test_provider_faults_default_deny_without_explicit_hook_attestation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(RuntimeEvidenceError, match="test-hook attestation"):
        create_runtime_evidence_session(
            runtime=fixture.runtime,
            identity=IDENTITY,
            session_id="fault-denied-001",
            campaign_plan_path=fixture.plan_path,
            inspector=fixture.inspector,
            queue_evidence_provider=fixture.queue.binding,
            fault_providers=(
                fixture.worker_binding,
                FaultProviderBinding(
                    "forbidden-provider-timeout",
                    canonical_digest({"provider": "timeout"}),
                    "provider_timeout",
                ),
            ),
        )
    assert not session_root(
        fixture.runtime, IDENTITY, "fault-denied-001"
    ).joinpath("session.json").exists()


@pytest.mark.parametrize(
    ("fault_type", "expected_code"),
    (
        (
            "lease_expiry",
            "DATA.RUNTIME_EVIDENCE.PROTECTED_OPERATION_CALLBACK_REQUIRED",
        ),
        (
            "provider_timeout",
            "DATA.RUNTIME_EVIDENCE.PROVIDER_TEST_HOOK_ATTESTATION_REQUIRED",
        ),
    ),
)
def test_unsupported_fault_intent_has_create_once_typed_failed_receipt(
    tmp_path: Path,
    fault_type: str,
    expected_code: str,
) -> None:
    fixture = _fixture(tmp_path)
    unavailable = unavailable_fault_adapter(fault_type)
    create_runtime_evidence_session(
        runtime=fixture.runtime,
        identity=IDENTITY,
        session_id=f"unsupported-{fault_type}-001",
        campaign_plan_path=fixture.plan_path,
        inspector=fixture.inspector,
        queue_evidence_provider=fixture.queue.binding,
        fault_providers=(fixture.worker_binding, unavailable.binding),
    )
    carrier = "article"
    execution_id = EXECUTION_IDS[carrier]
    arguments = {
        "runtime": fixture.runtime,
        "identity": IDENTITY,
        "session_id": f"unsupported-{fault_type}-001",
        "case_id": f"unsupported-{fault_type}-001",
        "fault_type": fault_type,
        "carrier": carrier,
        "execution_id": execution_id,
        "job_id": fixture.queue.job_ids[execution_id],
        "inspector": fixture.inspector,
        "queue_provider": fixture.queue,
        "providers": {fault_type: unavailable},
        "queue_event_timeout_seconds": QUEUE_FAULT_EVENT_TIMEOUT_SECONDS,
    }

    receipt, path = inject_fault(**arguments)
    replay, replay_path = inject_fault(**arguments)

    assert path == replay_path
    assert receipt == replay
    assert receipt["actionStatus"] == "failed"
    assert receipt["actionResultCode"] == expected_code
    assert (path.parent / "request.json").is_file()
    assert receipt["eventRef"] is None
    request_path = path.parent / "request.json"
    request = read_json(request_path)
    request["jobId"] = "tampered-job"
    request["requestDigest"] = canonical_digest(
        request, excluded="requestDigest"
    )
    write_json(request_path, request)
    with pytest.raises(RuntimeEvidenceError, match="fault request digest drift"):
        inject_fault(**arguments)


def test_builtin_worker_terminator_uses_fixed_registered_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[Mapping[str, Any]] = []

    def fake_terminate(checkpoint: Mapping[str, Any], *, grace_seconds: float) -> str:
        observed.append(dict(checkpoint))
        assert grace_seconds == 3.0
        return "terminated"

    monkeypatch.setattr(
        "content.execution.runtime_evidence.faults.terminate_lane_process",
        fake_terminate,
    )
    target = FaultActionTarget(
        fault_type="worker_termination",
        carrier="image",
        execution_id=EXECUTION_IDS["image"],
        job_id="job-image-0001",
        requested_at=_now().isoformat(),
        worker_checkpoint={
            "executionId": EXECUTION_IDS["image"],
            "pid": 9300,
            "pgid": 9300,
        },
    )
    result = CampaignWorkerTerminator(grace_seconds=3.0).trigger(target)
    assert result.result_code == "DATA.RUNTIME_EVIDENCE.WORKER_TERMINATED"
    assert observed == [target.worker_checkpoint]


def test_runner_api_has_no_metric_or_shell_input_and_rejects_stale_lease(
    tmp_path: Path,
) -> None:
    metric_fields = {
        "rss_bytes",
        "open_fd_count",
        "queue_depth",
        "heartbeat_age_seconds",
        "progress_age_seconds",
        "temporary_workspace_bytes",
    }
    assert not metric_fields.intersection(
        inspect.signature(capture_resource_sample).parameters
    )
    assert not {"command", "argv", "shell"}.intersection(
        inspect.signature(inject_fault).parameters
    )

    fixture = _fixture(tmp_path)
    snapshot_path = runtime_snapshot_path(fixture.runtime, ROOT_ID)
    snapshot = read_json(snapshot_path)
    snapshot["heartbeatAt"] = (_now() - timedelta(hours=1)).isoformat()
    write_json(snapshot_path, snapshot)
    with pytest.raises(RuntimeEvidenceError, match="lease is stale"):
        _session(fixture, session_id="stale-lease-001", all_faults=False)
    assert not session_root(
        fixture.runtime, IDENTITY, "stale-lease-001"
    ).joinpath("session.json").exists()
