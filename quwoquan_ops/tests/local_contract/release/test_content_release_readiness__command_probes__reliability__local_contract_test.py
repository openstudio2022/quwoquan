"""无类别内容就绪按环境配置保留 required probes，Exit 是独立显式要求。"""
# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-004
from __future__ import annotations

import argparse

import pytest

from quwoquan_ops.cli.lib import runtime_container_liveness

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
    bounded_startup = {
        "status": "running", "workload": "full",
        "attemptId": "startup-001", "candidateDigest": "sha256:" + "a" * 64,
        "providerRuntimeDigest": "sha256:" + "b" * 64,
    }
    monkeypatch.setattr(
        stackctl, "load_workload_startup_attempt",
        lambda _target, workload: bounded_startup if workload == "full" else None,
    )
    monkeypatch.setattr(
        stackctl, "active_deployment_candidate_snapshot",
        lambda _target: {"baselineId": "sha256:" + "a" * 64},
    )
    monkeypatch.setattr(
        runtime_container_liveness, "verify_running_receipt_liveness",
        lambda *_args, **_kwargs: type("Liveness", (), {"status": "healthy", "issues": lambda self: []})(),
    )
    for name in ("_run_release_feed_readback_probe", "_run_release_video_delivery_probe"):
        monkeypatch.setattr(stackctl, name, lambda **kwargs: ({"status": "passed"}, tmp_path / "probe.json"))
    monkeypatch.setattr(stackctl, "_load_data_release_lifecycle_exit", lambda **kwargs: calls.append("exit") or ({"passed": True}, tmp_path / "exit.json"))
    args = argparse.Namespace(env="alpha", report_dir=str(tmp_path), release_id="release-001", verify_run_id="verify-001", manifest_digest="sha256:" + "1" * 64)
    return args, calls


@pytest.mark.parametrize(
    "fault",
    ["", "empty", "skipped", "failed", "wrong-candidate", "missing-provider", "test-live", "stopped", "unhealthy"],
)
def test_import_prerequisite_requires_exact_policy_runtime(command_context, monkeypatch, fault):
    args, calls = command_context
    args.action = "import"
    monkeypatch.setattr(
        stackctl,
        "command_health",
        lambda a: {"exitCode": 1, "details": ["formal availability remains blocked"]},
    )
    startup = {
        "status": "running", "workload": "full",
        "attemptId": "startup-001", "candidateDigest": "sha256:" + "a" * 64,
        "providerRuntimeDigest": "sha256:" + "b" * 64,
    }
    if fault == "stopped":
        startup["status"] = "stopped"
    if fault == "missing-provider":
        startup["providerRuntimeDigest"] = ""
    requested_workloads = []

    def _load_policy_startup(_target, workload):
        requested_workloads.append(workload)
        return startup if workload == "full" and fault != "test-live" else None

    monkeypatch.setattr(
        stackctl, "load_workload_startup_attempt", _load_policy_startup,
    )
    if fault == "unhealthy":
        monkeypatch.setattr(
            runtime_container_liveness,
            "verify_running_receipt_liveness",
            lambda *_args, **_kwargs: type(
                "Liveness",
                (),
                {
                    "status": "unhealthy",
                    "issues": lambda self: ["compose service is not running"],
                },
            )(),
        )
    candidate = "sha256:" + ("c" if fault == "wrong-candidate" else "a") * 64
    monkeypatch.setattr(
        stackctl, "active_deployment_candidate_snapshot",
        lambda _target: {"baselineId": candidate},
    )
    checks = [
        {"name": scope, "scope": "content-import", "ok": True, "skipped": False}
        for scope in ("content-service", "entity-service", "search-service")
    ]
    if fault == "empty":
        checks = []
    elif fault in {"skipped", "failed"}:
        checks[0]["skipped" if fault == "skipped" else "ok"] = fault == "skipped"
    report = {
        "target": "alpha-local", "generationIssues": [], "checks": checks,
        "evidenceEnvelope": {
            "candidateDigest": {"status": "executed", "value": "sha256:" + "a" * 64},
            "startupAttemptId": {"status": "executed", "value": "startup-001"},
        },
    }
    monkeypatch.setattr(stackctl, "_read_json_object", lambda path: report)
    monkeypatch.setattr(
        stackctl, "_load_data_release_readiness",
        lambda **k: pytest.fail("导入前不得要求导入后内容"),
    )
    result = stackctl.command_content_readiness(args)
    assert result["exitCode"] == (2 if fault else 0)
    assert result["contentAcceptance"] == "not_evaluated"
    assert result["healthExitCode"] == 1
    assert result["workload"] == "full"
    assert requested_workloads == ["full"]
    assert calls == []


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
