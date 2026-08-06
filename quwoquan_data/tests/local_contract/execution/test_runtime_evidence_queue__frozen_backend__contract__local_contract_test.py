from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from content.execution import runtime_evidence_queue as queue_evidence
from content.execution import runtime_evidence_reliabletask as reliable_observer
from content.execution import runtime_evidence_reliabletask_process as process_port
from content.execution.runtime_evidence_contract import CARRIERS
from content.execution.runtime_evidence_queue import QueueEvidenceBlocker
from content.execution.runtime_evidence_reliabletask import (
    ReliableTaskQueueEvidenceProvider,
)
from content.execution.runtime_evidence_sampling import LocalQueueEvidenceProvider
from core.control_types import QueueBackend


def _execution_ids() -> dict[str, str]:
    return {carrier: f"execution-{carrier}" for carrier in CARRIERS}


def _envelope(execution_id: str, backend: QueueBackend) -> dict[str, object]:
    marker = CARRIERS.index(execution_id.removeprefix("execution-")) + 1
    return {
        "executionId": execution_id,
        "queueBackend": backend.value,
        "envelopeDigest": "sha256:" + str(marker) * 64,
        "queuePolicyDigest": "sha256:" + str(marker + 4) * 64,
        "executionManifestDigest": "sha256:" + str(marker + 5) * 64,
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + str(marker + 6) * 64,
            "inputs": [f"input-{marker}"],
        },
        "targetSetDigest": str(marker + 7) * 64,
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
    monkeypatch.setattr(
        reliable_observer,
        "_expected_tasks",
        lambda carrier, execution_id: (
            reliable_observer._ExpectedTask(
                job_id=f"job-{carrier}",
                entity_ref=f"/entity/{carrier}",
                stage="author",
                source_revision="sha256:" + "a" * 64,
            ),
        ),
    )

    provider = queue_evidence.resolve_frozen_queue_evidence_provider(
        _execution_ids()
    )

    assert isinstance(provider, ReliableTaskQueueEvidenceProvider)
    assert provider.binding.provider_id == "reliabletask_mongo_redis_observer_v1"
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
