# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from content.execution.campaign import observer_binary as campaign_binary
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.runtime_evidence import reliabletask_process as process_port
from core.io import read_json

ROOT_ID = "20260805--travel-homepage-m3--china--scale-013"


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output_root = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output_root,
        publish_root=tmp_path / "publish",
        campaigns_root=(
            output_root
            / "data/local/workspace/content-campaign-submissions"
        ),
        workspaces_root=output_root / "data/local/cache/campaign-workspaces",
    )


def _prepared(
    runtime: CampaignRuntimePaths,
    monkeypatch: pytest.MonkeyPatch,
) -> process_port.PreparedReliableTaskObserverBinary:
    source_digest = "sha256:" + "a" * 64
    ref = (
        "data/local/cache/reliabletask-observer-binaries/"
        + "a" * 64
        + "/data-content-worker"
    )
    binary = runtime.output_root / ref
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"campaign-observer")
    binary.chmod(0o755)
    monkeypatch.setattr(process_port, "OUTPUT_ROOT", runtime.output_root)
    binding = process_port.ReliableTaskObserverBinaryBinding(
        ref=ref,
        sha256="sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest(),
    )
    return process_port.PreparedReliableTaskObserverBinary(
        binding=binding,
        source_digest=source_digest,
        build_attestation_digest=process_port.observer_build_attestation_digest(
            source_digest=source_digest,
            binding=binding,
        ),
    )


def test_campaign_observer_binary_is_create_once_and_plan_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    prepared = _prepared(runtime, monkeypatch)
    calls = 0

    def prepare() -> process_port.PreparedReliableTaskObserverBinary:
        nonlocal calls
        calls += 1
        return prepared

    first = campaign_binary.resolve_campaign_observer_binary(
        runtime,
        ROOT_ID,
        plan_digest="sha256:" + "b" * 64,
        preparer=prepare,
    )
    second = campaign_binary.resolve_campaign_observer_binary(
        runtime,
        ROOT_ID,
        plan_digest="sha256:" + "b" * 64,
        preparer=lambda: pytest.fail("resume must not rebuild observer"),
    )

    assert first == second == prepared.binding
    assert calls == 1
    envelope = read_json(
        campaign_binary.campaign_observer_binary_path(runtime, ROOT_ID)
    )
    assert envelope["observerSourceDigest"] == prepared.source_digest
    assert envelope["observerBuildAttestationDigest"] == (
        prepared.build_attestation_digest
    )

    with pytest.raises(ValueError, match="plan digest drift"):
        campaign_binary.resolve_campaign_observer_binary(
            runtime,
            ROOT_ID,
            plan_digest="sha256:" + "c" * 64,
            preparer=lambda: pytest.fail("drift must not rebuild observer"),
        )


def test_controller_prepare_rejects_inherited_lane_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(process_port.OBSERVER_BINARY_REF_ENV, "stale-ref")
    monkeypatch.setenv(
        process_port.OBSERVER_BINARY_SHA256_ENV,
        "sha256:" + "d" * 64,
    )
    monkeypatch.setattr(
        process_port,
        "_observer_source_digest",
        lambda: pytest.fail("controller must reject env before source build"),
    )

    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.prepare_controller_observer_binary()

    assert captured.value.code.endswith("CONTROLLER_ENV_INVALID")


def test_capsule_missing_binding_never_scans_service_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(process_port.OBSERVER_BINARY_REF_ENV, raising=False)
    monkeypatch.delenv(process_port.OBSERVER_BINARY_SHA256_ENV, raising=False)
    monkeypatch.setattr(
        process_port,
        "_observer_source_digest",
        lambda: pytest.fail("capsule must not scan absent Service source"),
    )

    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.load_frozen_observer_binary_binding()

    assert captured.value.code.endswith("BINARY_BINDING_MISSING")


