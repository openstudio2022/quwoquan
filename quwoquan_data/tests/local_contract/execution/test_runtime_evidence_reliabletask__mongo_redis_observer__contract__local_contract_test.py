from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest
from content.execution import runtime_evidence_reliabletask as observer
from content.execution import runtime_evidence_reliabletask_process as process_port
from content.execution.reliabletask_transport import ReliableTaskFleetTransport
from content.execution.runtime_evidence_contract import CARRIERS, canonical_digest


def _binary_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> process_port.ReliableTaskObserverBinaryBinding:
    output_root = tmp_path / "output"
    monkeypatch.setattr(process_port, "OUTPUT_ROOT", output_root)
    relative = Path(
        "data/local/cache/reliabletask-observer-binaries/"
        + "f" * 64
        + "/data-content-worker"
    )
    binary = output_root / relative
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"frozen-observer")
    binary.chmod(0o755)
    return process_port.ReliableTaskObserverBinaryBinding(
        ref=relative.as_posix(),
        sha256="sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest(),
    )


def _envelopes(
    binary: process_port.ReliableTaskObserverBinaryBinding,
) -> list[dict[str, object]]:
    return [
        {
            "carrier": carrier,
            "executionId": f"execution-{carrier}",
            "queueBackend": "reliabletask",
            "envelopeDigest": "sha256:" + f"{index:x}" * 64,
            "queuePolicyDigest": "sha256:" + f"{index + 4:x}" * 64,
            "executionManifestDigest": "sha256:" + f"{index + 8:x}" * 64,
            "sourceDigest": {
                "algorithm": "sha256",
                "digest": "sha256:" + "a" * 64,
                "inputs": [f"input-{carrier}"],
            },
            "targetSetDigest": f"{index + 1:x}" * 64,
            **binary.as_document(),
        }
        for index, carrier in enumerate(CARRIERS, start=1)
    ]


def _task(carrier: str) -> observer._ExpectedTask:
    return observer._ExpectedTask(
        job_id=f"job-{carrier}",
        entity_ref=f"/entity/{carrier}",
        stage="author",
        source_revision="sha256:" + "b" * 64,
    )


def _provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> observer.ReliableTaskQueueEvidenceProvider:
    monkeypatch.setattr(
        observer,
        "_expected_tasks",
        lambda carrier, execution_id: (_task(carrier),),
    )
    return observer.ReliableTaskQueueEvidenceProvider(
        envelopes=_envelopes(_binary_binding(tmp_path, monkeypatch))
    )


def _observation_document(
    provider: observer.ReliableTaskQueueEvidenceProvider,
    carrier: str,
) -> dict[str, object]:
    expected = _task(carrier)
    task = {
        **expected.as_document(),
        "status": "ready",
        "attempts": 0,
        "createdAt": "2026-08-06T08:00:00Z",
        "updatedAt": "2026-08-06T08:00:01Z",
        "nextAttemptAt": "2026-08-06T08:00:00Z",
        "leaseState": "none",
    }
    lease_rows = [
        {
            "jobId": expected.job_id,
            "status": "ready",
            "leaseState": "none",
            "leaseUntil": "",
        }
    ]
    document: dict[str, object] = {
        "schema": "quwoquan.reliabletask_execution_observation",
        "version": 1,
        "executionId": f"execution-{carrier}",
        "carrier": carrier,
        "requestBindingDigest": provider.binding.configuration_digest,
        "observedAt": "2026-08-06T08:00:02Z",
        "tasks": [task],
        "pendingJobTimestamps": ["2026-08-06T08:00:01Z"],
        "readyJobTimestamps": ["2026-08-06T08:00:01.5Z"],
        "successfulJobCount": 0,
        "terminalJobCount": 0,
        "observationWindowSeconds": 2,
        "latencyMilliseconds": [],
        "providerThrottleCount": 0,
        "stuckJobCount": 0,
        "redisEntryCount": 1,
        "redisPendingCount": 0,
        "activeLeaseCount": 0,
        "expiredLeaseCount": 0,
        "leaseEvidenceDigest": observer._canonical_digest_any(lease_rows),
    }
    document["observationDigest"] = canonical_digest(
        document,
        excluded="observationDigest",
    )
    return document


