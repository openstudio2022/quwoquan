# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-003
from __future__ import annotations

import multiprocessing
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from quwoquan_ops.cli.lib import local_runtime_consumer_lease as leases

ARGS = dict(target="beta-local", device="device-1", consumer="client", package_name="app", ports=[18000], instance_generation="runtime-1")
DIGEST = "sha256:" + "a" * 64


def test_nonce_exact_release_and_bind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path))
    first = leases.acquire_consumer_lease(**ARGS)
    assert Path(first["path"]).is_relative_to(tmp_path)
    with pytest.raises(ValueError, match="in_use"):
        leases.acquire_consumer_lease(**ARGS)
    exact = dict(target="beta-local", device="device-1", consumer="client", lease_id=first["leaseId"], instance_generation="runtime-1")
    leases.bind_consumer_lease(**exact, handoff_digest=DIGEST)
    assert leases.release_consumer_lease(**exact)
    second = leases.acquire_consumer_lease(**ARGS)
    assert second["leaseId"] != first["leaseId"]
    with pytest.raises(ValueError, match="generation_conflict"):
        leases.release_consumer_lease(**exact)
    with pytest.raises(ValueError, match="mismatch"):
        leases.bind_consumer_lease(**exact, handoff_digest=DIGEST)
    assert "releasedAt" not in leases.list_consumer_leases("beta-local")[0]
    with pytest.raises(TypeError):
        leases.release_consumer_lease(target="beta-local", device="device-1", consumer="client")


def _acquire(root: str, start: object, result: object) -> None:
    os.environ["QWQ_DEPLOY_WORK_ROOT"] = root
    assert start.wait(10)
    try:
        result.put(leases.acquire_consumer_lease(**ARGS)["leaseId"])
    except ValueError as error:
        result.put(str(error))


def test_acquire_has_one_process_winner(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    start, result = ctx.Event(), ctx.Queue()
    workers = [ctx.Process(target=_acquire, args=(str(tmp_path), start, result)) for _ in range(2)]
    for worker in workers:
        worker.start()
    start.set()
    results = [result.get(timeout=12) for _ in workers]
    for worker in workers:
        worker.join(10)
        assert worker.exitcode == 0
    assert sum(item.startswith("sha256:") for item in results) == 1
    assert sum("in_use" in item for item in results) == 1


def test_disconnected_expired_unreleased_lease_retains_occupancy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path))
    leases.acquire_consumer_lease(**ARGS)
    monkeypatch.setattr(leases.shutil, "which", lambda _: None)
    active = leases.active_consumer_leases("beta-local", now=datetime.now(timezone.utc) + timedelta(days=2))
    assert len(active) == 1
    assert active[0]["state"] == "active_unverified"


def test_same_device_application_requires_exact_release_before_environment_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(tmp_path))
    first = leases.acquire_consumer_lease(**ARGS)
    with pytest.raises(ValueError, match="device_environment_conflict"):
        leases.acquire_consumer_lease(**{**ARGS, "target": "gamma-local", "instance_generation": "gamma-1"})
    leases.acquire_consumer_lease(**{**ARGS, "target": "gamma-local", "device": "device-2", "instance_generation": "gamma-1"})
    leases.release_consumer_lease(target="beta-local", device="device-1", consumer="client", lease_id=first["leaseId"], instance_generation="runtime-1")
    switched = leases.acquire_consumer_lease(**{**ARGS, "target": "gamma-local", "instance_generation": "gamma-1"})
    assert switched["leaseId"] != first["leaseId"]
