"""无类别内容就绪按环境配置保留 required probes，Exit 是独立显式要求。"""
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
from __future__ import annotations

import argparse

import pytest

from quwoquan_ops.cli import stackctl


@pytest.fixture
def command_context(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(stackctl, "command_health", lambda args: {"exitCode": 0, "details": []})
    monkeypatch.setattr(stackctl, "_read_json_object", lambda path: {"checks": [
        {"name": scope, "scope": scope} for scope in ("edge", "media", "content-import", "content-consumer")
    ]})
    monkeypatch.setattr(stackctl, "command_doctor", lambda args: calls.append("doctor") or {"exitCode": 0, "details": []})
    monkeypatch.setattr(stackctl, "command_product_telemetry_log_sink", lambda args: calls.append("log-sink") or {"exitCode": 0, "details": []})
    monkeypatch.setattr(stackctl, "_load_data_release_readiness", lambda **kwargs: ({"releaseId": "release-001"}, tmp_path / "readiness.json"))
    for name in ("_run_release_feed_readback_probe", "_run_release_video_delivery_probe"):
        monkeypatch.setattr(stackctl, name, lambda **kwargs: ({"status": "passed"}, tmp_path / "probe.json"))
    monkeypatch.setattr(stackctl, "_load_data_release_lifecycle_exit", lambda **kwargs: calls.append("exit") or ({"passed": True}, tmp_path / "exit.json"))
    args = argparse.Namespace(env="alpha", report_dir=str(tmp_path), release_id="release-001", verify_run_id="verify-001", manifest_digest="sha256:" + "1" * 64)
    return args, calls


def test_default_readiness_retains_public_probes_without_forcing_exit(command_context):
    args, calls = command_context
    result = stackctl.command_content_readiness(args)
    assert result["exitCode"] == 0
    assert "phase" not in result
    assert "readinessPhase" not in result
    assert calls == ["log-sink", "doctor"]
    assert {"release-bound-feed-readback", "release-video-delivery"}.issubset(result["probes"])


@pytest.mark.parametrize("environment", ["alpha", "beta", "gamma", "prod"])
def test_explicit_environment_configuration_retains_observability(command_context, environment):
    args, calls = command_context
    args.env = environment
    assert stackctl.command_content_readiness(args)["exitCode"] == 0
    assert calls == ["log-sink", "doctor"]


def test_full_verification_requires_explicit_exit(command_context):
    args, calls = command_context
    args.require_lifecycle_exit = True
    result = stackctl.command_content_readiness(args)
    assert result["exitCode"] == 2
    assert any("requires explicit lifecycleExitRef" in item for item in result["details"])


def test_explicit_exit_is_consumed(command_context):
    args, calls = command_context
    args.require_lifecycle_exit = True
    args.lifecycle_exit_ref = "env/alpha/runs/release-lifecycle-exit/release-001/exit-001/lifecycle-exit.json"
    assert stackctl.command_content_readiness(args)["exitCode"] == 0
    assert "exit" in calls


@pytest.mark.parametrize("probe", ["command_doctor", "command_product_telemetry_log_sink", "command_health"])
def test_required_probe_failure_blocks(command_context, monkeypatch, probe):
    args, _ = command_context
    monkeypatch.setattr(stackctl, probe, lambda args: {"exitCode": 2, "details": ["required probe failed"]})
    assert stackctl.command_content_readiness(args)["exitCode"] == 2


def test_missing_required_scope_blocks(command_context, monkeypatch):
    args, _ = command_context
    monkeypatch.setattr(stackctl, "_read_json_object", lambda path: {"checks": []})
    result = stackctl.command_content_readiness(args)
    assert result["exitCode"] == 2
    assert any("no probe executed" in item for item in result["details"])
