# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.queue import backend as queue_backend
from content.execution.queue import jobs
from content.execution.queue.partition import (
    MAX_PARTITION_COUNT,
    MIN_PARTITION_COUNT,
    checkpoint_policy_document,
    partition_count,
    partition_key,
)
from content.execution.queue.reliabletask import job_set as job_set_module
from content.execution.queue.reliabletask import jobs as reliable_jobs
from content.execution.queue.reliabletask.attempt import (
    select_or_freeze_job_set_attempt,
)
from content.execution.runtime_contract import canonical_sha256
from core.control_types import QueueBackend, QueueJobStage
from core.io import read_json, write_json
from core.schema import assert_valid, load_schema

EXECUTION_ID = "20260805--travel-image-m100--china--scale-101"
M3_EXECUTION_ID = "20260805--travel-image-m3--china--scale-102"
M10000_EXECUTION_ID = "20260805--travel-image-m10000--china--scale-103"
M1000_EXECUTION_ID = "20260805--travel-image-m1000--china--scale-104"


def test_python_go_task_digest_binds_integer_max_attempts() -> None:
    execution_id = "20260719--travel-homepage-coverage--cn-zhejiang--canary-001"
    entity_ref = "entity/地点/景区/001"
    source_revision = "sha256:" + f"{2:064d}"
    task = {
        "entityRef": entity_ref,
        "carrier": "homepage",
        "sourceRevision": source_revision,
        "idempotencyKey": (
            f"{execution_id}|{entity_ref}|homepage|{source_revision}|author"
        ),
        "jobId": "job-001",
        "executionId": execution_id,
        "ref": entity_ref,
        "stage": "author",
        "partitionKey": entity_ref,
        "maxAttempts": 3,
    }
    assert canonical_sha256([task]) == (
        "sha256:dc34c4fcdb4316ce53ae642a595808acc1a61e8bc1d3a8331e6e1c9cd2311edd"
    )
    assert canonical_sha256([{**task, "maxAttempts": 2}]) != canonical_sha256(
        [task]
    )


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
    spec_override: dict[str, object] | None = None,
) -> Path:
    root = tmp_path / "execution"
    spec = spec_override or _spec(approved_quota=approved_quota, backend=backend)
    manifest = _manifest(execution_id)
    monkeypatch.setattr(queue_backend, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(job_set_module, "execution_root", lambda _execution_id: root)
    monkeypatch.setattr(queue_backend.store, "load_spec", lambda _execution_id: spec)
    monkeypatch.setattr(
        queue_backend,
        "load_frozen_execution_manifest",
        lambda _execution_id: manifest,
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
    path = _freeze(tmp_path, monkeypatch, backend=QueueBackend.LOCAL_FILE)
    envelope = read_json(path)
    assert envelope["scaleClass"] == "M100_PLUS"
    assert envelope["queueBackend"] == "local_file"
    assert envelope["poolDeliveryBackend"] == "reliabletask"
    assert "observerBinaryRef" not in envelope
    assert "campaignGeneration" not in envelope
    repeated = _freeze(
        tmp_path,
        monkeypatch,
        backend=QueueBackend.LOCAL_FILE,
    )
    assert repeated == path
    assert read_json(repeated) == envelope

    resolved = jobs._backend_from_metadata(
        EXECUTION_ID,
        {},
        QueueBackend.LOCAL_FILE,
    )
    assert resolved is QueueBackend.LOCAL_FILE

    with pytest.raises(ValueError, match="queue backend tamper"):
        jobs._backend_from_metadata(
            EXECUTION_ID,
            {},
            QueueBackend.RELIABLE_TASK,
        )
    with pytest.raises(ValueError, match="queue backend tamper"):
        jobs._backend_from_metadata(
            EXECUTION_ID,
            {"queueBackend": "reliabletask"},
            None,
        )


@pytest.mark.parametrize(
    ("execution_id", "approved_quota"),
    ((EXECUTION_ID, 100), (M1000_EXECUTION_ID, 1000)),
)
def test_scale_semantic_stages_never_use_delivery_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    execution_id: str,
    approved_quota: int,
) -> None:
    _freeze(
        tmp_path / execution_id,
        monkeypatch,
        execution_id=execution_id,
        approved_quota=approved_quota,
        backend=QueueBackend.LOCAL_FILE,
    )
    ctx = SimpleNamespace(
        execution_id=execution_id,
        spec=SimpleNamespace(
            queue_policy=SimpleNamespace(backend=QueueBackend.LOCAL_FILE.value)
        ),
    )

    assert reliable_jobs.uses_reliabletask(
        ctx, stage=QueueJobStage.AUTHOR
    ) is False
    assert reliable_jobs.uses_reliabletask(
        ctx, stage=QueueJobStage.PUBLISH
    ) is True


def _declared_partition_bands() -> tuple[tuple[int, int | None, int], ...]:
    """Read the governed partition topology straight from its declared contract."""
    schema = load_schema("execution", "data_content_fleet_request")
    bands: list[tuple[int, int | None, int]] = []
    for branch in schema.get("allOf") or ():
        rule = branch["if"]["properties"]["jobs"]
        bands.append(
            (
                int(rule["minItems"]),
                int(rule["maxItems"]) if "maxItems" in rule else None,
                int(branch["then"]["properties"]["partitionCount"]["const"]),
            )
        )
    if not bands:
        raise AssertionError(
            "data_content_fleet_request must declare the partition topology bands"
        )
    return tuple(bands)


def _declared_partition_boundaries() -> tuple[tuple[int, int], ...]:
    rows: list[tuple[int, int]] = []
    for minimum, maximum, count in _declared_partition_bands():
        rows.append((minimum, count))
        if maximum is not None and maximum > minimum:
            rows.append((maximum, count))
    return tuple(rows)


@pytest.mark.parametrize(
    ("work_unit_count", "expected_count"),
    _declared_partition_boundaries(),
)
def test_partition_count_matches_declared_topology_bands(
    work_unit_count: int,
    expected_count: int,
) -> None:
    """Pin this side to the same declaration the Service importer validates against."""
    assert partition_count(work_unit_count) == expected_count


def _fleet_request_document(work_unit_count: int, partitions: int) -> dict[str, object]:
    execution_id = "20260805--travel-image-m1000--china--scale-104"
    revision = "sha256:" + "a" * 64

    def work_unit(index: int) -> dict[str, object]:
        entity_ref = f"/entity/地点/景区/西湖-{index:04d}"
        object_ref = f"west-lake-{index:04d}"
        return {
            "entityRef": entity_ref,
            "carrier": "image",
            "sourceRevision": revision,
            "idempotencyKey": (
                f"{execution_id}|{entity_ref}|image|{revision}|author"
            ),
            "jobId": f"job-author-{index:04d}",
            "executionId": execution_id,
            "ref": object_ref,
            "stage": "author",
            "partitionKey": partition_key("image", object_ref, partitions),
            "maxAttempts": 3,
        }

    return {
        "schema": "quwoquan.data_content_fleet_request",
        "executionId": execution_id,
        "campaignScale": "M1000",
        "scaleClass": "M100_PLUS",
        "executionEnvelopeDigest": "sha256:" + "e" * 64,
        "jobSetEnvelopeDigest": "sha256:" + "d" * 64,
        "jobSetDigest": "sha256:" + "c" * 64,
        "actualTaskDigest": "sha256:" + "b" * 64,
        # requiredWorkers carries the approved quota; it must never reach the
        # partition topology, which is why it is deliberately off-band here.
        "requiredWorkers": work_unit_count,
        "partitionCount": partitions,
        "partitionAlgorithm": "sha256_carrier_object_ref_mod_v1",
        "checkpointPolicy": checkpoint_policy_document(),
        "recoverDeadTasks": False,
        "objectTimeoutMilliseconds": 120000,
        "globalRequiredQuota": work_unit_count,
        "requiredQuota": work_unit_count,
        "jobs": [work_unit(index) for index in range(work_unit_count)],
    }


@pytest.mark.parametrize("work_unit_count", (3, 7, 10, 18, 100, 180, 1000))
def test_fleet_request_contract_rejects_worker_derived_partition_count(
    work_unit_count: int,
) -> None:
    """The declared contract admits only the job-count derivation, fail-closed."""
    expected = partition_count(work_unit_count)
    assert_valid(
        _fleet_request_document(work_unit_count, expected),
        "execution",
        "data_content_fleet_request",
        label="data_content_fleet_request",
    )
    for drifted in (16, 32, 64, 128, 256):
        if drifted == expected:
            continue
        with pytest.raises(ValueError, match="partitionCount"):
            assert_valid(
                _fleet_request_document(work_unit_count, drifted),
                "execution",
                "data_content_fleet_request",
                label="data_content_fleet_request",
            )


def test_declared_partition_topology_covers_the_governed_bounds() -> None:
    schema = load_schema("execution", "data_content_fleet_request")
    bands = _declared_partition_bands()
    declared_counts = sorted({count for _, _, count in bands})
    assert sorted(schema["properties"]["partitionCount"]["enum"]) == declared_counts
    assert declared_counts[0] == MIN_PARTITION_COUNT
    assert declared_counts[-1] == MAX_PARTITION_COUNT
    # Bands must tile every work-unit count without a gap or an overlap.
    assert bands[0][0] == 1
    assert bands[-1][1] is None
    for (_, previous_max, _), (current_min, _, _) in zip(bands, bands[1:]):
        assert previous_max is not None and current_min == previous_max + 1


def test_m10000_semantic_backend_is_independent_from_governed_pool_delivery(
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
    assert "observerBinaryRef" not in envelope
    assert "campaignGeneration" not in envelope

    local_path = _freeze(
        tmp_path / "local-backend",
        monkeypatch,
        execution_id=M10000_EXECUTION_ID,
        approved_quota=10_000,
        backend=QueueBackend.LOCAL_FILE,
    )
    local_envelope = read_json(local_path)
    assert local_envelope["queueBackend"] == "local_file"
    assert local_envelope["poolDeliveryBackend"] == "reliabletask"
    assert jobs._backend_from_metadata(
        M10000_EXECUTION_ID,
        {},
        QueueBackend.RELIABLE_TASK,
        stage=QueueJobStage.PUBLISH,
    ) is QueueBackend.RELIABLE_TASK
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
        "maxAttempts": 3,
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
            "maxAttempts": 3,
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


def test_attempt_selector_refreezes_same_tasks_for_new_host_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def binding(generation: int) -> dict[str, object]:
        digest = f"sha256:{generation:064x}"
        return {
            "hostSetId": "governed-workers",
            "generation": generation,
            "fencingToken": f"sha256:{generation + 10:064x}",
            "hostSetDigest": digest,
            "transportBinding": {
                "mongoTransportDigest": "sha256:" + "8" * 64,
                "redisTransportDigest": "sha256:" + "9" * 64,
            },
            "hosts": [{
                "hostScopeId": "worker-alpha",
                "workerCount": 1,
                "partitionKeys": [str(value) for value in range(16)],
                "runtimeProfileDigest": "sha256:" + "a" * 64,
                "executorBundleRef": "data/executor/content-worker",
                "executorBundleDigest": "sha256:" + "b" * 64,
                "executorBundleFileSha256": "sha256:" + "c" * 64,
                "sourceCapsuleId": "source-capsule",
                "sourceCapsuleDigest": "sha256:" + "d" * 64,
            }],
        }

    spec = _spec()
    spec["executionPolicy"]["workerHostSetBinding"] = binding(1)
    _freeze(tmp_path, monkeypatch, spec_override=spec)
    revision = "sha256:" + "9" * 64
    entity = "/entity/地点/景区/杭州西湖"
    task = {
        "entityRef": entity,
        "carrier": "image",
        "sourceRevision": revision,
        "idempotencyKey": f"{EXECUTION_ID}|{entity}|image|{revision}|author",
        "jobId": "image-author-generation-001",
        "executionId": EXECUTION_ID,
        "ref": "杭州西湖_image",
        "stage": "author",
        "partitionKey": "untrusted",
        "maxAttempts": 3,
    }
    first = select_or_freeze_job_set_attempt(
        EXECUTION_ID,
        "author",
        active_tasks=[task],
        required_workers=1,
    )
    spec["executionPolicy"]["workerHostSetBinding"] = binding(2)
    second = select_or_freeze_job_set_attempt(
        EXECUTION_ID,
        "author",
        active_tasks=[task],
        required_workers=1,
    )
    assert second["attemptOrdinal"] == 2
    assert second["workerHostSetBinding"]["generation"] == 2
    assert second["expectedTasks"] == first["expectedTasks"]


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


def test_semantic_freeze_never_binds_delivery_worker_or_campaign_context(
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
    assert envelope["poolDeliveryBackend"] == "reliabletask"
    assert "observerBinaryRef" not in envelope
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


def test_semantic_backend_envelope_rejects_legacy_observer_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _freeze(tmp_path, monkeypatch)
    legacy = read_json(path)
    legacy["observerBinaryRef"] = "data/local/cache/worker/data-content-worker"
    legacy["observerBinarySha256"] = "sha256:" + "f" * 64
    stable = {key: value for key, value in legacy.items() if key != "envelopeDigest"}
    legacy["envelopeDigest"] = queue_backend._digest(stable)
    write_json(path, legacy)

    with pytest.raises(ValueError, match="schema violation"):
        queue_backend.load_execution_queue_backend(EXECUTION_ID)
