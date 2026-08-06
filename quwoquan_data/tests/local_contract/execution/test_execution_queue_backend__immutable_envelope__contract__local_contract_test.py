# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution import queue_backend
from content.execution.queue import jobs
from core.control_types import QueueBackend
from core.io import read_json, write_json

EXECUTION_ID = "20260805--travel-image-m100--china--scale-101"
M3_EXECUTION_ID = "20260805--travel-image-m3--china--scale-102"


def _spec(
    *,
    approved_quota: int = 100,
    backend: QueueBackend = QueueBackend.RELIABLE_TASK,
) -> dict[str, object]:
    return {
        "executionPolicy": {"approvedQuota": approved_quota},
        "queuePolicy": {
            "backend": backend.value,
            "reliableTask": {
                "taskType": "data.content_object.execute",
                "queue": "reliabletask.data.content_supply",
                "store": "MongoStore",
                "readyIndex": "RedisReadyIndex",
            },
            "leaseSeconds": 1800,
            "heartbeatSeconds": 60,
            "deadLetterAfterAttempts": 2,
        },
    }


def _manifest(execution_id: str = EXECUTION_ID) -> dict[str, object]:
    return {
        "executionId": execution_id,
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + ("a" * 64),
            "inputs": ["quwoquan_data/schema"],
        },
        "targetSetDigest": "b" * 64,
        "familyRef": {"ref": "content/travel/image/image", "sha256": "c" * 64},
    }


def _freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    execution_id: str = EXECUTION_ID,
    approved_quota: int = 100,
    backend: QueueBackend = QueueBackend.RELIABLE_TASK,
) -> Path:
    root = tmp_path / "execution"
    spec = _spec(approved_quota=approved_quota, backend=backend)
    manifest = _manifest(execution_id)
    monkeypatch.setattr(queue_backend, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(queue_backend.store, "load_spec", lambda _execution_id: spec)
    monkeypatch.setattr(
        queue_backend,
        "load_frozen_execution_manifest",
        lambda _execution_id: manifest,
    )
    monkeypatch.setattr(
        queue_backend,
        "prepare_controller_observer_binary",
        lambda: SimpleNamespace(
            binding=SimpleNamespace(
                as_document=lambda: {
                    "observerBinaryRef": (
                        "data/local/cache/reliabletask-observer-binaries/"
                        + "d" * 64
                        + "/data-content-worker"
                    ),
                    "observerBinarySha256": "sha256:" + "e" * 64,
                }
            ),
        ),
    )
    return queue_backend.freeze_execution_queue_backend(
        execution_id,
        spec=spec,
        manifest=manifest,
    )


def test_m100_backend_is_resolved_only_from_create_once_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _freeze(tmp_path, monkeypatch)
    envelope = read_json(path)
    assert envelope["scaleClass"] == "M100_PLUS"
    assert envelope["queueBackend"] == "reliabletask"
    assert envelope["observerBinaryRef"].endswith("/data-content-worker")
    assert envelope["observerBinarySha256"] == "sha256:" + "e" * 64
    repeated = _freeze(tmp_path, monkeypatch)
    assert repeated == path
    assert read_json(repeated) == envelope

    resolved = jobs._backend_from_metadata(
        EXECUTION_ID,
        {},
        QueueBackend.RELIABLE_TASK,
    )
    assert resolved is QueueBackend.RELIABLE_TASK

    with pytest.raises(ValueError, match="queue backend tamper"):
        jobs._backend_from_metadata(
            EXECUTION_ID,
            {},
            QueueBackend.LOCAL_FILE,
        )
    with pytest.raises(ValueError, match="queue backend tamper"):
        jobs._backend_from_metadata(
            EXECUTION_ID,
            {"queueBackend": "local_file"},
            None,
        )


def test_m100_backend_rejects_environment_override_and_file_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _freeze(tmp_path, monkeypatch)
    monkeypatch.setenv("QWQ_OBJECT_QUEUE_BACKEND", "local_file")
    with pytest.raises(ValueError, match="environment override is forbidden"):
        jobs._backend_from_metadata(EXECUTION_ID, {}, None)

    monkeypatch.delenv("QWQ_OBJECT_QUEUE_BACKEND")
    tampered = read_json(path)
    tampered["queueBackend"] = "local_file"
    write_json(path, tampered)
    with pytest.raises(ValueError, match="envelope digest mismatch"):
        jobs._backend_from_metadata(EXECUTION_ID, {}, None)


def test_m100_backend_rejects_frozen_manifest_provider_profile_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(tmp_path, monkeypatch)
    drifted_manifest = {
        **_manifest(),
        "modelBinding": {
            "provider": "codex_sdk",
            "authorModel": "gpt-5.6-terra",
            "reviewerModel": "gpt-5.6-terra",
            "runtimeProfileDigest": "sha256:" + ("d" * 64),
        },
    }

    with pytest.raises(ValueError, match="new sequence with retryOf"):
        queue_backend.freeze_execution_queue_backend(
            EXECUTION_ID,
            spec=_spec(),
            manifest=drifted_manifest,
        )


def test_m3_backend_is_resolved_only_from_create_once_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _freeze(
        tmp_path,
        monkeypatch,
        execution_id=M3_EXECUTION_ID,
        approved_quota=3,
        backend=QueueBackend.LOCAL_FILE,
    )
    envelope = read_json(path)
    assert envelope["scaleClass"] == "BELOW_M100"
    assert envelope["queueBackend"] == "local_file"

    assert (
        jobs._backend_from_metadata(M3_EXECUTION_ID, {}, None)
        is QueueBackend.LOCAL_FILE
    )
    with pytest.raises(ValueError, match="queue backend tamper"):
        jobs._backend_from_metadata(
            M3_EXECUTION_ID,
            {"queueBackend": "reliabletask"},
            None,
        )

    monkeypatch.setenv("QWQ_OBJECT_QUEUE_BACKEND", "reliabletask")
    with pytest.raises(ValueError, match="environment override is forbidden"):
        jobs._backend_from_metadata(M3_EXECUTION_ID, {}, None)


def test_all_scales_require_the_create_once_backend_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "missing-envelope"
    spec = _spec(approved_quota=3, backend=QueueBackend.LOCAL_FILE)
    manifest = _manifest(M3_EXECUTION_ID)
    monkeypatch.setattr(queue_backend, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(queue_backend.store, "load_spec", lambda _execution_id: spec)
    monkeypatch.setattr(
        queue_backend,
        "load_frozen_execution_manifest",
        lambda _execution_id: manifest,
    )

    with pytest.raises(ValueError, match="immutable queue backend envelope is missing"):
        jobs._backend_from_metadata(M3_EXECUTION_ID, {}, QueueBackend.LOCAL_FILE)


def test_legacy_reliabletask_envelope_without_binary_binding_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _freeze(tmp_path, monkeypatch)
    legacy = read_json(path)
    legacy.pop("observerBinaryRef")
    legacy.pop("observerBinarySha256")
    stable = {key: value for key, value in legacy.items() if key != "envelopeDigest"}
    legacy["envelopeDigest"] = queue_backend._digest(stable)
    write_json(path, legacy)

    with pytest.raises(ValueError, match="schema violation"):
        queue_backend.load_execution_queue_backend(EXECUTION_ID)
