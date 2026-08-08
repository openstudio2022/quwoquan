# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.queue import backend as queue_backend
from content.execution.queue import jobs
from content.execution.queue.partition import partition_count, partition_key
from content.execution.queue.reliabletask.attempt import (
    select_or_freeze_job_set_attempt,
)
from content.execution.queue.reliabletask import job_set as job_set_module
from core.control_types import QueueBackend
from core.io import read_json, write_json

EXECUTION_ID = "20260805--travel-image-m100--china--scale-101"
M3_EXECUTION_ID = "20260805--travel-image-m3--china--scale-102"
M10000_EXECUTION_ID = "20260805--travel-image-m10000--china--scale-103"


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
    monkeypatch.setattr(job_set_module, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(queue_backend.store, "load_spec", lambda _execution_id: spec)
    monkeypatch.setattr(
        queue_backend,
        "load_frozen_execution_manifest",
        lambda _execution_id: manifest,
    )
    monkeypatch.setattr(
        queue_backend,
        "load_frozen_target_set",
        lambda _execution_id: {
            "entityCatalogDigest": "sha256:" + "f" * 64,
        },
    )
    monkeypatch.setattr(
        queue_backend,
        "load_frozen_campaign_observer_context",
        lambda: SimpleNamespace(
            execution_id=execution_id,
            source_digest="sha256:" + "a" * 64,
            entity_catalog_digest="sha256:" + "f" * 64,
            as_envelope_document=lambda: {
                "rootExecutionId": "20260805--travel-homepage-m100--china--scale-100",
                "campaignRunId": "campaign-run-001",
                "campaignGeneration": 2,
                "campaignFencingToken": "sha256:" + "1" * 64,
                "campaignPlanDigest": "sha256:" + "2" * 64,
                "campaignSourceRevision": "sha256:" + "3" * 64,
                "campaignEntityCatalogDigest": "sha256:" + "f" * 64,
            },
        ),
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
    monkeypatch.setattr(
        queue_backend,
        "load_frozen_observer_binary_binding",
        lambda: SimpleNamespace(
            as_document=lambda: {
                "observerBinaryRef": (
                    "data/local/cache/reliabletask-observer-binaries/"
                    + "d" * 64
                    + "/data-content-worker"
                ),
                "observerBinarySha256": "sha256:" + "e" * 64,
            }
        ),
    )
    monkeypatch.setattr(
        queue_backend,
        "load_frozen_campaign_worker_binary_binding",
        lambda: SimpleNamespace(
            as_document=lambda: {
                "observerBinaryRef": (
                    "data/local/cache/reliabletask-observer-binaries/"
                    + "d" * 64
                    + "/data-content-worker"
                ),
                "observerBinarySha256": "sha256:" + "e" * 64,
            }
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
    assert envelope["campaignGeneration"] == 2
    assert envelope["campaignSourceRevision"] == "sha256:" + "3" * 64
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


@pytest.mark.parametrize(
    ("required_workers", "expected_count"),
    ((1, 16), (4, 16), (5, 32), (16, 64), (33, 256), (65, 256)),
)
def test_partition_count_is_power_of_two_and_capped(
    required_workers: int,
    expected_count: int,
) -> None:
    assert partition_count(required_workers) == expected_count


def test_m10000_backend_requires_reliabletask_and_governed_observer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _freeze(
        tmp_path,
        monkeypatch,
        execution_id=M10000_EXECUTION_ID,
        approved_quota=10_000,
    )
    envelope = read_json(path)
    assert envelope["scaleClass"] == "M10000_PLUS"
    assert envelope["queueBackend"] == "reliabletask"
    assert envelope["observerBinaryRef"].endswith("/data-content-worker")
    assert envelope["campaignGeneration"] == 2

    with pytest.raises(ValueError, match="M10000_PLUS.*must be reliabletask"):
        _freeze(
            tmp_path / "local-backend",
            monkeypatch,
            execution_id=M10000_EXECUTION_ID,
            approved_quota=10_000,
            backend=QueueBackend.LOCAL_FILE,
        )
def test_reliabletask_stage_job_set_is_create_once_and_queue_mirror_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(tmp_path, monkeypatch)
    source_revision = "sha256:" + "9" * 64
    task = {
        "entityRef": "/entity/地点/景区/杭州西湖",
        "carrier": "image",
        "sourceRevision": source_revision,
        "idempotencyKey": (
            f"{EXECUTION_ID}|/entity/地点/景区/杭州西湖|image|"
            f"{source_revision}|author"
        ),
        "jobId": "image-author-001",
        "executionId": EXECUTION_ID,
        "ref": "杭州西湖_image",
        "stage": "author",
        "partitionKey": "source-unit-001",
    }

    first = queue_backend.freeze_reliabletask_job_set(
        EXECUTION_ID,
        "author",
        required_workers=1,
        expected_tasks=[task],
    )
    repeated = queue_backend.freeze_reliabletask_job_set(
        EXECUTION_ID,
        "author",
        required_workers=1,
        expected_tasks=[task],
    )

    assert repeated == first
    expected_task = {
        **task,
        "partitionKey": partition_key("image", "杭州西湖_image", 16),
    }
    assert first["expectedTasks"] == [expected_task]
    assert first["requiredWorkers"] == 1
    assert first["partitionCount"] == 16
    assert first["checkpointPolicy"]["resume"] == "strictly_after_cursor"
    assert first["jobSetDigest"].startswith("sha256:")
    loaded = queue_backend.load_reliabletask_job_set_envelopes(EXECUTION_ID)
    assert loaded == (first,)

    with pytest.raises(ValueError, match="job-set attempt collision"):
        queue_backend.freeze_reliabletask_job_set(
            EXECUTION_ID,
            "author",
            required_workers=5,
            expected_tasks=[task],
        )

    changed_revision = "sha256:" + "8" * 64
    second = queue_backend.freeze_reliabletask_job_set(
        EXECUTION_ID,
        "author",
        required_workers=1,
        expected_tasks=[{
            **task,
            "sourceRevision": changed_revision,
            "idempotencyKey": (
                f"{EXECUTION_ID}|/entity/地点/景区/杭州西湖|image|"
                f"{changed_revision}|author"
            ),
        }],
    )
    assert second["attemptOrdinal"] == 2
    assert second["previousJobSetEnvelopeDigest"] == first["envelopeDigest"]
    assert second["jobSetDigest"] != first["jobSetDigest"]
    assert queue_backend.load_reliabletask_job_set_envelopes(EXECUTION_ID) == (
        first,
        second,
    )

    path = queue_backend.reliabletask_job_set_envelope_path(
        EXECUTION_ID,
        "author",
        first["jobSetDigest"],
    )
    tampered = read_json(path)
    tampered["jobSetDigest"] = "sha256:" + "7" * 64
    write_json(path, tampered)
    with pytest.raises(ValueError, match="content-addressed path drift"):
        queue_backend.load_reliabletask_job_set_envelopes(EXECUTION_ID)


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


def test_attempt_selector_dispatches_one_revision_set_per_fleet_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(tmp_path, monkeypatch)

    def task(revision_character: str) -> dict[str, str]:
        revision = "sha256:" + revision_character * 64
        entity = "/entity/地点/景区/杭州西湖"
        return {
            "entityRef": entity,
            "carrier": "image",
            "sourceRevision": revision,
            "idempotencyKey": (
                f"{EXECUTION_ID}|{entity}|image|{revision}|author"
            ),
            "jobId": "image-author-001",
            "executionId": EXECUTION_ID,
            "ref": "杭州西湖_image",
            "stage": "author",
            "partitionKey": "untrusted",
        }

    first_task = task("9")
    first = select_or_freeze_job_set_attempt(
        EXECUTION_ID,
        "author",
        active_tasks=[first_task],
        required_workers=1,
    )
    repair_task = task("8")
    second = select_or_freeze_job_set_attempt(
        EXECUTION_ID,
        "author",
        active_tasks=[first_task, repair_task],
        required_workers=1,
    )

    assert first["attemptOrdinal"] == 1
    assert second["attemptOrdinal"] == 2
    assert [row["sourceRevision"] for row in second["expectedTasks"]] == [
        repair_task["sourceRevision"]
    ]
    assert select_or_freeze_job_set_attempt(
        EXECUTION_ID,
        "author",
        active_tasks=[first_task, repair_task],
        required_workers=1,
    ) == second
    assert select_or_freeze_job_set_attempt(
        EXECUTION_ID,
        "author",
        active_tasks=[first_task],
        required_workers=1,
    ) == first


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


def test_below_m100_campaign_reliabletask_binds_worker_without_observer_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "QWQ_CAMPAIGN_ROOT_EXECUTION_ID",
        "20260805--travel-homepage-m3--china--scale-102",
    )
    path = _freeze(
        tmp_path,
        monkeypatch,
        execution_id=M3_EXECUTION_ID,
        approved_quota=3,
        backend=QueueBackend.RELIABLE_TASK,
    )

    envelope = read_json(path)
    assert envelope["scaleClass"] == "BELOW_M100"
    assert envelope["queueBackend"] == "reliabletask"
    assert envelope["observerBinaryRef"].endswith("/data-content-worker")
    assert envelope["observerBinarySha256"] == "sha256:" + "e" * 64
    assert "rootExecutionId" not in envelope
    assert "campaignRunId" not in envelope
    assert "campaignFencingToken" not in envelope


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