def test_central_lane_context_is_accepted_only_when_plan_and_fence_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.execution.campaign import runtime as campaign_runtime
    from content.execution.campaign import workspace as campaign_workspace

    runtime = _runtime(tmp_path)
    carrier = "homepage"
    execution_id = ROOT_ID
    values = {
        "root_execution_id": ROOT_ID,
        "run_id": "campaign-run-001",
        "generation": "4",
        "fencing_token": "sha256:" + "1" * 64,
        "carrier": carrier,
        "execution_id": execution_id,
        "source_revision": "sha256:" + "2" * 64,
        "source_digest": "sha256:" + "3" * 64,
        "entity_catalog_digest": "sha256:" + "4" * 64,
    }
    plan = {
        "rootExecutionId": ROOT_ID,
        "executionMode": "central",
        "sourceRevision": values["source_revision"],
        "sourceDigest": values["source_digest"],
        "entityCatalogDigest": values["entity_catalog_digest"],
        "executionIds": {carrier: execution_id},
    }
    plan["planDigest"] = process_port._canonical_digest(
        plan,
        excluded="planDigest",
    )
    values["plan_digest"] = str(plan["planDigest"])
    for name, environment_name in process_port._CAMPAIGN_CONTEXT_ENV.items():
        monkeypatch.setenv(environment_name, values[name])
    monkeypatch.setattr(
        campaign_workspace.CampaignRuntimePaths,
        "defaults",
        classmethod(lambda cls: runtime),
    )
    monkeypatch.setattr(process_port, "read_json", lambda _path: plan)
    monkeypatch.setattr(process_port, "assert_valid", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        campaign_runtime,
        "assert_campaign_fence",
        lambda *args, **kwargs: {"status": "active", "finishedAt": None},
    )
    monkeypatch.setattr(
        campaign_runtime,
        "read_lane_checkpoint",
        lambda *args, **kwargs: {
            "runId": values["run_id"],
            "generation": int(values["generation"]),
            "fencingToken": values["fencing_token"],
            "executionId": execution_id,
            "carrier": carrier,
            "status": "running",
            "pid": os.getpid(),
        },
    )

    context = process_port.load_frozen_campaign_observer_context()

    assert context.generation == 4
    assert context.source_digest == values["source_digest"]

    monkeypatch.setenv(
        process_port._CAMPAIGN_CONTEXT_ENV["source_digest"],
        "sha256:" + "9" * 64,
    )
    with pytest.raises(process_port.ReliableTaskObserverError) as captured:
        process_port.load_frozen_campaign_observer_context()
    assert captured.value.code.endswith("BINARY_BINDING_INVALID")


def test_distributed_lane_context_uses_claim_instead_of_frozen_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.execution.campaign import lane_claim
    from content.execution.campaign import runtime as campaign_runtime
    from content.execution.campaign import workspace as campaign_workspace

    runtime = _runtime(tmp_path)
    carrier = "homepage"
    execution_id = ROOT_ID
    values = {
        "root_execution_id": ROOT_ID,
        "run_id": "campaign-run-002",
        "generation": "5",
        "fencing_token": "sha256:" + "5" * 64,
        "carrier": carrier,
        "execution_id": execution_id,
        "source_revision": "sha256:" + "6" * 64,
        "source_digest": "sha256:" + "7" * 64,
        "entity_catalog_digest": "sha256:" + "8" * 64,
    }
    plan = {
        "rootExecutionId": ROOT_ID,
        "executionMode": "distributed",
        "sourceRevision": values["source_revision"],
        "sourceDigest": values["source_digest"],
        "entityCatalogDigest": values["entity_catalog_digest"],
        "executionIds": {carrier: execution_id},
        "distributedRun": {
            "campaignRunId": values["run_id"],
            "campaignGeneration": int(values["generation"]),
            "campaignFencingToken": values["fencing_token"],
        },
    }
    plan["planDigest"] = process_port._canonical_digest(
        plan,
        excluded="planDigest",
    )
    values["plan_digest"] = str(plan["planDigest"])
    for name, environment_name in process_port._CAMPAIGN_CONTEXT_ENV.items():
        monkeypatch.setenv(environment_name, values[name])
    monkeypatch.setattr(
        campaign_workspace.CampaignRuntimePaths,
        "defaults",
        classmethod(lambda cls: runtime),
    )
    monkeypatch.setattr(process_port, "read_json", lambda _path: plan)
    monkeypatch.setattr(process_port, "assert_valid", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        campaign_runtime,
        "assert_campaign_fence",
        lambda *args, **kwargs: {
            "status": "frozen",
            "finishedAt": "2026-08-07T10:02:28Z",
        },
    )
    monkeypatch.setattr(
        campaign_runtime,
        "read_lane_checkpoint",
        lambda *args, **kwargs: {
            "runId": values["run_id"],
            "generation": int(values["generation"]),
            "fencingToken": values["fencing_token"],
            "executionId": execution_id,
            "carrier": carrier,
            "status": "ready",
            "pid": 1,
        },
    )
    monkeypatch.setattr(
        lane_claim,
        "read_lane_claim",
        lambda *args, **kwargs: {
            "campaignRunId": values["run_id"],
            "campaignGeneration": int(values["generation"]),
            "campaignFencingToken": values["fencing_token"],
            "executionId": execution_id,
            "carrier": carrier,
            "status": "running",
            "pid": os.getpid(),
        },
    )

    context = process_port.load_frozen_campaign_observer_context()

    assert context.run_id == values["run_id"]
    assert context.execution_id == execution_id
