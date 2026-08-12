from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from content.execution.runtime_evidence import queue as queue_evidence
from content.execution.runtime_evidence import reliabletask as reliable_observer
from content.execution.runtime_evidence import reliabletask_process as process_port
from content.execution.runtime_evidence.contract import CARRIERS
from content.execution.runtime_evidence.queue import QueueEvidenceBlocker
from content.execution.runtime_evidence.reliabletask import (
    ReliableTaskQueueEvidenceProvider,
)
from content.execution.runtime_evidence.sampling import LocalQueueEvidenceProvider
from core.control_types import QueueBackend


def _execution_ids() -> dict[str, str]:
    return {carrier: f"execution-{carrier}" for carrier in CARRIERS}


def _envelope(execution_id: str, backend: QueueBackend) -> dict[str, object]:
    marker = CARRIERS.index(execution_id.removeprefix("execution-")) + 1

    def digest_marker(offset: int) -> str:
        return f"{marker + offset:x}" * 64

    return {
        "executionId": execution_id,
        "queueBackend": backend.value,
        "envelopeDigest": "sha256:" + digest_marker(0),
        "queuePolicyDigest": "sha256:" + digest_marker(4),
        "executionManifestDigest": "sha256:" + digest_marker(5),
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + "a" * 64,
            "inputs": [f"input-{marker}"],
        },
        "targetSetDigest": digest_marker(7),
        "rootExecutionId": "execution-homepage",
        "campaignRunId": "campaign-run-001",
        "campaignGeneration": 1,
        "campaignFencingToken": "sha256:" + "b" * 64,
        "campaignPlanDigest": "sha256:" + "c" * 64,
        "campaignSourceRevision": "sha256:" + "d" * 64,
        "campaignEntityCatalogDigest": "sha256:" + "e" * 64,
    }


def test_local_observer_binding_is_derived_from_all_four_frozen_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_ids = _execution_ids()
    monkeypatch.setattr(
        queue_evidence,
        "resolve_execution_queue_backend",
        lambda execution_id, requested: QueueBackend.LOCAL_FILE,
    )
    monkeypatch.setattr(
        queue_evidence,
        "load_execution_queue_backend",
        lambda execution_id: _envelope(execution_id, QueueBackend.LOCAL_FILE),
    )

    first = queue_evidence.resolve_frozen_queue_evidence_provider(execution_ids)
    second = queue_evidence.resolve_frozen_queue_evidence_provider(execution_ids)

    assert isinstance(first, LocalQueueEvidenceProvider)
    assert first.binding == second.binding
    assert first.binding.provider_id == "local_object_queue_v1"
    assert first.binding.configuration_digest.startswith("sha256:")


def test_reliabletask_uses_governed_mongo_redis_reader_bound_to_frozen_jobs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    monkeypatch.setattr(process_port, "OUTPUT_ROOT", output_root)
    binary_ref = (
        "data/local/cache/reliabletask-observer-binaries/"
        + "f" * 64
        + "/data-content-worker"
    )
    binary = output_root / binary_ref
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"frozen-observer")
    binary.chmod(0o755)
    binary_fields = {
        "observerBinaryRef": binary_ref,
        "observerBinarySha256": (
            "sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest()
        ),
    }
    monkeypatch.setattr(
        queue_evidence,
        "resolve_execution_queue_backend",
        lambda execution_id, requested: QueueBackend.RELIABLE_TASK,
    )
    monkeypatch.setattr(
        queue_evidence,
        "load_execution_queue_backend",
        lambda execution_id: {
            **_envelope(execution_id, QueueBackend.RELIABLE_TASK),
            **binary_fields,
        },
    )
    def job_set(execution_id: str) -> tuple[dict[str, object], ...]:
        carrier = execution_id.removeprefix("execution-")
        backend = _envelope(execution_id, QueueBackend.RELIABLE_TASK)
        source_revision = "sha256:" + "a" * 64
        return ({
            "executionId": execution_id,
                "carrier": carrier,
                "stage": "author",
                "attemptOrdinal": 1,
                "previousJobSetEnvelopeDigest": None,
            "queueBackendEnvelopeDigest": backend["envelopeDigest"],
            "campaignBinding": {
                "rootExecutionId": "execution-homepage",
                "campaignRunId": "campaign-run-001",
                "campaignGeneration": 1,
                "campaignFencingToken": "sha256:" + "b" * 64,
                "campaignPlanDigest": "sha256:" + "c" * 64,
                "campaignSourceRevision": "sha256:" + "d" * 64,
                "campaignSourceDigest": "sha256:" + "a" * 64,
                "campaignEntityCatalogDigest": "sha256:" + "e" * 64,
            },
            "expectedTasks": [{
                "jobId": f"job-{carrier}",
                "entityRef": f"/entity/{carrier}",
                "stage": "author",
                "sourceRevision": source_revision,
                "executionId": execution_id,
                "carrier": carrier,
                "idempotencyKey": (
                    f"{execution_id}|/entity/{carrier}|{carrier}|"
                    f"{source_revision}|author"
                ),
                "ref": f"ref-{carrier}",
                "partitionKey": f"partition-{carrier}",
                "maxAttempts": 3,
            }],
            "jobSetDigest": "sha256:" + "9" * 64,
            "envelopeDigest": "sha256:" + "8" * 64,
        },)

    monkeypatch.setattr(
        reliable_observer,
        "load_reliabletask_job_set_envelopes",
        job_set,
    )

    provider = queue_evidence.resolve_frozen_queue_evidence_provider(
        _execution_ids()
    )

    assert isinstance(provider, ReliableTaskQueueEvidenceProvider)
    assert provider.binding.provider_id == "reliabletask_mongo_redis_observer_v3"
    assert provider.binding.configuration_digest.startswith("sha256:")


def test_queue_backend_environment_override_is_not_a_provider_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_override(execution_id: str, requested: object) -> QueueBackend:
        raise ValueError("queue backend environment override is forbidden")

    monkeypatch.setattr(
        queue_evidence,
        "resolve_execution_queue_backend",
        reject_override,
    )
    with pytest.raises(QueueEvidenceBlocker) as captured:
        queue_evidence.resolve_frozen_queue_evidence_provider(_execution_ids())
    assert captured.value.code == "DATA.RUNTIME_EVIDENCE.QUEUE_ENVELOPE_INVALID"
    assert "environment override is forbidden" in str(captured.value)


def test_mixed_backends_cannot_share_one_runtime_evidence_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def backend(execution_id: str, requested: object) -> QueueBackend:
        if execution_id.endswith("video"):
            return QueueBackend.RELIABLE_TASK
        return QueueBackend.LOCAL_FILE

    monkeypatch.setattr(queue_evidence, "resolve_execution_queue_backend", backend)
    monkeypatch.setattr(
        queue_evidence,
        "load_execution_queue_backend",
        lambda execution_id: _envelope(
            execution_id,
            backend(execution_id, None),
        ),
    )
    with pytest.raises(QueueEvidenceBlocker) as captured:
        queue_evidence.resolve_frozen_queue_evidence_provider(_execution_ids())
    assert captured.value.code == "DATA.RUNTIME_EVIDENCE.QUEUE_BACKEND_MIXED"