def test_reliabletask_observer_samples_exact_four_frozen_executions_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _provider(monkeypatch, tmp_path)
    transport = ReliableTaskFleetTransport(
        target="local",
        mongo_uri="mongodb://127.0.0.1:27017",
        redis_addr="127.0.0.1:6379",
    )
    monkeypatch.setattr(provider, "_transport", lambda: transport)
    calls: list[tuple[str, ...]] = []

    def run(
        command: list[str],
        *,
        cwd: object,
        environment: Mapping[str, str],
        timeout_seconds: float,
    ) -> str:
        calls.append(tuple(command))
        carrier = command[command.index("--observe-carrier") + 1]
        assert "--observe-execution" in command
        assert "--observe-binding-digest" in command
        assert environment["QWQ_DATA_FLEET_MONGO_URI"] == transport.mongo_uri
        assert environment["QWQ_DATA_FLEET_REDIS_ADDR"] == transport.redis_addr
        assert timeout_seconds > 0
        return json.dumps(
            _observation_document(provider, carrier),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    monkeypatch.setattr(observer, "run_observer_command", run)
    rows = provider.sample(
        {carrier: f"execution-{carrier}" for carrier in CARRIERS}
    )

    assert tuple(row.carrier for row in rows) == CARRIERS
    assert all(row.pending_job_timestamps for row in rows)
    assert len(calls) == 4


def test_reliabletask_observer_rejects_source_job_set_and_digest_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = _provider(monkeypatch, tmp_path)
    document = _observation_document(provider, "image")
    task = document["tasks"][0]
    assert isinstance(task, dict)
    task["sourceRevision"] = "sha256:" + "c" * 64
    document["observationDigest"] = canonical_digest(
        document,
        excluded="observationDigest",
    )

    with pytest.raises(observer.ReliableTaskObserverError) as captured:
        observer._parse_observation(
            json.dumps(document),
            target=provider._targets["image"],
            request_binding_digest=provider.binding.configuration_digest,
        )
    assert captured.value.code.endswith("FROZEN_TARGET_DRIFT")

    valid = _observation_document(provider, "image")
    valid["redisEntryCount"] = 2
    with pytest.raises(observer.ReliableTaskObserverError) as captured:
        observer._parse_observation(
            json.dumps(valid),
            target=provider._targets["image"],
            request_binding_digest=provider.binding.configuration_digest,
        )
    assert captured.value.code.endswith("DIGEST_DRIFT")


def test_observer_process_has_hard_deadline_and_does_not_echo_stderr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    terminated: list[object] = []

    class TimeoutProcess:
        pid = 12345
        returncode = None

        def communicate(self, timeout: float) -> tuple[str, str]:
            raise subprocess.TimeoutExpired(["observer"], timeout)

        def poll(self) -> None:
            return None

    monkeypatch.setattr(
        process_port.subprocess,
        "Popen",
        lambda *args, **kwargs: TimeoutProcess(),
    )
    monkeypatch.setattr(
        process_port,
        "_terminate_observer_process",
        lambda process: terminated.append(process),
    )
    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.run_observer_command(
            ["observer"],
            cwd=tmp_path,  # type: ignore[arg-type]
            environment={},
            timeout_seconds=0.01,
        )
    assert captured.value.code.endswith("DEADLINE_EXCEEDED")
    assert terminated

    class FailedProcess:
        pid = 12346
        returncode = 7

        def communicate(self, timeout: float) -> tuple[str, str]:
            return "", "mongodb://user:secret@private:27017"

        def poll(self) -> int:
            return 7

    monkeypatch.setattr(
        process_port.subprocess,
        "Popen",
        lambda *args, **kwargs: FailedProcess(),
    )
    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.run_observer_command(
            ["observer"],
            cwd=tmp_path,  # type: ignore[arg-type]
            environment={},
            timeout_seconds=1,
        )
    assert captured.value.code.endswith("PROCESS_FAILED")
    assert "secret" not in str(captured.value)
    assert "mongodb" not in str(captured.value)

    def spawn_failure(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("/private/secret/attacker-selected-binary")

    monkeypatch.setattr(process_port.subprocess, "Popen", spawn_failure)
    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.run_observer_command(
            ["observer"],
            cwd=tmp_path,  # type: ignore[arg-type]
            environment={},
            timeout_seconds=1,
        )
    assert captured.value.code.endswith("SPAWN_FAILED")
    assert "private" not in str(captured.value)
    assert "attacker" not in str(captured.value)


def test_observer_environment_cannot_select_backend_binary_or_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("QWQ_OBJECT_QUEUE_BACKEND", "local_file")
    monkeypatch.setenv("QWQ_DATA_FLEET_BINARY", "/tmp/fake-observer")
    monkeypatch.setenv("QWQ_DATA_FLEET_MONGO_DATABASE", "foreign")
    monkeypatch.setenv("QWQ_DATA_FLEET_REDIS_PASSWORD", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")
    monkeypatch.setenv("CURSOR_API_KEY", "cursor-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "cloud-secret")
    monkeypatch.setenv("PATH", "/tmp/attacker-selected-bin")
    monkeypatch.setattr(process_port, "OUTPUT_ROOT", tmp_path / "output")
    transport = ReliableTaskFleetTransport(
        target="local",
        mongo_uri="mongodb://127.0.0.1:27017",
        redis_addr="127.0.0.1:6379",
    )

    environment = process_port.observer_environment(transport)

    assert environment["QWQ_DATA_FLEET_MONGO_URI"] == transport.mongo_uri
    assert environment["QWQ_DATA_FLEET_REDIS_ADDR"] == transport.redis_addr
    assert "QWQ_OBJECT_QUEUE_BACKEND" not in environment
    assert "QWQ_DATA_FLEET_BINARY" not in environment
    assert "QWQ_DATA_FLEET_MONGO_DATABASE" not in environment
    assert "QWQ_DATA_FLEET_REDIS_PASSWORD" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert "CURSOR_API_KEY" not in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "PATH" not in environment
    assert set(environment) == {
        "HOME",
        "XDG_CACHE_HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "TZ",
        "QWQ_DATA_FLEET_MONGO_URI",
        "QWQ_DATA_FLEET_REDIS_ADDR",
    }


def test_fleet_command_prefers_frozen_worker_over_inherited_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from content.execution import reliabletask_fleet

    binary = tmp_path / "data-content-worker"
    binary.write_bytes(b"frozen-worker")
    binary.chmod(0o500)
    binding = process_port.ReliableTaskObserverBinaryBinding(
        ref="data/local/cache/reliabletask-observer-binaries/"
        + "a" * 64
        + "/data-content-worker",
        sha256="sha256:" + "b" * 64,
    )
    monkeypatch.setenv(process_port.OBSERVER_BINARY_REF_ENV, binding.ref)
    monkeypatch.setenv(process_port.OBSERVER_BINARY_SHA256_ENV, binding.sha256)
    monkeypatch.setenv("QWQ_DATA_FLEET_BINARY", "/tmp/untrusted-worker")
    monkeypatch.setattr(
        reliabletask_fleet,
        "load_frozen_observer_binary_binding",
        lambda: binding,
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "validate_frozen_observer_binary",
        lambda candidate: binary if candidate == binding else pytest.fail("binding drift"),
    )

    command, cwd = reliabletask_fleet._fleet_command()

    assert command == [str(binary)]
    assert cwd == reliabletask_fleet.REPO_ROOT


def test_observer_command_never_uses_go_path_or_cold_build_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding = _binary_binding(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", "/tmp/no-go-here")
    monkeypatch.setattr(process_port, "which", lambda executable: None)

    command, cwd = process_port.observer_command(binding)

    assert command == [
        str(process_port.OUTPUT_ROOT / binding.ref),
    ]
    assert cwd == process_port.REPO_ROOT / "quwoquan_service"
    assert "go" not in command
    assert "run" not in command


def test_observer_command_rejects_digest_mode_and_symlink_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding = _binary_binding(tmp_path, monkeypatch)
    binary = process_port.OUTPUT_ROOT / binding.ref
    binary.write_bytes(b"tampered")
    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.observer_command(binding)
    assert captured.value.code.endswith("BINARY_DIGEST_DRIFT")

    binary.write_bytes(b"frozen-observer")
    binary.chmod(0o644)
    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.observer_command(binding)
    assert captured.value.code.endswith("BINARY_UNSAFE")

    binary.unlink()
    target = tmp_path / "foreign-worker"
    target.write_bytes(b"frozen-observer")
    target.chmod(0o755)
    binary.symlink_to(target)
    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.observer_command(binding)
    assert captured.value.code.endswith("BINARY_UNSAFE")


def test_observer_binary_prepare_reuses_one_content_addressed_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    source_digest = "sha256:" + "a" * 64
    monkeypatch.setattr(process_port, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(
        process_port,
        "_observer_source_digest",
        lambda: source_digest,
    )
    ref = process_port._binary_cache_ref(source_digest)
    binary = output_root / ref
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"deterministic-observer")
    binary.chmod(0o755)
    monkeypatch.setattr(
        process_port,
        "which",
        lambda executable: pytest.fail("existing binding must not invoke Go"),
    )

    first = process_port.prepare_controller_observer_binary()
    second = process_port.prepare_controller_observer_binary()

    assert first == second
    assert first.binding.ref == ref
    assert first.binding.sha256 == (
        "sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    assert first.source_digest == source_digest
    assert first.build_attestation_digest.startswith("sha256:")


def test_observer_binary_prepare_accepts_controller_prebound_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding = _binary_binding(tmp_path, monkeypatch)
    monkeypatch.setenv(process_port.OBSERVER_BINARY_REF_ENV, binding.ref)
    monkeypatch.setenv(process_port.OBSERVER_BINARY_SHA256_ENV, binding.sha256)
    monkeypatch.setattr(
        process_port,
        "_validate_prebound_campaign_context",
        lambda: None,
    )
    monkeypatch.setattr(
        process_port,
        "_observer_source_digest",
        lambda: pytest.fail("frozen capsule must not scan Service source"),
    )

    assert process_port.load_frozen_observer_binary_binding() == binding


@pytest.mark.parametrize(
    ("ref", "sha256"),
    [
        (
            "data/local/cache/reliabletask-observer-binaries/"
            + "f" * 64
            + "/data-content-worker",
            "",
        ),
        ("", "sha256:" + "f" * 64),
    ],
)
def test_observer_binary_prepare_rejects_partial_controller_binding(
    monkeypatch: pytest.MonkeyPatch,
    ref: str,
    sha256: str,
) -> None:
    monkeypatch.setenv(process_port.OBSERVER_BINARY_REF_ENV, ref)
    monkeypatch.setenv(process_port.OBSERVER_BINARY_SHA256_ENV, sha256)

    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.load_frozen_observer_binary_binding()

    assert captured.value.code.endswith("BINARY_BINDING_INVALID")


def test_observer_binary_prepare_rejects_unfenced_direct_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    binding = _binary_binding(tmp_path, monkeypatch)
    monkeypatch.setenv(process_port.OBSERVER_BINARY_REF_ENV, binding.ref)
    monkeypatch.setenv(process_port.OBSERVER_BINARY_SHA256_ENV, binding.sha256)

    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.load_frozen_observer_binary_binding()

    assert captured.value.code.endswith("BINARY_BINDING_INVALID")
    assert "campaign fence" in str(captured.value)
