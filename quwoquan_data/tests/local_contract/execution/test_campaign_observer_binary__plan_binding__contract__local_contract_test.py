# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from content.execution import campaign_observer_binary as campaign_binary
from content.execution import runtime_evidence_reliabletask_process as process_port
from content.execution.campaign_workspace import CampaignRuntimePaths
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
